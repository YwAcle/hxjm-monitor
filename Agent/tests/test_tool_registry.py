"""工具协议、注册表和默认工具集合测试。"""

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import BaseModel, Field
import pytz

from llm_agent_service.tools import ToolRegistry, ToolSpec
from llm_agent_service.tools.default_tools import VadArgs, _vad, build_default_registry


class DemoArgs(BaseModel):
    limit: int = Field(ge=1, le=20)


class FakeService:
    """默认工具注册只需要服务对象，不连接真实数据库。"""

    pass


class ToolRegistryTests(unittest.TestCase):
    def _registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(ToolSpec(
            name="demo",
            description="测试工具",
            args_schema=DemoArgs,
            handler=lambda args: {"limit": args.limit},
        ))
        return registry

    def test_duplicate_name_is_rejected(self) -> None:
        registry = self._registry()
        with self.assertRaises(ValueError):
            registry.register(ToolSpec("demo", "重复", DemoArgs, lambda args: None))

    def test_unknown_tool_does_not_run_handler(self) -> None:
        registry = self._registry()
        result = registry.invoke("missing")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "UNKNOWN_TOOL")

    def test_invalid_arguments_are_returned_as_error(self) -> None:
        result = self._registry().invoke("demo", {"limit": 0})
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "TOOL_ERROR")

    def test_describe_does_not_expose_handler(self) -> None:
        description = self._registry().describe()[0]
        self.assertEqual(description["name"], "demo")
        self.assertNotIn("handler", description)
        self.assertIn("properties", description["args_schema"])

    def test_default_registry_contains_read_only_tools(self) -> None:
        registry = build_default_registry(FakeService())
        self.assertEqual(
            {tool["name"] for tool in registry.describe()},
            {
                "parse_time",
                "find_person",
                "query_person_tracklets",
                "query_person_reports",
                "query_reports_by_time",
                "query_vad_events",
                "list_known_persons",
                "super_resolve_image",
            },
        )
        self.assertTrue(all(tool["read_only"] for tool in registry.describe()))

    def test_parse_time_tool_returns_normalized_result(self) -> None:
        service = MagicMock()
        service.timezone = pytz.timezone("Asia/Shanghai")
        registry = build_default_registry(service)

        result = registry.invoke(
            "parse_time",
            {"text": "明天下午3点", "reference_time": "2026-09-17T10:00:00+08:00"},
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.data["type"], "datetime")
        self.assertEqual(result.data["start"], "2026-09-18T15:00:00+08:00")
        self.assertEqual(result.data["original_text"], "明天下午3点")

    @patch("llm_api_service.db.vad_repo.list_vad_anomalies")
    @patch("llm_api_service.db.vad_repo.list_recent_vad_anomalies")
    def test_recent_vad_query_does_not_default_to_today(self, recent_query, range_query) -> None:
        recent_query.return_value = []
        service = MagicMock(engine=object(), schema="public")
        result = _vad(service, VadArgs(time_prompt="距离现在最近", limit=1))
        self.assertEqual(result["count"], 0)
        recent_query.assert_called_once_with(service.engine, "public", limit=1)
        range_query.assert_not_called()

    @patch("llm_api_service.db.vad_repo.list_vad_anomalies")
    @patch("llm_api_service.db.vad_repo.list_recent_vad_anomalies")
    def test_recent_duration_uses_parsed_time_range(self, recent_query, range_query) -> None:
        service = MagicMock(engine=object(), schema="public")
        service._parse_time_range.return_value = SimpleNamespace(start_ts="start", end_ts="end")
        range_query.return_value = []

        result = _vad(service, VadArgs(time_prompt="最近三天的异常", limit=1))

        self.assertEqual(result["count"], 0)
        service._parse_time_range.assert_called_once_with("最近三天的异常")
        range_query.assert_called_once_with(service.engine, "public", "start", "end", limit=1)
        recent_query.assert_not_called()

    @patch("llm_api_service.db.vad_repo.list_recent_vad_anomalies")
    def test_vad_time_is_displayed_in_china_time(self, recent_query) -> None:
        recent_query.return_value = [SimpleNamespace(
            id="event-1",
            created_at=datetime(2026, 8, 22, 15, 7, 10, 164251, tzinfo=timezone.utc),
            anomaly_name="fire",
            stream_id="live/camera_4_boxmot",
        )]
        service = MagicMock(engine=object(), schema="public", timezone=pytz.timezone("Asia/Shanghai"))
        service._get_camera_from_stream_id.return_value = "camera_4"

        result = _vad(service, VadArgs(time_prompt="最近", mode="latest", limit=1))

        self.assertEqual(result["items"][0]["created_at"], "2026年08月22日 23时07分10秒")
        self.assertEqual(result["items"][0]["camera"], "camera_4")


if __name__ == "__main__":
    unittest.main()
