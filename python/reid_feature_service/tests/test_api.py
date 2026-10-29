"""API tests use synthetic images and an injected extractor; no model or DB needed."""

import asyncio
import hashlib
import json
import threading
import unittest
from io import BytesIO
from unittest.mock import Mock

import httpx
import numpy as np
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image, ImageOps

from reid_feature_service.server import PersonDetector, Settings, create_app


def picture(color="red", size=(16, 32), format="PNG"):
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format=format)
    return buffer.getvalue()


class FakeExtractor:
    embedding_dim = 3
    feature_space_id = "test-space"
    definition_text = '{"weights":"synthetic","preprocess":"test"}'
    definition_sha256 = hashlib.sha256(definition_text.encode()).hexdigest()
    device = "cpu"
    loads = 0

    def __init__(self, settings):
        type(self).loads += 1

    def extract_features(self, images):
        return np.array([np.asarray(image, dtype=np.float32).mean(axis=(0, 1)) + 1 for image in images])


class ApiTests(unittest.TestCase):
    def setUp(self):
        FakeExtractor.loads = 0
        self.app = create_app(Settings(sample_frames=2), FakeExtractor)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def image(self, data=None, metadata="{}"):
        return self.client.post("/v1/reid/image-features", files={
            "file": ("person.png", picture() if data is None else data, "image/png")},
            data={"metadata": metadata})

    def test_health_and_repeated_requests_share_one_model(self):
        health = self.client.get("/health").json()
        self.assertTrue(health["ready"])
        self.assertEqual(health["definition_text"], FakeExtractor.definition_text)
        self.assertEqual(health["definition_sha256"], hashlib.sha256(health["definition_text"].encode()).hexdigest())
        self.assertEqual(health["definition_version"], "1")
        first, second = self.image().json(), self.image().json()
        np.testing.assert_array_equal(first["embedding"], second["embedding"])
        self.assertAlmostEqual(np.linalg.norm(first["embedding"]), 1, places=6)
        self.assertEqual(first["persistence_status"], "not_requested")
        self.assertEqual(FakeExtractor.loads, 1)

    def test_tracklet_equals_manually_pooled_single_images(self):
        data = [picture("red"), picture("blue")]
        singles = [self.image(image).json()["embedding"] for image in data]
        expected = np.mean(singles, axis=0)
        expected /= np.linalg.norm(expected)
        response = self.client.post("/v1/reid/tracklet-features", files=[
            ("files", (f"{i}.png", image, "image/png")) for i, image in enumerate(data)
        ], data={"metadata": json.dumps({"frame_ids": ["f1", "f2"], "camera_id": "c1", "track_id": "7"})})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        np.testing.assert_allclose(result["embedding"], expected, atol=1e-6)
        self.assertEqual(result["selected_frame_ids"], ["f1", "f2"])
        self.assertEqual(result["source"], {"camera_id": "c1", "track_id": "7"})

    def test_one_frame_tracklet_equals_image(self):
        track = self.client.post("/v1/reid/tracklet-features", files=[
            ("files", ("a.png", picture(), "image/png"))]).json()
        np.testing.assert_allclose(track["embedding"], self.image().json()["embedding"], atol=1e-6)

    def test_uniform_sampling_and_validation_of_unselected_frame(self):
        response = self.client.post("/v1/reid/tracklet-features", files=[
            ("files", (f"{i}.png", picture(), "image/png")) for i in range(4)
        ], data={"metadata": json.dumps({"frame_ids": ["a", "b", "c", "d"]})})
        self.assertEqual(response.json()["selected_frame_ids"], ["a", "d"])
        self.assertEqual(response.json()["used_count"], 2)
        self.assertEqual(response.json()["input_count"], 4)
        response = self.client.post("/v1/reid/tracklet-features", files=[
            ("files", (f"{i}.png", b"broken" if i == 1 else picture(), "image/png")) for i in range(4)])
        self.assertEqual(response.status_code, 422)

    def test_invalid_images_and_metadata(self):
        for invalid in (b"", b"not an image", picture()[:25]):
            self.assertEqual(self.image(invalid).status_code, 422)
        self.assertEqual(self.image(picture(format="GIF")).status_code, 415)
        for metadata in ("[1]", "broken", '{"unknown":1}', '{"frame_ids":["a","b"]}',
                         '{"frame_ids":[1]}', '{"track_id":7}'):
            self.assertEqual(self.image(metadata=metadata).status_code, 422)
        self.assertEqual(self.client.post("/v1/reid/tracklet-features").status_code, 422)

    def test_frame_count_limit(self):
        response = self.client.post("/v1/reid/tracklet-features", files=[
            ("files", (f"{i}.png", picture(), "image/png")) for i in range(33)])
        self.assertEqual(response.status_code, 422)

    def test_per_image_pixel_and_request_limits(self):
        settings = Settings(max_image_bytes=100, max_pixels=600, max_request_bytes=2000)
        with TestClient(create_app(settings, FakeExtractor)) as client:
            response = client.post("/v1/reid/image-features", files={"file": ("a.png", b"x" * 101)})
            self.assertEqual(response.status_code, 413)
            response = client.post("/v1/reid/image-features", files={"file": ("a.png", picture(size=(30, 30)))})
            self.assertEqual(response.status_code, 413)
            response = client.post("/v1/reid/image-features", content=b"x" * 2001)
            self.assertEqual(response.status_code, 413)

    def test_readiness_and_failure_do_not_return_fake_features(self):
        self.app.state.ready = False
        self.assertEqual(self.client.get("/health").status_code, 503)
        self.assertEqual(self.image().status_code, 503)
        self.app.state.ready = True
        self.app.state.extractor.extract_features = lambda images: np.zeros((len(images), 3))
        with self.assertLogs("reid_feature_service.server", level="ERROR"):
            response = self.image()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"]["error_code"], "EXTRACTION_FAILED")


class ConcurrentApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_remains_responsive_and_admission_is_bounded(self):
        entered, release = threading.Event(), threading.Event()

        class BlockingExtractor(FakeExtractor):
            def extract_features(self, images):
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("test did not release extractor")
                return super().extract_features(images)

        app = create_app(Settings(max_requests=1), BlockingExtractor)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                first = asyncio.create_task(client.post("/v1/reid/image-features", files={"file": ("a.png", picture())}))
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                    health = await asyncio.wait_for(client.get("/health"), 1)
                    self.assertEqual(health.status_code, 200)
                    busy = await client.post("/v1/reid/image-features", files={"file": ("b.png", picture())})
                    self.assertEqual(busy.status_code, 503)
                finally:
                    release.set()
                    self.assertEqual((await first).status_code, 200)
                self.assertEqual((await client.post("/v1/reid/image-features", files={"file": ("c.png", picture())})).status_code, 200)

    async def test_chunked_upload_obeys_request_limit(self):
        app = create_app(Settings(max_request_bytes=20), FakeExtractor)
        async def chunks():
            yield b'--example\r\nContent-Disposition: form-data; name="file"; filename="a.png"\r\n\r\n'
            yield b"y" * 15

        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/v1/reid/image-features", content=chunks(), headers={
                    "content-type": "multipart/form-data; boundary=example"})
                self.assertEqual(response.status_code, 413)


class FakeDetector:
    def __init__(self, settings, device):
        self.candidates = []
        self.calls = 0

    def detect(self, image):
        self.calls += 1
        return self.candidates


