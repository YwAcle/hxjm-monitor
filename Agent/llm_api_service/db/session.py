"""
数据库连接管理
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from llm_api_service.config import DbConfig


def create_pg_engine(cfg: DbConfig) -> Engine:
    """创建 PostgreSQL 数据库引擎"""
    url = f"postgresql+{cfg.driver}://{cfg.user}:{cfg.password}@{cfg.host}:{cfg.port}/{cfg.database}"
    engine = create_engine(
        url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
    return engine

