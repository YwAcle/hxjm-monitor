"""真实 multipart 序列化、版本隔离缓存和登记候选映射。"""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx

from llm_agent_service.app import create_app
from llm_agent_service.config import DbConfig, ServiceConfig
from llm_agent_service.service.clipreid_client import ClipReIDClient
from llm_agent_service.service.gallery_search import GallerySearchService
from llm_report_service.llm.vision import decode_base64_image
from tests.test_gallery_search import image_data, target


class ClipReIDTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.space = "clipreid-rn50-test"
        self.vector = [1.0] + [0.0] * 3071
        self.health_ready = True
        self.response_space = None
        self.client_class = httpx.Client

    def handler(self, request):
        self.calls.append(request)
        if request.url.path == "/health":
            return httpx.Response(200, json={"ready": self.health_ready, "embedding_dim": 3072,
                                            "feature_space_id": self.space})
        self.assertEqual(request.url.path, "/v1/reid/image-features")
        self.assertIn("multipart/form-data", request.headers["content-type"])
        self.assertIn(b'name="file"', request.content)
        self.assertIn(b"image/png", request.content)
        return httpx.Response(200, json={"feature_type": "image", "embedding_dim": 3072,
            "normalized": True, "feature_space_id": self.response_space or self.space,
            "embedding": self.vector})

    def client(self, **kwargs):
        self.assertFalse(kwargs["trust_env"])
        return self.client_class(transport=httpx.MockTransport(self.handler), **kwargs)

    def test_cache_version_and_image_invalidation(self):
        client = ClipReIDClient("http://reid.test:28024")
        image = decode_base64_image(image_data())
        with patch("llm_agent_service.service.clipreid_client.httpx.Client", self.client):
            query, vectors, space = client.query_gallery(image, [target("A")])
            self.assertEqual(query, vectors["A"])
            self.assertEqual(space, self.space)
            self.assertEqual(len(self.calls), 3)
            client.query_gallery(image, [target("A")])
            self.assertEqual(len(self.calls), 5)  # health + query only
            self.space = "new-version"
            client.query_gallery(image, [target("A")])
            self.assertEqual(len(self.calls), 8)
            client.query_gallery(image, [])
            self.assertEqual(client._cache, {})

    def test_rejects_mixed_feature_space_and_invalid_vectors(self):
        client = ClipReIDClient("http://reid.test")
        with patch("llm_agent_service.service.clipreid_client.httpx.Client", self.client):
            self.response_space = "wrong"
            with self.assertRaisesRegex(ValueError, "特征空间"):
                client.query_gallery(decode_base64_image(image_data()), [])
            self.response_space = None
            for vector in ([0.0] * 3072, [True] * 3072, [1.0, 0.0], [2.0] + [0.0] * 3071):
                self.vector = vector
                with self.assertRaises(ValueError):
                    client.query_gallery(decode_base64_image(image_data()), [])
            self.health_ready = False
            with self.assertRaisesRegex(ValueError, "未就绪"):
                client.health()

    def test_pin_mismatch(self):
        with patch("llm_agent_service.service.clipreid_client.httpx.Client", self.client):
            with self.assertRaisesRegex(ValueError, "配置不一致"):
                ClipReIDClient("http://reid.test", feature_space_id="pinned").health()

    def test_ranks_reencoded_gallery_photos(self):
        service = GallerySearchService(engine=MagicMock(), schema="public", feature_client=ClipReIDClient("http://reid.test"),
                                       text_feature_client=MagicMock())
        with patch("llm_agent_service.service.clipreid_client.httpx.Client", self.client), \
             patch("llm_agent_service.service.gallery_search.list_gallery", return_value=[target("A")]):
            result = service.search_image(image_data(), 3)
        self.assertEqual(result["method"], "remote_clipreid")
        self.assertEqual(result["feature_dimension"], 3072)
        self.assertEqual(result["candidates"][0]["person_id"], "A")
        self.assertEqual(result["candidates"][0]["similarity"], 1)

    def test_chat_and_sse_use_configured_multipart_backend(self):
        for streaming in (False, True):
            llm = MagicMock()
            llm.invoke.side_effect = [
                SimpleNamespace(content='{"action":"tool","tool_name":"search_pedestrians_by_image","arguments":{}}'),
                SimpleNamespace(content='{"action":"final","answer":"候选A"}'),
            ]
            llm.stream.return_value = iter([SimpleNamespace(content="候选A")])
            with patch("llm_agent_service.app.ReidService"), \
                 patch("llm_agent_service.service.clipreid_client.httpx.Client", self.client), \
                 patch("llm_agent_service.service.gallery_search.list_gallery", return_value=[target("A")]):
                app = create_app(engine=MagicMock(), db_cfg=DbConfig("localhost", 5432, "u", "p", "db"),
                                 svc_cfg=ServiceConfig(reid_feature_base_url="http://reid.test"), llm=llm)
                response = app.test_client().post("/chat/stream" if streaming else "/chat", json={
                    "prompt": "用这张图片找人", "image": image_data(), "session_id": "clipreid-test"})
                self.assertEqual(response.status_code, 200)
                if streaming:
                    body = response.get_data(as_text=True)
                    self.assertIn("event: result", body)
                    self.assertIn("remote_clipreid", body)
                    self.assertIn("event: done", body)
                else:
                    self.assertEqual(response.get_json()["data"]["candidates"][0]["person_id"], "A")

    def test_changed_and_removed_photos_refresh_cache(self):
        client = ClipReIDClient("http://reid.test")
        image = decode_base64_image(image_data())
        with patch("llm_agent_service.service.clipreid_client.httpx.Client", self.client):
            client.query_gallery(image, [target("A"), target("B")])
            self.assertEqual(len(self.calls), 4)
            client.query_gallery(image, [target("A", image=image_data() + "\n")])
            self.assertEqual(len(self.calls), 7)  # health + query + changed photo
            self.assertEqual(len(client._cache), 1)
            self.assertEqual(next(iter(client._cache))[1], "A")

    def test_missing_or_invalid_photos_are_skipped(self):
        client = ClipReIDClient("http://reid.test")
        with patch("llm_agent_service.service.clipreid_client.httpx.Client", self.client):
            _, vectors, _ = client.query_gallery(decode_base64_image(image_data()), [
                target("missing", image=""), target("invalid", image="invalid image"),
            ])
        self.assertEqual(vectors, {})
        self.assertEqual(len(self.calls), 2)  # health + query, no gallery encode

    def test_gallery_encode_failure_aborts_instead_of_returning_partial_results(self):
        client = ClipReIDClient("http://reid.test")
        with patch.object(client, "health", return_value={"feature_space_id": self.space}), \
             patch.object(client, "_encode", side_effect=[self.vector, self.vector, ValueError("请求失败")]):
            with self.assertRaisesRegex(ValueError, "请求失败"):
                client.query_gallery(decode_base64_image(image_data()), [target("A"), target("B")])
        self.assertEqual(client._cache, {})

    def test_http_errors_fail_without_leaking_response(self):
        with patch("llm_agent_service.service.clipreid_client.httpx.Client") as factory:
            factory.return_value.__enter__.return_value.request.side_effect = httpx.ConnectError("private secret")
            with self.assertRaisesRegex(ValueError, "请求失败") as error:
                ClipReIDClient("http://reid.test").health()
            self.assertNotIn("private secret", str(error.exception))


if __name__ == "__main__":
    unittest.main()
