"""Read-only staged camera probe. Does not decode, save video or send controls."""
import argparse
import asyncio
import json
import math
import re
from urllib.parse import urlsplit

from websockets.asyncio.client import connect
from bridge_m20 import parse_packet


async def probe(url, camera="front", timeout=5):
    results = []
    parsed = urlsplit(url)
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(parsed.hostname, port), timeout)
        writer.close()
        await writer.wait_closed()
        results.append({"stage": "tcp", "ok": True, "detail": "TCP 端口可达，不代表视频可用。"})
    except (OSError, TimeoutError) as exc:
        return [{"stage": "tcp", "ok": False, "error_type": type(exc).__name__,
                 "detail": "TCP 不可达；核对设备开机、网络/路由、IP、端口和视频服务。"}]
    opened = False
    count = invalid = 0
    try:
        # LAN/Tailscale camera traffic must not be routed through OS HTTP proxies.
        async with connect(url, proxy=None, compression=None, open_timeout=timeout,
                           close_timeout=1, max_size=32 * 1024 * 1024, max_queue=4) as ws:
            opened = True
            results.append({"stage": "websocket", "ok": True, "detail": "WebSocket 握手成功。"})
            async with asyncio.timeout(timeout):
                while count < 2000:
                    message = await ws.recv()
                    count += 1
                    packet = parse_packet(message, camera)
                    if packet is not None:
                        results.append({"stage": "packet", "ok": True, "messages": count,
                                        "payload_bytes": len(packet.payload),
                                        "detail": "收到符合 M20 包头约定的数据；仍需验证 H.264 解码及浏览器播放。"})
                        return results
                    invalid += 1
            # A busy source consisting solely of invalid messages can hit this bound.
            raise TimeoutError
    except Exception as exc:
        if not opened:
            detail = "TCP 已通，但 WebSocket 未建立；核对 /front 或 /back 路径、认证和厂家服务。"
        elif invalid:
            detail = "收到消息但均不符合 M20 协议；核对 24 字节头、magic、版本、相机编号。"
        else:
            detail = "WebSocket 已通但未收到有效视频包；确认设备视频源和外部观看权限。"
        results.append({"stage": "packet" if opened else "websocket", "ok": False,
                        "error_type": type(exc).__name__, "messages": count,
                        "invalid_messages": invalid, "detail": detail})
        return results


def main():
    parser = argparse.ArgumentParser(description="分阶段检查 M20 TCP、WebSocket 与视频包；不会发送控制指令")
    parser.add_argument("--host", default="192.168.126.176")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--camera", choices=("front", "back"), default="front")
    parser.add_argument("--ws-url", help="覆盖自动生成的视频地址；诊断输出不打印账号密码")
    parser.add_argument("--timeout", type=float, default=5, help="每阶段超时秒数")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("端口或超时无效")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", args.host):
        parser.error("host 请填写 IPv4 或主机名")
    url = args.ws_url or f"ws://{args.host}:{args.port}/{args.camera}"
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ("ws", "wss") or not parsed.hostname or parsed.fragment:
            raise ValueError
        _ = parsed.port
    except ValueError:
        parser.error("ws-url 需为有效 ws(s) 地址")
    results = asyncio.run(probe(url, args.camera, args.timeout))
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for item in results:
            print(f"[{'通过' if item['ok'] else '未通过'}] {item['stage']}: {item['detail']}")
            if item.get("error_type"):
                print("  错误类别：", item["error_type"])
    return 0 if results[-1]["stage"] == "packet" and results[-1]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
