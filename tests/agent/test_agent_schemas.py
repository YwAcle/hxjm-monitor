"""Agent 基础数据模型测试。"""

import unittest
import jsonschema

from llm_agent_service.agent.schemas import agent_decision_response_format

from pydantic import ValidationError

from llm_agent_service.agent import AgentAction, AgentFinal, AgentStep


class AgentSchemaTests(unittest.TestCase):
    def test_server_schema_requires_valid_action_branches(self) -> None:
        schema = agent_decision_response_format()["json_schema"]["schema"]
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(schema)
        for payload in (
            {"action": "final", "answer": "完成"},
            {"action": "tool", "tool_name": "demo", "arguments": {"limit": 1}},
        ):
            validator.validate(payload)
        for payload in (
            {"answer": "完成"}, {"action": "final"},
            {"action": "final", "answer": ""},
            {"action": "tool", "tool_name": "demo"},
            {"action": "tool", "tool_name": "", "arguments": {}},
            {"action": "tool", "tool_name": "demo", "arguments": "invalid"},
            {"action": "final", "answer": "完成", "unexpected": True},
        ):
            with self.subTest(payload=payload):
                self.assertFalse(validator.is_valid(payload))

    def test_tool_action_accepts_arguments(self) -> None:
        action = AgentAction(
            action="tool",
            tool_name="find_person",
            arguments={"query": "张三"},
            decision_reason="需要先确认人员身份",
        )
        self.assertEqual(action.tool_name, "find_person")
        self.assertEqual(action.decision_reason, "需要先确认人员身份")

    def test_decision_reason_length_is_limited(self) -> None:
        with self.assertRaises(ValidationError):
            AgentAction(action="final", answer="完成", decision_reason="理" * 201)

    def test_final_answer_requires_text(self) -> None:
        with self.assertRaises(ValidationError):
            AgentFinal(answer="")

    def test_step_rejects_invalid_step_number(self) -> None:
        with self.assertRaises(ValidationError):
            AgentStep(step=0, action="tool")

    def test_unknown_fields_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            AgentFinal(answer="完成", unexpected="value")


if __name__ == "__main__":
    unittest.main()
