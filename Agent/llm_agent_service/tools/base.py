"""工具的统一定义、输入校验和返回结果协议。"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable, Type

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """工具执行结果；错误信息不应包含 SQL 或敏感配置。"""

    ok: bool
    data: dict[str, Any] | list[Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    truncated: bool = False
    elapsed_ms: int = Field(default=0, ge=0)


@dataclass(frozen=True)
class ToolSpec:
    """一个只读工具的名称、参数模型和处理函数。"""

    name: str
    description: str
    args_schema: Type[BaseModel]
    handler: Callable[[BaseModel], Any]
    timeout_s: float = 10.0
    result_limit: int = 20
    read_only: bool = True

    def invoke(self, arguments: dict[str, Any]) -> ToolResult:
        """校验参数后调用处理函数，并统一封装异常。"""
        started = monotonic()
        try:
            parsed = self.args_schema.model_validate(arguments)
            data = self.handler(parsed)
            return ToolResult(ok=True, data=data, elapsed_ms=_elapsed_ms(started))
        except Exception as exc:  # 工具边界统一转为稳定错误，不泄漏内部细节
            return ToolResult(
                ok=False,
                error_code="TOOL_ERROR",
                error_message=str(exc),
                elapsed_ms=_elapsed_ms(started),
            )


def _elapsed_ms(started: float) -> int:
    return max(0, int((monotonic() - started) * 1000))


__all__ = ["ToolResult", "ToolSpec"]
