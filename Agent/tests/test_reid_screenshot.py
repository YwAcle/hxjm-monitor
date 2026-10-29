"""截图检测、明确选人、多轮状态与聊天协议。"""
import httpx
import base64
from io import BytesIO
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image
from llm_agent_service.app import create_app
from llm_agent_service.config import DbConfig, ServiceConfig
from llm_agent_service.service.clipreid_client import ClipReIDClient
from llm_agent_service.service.gallery_search import GallerySearchService
from llm_agent_service.service.reid_selection import ReIDSelections
from tests.test_gallery_search import image_data, target
from tests import test_clipreid_client as clip_tests


def detection(status="selection_required"):
    return {"status": status, "image_width": 16, "image_height": 32,
            "coordinate_system": "xyxy_pixels_exif_corrected", "feature": None, "candidates": [
                {"candidate_id": "1", "bbox": [0, 0, 8, 32], "confidence": 0.9},
                {"candidate_id": "2", "bbox": [8, 0, 16, 32], "confidence": 0.8}]}


class ScreenshotTests(unittest.TestCase):
    def service(self):
        client = MagicMock()
        client.screenshot_image.side_effect = ClipReIDClient.screenshot_image
        client.detect.return_value = detection()
        return GallerySearchService(engine=MagicMock(), schema="public", feature_client=client,
                                    text_feature_client=MagicMock())

    def test_multiple_and_no_person_do_not_search_database(self):
        service = self.service()
        with patch("llm_agent_service.service.gallery_search.list_gallery") as rows:
            result = service.search_screenshot(image_data(), 3)
            self.assertEqual(result["type"], "pedestrian_selection")
            self.assertTrue(result["candidates"][0]["image_base64"].startswith("data:image/"))
            service.feature_client.query_gallery.assert_not_called()
            rows.assert_not_called()
            service.feature_client.detect.return_value = {"status": "no_person"}
            self.assertEqual(service.search_screenshot(image_data(), 3)["status"], "no_person")
            rows.assert_not_called()

    def test_invalid_bbox_rejected(self):
        service = self.service()
        for bbox in ([0, 0, 20, 32], [True, 0, 8, 32], [8, 0, 1, 32]):
            bad = detection()
            bad["candidates"][0]["bbox"] = bbox
            service.feature_client.detect.return_value = bad
            with self.assertRaises(ValueError):
                service.search_screenshot(image_data(), 3)

    def test_exif_corrected_before_detection(self):
        image = Image.new("RGB", (10, 20))
        exif = image.getexif()
        exif[274] = 6
        buffer = BytesIO()
        image.save(buffer, format="JPEG", exif=exif)
        fixed = ClipReIDClient.screenshot_image(base64.b64encode(buffer.getvalue()).decode())
        self.assertEqual(fixed.size, (20, 10))

    def test_selection_is_session_scoped_expiring_and_explicit(self):
        gallery = MagicMock()
        gallery.search_selected.return_value = {"type": "pedestrian_search", "status": "ok", "candidates": []}
        store = ReIDSelections(gallery, ttl_s=300, max_sessions=1)
        data = dict(detection(), type="pedestrian_selection", source_asset_id="asset", top_k=3)
        store.remember("a", image_data(), data)
        self.assertEqual(store.resume("b", "选择2")["status"], "selection_expired")
        self.assertEqual(store.resume("a", "你决定")["status"], "selection_required")
        self.assertEqual(store.resume("a", "选择9")["status"], "selection_required")
        gallery.search_selected.assert_not_called()
        result = store.resume("a", "第二个")
        self.assertEqual(result["selected_candidate_id"], "2")
        gallery.search_selected.assert_called_once_with(image_data(), [8, 0, 16, 32], 3)
        self.assertNotIn("a", store.pending)
        store.remember("a", image_data(), data)
        store.remember("b", image_data(), data)
        self.assertNotIn("a", store.pending)
        store.pending["b"]["created"] -= 301
        self.assertEqual(store.resume("b", "选择1")["status"], "selection_expired")
        store.remember("a", image_data(), data)
        self.assertIsNone(store.resume("a", "新图", image_data()))
        self.assertNotIn("a", store.pending)
        store.remember("a", image_data(), data)
        self.assertEqual(store.resume("a", "取消")["status"], "cancelled")

    def test_chat_and_sse_two_turns_and_clear(self):
        for streaming in (False, True):
            llm = MagicMock()
            llm.invoke.return_value = SimpleNamespace(content='{"action":"tool","tool_name":"search_pedestrians_in_screenshot","arguments":{"top_k":3}}')
            gallery = self.service()
            gallery.search_selected = MagicMock(return_value={"type": "pedestrian_search", "status": "ok", "candidates": [
                {"person_id": "A", "name": "候选A", "similarity": 0.9, "image_base64": image_data()}]})
            with patch("llm_agent_service.app.ReidService") as reid, patch("llm_agent_service.app.GallerySearchService", return_value=gallery):
                reid.return_value.clear_memory.return_value = False
                app = create_app(engine=MagicMock(), db_cfg=DbConfig("localhost", 5432, "u", "p", "db"),
                                 svc_cfg=ServiceConfig(), llm=llm)
            browser = app.test_client()
            endpoint = "/chat/stream" if streaming else "/chat"
            response = browser.post(endpoint, json={"session_id": "s", "prompt": "截图找人", "image": image_data()})
            body = response.get_data(as_text=True)
            self.assertIn("selection_required", body)
            self.assertIn("pedestrian_selection", body)
            llm.invoke.assert_called_once()
            llm.stream.assert_not_called()  # 多人选择不额外调用模型生成正文
            response = browser.post(endpoint, json={"session_id": "s", "prompt": "选择2"})
            body = response.get_data(as_text=True)
            self.assertIn("pedestrian_search", body)
            gallery.search_selected.assert_called_once()
            llm.invoke.assert_called_once()
            if streaming:
                self.assertIn("event: result", body)
                self.assertIn("event: done", body)
            # 重建待选择状态并清空会话
            browser.post(endpoint, json={"session_id": "s", "prompt": "截图找人", "image": image_data()}).get_data()
            self.assertEqual(browser.delete("/sessions/s/memory").status_code, 200)
            response = browser.post(endpoint, json={"session_id": "s", "prompt": "选择2"})
            self.assertIn("selection_expired", response.get_data(as_text=True))


