from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import ProgrammingError


@dataclass(frozen=True)
class MediaAssetRow:
    id: str
    stream_id: str
    asset_type: str
    start_ts: datetime
    duration_ms: int
    path: str
    content_type: str | None


def _is_undefined_column_error(e: ProgrammingError) -> bool:
    orig = getattr(e, "orig", None)
    try:
        if orig is not None and getattr(orig, "args", None):
            a0 = orig.args[0]
            if isinstance(a0, dict) and a0.get("C") == "42703":
                return True
    except Exception:
        pass

    msg = str(e).lower()
    return "does not exist" in msg and "column" in msg


def get_media_asset_by_id(engine: Engine, schema: str, media_asset_id: str) -> MediaAssetRow | None:
    sql_play_url = text(
        f"""
        select m.id, m.stream_id, m.asset_type, m.start_ts, m.duration_ms, m.play_url as path, m.content_type
        from {schema}.media_asset m
        where m.id = :id
        limit 1
        """
    )
    sql_path = text(
        f"""
        select m.id, m.stream_id, m.asset_type, m.start_ts, m.duration_ms, m.path, m.content_type
        from {schema}.media_asset m
        where m.id = :id
        limit 1
        """
    )

    with engine.connect() as conn:
        try:
            r = conn.execute(sql_play_url, {"id": media_asset_id}).mappings().first()
        except ProgrammingError as e:
            if not _is_undefined_column_error(e):
                raise
            r = conn.execute(sql_path, {"id": media_asset_id}).mappings().first()

    if r is None:
        return None

    return MediaAssetRow(
        id=str(r["id"]),
        stream_id=str(r["stream_id"]),
        asset_type=str(r["asset_type"]),
        start_ts=r["start_ts"],
        duration_ms=int(r["duration_ms"]),
        path=str(r["path"]),
        content_type=(str(r["content_type"]) if r["content_type"] is not None else None),
    )


def select_episode_media(
    engine: Engine,
    schema: str,
    episode_id: str,
    stream_id: str | None,
    start_ts: datetime,
    end_ts: datetime,
    limit: int = 2,
) -> list[MediaAssetRow]:
    link_sql_play_url = text(
        f"""
        with assets as (
          select m.id, m.stream_id, m.asset_type, m.start_ts, m.duration_ms, m.play_url as path, m.content_type,
                 greatest(0, extract(epoch from least(:end_ts, m.start_ts + (m.duration_ms * interval '1 millisecond'))
                                      - greatest(:start_ts, m.start_ts)) * 1000) as overlap_ms
          from {schema}.episode_media_link l
          join {schema}.media_asset m on m.id = l.media_asset_id
          where l.episode_id = :episode_id
            and m.asset_type in ('clip', 'segment')
        )
        select * from assets
        order by overlap_ms desc, duration_ms desc
        limit :limit
        """
    )
    link_sql_path = text(
        f"""
        with assets as (
          select m.id, m.stream_id, m.asset_type, m.start_ts, m.duration_ms, m.path, m.content_type,
                 greatest(0, extract(epoch from least(:end_ts, m.start_ts + (m.duration_ms * interval '1 millisecond'))
                                      - greatest(:start_ts, m.start_ts)) * 1000) as overlap_ms
          from {schema}.episode_media_link l
          join {schema}.media_asset m on m.id = l.media_asset_id
          where l.episode_id = :episode_id
            and m.asset_type in ('clip', 'segment')
        )
        select * from assets
        order by overlap_ms desc, duration_ms desc
        limit :limit
        """
    )

    with engine.connect() as conn:
        params = {"episode_id": episode_id, "start_ts": start_ts, "end_ts": end_ts, "limit": int(limit)}
        try:
            rows = conn.execute(link_sql_play_url, params).mappings().all()
        except ProgrammingError as e:
            if not _is_undefined_column_error(e):
                raise
            rows = conn.execute(link_sql_path, params).mappings().all()

    if len(rows) == 0 and stream_id is not None:
        fallback_sql_play_url = text(
            f"""
            with assets as (
              select m.id, m.stream_id, m.asset_type, m.start_ts, m.duration_ms, m.play_url as path, m.content_type,
                     greatest(0, extract(epoch from least(:end_ts, m.start_ts + (m.duration_ms * interval '1 millisecond'))
                                          - greatest(:start_ts, m.start_ts)) * 1000) as overlap_ms
              from {schema}.media_asset m
              where m.stream_id = :stream_id
                and m.asset_type in ('clip', 'segment')
                and m.start_ts < :end_ts
                and (m.start_ts + (m.duration_ms * interval '1 millisecond')) > :start_ts
            )
            select * from assets
            order by overlap_ms desc, duration_ms desc
            limit :limit
            """
        )
        fallback_sql_path = text(
            f"""
            with assets as (
              select m.id, m.stream_id, m.asset_type, m.start_ts, m.duration_ms, m.path, m.content_type,
                     greatest(0, extract(epoch from least(:end_ts, m.start_ts + (m.duration_ms * interval '1 millisecond'))
                                          - greatest(:start_ts, m.start_ts)) * 1000) as overlap_ms
              from {schema}.media_asset m
              where m.stream_id = :stream_id
                and m.asset_type in ('clip', 'segment')
                and m.start_ts < :end_ts
                and (m.start_ts + (m.duration_ms * interval '1 millisecond')) > :start_ts
            )
            select * from assets
            order by overlap_ms desc, duration_ms desc
            limit :limit
            """
        )
        with engine.connect() as conn:
            params = {"stream_id": stream_id, "start_ts": start_ts, "end_ts": end_ts, "limit": int(limit)}
            try:
                rows = conn.execute(fallback_sql_play_url, params).mappings().all()
            except ProgrammingError as e:
                if not _is_undefined_column_error(e):
                    raise
                rows = conn.execute(fallback_sql_path, params).mappings().all()

    return [
        MediaAssetRow(
            id=str(r["id"]),
            stream_id=str(r["stream_id"]),
            asset_type=str(r["asset_type"]),
            start_ts=r["start_ts"],
            duration_ms=int(r["duration_ms"]),
            path=str(r["path"]),
            content_type=(str(r["content_type"]) if r["content_type"] is not None else None),
        )
        for r in rows
    ]
