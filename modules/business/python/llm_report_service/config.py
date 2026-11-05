from __future__ import annotations

from dataclasses import dataclass

from ai_infra.config import ModelConfig


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    user: str
    password: str
    database: str
    schema: str = "public"
    driver: str = "pg8000"


@dataclass(frozen=True)
class ServiceConfig:
    scan_interval_s: float = 60.0
    batch_size: int = 10
    media_limit: int = 2
    max_video_frames: int = 8
    media_base_dir: str = "/home/guest/Documents/lkh/mtx/mediamtx"
    oom_fallback_text_only: bool = True
    oom_retry_max_new_tokens: int = 128
