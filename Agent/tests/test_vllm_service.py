from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import httpx
from langchain_core.messages import HumanMessage

from llm_agent_service.llm import build_llm
from llm_report_service.config import ModelConfig, ServiceConfig
from llm_report_service.llm.factory import build_chat_model
from llm_report_service.llm.vllm_model import ChatVLLM
from llm_report_service.service.report_runner import run_llm_report
from tests.test_sglang_report_service import _semantic
from tests import test_sglang_agent_service as agent_tests


ROOT = Path(__file__).resolve().parents[1]


class VLLMServiceTests(unittest.TestCase):
    def test_factory_and_report_multimodal_schema(self) -> None:
        captured = []

        def handler(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200, json={
                "choices": [{"message": {"content": json.dumps({
                    "event_type": "walking", "summary": "Walking",
                    "risk_level": "low", "key_observations": [], "confidence": 0.9,
                })}, "finish_reason": "stop"}],
            })

        model = build_chat_model(ModelConfig(backend="vllm", enable_thinking=False))
        self.assertIsInstance(model, ChatVLLM)
        self.assertEqual(model._llm_type, "vllm_openai")
        model._client = httpx.Client(transport=httpx.MockTransport(handler))
        try:
            report, text = run_llm_report(model, _semantic(), [], ServiceConfig())
            self.assertEqual(text, "Walking")
            self.assertEqual(report["risk_level"], "low")
            payload = captured[0]
            self.assertEqual(payload["response_format"]["type"], "json_schema")
            self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})
            self.assertTrue(any(block["type"] == "image_url"
                                for block in payload["messages"][1]["content"]))
        finally:
            model.close()

    def test_health_and_stream(self) -> None:
        def handler(request):
            if request.method == "GET":
                return httpx.Response(200, json={"data": [{"id": "test-model"}]})
            payload = json.loads(request.content)
            self.assertTrue(payload["stream"])
            event = json.dumps({"choices": [{"delta": {"content": "Hello"}}]})
            return httpx.Response(200, text=f"data: {event}\n\ndata: [DONE]\n\n")

        model = build_llm(ModelConfig(backend="vllm", model_name="test-model"))
        model._client = httpx.Client(transport=httpx.MockTransport(handler))
        try:
            self.assertEqual(model.check_health()["model"], "test-model")
            self.assertEqual("".join(chunk.content for chunk in model.stream(
                [HumanMessage(content="hello")]
            )), "Hello")
        finally:
            model.close()

    def test_agent_image_request(self) -> None:
        fixture = agent_tests.SGLangAgentServiceTests()
        fixture.setUp()
        model = ChatVLLM()
        model._client = fixture.model._client
        fixture.service.llm = model
        try:
            fixture.test_image_invocation_sends_data_url()
        finally:
            model.close()
            fixture.model._client = None

    def test_launch_arguments_and_quoted_env(self) -> None:
        # A fake interpreter captures argv without loading model weights or a GPU.
        with tempfile.TemporaryDirectory() as directory:
            python = Path(directory) / "python"
            python.write_text('#!/bin/bash\nif [[ "$1" == "-c" ]]; then exit 0; fi\nprintf "%s\\n" "$@"\n')
            python.chmod(0o755)
            env = dict(os.environ, VLLM_PYTHON_BIN=str(python),
                       VLLM_CACHE_ROOT=directory, LLM_MODEL_PATH="org/test-model",
                       LLM_MODEL_ID="test-name", LLM_TP_SIZE="2")
            env["VLLM_LIMIT_MM_PER_PROMPT"] = '{"image":32}'
            result = subprocess.run([str(ROOT / "llm_report_service/start_vllm.sh"),
                                     "--enforce-eager"], env=env, text=True,
                                    capture_output=True, check=True)
            args = result.stdout.splitlines()
            self.assertEqual(args[args.index("--model") + 1], "org/test-model")
            self.assertEqual(args[args.index("--served-model-name") + 1], "test-name")
            self.assertEqual(args[args.index("--tensor-parallel-size") + 1], "2")
            self.assertEqual(json.loads(args[args.index("--limit-mm-per-prompt") + 1]),
                             {"image": 32})
            self.assertIn("--enforce-eager", args)
            env["VLLM_LIMIT_MM_PER_PROMPT"] = ""
            result = subprocess.run([str(ROOT / "llm_report_service/start_vllm.sh")],
                                    env=env, text=True, capture_output=True, check=True)
            args = result.stdout.splitlines()
            self.assertEqual(json.loads(args[args.index("--limit-mm-per-prompt") + 1]),
                             {"image": 32})


if __name__ == "__main__":
    unittest.main()
