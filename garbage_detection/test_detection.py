import threading
import time
import unittest
import errno
from unittest.mock import patch

import numpy as np

from detector import validate_result
from server import Camera, Service, main


class DetectionTests(unittest.TestCase):
    def test_camera_recovers_after_failed_open_and_clears_disconnected_frames(self):
        from unittest.mock import Mock
        import cv2
        camera = Camera("rtsp://user:password@private.invalid", "camera_1")
        first, second = Mock(), Mock()
        first.open.return_value = False
        second.open.return_value = True
        frame = np.zeros((20, 30, 3), dtype=np.uint8)
        observed = []

        def encode(*args):
            return True, np.array([1, 2, 3], dtype=np.uint8)

        def wait(delay):
            observed.append(camera.frame)
            if len(observed) == 2:
                camera.stop.set()

        def read():
            # The first frame is published before the next read discovers disconnection.
            if second.read.call_count == 2:
                self.assertEqual(camera.snapshot()[1], bytes([1, 2, 3]))
                return False, None
            return True, frame

        second.read.side_effect = read
        with patch.object(cv2, "VideoCapture", side_effect=[first, second]), \
                patch.object(cv2, "imencode", side_effect=encode), \
                patch.object(camera.stop, "wait", side_effect=wait):
            camera.run()
        first.release.assert_called_once()
        second.release.assert_called_once()
        self.assertEqual(len(observed), 2)
        self.assertIsNone(camera.frame)
        self.assertIsNone(camera.jpeg)
        with self.assertRaisesRegex(RuntimeError, "读取中断"):
            camera.snapshot()
        self.assertNotIn("password", camera.error)

    def test_occupied_port_has_actionable_message(self):
        with patch.dict("os.environ", {"GARBAGE_RTSP_URL": "rtsp://private.invalid", "GARBAGE_PORT": "23071", "GARBAGE_RTSP_TRANSPORT": "udp"}):
            with patch("server.ThreadingHTTPServer", side_effect=OSError(errno.EADDRINUSE, "Address already in use")):
                with self.assertRaises(SystemExit) as error:
                    main()
                self.assertIn("端口 23071 已被占用", str(error.exception))
                self.assertIn("无需重复启动", str(error.exception))
            with patch("server.ThreadingHTTPServer", side_effect=OSError(errno.EACCES, "Permission denied")):
                with self.assertRaises(OSError):
                    main()

    def test_locations_use_box_center_and_image_coordinates(self):
        data = validate_result('''```json
        {"has_garbage":true,"targets":[
          {"label":"纸屑","confidence":0.8,"bbox":[0,700,200,1000]},
          {"label":"瓶子","confidence":0.7,"bbox":[400,400,600,600]}]}
        ```''')
        self.assertEqual([t["region_id"] for t in data["targets"]], ["r3c1", "r2c2"])
        self.assertEqual(data["targets"][0]["region_name"], "左下")

    def test_malformed_results_are_errors_not_clear_frames(self):
        invalid = ["not json", '{"has_garbage":"false"}',
                   '{"has_garbage":false,"targets":[{"label":"瓶子","confidence":0.5,"bbox":[0,0,30,30]}]}']
        for box in ([400, 0, 100, 20], [-1, 0, 100, 100], [0, 0, 1001, 100], [True, 0, 100, 100]):
            import json
            invalid.append(json.dumps({"has_garbage": True, "targets": [
                {"label": "纸屑", "confidence": 0.9, "bbox": box}]}))
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                validate_result(raw)
        self.assertTrue(validate_result('{"has_garbage":true}')['unlocalized'])
        self.assertFalse(validate_result('{"has_garbage":false,"targets":[]}')['has_garbage'])

    def test_classification_only_output_never_invents_locations(self):
        result = validate_result('{"has_garbage":true,"targets":["纸屑","塑料袋"]}')
        self.assertTrue(result["unlocalized"])
        self.assertEqual(result["targets"][0]["label"], "纸屑")
        for target in result["targets"]:
            self.assertIsNone(target["bbox"])
            self.assertIsNone(target["region_id"])
            self.assertIsNone(target["confidence"])

    def camera(self):
        from PIL import Image
        import io
        camera = Camera("rtsp://private.invalid")
        camera.frame = np.zeros((20, 30, 3), dtype=np.uint8)
        jpg = io.BytesIO()
        Image.new("RGB", (30, 20)).save(jpg, "JPEG")
        camera.jpeg, camera.captured_at = jpg.getvalue(), "2026-10-19T00:00:00+00:00"
        camera.arrived, camera.error = time.monotonic(), None
        return camera

    def test_duplicate_job_rejected_and_snapshot_stays_paired(self):
        ready, release = threading.Event(), threading.Event()

        class FakeDetector:
            device = "cpu"
            def load(self):
                ready.set()
                if not release.wait(5):
                    raise RuntimeError("test timeout")
            def infer(self, image):
                self.size = image.size
                return validate_result('{"has_garbage":false,"targets":[]}')

        camera, detector = self.camera(), FakeDetector()
        service = Service(camera, detector)
        job = service.start()
        self.assertTrue(ready.wait(2))
        try:
            self.assertIsNone(service.start())
            camera.frame = np.zeros((100, 100, 3), dtype=np.uint8)
            camera.captured_at = "later"
        finally:
            release.set()
        deadline = time.monotonic() + 3
        while service.status()["job"]["state"] in ("loading", "running") and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(service.job["state"], "done")
        self.assertEqual(service.result["id"], job)
        self.assertEqual(service.result["image_width"], 30)
        self.assertEqual(detector.size, (30, 20))
        self.assertNotEqual(service.result["captured_at"], "later")
        self.assertFalse(service.result["map_calibrated"])

    def test_stale_camera_cannot_start_detection(self):
        camera = self.camera()
        camera.arrived -= 11
        with self.assertRaises(RuntimeError):
            camera.snapshot()

    def test_inference_failure_is_visible(self):
        class BrokenDetector:
            device = "cpu"
            def load(self):
                raise RuntimeError("模型加载失败")
        service = Service(self.camera(), BrokenDetector())
        service.detect("test", service.camera.jpeg, "test")
        self.assertEqual(service.job["state"], "error")
        self.assertEqual(service.job["error"], "模型加载失败")
        self.assertIsNone(service.result)

    def test_camera_selection_keeps_snapshot_and_identity_paired(self):
        from unittest.mock import Mock
        first, fourth = self.camera(), self.camera()
        first.id, fourth.id = "camera_1", "camera_4"
        first.name, fourth.name = "摄像头 1", "摄像头 4"
        fourth.captured_at = "fourth-frame"
        detector = Mock(device="cpu")
        detector.infer.return_value = {"has_garbage": False, "targets": []}
        service = Service({first.id: first, fourth.id: fourth}, detector)
        with patch("server.threading.Thread") as thread:
            job = service.start(camera_id="camera_4")
            args = thread.call_args.kwargs["args"]
            self.assertEqual(service.job["camera_id"], "camera_4")
            self.assertIsNone(service.start(camera_id="camera_1"))
        # Another viewer can select camera 1 while camera 4's frozen image is being analyzed.
        self.assertEqual(service.status("camera_1")["camera"]["id"], "camera_1")
        fourth.captured_at = "later"
        service.detect(*args)
        self.assertEqual(service.result["id"], job)
        self.assertEqual(service.result["camera_id"], "camera_4")
        self.assertEqual(service.result["captured_at"], "fourth-frame")

    def test_offline_or_unknown_camera_never_uses_another_feed(self):
        camera = self.camera()
        offline = Camera("rtsp://secret.invalid", "camera_2")
        service = Service({camera.id: camera, offline.id: offline}, object())
        with self.assertRaisesRegex(RuntimeError, "摄像头 2"):
            service.start(camera_id="camera_2")
        with self.assertRaisesRegex(ValueError, "编号"):
            service.start(camera_id="camera_9")
        self.assertEqual(service.job["state"], "idle")

    def test_camera_status_is_per_request_and_does_not_expose_credentials(self):
        import json
        from unittest.mock import Mock
        online = self.camera()
        offline = Camera("rtsp://user:password@private.invalid", "camera_2")
        service = Service({online.id: online, offline.id: offline}, Mock(device="cpu"))
        state = service.status("camera_2")
        self.assertFalse(state["camera"]["online"])
        self.assertTrue(service.status("camera_3")["camera"]["online"])
        self.assertEqual(len(state["cameras"]), 2)
        self.assertEqual(len(state["categories"]), 14)
        self.assertNotIn("password", json.dumps(state))


if __name__ == "__main__":
    unittest.main()
