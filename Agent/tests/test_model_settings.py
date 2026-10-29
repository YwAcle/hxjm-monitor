"""Verify config propagation without loading weights or starting GPU processes."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from llm_report_service.llm.settings import resolve_model_settings


ROOT = Path(__file__).resolve().parents[1]


class ModelSettingsTests(unittest.TestCase):
    def test_common_settings_for_both_backends(self):
        for backend in ("vllm", "sglang"):
            result = resolve_model_settings({
                "LLM_BACKEND": backend, "LLM_MODEL_PATH": "./weights/test-model",
                "LLM_SERVER_PORT": "18080", "LLM_TP_SIZE": "2",
                "LLM_CHAT_TEMPLATE": "./scripts/template.jinja",
                "VLLM_TP_SIZE": "9", "SGLANG_TP_SIZE": "8",
            }, ROOT)
            self.assertEqual(result["LLM_MODEL_PATH"], str(ROOT / "weights/test-model"))
            self.assertEqual(result["LLM_MODEL_ID"], "test-model")
            self.assertEqual(result["LLM_BASE_URL"], "http://127.0.0.1:18080/v1")
            self.assertEqual(result["LLM_TP_SIZE"], "2")
            self.assertEqual(result["LLM_CHAT_TEMPLATE"], str(ROOT / "scripts/template.jinja"))

    def test_remote_overrides_and_legacy_fallback(self):
        result = resolve_model_settings({
            "LLM_BACKEND": "vllm", "VLLM_MODEL_PATH": "org/weights",
            "VLLM_MODEL_NAME": "old-alias", "VLLM_MAX_MODEL_LEN": "4096",
            "LLM_BASE_URL": "https://example.invalid/v1", "LLM_MODEL_ID": "remote-name",
        })
        self.assertEqual(result["LLM_MODEL_ID"], "remote-name")
        self.assertEqual(result["LLM_BASE_URL"], "https://example.invalid/v1")
        self.assertEqual(result["LLM_MODEL_PATH"], "org/weights")
        self.assertEqual(result["LLM_CONTEXT_LENGTH"], "4096")
        self.assertEqual(resolve_model_settings({
            "LLM_BACKEND": "sglang", "SGLANG_MODEL_NAME": "old-alias",
        })["LLM_MODEL_ID"], "old-alias")

    def test_invalid_backend_and_multiline_rejected(self):
        for env in ({"LLM_BACKEND": "other"}, {"LLM_MODEL_ID": "model\ninjected=1"}):
            with self.assertRaises(ValueError):
                resolve_model_settings(env)

    def test_switch_preview_and_python_agree(self):
        for backend in ("vllm", "sglang"):
            env = dict(os.environ, LLM_BACKEND="sglang" if backend == "vllm" else "vllm",
                       LLM_MODEL_PATH="./weights/preview", LLM_MODEL_ID="preview-alias",
                       LLM_SERVER_PORT="18081", LLM_BASE_URL="http://127.0.0.1:18081/v1",
                       LLM_API_KEY="test-secret-must-not-print")
            result = subprocess.run([str(ROOT / "scripts/start_all.sh"), backend, "--show-config"],
                                    cwd=ROOT, env=env, capture_output=True, text=True, check=True)
            fields = dict(line.split("=", 1) for line in result.stdout.splitlines())
            expected = resolve_model_settings(dict(env, LLM_MODE="local", LLM_BACKEND=backend))
            expected = {key: value for key, value in expected.items() if not key.endswith("_API_KEY")}
            self.assertEqual(fields, expected)
            self.assertNotIn(env["LLM_API_KEY"], result.stdout + result.stderr)

    def test_sglang_receives_common_configuration(self):
        cache = ROOT / ".runtime-cache"
        cache.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as directory:
            base = Path(directory)
            bindir = base / "bin"
            bindir.mkdir()
            for name in ("sglang", "python", "x86_64-conda-linux-gnu-gcc",
                         "x86_64-conda-linux-gnu-g++", "nvcc"):
                path = bindir / name
                path.write_text('#!/bin/bash\nprintf "%s\\n" "$@"\n')
                path.chmod(0o755)
            model = base / "model"
            model.mkdir()
            (model / "config.json").write_text("{}")
            env = dict(os.environ, SGLANG_ENV_ROOT=directory, CUDA_TOOLKIT=directory,
                       SGLANG_BIN=str(bindir / "sglang"), SGLANG_PYTHON_BIN=str(bindir / "python"),
                       SGLANG_CACHE_ROOT=str(base / "cache"), LLM_BACKEND="vllm",
                       LLM_MODEL_PATH=str(model), LLM_MODEL_ID="shared-name", LLM_TP_SIZE="2",
                       LLM_CONTEXT_LENGTH="12345", LLM_GPU_MEMORY_UTILIZATION="0.75",
                       LLM_SERVER_PORT="18082", LLM_API_KEY="test-key")
            result = subprocess.run([str(ROOT / "scripts/start_sglang.sh")], cwd=ROOT,
                                    env=env, capture_output=True, text=True, check=True)
            args = result.stdout.splitlines()
            for flag, value in (("--model-path", str(model)), ("--served-model-name", "shared-name"),
                                ("--tp-size", "2"), ("--context-length", "12345"),
                                ("--mem-fraction-static", "0.75"), ("--port", "18082"),
                                ("--api-key", "test-key")):
                self.assertEqual(args[args.index(flag) + 1], value)

    def test_api_profile_is_independent_and_can_switch_back(self):
        env = {
            "LLM_MODE": "api", "LLM_BACKEND": "vllm",
            "LLM_MODEL_ID": "local-model", "LLM_API_KEY": "local-secret",
            "LLM_BASE_URL": "http://127.0.0.1:18000/v1", "LLM_ENABLE_THINKING": "false",
            "LLM_REMOTE_BASE_URL": "https://example.invalid/api/v1/",
            "LLM_REMOTE_MODEL_ID": "remote-model", "LLM_REMOTE_API_KEY": "remote-secret",
        }
        remote = resolve_model_settings(env)
        self.assertEqual(remote["LLM_BASE_URL"], "https://example.invalid/api/v1")
        self.assertEqual(remote["LLM_MODEL_ID"], "remote-model")
        self.assertEqual(remote["LLM_API_KEY"], "remote-secret")
        self.assertEqual(remote["LLM_ENABLE_THINKING"], "")
        self.assertEqual(remote["LLM_HEALTHCHECK"], "auto")
        # 归一化可重复执行；父 Shell 与多个 Python 子进程不能丢失本地配置。
        inherited = {**env, **remote}
        self.assertEqual(resolve_model_settings(inherited), remote)
        inherited["LLM_MODE"] = "local"
        local = resolve_model_settings(inherited)
        for key in ("LLM_BASE_URL", "LLM_MODEL_ID", "LLM_API_KEY", "LLM_ENABLE_THINKING"):
            self.assertEqual(local[key], env[key])
        self.assertEqual(local["LLM_HEALTHCHECK"], "auto")

    def test_api_requires_own_address_and_model(self):
        env = {"LLM_MODE": "api", "LLM_BASE_URL": "http://localhost:8000/v1",
               "LLM_MODEL_ID": "local-model", "LLM_API_KEY": "local-secret"}
        with self.assertRaisesRegex(ValueError, "LLM_REMOTE_BASE_URL"):
            resolve_model_settings(env)
        env["LLM_REMOTE_BASE_URL"] = "https://example.invalid/v1"
        with self.assertRaisesRegex(ValueError, "LLM_REMOTE_MODEL_ID"):
            resolve_model_settings(env)
        env["LLM_REMOTE_MODEL_ID"] = "remote-model"
        result = resolve_model_settings(env)
        self.assertEqual(result["LLM_API_KEY"], "")  # 不泄漏本地密钥给远程服务
        env["LLM_REMOTE_ENABLE_THINKING"] = "true"
        self.assertEqual(resolve_model_settings(env)["LLM_ENABLE_THINKING"], "true")

    def test_invalid_mode_healthcheck_and_api_url(self):
        for env in ({"LLM_MODE": "other"}, {"LLM_HEALTHCHECK": "other"}):
            with self.assertRaises(ValueError):
                resolve_model_settings(env)
        for url in ("file:///tmp/model", "https://host/v1/chat/completions",
                    "https://secret@host/v1", "https://host/v1?api_key=secret"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                resolve_model_settings({"LLM_MODE": "api", "LLM_REMOTE_BASE_URL": url,
                                        "LLM_REMOTE_MODEL_ID": "remote-model"})
        with self.assertRaises(ValueError):
            resolve_model_settings({"LLM_MODE": "api", "LLM_REMOTE_BASE_URL": "https://host/v1",
                                    "LLM_REMOTE_MODEL_ID": "model\ninjected=1"})
        # 未启用的 API 配置不影响本地模式。
        self.assertEqual(resolve_model_settings({"LLM_REMOTE_BASE_URL": "not-a-url"})["LLM_MODE"], "local")

    def test_response_format_policy_is_api_only_and_validated(self):
        env = {"LLM_MODE": "api", "LLM_REMOTE_BASE_URL": "https://example.invalid/v1",
               "LLM_REMOTE_MODEL_ID": "remote-model"}
        self.assertEqual(resolve_model_settings(env)["LLM_RESPONSE_FORMAT"], "json_schema")
        for mode in ("json_schema", "json_object", "none"):
            with self.subTest(mode=mode):
                result = resolve_model_settings(dict(env, LLM_REMOTE_RESPONSE_FORMAT=mode))
                self.assertEqual(result["LLM_RESPONSE_FORMAT"], mode)
                local = resolve_model_settings({**env, **result, "LLM_MODE": "local"})
                self.assertEqual(local["LLM_RESPONSE_FORMAT"], "json_schema")
        with self.assertRaisesRegex(ValueError, "LLM_REMOTE_RESPONSE_FORMAT"):
            resolve_model_settings(dict(env, LLM_REMOTE_RESPONSE_FORMAT="invalid"))
        self.assertEqual(resolve_model_settings({"LLM_REMOTE_RESPONSE_FORMAT": "invalid"})["LLM_RESPONSE_FORMAT"], "json_schema")

    def test_api_preview_hides_both_keys_and_overrides_file_mode(self):
        env = dict(os.environ, LLM_MODE="local", CONFIG_PYTHON_BIN=sys.executable,
                   LLM_API_KEY="local-preview-secret", LLM_REMOTE_API_KEY="remote-preview-secret",
                   LLM_REMOTE_BASE_URL="https://example.invalid/v1", LLM_REMOTE_MODEL_ID="remote-model")
        result = subprocess.run([str(ROOT / "scripts/start_all.sh"), "api", "--show-config"],
                                cwd=ROOT, env=env, capture_output=True, text=True, check=True)
        fields = dict(line.split("=", 1) for line in result.stdout.splitlines())
        self.assertEqual(fields["LLM_MODE"], "api")
        self.assertEqual(fields["LLM_MODEL_ID"], "remote-model")
        self.assertEqual(fields["LLM_BASE_URL"], env["LLM_REMOTE_BASE_URL"])
        for secret in (env["LLM_API_KEY"], env["LLM_REMOTE_API_KEY"]):
            self.assertNotIn(secret, result.stdout + result.stderr)
        self.assertFalse(any(key.endswith("_API_KEY") for key in fields))

    def test_api_healthcheck_can_skip_or_require_models(self):
        class Handler(BaseHTTPRequestHandler):
            requests = []

            def do_GET(self):
                self.requests.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"data": [{"id": "actual-model"}]}')

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            env = dict(os.environ, LLM_MODE="api", LLM_HEALTHCHECK="auto",
                       LLM_BASE_URL=f"http://127.0.0.1:{server.server_port}/v1",
                       LLM_MODEL_ID="wrong-model", NO_PROXY="127.0.0.1,localhost",
                       no_proxy="127.0.0.1,localhost")
            command = [sys.executable, "-B", str(ROOT / "scripts/check_model_endpoint.py")]
            result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, check=True)
            self.assertIn("跳过", result.stdout)
            self.assertEqual(Handler.requests, [])
            env["LLM_HEALTHCHECK"] = "models"
            result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(Handler.requests, ["/v1/models"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_api_never_starts_local_model_even_with_forced_start(self):
        cache = ROOT / ".runtime-cache"
        cache.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as directory:
            base = Path(directory)
            marker = base / "model-started"
            engine = base / "model.sh"
            engine.write_text(f'#!/bin/bash\necho started > "{marker}"\nexit 9\n')
            engine.chmod(0o755)
            worker = base / "worker.sh"
            worker.write_text('#!/bin/bash\nexit 0\n')
            worker.chmod(0o755)
            env = dict(os.environ, CONFIG_PYTHON_BIN=sys.executable,
                       LLM_REMOTE_BASE_URL="http://127.0.0.1:1/v1", LLM_REMOTE_MODEL_ID="api-model",
                       LLM_HEALTHCHECK="auto", START_VLLM="1", START_SGLANG="1",
                       VLLM_START_SCRIPT=str(engine), SGLANG_START_SCRIPT=str(engine),
                       REPORT_START_SCRIPT=str(worker), AGENT_START_SCRIPT=str(worker),
                       SERVICE_STACK_RUNTIME_DIR=str(base / "logs"),
                       AGENT_READY_URL="http://127.0.0.1:1/ready")
            result = subprocess.run([str(ROOT / "scripts/start_all.sh"), "api"], cwd=ROOT,
                                    env=env, capture_output=True, text=True, timeout=10)
            # 假 Worker 会立即退出；只检查启动流程已越过模型阶段且未启动本地引擎。
            self.assertIn("正在启动报告 Worker", result.stdout)
            self.assertIn("跳过 /models", result.stdout)
            self.assertFalse(marker.exists())

    def test_model_mismatch_stops_before_starting_services(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"data": [{"id": "actual-model"}]}).encode())

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            env = dict(os.environ, LLM_BASE_URL=f"http://127.0.0.1:{server.server_port}/v1",
                       LLM_MODEL_ID="wrong-model", NO_PROXY="127.0.0.1,localhost",
                       no_proxy="127.0.0.1,localhost")
            command = 'source scripts/load_env.sh; load_env_defaults .env; if model_endpoint_ready; then echo READY; else echo WOULD_START; fi'
            result = subprocess.run(["bash", "-c", command], cwd=ROOT, env=env,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertIn("actual-model", result.stderr)
            self.assertIn("wrong-model", result.stderr)
            self.assertEqual(result.stdout, "")
            env["LLM_MODEL_ID"] = "actual-model"
            result = subprocess.run(["bash", "-c", command], cwd=ROOT, env=env,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), "READY")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
