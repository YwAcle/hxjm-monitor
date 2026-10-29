"""Agent SSE 流式输出测试。"""

from __future__ import annotations

import unittest
import json
import base64
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from llm_agent_service.app import create_app
from llm_agent_service.config import DbConfig, ServiceConfig
from llm_agent_service.service.agent_service import AgentService
from llm_agent_service.service.memory import SessionMemoryStore
from llm_agent_service.agent.executor import AgentExecutor
from llm_agent_service.tools import ToolRegistry, ToolSpec
from pydantic import BaseModel
from PIL import Image


class AgentStreamTests(unittest.TestCase):
    def test_current_time_reaches_decision_and_stream_generation(self) -> None:
        from datetime import datetime, timedelta, timezone

        llm = MagicMock()
        llm.invoke.return_value = SimpleNamespace(content='{"action":"final","answer":"准备回答"}')
        llm.stream.return_value = iter([SimpleNamespace(content="现在是2026年10月08日 13时30分15秒。")])
        executor = AgentExecutor(llm=llm, registry=ToolRegistry())
        now = datetime(2026, 10, 8, 13, 30, 15, tzinfo=timezone(timedelta(hours=8)))
        with patch("llm_agent_service.agent.prompts.datetime") as clock:
            clock.now.return_value = now
            list(executor.stream_run("现在是什么时间", session_id="current-time"))

        for messages in (llm.invoke.call_args.args[0], llm.stream.call_args.args[0]):
            self.assertEqual(sum(message.type == "system" for message in messages), 1)
            self.assertIn("当前时间：2026年10月08日 13时30分15秒", messages[0].content)
            self.assertIn("北京时间，Asia/Shanghai", messages[0].content)
            self.assertIn("历史消息中的日期时间只代表历史信息", messages[0].content)

    def test_stream_logs_and_memory_match_confirmed_answer(self) -> None:
        answer = "当前已登记人员共 3 人：谭梓豪、王新龙、任路阳。"
        llm = MagicMock()
        llm.invoke.return_value = SimpleNamespace(
            content=json.dumps({"action": "final", "answer": "准备回答"}, ensure_ascii=False)
        )
        llm.stream.return_value = iter([
            SimpleNamespace(content=answer[:13]), SimpleNamespace(content=answer[13:]),
        ])
        service = MagicMock()
        service.memory = SessionMemoryStore()
        with patch("llm_agent_service.app.ReidService", return_value=service):
            app = create_app(
                engine=MagicMock(),
                db_cfg=DbConfig("localhost", 5432, "user", "password", "db"),
                svc_cfg=ServiceConfig(),
                llm=llm,
            )

        with self.assertLogs("llm_agent_service.events", level="INFO") as captured:
            response = app.test_client().post(
                "/chat/stream", json={"prompt": "是谁", "session_id": "stream-consistency"}
            )
            body = response.get_data(as_text=True)

        records = [json.loads(record.getMessage()) for record in captured.records]
        agent_end = next(record for record in records if record["event"] == "agent_end")
        request_end = next(record for record in records if record["event"] == "request_end")
        events = [
            json.loads(line.removeprefix("data: "))
            for block in body.split("\n\n")
            if block.startswith("event: delta\n")
            for line in block.splitlines()
            if line.startswith("data: ")
        ]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(agent_end["answer"], answer)
        self.assertEqual(request_end["response_text"], answer)
        self.assertEqual(request_end["response_chars"], len(answer))
        self.assertEqual(request_end["status"], "success")
        self.assertEqual("".join(event["text"] for event in events), answer)
        with service.memory.conversation("stream-consistency") as conversation:
            self.assertEqual(conversation.messages()[-1].content, answer)
        llm.invoke.assert_called_once()
        llm.stream.assert_called_once()
        self.assertIn("是谁", str(llm.stream.call_args.args[0]))
        self.assertNotIn("准备回答", str(llm.stream.call_args.args[0]))
        schema = llm.invoke.call_args.kwargs["response_format"]["json_schema"]["schema"]
        self.assertEqual(schema["$defs"]["AgentFinalAction"]["properties"]["answer"]["const"], "准备回答")
        self.assertEqual(sum(message.type == "system" for message in llm.invoke.call_args.args[0]), 1)

    def test_service_only_streams_final_answer(self) -> None:
        executor = MagicMock()
        executor.stream_run.return_value = iter([
            {"event": "status", "data": {"stage": "generating"}},
            {"event": "delta", "data": {"text": "火灾发生在"}},
            {"event": "delta", "data": {"text": " camera_4。"}},
            {"event": "done", "data": {"session_id": "s-1", "finish_reason": "final", "steps": 2}},
        ])

        events = list(AgentService(executor=executor).stream("查询最近异常", session_id="s-1"))

        self.assertEqual([item["event"] for item in events], ["status", "status", "delta", "delta", "done"])
        self.assertEqual(
            "".join(item["data"].get("text", "") for item in events),
            "火灾发生在 camera_4。",
        )
        self.assertEqual(events[-1]["data"]["finish_reason"], "final")
        executor.stream_run.assert_called_once_with(
            "查询最近异常", session_id="s-1", image_base64=None, trace_id=None, context={}
        )
        executor.stream_final_answer.assert_not_called()

    def test_stream_emits_tokens_before_completion_and_uses_tool_evidence(self) -> None:
        class EmptyArgs(BaseModel):
            pass

        registry = ToolRegistry()
        registry.register(ToolSpec("demo", "查询事件", EmptyArgs, lambda args: {"camera": "camera_4"}))
        llm = MagicMock()
        llm.invoke.side_effect = [
            SimpleNamespace(content='{"action":"tool","tool_name":"demo","arguments":{}}'),
            SimpleNamespace(content='{"action":"final","answer":"准备回答"}'),
        ]
        llm.stream.return_value = iter([
            SimpleNamespace(content="事件发生在"), SimpleNamespace(content=" camera_4。"),
        ])
        memory = SessionMemoryStore()
        executor = AgentExecutor(llm=llm, registry=registry, memory=memory)
        with self.assertLogs("llm_agent_service.events", level="INFO") as captured:
            stream = executor.stream_run("查事件", session_id="tokens")
            self.assertEqual(next(stream)["event"], "status")
            self.assertEqual(next(stream)["data"]["text"], "事件发生在")
            with memory.conversation("tokens") as conversation:
                self.assertEqual(conversation.messages(), [])
            self.assertFalse(any(json.loads(record.getMessage())["event"] == "agent_end" for record in captured.records))
            events = list(stream)
        self.assertEqual(events[-1]["event"], "done")
        self.assertIn("camera_4", str(llm.stream.call_args.args[0]))
        with memory.conversation("tokens") as conversation:
            self.assertEqual(conversation.messages()[-1].content, "事件发生在 camera_4。")

    def test_truncated_sse_finishes_with_done_instead_of_internal_error(self) -> None:
        llm = MagicMock()
        llm.invoke.return_value = SimpleNamespace(content='{"action":"final","answer":"准备回答"}')
        llm.stream.return_value = iter([
            SimpleNamespace(content="部分回答", response_metadata={"finish_reason": "length"}),
        ])
        service = MagicMock()
        service.memory = SessionMemoryStore()
        with patch("llm_agent_service.app.ReidService", return_value=service):
            app = create_app(engine=MagicMock(), db_cfg=DbConfig("localhost", 5432, "user", "password", "db"),
                             svc_cfg=ServiceConfig(agent_answer_max_new_tokens=1234), llm=llm)
        with self.assertLogs("llm_agent_service.events", level="INFO") as captured:
            response = app.test_client().post("/chat/stream", json={"prompt": "你好", "session_id": "truncated"})
            body = response.get_data(as_text=True)

        self.assertEqual(llm.stream.call_args.kwargs["max_new_tokens"], 1234)
        self.assertIn("event: done", body)
        self.assertNotIn("event: error", body)
        done = json.loads(next(
            line.removeprefix("data: ")
            for block in body.split("\n\n")
            if block.startswith("event: done\n")
            for line in block.splitlines()
            if line.startswith("data: ")
        ))
        self.assertEqual(done["finish_reason"], "length")
        self.assertTrue(done["truncated"])
        records = [json.loads(record.getMessage()) for record in captured.records]
        request_end = next(record for record in records if record["event"] == "request_end")
        self.assertEqual(request_end["status"], "success")
        self.assertEqual(request_end["finish_reason"], "length")
        with service.memory.conversation("truncated") as conversation:
            self.assertEqual(conversation.messages(), [])

    def test_failed_stream_preserves_partial_logs_without_saving_history(self) -> None:
        def broken_stream(messages, **kwargs):
            yield SimpleNamespace(content="部分回答")
            raise RuntimeError("连接中断")

        llm = MagicMock()
        llm.invoke.return_value = SimpleNamespace(content='{"action":"final","answer":"准备回答"}')
        llm.stream.side_effect = broken_stream
        service = MagicMock()
        service.memory = SessionMemoryStore()
        with patch("llm_agent_service.app.ReidService", return_value=service):
            app = create_app(engine=MagicMock(), db_cfg=DbConfig("localhost", 5432, "user", "password", "db"),
                             svc_cfg=ServiceConfig(), llm=llm)
        with self.assertLogs("llm_agent_service.events", level="INFO") as captured:
            response = app.test_client().post("/chat/stream", json={"prompt": "你好", "session_id": "broken"})
            body = response.get_data(as_text=True)
        records = [json.loads(record.getMessage()) for record in captured.records]
        agent_end = next(record for record in records if record["event"] == "agent_end")
        request_end = next(record for record in records if record["event"] == "request_end")
        self.assertEqual(agent_end["answer"], "部分回答")
        self.assertEqual(request_end["response_text"], "部分回答")
        self.assertEqual(agent_end["finish_reason"], "error")
        self.assertEqual(request_end["status"], "error")
        self.assertIn("event: error", body)
        self.assertNotIn("event: done", body)
        with service.memory.conversation("broken") as conversation:
            self.assertEqual(conversation.messages(), [])

    def test_truncated_stream_returns_partial_answer_without_saving_history(self) -> None:
        llm = MagicMock()
        llm.invoke.return_value = SimpleNamespace(content='{"action":"final","answer":"准备回答"}')
        llm.stream.return_value = iter([
            SimpleNamespace(content="部分回答", response_metadata={"finish_reason": "length"}),
        ])
        memory = SessionMemoryStore()
        with self.assertLogs("llm_agent_service.events", level="INFO") as captured:
            events = list(AgentExecutor(
                llm=llm, registry=ToolRegistry(), memory=memory,
            ).stream_run("你好", session_id="length"))

        self.assertEqual(events[-1]["event"], "done")
        self.assertEqual(events[-1]["data"]["finish_reason"], "length")
        self.assertTrue(events[-1]["data"]["truncated"])
        text = "".join(item["data"].get("text", "") for item in events if item["event"] == "delta")
        self.assertIn("部分回答", text)
        self.assertIn("长度上限", text)
        self.assertEqual(llm.stream.call_args.kwargs["max_new_tokens"], 2048)
        record = json.loads(captured.records[-1].getMessage())
        self.assertEqual(record["event"], "agent_end")
        self.assertEqual(record["finish_reason"], "length")
        self.assertIsNone(record.get("error_code"))
        with memory.conversation("length") as conversation:
            self.assertEqual(conversation.messages(), [])

    def test_empty_and_cancelled_streams_do_not_save_history(self) -> None:
        for mode in ("empty", "cancel"):
            with self.subTest(mode=mode):
                llm = MagicMock()
                llm.invoke.return_value = SimpleNamespace(content='{"action":"final","answer":"准备回答"}')
                llm.stream.return_value = iter([] if mode == "empty" else [
                    SimpleNamespace(content="部分", response_metadata={"finish_reason": "stop"}),
                ])
                memory = SessionMemoryStore()
                stream = AgentExecutor(llm=llm, registry=ToolRegistry(), memory=memory).stream_run("你好", session_id=mode)
                with self.assertLogs("llm_agent_service.events", level="INFO") as captured:
                    next(stream)
                    if mode == "cancel":
                        next(stream)
                        stream.close()
                    else:
                        with self.assertRaises(RuntimeError):
                            list(stream)
                record = json.loads(captured.records[-1].getMessage())
                self.assertEqual(record["event"], "agent_end")
                self.assertEqual(record["finish_reason"], "error")
                with memory.conversation(mode) as conversation:
                    self.assertEqual(conversation.messages(), [])

    def test_client_close_logs_once_and_does_not_save_partial_answer(self) -> None:
        for stop_event in ("delta", "done"):
            with self.subTest(stop_event=stop_event):
                llm = MagicMock()
                llm.invoke.return_value = SimpleNamespace(content='{"action":"final","answer":"准备回答"}')
                llm.stream.return_value = iter([SimpleNamespace(content="你好"), SimpleNamespace(content="！")])
                service = MagicMock()
                service.memory = SessionMemoryStore()
                with patch("llm_agent_service.app.ReidService", return_value=service):
                    app = create_app(engine=MagicMock(), db_cfg=DbConfig("localhost", 5432, "user", "password", "db"),
                                     svc_cfg=ServiceConfig(), llm=llm)
                with self.assertLogs("llm_agent_service.events", level="INFO") as captured:
                    response = app.test_client().post("/chat/stream", json={"prompt": "你好", "session_id": "close"}, buffered=False)
                    for chunk in response.response:
                        if f"event: {stop_event}\n" in chunk.decode():
                            break
                    response.close()
                records = [json.loads(record.getMessage()) for record in captured.records]
                agent_ends = [record for record in records if record["event"] == "agent_end"]
                request_ends = [record for record in records if record["event"] == "request_end"]
                self.assertEqual(len(agent_ends), 1)
                self.assertEqual(len(request_ends), 1)
                self.assertEqual(agent_ends[0]["answer"], request_ends[0]["response_text"])
                self.assertEqual(request_ends[0]["status"], "error" if stop_event == "delta" else "success")
                with service.memory.conversation("close") as conversation:
                    self.assertEqual(len(conversation.messages()), 0 if stop_event == "delta" else 2)

    def test_terminal_image_tool_streams_its_result_without_model_generation(self) -> None:
        class EmptyArgs(BaseModel):
            pass

        registry = ToolRegistry()
        registry.register(ToolSpec("super_resolve_image", "超分", EmptyArgs, lambda args: {
            "text": "图片超分完成。", "type": "super_resolution",
        }))
        llm = MagicMock()
        memory = SessionMemoryStore()
        events = list(AgentExecutor(llm=llm, registry=registry, memory=memory).stream_run(
            "请超分", session_id="image", image_base64="data:image/png;base64,ABC",
        ))
        self.assertEqual("".join(event["data"].get("text", "") for event in events), "图片超分完成。")
        self.assertEqual(events[-1]["event"], "done")
        llm.invoke.assert_not_called()
        llm.stream.assert_not_called()

    def test_stream_endpoint_emits_only_public_events(self) -> None:
        agent_service = MagicMock()
        agent_service.stream.return_value = iter([
            {"event": "status", "data": {"stage": "processing"}},
            {"event": "status", "data": {"stage": "generating"}},
            {"event": "delta", "data": {"text": "最近一次异常是火灾，"}},
            {"event": "delta", "data": {"text": "发生在 camera_4。"}},
            {"event": "done", "data": {"session_id": "browser-1", "finish_reason": "final", "steps": 2}},
        ])
        service = MagicMock()
        db_cfg = DbConfig("localhost", 5432, "user", "password", "db")

        with patch("llm_agent_service.app.ReidService", return_value=service), patch(
            "llm_agent_service.app.AgentService", return_value=agent_service
        ):
            app = create_app(
                engine=MagicMock(),
                db_cfg=db_cfg,
                svc_cfg=ServiceConfig(),
                llm=MagicMock(),
            )

        response = app.test_client().post(
            "/chat/stream",
            json={"prompt": "最近一次异常", "session_id": "browser-1", "trace_id": "trace-1"},
        )
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content_type.startswith("text/event-stream"))
        self.assertEqual(response.headers["X-Trace-ID"], "trace-1")
        self.assertIn("event: delta", body)
        self.assertIn("最近一次异常是火灾", body)
        self.assertNotIn("tool_name", body)
        self.assertNotIn("decision_reason", body)
        agent_service.stream.assert_called_once_with(
            "最近一次异常",
            image_base64=None,
            session_id="browser-1",
            trace_id="trace-1",
        )


