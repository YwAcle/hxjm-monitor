"""Exercise port reuse and ownership without GPU or real business requests."""
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[2] / "apps/llm"


class Handler(BaseHTTPRequestHandler):
    status = 200

    def do_GET(self):
        self.send_response(self.status)
        self.end_headers()
        self.wfile.write(json.dumps({'data': [{'id': 'launcher-test'}]}).encode())

    def log_message(self, *args):
        pass


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def script(self, name, body):
        p = self.base / name
        p.write_text('#!/bin/bash\n' + body)
        p.chmod(0o755)
        return p

    def server(self, status=200):
        handler = type('TestHandler', (Handler,), {'status': status})
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def env(self, server):
        worker = self.script('worker.sh', 'exec sleep 60\n')
        model = self.script('model.sh', 'touch "' + str(self.base / 'model-started') + '"\nexit 9\n')
        url = f'http://127.0.0.1:{server.server_port}'
        return dict(os.environ, CONFIG_PYTHON_BIN=sys.executable, LLM_MODE='local',
                    LLM_BACKEND='vllm', LLM_MODEL_ID='launcher-test', LLM_HEALTHCHECK='models',
                    LLM_BASE_URL=url + '/v1', VLLM_START_SCRIPT=str(model),
                    REPORT_START_SCRIPT=str(worker), AGENT_START_SCRIPT=str(worker),
                    SERVICE_STACK_RUNTIME_DIR=str(self.base / 'logs'),
                    AGENT_PORT='0',
                    AGENT_READY_URL=url + '/ready', VLLM_STARTUP_TIMEOUT_S='0',
                    AGENT_LAUNCH_READY_FILE=str(self.base / 'ready'))

    def test_reuses_existing_model_and_stops_only_owned_children(self):
        server = self.server()
        env = self.env(server)
        proc = subprocess.Popen(['bash', str(ROOT / 'scripts/internal/run_stack.sh')],
                                cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True)
        try:
            deadline = time.monotonic() + 12
            while not (self.base / 'ready').exists() and proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue((self.base / 'ready').exists())
            self.assertFalse((self.base / 'model-started').exists())
        finally:
            proc.send_signal(signal.SIGTERM)
            output, _ = proc.communicate(timeout=10)
        self.assertIn('模型接口已配置', output)
        self.assertFalse((self.base / 'ready').exists())
        # The externally supplied model listener is untouched by cleanup.
        self.assertGreater(server.fileno(), 0)
        import urllib.request
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                f'http://127.0.0.1:{server.server_port}/v1/models') as response:
            self.assertEqual(response.status, 200)

    def test_occupied_unready_port_never_starts_second_engine(self):
        server = self.server(503)
        result = subprocess.run(['bash', str(ROOT / 'scripts/internal/run_stack.sh')],
                                cwd=ROOT, env=self.env(server), capture_output=True, text=True, timeout=12)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('端口已占用', result.stdout)
        self.assertFalse((self.base / 'model-started').exists())
        self.assertFalse((self.base / 'ready').exists())

    @unittest.skipUnless(shutil.which('tmux'), 'tmux unavailable')
    def test_background_start_duplicate_start_and_stop(self):
        # A private directory gives the test its own tmux socket and runtime files.
        root = self.base / 'Agent'
        internal = root / 'scripts/internal'
        internal.mkdir(parents=True)
        shutil.copy(ROOT / 'scripts/internal/manage.py', internal / 'manage.py')
        supervisor = internal / 'run_stack.sh'
        supervisor.write_text('''#!/bin/bash
set -eu
trap 'rm -f "$AGENT_LAUNCH_READY_FILE"; exit 0' TERM HUP
printf 'test ready\\n' > "$AGENT_LAUNCH_READY_FILE"
while true; do sleep 0.1; done
''')
        command = [sys.executable, str(internal / 'manage.py')]
        def run(action):
            return subprocess.run(command + [action], cwd=ROOT, capture_output=True,
                                  text=True, timeout=15)
        try:
            result = run('start')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('test ready', result.stdout)
            result = run('start')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('重复启动', result.stdout)
            result = run('stop')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse((root / '.runtime-cache/launcher/ready').exists())
            self.assertEqual(run('stop').returncode, 0)
        finally:
            run('stop')

    def test_existing_agent_is_not_mistaken_for_successful_start(self):
        server = self.server()
        env = self.env(server)
        env['AGENT_PORT'] = str(server.server_port)
        result = subprocess.run(['bash', str(ROOT / 'scripts/internal/run_stack.sh')],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=12)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Agent 端口', result.stderr)
        self.assertFalse((self.base / 'ready').exists())

    def test_owned_model_process_group_is_stopped(self):
        ready_server = self.server()
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        model = self.base / 'fake_model.py'
        model.write_text('''from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"data":[{"id":"launcher-test"}]}')
    def log_message(self, *args): pass
HTTPServer(('127.0.0.1', ''' + str(port) + '''), Handler).serve_forever()
''')
        engine = self.script('engine.sh', f'exec "{sys.executable}" "{model}"\n')
        env = self.env(ready_server)
        env.update(LLM_BASE_URL=f'http://127.0.0.1:{port}/v1',
                   VLLM_START_SCRIPT=str(engine), VLLM_STARTUP_TIMEOUT_S='10')
        proc = subprocess.Popen(['bash', str(ROOT / 'scripts/internal/run_stack.sh')],
                                cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True)
        try:
            deadline = time.monotonic() + 12
            while not (self.base / 'ready').exists() and proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue((self.base / 'ready').exists())
        finally:
            proc.send_signal(signal.SIGTERM)
            output, _ = proc.communicate(timeout=10)
        self.assertIn('vllm 启动成功', output)
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', port), timeout=1)
