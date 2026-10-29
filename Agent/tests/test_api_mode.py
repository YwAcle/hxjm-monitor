"""API 配置在干净子进程中贯穿多个业务客户端，不访问外网或 GPU。"""

import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class APIModeTests(unittest.TestCase):
    def run_api_python(self, script, **overrides):
        env = {key: value for key, value in os.environ.items() if not key.startswith("LLM_")}
        env.update({
            "LLM_MODE": "api", "LLM_BACKEND": "vllm", "LLM_HEALTHCHECK": "auto",
            "LLM_MODEL_ID": "local-model", "LLM_API_KEY": "local-only-secret",
            "LLM_ENABLE_THINKING": "false",
            "LLM_REMOTE_BASE_URL": "https://example.invalid/v1",
            "LLM_REMOTE_MODEL_ID": "remote-vision-model", "LLM_REMOTE_API_KEY": "test-api-secret",
            "LLM_REMOTE_ENABLE_THINKING": "", "LLM_REMOTE_RESPONSE_FORMAT": "json_schema",
        })
        env.update(overrides)
        result = subprocess.run([sys.executable, "-B", "-c", script], cwd=ROOT, env=env,
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_api_config_reaches_report_agent_and_chat(self):
        self.run_api_python('''
import json
import httpx
from langchain_core.messages import HumanMessage
from llm_agent_service.llm import build_llm as build_agent
from llm_chat_service.config import ModelConfig as ChatConfig
from llm_chat_service.llm.model import build_llm as build_chat
from llm_report_service.config import ModelConfig
from llm_report_service.llm.factory import build_chat_model

for model in (build_chat_model(ModelConfig()), build_agent(ModelConfig()), build_chat(ChatConfig())):
    try:
        assert model.model_name == "remote-vision-model"
        assert model.base_url == "https://example.invalid/v1"
        assert model.api_key == "test-api-secret"
        assert model.enable_thinking is None
        assert model.check_health() == {"model": "remote-vision-model", "healthcheck": "skipped"}
        assert model._client is None  # 就绪检查不能请求服务商或产生费用
        headers = model._get_client().headers
        assert headers["Authorization"] == "Bearer test-api-secret"
        model.close()
        captured = []
        def handler(request):
            assert str(request.url) == "https://example.invalid/v1/chat/completions"
            assert request.headers["Authorization"] == "Bearer test-api-secret"
            captured.append(json.loads(request.content))
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})
        model._client = httpx.Client(transport=httpx.MockTransport(handler), headers=headers)
        content = [{"type": "text", "text": "Describe this image"},
                   {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]
        schema = {"type": "json_schema", "json_schema": {"name": "report", "schema": {"type": "object"}}}
        assert model.invoke([HumanMessage(content=content)], response_format=schema).content == "ok"
        assert captured[0]["model"] == "remote-vision-model"
        assert captured[0]["messages"][0]["content"] == content
        assert captured[0]["response_format"] == schema
        assert "chat_template_kwargs" not in captured[0]
    finally:
        model.close()
''')

    def test_api_response_format_modes_reach_all_clients(self):
        for mode in ("json_schema", "json_object", "none"):
            with self.subTest(mode=mode):
                self.run_api_python('''
import os
from langchain_core.messages import HumanMessage
from llm_agent_service.llm import build_llm as build_agent
from llm_chat_service.config import ModelConfig as ChatConfig
from llm_chat_service.llm.model import build_llm as build_chat
from llm_report_service.config import ModelConfig
from llm_report_service.llm.factory import build_chat_model

mode = os.environ["LLM_REMOTE_RESPONSE_FORMAT"]
schema = {"type": "json_schema", "json_schema": {"name": "decision", "schema": {"type": "object"}}}
messages = [HumanMessage(content="Return a JSON object")]
for model in (build_chat_model(ModelConfig()), build_agent(ModelConfig()), build_chat(ChatConfig())):
    try:
        assert model.response_format_mode == mode
        for stream in (False, True):
            for kwargs in ({"response_format": schema}, {"extra_body": {"response_format": schema}}):
                payload = model._payload(messages, None, kwargs, stream=stream)
                if mode == "none":
                    assert "response_format" not in payload
                else:
                    assert payload["response_format"] == (schema if mode == "json_schema" else {"type": "json_object"})
            assert "response_format" not in model._payload(messages, None, {}, stream=stream)
        assert schema["type"] == "json_schema"  # 不修改调用方的原始 schema
    finally:
        model.close()
''', LLM_REMOTE_RESPONSE_FORMAT=mode)

    def test_api_can_explicitly_enable_models_check_and_thinking(self):
        self.run_api_python('''
import httpx
from langchain_core.messages import HumanMessage
from llm_report_service.config import ModelConfig
from llm_report_service.llm.factory import build_chat_model
model = build_chat_model(ModelConfig())
try:
    requests = []
    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(200, json={"data": [{"id": "remote-vision-model"}]})
    model._client = httpx.Client(transport=httpx.MockTransport(handler))
    assert model.check_health()["model"] == "remote-vision-model"
    assert requests == ["https://example.invalid/v1/models"]
    payload = model._payload([HumanMessage(content="hello")], None, {}, stream=False)
    assert payload["chat_template_kwargs"] == {"enable_thinking": True}
finally:
    model.close()
''', LLM_HEALTHCHECK="models", LLM_REMOTE_ENABLE_THINKING="true")

    def test_local_engine_argument_overrides_api_mode_in_file(self):
        env = dict(os.environ, LLM_MODE="api", LLM_REMOTE_BASE_URL="",
                   LLM_REMOTE_MODEL_ID="", CONFIG_PYTHON_BIN=sys.executable)
        for backend in ("vllm", "sglang"):
            result = subprocess.run([str(ROOT / "scripts/start_all.sh"), backend, "--show-config"],
                                    cwd=ROOT, env=env, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            fields = dict(line.split("=", 1) for line in result.stdout.splitlines())
            self.assertEqual(fields["LLM_MODE"], "local")
            self.assertEqual(fields["LLM_BACKEND"], backend)


if __name__ == "__main__":
    unittest.main()
