"""Agent 对话服务：请求级能力工具决策。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from llm_agent_service.agent.executor import AgentExecutor
from llm_agent_service.tools.base import public_tool_data


class AgentService:
    """将 API 请求转换为 Agent 执行结果，使用请求级工具目录。"""

    def __init__(self, *, executor: AgentExecutor, registry_factory=None) -> None:
        self.executor = executor
        self.registry_factory = registry_factory

    def process(
        self,
        prompt: str,
        *,
        session_id: str,
        image_base64: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        registry_kwargs = {"registry": self.registry_factory()} if self.registry_factory else {}
        context: dict[str, Any] = {}
        result = self.executor.run(
            prompt,
            session_id=session_id,
            image_base64=image_base64,
            trace_id=trace_id,
            context=context,
            **registry_kwargs,
        )
        response = {"type": "agent", "text": result.answer, "agent": {
            "mode": "agent", "steps": len(result.steps), "finish_reason": result.finish_reason,
        }}
        tool_data = public_tool_data(getattr(result, "data", None))
        if isinstance(tool_data, dict):
            # 保留超分等业务工具的类型，兼容前端原有图片展示和下载逻辑。
            if tool_data.get("type") == "super_resolution":
                response["type"] = "super_resolution"
                response["navigate_to"] = tool_data.get("navigate_to", "super_resolution")
                response["text"] = tool_data.get("text", response["text"])
            response["data"] = tool_data.get("data", tool_data)
            if tool_data.get("navigate_to") and "navigate_to" not in response:
                response["navigate_to"] = tool_data["navigate_to"]
        return response

    def stream(
        self,
        prompt: str,
        *,
        session_id: str,
        image_base64: str | None = None,
        trace_id: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """先完成工具决策，再将唯一一次正文生成实时发送给用户。"""
        yield {"event": "status", "data": {"stage": "processing"}}
        registry_kwargs = {"registry": self.registry_factory()} if self.registry_factory else {}
        context: dict[str, Any] = {}
        for item in self.executor.stream_run(
            prompt,
            session_id=session_id,
            image_base64=image_base64,
            trace_id=trace_id,
            context=context,
            **registry_kwargs,
        ):
            yield item



__all__ = ["AgentService"]