class DetectorBoxTests(unittest.TestCase):
    def detector(self, boxes, confidence):
        detector = PersonDetector.__new__(PersonDetector)
        detector.device, detector.confidence = "cpu", 0.4
        detector.model = Mock()
        result = Mock()
        result.boxes.xyxy.cpu.return_value.numpy.return_value = np.asarray(boxes).reshape(-1, 4)
        result.boxes.conf.cpu.return_value.numpy.return_value = np.asarray(confidence)
        detector.model.predict.return_value = [result]
        return detector

    def test_boxes_are_clipped_rounded_and_numbered_from_left_to_right(self):
        detector = self.detector([[20.2, 1.8, 41.5, 61.2], [-2, 0, 10.2, 58], [5, 4, 5, 8]],
                                 [0.8, 0.9, 0.7])
        image = Image.new("RGB", (40, 60))
        candidates = detector.detect(image)
        self.assertEqual([x["bbox"] for x in candidates], [[0, 0, 11, 58], [20, 1, 40, 60]])
        self.assertEqual([x["candidate_id"] for x in candidates], ["1", "2"])
        self.assertEqual(detector.model.predict.call_args.kwargs["classes"], [0])
        self.assertIs(detector.model.predict.call_args.kwargs["source"], image)

    def test_excess_people_are_rejected_instead_of_silently_truncated(self):
        detector = self.detector([[0, 0, 10, 20]] * 101, [0.9] * 101)
        with self.assertRaises(HTTPException) as error:
            detector.detect(Image.new("RGB", (40, 60)))
        self.assertEqual(error.exception.detail["error_code"], "TOO_MANY_PEOPLE")

    def test_invalid_model_coordinates_are_rejected(self):
        detector = self.detector([[0, 0, np.nan, 20]], [0.9])
        with self.assertRaises(ValueError):
            detector.detect(Image.new("RGB", (40, 60)))


