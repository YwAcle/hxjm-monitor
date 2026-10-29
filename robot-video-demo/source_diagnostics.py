"""Small, credential-free observations of the camera receiver (not video health)."""
import json
from pathlib import Path
import time


LABELS = {
    "connecting": "正在连接摄像头 WebSocket；若超时请先检查网络和视频服务。",
    "connected": "WebSocket 已建立；等待符合 M20 协议的视频包。",
    "forwarding": "已收到有效协议包并交给 FFmpeg；最终播放以浏览器解码为准。",
    "invalid": "已收到消息，但包头/版本/相机编号不符合约定；请核对厂家协议。",
    "connect_error": "WebSocket 未建立；检查 IP、端口、路径及视频服务。",
    "stream_error": "视频接收或 FFmpeg 转发中断；检查设备视频源与 MediaMTX 日志。",
    "stopped": "视频接收程序已停止。",
    "waiting": "等待接收程序启动。",
    "external": "由外部采集程序或 RTSP 相机供流；接收诊断不适用。",
    "disabled": "此路已禁用。",
    "stale": "接收诊断已过期，请检查接收进程。",
}


class SourceStatus:
    def __init__(self, path=None):
        self.path = Path(path) if path else None

    def write(self, stage, packets=0, invalid=0, error=None):
        if not self.path:
            return
        payload = {"stage": stage, "detail": LABELS[stage], "packets": packets,
                   "invalid_packets": invalid, "updated_at": time.time(), "error_type": error}
        try:
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            # Diagnostics must not interrupt video delivery.
            pass


def read_source_status(settings, directory):
    rows = []
    for camera in settings.cameras:
        stage = "disabled" if camera.source == "disabled" else "waiting" if camera.source in ("m20", "simulated") else "external"
        row = {"id": camera.id, "stage": stage, "detail": LABELS[stage]}
        if stage == "waiting":
            try:
                data = json.loads((Path(directory) / f"{camera.id}.json").read_text(encoding="utf-8"))
                age = max(0, time.time() - float(data["updated_at"]))
                row.update({"stage": data["stage"], "detail": LABELS[data["stage"]],
                            "packets": int(data["packets"]), "invalid_packets": int(data["invalid_packets"]),
                            "age_seconds": round(age, 1), "error_type": data.get("error_type")})
                if age > 50:
                    row.update(stage="stale", detail=LABELS["stale"])
            except (OSError, ValueError, KeyError, TypeError):
                pass
        rows.append(row)
    return rows
