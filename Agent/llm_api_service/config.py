"""
配置类定义
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DbConfig:
    """数据库配置"""
    host: str = "192.168.108.238"
    port: int = 5432
    user: str = "root"
    password: str = "123456"
    database: str = "postgres"
    schema: str = "public"
    driver: str = "pg8000"


@dataclass(frozen=True)
class OpenRouterConfig:
    """OpenRouter API 配置"""
    api_key: str = ""
    model: str = "minimax/minimax-m2"
    base_url: str = "https://openrouter.ai/api/v1/chat/completions"
    max_tokens: int = 2048
    temperature: float = 0.1


@dataclass(frozen=True)
class PlaybackConfig:
    """回放服务配置"""
    host: str = "192.168.108.238"
    port: int = 9996
    default_duration: int = 30  # 默认回放时长（秒）


@dataclass(frozen=True)
class ServiceConfig:
    """服务配置"""
    tz: str = "Asia/Shanghai"
    max_iterations: int = 10
    tracklet_limit: int = 100
    anomaly_limit: int = 100
    report_limit: int = 50


def load_config_from_env() -> tuple[DbConfig, OpenRouterConfig, PlaybackConfig, ServiceConfig]:
    """从环境变量加载配置"""
    db_cfg = DbConfig(
        host=os.getenv("DB_HOST", "192.168.108.238"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "123456"),
        database=os.getenv("DB_NAME", "postgres"),
        schema=os.getenv("DB_SCHEMA", "public"),
    )
    
    openrouter_cfg = OpenRouterConfig(
        api_key=os.getenv("OPENROUTER_API_KEY", ""),
        model=os.getenv("OPENROUTER_MODEL", "minimax/minimax-m2"),
        max_tokens=int(os.getenv("OPENROUTER_MAX_TOKENS", "2048")),
        temperature=float(os.getenv("OPENROUTER_TEMPERATURE", "0.1")),
    )
    
    playback_cfg = PlaybackConfig(
        host=os.getenv("PLAYBACK_HOST", "192.168.108.238"),
        port=int(os.getenv("PLAYBACK_PORT", "9996")),
        default_duration=int(os.getenv("PLAYBACK_DURATION", "30")),
    )
    
    svc_cfg = ServiceConfig(
        tz=os.getenv("TZ", "Asia/Shanghai"),
        max_iterations=int(os.getenv("MAX_ITERATIONS", "10")),
        tracklet_limit=int(os.getenv("TRACKLET_LIMIT", "100")),
        anomaly_limit=int(os.getenv("ANOMALY_LIMIT", "100")),
        report_limit=int(os.getenv("REPORT_LIMIT", "50")),
    )
    
    return db_cfg, openrouter_cfg, playback_cfg, svc_cfg

