"""Contract tests for the remote JSON API; synthetic JPEGs and injected fakes only."""

import asyncio
import base64
import hashlib
import tempfile
import threading
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import httpx
import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from reid_feature_service import remote_server
from reid_feature_service.server import Settings, TextTooLongError

TMP = tempfile.TemporaryDirectory()


def tearDownModule():
    TMP.cleanup()


def make_settings():
    directory = Path(TMP.name)
    (directory / "fake.pth").write_bytes(b"weights")
    model = directory / "chinese-clip-vit-base-patch16"
    model.mkdir(exist_ok=True)
    (model / "pytorch_model.bin").write_bytes(b"text-weights")
    return Settings(weights=directory / "fake.pth", text_model=model)


def jpeg(color="red", size=(64, 128), orientation=None):
    buffer = BytesIO()
    options = {}
    if orientation is not None:
        exif = Image.Exif()
        exif[274] = orientation
        options["exif"] = exif
    Image.new("RGB", size, color).save(buffer, format="JPEG", **options)
    return buffer.getvalue()


def png(size=(32, 32)):
    buffer = BytesIO()
    Image.new("RGB", size, "red").save(buffer, format="PNG")
    return buffer.getvalue()


def data_url(payload, mime="jpeg"):
    return f"data:image/{mime};base64," + base64.b64encode(payload).decode()


class FakeExtractor:
    embedding_dim = 3
    definition_sha256 = "a" * 64
    feature_space_id = "clipreid-rn50-" + "a" * 24
    device = "cpu"

    def __init__(self, settings):
        self.sizes = []
        self.calls = 0

    def extract_features(self, images):
        self.calls += 1
        self.sizes.extend(image.size for image in images)
        return np.array([np.asarray(image, dtype=np.float32).mean(axis=(0, 1)) + 1
                         for image in images])


class FakeTextExtractor:
    embedding_dim = 4
    feature_space_id = "fs-" + "b" * 64
    text_contract_id = "fs-" + "b" * 64 + "-text-v1"
    model_name = "Fake-Chinese-CLIP"
    device = "cpu"
    token_limit = 150

    def __init__(self, settings, device):
        self.device = device
        self.model_path = Path(settings.text_model)
        self.calls = 0

    def encode_text(self, text):
        self.calls += 1
        if len(text) > self.token_limit:
            raise TextTooLongError("stub token limit")
        return np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32), len(text)

    def encode_image(self, image):
        self.calls += 1
        return np.array([4.0, 3.0, 2.0, 1.0], dtype=np.float32)


def compare_payload(query_box=(0.1, 0.1, 0.9, 0.9), target_boxes=None, image=None):
    image = data_url(jpeg(size=(200, 100))) if image is None else image
    target_boxes = target_boxes or [query_box]
    return {
        "request_id": "req-1",
        "query": {"image": image, "box": list(query_box)},
        "targets": [{"id": f"t{index + 1}", "image": image, "box": list(box)}
                    for index, box in enumerate(target_boxes)],
    }


def text_payload(text="穿黑色外套的男子", ids=("t1",), image=None):
    image = data_url(jpeg(size=(200, 100))) if image is None else image
    return {
        "request_id": "txt-1",
        "query": {"text": text, "language": "auto"},
        "targets": [{"id": identifier, "image": image, "box": [0.1, 0.1, 0.9, 0.9]}
                    for identifier in ids],
    }


