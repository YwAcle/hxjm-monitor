"""第二天上午 Agent 决策解析和有限步执行测试。"""

import base64
import unittest
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from llm_agent_service.agent.executor import AgentExecutor
from llm_agent_service.agent.prompts import extract_action
from llm_agent_service.agent.schemas import agent_decision_response_format
from llm_agent_service.tools import ToolRegistry, ToolSpec
from llm_agent_service.service.image_assets import SessionImageAssets
from llm_agent_service.service.memory import SessionMemoryStore

from pydantic import BaseModel


class EmptyArgs(BaseModel):
    pass


class FakeLLM:
    def __init__(self, responses):
        self.responses = iter(responses)

    def invoke(self, messages, **kwargs):
        self.last_messages = messages
        self.last_kwargs = kwargs
        self.calls = getattr(self, "calls", []) + [kwargs]
        return SimpleNamespace(content=next(self.responses))


class FailingLLM:
    def invoke(self, messages, **kwargs):
        raise RuntimeError("模型连接失败")


class AgentExecutorTests(unittest.TestCase):
    def test_decision_and_repair_calls_use_json_schema(self) -> None:
        llm = FakeLLM(["not JSON", '{"action":"final","answer":"完成"}'])
        result = AgentExecutor(llm=llm, registry=ToolRegistry()).run("你是谁")
        self.assertEqual(result.answer, "完成")
        self.assertEqual(len(llm.calls), 2)
        for kwargs in llm.calls:
            self.assertEqual(kwargs["response_format"], agent_decision_response_format())
            self.assertEqual(kwargs["max_new_tokens"], 2048)

    def test_tool_logs_include_full_results_and_arguments(self) -> None:
        data = {"items": [{"description": "result" * 3000}], "count": 1}
        registry = ToolRegistry()
        registry.register(ToolSpec("demo", "测试", EmptyArgs, lambda args: data))
        with self.assertLogs("llm_agent_service.events", level="INFO") as captured:
            AgentExecutor(llm=FakeLLM([
                '{"action":"tool","tool_name":"demo","arguments":{"limit":5}}',
                '{"action":"final","answer":"完成"}',
            ]), registry=registry, max_tool_result_chars=100).run(
                "完整用户输入", trace_id="trace-log", session_id="session-log",
            )
        records = [json.loads(record.getMessage()) for record in captured.records]
        start = next(record for record in records if record["event"] == "tool_start")
        end = next(record for record in records if record["event"] == "tool_end")
        self.assertEqual(start["arguments"], {"limit": 5})
        self.assertEqual(end["result"]["data"], data)
        self.assertEqual(end["trace_id"], "trace-log")
        self.assertEqual(end["session_id"], "session-log")

    def test_direct_super_resolution_logs_result_without_image_data(self) -> None:
        encoded = "data:image/png;base64,ABC123"
        registry = ToolRegistry()
        data = {"text": "done", "data": {"image": encoded, "image_base64": "RAWBASE64"}}
        registry.register(ToolSpec("super_resolve_image", "测试", EmptyArgs, lambda args: data))
        with self.assertLogs("llm_agent_service.events", level="INFO") as captured:
            AgentExecutor(llm=FakeLLM([]), registry=registry).run(
                "请超分图片", image_base64=encoded,
            )
        records = [json.loads(record.getMessage()) for record in captured.records]
        end = next(record for record in records if record["event"] == "tool_end")
        self.assertEqual(end["result"]["data"]["text"], "done")
        self.assertNotIn(encoded, "\n".join(captured.output))
        self.assertNotIn("RAWBASE64", "\n".join(captured.output))

    def test_extracts_plain_and_fenced_json(self) -> None:
        self.assertEqual(extract_action('{"action":"final","answer":"完成"}').answer, "完成")
        action = extract_action('```json\n{"action":"tool","tool_name":"demo","arguments":{"limit":5}}\n```')
        self.assertEqual(action.arguments["limit"], 5)

    def test_extracts_super_resolution_when_model_base64_is_truncated(self) -> None:
        action = extract_action(
            '{"action":"tool","tool_name":"super_resolve_image",'
            '"arguments":{"image_base64":"data:image/png;base64,AAAA'
        )
        self.assertEqual(action.tool_name, "super_resolve_image")
        self.assertEqual(action.arguments["prompt"], "请将图片超分2倍")

    def test_tool_then_final(self) -> None:
        registry = ToolRegistry()
        registry.register(ToolSpec("demo", "测试", EmptyArgs, lambda args: {"value": 1}))
        result = AgentExecutor(
            llm=FakeLLM([
                '{"action":"tool","tool_name":"demo","arguments":{}}',
                '{"action":"final","answer":"查询完成"}',
            ]),
            registry=registry,
        ).run("请查询")
        self.assertEqual(result.answer, "查询完成")
        self.assertEqual(result.finish_reason, "final")
        self.assertEqual(len(result.steps), 2)

    def test_decision_reason_is_not_returned_in_result(self) -> None:
        registry = ToolRegistry()
        result = AgentExecutor(
            llm=FakeLLM([
                '{"action":"final","answer":"完成","decision_reason":"已有足够信息"}'
            ]),
            registry=registry,
        ).run("你好")
        self.assertNotIn("decision_reason", result.model_dump_json())

    def test_stops_at_max_steps(self) -> None:
        registry = ToolRegistry()
        registry.register(ToolSpec("demo", "测试", EmptyArgs, lambda args: {"value": 1}))
        result = AgentExecutor(
            # 使用不同参数，避免先命中重复调用保护，从而专门测试 max_steps。
            llm=FakeLLM([
                '{"action":"tool","tool_name":"demo","arguments":{"round":1}}',
                '{"action":"tool","tool_name":"demo","arguments":{"round":2}}',
            ]),
            registry=registry,
            max_steps=2,
        ).run("请查询")
        self.assertEqual(result.finish_reason, "max_steps")
        self.assertEqual(len(result.steps), 2)

    def test_invalid_model_output_returns_error(self) -> None:
        registry = ToolRegistry()
        result = AgentExecutor(llm=FakeLLM(["不是 JSON", "仍然不是 JSON"]), registry=registry).run("请查询")
        self.assertEqual(result.finish_reason, "error")

    def test_invalid_output_is_retried_once(self) -> None:
        registry = ToolRegistry()
        result = AgentExecutor(
            llm=FakeLLM(["说明文字", '{"action":"final","answer":"修复后完成"}']),
            registry=registry,
        ).run("请查询")
        self.assertEqual(result.answer, "修复后完成")
        self.assertEqual(result.finish_reason, "final")

    def test_streams_only_the_confirmed_final_answer(self) -> None:
        llm = MagicMock()
        llm.stream.return_value = iter([SimpleNamespace(content="当前已登记人员共 3 人：")])
        executor = AgentExecutor(llm=llm, registry=ToolRegistry())

        answer = "当前已登记人员共 3 人：谭梓豪、王新龙、任路阳。"
        output = "".join(executor.stream_final_answer(answer))

        self.assertEqual(output, answer)
        llm.stream.assert_not_called()
        llm.invoke.assert_not_called()

    def test_stream_does_not_require_a_streaming_model(self) -> None:
        output = "".join(
            AgentExecutor(llm=object(), registry=ToolRegistry()).stream_final_answer("查询完成。")
        )
        self.assertEqual(output, "查询完成。")

    def test_stream_preserves_long_answer_and_whitespace(self) -> None:
        answer = "  查询结果：\n" + "监控事件及证据。\n" * 30 + "\n "
        chunks = list(
            AgentExecutor(llm=object(), registry=ToolRegistry()).stream_final_answer(answer)
        )
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(0 < len(chunk) <= 64 for chunk in chunks))
        self.assertEqual("".join(chunks), answer)

    def test_stream_empty_answer_emits_no_chunks(self) -> None:
        executor = AgentExecutor(llm=object(), registry=ToolRegistry())
        self.assertEqual(list(executor.stream_final_answer("")), [])

    def test_repeated_tool_call_is_stopped(self) -> None:
        registry = ToolRegistry()
        registry.register(ToolSpec("demo", "测试", EmptyArgs, lambda args: {"value": 1}))
        result = AgentExecutor(
            llm=FakeLLM(['{"action":"tool","tool_name":"demo","arguments":{}}'] * 2),
            registry=registry,
        ).run("请查询")
        self.assertEqual(result.finish_reason, "error")
        self.assertEqual(len(result.steps), 1)

    def test_image_only_request_inherits_previous_super_resolution_intent(self) -> None:
        registry = ToolRegistry()
        registry.register(ToolSpec("super_resolve_image", "超分", EmptyArgs, lambda args: {
            "type": "super_resolution", "text": "图片超分完成。", "data": {"status": "success"}
        }))
        memory = SessionMemoryStore(max_sessions=2, max_messages=4)
        with memory.conversation("s") as conversation:
            conversation.add_exchange("帮我超分", "好的，请上传图片")
        result = AgentExecutor(llm=FakeLLM([]), registry=registry, memory=memory).run(
            "", session_id="s", image_base64="data:image/png;base64,test"
        )
        self.assertEqual(result.finish_reason, "final")
        self.assertEqual(result.data["data"]["status"], "success")

    def test_successful_super_resolution_is_terminal(self) -> None:
        registry = ToolRegistry()
        registry.register(ToolSpec("super_resolve_image", "超分", EmptyArgs, lambda args: {
            "type": "super_resolution", "text": "图片超分完成。", "data": {"status": "success"}
        }))
        result = AgentExecutor(
            llm=FakeLLM(['{"action":"tool","tool_name":"super_resolve_image","arguments":{}}']),
            registry=registry,
        ).run("请超分")
        self.assertEqual(result.finish_reason, "final")
        self.assertEqual(result.data["data"]["status"], "success")

    def test_pending_super_resolution_with_image_skips_image_description(self) -> None:
        registry = ToolRegistry()
        registry.register(ToolSpec("super_resolve_image", "超分", EmptyArgs, lambda args: {
            "type": "super_resolution", "text": "图片超分完成。", "data": {"status": "success"}
        }))
        memory = SessionMemoryStore(max_sessions=2, max_messages=4)
        with memory.conversation("s") as conversation:
            conversation.add_exchange("帮我超分", "好的，请上传图片")
        llm = FakeLLM(["不应调用模型"])
        result = AgentExecutor(llm=llm, registry=registry, memory=memory).run(
            "请结合当前会话上下文处理这张图片", session_id="s", image_base64="data:image/png;base64,test"
        )
        self.assertEqual(result.finish_reason, "final")
        self.assertEqual(result.data["data"]["status"], "success")

    def test_two_turn_super_resolution_keeps_first_turn_in_memory(self) -> None:
        class SuperArgs(BaseModel):
            image_base64: str = ""
            prompt: str = ""

        registry = ToolRegistry()
        registry.register(ToolSpec("super_resolve_image", "超分", SuperArgs, lambda args: {
            "type": "super_resolution",
            "text": "图片超分完成。" if args.image_base64 else "请上传需要超分的图片。",
            "data": {"status": "success" if args.image_base64 else "missing_image"},
        }))
        memory = SessionMemoryStore(max_sessions=2, max_messages=6)
        executor = AgentExecutor(
            llm=FakeLLM(['{"action":"tool","tool_name":"super_resolve_image","arguments":{}}']),
            registry=registry,
            memory=memory,
        )
        first = executor.run("帮我超分", session_id="s")
        second = executor.run("", session_id="s", image_base64="data:image/png;base64,test")
        self.assertEqual(first.data["data"]["status"], "missing_image")
        self.assertEqual(second.data["data"]["status"], "success")

    def test_trace_id_is_attached_to_agent_events(self) -> None:
        registry = ToolRegistry()
        with patch("llm_agent_service.agent.executor.emit_event") as emit_event:
            result = AgentExecutor(
                llm=FakeLLM(['{"action":"final","answer":"完成"}']),
                registry=registry,
            ).run("你好", session_id="session-1", trace_id="trace-1")

        self.assertEqual(result.finish_reason, "final")
        self.assertTrue(emit_event.called)
        self.assertTrue(
            all(
                call.kwargs.get("trace_id") == "trace-1"
                for call in emit_event.call_args_list
            )
        )

    def test_llm_failure_emits_agent_end(self) -> None:
        with patch("llm_agent_service.agent.executor.emit_event") as emit_event:
            with self.assertRaises(RuntimeError):
                AgentExecutor(llm=FailingLLM(), registry=ToolRegistry()).run(
                    "你好",
                    session_id="session-1",
                    trace_id="trace-1",
                )

        agent_end = [
            call for call in emit_event.call_args_list if call.args[0] == "agent_end"
        ]
        self.assertEqual(len(agent_end), 1)
        self.assertEqual(agent_end[0].kwargs["error_code"], "LLM_CALL_ERROR")


