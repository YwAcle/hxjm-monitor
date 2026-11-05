import asyncio
import json
from pathlib import Path
import socket
import time

from fastapi.testclient import TestClient
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from bridge_m20 import HEADER, MAGIC
from check_camera import probe
from settings import Settings
from source_diagnostics import SourceStatus, read_source_status
from web_server import create_app


def test_probe_distinguishes_tcp_handshake_and_packet_failures():
    async def exercise():
        # A reserved, non-listening local port produces a deterministic refusal.
        with socket.socket() as reserved:
            reserved.bind(("127.0.0.1", 0))
            port = reserved.getsockname()[1]
            result = await probe(f"ws://127.0.0.1:{port}/front", timeout=.3)
            assert result[-1]["stage"] == "tcp" and not result[-1]["ok"]

        async def not_websocket(reader, writer):
            try:
                await reader.read(4096)
                writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        async with await asyncio.start_server(not_websocket, "127.0.0.1", 0) as server:
            result = await probe(f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}/front", timeout=.3)
            assert result[0]["ok"]
            assert result[-1]["stage"] == "websocket" and not result[-1]["ok"]

        async def invalid(ws):
            try:
                while True:
                    await ws.send("not an M20 packet")
                    await asyncio.sleep(.01)
            except ConnectionClosed:
                pass

        async with serve(invalid, "127.0.0.1", 0) as server:
            result = await probe(f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}/front", timeout=1)
            assert result[1]["ok"]
            assert result[-1]["stage"] == "packet" and not result[-1]["ok"]
            assert result[-1]["invalid_messages"] > 0

        async def valid(ws):
            await ws.send(HEADER.pack(MAGIC, 1, 0, 0, 1, 123) + b"\x00\x00\x01\x65test")

        async with serve(valid, "127.0.0.1", 0) as server:
            result = await probe(f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}/front", timeout=1)
            assert [item["stage"] for item in result] == ["tcp", "websocket", "packet"]
            assert all(item["ok"] for item in result)
            assert result[-1]["payload_bytes"] == 8

    asyncio.run(exercise())


def test_source_diagnostics_stale_and_unsupported_sources(tmp_path):
    settings = Settings(mode="hardware").load_cameras(Path(__file__).resolve().parents[1] / "cameras.json")
    status = SourceStatus(tmp_path / "camera_1.json")
    status.write("forwarding", packets=5, invalid=2)
    first, second, third, fourth = read_source_status(settings, tmp_path)
    assert first["stage"] == "forwarding" and first["packets"] == 5
    assert second["stage"] == "waiting"
    assert third["stage"] == fourth["stage"] == "external"
    data = json.loads(status.path.read_text(encoding="utf-8"))
    data["updated_at"] = time.time() - 60
    status.path.write_text(json.dumps(data), encoding="utf-8")
    assert read_source_status(settings, tmp_path)[0]["stage"] == "stale"
    status.path.write_text("{partial", encoding="utf-8")
    assert read_source_status(settings, tmp_path)[0]["stage"] == "waiting"


def test_front_only_config_and_diagnostics_api(tmp_path):
    settings = Settings(mode="hardware").load_cameras(Path(__file__).resolve().parents[1] / "cameras.front-only.json")
    assert [camera.source for camera in settings.cameras] == ["m20", "disabled", "disabled", "disabled"]
    SourceStatus(tmp_path / "camera_1.json").write("connect_error", error="TimeoutError")
    with TestClient(create_app(settings, source_status=lambda: read_source_status(settings, tmp_path))) as client:
        result = client.get("/api/health").json()
        assert result["sources"][0]["error_type"] == "TimeoutError"
        assert result["sources"][1]["stage"] == "disabled"
        assert "192.168.126.176" not in json.dumps(result)
        assert "source-diagnostic" in client.get("/").text
