"""Numeric invariants plus opt-in real RN50 checks, using synthetic images only."""

import os
import time
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

import numpy as np
from PIL import Image

from reid_feature_service.server import Extractor, Settings, legacy_modules, normalize_features, pool_features


class PoolingTests(unittest.TestCase):
    def test_normalize_each_frame_before_mean(self):
        features = np.array([[30, 0], [0, 4]], dtype=np.float32)
        np.testing.assert_allclose(pool_features(features), [2 ** -0.5, 2 ** -0.5], atol=1e-6)
        np.testing.assert_allclose(pool_features([[3, 4]]), [0.6, 0.8], atol=1e-6)
        np.testing.assert_allclose(pool_features(features[::-1]), pool_features(features), atol=1e-6)

    def test_reject_invalid_features(self):
        for features in ([], [[0, 0]], [[np.nan, 1]], [[np.inf, 1]], [[1e38, 1e38]]):
            with np.errstate(over="ignore"), self.assertRaises(ValueError):
                normalize_features(features)
        with self.assertRaises(ValueError):
            pool_features([[1, 0], [-1, 0]])


@unittest.skipUnless(os.getenv("REID_FEATURE_TEST_MODEL") == "1", "set REID_FEATURE_TEST_MODEL=1 for real model checks")
class RealModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        torch.set_num_threads(2)
        cls.settings = Settings.from_env()
        cls.extractor = Extractor(cls.settings)
        rng = np.random.default_rng(17)
        cls.images = [Image.fromarray(rng.integers(0, 256, (256, 128, 3), dtype=np.uint8)) for _ in range(2)]

    def test_dimension_normalization_repeatability_and_batch_consistency(self):
        single = self.extractor.extract_features([self.images[0]])
        repeated = self.extractor.extract_features([self.images[0]])
        batch = self.extractor.extract_features(self.images)
        self.assertEqual(batch.shape, (2, 3072))
        self.assertTrue(np.isfinite(batch).all())
        np.testing.assert_allclose(np.linalg.norm(batch, axis=1), 1, atol=1e-6)
        np.testing.assert_allclose(single, repeated, atol=1e-6, rtol=1e-5)
        np.testing.assert_allclose(single[0], batch[0], atol=2e-5, rtol=2e-4)
        np.testing.assert_allclose(pool_features(single), single[0], atol=1e-6)

    def test_matches_legacy_loader_and_forward(self):
        # Validate the strict loader against the old load_param/forward on the same architecture.
        _, model_module, _ = legacy_modules()
        model = self.extractor.model
        tensor = self.extractor.torch.stack([self.extractor.transform(image) for image in self.images]).to(self.extractor.device)
        before = self.extractor.extract_features(self.images)
        with redirect_stdout(StringIO()):
            model_module.build_transformer.load_param(model, str(self.settings.weights))
        with self.extractor.torch.inference_mode():
            old_output = normalize_features(model(tensor).float().cpu().numpy())
        np.testing.assert_allclose(before, old_output, atol=1e-6, rtol=1e-5)

    def test_incomplete_checkpoint_is_rejected_without_network_access(self):
        import torch
        with patch.object(torch, "load", return_value={}):
            with self.assertRaisesRegex(ValueError, "missing inference parameters"):
                Extractor(self.settings)

    @unittest.skipUnless(os.getenv("REID_FEATURE_TEST_DETECTOR") == "1",
                         "set REID_FEATURE_TEST_DETECTOR=1 for real YOLO screenshot checks")
    def test_real_screenshot_detection_selection_and_crop_features(self):
        import json
        from importlib.util import find_spec
        from io import BytesIO
        from pathlib import Path
        from fastapi.testclient import TestClient
        from reid_feature_service.server import create_app

        # Ultralytics ships this public demonstration image; no track sample is required.
        source = Path(find_spec("ultralytics").origin).parent / "assets/bus.jpg"
        self.assertTrue(source.is_file(), "ultralytics/assets/bus.jpg is required for this opt-in test")
        payload = source.read_bytes()

        def existing_extractor(settings):
            self.extractor.torch.set_num_threads(settings.cpu_threads)
            return self.extractor

        def png(image):
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            return buffer.getvalue()

        with TestClient(create_app(self.settings, existing_extractor)) as client:
            response = client.post("/v1/reid/person-crops", files={"file": ("bus.jpg", payload)})
            self.assertEqual(response.status_code, 200, response.text)
            multiple = response.json()
            self.assertEqual(multiple["status"], "selection_required")
            self.assertGreaterEqual(multiple["person_count"], 2)
            self.assertIsNone(multiple["feature"])
            chosen = max(multiple["candidates"],
                         key=lambda c: (c["bbox"][2] - c["bbox"][0]) * (c["bbox"][3] - c["bbox"][1]))
            selected = client.post("/v1/reid/image-features", files={"file": ("bus.jpg", payload)},
                                   data={"bbox": json.dumps(chosen["bbox"])})
            self.assertEqual(selected.status_code, 200, selected.text)
            with Image.open(BytesIO(payload)) as original:
                crop = original.convert("RGB").crop(chosen["bbox"])
                cropped_payload = png(crop)
            manual = client.post("/v1/reid/image-features", files={"file": ("crop.png", cropped_payload)})
            self.assertEqual(manual.status_code, 200, manual.text)
            np.testing.assert_allclose(selected.json()["embedding"], manual.json()["embedding"], atol=1e-6)
            single = client.post("/v1/reid/person-crops", files={"file": ("crop.png", cropped_payload)})
            self.assertEqual(single.status_code, 200, single.text)
            result = single.json()
            self.assertEqual(result["status"], "extracted")
            self.assertEqual(result["feature"]["embedding_dim"], 3072)
            self.assertAlmostEqual(np.linalg.norm(result["feature"]["embedding"]), 1, places=6)
            blank = client.post("/v1/reid/person-crops", files={
                "file": ("blank.png", png(Image.new("RGB", (640, 480))))})
            self.assertEqual(blank.status_code, 200, blank.text)
            self.assertEqual(blank.json()["status"], "no_person")
            self.assertIsNone(blank.json()["feature"])
            print(f"Real screenshot check device={self.extractor.device} "
                  f"people={multiple['person_count']} selected_dim={selected.json()['embedding_dim']} "
                  "single=extracted blank=no_person", flush=True)

    def test_real_api_and_report_batch_timings(self):
        from concurrent.futures import ThreadPoolExecutor
        from io import BytesIO
        from fastapi.testclient import TestClient
        from reid_feature_service.server import create_app

        payloads = []
        for image in self.images:
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            payloads.append(buffer.getvalue())
        def existing_extractor(settings):
            self.extractor.torch.set_num_threads(settings.cpu_threads)
            return self.extractor

        with TestClient(create_app(self.settings, existing_extractor)) as client:
            def query(index):
                return client.post("/v1/reid/image-features", files={
                    "file": ("person.png", payloads[index], "image/png")})
            with ThreadPoolExecutor(max_workers=2) as callers:
                results = list(callers.map(query, [0, 1]))
            self.assertTrue(all(result.status_code == 200 for result in results))
            expected = pool_features([result.json()["embedding"] for result in results])
            track = client.post("/v1/reid/tracklet-features", files=[
                ("files", (f"{i}.png", data, "image/png")) for i, data in enumerate(payloads)])
            self.assertEqual(track.status_code, 200, track.text)
            np.testing.assert_allclose(track.json()["embedding"], expected, atol=2e-5, rtol=2e-4)
            for count in (1, 4, 8):
                elapsed = []
                for _ in range(3):
                    started = time.perf_counter()
                    if count == 1:
                        response = query(0)
                    else:
                        response = client.post("/v1/reid/tracklet-features", files=[
                            ("files", (f"{i}.png", payloads[i % 2], "image/png")) for i in range(count)])
                    self.assertEqual(response.status_code, 200, response.text)
                    elapsed.append((time.perf_counter() - started) * 1000)
                print(f"API benchmark device={self.extractor.device} frames={count} "
                      f"median_ms={np.median(elapsed):.1f} max_ms={max(elapsed):.1f}", flush=True)
        if str(self.extractor.device).startswith("cuda"):
            print(f"GPU peak allocated MiB={self.extractor.torch.cuda.max_memory_allocated() / 2**20:.1f}", flush=True)
