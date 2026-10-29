"""登记库主动检索：模型兼容性、候选映射及聊天图片/结果传递。"""

import base64
import json
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image

from llm_agent_service.agent.executor import AgentExecutor
from llm_agent_service.app import create_app
from llm_agent_service.config import DbConfig, ServiceConfig
from llm_agent_service.db.gallery_repo import GalleryTarget, list_gallery
from llm_agent_service.service.gallery_search import GallerySearchService
from llm_agent_service.service.text_reid_client import TextTooLongError
from llm_agent_service.tools.default_tools import build_default_registry


def image_data():
    output = BytesIO()
    Image.new("RGB", (16, 32), "red").save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()


def target(person_id, image=None):
    return GalleryTarget(person_id, "登记" + person_id, "E" + person_id,
                         image if image is not None else image_data())


class GallerySearchTests(unittest.TestCase):
    def setUp(self):
        self.features = MagicMock(method="remote_clipreid")
        self.text_features = MagicMock(method="remote_chinese_clip_text")
        self.service = GallerySearchService(
            engine=MagicMock(), schema="public", feature_client=self.features,
            text_feature_client=self.text_features, text_max_chars=20,
        )

    @patch("llm_agent_service.service.gallery_search.list_gallery")
    def test_ranks_clipreid_features_and_skips_missing_images(self, gallery):
        gallery.return_value = [target("B"), target("A"), target("C", image="")]
        self.features.query_gallery.return_value = ([1, 0], {"A": [1, 0], "B": [0, 1]}, "clipreid-test")
        result = self.service.search_image(image_data(), 1)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["compatible_count"], 2)
        self.assertEqual(result["skipped_count"], 1)
        self.assertEqual(result["method"], "remote_clipreid")
        self.assertEqual(result["embedding_model"], "clipreid-test")
        self.assertEqual(result["candidates"][0]["person_id"], "A")
        self.assertAlmostEqual(result["candidates"][0]["similarity"], 1)
        self.features.query_gallery.assert_called_once()

    @patch("llm_agent_service.service.gallery_search.list_gallery")
    def test_missing_and_invalid_images_do_not_search(self, gallery):
        self.assertEqual(self.service.search_image("", 5)["status"], "missing_image")
        with self.assertRaisesRegex(ValueError, "无法解码"):
            self.service.search_image("invalid image", 5)
        gallery.assert_not_called()
        self.features.query_gallery.assert_not_called()

    @patch("llm_agent_service.service.gallery_search.list_gallery")
    def test_gallery_limit_and_tie_order_are_explicit(self, gallery):
        self.service.candidate_limit = 2
        rows = [target("B"), target("A"), target("C")]
        gallery.return_value = rows
        self.features.query_gallery.return_value = ([1, 0], {"A": [1, 0], "B": [1, 0]}, "clipreid-test")
        result = self.service.search_image(image_data(), 5)
        self.assertTrue(result["gallery_truncated"])
        self.assertEqual(result["scanned_count"], 2)
        self.assertEqual(result["count"], 2)
        self.assertEqual([item["person_id"] for item in result["candidates"]], ["A", "B"])
        gallery.assert_called_once_with(self.service.engine, "public", 3)
        self.assertEqual(self.features.query_gallery.call_args.args[1], rows[:2])

    @patch("llm_agent_service.service.gallery_search.list_gallery")
    def test_empty_gallery_and_unusable_photos_are_distinct(self, gallery):
        self.features.query_gallery.return_value = ([1, 0], {}, "clipreid-test")
        gallery.return_value = []
        self.assertEqual(self.service.search_image(image_data(), 5)["status"], "empty_gallery")
        gallery.return_value = [target("A", image="invalid")]
        self.assertEqual(self.service.search_image(image_data(), 5)["status"], "no_valid_images")

    @patch("llm_agent_service.service.gallery_search.list_gallery")
    def test_clipreid_failure_is_not_reported_as_no_match(self, gallery):
        gallery.return_value = [target("A")]
        self.features.query_gallery.side_effect = ValueError("CLIP-ReID 服务请求失败")
        with self.assertRaisesRegex(ValueError, "请求失败"):
            self.service.search_image(image_data(), 5)

    @patch("llm_agent_service.service.gallery_search.list_gallery")
    def test_text_search_ranks_chinese_clip_features(self, gallery):
        gallery.return_value = [target("B"), target("A"), target("C", image="")]
        self.text_features.query_gallery.return_value = (
            [1, 0], {"A": [1, 0], "B": [0, 1]},
            {"feature_space_id": "chinese-clip-test", "embedding_dim": 2,
             "text_contract_id": "text-v1", "language": "zh",
             "token_count": 4, "text_chars": 5},
        )
        result = self.service.search_description("红衣服的人", 1)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["search_type"], "text")
        self.assertEqual(result["method"], "remote_chinese_clip_text")
        self.assertEqual(result["embedding_model"], "chinese-clip-test")
        self.assertEqual(result["text_contract_id"], "text-v1")
        self.assertEqual(result["feature_dimension"], 2)
        self.assertEqual(result["scanned_count"], 3)
        self.assertEqual(result["compatible_count"], 2)
        self.assertEqual(result["skipped_count"], 1)
        self.assertEqual(result["token_count"], 4)
        self.assertEqual(result["candidates"][0]["person_id"], "A")
        self.assertAlmostEqual(result["candidates"][0]["similarity"], 1)
        self.assertNotIn("match_reason", result["candidates"][0])
        self.text_features.query_gallery.assert_called_once()
        self.assertEqual(self.text_features.query_gallery.call_args.args[0], "红衣服的人")

    @patch("llm_agent_service.service.gallery_search.list_gallery")
    def test_text_search_gallery_limit_and_tie_order(self, gallery):
        self.service.candidate_limit = 2
        gallery.return_value = [target("B"), target("A"), target("C")]
        self.text_features.query_gallery.return_value = (
            [1, 0], {"A": [1, 0], "B": [1, 0]},
            {"feature_space_id": "chinese-clip-test", "embedding_dim": 2,
             "text_contract_id": "text-v1", "language": "zh",
             "token_count": 2, "text_chars": 2},
        )
        result = self.service.search_description("红衣", 5)
        self.assertTrue(result["gallery_truncated"])
        self.assertEqual(result["scanned_count"], 2)
        self.assertEqual([item["person_id"] for item in result["candidates"]], ["A", "B"])
        gallery.assert_called_once_with(self.service.engine, "public", 3)
        self.assertEqual(self.text_features.query_gallery.call_args.args[1], gallery.return_value[:2])

    @patch("llm_agent_service.service.gallery_search.list_gallery")
    def test_empty_or_too_long_description_is_not_searched(self, gallery):
        self.assertEqual(self.service.search_description("  ", 5)["status"], "missing_description")
        self.assertEqual(self.service.search_description("红" * 21, 5)["status"],
                         "description_too_long")
        gallery.assert_not_called()
        self.text_features.query_gallery.assert_not_called()

    @patch("llm_agent_service.service.gallery_search.list_gallery")
    def test_remote_text_too_long_is_reported_without_partial_results(self, gallery):
        gallery.return_value = [target("A")]
        self.text_features.query_gallery.side_effect = TextTooLongError("too long")
        result = self.service.search_description("红衣服", 5)
        self.assertEqual(result["status"], "description_too_long")
        self.assertEqual(result["candidates"], [])

    @patch("llm_agent_service.service.gallery_search.list_gallery")
    def test_empty_gallery_skips_remote_text_encoding(self, gallery):
        gallery.return_value = []
        result = self.service.search_description("红衣服", 5)
        self.assertEqual(result["status"], "empty_gallery")
        self.text_features.query_gallery.assert_not_called()

    @patch("llm_agent_service.service.gallery_search.list_gallery")
    def test_unusable_photos_are_not_reported_as_no_match(self, gallery):
        gallery.return_value = [target("A", image="invalid image")]
        self.text_features.query_gallery.return_value = (
            [1, 0], {},
            {"feature_space_id": "chinese-clip-test", "embedding_dim": 2,
             "text_contract_id": "text-v1", "language": "zh",
             "token_count": 2, "text_chars": 2},
        )
        result = self.service.search_description("红衣服", 5)
        self.assertEqual(result["status"], "no_valid_images")
        self.assertNotIn(result["status"], {"no_match", "no_person", "selection_required"})

    @patch("llm_agent_service.service.gallery_search.list_gallery")
    def test_text_service_failure_is_not_reported_as_no_match(self, gallery):
        gallery.return_value = [target("A")]
        self.text_features.query_gallery.side_effect = ValueError("Chinese-CLIP 服务请求失败")
        with self.assertRaisesRegex(ValueError, "请求失败"):
            self.service.search_description("红衣服", 5)

    def test_repository_reads_active_photos_without_old_embeddings(self):
        engine = MagicMock()
        engine.connect.return_value.__enter__.return_value.execute.return_value.mappings.return_value.all.return_value = [{
            "id": "A", "name": "登记A", "employee_id": "E1", "image_base64": image_data(),
            "embedding_model": "model-v1", "embedding": "[1, 0]",
        }]
        rows = list_gallery(engine, "public", 3)
        self.assertEqual(rows[0].image_base64, image_data())
        self.assertFalse(hasattr(rows[0], "embedding"))
        execute = engine.connect.return_value.__enter__.return_value.execute
        self.assertIn("WHERE is_active = true", str(execute.call_args.args[0]))
        self.assertNotIn("embedding", str(execute.call_args.args[0]))
        self.assertEqual(execute.call_args.args[1], {"limit": 3})
        with self.assertRaises(ValueError):
            list_gallery(engine, 'public"; DROP TABLE x', 3)


