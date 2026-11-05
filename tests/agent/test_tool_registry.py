"""工具协议、注册表和默认工具集合测试。"""

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import BaseModel, Field
import pytz

from llm_agent_service.tools import ToolRegistry, ToolSpec
from llm_agent_service.tools.default_tools import build_default_registry


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
        registry = build_default_registry()
        self.assertEqual(
            {tool["name"] for tool in registry.describe()},
            {
                "parse_time",
                "super_resolve_image",
            },
        )
        self.assertTrue(all(tool["read_only"] for tool in registry.describe()))

    def test_parse_time_tool_returns_normalized_result(self) -> None:
        service = MagicMock()
        service.timezone = pytz.timezone("Asia/Shanghai")
        registry = build_default_registry(timezone="Asia/Shanghai")

        result = registry.invoke(
            "parse_time",
            {"text": "明天下午3点", "reference_time": "2026-09-17T10:00:00+08:00"},
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.data["type"], "datetime")
        self.assertEqual(result.data["start"], "2026-09-18T15:00:00+08:00")
        self.assertEqual(result.data["original_text"], "明天下午3点")



if __name__ == "__main__":
    unittest.main()
