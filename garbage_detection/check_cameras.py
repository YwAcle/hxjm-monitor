"""Read local camera settings and check connectivity without printing credentials."""
import concurrent.futures
import argparse
import json
import re
import shlex
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit


def settings():
    values = {}
    for line in (Path(__file__).resolve().parent / ".env").read_text().splitlines():
        parts = shlex.split(line, comments=True)
        if parts and "=" in parts[0]:
            key, value = parts[0].split("=", 1)
            values[key] = value
    return values


def check(item, timeout=15, video=False, transport="udp", seconds=10):
    index, url = item
    parsed = urlsplit(url)
    result = {"camera": index, "host": parsed.hostname, "port": parsed.port or 554}
    if not parsed.hostname:
        return dict(result, error="未配置摄像头地址")
    started = time.monotonic()
    try:
        with socket.create_connection((parsed.hostname, result["port"]), timeout=timeout) as connection:
            result["tcp"] = "connected"
            connection.settimeout(timeout)
            target = f"rtsp://{parsed.hostname}:{result['port']}{parsed.path}"
            connection.sendall(f"OPTIONS {target} RTSP/1.0\r\nCSeq: 1\r\n\r\n".encode())
            response = connection.recv(4096).split(b"\r\n", 1)[0].decode(errors="replace")
            result["rtsp"] = response
    except OSError as exc:
        result.update(error=type(exc).__name__, detail=str(exc))
    result["seconds"] = round(time.monotonic() - started, 2)
    if result.get("tcp") == "connected" and video:
        help_text = subprocess.run(["ffmpeg", "-hide_banner", "-h", "demuxer=rtsp"],
                                   capture_output=True, text=True, timeout=5).stdout
        timeout_option = "-stimeout" if "-stimeout " in help_text else "-timeout"
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostats",
                   "-rtsp_transport", transport, timeout_option, str(int(timeout * 1_000_000)),
                   "-analyzeduration", "1000000", "-probesize", "262144", "-threads", "1", "-i", url,
                   "-map", "0:v:0", "-an", "-t", str(seconds), "-vsync", "0", "-progress", "pipe:1", "-f", "null", "-"]
        try:
            video = subprocess.run(command, capture_output=True, timeout=2 * timeout + seconds + 10)
            frames = [int(line.split("=", 1)[1]) for line in video.stdout.decode(errors="replace").splitlines()
                      if line.startswith("frame=")]
            result["video"] = {"exit_code": video.returncode, "frames": max(frames, default=0),
                               "error_lines": len(video.stderr.splitlines()),
                               "errors": re.sub(r"rtsp://\S+", "<RTSP地址>", video.stderr.decode(errors="replace")).splitlines()[:3]}
        except subprocess.TimeoutExpired:
            result["video"] = {"error": "视频解码超时"}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", action="store_true", help="尝试实际视频解码（需要 ffmpeg）")
    parser.add_argument("--timeout", type=float, default=15, help="网络超时秒数，默认 15")
    parser.add_argument("--transport", choices=("tcp", "udp"), help="默认使用 .env 中的传输方式")
    parser.add_argument("--substream", action="store_true", help="测试 102 子码流，保持 .env 不变")
    parser.add_argument("--seconds", type=int, default=10, help="视频测试时长")
    args = parser.parse_args()
    if not 0 < args.timeout <= 60 or not 1 <= args.seconds <= 120:
        parser.error("timeout 必须在 0～60 秒之间，seconds 必须在 1～120 秒之间")
    config = settings()
    transport = args.transport or config.get("GARBAGE_RTSP_TRANSPORT", "udp")
    cameras = [(i, config.get(f"GARBAGE_RTSP_URL_{i}", "")) for i in range(1, 5)]
    if args.substream:
        cameras = [(i, url.replace("/Channels/101", "/Channels/102")) for i, url in cameras]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(lambda item: check(item, args.timeout, args.video, transport, args.seconds), cameras):
            print(json.dumps(result, ensure_ascii=False), flush=True)
