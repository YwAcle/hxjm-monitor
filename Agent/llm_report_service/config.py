from __future__ import annotations

from dataclasses import dataclass

from llm_report_service.llm.settings import (
    LLM_BACKEND,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_CONNECT_TIMEOUT_S,
    LLM_ENABLE_THINKING,
    LLM_MAX_RETRIES,
    LLM_MODEL_ID,
    LLM_REQUEST_TIMEOUT_S,
)


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
class ModelConfig:
    backend: str = LLM_BACKEND
    base_url: str = LLM_BASE_URL
    model_name: str = LLM_MODEL_ID
    api_key: str = LLM_API_KEY
    connect_timeout_s: float = LLM_CONNECT_TIMEOUT_S
    request_timeout_s: float = LLM_REQUEST_TIMEOUT_S
    max_retries: int = LLM_MAX_RETRIES
    enable_thinking: bool | None = LLM_ENABLE_THINKING
    max_new_tokens: int = 256
    temperature: float = 0.0


@dataclass(frozen=True)
class ServiceConfig:
    scan_interval_s: float = 60.0
    batch_size: int = 10
    media_limit: int = 2
    max_video_frames: int = 8
    media_base_dir: str = "/home/guest/Documents/lkh/mtx/mediamtx"
    oom_fallback_text_only: bool = True
    oom_retry_max_new_tokens: int = 128
