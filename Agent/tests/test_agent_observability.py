"""第三天上午的追踪、日志和请求限制测试。"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

from PIL import Image

from llm_agent_service.app import create_app
from llm_agent_service.config import DbConfig, ServiceConfig


def _image_base64(*, size: tuple[int, int] = (24, 16), image_format: str = "PNG") -> str:
    output = BytesIO()
    Image.new("RGB", size, (30, 60, 90)).save(output, format=image_format)
    return base64.b64encode(output.getvalue()).decode("ascii")


class AgentMorningApiTests(unittest.TestCase):
    def test_jsonl_contains_complete_events_and_appends_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "agent.jsonl"
            env = dict(os.environ, AGENT_JSONL_LOG=str(path), LOG_WRITE_MODE="append",
                       AGENT_JSONL_WRITE_MODE="append")
            command = [sys.executable, "-c", (
                "from llm_agent_service.observability import emit_event; "
                "print('plain startup message'); "
                "emit_event('request_end', trace_id='test-jsonl', "
                "response_text='完整回复\\n' * 1000, result={'items': [{'id': 1}]})"
            )]
            for _ in range(2):
                subprocess.run(command, env=env, check=True, capture_output=True,
                               cwd=Path(__file__).resolve().parents[1])
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            for line in lines:
                record = json.loads(line)
                self.assertEqual(record["event"], "request_end")
                self.assertEqual(record["response_text"], "完整回复\n" * 1000)
                self.assertEqual(record["result"], {"items": [{"id": 1}]})

    def test_jsonl_write_mode_and_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent.jsonl"
            for global_mode, override, expected_lines in (
                ("append", None, 2), ("overwrite", None, 1),
                ("overwrite", "append", 2), ("append", "overwrite", 1),
            ):
                with self.subTest(global_mode=global_mode, override=override):
                    path.write_text('{"event":"old"}\n', encoding="utf-8")
                    env = dict(os.environ, AGENT_JSONL_LOG=str(path), LOG_WRITE_MODE=global_mode)
                    # Explicit values isolate this subprocess from local .env overrides.
                    env["AGENT_JSONL_WRITE_MODE"] = override or global_mode
                    subprocess.run([sys.executable, "-c",
                                    "from llm_agent_service.observability import emit_event; emit_event('new')"],
                                   env=env, check=True, capture_output=True,
                                   cwd=Path(__file__).resolve().parents[1])
                    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
                    self.assertEqual(len(records), expected_lines)
                    self.assertEqual(records[-1]["event"], "new")

    def test_shell_log_modes_and_invalid_mode_preserve_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent.log"
            root = Path(__file__).resolve().parents[1]
            command = ["bash", "-c",
                       'source "$1"; prepare_log_file "$2" "$3" || exit $?; printf "new\\n" >>"$2"',
                       "bash", str(root / "scripts/logging.sh"), str(path)]
            for mode, expected in (("append", "old\nnew\n"), ("overwrite", "new\n")):
                path.write_text("old\n")
                subprocess.run([*command, mode], check=True, capture_output=True)
                self.assertEqual(path.read_text(), expected)
            path.write_text("old\n")
            result = subprocess.run([*command, "invalid"], capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(path.read_text(), "old\n")

    def _client(self, config: ServiceConfig | None = None):
        reid_service = MagicMock()
        agent_service = MagicMock()
        agent_service.process.return_value = {"type": "agent", "text": "完成"}
        with patch("llm_agent_service.app.ReidService", return_value=reid_service), patch(
            "llm_agent_service.app.AgentService", return_value=agent_service
        ):
            app = create_app(
                engine=MagicMock(),
                db_cfg=DbConfig("localhost", 5432, "user", "password", "db"),
                svc_cfg=config or ServiceConfig(),
                llm=MagicMock(),
            )
        return app.test_client(), agent_service

    def test_generated_trace_id_is_returned_in_body_and_header(self) -> None:
        client, agent_service = self._client()

        first = client.post("/chat", json={"prompt": "你好", "session_id": "session-1"})
        second = client.post("/chat", json={"prompt": "你好", "session_id": "session-1"})

        first_trace_id = first.get_json()["trace_id"]
        second_trace_id = second.get_json()["trace_id"]
        self.assertRegex(first_trace_id, r"^[a-f0-9]{32}$")
        self.assertNotEqual(first_trace_id, second_trace_id)
        self.assertEqual(first.headers["X-Trace-ID"], first_trace_id)
        self.assertEqual(
            agent_service.process.call_args_list[0].kwargs["trace_id"],
            first_trace_id,
        )

    def test_trace_id_can_be_supplied_by_header(self) -> None:
        client, agent_service = self._client()

        response = client.post(
            "/chat",
            json={"prompt": "你好", "session_id": "session-1"},
            headers={"X-Trace-ID": "frontend-trace-1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["trace_id"], "frontend-trace-1")
        self.assertEqual(
            agent_service.process.call_args.kwargs["trace_id"],
            "frontend-trace-1",
        )

    def test_invalid_trace_id_is_rejected(self) -> None:
        client, agent_service = self._client()

        response = client.post(
            "/chat",
            json={"prompt": "你好", "trace_id": "包含 空格"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error_code"], "INVALID_TRACE_ID")
        agent_service.process.assert_not_called()

    def test_prompt_length_limit_is_enforced(self) -> None:
        client, agent_service = self._client(ServiceConfig(max_prompt_chars=4))

        response = client.post("/chat", json={"prompt": "12345"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error_code"], "PROMPT_TOO_LONG")
        agent_service.process.assert_not_called()

    def test_request_body_limit_is_enforced(self) -> None:
        client, agent_service = self._client(ServiceConfig(max_request_bytes=32))

        response = client.post("/chat", json={"prompt": "x" * 100})

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.get_json()["error_code"], "REQUEST_TOO_LARGE")
        agent_service.process.assert_not_called()

    def test_image_byte_limit_is_enforced(self) -> None:
        client, agent_service = self._client(ServiceConfig(max_image_bytes=10))

        response = client.post(
            "/chat",
            json={"prompt": "描述图片", "image": _image_base64()},
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.get_json()["error_code"], "IMAGE_TOO_LARGE")
        agent_service.process.assert_not_called()

    def test_image_dimension_limit_is_enforced(self) -> None:
        client, agent_service = self._client(ServiceConfig(max_image_side=20))

        response = client.post(
            "/chat",
            json={"prompt": "描述图片", "image": _image_base64(size=(24, 16))},
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(
            response.get_json()["error_code"],
            "IMAGE_DIMENSIONS_TOO_LARGE",
        )
        agent_service.process.assert_not_called()

    def test_image_pixel_limit_is_enforced(self) -> None:
        client, agent_service = self._client(
            ServiceConfig(max_image_side=100, max_image_pixels=30)
        )

        response = client.post(
            "/chat",
            json={"prompt": "描述图片", "image": _image_base64(size=(6, 6))},
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(
            response.get_json()["error_code"],
            "IMAGE_DIMENSIONS_TOO_LARGE",
        )
        agent_service.process.assert_not_called()

    def test_unsupported_image_format_is_rejected(self) -> None:
        client, agent_service = self._client()

        response = client.post(
            "/chat",
            json={"prompt": "描述图片", "image": _image_base64(image_format="BMP")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error_code"],
            "UNSUPPORTED_IMAGE_FORMAT",
        )
        agent_service.process.assert_not_called()

    def test_structured_logs_do_not_contain_image_base64(self) -> None:
        client, _agent_service = self._client()
        encoded_image = _image_base64()

        with self.assertLogs("llm_agent_service.events", level="INFO") as captured:
            response = client.post(
                "/chat",
                json={"prompt": "描述图片", "image": encoded_image},
            )

        self.assertEqual(response.status_code, 200)
        log_text = "\n".join(captured.output)
        self.assertNotIn(encoded_image, log_text)
        records = [json.loads(line.split(":", 2)[-1]) for line in captured.output]
        self.assertEqual(records[0]["event"], "request_start")
        self.assertEqual(records[0]["prompt"], "描述图片")
        self.assertEqual(records[-1]["event"], "request_end")

    def test_full_multiline_prompt_is_logged_for_chat_and_stream(self) -> None:
        prompt = "查询今天的异常\n" + "完整提示词" * 1000
        for path in ("/chat", "/chat/stream"):
            with self.subTest(path=path):
                client, service = self._client()
                service.stream.return_value = iter([])
                with self.assertLogs("llm_agent_service.events", level="INFO") as captured:
                    response = client.post(path, json={"prompt": prompt})
                    response.get_data()
                self.assertEqual(response.status_code, 200)
                records = [json.loads(record.getMessage()) for record in captured.records]
                start = next(record for record in records if record["event"] == "request_start")
                self.assertEqual(start["prompt"], prompt)

    def test_exception_details_are_not_written_to_logs_or_response(self) -> None:
        client, agent_service = self._client()
        secret = "password=highly-sensitive"
        agent_service.process.side_effect = RuntimeError(secret)

        with self.assertLogs("llm_agent_service.events", level="INFO") as captured:
            response = client.post("/chat", json={"prompt": "你好"})

        self.assertEqual(response.status_code, 500)
        response_text = response.get_data(as_text=True)
        log_text = "\n".join(captured.output)
        self.assertNotIn(secret, response_text)
        self.assertNotIn(secret, log_text)
        self.assertEqual(response.get_json()["error_code"], "INTERNAL_ERROR")

    def test_final_response_text_is_logged_without_truncation(self) -> None:
        client, service = self._client()
        answer = "完整回复\n" * 1000
        service.process.return_value = {"type": "agent", "text": answer}
        with self.assertLogs("llm_agent_service.events", level="INFO") as captured:
            response = client.post("/chat", json={"prompt": "你好"})
        records = [json.loads(record.getMessage()) for record in captured.records]
        self.assertEqual(records[-1]["response_text"], response.get_json()["text"])
        self.assertEqual(records[-1]["response_text"], answer)

    def test_stream_logs_actual_deltas_and_partial_text_on_error(self) -> None:
        for failed in (False, True):
            with self.subTest(failed=failed):
                client, service = self._client()
                def stream(*args, **kwargs):
                    yield {"event": "delta", "data": {"text": "实际流式"}}
                    yield {"event": "delta", "data": {"text": "回复\n"}}
                    if failed:
                        raise RuntimeError("internal detail")
                    yield {"event": "done", "data": {"finish_reason": "final"}}
                service.stream.side_effect = stream
                with self.assertLogs("llm_agent_service.events", level="INFO") as captured:
                    client.post("/chat/stream", json={"prompt": "你好"}).get_data()
                records = [json.loads(record.getMessage()) for record in captured.records]
                end = records[-1]
                self.assertEqual(end["response_text"], "实际流式回复\n")
                self.assertEqual(end["response_chars"], len(end["response_text"]))
                self.assertEqual(end["status"], "error" if failed else "success")


if __name__ == "__main__":
    unittest.main()
