from __future__ import annotations

import base64
import json
import unittest
from io import BytesIO

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from PIL import Image

from llm_report_service.config import ModelConfig, ServiceConfig
from llm_report_service.llm.factory import build_chat_model
from llm_report_service.llm.sglang_model import ChatSGLang
from llm_report_service.service.episode_builder import EpisodeSemanticInput
from llm_report_service.service.report_runner import (
    build_remote_multimodal_content,
    run_llm_report,
)


def _image_base64() -> str:
    output = BytesIO()
    Image.new("RGB", (32, 24), (20, 40, 60)).save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


def _semantic(*, with_image: bool = True) -> EpisodeSemanticInput:
    return EpisodeSemanticInput(
        episode_id="episode-1",
        time_range={
            "start": "2026-09-10T10:00:00Z",
            "end": "2026-09-10T10:01:00Z",
        },
        camera_id=1,
        person={
            "name": "STR-001",
            "image_base64": _image_base64() if with_image else None,
        },
        trajectory={"color_rgb": [255, 0, 0], "points": [[1, 2]], "point_count": 1},
        media=[],
    )


class ChatSGLangTests(unittest.TestCase):
    def test_build_chat_model_is_restricted_to_sglang(self) -> None:
        remote = build_chat_model(ModelConfig())
        self.assertIsInstance(remote, ChatSGLang)
        remote.close()

        with self.assertRaises(ValueError):
            build_chat_model(ModelConfig(backend="transformers"))

    def test_thinking_setting_reaches_chat_payload(self) -> None:
        messages = [HumanMessage(content="hello")]
        model = build_chat_model(ModelConfig(enable_thinking=False))
        try:
            payload = model._payload(messages, None, {}, stream=False)
            self.assertEqual(
                payload["chat_template_kwargs"], {"enable_thinking": False}
            )
            overridden = model._payload(
                messages,
                None,
                {"extra_body": {"chat_template_kwargs": {"enable_thinking": True}}},
                stream=False,
            )
            self.assertEqual(
                overridden["chat_template_kwargs"], {"enable_thinking": True}
            )
        finally:
            model.close()

        model = build_chat_model(ModelConfig(enable_thinking=None))
        try:
            self.assertNotIn(
                "chat_template_kwargs",
                model._payload(messages, None, {}, stream=False),
            )
        finally:
            model.close()

    def test_multimodal_content_uses_data_url(self) -> None:
        content = build_remote_multimodal_content(
            _semantic(),
            [],
            max_video_frames=2,
            media_base_dir="/tmp",
        )
        image_blocks = [block for block in content if block["type"] == "image_url"]
        self.assertEqual(len(image_blocks), 1)
        self.assertTrue(
            image_blocks[0]["image_url"]["url"].startswith(
                "data:image/jpeg;base64,"
            )
        )
        self.assertEqual(content[-1]["type"], "text")
        self.assertIn("episode-1", content[-1]["text"])

    def test_langchain_invoke_sends_openai_payload(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "model": "internvl3.5-8b",
                    "choices": [
                        {
                            "message": {"content": '{"ok": true}'},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 4},
                },
            )

        model = ChatSGLang(model_name="internvl3.5-8b", max_retries=0)
        model._client = httpx.Client(transport=httpx.MockTransport(handler))
        response = model.invoke(
            [SystemMessage(content="system"), HumanMessage(content="hello")],
            response_format={"type": "json_object"},
        )

        self.assertEqual(response.content, '{"ok": true}')
        self.assertEqual(captured["model"], "internvl3.5-8b")
        self.assertEqual(captured["messages"][1]["role"], "user")
        self.assertEqual(captured["response_format"], {"type": "json_object"})

    def test_report_runner_uses_json_schema(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "model": "internvl3.5-8b",
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "event_type": "walking",
                                        "summary": "STR-001 正在行走。",
                                        "risk_level": "low",
                                        "key_observations": ["未发现异常"],
                                        "confidence": 0.9,
                                    },
                                    ensure_ascii=False,
                                )
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {},
                },
            )

        model = ChatSGLang(model_name="internvl3.5-8b", max_retries=0)
        model._client = httpx.Client(transport=httpx.MockTransport(handler))
        report, text = run_llm_report(
            model,
            _semantic(),
            [],
            ServiceConfig(max_video_frames=2, media_base_dir="/tmp"),
        )

        self.assertEqual(report["risk_level"], "low")
        self.assertEqual(text, "STR-001 正在行走。")
        self.assertEqual(captured["response_format"]["type"], "json_schema")
        schema = captured["response_format"]["json_schema"]["schema"]
        self.assertIn("risk_level", schema["properties"])


if __name__ == "__main__":
    unittest.main()
