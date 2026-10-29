"""Start and stop only this directory's background server (Linux)."""
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / ".runtime"
PID_FILE = RUNTIME / "service.json"
LOG_FILE = RUNTIME / "service.log"


def show_addresses(port):
    print(f"局域网：http://192.168.109.191:{port}/")
    print(f"Tailscale：http://100.127.237.7:{port}/（需连接 Tailscale）")
    print(f"本机：http://localhost:{port}/")
    print("自动入口：打开网页，点击“保存自动访问入口”，将文件保存到自己的电脑，以后双击即可自动选择地址。")


def identity(pid):
    try:
        proc = Path(f"/proc/{pid}")
        stat = (proc / "stat").read_text().rsplit(")", 1)[1].split()
        args = (proc / "cmdline").read_bytes().split(b"\0")
        if (stat[0] == "Z" or os.fsencode(str(ROOT / "server.py")) not in args
                or (proc / "cwd").resolve() != ROOT):
            return None
        return {"pid": pid, "start_ticks": stat[19]}
    except (OSError, IndexError, ValueError):
        return None


def recover_process():
    matches = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if proc.stat().st_uid != os.getuid():
                continue
        except OSError:
            continue
        record = identity(int(proc.name))
        if record:
            matches.append(record)
    if len(matches) > 1:
        raise RuntimeError("发现多个本目录服务进程，无法自动恢复记录，请先核对进程。")
    return matches[0] if matches else None


def managed_process():
    try:
        record = json.loads(PID_FILE.read_text())
        if type(record["pid"]) is int and record["pid"] > 1 and identity(record["pid"]) == record:
            return record
    except (OSError, ValueError, KeyError, TypeError):
        pass
    # Recover a surviving server only after checking its script, cwd, owner and start time.
    record = recover_process()
    if record:
        PID_FILE.write_text(json.dumps(record))
    return record


def stop_process(record):
    # A pidfd pins the process, so an expired PID can never target a replacement process.
    try:
        fd = os.pidfd_open(record["pid"])
    except ProcessLookupError:
        return
    try:
        if identity(record["pid"]) != record:
            return
        signal.pidfd_send_signal(fd, signal.SIGTERM)
        deadline = time.monotonic() + 10
        while identity(record["pid"]) == record and time.monotonic() < deadline:
            time.sleep(0.1)
        if identity(record["pid"]) == record:
            signal.pidfd_send_signal(fd, signal.SIGKILL)
            deadline = time.monotonic() + 5
            while identity(record["pid"]) == record and time.monotonic() < deadline:
                time.sleep(0.1)
        if identity(record["pid"]) == record:
            raise RuntimeError("服务尚未退出，请查看 .runtime/service.log。")
    except ProcessLookupError:
        pass
    finally:
        os.close(fd)


def start():
    existing = managed_process()
    if existing:
        print(f"垃圾检测服务已在运行（PID {existing['pid']}），无需重复启动。")
        show_addresses(int(os.getenv('GARBAGE_PORT', '23071')))
        return
    PID_FILE.unlink(missing_ok=True)
    port = int(os.getenv("GARBAGE_PORT", "23071"))
    host = os.getenv("GARBAGE_HOST", "0.0.0.0")
    host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(host, host)
    host = f"[{host}]" if ":" in host else host
    opener = build_opener(ProxyHandler({}))
    with LOG_FILE.open("ab") as log:
        process = subprocess.Popen([os.getenv("GARBAGE_PYTHON", "/home/guest/anaconda3/envs/reid/bin/python"),
                                    "-B", str(ROOT / "server.py")],
                                   cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
    record = identity(process.pid)
    if record is None:
        process.wait(timeout=5)
        raise RuntimeError(f"服务启动失败，请查看 {LOG_FILE}")
    PID_FILE.write_text(json.dumps(record))
    deadline = time.monotonic() + 20
    while process.poll() is None and time.monotonic() < deadline:
        try:
            with opener.open(f"http://{host}:{port}/api/state", timeout=1) as response:
                if json.load(response).get("pid") == process.pid:
                    print(f"垃圾检测服务已后台启动（PID {process.pid}）。")
                    show_addresses(port)
                    print(f"日志：{LOG_FILE}\n停止：bash {ROOT / 'stop.sh'}")
                    return
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    stop_process(record)
    process.wait(timeout=5)
    PID_FILE.unlink(missing_ok=True)
    raise RuntimeError(f"服务启动失败或超时，请查看 {LOG_FILE}；端口 {port} 可能已被其他服务占用。")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("start", "stop"):
        raise SystemExit("用法：python3 manage.py start|stop")
    RUNTIME.mkdir(exist_ok=True)
    with (RUNTIME / "service.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("已有启动或停止操作正在执行，请稍后重试。") from None
        try:
            if sys.argv[1] == "start":
                start()
            else:
                record = managed_process()
                if record:
                    stop_process(record)
                    print("垃圾检测服务已停止，网页、摄像头拉流和模型推理均已关闭。")
                else:
                    print("垃圾检测服务未运行，无需重复停止。")
                PID_FILE.unlink(missing_ok=True)
        except (OSError, RuntimeError) as exc:
            raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