def encoded_image(fill: bytes = b"a") -> str:
    return "data:image/png;base64," + base64.b64encode(fill).decode("ascii")


class SessionImageAssetExecutorTests(unittest.TestCase):
    def test_previous_image_is_reattached_when_referenced(self) -> None:
        store = SessionImageAssets()
        image = encoded_image(b"first")
        llm = FakeLLM([
            '{"action":"final","answer":"收到图片"}',
            '{"action":"final","answer":"是一件红色上衣"}',
        ])
        executor = AgentExecutor(llm=llm, registry=ToolRegistry(), image_assets=store)

        executor.run("描述这张图", session_id="s", image_base64=image)
        result = executor.run("刚才那张图里是什么颜色", session_id="s")

        self.assertEqual(result.answer, "是一件红色上衣")
        content = llm.last_messages[-1].content
        self.assertIsInstance(content, list)
        self.assertEqual(content[0]["text"], "刚才那张图里是什么颜色")
        self.assertEqual(content[1]["image_url"]["url"], image)

    def test_short_image_phrase_reattaches_image(self) -> None:
        store = SessionImageAssets()
        image = encoded_image(b"first")
        llm = FakeLLM([
            '{"action":"final","answer":"收到图片"}',
            '{"action":"final","answer":"图中有三名女性"}',
        ])
        executor = AgentExecutor(llm=llm, registry=ToolRegistry(), image_assets=store)

        executor.run("先记住这张图，不要描述", session_id="s", image_base64=image)
        result = executor.run("图里有几个女生", session_id="s")

        self.assertEqual(result.answer, "图中有三名女性")
        self.assertEqual(llm.last_messages[-1].content[1]["image_url"]["url"], image)

    def test_context_exposes_image_used_for_this_turn(self) -> None:
        store = SessionImageAssets()
        image = encoded_image(b"first")
        llm = FakeLLM([
            '{"action":"final","answer":"收到图片"}',
            '{"action":"final","answer":"图中有一人"}',
        ])
        executor = AgentExecutor(llm=llm, registry=ToolRegistry(), image_assets=store)

        uploaded: dict[str, object] = {}
        executor.run("先记住这张图", session_id="s", image_base64=image, context=uploaded)
        recalled: dict[str, object] = {}
        executor.run("刚才那张图里有几个人", session_id="s", context=recalled)

        self.assertEqual(uploaded["effective_image"], image)
        self.assertEqual(recalled["effective_image"], image)

    def test_prompt_without_reference_does_not_attach_image(self) -> None:
        store = SessionImageAssets()
        store.put("s", encoded_image())
        llm = FakeLLM(['{"action":"final","answer":"你好"}'])
        executor = AgentExecutor(llm=llm, registry=ToolRegistry(), image_assets=store)

        executor.run("你好", session_id="s")

        self.assertEqual(llm.last_messages[-1].content, "你好")

    def test_new_upload_takes_precedence_over_stored_image(self) -> None:
        store = SessionImageAssets()
        store.put("s", encoded_image(b"old"))
        image = encoded_image(b"new")
        llm = FakeLLM(['{"action":"final","answer":"完成"}'])
        executor = AgentExecutor(llm=llm, registry=ToolRegistry(), image_assets=store)

        executor.run("刚才那张图换成新的了", session_id="s", image_base64=image)

        self.assertEqual(llm.last_messages[-1].content[1]["image_url"]["url"], image)
        self.assertEqual(store.latest("s").data_url, image)

    def test_explicit_ordinal_selects_older_asset(self) -> None:
        store = SessionImageAssets()
        first = encoded_image(b"first")
        llm = FakeLLM([
            '{"action":"final","answer":"一"}',
            '{"action":"final","answer":"二"}',
            '{"action":"final","answer":"三"}',
        ])
        executor = AgentExecutor(llm=llm, registry=ToolRegistry(), image_assets=store)

        executor.run("描述这张图", session_id="s", image_base64=first)
        executor.run("再看这张图", session_id="s", image_base64=encoded_image(b"second"))
        executor.run("第一张图里有什么", session_id="s")

        self.assertEqual(llm.last_messages[-1].content[1]["image_url"]["url"], first)

    def test_missing_asset_adds_explicit_note_instead_of_image(self) -> None:
        store = SessionImageAssets()
        llm = FakeLLM(['{"action":"final","answer":"请重新上传"}'])
        executor = AgentExecutor(llm=llm, registry=ToolRegistry(), image_assets=store)

        executor.run("刚才那张图里有什么", session_id="s")

        content = llm.last_messages[-1].content
        self.assertIsInstance(content, str)
        self.assertIn("已过期", content)
        self.assertIn("重新上传", content)

    def test_recalled_image_is_injected_into_image_tool(self) -> None:
        class ImageArgs(BaseModel):
            image_base64: str = ""

        captured = {}

        def handler(args):
            captured["image"] = args.image_base64
            return {"type": "pedestrian_search", "status": "ok", "count": 0, "candidates": []}

        registry = ToolRegistry()
        registry.register(ToolSpec("search_pedestrians_by_image", "测试", ImageArgs, handler))
        store = SessionImageAssets()
        image = encoded_image(b"person")
        llm = FakeLLM([
            '{"action":"final","answer":"收到"}',
            '{"action":"tool","tool_name":"search_pedestrians_by_image",'
            '"arguments":{"image_base64":"data:image/png;base64,FORGED"}}',
            '{"action":"final","answer":"已检索"}',
        ])
        executor = AgentExecutor(llm=llm, registry=registry, image_assets=store)

        executor.run("描述这张图", session_id="s", image_base64=image)
        result = executor.run("用刚才那张图找相似的人", session_id="s")

        self.assertEqual(captured["image"], image)
        self.assertEqual(result.answer, "已检索")

    def test_recalled_image_is_used_for_super_resolution(self) -> None:
        class SuperArgs(BaseModel):
            image_base64: str = ""
            prompt: str = ""

        captured = {}
        registry = ToolRegistry()
        registry.register(ToolSpec("super_resolve_image", "超分", SuperArgs, lambda args: (
            captured.update({"image": args.image_base64}) or {
                "type": "super_resolution", "text": "图片超分完成。",
                "data": {"status": "success"},
            }
        )))
        store = SessionImageAssets()
        image = encoded_image(b"person")
        llm = FakeLLM(['{"action":"final","answer":"收到"}'])
        executor = AgentExecutor(llm=llm, registry=registry, image_assets=store)

        executor.run("描述这张图", session_id="s", image_base64=image)
        result = executor.run("请把刚才那张图超分", session_id="s")

        self.assertEqual(captured["image"], image)
        self.assertEqual(result.data["data"]["status"], "success")

    def test_asset_events_do_not_include_image_data(self) -> None:
        image = encoded_image(b"person")
        with self.assertLogs("llm_agent_service.events", level="INFO") as captured:
            AgentExecutor(
                llm=FakeLLM(['{"action":"final","answer":"已收到"}']),
                registry=ToolRegistry(),
                image_assets=SessionImageAssets(),
            ).run("描述这张图", session_id="s", image_base64=image)

        self.assertNotIn("base64", "\n".join(captured.output))
        events = [json.loads(record.getMessage()) for record in captured.records]
        stored = next(event for event in events if event["event"] == "image_asset_stored")
        self.assertEqual(stored["session_id"], "s")
        self.assertNotIn("data_url", stored)

    def test_image_only_request_inherits_previous_search_intent(self) -> None:
        class ImageArgs(BaseModel):
            image_base64: str = ""

        captured = {}

        def handler(args):
            captured["image"] = args.image_base64
            return {"type": "pedestrian_search", "status": "ok", "count": 0, "candidates": []}

        registry = ToolRegistry()
        registry.register(ToolSpec("search_pedestrians_by_image", "测试", ImageArgs, handler))
        memory = SessionMemoryStore(max_sessions=2, max_messages=6)
        with memory.conversation("s") as conversation:
            conversation.add_exchange("帮我找图里的人", "请上传需要查找的图片")
        image = encoded_image(b"person")
        llm = FakeLLM([
            '{"action":"tool","tool_name":"search_pedestrians_by_image","arguments":{}}',
            '{"action":"final","answer":"已检索"}',
        ])
        executor = AgentExecutor(
            llm=llm, registry=registry, memory=memory, image_assets=SessionImageAssets()
        )

        result = executor.run("", session_id="s", image_base64=image)

        self.assertEqual(captured["image"], image)
        self.assertEqual(result.answer, "已检索")

    def test_default_image_prompt_inherits_intent_after_upload_request(self) -> None:
        class ImageArgs(BaseModel):
            image_base64: str = ""

        captured = {}
        registry = ToolRegistry()
        registry.register(ToolSpec("search_pedestrians_by_image", "测试", ImageArgs,
                                   lambda args: (captured.update({"image": args.image_base64})
                                                 or {"status": "ok", "count": 0, "candidates": []})))
        memory = SessionMemoryStore(max_sessions=2, max_messages=6)
        with memory.conversation("s") as conversation:
            conversation.add_exchange("找这张图里的人", "抱歉，请重新上传需要查找的图片。")
        image = encoded_image(b"person")
        llm = FakeLLM([
            '{"action":"tool","tool_name":"search_pedestrians_by_image","arguments":{}}',
            '{"action":"final","answer":"已检索"}',
        ])
        executor = AgentExecutor(
            llm=llm, registry=registry, memory=memory, image_assets=SessionImageAssets()
        )

        result = executor.run("请描述这张图片的内容。", session_id="s", image_base64=image)

        self.assertEqual(captured["image"], image)
        self.assertEqual(result.answer, "已检索")

    def test_default_image_prompt_stays_description_without_upload_request(self) -> None:
        memory = SessionMemoryStore(max_sessions=2, max_messages=6)
        with memory.conversation("s") as conversation:
            conversation.add_exchange("你好", "你好，有什么可以帮助你的？")
        llm = FakeLLM(['{"action":"final","answer":"图片中有一名行人"}'])
        executor = AgentExecutor(
            llm=llm, registry=ToolRegistry(), memory=memory, image_assets=SessionImageAssets()
        )

        executor.run("请描述这张图片的内容。", session_id="s", image_base64=encoded_image())

        self.assertEqual(llm.last_messages[-1].content[0]["text"], "请描述这张图片的内容。")

    def test_image_only_request_without_history_keeps_empty_prompt(self) -> None:
        llm = FakeLLM(['{"action":"final","answer":"图片中有一名行人"}'])
        executor = AgentExecutor(llm=llm, registry=ToolRegistry(), image_assets=SessionImageAssets())

        executor.run("", session_id="s", image_base64=encoded_image())

        self.assertEqual(len(llm.last_messages[-1].content), 1)
        self.assertIn("image_url", llm.last_messages[-1].content[0])

    def test_chat_history_never_contains_image_data(self) -> None:
        memory = SessionMemoryStore(max_sessions=2, max_messages=4)
        image = encoded_image(b"person")
        executor = AgentExecutor(
            llm=FakeLLM(['{"action":"final","answer":"图中有一名行人"}']),
            registry=ToolRegistry(),
            memory=memory,
            image_assets=SessionImageAssets(),
        )

        executor.run("描述这张图", session_id="s", image_base64=image)

        with memory.conversation("s") as conversation:
            history = conversation.messages()
        self.assertEqual([message.content for message in history],
                         ["描述这张图", "图中有一名行人"])
        self.assertNotIn(image, "\n".join(str(message.content) for message in history))


if __name__ == "__main__":
    unittest.main()
