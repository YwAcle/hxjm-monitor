from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from llm_report_service.config import DbConfig


def build_pg_uri(cfg: DbConfig) -> str:
    driver = cfg.driver.strip() if cfg.driver is not None and cfg.driver.strip() != "" else "pg8000"
    return (
        f"postgresql+{driver}://{cfg.user}:{cfg.password}@{cfg.host}:{cfg.port}/{cfg.database}"
    )


def create_pg_engine(cfg: DbConfig) -> Engine:
    preferred = cfg.driver.strip() if cfg.driver is not None and cfg.driver.strip() != "" else "pg8000"

    candidates: list[str] = []
    if preferred in {"pg8000", "psycopg2", "psycopg"}:
        candidates.append(preferred)
    candidates.extend(["pg8000", "psycopg", "psycopg2"])
    candidates = [c for i, c in enumerate(candidates) if c and c not in candidates[:i]]

    last_err: Exception | None = None
    for driver in candidates:
        try:
            if driver == "pg8000":
                import pg8000  # noqa: F401
            elif driver == "psycopg2":
                import psycopg2  # noqa: F401
            elif driver == "psycopg":
                import psycopg  # noqa: F401
        except Exception as e:
            last_err = e
            continue

        uri = build_pg_uri(DbConfig(**{**cfg.__dict__, "driver": driver}))
        return create_engine(uri, pool_pre_ping=True)

    raise SystemExit(
        "Missing PostgreSQL driver. Please install one of: pg8000 (pure python), psycopg2-binary (psycopg2) or psycopg (psycopg3). "
        f"Last error: {last_err}"
    )
