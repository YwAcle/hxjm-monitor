import asyncio
import struct
import pytest
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed
import bridge_m20 as m20


def packet(camera=0, magic=m20.MAGIC, version=1, payload=b"\x00\x00\x00\x01\x67fake-h264"):
    return m20.HEADER.pack(magic, version, camera, 0, 42, 9999) + payload


def test_protocol_header_and_camera_filter():
    assert m20.HEADER.size == 24
    p = m20.parse_packet(packet(), "front")
    assert p.payload.startswith(b"\x00\x00\x00\x01")
    assert (p.sequence, p.timestamp) == (42, 9999)
    for invalid in ("text", b"short", packet(payload=b""), packet(magic=b"BADMAGIC"), packet(version=2), packet(camera=1)):
        assert m20.parse_packet(invalid, "front") is None
    assert m20.parse_packet(packet(camera=1), "back") is not None


def test_ffmpeg_mapping_and_codec(monkeypatch):
    monkeypatch.delenv("M20_RTSP_URL", raising=False)
    args = m20.parse_args([])
    assert args.ws_url == "ws://192.168.126.176:8765/front"
    assert args.rtsp_url.endswith("/live/camera_1")
    cmd = m20.ffmpeg_command(args)
    assert cmd[cmd.index("-c:v") + 1] == "copy"
    assert cmd[cmd.index("-rtsp_transport") + 1] == "tcp"
    assert cmd.index("-r") < cmd.index("-i")
    args = m20.parse_args(["--camera", "back", "--codec", "h264", "--fps", "30"])
    cmd = m20.ffmpeg_command(args)
    assert args.rtsp_url.endswith("/live/camera_2")
    assert "libx264" in cmd and cmd[cmd.index("-bf") + 1] == "0"
    monkeypatch.setenv("M20_RTSP_URL", "rtsp://example:8554/test")
    assert m20.parse_args([]).rtsp_url == "rtsp://example:8554/test"


@pytest.mark.parametrize("argv", [["--fps", "nan"], ["--timeout", "inf"], ["--port", "0"], ["--ws-url", "http://wrong"], ["--rtsp-url", "rtsp://host"], ["--rtsp-url", "rtsp://host:bad/path"]])
def test_invalid_cli(argv):
    with pytest.raises(SystemExit):
        m20.parse_args(argv)


class Sink:
    def __init__(self):
        self.chunks = []
        self.closed = False

    def write(self, data):
        self.chunks.append(data)

    async def drain(self):
        await asyncio.sleep(0)

    def close(self):
        self.closed = True


class FakeFFmpeg:
    """Verify actual local WS reception and byte piping, without claiming encoding."""
    def __init__(self):
        self.stdin = Sink()
        self.stderr = asyncio.StreamReader()
        self.stderr.feed_eof()
        self.returncode = None

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9

    async def wait(self):
        return self.returncode


def test_local_websocket_to_ffmpeg_pipe_and_cleanup(monkeypatch):
    async def scenario():
        fake = FakeFFmpeg()
        commands = []

        async def spawn(*cmd, **kwargs):
            commands.append(cmd)
            return fake

        monkeypatch.setattr(m20.asyncio, "create_subprocess_exec", spawn)
        good = packet()

        async def sender(ws):
            assert ws.request.path == "/front"
            await ws.send("ignored-text")
            await ws.send(packet(camera=1))
            await ws.send(good)
            await asyncio.sleep(.1)

        async with serve(sender, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            args = m20.parse_args(["--ws-url", f"ws://127.0.0.1:{port}/front"])
            with pytest.raises(ConnectionClosed):
                await m20.relay_session(args)
        assert fake.stdin.chunks == [good[24:]]
        assert fake.stdin.closed and fake.returncode is not None
        assert commands[0][-1].endswith("/live/camera_1")
    asyncio.run(scenario())


def test_invalid_messages_do_not_prevent_timeout(monkeypatch):
    async def scenario():
        async def spawn(*args, **kwargs):
            raise AssertionError("无有效数据时不应启动 FFmpeg")
        monkeypatch.setattr(m20.asyncio, "create_subprocess_exec", spawn)

        async def sender(ws):
            try:
                while True:
                    await ws.send("not-video")
                    await asyncio.sleep(.01)
            except ConnectionClosed:
                pass

        async with serve(sender, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            args = m20.parse_args(["--ws-url", f"ws://127.0.0.1:{port}/front", "--timeout", "0.1"])
            with pytest.raises(TimeoutError):
                await m20.relay_session(args)
    asyncio.run(scenario())
