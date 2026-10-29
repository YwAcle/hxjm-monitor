"""
配置类
"""
from __future__ import annotations

from dataclasses import dataclass

from llm_report_service.config import ModelConfig


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    user: str
    password: str
    database: str
    schema: str = "public"
    driver: str = "pg8000"
    connect_timeout_s: float = 5.0


@dataclass(frozen=True)
class ServiceConfig:
    tz: str = "Asia/Shanghai"
    playback_base_url: str = ""
    memory_max_sessions: int = 1000
    memory_max_messages: int = 20
    max_request_bytes: int = 20 * 1024 * 1024
    max_prompt_chars: int = 8000
    max_image_bytes: int = 10 * 1024 * 1024
    max_image_pixels: int = 25_000_000
    max_image_side: int = 8192
    reid_timeout_s: float = 15.0
    reid_feature_base_url: str = "http://100.127.237.7:28024"
    reid_feature_space_id: str = ""
    reid_text_feature_space_id: str = ""
    reid_text_contract_id: str = ""
    reid_text_max_chars: int = 200
    agent_request_timeout_s: float = 180.0
    agent_answer_max_new_tokens: int = 2048
    image_asset_ttl_s: int = 1800
    image_asset_max_per_session: int = 4
    image_asset_max_bytes_per_session: int = 32 * 1024 * 1024
    image_asset_max_total_bytes: int = 256 * 1024 * 1024


__all__ = ["DbConfig", "ModelConfig", "ServiceConfig"]
