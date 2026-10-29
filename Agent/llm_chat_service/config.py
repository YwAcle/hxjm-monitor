from __future__ import annotations

from dataclasses import dataclass

from llm_report_service.llm.settings import (
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
    base_url: str = LLM_BASE_URL
    model_name: str = LLM_MODEL_ID
    api_key: str = LLM_API_KEY
    connect_timeout_s: float = LLM_CONNECT_TIMEOUT_S
    request_timeout_s: float = LLM_REQUEST_TIMEOUT_S
    max_retries: int = LLM_MAX_RETRIES
    enable_thinking: bool | None = LLM_ENABLE_THINKING
    max_new_tokens: int = 512
    temperature: float = 0.0


@dataclass(frozen=True)
class ServiceConfig:
    tz: str = "Asia/Shanghai"
    default_time_range: str = "today"
    playback_top_n: int = 10
    tracklet_limit: int = 200
    report_limit: int = 200
    media_limit_per_episode: int = 2
    media_base_dir: str = "/home/guest/Documents/lkh/mtx/mediamtx"
    playback_base_url: str = ""
    oom_fallback_text_only: bool = True
    oom_retry_max_new_tokens: int = 128
