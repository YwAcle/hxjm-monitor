"""Chinese-CLIP text API tests use an injected extractor; real weights are opt-in only."""

import hashlib
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch
from fastapi.testclient import TestClient
from PIL import Image

from reid_feature_service.server import (Settings, TextExtractor, TextTooLongError,
                                         canonical_definition_text, create_app, space_identity)


def picture(color="red", size=(16, 32), format="PNG"):
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format=format)
    return buffer.getvalue()


class FakeImageExtractor:
    embedding_dim = 3
    feature_space_id = "image-space"
    device = "cpu"

    def __init__(self, settings):
        pass

    def extract_features(self, images):
        return np.array([[1.0, 1.0, 1.0]] * len(images), dtype=np.float32)


class FakeTextExtractor:
    embedding_dim = 4
    feature_space_id = "text-space"
    text_contract_id = "text-space-text-v1"
    model_profile = "chinese_clip_text_reid"
    model_name = "Fake-Chinese-CLIP"
    alignment_verified = True
    definition_text = '{"model":"fake-chinese-clip","dimensions":4}'
    definition_sha256 = hashlib.sha256(definition_text.encode()).hexdigest()
    definition_version = "canonical_json_v1"
    loads = 0
    token_limit = 32

    def __init__(self, settings, device):
        type(self).loads += 1
        self.device = device

    def encode_text(self, text):
        token_count = len(text)
        if token_count > self.token_limit:
            raise TextTooLongError("token limit")
        vector = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32)
        return vector / np.linalg.norm(vector), token_count

    def encode_image(self, image):
        vector = np.array([4.0, 3.0, 2.0, 1.0], dtype=np.float32)
        return vector / np.linalg.norm(vector)


