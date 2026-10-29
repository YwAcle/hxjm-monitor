"""新增 Agent 工具查询接口测试。"""

import base64
import unittest
from unittest.mock import MagicMock, patch

from llm_agent_service.app import create_app
from llm_agent_service.config import DbConfig, ServiceConfig
from llm_agent_service.service.image_assets import SessionImageAssets


class AgentToolsApiTests(unittest.TestCase):
    def test_tools_endpoint_returns_public_metadata(self) -> None:
        service = MagicMock()
        with patch("llm_agent_service.app.ReidService", return_value=service):
            app = create_app(
                engine=MagicMock(),
                db_cfg=DbConfig("localhost", 5432, "user", "password", "db"),
                svc_cfg=ServiceConfig(),
                llm=MagicMock(),
            )

        response = app.test_client().get("/tools")
        self.assertEqual(response.status_code, 200)
        tools = response.get_json()["tools"]
        self.assertEqual(len(tools), 11)
        self.assertIn("search_pedestrians_in_screenshot", {item["name"] for item in tools})
        self.assertTrue(all("handler" not in item for item in tools))
        self.assertTrue(all(item["read_only"] for item in tools))


class SessionImageAssetApiTests(unittest.TestCase):
    def test_session_clear_also_removes_stored_images(self) -> None:
        with patch("llm_agent_service.app.ReidService") as reid, \
             patch("llm_agent_service.app.AgentExecutor") as executor:
            reid.return_value.clear_memory.return_value = False
            app = create_app(
                engine=MagicMock(),
                db_cfg=DbConfig("localhost", 5432, "user", "password", "db"),
                svc_cfg=ServiceConfig(),
                llm=MagicMock(),
            )

        store = executor.call_args.kwargs["image_assets"]
        self.assertIsInstance(store, SessionImageAssets)
        store.put("s", "data:image/png;base64," + base64.b64encode(b"a").decode("ascii"))

        response = app.test_client().delete("/sessions/s/memory")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(store.assets("s"), [])


if __name__ == "__main__":
    unittest.main()
