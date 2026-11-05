"""Bounded multi-camera analysis configuration; URLs are deployment settings."""
import json
import math
import os
import re
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
from .algorithms import algorithm_spec

ALGORITHM = os.getenv("VIDEO_ANALYSIS_ALGORITHM", "botsort").lower()
ALGORITHM_SPEC = algorithm_spec(ALGORITHM)
CACHE_ROOT = Path(os.getenv("VIDEO_ANALYSIS_CACHE_DIR", str(Path(__file__).parent / ".runtime")))
CAMERA_ID = os.getenv("VIDEO_ANALYSIS_CAMERA_ID", "camera_1")
if not re.fullmatch(r"camera_[1-9][0-9]*", CAMERA_ID):
    raise ValueError("VIDEO_ANALYSIS_CAMERA_ID must be camera_<positive integer>")
RTSP_URL = os.getenv("VIDEO_ANALYSIS_RTSP_URL", f"rtsp://127.0.0.1:18554/live/{CAMERA_ID}")
RTSP_TRANSPORT = os.getenv("VIDEO_ANALYSIS_RTSP_TRANSPORT", "tcp").lower()
if RTSP_TRANSPORT not in {"udp", "tcp"}:
    raise ValueError("VIDEO_ANALYSIS_RTSP_TRANSPORT must be udp or tcp")
OPEN_TIMEOUT_MS = 5000
READ_TIMEOUT_MS = 5000
DECODE_THREADS = int(os.getenv('VIDEO_ANALYSIS_DECODE_THREADS', '1'))
if not 1 <= DECODE_THREADS <= 8:
    raise ValueError('VIDEO_ANALYSIS_DECODE_THREADS must be between 1 and 8')
OPENCV_THREADS = int(os.getenv('VIDEO_ANALYSIS_OPENCV_THREADS', '4'))
if not 1 <= OPENCV_THREADS <= 8:
    raise ValueError('VIDEO_ANALYSIS_OPENCV_THREADS must be between 1 and 8')


def positive_seconds(name, default):
    value = float(os.getenv(name, default))
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value


INFERENCE_INTERVAL_SECONDS = positive_seconds("VIDEO_ANALYSIS_INTERVAL_SECONDS", ALGORITHM_SPEC.default_interval)
# Synchronized JPEG frames share the inference workers with all cameras. Keep
# the default sustainable for multi-camera playback; deployments can raise it
# explicitly after measuring their available inference and network capacity.
SYNC_FPS = positive_seconds("VIDEO_ANALYSIS_SYNC_FPS", "8")
if SYNC_FPS > 60:
    raise ValueError("VIDEO_ANALYSIS_SYNC_FPS must be at most 60")
SYNC_FRAME_WIDTH = 1280
SYNC_FRAME_HEIGHT = 720
SYNC_JPEG_QUALITY = 80
SYNC_MAX_JPEG_BYTES = 2 * 1024 * 1024
RECONNECT_DELAY_SECONDS = positive_seconds("VIDEO_ANALYSIS_RECONNECT_SECONDS", "2")
WS_SEND_TIMEOUT_SECONDS = positive_seconds("VIDEO_ANALYSIS_WS_SEND_TIMEOUT_SECONDS", "5")
RESULT_TTL_MS = int(positive_seconds("VIDEO_ANALYSIS_RESULT_TTL_SECONDS", "3") * 1000)


def camera_configs():
    raw = os.getenv("VIDEO_ANALYSIS_CAMERAS")
    if raw:
        cameras = json.loads(raw)
    else:
        base = os.getenv("VIDEO_ANALYSIS_RTSP_BASE", "rtsp://127.0.0.1:18554/live").rstrip("/")
        # Keep the explicit stage-one single-camera deployment setting compatible.
        cameras = ({CAMERA_ID: RTSP_URL} if os.getenv("VIDEO_ANALYSIS_RTSP_URL") else
                   {f"camera_{i}": f"{base}/camera_{i}" for i in range(1, 5)})
    if not isinstance(cameras, dict) or not 1 <= len(cameras) <= 16:
        raise ValueError("VIDEO_ANALYSIS_CAMERAS must map 1 to 16 camera IDs to RTSP URLs")
    for camera_id, url in cameras.items():
        if not re.fullmatch(r"camera_[1-9][0-9]*", camera_id):
            raise ValueError("Camera IDs must be camera_<positive integer>")
        if not isinstance(url, str) or not url.startswith("rtsp://"):
            raise ValueError("Camera sources must be RTSP URLs")
    return cameras


CAMERAS = camera_configs()
WORKER_COUNT = int(os.getenv("VIDEO_ANALYSIS_WORKERS", "1"))
if not 1 <= WORKER_COUNT <= 4:
    raise ValueError("VIDEO_ANALYSIS_WORKERS must be between 1 and 4")
INFERENCE_TIMEOUT_SECONDS = positive_seconds("VIDEO_ANALYSIS_INFERENCE_TIMEOUT_SECONDS", "10")
MODEL_TIMEOUT_SECONDS = positive_seconds("VIDEO_ANALYSIS_MODEL_TIMEOUT_SECONDS", "60")
WORKER_RETRY_SECONDS = positive_seconds("VIDEO_ANALYSIS_WORKER_RETRY_SECONDS", "5")
WORKER_RETRY_MAX_SECONDS = positive_seconds("VIDEO_ANALYSIS_WORKER_RETRY_MAX_SECONDS", "120")
# Reserve memory for SSH, decoding and other services; loading has extra headroom.
MEMORY_RESERVE_BYTES = int(positive_seconds("VIDEO_ANALYSIS_MEMORY_RESERVE_GIB", "8") * 1024 ** 3)
MODEL_HEADROOM_BYTES = int(positive_seconds("VIDEO_ANALYSIS_MODEL_HEADROOM_GIB", "4") * 1024 ** 3)
WORKER_IDLE_SECONDS = positive_seconds("VIDEO_ANALYSIS_WORKER_IDLE_SECONDS", "60")
FRAME_FRESH_MS = int(positive_seconds("VIDEO_ANALYSIS_FRAME_FRESH_SECONDS", "2") * 1000)
MAX_FRAME_BYTES = int(os.getenv("VIDEO_ANALYSIS_MAX_FRAME_BYTES", str(3840 * 2160 * 3)))
if not 1 <= MAX_FRAME_BYTES <= 128 * 1024 * 1024:
    raise ValueError("VIDEO_ANALYSIS_MAX_FRAME_BYTES must be between 1 and 128 MiB")
MAX_CLIENTS = int(os.getenv("VIDEO_ANALYSIS_MAX_CLIENTS", "64"))
if not 1 <= MAX_CLIENTS <= 1024:
    raise ValueError("VIDEO_ANALYSIS_MAX_CLIENTS must be between 1 and 1024")
