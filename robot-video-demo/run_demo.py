"""One command starts MediaMTX, source/bridge, and the WebRTC dashboard."""
import argparse
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import uvicorn
from settings import Settings
from web_server import create_app
from source_diagnostics import SourceStatus, read_source_status

ROOT = Path(__file__).resolve().parent


def resolve_tool(name, override=None):
    local = ROOT / ".runtime" / (name + (".exe" if os.name == "nt" else ""))
    found = override or (str(local) if local.exists() else shutil.which(name))
    if not found or shutil.which(str(found)) is None:
        raise RuntimeError(f"找不到 {name}。先运行 python tools/install_tools.py 或用 --{name} 指定路径")
    return str(found)


def main():
    p = argparse.ArgumentParser(description="机器狗视频完整链路 Demo")
    p.add_argument("--mode", choices=("simulated", "hardware"), default="simulated")
    p.add_argument("--robot-host", default="192.168.126.176")
    p.add_argument("--robot-port", type=int, default=8765)
    p.add_argument("--config", default=str(ROOT / "cameras.json"), help="四路摄像头 JSON 配置文件")
    p.add_argument("--codec", choices=("copy", "h264"), default="copy")
    p.add_argument("--fps", type=int, default=25)
    p.add_argument("--public-host", default="127.0.0.1", help="浏览器和 ICE 可访问的服务器地址，跨机时必须修改")
    p.add_argument("--bind", choices=("127.0.0.1", "0.0.0.0"), default="127.0.0.1")
    for key, default in (("web", 8890), ("rtsp", 28554), ("whep", 28889), ("ice", 28189), ("mock", 28765)):
        p.add_argument(f"--{key}-port", type=int, default=default)
    p.add_argument("--ffmpeg")
    p.add_argument("--mediamtx")
    args = p.parse_args()
    for name in ("public_host", "robot_host"):
        if not re.fullmatch(r"[A-Za-z0-9.-]+", getattr(args, name)):
            p.error(f"{name} 请填写 IPv4 或主机名，不含协议、端口或路径")
    ports = [getattr(args, k + "_port") for k in ("web", "rtsp", "whep", "ice", "mock")]
    if len(set(ports)) != len(ports) or any(not 1 <= n <= 65535 for n in ports + [args.robot_port]):
        p.error("各服务端口须为 1~65535，且不能重复")
    if not 1 <= args.fps <= 60:
        p.error("fps 应为 1~60；实物时请确认厂家帧率")
    settings = Settings(**{key: value for key, value in vars(args).items() if key not in ("ffmpeg", "mediamtx", "config")})
    settings.load_cameras(args.config)
    ffmpeg = resolve_tool("ffmpeg", args.ffmpeg)
    mtx = resolve_tool("mediamtx", args.mediamtx)
    runtime = ROOT / ".runtime"
    logs = runtime / "logs" / str(args.web_port)
    config = runtime / f"mediamtx-{args.web_port}.yml"
    # Don't silently replace an existing project using one of our ports.
    for port, kind in [(args.web_port, socket.SOCK_STREAM), (args.rtsp_port, socket.SOCK_STREAM),
                       (args.whep_port, socket.SOCK_STREAM), (args.ice_port, socket.SOCK_DGRAM)] + ([(args.mock_port, socket.SOCK_STREAM)] if args.mode == "simulated" else []):
        with socket.socket(socket.AF_INET, kind) as probe:
            probe.bind((args.bind, port))
    logs.mkdir(parents=True, exist_ok=True)
    config.write_text(settings.mediamtx_yaml(), encoding="utf-8")
    children, handles = {}, []
    def start(name, cmd):
        handle = (logs / (name + ".log")).open("w", encoding="utf-8")
        handles.append(handle)
        children[name] = subprocess.Popen(cmd, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT,
                                         start_new_session=os.name != "nt",
                                         env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
    try:
        start("mediamtx", [mtx, str(config)])
        if args.mode == "simulated":
            start("mock", [sys.executable, "mock_robot.py", "--port", str(args.mock_port), "--fps", str(args.fps), "--ffmpeg", ffmpeg])
        time.sleep(.5)
        for name, child in children.items():
            if child.poll() is not None:
                raise RuntimeError(f"{name} 启动失败，查看 .runtime/logs/{args.web_port}/{name}.log")
        for camera in settings.cameras:
            if camera.source in ("simulated", "m20"):
                SourceStatus(logs / f"{camera.id}.json").write("connecting")
                start("bridge_" + camera.id, [sys.executable, "bridge_m20.py", "--camera", camera.camera,
                      "--ws-url", camera.url, "--rtsp-url", settings.target_url(camera),
                      "--fps", str(camera.fps), "--codec", camera.codec, "--ffmpeg", ffmpeg,
                      "--status-file", str(logs / f"{camera.id}.json")])
        def status():
            return {name: {"running": child.poll() is None, "returncode": child.poll(), "pid": child.pid}
                    for name, child in children.items()}
        print(f"模式：{args.mode}；大屏：http://{args.public_host}:{args.web_port}/", flush=True)
        print("子进程存活不代表有视频，请以大屏收到的解码帧为准。Ctrl+C 停止。", flush=True)
        print(f"代码目录：{ROOT}", flush=True)
        print(f"摄像头配置：{Path(args.config).resolve()}", flush=True)
        uvicorn.run(create_app(settings, status, source_status=lambda: read_source_status(settings, logs)),
                    host=args.bind, port=args.web_port)
    finally:
        # Stop bridge first so mock_robot can cleanly terminate its own encoder.
        for name in reversed(children):
            child = children.get(name)
            if child and child.poll() is None:
                if os.name == "nt":
                    # Only the tree rooted at the process started above. This
                    # includes its FFmpeg; never target programs by image name.
                    subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        for handle in handles:
            handle.close()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"启动失败：{exc}", file=sys.stderr)
        raise SystemExit(1)
