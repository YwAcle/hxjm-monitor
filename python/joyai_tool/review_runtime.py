"""Load the worktree's Qwen only while queued clips need a verdict."""
from pathlib import Path
import subprocess
import threading
import time
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

from .verdict import VisionReviewer


class OnDemandReviewer:
    def __init__(self, config, stop_event):
        endpoint = urlsplit(config['review_url'])
        if endpoint.scheme != 'http' or endpoint.hostname != '127.0.0.1' or endpoint.path != '/v1':
            raise ValueError('按需复核必须使用本目录的本机 Qwen 接口')
        self.root = Path(__file__).resolve().parents[2]
        self.health_url = f'{endpoint.scheme}://{endpoint.netloc}/health'
        self.stop_event = stop_event
        self.timeout = config.get('review_start_timeout', 1200)
        self.reviewer = VisionReviewer(config['review_url'], config['review_model'],
            config.get('review_api_key', ''), timeout=120, max_tokens=1800)
        self.lock = threading.Lock()
        self.state = 'stopped'
        self.error = None
        self.owned = False

    def status(self):
        with self.lock:
            return {'mode': 'on_demand', 'state': self.state, 'last_error': self.error}

    def update(self, state, error=None):
        with self.lock:
            self.state, self.error = state, error

    def command(self, action):
        result = subprocess.run(['bash', str(self.root / 'scripts/joyai-tool.sh'), action],
            cwd=self.root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError('复核模型启停失败，请检查本目录 joyai_qwen.log 及端口占用')

    def healthy(self):
        try:
            with urlopen(self.health_url, timeout=2) as response:
                return response.status == 200
        except (OSError, URLError):
            return False

    def alive(self):
        result = subprocess.run(['python3', str(self.root / 'scripts/local-runtime.py'),
            '--root', str(self.root), '--state', str(self.root / '.run/local-runtime'),
            'status', 'joyai_qwen'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        return result.returncode == 0

    def ensure_ready(self):
        if self.stop_event.is_set():
            raise RuntimeError('监控正在停止，片段保留等待下次复核')
        if self.owned and self.healthy():
            return
        self.update('starting')
        # Mark ownership before launch so even a lost startup response is cleaned up.
        self.owned = True
        try:
            self.command('review-start')
            deadline = time.monotonic() + self.timeout
            while not self.stop_event.is_set():
                if self.healthy():
                    self.update('ready')
                    return
                if not self.alive():
                    raise RuntimeError('复核模型进程启动失败，片段保留；请检查 joyai_qwen.log')
                if time.monotonic() >= deadline:
                    raise RuntimeError('复核模型加载超时，片段保留等待重试')
                self.stop_event.wait(1)
            raise RuntimeError('监控正在停止，已取消复核模型加载')
        except Exception as exc:
            try:
                self.release()
            finally:
                self.update('error', str(exc))
            raise

    def review(self, kind, frames, evidence):
        self.ensure_ready()
        self.update('reviewing')
        try:
            return self.reviewer.review(kind, frames, evidence)
        finally:
            self.update('ready')

    def release(self):
        if not self.owned:
            return
        self.update('releasing')
        try:
            self.command('review-stop')
        except Exception as exc:
            self.update('error', str(exc))
            raise
        self.owned = False
        self.update('stopped')
