from __future__ import annotations

import base64
import json
import threading
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

import httpx
from PIL import Image

from llm_agent_service.app import create_app
from llm_agent_service.config import DbConfig, ModelConfig, ServiceConfig
from llm_agent_service.llm import build_llm
from llm_agent_service.service.memory import SessionMemoryStore
from llm_agent_service.service.reid_service import ReidService
from llm_report_service.llm.sglang_model import ChatSGLang, SGLangRequestError
from langchain_core.messages import HumanMessage


def _image_base64() -> str:
    output = BytesIO()
    Image.new("RGB", (24, 16), (30, 60, 90)).save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, statement):
        return None


class _Engine:
    def connect(self):
        return _Connection()


class SGLangAgentServiceTests(unittest.TestCase):
    def test_stream_preserves_finish_reason(self) -> None:
        events = [
            {"choices": [{"delta": {"content": "部分回答"}, "finish_reason": None}]},
            {"choices": [{"delta": {}, "finish_reason": "length"}]},
        ]
        body = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
        model = ChatSGLang(max_retries=0)
        model._client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body)))
        try:
            chunks = list(model.stream([HumanMessage(content="你好")]))
            self.assertEqual("".join(chunk.content for chunk in chunks), "部分回答")
            self.assertTrue(any(chunk.response_metadata.get("finish_reason") == "length" for chunk in chunks))
        finally:
            model.close()

    def test_stream_rejects_missing_end_marker_and_error_events(self) -> None:
        for event in (
            {"choices": [{"delta": {"content": "部分回答"}}]},
            {"error": {"message": "模型错误"}},
        ):
            with self.subTest(event=event):
                body = f"data: {json.dumps(event)}\n\n"
                model = ChatSGLang(max_retries=0)
                model._client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body)))
                try:
                    with self.assertRaises(SGLangRequestError):
                        list(model.stream([HumanMessage(content="你好")]))
                finally:
                    model.close()

    def setUp(self) -> None:
        self.requests: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET" and request.url.path.endswith("/models"):
                return httpx.Response(
                    200,
                    json={
                        "object": "list",
                        "data": [{"id": "internvl3.5-8b", "object": "model"}],
                    },
                )

            payload = json.loads(request.content)
            self.requests.append(payload)
            return httpx.Response(
                200,
                json={
                    "model": "internvl3.5-8b",
                    "choices": [
                        {
                            "message": {"content": "测试响应"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {},
                },
            )

        self.model = ChatSGLang(model_name="internvl3.5-8b", max_retries=0)
        self.model._client = httpx.Client(transport=httpx.MockTransport(handler))
        self.service = ReidService.__new__(ReidService)
        self.service.llm = self.model
        self.service.memory = SessionMemoryStore(max_sessions=10, max_messages=4)
        self.service.known_persons = {}
        self.service._known_persons_lock = threading.Lock()

    def tearDown(self) -> None:
        self.model.close()

    def test_agent_factory_defaults_to_sglang(self) -> None:
        model = build_llm(ModelConfig())
        self.assertIsInstance(model, ChatSGLang)
        model.close()

    def test_text_invocation_uses_langchain_chat_payload(self) -> None:
        response = self.service._invoke_text("你好", max_new_tokens=64)

        self.assertEqual(response, "测试响应")
        self.assertEqual(self.requests[0]["messages"][0]["role"], "user")
        self.assertEqual(self.requests[0]["messages"][0]["content"], "你好")
        self.assertEqual(self.requests[0]["max_tokens"], 64)

    def test_image_invocation_sends_data_url(self) -> None:
        image = Image.open(BytesIO(base64.b64decode(_image_base64()))).convert("RGB")
        response = self.service._invoke_image(
            "描述图片",
            image,
            max_new_tokens=128,
        )

        self.assertEqual(response, "测试响应")
        content = self.requests[0]["messages"][0]["content"]
        self.assertEqual(content[0], {"type": "text", "text": "描述图片"})
        self.assertEqual(content[1]["type"], "image_url")
        self.assertTrue(
            content[1]["image_url"]["url"].startswith(
                "data:image/jpeg;base64,"
            )
        )

    def test_ready_checks_database_and_sglang(self) -> None:
        db_cfg = DbConfig(
            host="localhost",
            port=5432,
            user="test",
            password="test",
            database="test",
        )
        with patch("llm_agent_service.app.ReidService"):
            app = create_app(
                engine=_Engine(),
                db_cfg=db_cfg,
                svc_cfg=ServiceConfig(),
                llm=self.model,
            )

        response = app.test_client().get("/ready")
        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["database"], "ok")
        self.assertEqual(data["llm"], "ok")
        self.assertEqual(data["llm_model"], "internvl3.5-8b")

    def test_ready_marks_skipped_model_healthcheck(self) -> None:
        self.model.check_models = False
        with patch("llm_agent_service.app.ReidService"):
            app = create_app(
                engine=_Engine(),
                db_cfg=DbConfig(host="localhost", port=5432, user="test", password="test", database="test"),
                svc_cfg=ServiceConfig(),
                llm=self.model,
            )
        with patch.object(httpx.Client, "get", side_effect=AssertionError("不应访问远程模型列表")):
            response = app.test_client().get("/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["llm_healthcheck"], "skipped")

    def test_chat_api_passes_and_returns_session_id(self) -> None:
        db_cfg = DbConfig(
            host="localhost",
            port=5432,
            user="test",
            password="test",
            database="test",
        )
        service = MagicMock()
        service.clear_memory.return_value = True
        agent_service = MagicMock()
        agent_service.process.return_value = {"type": "agent", "text": "测试响应"}
        with patch("llm_agent_service.app.ReidService", return_value=service), patch(
            "llm_agent_service.app.AgentService", return_value=agent_service
        ):
            app = create_app(
                engine=_Engine(),
                db_cfg=db_cfg,
                svc_cfg=ServiceConfig(),
                llm=self.model,
            )

        client = app.test_client()
        response = client.post(
            "/chat",
            json={"prompt": "你好", "session_id": "browser-1", "trace_id": "trace-1"},
        )
        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["session_id"], "browser-1")
        self.assertEqual(data["trace_id"], "trace-1")
        self.assertEqual(response.headers["X-Trace-ID"], "trace-1")
        agent_service.process.assert_called_once_with(
            "你好",
            image_base64=None,
            session_id="browser-1",
            trace_id="trace-1",
        )

        clear_response = client.delete("/sessions/browser-1/memory")
        self.assertEqual(clear_response.status_code, 200)
        self.assertTrue(clear_response.get_json()["cleared"])
        service.clear_memory.assert_called_once_with("browser-1")

    def test_chat_api_keeps_image_prompt_and_session_id(self) -> None:
        db_cfg = DbConfig(
            host="localhost",
            port=5432,
            user="test",
            password="test",
            database="test",
        )
        service = MagicMock()
        agent_service = MagicMock()
        agent_service.process.return_value = {"type": "agent", "text": "海绵宝宝"}
        with patch("llm_agent_service.app.ReidService", return_value=service), patch(
            "llm_agent_service.app.AgentService", return_value=agent_service
        ):
            app = create_app(
                engine=_Engine(),
                db_cfg=db_cfg,
                svc_cfg=ServiceConfig(),
                llm=self.model,
            )

        response = app.test_client().post(
            "/chat",
            data={
                "prompt": "请分析这张图片",
                "session_id": "image-session",
                "file": (BytesIO(base64.b64decode(_image_base64())), "image.png"),
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["session_id"], "image-session")
        agent_service.process.assert_called_once_with(
            "请分析这张图片",
            image_base64=unittest.mock.ANY,
            session_id="image-session",
            trace_id=unittest.mock.ANY,
        )
        image_argument = agent_service.process.call_args.kwargs["image_base64"]
        self.assertTrue(image_argument.startswith("data:image/png;base64,"))

    def test_chat_api_keeps_empty_prompt_for_json_image_only(self) -> None:
        db_cfg = DbConfig(
            host="localhost",
            port=5432,
            user="test",
            password="test",
            database="test",
        )
        service = MagicMock()
        agent_service = MagicMock()
        agent_service.process.return_value = {"type": "agent", "text": "图片描述"}
        with patch("llm_agent_service.app.ReidService", return_value=service), patch(
            "llm_agent_service.app.AgentService", return_value=agent_service
        ):
            app = create_app(
                engine=_Engine(),
                db_cfg=db_cfg,
                svc_cfg=ServiceConfig(),
                llm=self.model,
            )

        response = app.test_client().post(
            "/chat",
            json={
                "prompt": "",
                "image": _image_base64(),
                "session_id": "image-only-json",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["session_id"], "image-only-json")
        agent_service.process.assert_called_once_with(
            "",
            image_base64=unittest.mock.ANY,
            session_id="image-only-json",
            trace_id=unittest.mock.ANY,
        )
        image_argument = agent_service.process.call_args.kwargs["image_base64"]
        self.assertTrue(image_argument.startswith("data:image/png;base64,"))

    def test_chat_api_keeps_empty_prompt_for_file_only(self) -> None:
        db_cfg = DbConfig(
            host="localhost",
            port=5432,
            user="test",
            password="test",
            database="test",
        )
        service = MagicMock()
        agent_service = MagicMock()
        agent_service.process.return_value = {"type": "agent", "text": "图片描述"}
        with patch("llm_agent_service.app.ReidService", return_value=service), patch(
            "llm_agent_service.app.AgentService", return_value=agent_service
        ):
            app = create_app(
                engine=_Engine(),
                db_cfg=db_cfg,
                svc_cfg=ServiceConfig(),
                llm=self.model,
            )

        response = app.test_client().post(
            "/chat",
            data={
                "session_id": "image-only-file",
                "file": (BytesIO(base64.b64decode(_image_base64())), "image.png"),
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        agent_service.process.assert_called_once_with(
            "",
            image_base64=unittest.mock.ANY,
            session_id="image-only-file",
            trace_id=unittest.mock.ANY,
        )

    def test_chat_api_rejects_request_without_prompt_or_image(self) -> None:
        db_cfg = DbConfig(
            host="localhost",
            port=5432,
            user="test",
            password="test",
            database="test",
        )
        service = MagicMock()
        with patch("llm_agent_service.app.ReidService", return_value=service):
            app = create_app(
                engine=_Engine(),
                db_cfg=db_cfg,
                svc_cfg=ServiceConfig(),
                llm=self.model,
            )

        response = app.test_client().post(
            "/chat",
            json={"prompt": "", "session_id": "empty-request"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "缺少 prompt")
        service.process.assert_not_called()

    def test_same_session_sends_previous_turns(self) -> None:
        first = self.service.process("第一句话", session_id="session-a")
        second = self.service.process("我刚才说了什么", session_id="session-a")

        self.assertEqual(first["text"], "测试响应")
        self.assertEqual(second["text"], "测试响应")
        messages = self.requests[1]["messages"]
        self.assertEqual(
            [(message["role"], message["content"]) for message in messages],
            [
                ("user", "第一句话"),
                ("assistant", "测试响应"),
                ("user", "我刚才说了什么"),
            ],
        )

    def test_image_description_is_available_to_follow_up(self) -> None:
        self.service.process(
            "描述图片",
            image_base64=_image_base64(),
            session_id="image-session",
        )
        self.service.process("刚才的图片是什么", session_id="image-session")

        messages = self.requests[1]["messages"]
        self.assertEqual(
            [(message["role"], message["content"]) for message in messages],
            [
                ("user", "描述图片\n[用户上传了一张图片]"),
                ("assistant", "测试响应"),
                ("user", "刚才的图片是什么"),
            ],
        )

    def test_memory_response_keeps_visible_text_and_business_summary(self) -> None:
        memory_text = self.service._memory_response_text(
            {
                "text": "图片中是海绵宝宝。\n\nReID分析结果如下",
                "summary": "今天没有查询到相关轨迹。",
            }
        )

        self.assertIn("图片中是海绵宝宝", memory_text)
        self.assertIn("今天没有查询到相关轨迹", memory_text)

    def test_sessions_are_isolated_and_memory_can_be_cleared(self) -> None:
        self.service.process("会话A", session_id="session-a")
        self.service.process("会话B", session_id="session-b")
        self.assertEqual(len(self.requests[1]["messages"]), 1)

        self.assertTrue(self.service.clear_memory("session-a"))
        self.assertFalse(self.service.clear_memory("session-a"))
        self.service.process("清空之后", session_id="session-a")
        self.assertEqual(len(self.requests[2]["messages"]), 1)

    def test_memory_keeps_only_configured_recent_messages(self) -> None:
        for index in range(3):
            self.service.process(f"消息{index}", session_id="bounded")

        with self.service.memory.conversation("bounded") as conversation:
            contents = [message.content for message in conversation.messages()]
        self.assertEqual(contents, ["消息1", "测试响应", "消息2", "测试响应"])


if __name__ == "__main__":
    unittest.main()