class RemoteApiTests(unittest.TestCase):
    def setUp(self):
        self.app = remote_server.create_app(make_settings(), FakeExtractor, FakeTextExtractor)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.extractor = self.app.state.extractor

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def compare(self, payload):
        return self.client.post("/api/analysis/reid/compare", json=payload)

    def compare_text(self, payload):
        return self.client.post("/api/analysis/reid/compare-text", json=payload)

    def test_health_reports_both_spaces_without_running_inference(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["service"], "reid")
        self.assertIs(body["ready"], True)
        self.assertEqual(body["model"], "fake.pth")
        self.assertEqual(body["model_sha256"], hashlib.sha256(b"weights").hexdigest())
        self.assertEqual(body["feature_space_id"], "clipreid-rn50-" + "a" * 64)
        self.assertEqual(body["embedding_dim"], 3)
        text = body["text_reid"]
        self.assertIs(text["ready"], True)
        self.assertEqual(text["model"], "chinese-clip-vit-base-patch16")
        self.assertEqual(text["model_sha256"], hashlib.sha256(b"text-weights").hexdigest())
        self.assertEqual(text["feature_space_id"], "fs-" + "b" * 64)
        self.assertEqual(text["text_contract_id"], "fs-" + "b" * 64 + "-text-v1")
        self.assertEqual(text["embedding_dim"], 4)
        self.assertEqual(self.extractor.calls, 0)

    def test_compare_contract_and_math_properties(self):
        left = data_url(jpeg("red", (200, 100)))
        right = data_url(jpeg("blue", (200, 100)))
        payload = {
            "request_id": "cmp-1",
            "query": {"image": left, "box": [0.1, 0.1, 0.9, 0.9]},
            "targets": [
                {"id": "a", "image": left, "box": [0.1, 0.1, 0.9, 0.9]},
                {"id": "b", "image": right, "box": [0.1, 0.1, 0.9, 0.9]},
            ],
        }
        response = self.compare(payload)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["request_id"], "cmp-1")
        self.assertEqual(result["metric"], "cosine")
        self.assertEqual(result["model"], "fake.pth")
        self.assertEqual(result["model_sha256"], hashlib.sha256(b"weights").hexdigest())
        self.assertEqual(result["feature_space_id"], "clipreid-rn50-" + "a" * 64)
        self.assertEqual(result["embedding_dim"], 3)
        self.assertIs(result["cold_start"], False)
        self.assertGreaterEqual(result["duration_ms"], 0)
        self.assertNotIn("embedding", result)
        similarity = {match["id"]: match["similarity"] for match in result["matches"]}
        self.assertEqual(set(similarity), {"a", "b"})
        self.assertAlmostEqual(similarity["a"], 1.0, delta=1e-6)
        self.assertEqual(self.compare(payload).json()["matches"], result["matches"])

        swapped = dict(payload,
                       query={"image": right, "box": payload["targets"][1]["box"]},
                       targets=[{"id": "q", "image": left, "box": [0.1, 0.1, 0.9, 0.9]}])
        reversed_similarity = self.compare(swapped).json()["matches"][0]["similarity"]
        self.assertAlmostEqual(reversed_similarity, similarity["b"], delta=1e-5)

        single = self.compare(dict(payload, targets=[payload["targets"][1]])).json()
        self.assertAlmostEqual(single["matches"][0]["similarity"], similarity["b"], delta=1e-6)
        reordered = self.compare(dict(payload, targets=list(reversed(payload["targets"])))).json()
        self.assertAlmostEqual({match["id"]: match["similarity"] for match in reordered["matches"]}["b"],
                               similarity["b"], delta=1e-6)

    def test_box_is_converted_to_exact_pixels_without_padding(self):
        image = data_url(jpeg("grey", (1920, 1080)))
        payload = {
            "query": {"image": image, "box": [0.10, 0.22, 0.36, 0.81]},
            "targets": [{"id": "t1", "image": image, "box": [0.52, 0.18, 0.71, 0.79]}],
        }
        response = self.compare(payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.extractor.sizes, [(499, 637), (365, 659)])

    def test_compare_rejects_invalid_requests(self):
        good = compare_payload()
        self.assertEqual(self.compare(dict(good, unknown=1)).status_code, 422)
        self.assertEqual(self.compare(dict(good, targets=[])).status_code, 422)
        self.assertEqual(self.compare(dict(good, targets=[
            {"id": f"t{index}", "image": good["targets"][0]["image"], "box": [0.1, 0.1, 0.9, 0.9]}
            for index in range(9)])).status_code, 422)
        duplicate = [dict(good["targets"][0], id="x")] * 2
        response = self.compare(dict(good, targets=duplicate))
        self.assertEqual(response.status_code, 422)
        self.assertIn("DUPLICATE_TARGET_ID", response.json()["detail"])
        long_id = [dict(good["targets"][0], id="x" * 33)]
        self.assertEqual(self.compare(dict(good, targets=long_id)).status_code, 422)
        self.assertEqual(self.compare(dict(good, query={"image": good["query"]["image"],
                                                        "box": [0, 0, 1]})).status_code, 422)
        for box in ([0.5, 0.2, 0.5, 0.8], [0, 0, 1.1, 1], [0.2, 0.2, 0.1, 0.8], [0, -0.1, 1, 1]):
            with self.subTest(box=box):
                response = self.compare(dict(good, query={"image": good["query"]["image"], "box": box}))
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIn("INVALID_BOX", response.json()["detail"])
        too_small = self.compare(dict(good, query={"image": good["query"]["image"],
                                                   "box": [0.4, 0.5, 0.42, 0.52]}))
        self.assertEqual(too_small.status_code, 422)
        self.assertIn("BOX_TOO_SMALL", too_small.json()["detail"])
        self.assertEqual(self.extractor.calls, 0)

    def test_small_crop_floor_is_eight_pixels_and_256_area(self):
        image = data_url(jpeg("grey", (200, 100)))

        def post(box):
            return self.compare({"query": {"image": image, "box": box},
                                 "targets": [{"id": "t1", "image": image, "box": [0.1, 0.1, 0.9, 0.9]}]})

        self.assertEqual(post([0.5, 0.5, 0.58, 0.66]).status_code, 200)  # 16x16 = 256 px
        for box in ([0.5, 0.5, 0.58, 0.62],   # 16x12 = 192 px
                    [0.5, 0.5, 0.53, 0.7]):   # 6x20, width below 8
            with self.subTest(box=box):
                response = post(box)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIn("BOX_TOO_SMALL", response.json()["detail"])

    def test_compare_rejects_bad_images(self):
        for image, status in (("/tmp/photo.jpg", 422), (data_url(png(), "png"), 415),
                              ("data:image/jpeg;base64,!!!", 422), (data_url(b"not a jpeg"), 422)):
            with self.subTest(image=image[:24]):
                payload = compare_payload(image=image)
                response = self.compare(payload)
                self.assertEqual(response.status_code, status, response.text)
        response = self.compare(compare_payload(image=data_url(jpeg(size=(64, 64), orientation=6))))
        self.assertEqual(response.status_code, 422)
        self.assertIn("EXIF_ROTATION", response.json()["detail"])
        self.assertEqual(self.extractor.calls, 0)

    def test_image_and_request_size_limits(self):
        huge = "data:image/jpeg;base64," + "A" * remote_server.MAX_IMAGE_CHARS
        self.assertEqual(self.compare(compare_payload(image=huge)).status_code, 413)
        with patch.object(remote_server, "MAX_REQUEST_BYTES", 1000):
            response = self.client.post("/api/analysis/reid/compare", content=b"x" * 2000)
        self.assertEqual(response.status_code, 413)

    def test_compare_text_contract(self):
        response = self.compare_text(text_payload())
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["query_type"], "text")
        self.assertEqual(result["metric"], "cosine")
        self.assertEqual(result["model"], "chinese-clip-vit-base-patch16")
        self.assertEqual(result["model_sha256"], hashlib.sha256(b"text-weights").hexdigest())
        self.assertEqual(result["feature_space_id"], "fs-" + "b" * 64)
        self.assertEqual(result["text_contract_id"], "fs-" + "b" * 64 + "-text-v1")
        self.assertEqual(result["embedding_dim"], 4)
        self.assertEqual(result["language"], "zh")
        self.assertIs(result["cold_start"], False)
        self.assertEqual(result["matches"][0]["id"], "t1")
        self.assertAlmostEqual(result["matches"][0]["similarity"], 0.666667, delta=1e-6)
        self.assertNotIn("embedding", result)
        image_space = self.compare(compare_payload()).json()["feature_space_id"]
        self.assertNotEqual(result["feature_space_id"], image_space)

        ordered = self.compare_text(text_payload(ids=("t1", "t2"))).json()["matches"]
        reordered = self.compare_text(text_payload(ids=("t2", "t1"))).json()["matches"]
        self.assertEqual({match["id"]: match["similarity"] for match in ordered},
                         {match["id"]: match["similarity"] for match in reordered})

    def test_compare_text_rejects_invalid_text_and_targets(self):
        for text in ("", "   "):
            response = self.compare_text(text_payload(text))
            self.assertEqual(response.status_code, 422)
            self.assertIn("TEXT_EMPTY", response.json()["detail"])
        response = self.compare_text(text_payload("字" * 201))
        self.assertEqual(response.status_code, 422)
        self.assertIn("TEXT_TOO_LONG", response.json()["detail"])
        response = self.compare_text(text_payload("字" * 160))
        self.assertEqual(response.status_code, 422)
        self.assertIn("TEXT_TOO_LONG", response.json()["detail"])
        self.assertEqual(self.compare_text(dict(text_payload(), unknown=1)).status_code, 422)
        self.assertEqual(self.compare_text(text_payload(ids=("t1", "t1"))).status_code, 422)
        payload = text_payload()
        payload["query"]["language"] = "fr"
        self.assertEqual(self.compare_text(payload).status_code, 422)

    def test_language_detection_and_override(self):
        self.assertEqual(self.compare_text(text_payload("a man in black")).json()["language"], "en")
        self.assertEqual(self.compare_text(text_payload("12345")).json()["language"], "unknown")
        payload = text_payload("行人")
        payload["query"]["language"] = "en"
        self.assertEqual(self.compare_text(payload).json()["language"], "en")

    def test_broken_text_model_keeps_compare_working(self):
        def broken(settings, device):
            raise FileNotFoundError("missing Chinese-CLIP model")

        app = remote_server.create_app(make_settings(), FakeExtractor, broken)
        with self.assertLogs("reid_feature_service.remote_server", level="ERROR"):
            with TestClient(app) as client:
                health = client.get("/api/health")
                self.assertEqual(health.status_code, 200)
                self.assertIs(health.json()["text_reid"]["ready"], False)
                self.assertEqual(health.json()["text_reid"]["error"], "initialization_failed")
                response = client.post("/api/analysis/reid/compare-text", json=text_payload())
                self.assertEqual(response.status_code, 503)
                self.assertIn("TEXT_MODEL_NOT_READY", response.json()["detail"])
                self.assertEqual(client.post("/api/analysis/reid/compare",
                                             json=compare_payload()).status_code, 200)


class ConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    def blocking_app(self, entered, release):
        class BlockingExtractor(FakeExtractor):
            def extract_features(self, images):
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("test did not release extractor")
                return super().extract_features(images)

        return remote_server.create_app(make_settings(), BlockingExtractor, FakeTextExtractor)

    async def test_second_request_is_rejected_with_429_while_health_stays_up(self):
        entered, release = threading.Event(), threading.Event()
        app = self.blocking_app(entered, release)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://test") as client:
                first = asyncio.create_task(client.post("/api/analysis/reid/compare",
                                                        json=compare_payload()))
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                    health = await asyncio.wait_for(client.get("/api/health"), 1)
                    self.assertEqual(health.status_code, 200)
                    busy = await client.post("/api/analysis/reid/compare", json=compare_payload())
                    self.assertEqual(busy.status_code, 429)
                    self.assertIn("SERVICE_BUSY", busy.json()["detail"])
                finally:
                    release.set()
                    self.assertEqual((await first).status_code, 200)
                later = await client.post("/api/analysis/reid/compare", json=compare_payload())
                self.assertEqual(later.status_code, 200)

    async def test_timeout_returns_500_and_keeps_the_slot_until_the_job_ends(self):
        entered, release = threading.Event(), threading.Event()
        app = self.blocking_app(entered, release)
        with patch.object(remote_server, "INFERENCE_TIMEOUT", 0.2):
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                             base_url="http://test") as client:
                    first = asyncio.create_task(client.post("/api/analysis/reid/compare",
                                                            json=compare_payload()))
                    self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                    timeout = await first
                    self.assertEqual(timeout.status_code, 500)
                    self.assertIn("INFERENCE_TIMEOUT", timeout.json()["detail"])
                    busy = await client.post("/api/analysis/reid/compare", json=compare_payload())
                    self.assertEqual(busy.status_code, 429)
                    release.set()
                    response = None
                    for _ in range(50):
                        await asyncio.sleep(0.05)
                        response = await client.post("/api/analysis/reid/compare",
                                                     json=compare_payload())
                        if response.status_code == 200:
                            break
                    self.assertEqual(response.status_code, 200, response.text)


if __name__ == "__main__":
    unittest.main()