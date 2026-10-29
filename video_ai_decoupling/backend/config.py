import os
from pathlib import Path


DEMO_ROOT = Path(__file__).resolve().parents[1]
HXJM_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = HXJM_ROOT / "python"

RTSP_URL = os.getenv("DEMO_RTSP_URL", "rtsp://127.0.0.1:18554/live/camera_1")
RTSP_TRANSPORT = os.getenv("DEMO_RTSP_TRANSPORT", "udp").strip().lower()
CAMERA_ID = os.getenv("DEMO_CAMERA_ID", "camera_1")
OPEN_TIMEOUT_MS = 5000
READ_TIMEOUT_MS = 5000
INFERENCE_INTERVAL_SECONDS = float(os.getenv("DEMO_INFERENCE_INTERVAL_SECONDS", "1"))
RECONNECT_DELAY_SECONDS = float(os.getenv("DEMO_RECONNECT_DELAY_SECONDS", "2"))
WS_SEND_TIMEOUT_SECONDS = float(os.getenv("DEMO_WS_SEND_TIMEOUT_SECONDS", "5"))