class TextApiTests(unittest.TestCase):
    def setUp(self):
        FakeTextExtractor.loads = 0
        self.app = create_app(Settings(), FakeImageExtractor,
                              text_extractor_factory=FakeTextExtractor)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def encode(self, payload=None):
        return self.client.post("/v1/reid/text-features", json=payload or {"text": "穿黑色外套的男子"})

    def test_health_reports_text_contract(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        block = response.json()["text_reid"]
        self.assertIs(block["ready"], True)
        self.assertIs(block["alignment_verified"], True)
        self.assertEqual(block["feature_space_id"], "text-space")
        self.assertEqual(block["embedding_dim"], 4)
        self.assertEqual(block["text_contract_id"], "text-space-text-v1")
        self.assertEqual(block["definition_text"], FakeTextExtractor.definition_text)
        self.assertEqual(block["definition_sha256"], FakeTextExtractor.definition_sha256)
        self.assertEqual(block["definition_version"], "canonical_json_v1")
        self.assertEqual(FakeTextExtractor.loads, 1)

    def test_text_features_response_contract(self):
        response = self.encode({"text": " 穿黑色外套的男子 ", "language": "auto",
                                "template_id": "", "metadata": {"request_id": "q1"}})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["feature_type"], "text")
        self.assertEqual(result["model_profile"], "chinese_clip_text_reid")
        self.assertEqual(result["feature_space_id"], "text-space")
        self.assertEqual(result["text_contract_id"], "text-space-text-v1")
        self.assertEqual(result["embedding_dim"], 4)
        self.assertIs(result["normalized"], True)
        self.assertIs(result["truncated"], False)
        self.assertEqual(result["language"], "zh")
        self.assertEqual(result["text_chars"], 8)
        self.assertEqual(result["token_count"], 8)
        self.assertEqual(result["source"], {"request_id": "q1"})
        self.assertAlmostEqual(float(np.linalg.norm(result["embedding"])), 1, places=6)

    def test_language_detection_and_explicit_override(self):
        self.assertEqual(self.encode({"text": "a man in black"}).json()["language"], "en")
        self.assertEqual(self.encode({"text": "12345"}).json()["language"], "unknown")
        self.assertEqual(self.encode({"text": "行人", "language": "en"}).json()["language"], "en")

    def test_empty_and_overlong_text(self):
        for text in ("", "   "):
            response = self.encode({"text": text})
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["detail"]["error_code"], "TEXT_EMPTY")
        response = self.encode({"text": "字" * 201})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["error_code"], "TEXT_TOO_LONG")

    def test_token_limit_is_reported_as_text_too_long(self):
        response = self.encode({"text": "字" * 100})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["error_code"], "TEXT_TOO_LONG")

    def test_invalid_request_schema(self):
        self.assertEqual(self.client.post("/v1/reid/text-features", json={}).status_code, 422)
        self.assertEqual(self.client.post("/v1/reid/text-features",
                                          json={"text": 1}).status_code, 422)
        self.assertEqual(self.client.post("/v1/reid/text-features",
                                          json={"text": "行人", "unknown": 1}).status_code, 422)

    def test_image_features_share_the_text_space(self):
        response = self.client.post("/v1/reid/text-reid-image-features", files={
            "file": ("person.png", picture(), "image/png")})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["feature_type"], "image")
        self.assertEqual(result["model_profile"], "chinese_clip_text_reid")
        self.assertEqual(result["feature_space_id"], "text-space")
        self.assertEqual(result["embedding_dim"], 4)
        self.assertIs(result["normalized"], True)
        self.assertAlmostEqual(float(np.linalg.norm(result["embedding"])), 1, places=6)
        bad = self.client.post("/v1/reid/text-reid-image-features", files={
            "file": ("person.png", b"not an image", "image/png")})
        self.assertEqual(bad.status_code, 422)
        self.assertEqual(bad.json()["detail"]["error_code"], "INVALID_IMAGE")

    def test_text_model_failure_keeps_image_endpoints_working(self):
        def broken(settings, device):
            raise FileNotFoundError("missing Chinese-CLIP model")

        app = create_app(Settings(), FakeImageExtractor, text_extractor_factory=broken)
        with self.assertLogs("reid_feature_service.server", level="ERROR"):
            with TestClient(app) as client:
                health = client.get("/health")
                self.assertEqual(health.status_code, 200)
                block = health.json()["text_reid"]
                self.assertIs(block["ready"], False)
                self.assertIs(block["alignment_verified"], False)
                self.assertEqual(block["error"], "initialization_failed")
                self.assertEqual(client.post("/v1/reid/text-features",
                                             json={"text": "行人"}).status_code, 503)
                self.assertEqual(client.post("/v1/reid/text-features", json={
                    "text": "行人"}).json()["detail"]["error_code"], "TEXT_MODEL_NOT_READY")
                self.assertEqual(client.post("/v1/reid/image-features", files={
                    "file": ("person.png", picture(), "image/png")}).status_code, 200)

    def test_disabled_text_model_is_reported_not_ready(self):
        app = create_app(Settings(), FakeImageExtractor, text_extractor_factory=None)
        with TestClient(app) as client:
            block = client.get("/health").json()["text_reid"]
            self.assertIs(block["ready"], False)
            self.assertEqual(block["error"], "disabled")
            self.assertEqual(client.post("/v1/reid/text-reid-image-features", files={
                "file": ("person.png", picture(), "image/png")}).status_code, 503)


class BinLoaderTests(unittest.TestCase):
    class TinyModel(torch.nn.Module):
        def __init__(self, config):
            super().__init__()
            self.linear = torch.nn.Linear(2, 2, bias=False)

    def extractor(self):
        instance = TextExtractor.__new__(TextExtractor)
        instance.torch = torch
        return instance

    def test_loads_trusted_bin_and_ignores_position_ids_buffers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pytorch_model.bin"
            torch.save({"module.linear.weight": torch.eye(2),
                        "text_model.embeddings.position_ids": torch.arange(2)}, path)
            model = self.extractor()._load_bin_model(self.TinyModel, object(), [path])
        self.assertTrue(torch.equal(model.linear.weight, torch.eye(2)))

    def test_missing_parameters_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pytorch_model.bin"
            torch.save({"text_model.embeddings.position_ids": torch.arange(2)}, path)
            with self.assertRaises(ValueError):
                self.extractor()._load_bin_model(self.TinyModel, object(), [path])


