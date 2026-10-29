"""Agent 执行过程中使用的基础数据模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator


class AgentFinal(BaseModel):
    """模型决定结束执行时返回的最终回答。"""

    model_config = ConfigDict(extra="forbid")

    action: Literal["final"] = "final"
    answer: str = Field(min_length=1)
    citations: list[str] = Field(default_factory=list)
    navigate_to: str | None = None
    decision_reason: str | None = Field(default=None, max_length=200)


class AgentToolAction(BaseModel):
    """服务端生成约束中的工具动作。"""

    model_config = ConfigDict(extra="forbid")

    action: Literal["tool"]
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any]
    decision_reason: str | None = Field(default=None, max_length=200)


class AgentFinalAction(AgentFinal):
    action: Literal["final"]


def agent_decision_response_format(*, prepare_stream: bool = False) -> dict[str, Any]:
    # Python model validators do not encode conditional requirements in JSON Schema.
    # Separate branches require an answer for final and arguments for tool.
    schema = TypeAdapter(AgentToolAction | AgentFinalAction).json_schema()
    if prepare_stream:
        schema["$defs"]["AgentFinalAction"]["properties"]["answer"]["const"] = "准备回答"
    return {
        "type": "json_schema",
        "json_schema": {"name": "agent_decision", "strict": True, "schema": schema},
    }


class AgentAction(BaseModel):
    """模型每一步只能选择调用工具或直接结束。"""

    model_config = ConfigDict(extra="forbid")

    action: Literal["tool", "final"]
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    answer: str | None = None
    citations: list[str] = Field(default_factory=list)
    navigate_to: str | None = None
    decision_reason: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_action_fields(self) -> "AgentAction":
        """确保两类动作都包含自身所需的核心字段。"""
        if self.action == "tool" and not self.tool_name:
            raise ValueError("tool 动作必须提供 tool_name")
        if self.action == "final" and not self.answer:
            raise ValueError("final 动作必须提供 answer")
        return self


class AgentStepStatus:
    """步骤状态常量，避免在日志和响应中散落字符串。"""

    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AgentStep(BaseModel):
    """一次模型决策或工具执行的摘要，不保存模型思维过程。"""

    model_config = ConfigDict(extra="forbid")

    step: int = Field(ge=1)
    action: Literal["tool", "final"]
    tool_name: str | None = None
    status: Literal["started", "succeeded", "failed"] = AgentStepStatus.STARTED
    arguments: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None
    elapsed_ms: int | None = Field(default=None, ge=0)
    created_at: datetime = Field(default_factory=datetime.now)


class FinishReason:
    """Agent 循环的结束原因常量。"""

    FINAL = "final"
    LENGTH = "length"
    MAX_STEPS = "max_steps"
    TIMEOUT = "timeout"
    ERROR = "error"
    FALLBACK = "fallback"


__all__ = ["AgentAction", "AgentFinal", "AgentStep", "AgentStepStatus", "FinishReason"]
