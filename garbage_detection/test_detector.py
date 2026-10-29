import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from detector import Detector, inspection_windows, merge_candidates, touches_crop_edge
from inference_worker import InferenceWorker


class DetectorTests(unittest.TestCase):
    def test_uniform_image_is_rejected_before_model_loading(self):
        detector = Detector("unused")
        with patch.object(detector, "load") as load:
            with self.assertRaisesRegex(ValueError, "纯色"):
                detector.infer(Image.new("RGB", (1280, 720), "white"))
            load.assert_not_called()

    def test_detail_crops_cover_image_and_overlap(self):
        windows = inspection_windows(2000, 1000, True)
        self.assertEqual(len(windows), 5)
        self.assertEqual(windows[0], (0, 0, 2000, 1000))
        self.assertEqual(windows[-1], (800, 400, 2000, 1000))
        self.assertGreater(windows[1][2], windows[2][0])
        self.assertEqual(len(inspection_windows(200, 200, True)), 1)
        self.assertEqual(len(inspection_windows(2000, 1000, False)), 1)

    def test_overlapping_tiles_do_not_duplicate_targets(self):
        a = {"label": "纸屑", "confidence": .8, "bbox": [100, 100, 200, 200]}
        duplicate = {"label": "塑料袋", "confidence": .6, "bbox": [105, 100, 200, 205]}
        separate = {"label": "瓶子", "confidence": .7, "bbox": [500, 500, 600, 700]}
        self.assertEqual(merge_candidates([duplicate, separate, a]), [a, separate])

    def test_timeout_kills_worker_and_allows_retry(self):
        worker = InferenceWorker(".runtime/grounding-dino-tiny")
        with patch.object(worker, "load"), patch("inference_worker.subprocess.run") as run:
            run.side_effect = subprocess.TimeoutExpired("worker", 120)
            with self.assertRaisesRegex(RuntimeError, "120 秒"):
                worker.infer(Image.new("RGB", (30, 30)))
            self.assertEqual(run.call_args.kwargs["timeout"], 120)
            run.side_effect = None
            run.return_value = subprocess.CompletedProcess([], 0, stdout=b'{"has_garbage":false,"device":"cpu"}', stderr=b'')
            self.assertFalse(worker.infer(Image.new("RGB", (30, 30)))["has_garbage"])
            run.return_value.stdout = b'{"error":"invalid image"}'
            with self.assertRaisesRegex(ValueError, "invalid image"):
                worker.infer(Image.new("RGB", (30, 30)))

    def test_crops_preserve_complete_targets_and_original_image_edges(self):
        full = {"label": "纸屑", "confidence": .3, "bbox": [700, 400, 900, 700], "full_frame": True}
        crop = {"label": "塑料袋", "confidence": .8, "bbox": [705, 405, 900, 700]}
        self.assertEqual(merge_candidates([crop, full]), [full])
        self.assertTrue(touches_crop_edge([100, 100, 600, 400], (0, 0, 600, 600), (1000, 1000)))
        self.assertFalse(touches_crop_edge([100, 100, 599, 400], (400, 0, 1000, 600), (1000, 1000)))
        self.assertFalse(touches_crop_edge([0, 0, 999, 999], (0, 0, 1000, 1000), (1000, 1000)))

    def test_overlapping_categories_keep_highest_scoring_full_frame_label(self):
        bottle = {"label": "瓶罐类", "confidence": .4, "bbox": [100, 100, 300, 400], "full_frame": True, "priority": 0}
        cup = {"label": "一次性杯", "confidence": .9, "bbox": [101, 101, 300, 400], "full_frame": True, "priority": 1}
        tissue = {"label": "纸巾", "confidence": .5, "bbox": [600, 600, 700, 700], "full_frame": True, "priority": 1}
        self.assertEqual(merge_candidates([cup, tissue, bottle]), [cup, tissue])
        bottle["confidence"] = .95
        self.assertEqual(merge_candidates([cup, tissue, bottle]), [bottle, tissue])


if __name__ == "__main__":
    unittest.main()
