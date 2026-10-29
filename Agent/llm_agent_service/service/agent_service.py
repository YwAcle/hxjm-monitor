"""Agent 对话服务：工具决策与待选择截图的明确用户续接。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from llm_agent_service.agent.executor import AgentExecutor
from llm_agent_service.service.reid_selection import ReIDSelections, selection_text


class AgentService:
    """将 API 请求转换为 Agent 执行结果，显式续接用户的截图选择。"""

    def __init__(self, *, executor: AgentExecutor, gallery_search=None) -> None:
        self.executor = executor
        self.selections = ReIDSelections(gallery_search) if gallery_search is not None else None

    def process(
        self,
        prompt: str,
        *,
        session_id: str,
        image_base64: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        resumed = self.selections.resume(session_id, prompt, image_base64) if self.selections else None
        if resumed is not None:
            text = selection_text(resumed)
            self._save_exchange(session_id, prompt, text)
            return {"type": "agent", "text": text, "data": resumed,
                    "agent": {"mode": "agent", "steps": 1, "finish_reason": "final"}}
        context: dict[str, Any] = {}
        result = self.executor.run(
            prompt,
            session_id=session_id,
            image_base64=image_base64,
            trace_id=trace_id,
            context=context,
        )
        if self.selections:
            # 截图可能来自上一轮回注而非本次上传，用执行器确认的实际图片保存待选择状态。
            self.selections.remember(
                session_id,
                image_base64 or context.get("effective_image"),
                getattr(result, "data", None),
            )
        response = {"type": "agent", "text": result.answer, "agent": {
            "mode": "agent", "steps": len(result.steps), "finish_reason": result.finish_reason,
        }}
        tool_data = getattr(result, "data", None)
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
        resumed = self.selections.resume(session_id, prompt, image_base64) if self.selections else None
        if resumed is not None:
            text = selection_text(resumed)
            self._save_exchange(session_id, prompt, text)
            yield {"event": "delta", "data": {"text": text}}
            yield {"event": "result", "data": resumed}
            yield {"event": "done", "data": {"session_id": session_id, "finish_reason": "final", "steps": 1}}
            return
        context: dict[str, Any] = {}
        for item in self.executor.stream_run(
            prompt,
            session_id=session_id,
            image_base64=image_base64,
            trace_id=trace_id,
            context=context,
        ):
            if item.get("event") == "result" and self.selections:
                self.selections.remember(
                    session_id,
                    image_base64 or context.get("effective_image"),
                    item.get("data"),
                )
            yield item

    def _save_exchange(self, session_id, prompt, text):
        if self.executor.memory is not None:
            with self.executor.memory.conversation(session_id) as conversation:
                conversation.add_exchange(prompt, text)


__all__ = ["AgentService"]
