"""Own one repository-specific tmux session; never stop processes by port."""

import fcntl
import hashlib
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / '.runtime-cache/launcher'
SOCKET = 'hxjm-agent-' + hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]
TMUX = ['tmux', '-L', SOCKET]
SESSION = 'services'


def running():
    return subprocess.run(TMUX + ['has-session', '-t', '=' + SESSION],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def main():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    # Start/stop serialize within this checkout; separate checkouts have separate sockets.
    with (RUNTIME / 'lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('另一个启动/停止操作正在执行，请稍后重试。')
        if sys.argv[1] == 'stop':
            if not running():
                print('本入口没有正在运行的服务。')
                return
            pid = int(subprocess.check_output(TMUX + ['display-message', '-p', '-t',
                                                      SESSION + ':stack', '#{pane_pid}']))
            # The supervisor handles TERM and cleans up only the children it started.
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            deadline = time.monotonic() + 30
            while running() and time.monotonic() < deadline:
                time.sleep(0.2)
            if running():
                raise SystemExit('停止超时，请检查 launcher/stack.log；未强制终止其他服务。')
            print('已停止本入口创建的服务；复用的模型服务保持运行。')
            return
        if running():
            print('服务已由本入口启动；重复启动不会创建新进程。')
            print('日志：' + str(RUNTIME / 'stack.log'))
            return
        ready = RUNTIME / 'ready'
        ready.unlink(missing_ok=True)
        command = 'exec bash {} >> {} 2>&1'.format(
            shlex.quote(str(ROOT / 'scripts/internal/run_stack.sh')),
            shlex.quote(str(RUNTIME / 'stack.log')))
        os.environ['AGENT_LAUNCH_READY_FILE'] = str(ready)
        # A new server inherits the invoking shell's exported .env and overrides.
        # It exits with its only session; no shared tmux server state is modified.
        subprocess.run(TMUX + ['-f', '/dev/null', 'new-session', '-d', '-s', SESSION,
                              '-n', 'stack', '-c', str(ROOT), command], check=True)
        timeout = int(os.environ.get('VLLM_STARTUP_TIMEOUT_S', '300'))
        timeout = max(timeout, int(os.environ.get('SGLANG_STARTUP_TIMEOUT_S', '300')))
        timeout += int(os.environ.get('AGENT_STARTUP_TIMEOUT_S', '360')) + 30
        deadline = time.monotonic() + timeout
        print('服务后台启动中，日志：' + str(RUNTIME / 'stack.log'), flush=True)
        while time.monotonic() < deadline:
            if not running():
                raise SystemExit('服务启动失败，请查看 ' + str(RUNTIME / 'stack.log'))
            if ready.exists():
                print(ready.read_text().strip())
                return
            time.sleep(0.5)
        raise SystemExit('等待启动超时，后台服务状态请查看 ' + str(RUNTIME / 'stack.log'))


if __name__ == '__main__':
    main()
