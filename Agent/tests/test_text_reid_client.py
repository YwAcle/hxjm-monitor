"""Chinese-CLIP 文本客户端：契约校验和错误边界。"""

import unittest
from unittest.mock import patch

import httpx

from llm_agent_service.service.text_reid_client import TextReIDClient, TextTooLongError


class TextReIDClientTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.space = "fs-chinese-clip-test"
        self.contract = "text-v1"
        self.dim = 4
        self.text_vector = [1.0, 0.0, 0.0, 0.0]
        self.health_block = self._health()
        self.text_overrides = {}
        self.text_status = 200
        self.client_class = httpx.Client

    def _health(self):
        return {
            "ready": True, "feature_space_id": self.space, "embedding_dim": self.dim,
            "text_contract_id": self.contract, "alignment_verified": True,
        }

    def handler(self, request):
        self.calls.append(request)
        if request.url.path == "/health":
            return httpx.Response(200, json={"ready": True, "text_reid": self.health_block})
        self.assertEqual(request.url.path, "/v1/reid/text-features")
        if self.text_status != 200:
            return httpx.Response(self.text_status,
                                  json={"detail": {"error_code": "TEXT_TOO_LONG"}})
        payload = {
            "feature_type": "text", "model_profile": "chinese_clip_text_reid",
            "embedding": self.text_vector, "embedding_dim": self.dim,
            "feature_space_id": self.space, "text_contract_id": self.contract,
            "normalized": True, "dtype": "float32", "language": "zh",
            "template_id": "", "text_chars": 5, "token_count": 4, "truncated": False,
        }
        payload.update(self.text_overrides)
        return httpx.Response(200, json=payload)

    def client(self, **kwargs):
        self.assertFalse(kwargs["trust_env"])
        return self.client_class(transport=httpx.MockTransport(self.handler), **kwargs)

    def test_encodes_text_without_encoding_registration_images(self):
        client = TextReIDClient("http://reid.test")
        with patch("llm_agent_service.service.text_reid_client.httpx.Client", self.client):
            query, info = client.query_text("红色上衣")
        self.assertEqual(query, self.text_vector)
        self.assertEqual(info["feature_space_id"], self.space)
        self.assertEqual(info["text_contract_id"], self.contract)
        self.assertEqual(info["language"], "zh")
        self.assertEqual(info["token_count"], 4)
        self.assertEqual(info["embedding_dim"], self.dim)
        self.assertEqual([call.url.path for call in self.calls],
                         ["/health", "/v1/reid/text-features"])

    def test_unready_or_incomplete_health_is_rejected(self):
        client = TextReIDClient("http://reid.test")
        with patch("llm_agent_service.service.text_reid_client.httpx.Client", self.client):
            for changes in ({"ready": False}, {"alignment_verified": False},
                            {"feature_space_id": ""}, {"embedding_dim": 0},
                            {"text_contract_id": ""}):
                self.health_block = dict(self._health(), **changes)
                with self.assertRaisesRegex(ValueError, "未就绪|特征空间"):
                    client.health()
            for block in (None, {}, "invalid"):
                self.health_block = block
                with self.assertRaisesRegex(ValueError, "未提供|未就绪"):
                    client.health()

    def test_space_and_contract_pins_are_enforced(self):
        with patch("llm_agent_service.service.text_reid_client.httpx.Client", self.client):
            with self.assertRaisesRegex(ValueError, "配置不一致"):
                TextReIDClient("http://reid.test", feature_space_id="pinned").health()
            with self.assertRaisesRegex(ValueError, "配置不一致"):
                TextReIDClient("http://reid.test", text_contract_id="pinned").health()

    def test_rejects_mismatched_or_invalid_features(self):
        client = TextReIDClient("http://reid.test")
        with patch("llm_agent_service.service.text_reid_client.httpx.Client", self.client):
            for changes in ({"feature_space_id": "other"}, {"embedding_dim": 8},
                            {"feature_type": "image"}, {"model_profile": "other"},
                            {"normalized": False}, {"text_contract_id": "other"},
                            {"truncated": True}):
                self.text_overrides = changes
                with self.assertRaises(ValueError):
                    client.query_text("红色上衣")
            self.text_overrides = {}
            for vector in ([0.0] * 4, [True] * 4, [1.0, 0.0], [2.0, 0.0, 0.0, 0.0],
                           [float("nan"), 1.0, 0.0, 0.0]):
                self.text_vector = vector
                with self.assertRaises(ValueError):
                    client.query_text("红色上衣")

    def test_rejects_invalid_text_metadata(self):
        client = TextReIDClient("http://reid.test")
        with patch("llm_agent_service.service.text_reid_client.httpx.Client", self.client):
            for changes in ({"language": ""}, {"token_count": 0}, {"text_chars": 0},
                            {"token_count": True}):
                self.text_overrides = changes
                with self.assertRaisesRegex(ValueError, "编码信息"):
                    client.query_text("红色上衣")

    def test_text_length_is_checked_locally_and_remotely(self):
        client = TextReIDClient("http://reid.test", max_text_chars=2)
        with patch("llm_agent_service.service.text_reid_client.httpx.Client", self.client):
            with self.assertRaises(TextTooLongError):
                client.query_text("红色上衣")
        self.assertEqual(self.calls, [])
        client = TextReIDClient("http://reid.test")
        self.text_status = 422
        with patch("llm_agent_service.service.text_reid_client.httpx.Client", self.client):
            with self.assertRaises(TextTooLongError):
                client.query_text("红色上衣")
        self.assertEqual(len(self.calls), 2)  # health + rejected text

    def test_empty_text_is_not_sent(self):
        client = TextReIDClient("http://reid.test")
        with patch("llm_agent_service.service.text_reid_client.httpx.Client", self.client):
            for value in ("", "   ", None):
                with self.assertRaisesRegex(ValueError, "文本描述为空"):
                    client.query_text(value)
        self.assertEqual(self.calls, [])

    def test_http_and_payload_failures_are_sanitized(self):
        def broken_client(**kwargs):
            return self.client_class(
                transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(
                    httpx.ConnectError("refused"))), **kwargs)

        client = TextReIDClient("http://reid.test")
        with patch("llm_agent_service.service.text_reid_client.httpx.Client", broken_client):
            with self.assertRaisesRegex(ValueError, "请求失败"):
                client.health()
        with patch("llm_agent_service.service.text_reid_client.httpx.Client", self.client):
            self.health_block = dict(self._health(), embedding_dim="4")
            with self.assertRaisesRegex(ValueError, "未就绪"):
                client.health()


if __name__ == "__main__":
    unittest.main()