class ScreenshotProtocolTests(unittest.TestCase):
    setUp = clip_tests.ClipReIDTests.setUp
    client = clip_tests.ClipReIDTests.client
    def handler(self, request):
        if request.url.path == "/v1/reid/person-crops":
            self.calls.append(request)
            return httpx.Response(200, json={
                "status": "extracted", "image_width": 16, "image_height": 32,
                "coordinate_system": "xyxy_pixels_exif_corrected",
                "candidates": [{"candidate_id": "1", "bbox": [0, 0, 16, 32]}],
                "feature": {"feature_type": "image", "embedding_dim": 3072, "normalized": True,
                            "feature_space_id": self.space, "embedding": self.vector}})
        return clip_tests.ClipReIDTests.handler(self, request)

    def test_single_uses_existing_feature_and_selection_posts_bbox(self):
        service = GallerySearchService(engine=MagicMock(), schema="public", feature_client=ClipReIDClient("http://reid.test"),
                                       text_feature_client=MagicMock())
        with patch("llm_agent_service.service.clipreid_client.httpx.Client", self.client), \
             patch("llm_agent_service.service.gallery_search.list_gallery", return_value=[target("A")]):
            result = service.search_screenshot(image_data(), 3)
            self.assertEqual(result["candidates"][0]["person_id"], "A")
            # detect + health + gallery encode，单人已返回的特征不重复提取
            self.assertEqual(len(self.calls), 3)
            service.search_selected(image_data(), [8, 0, 16, 32], 3)
            post = self.calls[-1]
            self.assertIn(b'name="bbox"', post.content)
            self.assertIn(b'[8, 0, 16, 32]', post.content)
