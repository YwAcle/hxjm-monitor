from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class EpisodeRow:
    id: str
    start_ts: datetime
    end_ts: datetime
    meta: Any


@dataclass(frozen=True)
class TrackletRow:
    id: str
    stream_id: str
    start_ts: datetime
    end_ts: datetime | None
    color_rgb: Any
    trajectory_points: Any
    query_asset_base64: Any
    stranger_target_id: Any


def count_episodes(engine: Engine, schema: str) -> int:
    sql = text(f"select count(*) as cnt from {schema}.episode")
    with engine.connect() as conn:
        v = conn.execute(sql).mappings().first()
    if v is None:
        return 0
    return int(v["cnt"])


def fetch_episode_batch(engine: Engine, schema: str, offset: int, limit: int) -> list[EpisodeRow]:
    sql = text(
        f"""
        select e.id, e.start_ts, e.end_ts, e.meta
        from {schema}.episode e
        order by e.start_ts, e.id
        offset :offset
        limit :limit
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(sql, {"offset": int(offset), "limit": int(limit)}).mappings().all()

    return [
        EpisodeRow(
            id=str(r["id"]),
            start_ts=r["start_ts"],
            end_ts=r["end_ts"],
            meta=r["meta"],
        )
        for r in rows
    ]


def fetch_pending_episodes(
    engine: Engine,
    schema: str,
    prompt_type: str,
    limit: int = 10,
    since_ts: datetime | None = None,
) -> list[EpisodeRow]:
    since_clause = "and e.start_ts >= :since_ts" if since_ts is not None else ""
    sql = text(
        f"""
        select e.id, e.start_ts, e.end_ts, e.meta
        from {schema}.episode e
        where not exists (
          select 1
          from {schema}.llm_report r
          where r.episode_id = e.id
            and coalesce(r.prompt_type, '') = :prompt_type
        )
        {since_clause}
        order by e.start_ts, e.id
        limit :limit
        """
    )

    with engine.connect() as conn:
        params = {"prompt_type": prompt_type, "limit": int(limit)}
        if since_ts is not None:
            params["since_ts"] = since_ts
        rows = conn.execute(sql, params).mappings().all()

    return [
        EpisodeRow(
            id=str(r["id"]),
            start_ts=r["start_ts"],
            end_ts=r["end_ts"],
            meta=r["meta"],
        )
        for r in rows
    ]


def fetch_primary_tracklet(engine: Engine, schema: str, episode_id: str) -> TrackletRow | None:
    sql = text(
        f"""
        select t.id, t.stream_id, t.start_ts, t.end_ts, t.color_rgb, t.trajectory_points, t.query_asset_base64, t.stranger_target_id
        from {schema}.episode_tracklet_link l
        join {schema}.tracklet t on t.id = l.tracklet_id
        where l.episode_id = :episode_id
        order by l.created_at, l.id
        limit 1
        """
    )

    with engine.connect() as conn:
        r = conn.execute(sql, {"episode_id": episode_id}).mappings().first()

    if r is None:
        return None

    return TrackletRow(
        id=str(r["id"]),
        stream_id=str(r["stream_id"]),
        start_ts=r["start_ts"],
        end_ts=r["end_ts"],
        color_rgb=r["color_rgb"],
        trajectory_points=r["trajectory_points"],
        query_asset_base64=r["query_asset_base64"],
        stranger_target_id=r["stranger_target_id"],
    )
