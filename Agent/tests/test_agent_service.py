"""纯 Agent 业务适配层测试。"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock

from llm_agent_service.agent.prompts import build_system_prompt
from llm_agent_service.service.agent_service import AgentService


class AgentServiceTests(unittest.TestCase):
    def test_text_request_is_delegated_to_agent_executor(self) -> None:
        executor = MagicMock()
        executor.run.return_value = SimpleNamespace(
            answer="你好，有什么可以帮助你的？",
            steps=[object()],
            finish_reason="final",
        )
        service = AgentService(executor=executor)

        result = service.process("你好", session_id="session-1")

        self.assertEqual(result["type"], "agent")
        self.assertEqual(result["text"], "你好，有什么可以帮助你的？")
        self.assertEqual(result["agent"]["steps"], 1)
        self.assertEqual(result["agent"]["finish_reason"], "final")
        executor.run.assert_called_once_with(
            "你好",
            session_id="session-1",
            image_base64=None,
            trace_id=None,
            context=ANY,
        )

    def test_image_request_is_delegated_to_agent_executor(self) -> None:
        executor = MagicMock()
        executor.run.return_value = SimpleNamespace(
            answer="图片中是一辆汽车。",
            steps=[object()],
            finish_reason="final",
        )
        service = AgentService(executor=executor)

        result = service.process(
            "描述图片",
            session_id="session-1",
            image_base64="data:image/jpeg;base64,dGVzdA==",
        )

        self.assertEqual(result["text"], "图片中是一辆汽车。")
        executor.run.assert_called_once_with(
            "描述图片",
            session_id="session-1",
            image_base64="data:image/jpeg;base64,dGVzdA==",
            trace_id=None,
            context=ANY,
        )

    def test_system_prompt_allows_final_without_tool_call(self) -> None:
        prompt = build_system_prompt([])
        self.assertIn("普通对话，必须直接返回 final", prompt)
        self.assertIn("不得调用工具", prompt)

    def test_selection_state_uses_recalled_image(self) -> None:
        stored = "data:image/png;base64,c3RvcmVk"
        selection = {
            "type": "pedestrian_selection", "status": "selection_required",
            "candidates": [{"candidate_id": "1", "bbox": [0, 0, 8, 32]}], "top_k": 3,
        }
        executor = MagicMock()

        def run(prompt, **kwargs):
            kwargs["context"]["effective_image"] = stored
            return SimpleNamespace(answer="请选择编号", steps=[object()],
                                   finish_reason="final", data=selection)

        executor.run.side_effect = run
        service = AgentService(executor=executor, gallery_search=MagicMock())

        service.process("帮我找图里的人", session_id="s")

        self.assertEqual(service.selections.pending["s"]["image"], stored)

    def test_stream_selection_state_uses_recalled_image(self) -> None:
        stored = "data:image/png;base64,c3RvcmVk"
        selection = {
            "type": "pedestrian_selection", "status": "selection_required",
            "candidates": [{"candidate_id": "1", "bbox": [0, 0, 8, 32]}], "top_k": 3,
        }
        executor = MagicMock()

        def stream_run(prompt, **kwargs):
            kwargs["context"]["effective_image"] = stored
            yield {"event": "result", "data": selection}
            yield {"event": "done", "data": {"finish_reason": "final"}}

        executor.stream_run.side_effect = stream_run
        service = AgentService(executor=executor, gallery_search=MagicMock())

        list(service.stream("帮我找图里的人", session_id="s"))

        self.assertEqual(service.selections.pending["s"]["image"], stored)

    def test_super_resolution_result_keeps_frontend_type_and_data(self) -> None:
        executor = MagicMock()
        executor.run.return_value = SimpleNamespace(
            answer="图片超分完成：100×100。",
            steps=[object(), object()],
            finish_reason="final",
            data={
                "type": "super_resolution",
                "navigate_to": "super_resolution",
                "text": "图片超分完成：100×100。",
                "data": {"status": "success", "image_base64": "data:image/jpeg;base64,test"},
            },
        )
        result = AgentService(executor=executor).process("超分", session_id="s")
        self.assertEqual(result["type"], "super_resolution")
        self.assertEqual(result["data"]["image_base64"], "data:image/jpeg;base64,test")


if __name__ == "__main__":
    unittest.main()
