#!/usr/bin/env python3
"""Centralized configuration for the Garden service.

This module only owns default values and environment-based resolution helpers.
It should stay free of HTTP routing, frame decoding, and model inference logic
so the boundary between configuration and runtime behavior remains clear.
"""

import os
from pathlib import Path


# Keep all project-relative defaults in one place so other modules do not need
# to repeat path construction logic.
BASE_DIR = Path(__file__).resolve().parent

# Service-wide defaults shared by the HTTP layer, model workers, and SSE layer.
DEFAULT_IPC_ADDR = "ipc:///tmp/py_ai_garden.ipc"
DEFAULT_MODEL_PATH = "/home/guest/hxjm/llm-service/garden/Garden"
DEFAULT_PROMPT_TEMPLATE = str(BASE_DIR / "prompts" / "garbage_detection.json")
DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8765
DEFAULT_MODEL_WORKERS = 4
DEFAULT_EXPECTED_STREAMS = "camera_1,camera_2,camera_3,camera_4"
DEFAULT_SSE_HEARTBEAT_SEC = 15
DEFAULT_SESSION_TTL_MS = 3600000
DEFAULT_SESSION_IDLE_TIMEOUT_MS = 300000
DEFAULT_SESSION_CLEANUP_INTERVAL_MS = 30000
DEFAULT_REPLAY_WINDOW_MS = 300000
DEFAULT_REPLAY_BUFFER_SIZE = 1000
DEFAULT_SESSION_QUEUE_SIZE = 256
DEFAULT_TASK_NAMESPACE = "vision.garden.garbage.detect"


def _load_torch_module(torch_module=None):
    """Lazily import torch so callers may inject or defer the dependency."""
    if torch_module is not None:
        return torch_module

    import torch

    return torch

# 自动选择合适的浮点数精度
def resolve_torch_dtype(torch_module=None):
    """Resolve the runtime dtype from env with hardware-aware fallback."""
    torch_module = _load_torch_module(torch_module)
    value = os.getenv("GARDEN_TORCH_DTYPE", "auto").strip().lower()
    if value == "bfloat16":
        return torch_module.bfloat16
    if value == "float16":
        return torch_module.float16
    if value == "float32":
        return torch_module.float32

    if torch_module.cuda.is_available():
        if torch_module.cuda.is_bf16_supported():
            return torch_module.bfloat16
        return torch_module.float16
    return torch_module.float32

# 自动检测可用的GPU设备
def resolve_device_names(torch_module=None):
    """Resolve the list of execution devices used by model workers."""
    torch_module = _load_torch_module(torch_module)
    raw = os.getenv("GARDEN_CUDA_DEVICES", "").strip()
    if raw:
        selected = [item.strip() for item in raw.split(",") if item.strip()]
        if selected:
            if torch_module.cuda.is_available():
                return [f"cuda:{item}" for item in selected]
            return ["cpu"]

    if torch_module.cuda.is_available():
        return [f"cuda:{idx}" for idx in range(torch_module.cuda.device_count())]
    return ["cpu"]

# 解析预期的摄像头流列表
def resolve_expected_streams():
    """Resolve dashboard placeholder stream names from configuration."""
    raw = os.getenv("GARDEN_EXPECTED_STREAMS", DEFAULT_EXPECTED_STREAMS).strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]
