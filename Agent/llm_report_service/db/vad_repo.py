from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class VadRow:
    id: int
    created_at: datetime
    media_asset_id: str
    stream_id: str | None
    frame_vad_base64: str | None
    anomaly_name: str | None
    anomaly_level: int | None


def count_vads(engine: Engine, schema: str) -> int:
    sql = text(f"select count(*) as cnt from {schema}.vad")
    with engine.connect() as conn:
        v = conn.execute(sql).mappings().first()
    if v is None:
        return 0
    return int(v["cnt"])


def fetch_vad_batch(engine: Engine, schema: str, offset: int, limit: int) -> list[VadRow]:
    sql = text(
        f"""
        select v.id, v.created_at, v.media_asset_id, v.stream_id, v.frame_vad_base64, v.anomaly_name, v.anomaly_level
        from {schema}.vad v
        order by v.id
        offset :offset
        limit :limit
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(sql, {"offset": int(offset), "limit": int(limit)}).mappings().all()

    return [
        VadRow(
            id=int(r["id"]),
            created_at=r["created_at"],
            media_asset_id=str(r["media_asset_id"]),
            stream_id=(str(r["stream_id"]) if r["stream_id"] is not None else None),
            frame_vad_base64=(str(r["frame_vad_base64"]) if r["frame_vad_base64"] is not None else None),
            anomaly_name=(str(r["anomaly_name"]) if r["anomaly_name"] is not None else None),
            anomaly_level=(int(r["anomaly_level"]) if r["anomaly_level"] is not None else None),
        )
        for r in rows
    ]


def fetch_pending_vads(
    engine: Engine,
    schema: str,
    prompt_type: str,
    limit: int = 10,
    since_ts: datetime | None = None,
) -> list[VadRow]:
    since_clause = "and v.created_at >= :since_ts" if since_ts is not None else ""
    sql = text(
        f"""
        select v.id, v.created_at, v.media_asset_id, v.stream_id, v.frame_vad_base64, v.anomaly_name, v.anomaly_level
        from {schema}.vad v
        where not exists (
          select 1
          from {schema}.llm_report r
          where r.vad_id = v.id
            and coalesce(r.prompt_type, '') = :prompt_type
        )
        {since_clause}
        order by v.id
        limit :limit
        """
    )

    with engine.connect() as conn:
        params = {"prompt_type": prompt_type, "limit": int(limit)}
        if since_ts is not None:
            params["since_ts"] = since_ts
        rows = conn.execute(sql, params).mappings().all()

    return [
        VadRow(
            id=int(r["id"]),
            created_at=r["created_at"],
            media_asset_id=str(r["media_asset_id"]),
            stream_id=(str(r["stream_id"]) if r["stream_id"] is not None else None),
            frame_vad_base64=(str(r["frame_vad_base64"]) if r["frame_vad_base64"] is not None else None),
            anomaly_name=(str(r["anomaly_name"]) if r["anomaly_name"] is not None else None),
            anomaly_level=(int(r["anomaly_level"]) if r["anomaly_level"] is not None else None),
        )
        for r in rows
    ]
