"""M20 WebSocket H.264 -> FFmpeg -> MediaMTX RTSP publisher.

Run from project root: python bridge_m20.py --camera front
The protocol is taken from the supplied receive_m20_h264.py, not inferred RTSP.
"""
import argparse
import asyncio
import contextlib
import logging
import math
import os
import shutil
import struct
from dataclasses import dataclass
from urllib.parse import urlsplit

from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException
from source_diagnostics import SourceStatus

HEADER = struct.Struct("!8sBBHIQ")
MAGIC = b"M20H264\x00"
CAMERA_IDS = {"front": 0, "back": 1}
log = logging.getLogger("m20-rtsp")


@dataclass(frozen=True)
class Packet:
    payload: bytes
    flags: int
    sequence: int
    timestamp: int


def parse_packet(message, camera):
    """One binary WS message = 24-byte header + Annex-B payload.

    Flags and timestamp are preserved but not interpreted: vendor units and flag
    semantics weren't supplied. Raw H.264 publishing generates timestamps by fps.
    """
    if not isinstance(message, bytes) or len(message) <= HEADER.size:
        return None
    magic, version, camera_id, flags, sequence, timestamp = HEADER.unpack_from(message)
    if magic != MAGIC or version != 1 or camera_id != CAMERA_IDS[camera]:
        return None
    payload = message[HEADER.size:]
    return Packet(payload, flags, sequence, timestamp)


def ffmpeg_command(args):
    cmd = [args.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
           "-fflags", "+genpts", "-r", str(args.fps), "-f", "h264", "-i", "pipe:0",
           "-map", "0:v:0", "-an"]
    if args.codec == "copy":
        cmd += ["-c:v", "copy"]
    else:
        cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
                "-pix_fmt", "yuv420p", "-profile:v", "baseline", "-bf", "0",
                "-g", str(max(1, round(args.fps * 2))),
                "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2"]
    cmd += ["-f", "rtsp", "-rtsp_transport", "tcp", args.rtsp_url]
    return cmd


async def read_stderr(stream, tail):
    # Drain to prevent child-process deadlock. Do not log raw output: FFmpeg can
    # include credentials from RTSP URLs. Return codes are logged instead.
    while True:
        chunk = await stream.read(4096)
        if not chunk:
            break
        tail[:] = (tail + chunk)[-8192:]


async def stop_process(process):
    if process.stdin:
        process.stdin.close()
    if process.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 3)
        except asyncio.TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            await process.wait()


