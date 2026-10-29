"""Four independent channels; hardware sources are supplied in cameras.json."""
from dataclasses import dataclass
import json
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Camera:
    id: str
    name: str
    source: str
    url: str = ""
    camera: str = "front"
    fps: int = 25
    codec: str = "copy"

    @property
    def path(self):
        return f"live/{self.id}"


@dataclass
class Settings:
    mode: str = "simulated"
    robot_host: str = "192.168.126.176"
    robot_port: int = 8765
    fps: int = 25
    codec: str = "copy"
    web_port: int = 8890
    rtsp_port: int = 28554
    whep_port: int = 28889
    ice_port: int = 28189
    mock_port: int = 28765
    public_host: str = "127.0.0.1"
    bind: str = "127.0.0.1"
    cameras: tuple = ()

    def target_url(self, camera):
        return f"rtsp://127.0.0.1:{self.rtsp_port}/{camera.path}"

    def whep_url(self, camera):
        return f"http://{self.public_host}:{self.whep_port}/{camera.path}/whep"

    def load_cameras(self, file):
        data = json.loads(Path(file).read_text(encoding="utf-8-sig"))
        rows = data.get("cameras") if isinstance(data, dict) else None
        if not isinstance(rows, list) or len(rows) != 4:
            raise ValueError("摄像头配置必须包含 cameras 数组，恰好四项")
        cameras = []
        expected = {f"camera_{i}" for i in range(1, 5)}
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("每项摄像头配置必须是对象")
            ident, name = row.get("id"), row.get("name")
            if not isinstance(ident, str) or ident not in expected or any(c.id == ident for c in cameras):
                raise ValueError("摄像头 id 必须是互不重复的 camera_1 到 camera_4")
            if not isinstance(name, str) or not name.strip() or len(name) > 80:
                raise ValueError("每路摄像头需要 1~80 字的 name")
            source = row.get("source")
            if source not in ("m20", "rtsp", "publisher", "disabled"):
                raise ValueError(f"{ident} source 须为 m20/rtsp/publisher/disabled")
            camera = row.get("camera", "front")
            fps, codec = row.get("fps", self.fps), row.get("codec", self.codec)
            if camera not in ("front", "back") or type(fps) is not int or not 1 <= fps <= 60 or codec not in ("copy", "h264"):
                raise ValueError(f"{ident} 的 camera、fps 或 codec 无效")
            url = row.get("url", "")
            if not isinstance(url, str):
                raise ValueError(f"{ident} url 必须为字符串")
            if self.mode == "simulated":
                source = "simulated"
                url = f"ws://127.0.0.1:{self.mock_port}/{ident}"
                camera = "back" if ident == "camera_2" else "front"
                fps = self.fps
            elif source == "m20":
                url = url or f"ws://{self.robot_host}:{self.robot_port}/{camera}"
            if source in ("m20", "rtsp"):
                try:
                    parsed = urlsplit(url)
                    schemes = ("ws", "wss") if source == "m20" else ("rtsp", "rtsps")
                    if parsed.scheme not in schemes or not parsed.hostname or parsed.fragment:
                        raise ValueError
                    _ = parsed.port
                    if source == "rtsp" and parsed.path in ("", "/"):
                        raise ValueError
                except ValueError:
                    raise ValueError(f"{ident} 的视频地址格式无效") from None
            cameras.append(Camera(ident, name.strip(), source, url, camera, fps, codec))
        self.cameras = tuple(sorted(cameras, key=lambda c: c.id))
        return self

    def public_cameras(self):
        # Source credentials and private endpoints never go to the browser API.
        return [{"id": c.id, "name": c.name, "source": c.source,
                 "fps_assumption": c.fps, "codec": c.codec, "path": c.path,
                 "whep_url": self.whep_url(c), "enabled": c.source != "disabled"}
                for c in self.cameras]

    def mediamtx_yaml(self):
        result = f'''logLevel: info
rtsp: yes
rtspAddress: {self.bind}:{self.rtsp_port}
rtspTransports: [tcp]
rtmp: no
hls: no
srt: no
webrtc: yes
webrtcAddress: {self.bind}:{self.whep_port}
webrtcAllowOrigin: '*'
webrtcLocalUDPAddress: {self.bind}:{self.ice_port}
webrtcAdditionalHosts: [{self.public_host}]
paths:
'''
        if all(c.source == "disabled" for c in self.cameras):
            return result.removesuffix("paths:\n") + "paths: {}\n"
        for camera in self.cameras:
            if camera.source == "disabled":
                continue
            source = json.dumps(camera.url) if camera.source == "rtsp" else "publisher"
            result += f"  {camera.path}:\n    source: {source}\n"
            if camera.source == "rtsp":
                result += "    rtspTransport: tcp\n    sourceOnDemand: yes\n"
        return result