class AgentImageUploadStreamTests(unittest.TestCase):
    @staticmethod
    def _image_bytes(*, image_format: str = "PNG", size: tuple[int, int] = (24, 16)) -> bytes:
        output = BytesIO()
        Image.new("RGB", size, (30, 60, 90)).save(output, format=image_format)
        return output.getvalue()

    def _client(self, config: ServiceConfig | None = None):
        service = MagicMock()
        service.stream.return_value = iter([
            {"event": "status", "data": {"stage": "processing"}},
            {"event": "status", "data": {"stage": "generating"}},
            {"event": "delta", "data": {"text": "图片内容"}},
            {"event": "delta", "data": {"text": "描述。"}},
            {"event": "done", "data": {"session_id": "image-session", "finish_reason": "final", "steps": 1}},
        ])
        with patch("llm_agent_service.app.ReidService"), patch(
            "llm_agent_service.app.AgentService", return_value=service,
        ):
            app = create_app(
                engine=MagicMock(), db_cfg=DbConfig("localhost", 5432, "user", "password", "db"),
                svc_cfg=config or ServiceConfig(), llm=MagicMock(),
            )
        return app.test_client(), service

    def test_multipart_image_streams_before_completion_and_logs_metadata(self) -> None:
        client, service = self._client()
        image = self._image_bytes()
        with self.assertLogs("llm_agent_service.events", level="INFO") as captured:
            response = client.post("/chat/stream", data={
                "prompt": "描述图片", "session_id": "image-session", "trace_id": "image-trace",
                "file": (BytesIO(image), "image.png"),
            }, headers={"X-Session-ID": "header-session", "X-Trace-ID": "header-trace"}, buffered=False)
            blocks = iter(response.response)
            self.assertIn(b"event: status", next(blocks))
            self.assertIn(b"event: status", next(blocks))
            self.assertIn("图片内容", next(blocks).decode())
            records = [json.loads(record.getMessage()) for record in captured.records]
            self.assertFalse(any(record["event"] == "request_end" for record in records))
            remaining = b"".join(blocks).decode()
            response.close()
        self.assertIn("描述。", remaining)
        self.assertIn("event: done", remaining)
        self.assertTrue(response.content_type.startswith("text/event-stream"))
        self.assertEqual(response.headers["X-Trace-ID"], "image-trace")
        self.assertEqual(response.headers["X-Accel-Buffering"], "no")
        service.stream.assert_called_once_with(
            "描述图片", session_id="image-session", trace_id="image-trace",
            image_base64="data:image/png;base64," + base64.b64encode(image).decode("ascii"),
        )
        records = [json.loads(record.getMessage()) for record in captured.records]
        start = next(record for record in records if record["event"] == "request_start")
        self.assertEqual(start["content_type"], "multipart/form-data")
        self.assertTrue(start["has_image"])
        self.assertEqual(start["image_bytes"], len(image))
        self.assertEqual((start["image_width"], start["image_height"]), (24, 16))
        self.assertEqual(records[-1]["response_text"], "图片内容描述。")
        self.assertNotIn(base64.b64encode(image).decode("ascii"), str(records))

    def test_json_and_form_images_use_identical_normalization(self) -> None:
        for image_format, media_type in (("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")):
            image = self._image_bytes(image_format=image_format)
            encoded = base64.b64encode(image).decode("ascii")
            for mode in ("json", "file", "image", "image_base64", "base64"):
                with self.subTest(image_format=image_format, mode=mode):
                    client, service = self._client()
                    if mode == "json":
                        response = client.post("/chat/stream", json={"image": encoded})
                    else:
                        data = {"file": (BytesIO(image), "image.dat")} if mode == "file" else {mode: encoded}
                        response = client.post("/chat/stream", data=data, content_type="multipart/form-data")
                    response.get_data()
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(service.stream.call_args.args[0], "")
                    self.assertEqual(service.stream.call_args.kwargs["image_base64"], f"data:{media_type};base64,{encoded}")

    def test_multipart_validation_rejects_before_starting_stream(self) -> None:
        cases = [
            ({"file": (BytesIO(b""), "empty.png")}, ServiceConfig(), 400, "INVALID_IMAGE"),
            ({"file": (BytesIO(b"not an image"), "bad.png")}, ServiceConfig(), 400, "INVALID_IMAGE"),
            ({"file": (BytesIO(self._image_bytes(image_format="BMP")), "bad.bmp")}, ServiceConfig(), 400, "UNSUPPORTED_IMAGE_FORMAT"),
            ({"file": (BytesIO(self._image_bytes()), "large.png")}, ServiceConfig(max_image_bytes=10), 413, "IMAGE_TOO_LARGE"),
            ({"file": (BytesIO(self._image_bytes()), "wide.png")}, ServiceConfig(max_image_side=20), 413, "IMAGE_DIMENSIONS_TOO_LARGE"),
            ({"file": (BytesIO(self._image_bytes()), "pixels.png")}, ServiceConfig(max_image_pixels=10), 413, "IMAGE_DIMENSIONS_TOO_LARGE"),
            ({"prompt": "x" * 100}, ServiceConfig(max_request_bytes=32), 413, "REQUEST_TOO_LARGE"),
            ({"prompt": "too long"}, ServiceConfig(max_prompt_chars=2), 400, "PROMPT_TOO_LONG"),
            ({"prompt": "hello", "session_id": "invalid id"}, ServiceConfig(), 400, "INVALID_SESSION_ID"),
            ({"prompt": "hello", "trace_id": "invalid id"}, ServiceConfig(), 400, "INVALID_TRACE_ID"),
            ({}, ServiceConfig(), 400, "MISSING_PROMPT"),
            ({"prompt": "描述", "file": [(BytesIO(self._image_bytes()), "a.png"), (BytesIO(self._image_bytes()), "b.png")]}, ServiceConfig(), 400, "MULTIPLE_IMAGES"),
            ({"file": (BytesIO(self._image_bytes()), "a.png"), "image": base64.b64encode(self._image_bytes()).decode("ascii")}, ServiceConfig(), 400, "MULTIPLE_IMAGES"),
        ]
        for data, config, status, code in cases:
            with self.subTest(code=code):
                client, service = self._client(config)
                response = client.post("/chat/stream", data=data, content_type="multipart/form-data")
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.get_json()["error_code"], code)
                self.assertTrue(response.content_type.startswith("application/json"))
                service.stream.assert_not_called()

    def test_form_text_and_header_ids_are_supported(self) -> None:
        client, service = self._client()
        response = client.post("/chat/stream", data={"prompt": "你好"}, content_type="multipart/form-data",
                               headers={"X-Session-ID": "header-session", "X-Trace-ID": "header-trace"})
        response.get_data()
        self.assertEqual(response.status_code, 200)
        service.stream.assert_called_once_with("你好", image_base64=None, session_id="header-session", trace_id="header-trace")

    def test_multipart_image_reaches_the_actual_model_stream(self) -> None:
        llm = MagicMock()
        llm.invoke.return_value = SimpleNamespace(content='{"action":"final","answer":"准备回答"}')
        llm.stream.return_value = iter([SimpleNamespace(content="图片"), SimpleNamespace(content="描述。")])
        service = MagicMock()
        service.memory = SessionMemoryStore()
        with patch("llm_agent_service.app.ReidService", return_value=service):
            app = create_app(engine=MagicMock(), db_cfg=DbConfig("localhost", 5432, "user", "password", "db"),
                             svc_cfg=ServiceConfig(), llm=llm)
        image = self._image_bytes()
        response = app.test_client().post("/chat/stream", data={
            "file": (BytesIO(image), "image.png"), "prompt": "描述", "session_id": "vision",
        })
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body.count("event: delta"), 2)
        image_url = "data:image/png;base64," + base64.b64encode(image).decode("ascii")
        self.assertIn(image_url, str(llm.stream.call_args.args[0]))
        llm.stream.assert_called_once()
        with service.memory.conversation("vision") as conversation:
            self.assertEqual(conversation.messages()[-1].content, "图片描述。")


if __name__ == "__main__":
    unittest.main()
