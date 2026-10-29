"""Agent 工具注册表。"""

from __future__ import annotations

from typing import Any

from llm_agent_service.tools.base import ToolResult, ToolSpec


class ToolRegistry:
    """按稳定名称管理工具，拒绝重复注册和未知调用。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, tool: ToolSpec) -> None:
        if not tool.name or not tool.name.strip():
            raise ValueError("工具名称不能为空")
        if tool.name in self._tools:
            raise ValueError(f"工具已注册: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"未知工具: {name}") from exc

    def list(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def describe(self) -> list[dict[str, Any]]:
        """供 /tools 和 Agent 提示词使用；参数的 Field 描述随 JSON Schema 一并传递。"""
        return [{
            "name": tool.name,
            "description": tool.description,
            "read_only": tool.read_only,
            "args_schema": tool.args_schema.model_json_schema(),
        } for tool in self.list()]

    def invoke(self, name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
        """只允许调用已注册工具，未知名称不会触发任何处理函数。"""
        try:
            tool = self.get(name)
        except KeyError as exc:
            return ToolResult(ok=False, error_code="UNKNOWN_TOOL", error_message=str(exc))
        return tool.invoke(arguments or {})


__all__ = ["ToolRegistry"]