class ScreenshotApiTests(unittest.TestCase):
    def setUp(self):
        self.detector_loads = 0
        self.extracted_images = []
        self.detector = FakeDetector(None, "cpu")

        def load_detector(settings, device):
            self.detector_loads += 1
            return self.detector

        outer = self

        class RecordingExtractor(FakeExtractor):
            def extract_features(self, images):
                outer.extracted_images.extend(np.asarray(image).copy() for image in images)
                return super().extract_features(images)

        self.app = create_app(Settings(), RecordingExtractor, load_detector)
        self.client = TestClient(self.app)
        self.client.__enter__()
        image = Image.new("RGB", (40, 60), "red")
        image.paste("blue", (20, 0, 40, 60))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        self.screenshot = buffer.getvalue()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def detect(self, payload=None, metadata="{}"):
        return self.client.post("/v1/reid/person-crops", files={
            "file": ("scene.png", self.screenshot if payload is None else payload, "image/png")},
            data={"metadata": metadata})

    def selected(self, bbox, payload=None):
        return self.client.post("/v1/reid/image-features", files={
            "file": ("scene.png", self.screenshot if payload is None else payload, "image/png")},
            data={"bbox": bbox})

    def test_one_person_returns_box_and_features_of_crop_without_second_detection(self):
        candidate = {"candidate_id": "1", "bbox": [20, 0, 40, 60], "confidence": 0.9}
        self.detector.candidates = [candidate]
        response = self.detect(metadata='{"request_id":"query-1","source_asset_id":"scene-1"}')
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["status"], "extracted")
        self.assertFalse(result["selection_required"])
        self.assertEqual(result["selected_candidate_id"], "1")
        self.assertEqual(result["candidates"], [candidate])
        self.assertEqual(result["feature"]["request_id"], "query-1")
        self.assertEqual(result["feature"]["source"], {"source_asset_id": "scene-1"})
        self.assertEqual(result["feature"]["crop"]["bbox"], candidate["bbox"])
        self.assertEqual(self.extracted_images[0].shape, (60, 20, 3))
        np.testing.assert_array_equal(self.extracted_images[0][0, 0], [0, 0, 255])
        selected = self.selected(json.dumps(candidate["bbox"]))
        self.assertEqual(selected.status_code, 200, selected.text)
        np.testing.assert_allclose(result["feature"]["embedding"], selected.json()["embedding"])
        self.assertEqual(self.detector.calls, 1)

    def test_multiple_people_wait_for_agent_then_extract_selected_crop(self):
        candidates = [
            {"candidate_id": "1", "bbox": [0, 0, 20, 60], "confidence": 0.9},
            {"candidate_id": "2", "bbox": [20, 0, 40, 60], "confidence": 0.8},
        ]
        self.detector.candidates = candidates
        response = self.detect()
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["status"], "selection_required")
        self.assertEqual(result["person_count"], 2)
        self.assertEqual(result["candidates"], candidates)
        self.assertTrue(result["selection_required"])
        self.assertIsNone(result["feature"])
        self.assertIsNone(result["selected_candidate_id"])
        self.assertEqual(self.extracted_images, [])
        selected = self.selected(json.dumps(candidates[1]["bbox"]))
        self.assertEqual(selected.status_code, 200, selected.text)
        expected = np.array([1, 1, 256], dtype=np.float32)
        expected /= np.linalg.norm(expected)
        np.testing.assert_allclose(selected.json()["embedding"], expected, atol=1e-6)
        self.assertEqual(self.detector.calls, 1)

    def test_no_person_does_not_extract_full_screenshot(self):
        result = self.detect().json()
        self.assertEqual(result["status"], "no_person")
        self.assertEqual(result["person_count"], 0)
        self.assertEqual(result["candidates"], [])
        self.assertIsNone(result["feature"])
        self.assertFalse(result["selection_required"])
        self.assertEqual(self.extracted_images, [])

    def test_detector_is_loaded_once_and_not_used_by_image_or_tracklet(self):
        self.assertFalse(self.client.get("/health").json()["detector_loaded"])
        self.assertEqual(self.selected("[0,0,20,60]").status_code, 200)
        response = self.client.post("/v1/reid/tracklet-features", files=[
            ("files", ("crop.png", picture(), "image/png"))])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.detector_loads, 0)
        self.detect()
        self.detect()
        self.assertEqual(self.detector_loads, 1)
        self.assertEqual(self.detector.calls, 2)
        self.assertTrue(self.client.get("/health").json()["detector_loaded"])

    def test_bad_bbox_is_rejected_before_feature_extraction(self):
        for bbox in ("broken", "null", "{}", "[0,0,1]", "[false,0,20,60]", "[0,0,20.5,60]",
                     "[-1,0,20,60]", "[0,0,41,60]", "[20,0,10,60]", "[0,0,20,0]", " " * 257):
            with self.subTest(bbox=bbox):
                response = self.selected(bbox)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(response.json()["detail"]["error_code"], "INVALID_BBOX")
        self.assertEqual(self.extracted_images, [])
        self.assertEqual(self.detector_loads, 0)

    def test_bbox_uses_exif_corrected_coordinates(self):
        image = Image.open(BytesIO(self.screenshot))
        exif = image.getexif()
        exif[274] = 6
        buffer = BytesIO()
        image.save(buffer, format="JPEG", exif=exif)
        payload = buffer.getvalue()
        with Image.open(BytesIO(payload)) as original:
            expected = np.asarray(ImageOps.exif_transpose(original).convert("RGB"))[:20, :60]
        response = self.selected("[0,0,60,20]", payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["crop"]["image_width"], 60)
        self.assertEqual(response.json()["crop"]["image_height"], 40)
        np.testing.assert_array_equal(self.extracted_images[0], expected)

    def test_invalid_screenshot_and_metadata_do_not_load_detector(self):
        self.assertEqual(self.detect(b"broken").status_code, 422)
        self.assertEqual(self.detect(metadata='{"unknown":1}').status_code, 422)
        self.assertEqual(self.detector_loads, 0)

    def test_detector_load_failure_preserves_existing_feature_endpoints(self):
        def broken_detector(settings, device):
            raise FileNotFoundError("missing weights")

        with TestClient(create_app(Settings(), FakeExtractor, broken_detector)) as client:
            with self.assertLogs("reid_feature_service.server", level="ERROR"):
                response = client.post("/v1/reid/person-crops", files={"file": ("a.png", self.screenshot)})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["detail"]["error_code"], "DETECTOR_UNAVAILABLE")
            self.assertTrue(client.get("/health").json()["ready"])
            self.assertEqual(client.post("/v1/reid/image-features", files={
                "file": ("crop.png", picture())}).status_code, 200)
