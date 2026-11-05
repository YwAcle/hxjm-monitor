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
from tests.agent.gallery_capability_fixture import GalleryCapabilityFixture
from business_api.config import DbConfig
from llm_agent_service.config import ModelConfig, ServiceConfig
from llm_agent_service.llm import build_llm
from llm_agent_service.service.memory import SessionMemoryStore
from ai_infra.sglang_model import ChatSGLang, SGLangRequestError
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
        bridge = GalleryCapabilityFixture(MagicMock()).bridge
        patcher = patch("llm_agent_service.app.CapabilityBridge.from_env", return_value=bridge)
        patcher.start()
        self.addCleanup(patcher.stop)
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

    def tearDown(self) -> None:
        self.model.close()

    def test_agent_factory_defaults_to_sglang(self) -> None:
        model = build_llm(ModelConfig())
        self.assertIsInstance(model, ChatSGLang)
        model.close()



    def test_ready_checks_capability_and_sglang(self) -> None:
        db_cfg = DbConfig(
            host="localhost",
            port=5432,
            user="test",
            password="test",
            database="test",
        )
        with patch("llm_agent_service.app.SessionMemoryStore", return_value=SessionMemoryStore()):
            app = create_app(
                svc_cfg=ServiceConfig(),
                llm=self.model,
            )

        response = app.test_client().get("/ready")
        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["capability_directory"], "ok")
        self.assertEqual(data["llm"], "ok")
        self.assertEqual(data["llm_model"], "internvl3.5-8b")

    def test_ready_marks_skipped_model_healthcheck(self) -> None:
        self.model.check_models = False
        with patch("llm_agent_service.app.SessionMemoryStore", return_value=SessionMemoryStore()):
            app = create_app(
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
        service.memory.clear.return_value = True
        agent_service = MagicMock()
        agent_service.process.return_value = {"type": "agent", "text": "测试响应"}
        with patch("llm_agent_service.app.SessionMemoryStore", return_value=service.memory), patch(
            "llm_agent_service.app.AgentService", return_value=agent_service
        ):
            app = create_app(
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
        service.memory.clear.assert_called_once_with("browser-1")

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
        with patch("llm_agent_service.app.SessionMemoryStore", return_value=service.memory), patch(
            "llm_agent_service.app.AgentService", return_value=agent_service
        ):
            app = create_app(
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
        with patch("llm_agent_service.app.SessionMemoryStore", return_value=service.memory), patch(
            "llm_agent_service.app.AgentService", return_value=agent_service
        ):
            app = create_app(
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
        with patch("llm_agent_service.app.SessionMemoryStore", return_value=service.memory), patch(
            "llm_agent_service.app.AgentService", return_value=agent_service
        ):
            app = create_app(
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
        with patch("llm_agent_service.app.SessionMemoryStore", return_value=service.memory):
            app = create_app(
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







if __name__ == "__main__":
    unittest.main()