class GalleryChatTests(unittest.TestCase):
    def test_description_tool_does_not_receive_uploaded_image(self):
        gallery = MagicMock()
        gallery.search_description.return_value = {
            "type": "pedestrian_search", "search_type": "text", "status": "ok",
            "candidates": [{"person_id": "A", "similarity": 0.31}],
        }
        registry = build_default_registry(MagicMock(), gallery)
        llm = MagicMock()
        llm.invoke.side_effect = [
            SimpleNamespace(content=json.dumps({
                "action": "tool", "tool_name": "search_pedestrians_by_description",
                "arguments": {"description": "红色上衣", "top_k": 2, "image_base64": "FORGED"},
            })),
            SimpleNamespace(content='{"action":"final","answer":"找到候选"}'),
        ]
        result = AgentExecutor(llm=llm, registry=registry).run(
            "找穿红衣服的人", image_base64=image_data())
        gallery.search_description.assert_called_once_with("红色上衣", 2)
        self.assertEqual(result.data["search_type"], "text")

    def test_text_search_returns_candidate_cards(self):
        for streaming in (False, True):
            llm = MagicMock()
            llm.invoke.side_effect = [
                SimpleNamespace(content=json.dumps({
                    "action": "tool", "tool_name": "search_pedestrians_by_description",
                    "arguments": {"description": "红色上衣"},
                })),
                SimpleNamespace(content='{"action":"final","answer":"准备回答"}'),
            ]
            llm.stream.return_value = iter([SimpleNamespace(content="候选A")])
            gallery = MagicMock()
            gallery.search_description.return_value = {
                "type": "pedestrian_search", "search_type": "text", "status": "ok",
                "method": "remote_chinese_clip_text",
                "candidates": [{"person_id": "A", "similarity": 0.31,
                                "image_base64": image_data()}],
            }
            with patch("llm_agent_service.app.ReidService"), \
                 patch("llm_agent_service.app.GallerySearchService", return_value=gallery):
                app = create_app(engine=MagicMock(), db_cfg=DbConfig("localhost", 5432, "u", "p", "db"),
                                 svc_cfg=ServiceConfig(), llm=llm)
            response = app.test_client().post("/chat/stream" if streaming else "/chat", json={
                "prompt": "找穿红色上衣的人", "session_id": "text-search-test",
            })
            self.assertEqual(response.status_code, 200)
            if streaming:
                body = response.get_data(as_text=True)
                self.assertIn("event: result", body)
                self.assertIn("remote_chinese_clip_text", body)
                self.assertIn("similarity", body)
                self.assertIn("event: done", body)
            else:
                data = response.get_json()["data"]
                self.assertEqual(data["search_type"], "text")
                self.assertAlmostEqual(data["candidates"][0]["similarity"], 0.31)
            gallery.search_description.assert_called_once_with("红色上衣", 5)
    def test_executor_uses_uploaded_image_and_keeps_photos_out_of_model_observation(self):
        gallery = MagicMock()
        image = image_data()
        gallery.search_image.return_value = {
            "type": "pedestrian_search", "candidates": [{"person_id": "A", "image_base64": image}],
        }
        registry = build_default_registry(MagicMock(), gallery)
        llm = MagicMock()
        llm.invoke.side_effect = [
            SimpleNamespace(content=json.dumps({"action": "tool", "tool_name": "search_pedestrians_by_image",
                                                "arguments": {"image_base64": "FORGED"}})),
            SimpleNamespace(content='{"action":"final","answer":"找到一个相似候选"}'),
        ]
        result = AgentExecutor(llm=llm, registry=registry).run("用图片找人", image_base64=image)
        gallery.search_image.assert_called_once_with(image, 5)
        self.assertEqual(result.data["candidates"][0]["image_base64"], image)
        observation = llm.invoke.call_args.args[0][-1].content
        self.assertNotIn(image, observation)
        self.assertIn("person_id", observation)

    def test_chat_and_stream_return_candidate_cards(self):
        for streaming in (False, True):
            llm = MagicMock()
            llm.invoke.side_effect = [
                SimpleNamespace(content='{"action":"tool","tool_name":"search_pedestrians_by_image","arguments":{}}'),
                SimpleNamespace(content='{"action":"final","answer":"准备回答"}'),
            ]
            llm.stream.return_value = iter([SimpleNamespace(content="候选A")])
            gallery = MagicMock()
            gallery.search_image.return_value = {"type": "pedestrian_search", "status": "ok",
                "candidates": [{"person_id": "A", "image_base64": image_data()}]}
            with patch("llm_agent_service.app.ReidService"), patch("llm_agent_service.app.GallerySearchService", return_value=gallery):
                app = create_app(engine=MagicMock(), db_cfg=DbConfig("localhost", 5432, "u", "p", "db"),
                                 svc_cfg=ServiceConfig(), llm=llm)
            response = app.test_client().post("/chat/stream" if streaming else "/chat", json={
                "prompt": "用这张图片找相似行人", "image": image_data(), "session_id": "gallery-test",
            })
            self.assertEqual(response.status_code, 200)
            if streaming:
                body = response.get_data(as_text=True)
                self.assertIn("event: result", body)
                self.assertIn('"person_id":"A"', body.replace(" ", ""))
                self.assertIn("event: done", body)
            else:
                self.assertEqual(response.get_json()["data"]["candidates"][0]["person_id"], "A")


if __name__ == "__main__":
    unittest.main()