async def relay_session(args):
    process = None
    stderr_job = None
    status = SourceStatus(args.status_file)
    status.write("connecting")
    async with connect(args.ws_url, proxy=None, compression=None, max_size=32 * 1024 * 1024,
                       max_queue=8, open_timeout=args.timeout, close_timeout=3) as websocket:
        log.info("WebSocket 已连接，相机=%s；等待有效视频数据", args.camera)
        status.write("connected")
        loop = asyncio.get_running_loop()
        last_valid = loop.time()
        count, invalid = 0, 0
        report_at = last_valid
        try:
            while True:
                if process and process.returncode is not None:
                    raise RuntimeError(f"FFmpeg 已退出，返回码 {process.returncode}；请检查 RTSP 发布权限、路径和编码")
                remaining = args.timeout - (loop.time() - last_valid)
                if remaining <= 0:
                    raise TimeoutError("等待有效 M20 数据超时")
                message = await asyncio.wait_for(websocket.recv(), remaining)
                packet = parse_packet(message, args.camera)
                if packet is None:
                    invalid += 1
                    if invalid == 1 or loop.time() - report_at >= 5:
                        status.write("invalid", count, invalid)
                        report_at = loop.time()
                    continue
                last_valid = loop.time()
                if process is None:
                    process = await asyncio.create_subprocess_exec(
                        *ffmpeg_command(args), stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
                    stderr_job = asyncio.create_task(read_stderr(process.stderr, bytearray()))
                    log.info("已启动 FFmpeg，模式=%s；有有效输入不等于浏览器已播放", args.codec)
                process.stdin.write(packet.payload)
                await asyncio.wait_for(process.stdin.drain(), args.timeout)
                count += 1
                if count == 1 or last_valid - report_at >= 2:
                    status.write("forwarding", count, invalid)
                    log.info("有效包=%d，忽略包=%d，最近序号=%d", count, invalid, packet.sequence)
                    report_at = last_valid
        finally:
            if process:
                await stop_process(process)
            if stderr_job:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(stderr_job, 3)


async def run(args):
    delay = 2
    status = SourceStatus(args.status_file)
    while True:
        started = asyncio.get_running_loop().time()
        try:
            await relay_session(args)
        except (OSError, WebSocketException, TimeoutError, RuntimeError) as exc:
            # Connection errors may embed full URLs/credentials, so only the
            # exception class is logged. No video payload or tokens are printed.
            # The last persisted stage distinguishes handshake failure from a
            # source that connected but stopped providing valid packets.
            stage = "connect_error"
            if args.status_file:
                try:
                    import json
                    from pathlib import Path
                    previous = json.loads(Path(args.status_file).read_text(encoding="utf-8"))["stage"]
                    if previous != "connecting":
                        stage = "stream_error"
                except (OSError, ValueError, KeyError):
                    pass
            status.write(stage, error=type(exc).__name__)
            log.warning("会话中断 (%s)，阶段=%s；检查源服务/协议及 MediaMTX 日志", type(exc).__name__, stage)
            if args.once:
                return 1
        if asyncio.get_running_loop().time() - started > 30:
            delay = 2
        log.info("%s 秒后重新连接；旧 FFmpeg 已清理", delay)
        await asyncio.sleep(delay)
        delay = min(delay * 2, 30)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="M20 视频桥接：WebSocket H.264 → RTSP / MediaMTX")
    parser.add_argument("--camera", choices=CAMERA_IDS, default="front")
    parser.add_argument("--host", default="192.168.126.176", help="M20 视频服务主机")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--ws-url", help="覆盖 M20 WS 地址，可使用 wss://")
    parser.add_argument("--rtsp-url", help="发布目标，也可设置 M20_RTSP_URL 环境变量")
    parser.add_argument("--fps", type=float, default=25, help="实际源帧率；25 仅为默认假设，不是厂家确认值")
    parser.add_argument("--codec", choices=("copy", "h264"), default="copy", help="copy 保留编码；h264 使用 libx264 重编码")
    parser.add_argument("--timeout", type=float, default=15, help="连接/有效数据/管道背压超时秒数")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="FFmpeg 可执行文件路径")
    parser.add_argument("--once", action="store_true", help="失败后退出，不自动重连")
    parser.add_argument("--status-file", help="启动器使用的本地诊断文件，不保存地址或视频数据")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port 应为 1~65535")
    if not math.isfinite(args.fps) or not 1 <= args.fps <= 120:
        parser.error("fps 应为 1~120")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("timeout 必须大于零")
    args.ws_url = args.ws_url or f"ws://{args.host}:{args.port}/{args.camera}"
    camera_path = "camera_1" if args.camera == "front" else "camera_2"
    args.rtsp_url = args.rtsp_url or os.getenv("M20_RTSP_URL") or f"rtsp://127.0.0.1:18554/live/{camera_path}"
    try:
        ws, rtsp = urlsplit(args.ws_url), urlsplit(args.rtsp_url)
        if ws.scheme not in ("ws", "wss") or not ws.hostname or ws.fragment:
            raise ValueError
        if rtsp.scheme not in ("rtsp", "rtsps") or not rtsp.hostname or rtsp.path in ("", "/") or rtsp.fragment:
            raise ValueError
        _ = ws.port, rtsp.port
    except ValueError:
        parser.error("请提供有效 ws(s) 源地址和带视频路径的 rtsp(s) 发布地址")
    return args


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if shutil.which(args.ffmpeg) is None:
        log.error("找不到 FFmpeg；Ubuntu: sudo apt install ffmpeg，或用 --ffmpeg 指定路径")
        return 2
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        SourceStatus(args.status_file).write("stopped")
        log.info("桥接已停止")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
