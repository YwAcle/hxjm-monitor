"""会话图片资产库：去重、上限、过期和引用解析。"""

import base64
import unittest
from unittest.mock import patch

from llm_agent_service.service.image_assets import (
    IMAGE_ASSET_MISSING_NOTE,
    SessionImageAssets,
    image_reference,
)


def data_url(size: int, fill: bytes = b"a") -> str:
    payload = base64.b64encode(fill * size).decode("ascii")
    return f"data:image/png;base64,{payload}"


class ImageReferenceTests(unittest.TestCase):
    def test_detects_chinese_and_english_references(self) -> None:
        for prompt in ("上图里有什么", "刚才那张图是什么颜色", "图片中一共有几个人",
                       "这张照片里的人穿什么", "图里有几个女生", "画面上有几个人",
                       "照片上有几辆车", "镜头的右侧是谁", "what is in the previous image",
                       "describe the image above", "what is in the picture"):
            with self.subTest(prompt=prompt):
                self.assertEqual(image_reference(prompt), (True, None))

    def test_detects_ordinal_references(self) -> None:
        self.assertEqual(image_reference("第一张图里有什么"), (True, 1))
        self.assertEqual(image_reference("第2张图片里的人"), (True, 2))
        self.assertEqual(image_reference("第三幅图"), (True, 3))

    def test_ignores_prompts_without_reference(self) -> None:
        for prompt in ("你好", "查询昨天的异常事件", "帮我找穿红衣服的人", ""):
            with self.subTest(prompt=prompt):
                self.assertEqual(image_reference(prompt), (False, None))


class SessionImageAssetsTests(unittest.TestCase):
    def test_stores_and_returns_assets_in_upload_order(self) -> None:
        store = SessionImageAssets()
        first = store.put("s", data_url(8, b"a"))
        second = store.put("s", data_url(8, b"b"))
        self.assertEqual([asset.asset_id for asset in store.assets("s")],
                         [first.asset_id, second.asset_id])
        self.assertEqual(store.latest("s").asset_id, second.asset_id)
        self.assertEqual(second.mime, "image/png")
        self.assertEqual(second.bytes_len, 8)

    def test_identical_image_is_reused_and_refreshed(self) -> None:
        store = SessionImageAssets()
        first = store.put("s", data_url(8))
        second = store.put("s", data_url(8))
        self.assertEqual(first.asset_id, second.asset_id)
        self.assertGreaterEqual(second.created, first.created)
        self.assertEqual(len(store.assets("s")), 1)

    def test_limits_assets_per_session(self) -> None:
        store = SessionImageAssets(max_per_session=2)
        store.put("s", data_url(8, b"a"))
        store.put("s", data_url(8, b"b"))
        third = store.put("s", data_url(8, b"c"))
        self.assertEqual([asset.asset_id for asset in store.assets("s")][-1], third.asset_id)
        self.assertEqual(len(store.assets("s")), 2)

    def test_per_session_byte_cap_evicts_oldest(self) -> None:
        store = SessionImageAssets(max_bytes_per_session=40)
        store.put("s", data_url(24, b"a"))
        second = store.put("s", data_url(24, b"b"))
        self.assertEqual([asset.asset_id for asset in store.assets("s")], [second.asset_id])

    def test_total_byte_cap_evicts_oldest_across_sessions(self) -> None:
        store = SessionImageAssets(max_total_bytes=40)
        store.put("a", data_url(24, b"a"))
        store.put("b", data_url(24, b"b"))
        self.assertEqual(store.assets("a"), [])
        self.assertEqual(len(store.assets("b")), 1)

    def test_assets_expire_after_ttl(self) -> None:
        clock = [1000.0]
        store = SessionImageAssets(ttl_s=10)
        with patch("llm_agent_service.service.image_assets.monotonic", lambda: clock[0]):
            store.put("s", data_url(8))
            clock[0] += 9
            self.assertEqual(len(store.assets("s")), 1)
            clock[0] += 1
            self.assertEqual(store.assets("s"), [])

    def test_oversized_image_is_rejected(self) -> None:
        store = SessionImageAssets(max_bytes_per_session=4)
        with self.assertRaises(ValueError):
            store.put("s", data_url(5))
        self.assertEqual(store.assets("s"), [])

    def test_sessions_are_isolated(self) -> None:
        store = SessionImageAssets()
        store.put("a", data_url(8))
        self.assertIsNone(store.resolve("b", "刚才那张图")[0])
        self.assertEqual(store.resolve("b", "刚才那张图")[1], "missing")

    def test_clear_removes_session_images(self) -> None:
        store = SessionImageAssets()
        store.put("s", data_url(8))
        self.assertTrue(store.clear("s"))
        self.assertFalse(store.clear("s"))
        self.assertEqual(store.assets("s"), [])

    def test_resolve_uses_latest_or_explicit_ordinal(self) -> None:
        store = SessionImageAssets()
        first = store.put("s", data_url(8, b"a"))
        second = store.put("s", data_url(8, b"b"))
        self.assertEqual(store.resolve("s", "刚才那张图")[0].asset_id, second.asset_id)
        self.assertEqual(store.resolve("s", "第一张图")[0].asset_id, first.asset_id)
        self.assertEqual(store.resolve("s", "第三张图"), (None, "missing"))
        self.assertEqual(store.resolve("s", "你好"), (None, "no_reference"))
        self.assertEqual(store.resolve("empty", "第一张图"), (None, "missing"))

    def test_resolve_refreshes_touched_asset(self) -> None:
        store = SessionImageAssets(ttl_s=10)
        clock = [1000.0]
        with patch("llm_agent_service.service.image_assets.monotonic", lambda: clock[0]):
            asset = store.put("s", data_url(8))
            clock[0] += 8
            store.resolve("s", "刚才那张图")
            clock[0] += 8
            self.assertEqual(len(store.assets("s")), 1)
            self.assertEqual(store.latest("s").created, 1008.0)
        self.assertEqual(asset.bytes_len, 8)

    def test_expired_asset_is_not_returned_from_resolve(self) -> None:
        clock = [1000.0]
        store = SessionImageAssets(ttl_s=5)
        with patch("llm_agent_service.service.image_assets.monotonic", lambda: clock[0]):
            store.put("s", data_url(8))
            clock[0] += 6
            self.assertEqual(store.resolve("s", "刚才那张图"), (None, "missing"))

    def test_missing_note_is_exposed(self) -> None:
        self.assertIn("重新上传", IMAGE_ASSET_MISSING_NOTE)


if __name__ == "__main__":
    unittest.main()