class DefinitionTests(unittest.TestCase):
    def test_space_id_is_derived_from_the_exact_definition_text(self):
        text = canonical_definition_text({"b": 1, "a": [1, 2]})
        self.assertEqual(text, '{"a":[1,2],"b":1}')
        space, digest, version = space_identity(text, "fs-", "canonical_json_v1")
        self.assertEqual(space, "fs-" + digest)
        self.assertEqual(digest, hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual(version, "canonical_json_v1")
        legacy, legacy_digest, _ = space_identity(text, "clipreid-rn50-",
                                                  "legacy_python_json_v1", digest_chars=24)
        self.assertEqual(legacy, "clipreid-rn50-" + legacy_digest[:24])


class TextSettingsTests(unittest.TestCase):
    def test_environment_types_and_optional_overrides(self):
        env = {
            "REID_FEATURE_TEXT_MODEL": "/tmp/chinese-clip",
            "REID_FEATURE_TEXT_MAX_CHARS": "120",
            "REID_FEATURE_TEXT_MAX_TOKENS": "64",
            "REID_FEATURE_TEXT_SPACE_ID": "pinned-space",
            "REID_FEATURE_TEXT_CONTRACT_ID": "pinned-contract",
        }
        with patch.dict(os.environ, env):
            settings = Settings.from_env()
        self.assertEqual(settings.text_model, Path("/tmp/chinese-clip"))
        self.assertEqual(settings.text_max_chars, 120)
        self.assertEqual(settings.text_max_tokens, 64)
        self.assertEqual(settings.text_space_id, "pinned-space")
        self.assertEqual(settings.text_contract_id, "pinned-contract")

    def test_blank_optional_values_keep_defaults(self):
        with patch.dict(os.environ, {"REID_FEATURE_TEXT_MODEL": " ",
                                     "REID_FEATURE_TEXT_SPACE_ID": ""}):
            settings = Settings.from_env()
        self.assertEqual(settings.text_model, Settings().text_model)
        self.assertEqual(settings.text_space_id, "")


@unittest.skipUnless(os.getenv("REID_FEATURE_TEST_TEXT_MODEL") == "1",
                     "set REID_FEATURE_TEST_TEXT_MODEL=1 for real Chinese-CLIP checks")
class RealTextModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.extractor = TextExtractor(Settings(), "cpu")

    def test_dimension_normalization_and_shared_space(self):
        vector, tokens = self.extractor.encode_text("穿黑色外套、背双肩包的男子")
        self.assertEqual(vector.shape, (512,))
        self.assertAlmostEqual(float(np.linalg.norm(vector)), 1, places=5)
        self.assertGreaterEqual(tokens, 1)
        image = Image.new("RGB", (224, 224), (128, 128, 128))
        try:
            image_vector = self.extractor.encode_image(image)
        finally:
            image.close()
        self.assertEqual(image_vector.shape, (512,))
        self.assertAlmostEqual(float(np.linalg.norm(image_vector)), 1, places=5)
        self.assertIs(self.extractor.alignment_verified, True)
        self.assertTrue(self.extractor.feature_space_id.startswith("fs-"))
        self.assertEqual(self.extractor.feature_space_id,
                         "fs-" + self.extractor.definition_sha256)
        self.assertEqual(hashlib.sha256(self.extractor.definition_text.encode()).hexdigest(),
                         self.extractor.definition_sha256)
        self.assertEqual(self.extractor.definition_version, "canonical_json_v1")
        self.assertEqual(self.extractor.text_contract_id,
                         self.extractor.feature_space_id + "-text-v1")

    def test_overlong_text_is_rejected_instead_of_truncated(self):
        with self.assertRaises(TextTooLongError):
            self.extractor.encode_text("人" * 1200)


if __name__ == "__main__":
    unittest.main()