from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class TrackletRow:
    id: str
    stream_id: str
    start_ts: datetime
    end_ts: datetime | None
    gallery_target_id: str | None
    gallery_similarity: float | None
    query_asset_base64: Any
    frame_asset_base64: Any
    frame_end_base64: Any
    trajectory_points: Any
    episode_id: str | None


def list_tracklets_for_person(
    engine: Engine,
    schema: str,
    person_id: str,
    start_ts: datetime,
    end_ts: datetime,
    limit: int = 200,
) -> list[TrackletRow]:
    sql = text(
        f"""
        select t.id, t.stream_id, t.start_ts, t.end_ts, t.gallery_target_id, t.gallery_similarity,
               t.query_asset_base64, t.frame_asset_base64, t.frame_end_base64, t.trajectory_points,
               x.episode_id
        from {schema}.tracklet t
        left join lateral (
          select l.episode_id
          from {schema}.episode_tracklet_link l
          where l.tracklet_id = t.id
          order by l.created_at, l.id
          limit 1
        ) x on true
        where t.gallery_target_id = :person_id
          and t.start_ts < :end_ts
          and coalesce(t.end_ts, t.start_ts) > :start_ts
        order by t.start_ts asc, t.id
        limit :limit
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {
                "person_id": person_id,
                "start_ts": start_ts,
                "end_ts": end_ts,
                "limit": int(limit),
            },
        ).mappings().all()

    return [
        TrackletRow(
            id=str(r["id"]),
            stream_id=str(r["stream_id"]),
            start_ts=r["start_ts"],
            end_ts=r["end_ts"],
            gallery_target_id=(str(r["gallery_target_id"]) if r["gallery_target_id"] is not None else None),
            gallery_similarity=(float(r["gallery_similarity"]) if r["gallery_similarity"] is not None else None),
            query_asset_base64=r["query_asset_base64"],
            frame_asset_base64=r["frame_asset_base64"],
            frame_end_base64=r["frame_end_base64"],
            trajectory_points=r["trajectory_points"],
            episode_id=(str(r["episode_id"]) if r["episode_id"] is not None else None),
        )
        for r in rows
    ]


def list_tracklets_for_persons(
    engine: Engine,
    schema: str,
    person_ids: list[str],
    start_ts: datetime,
    end_ts: datetime,
    limit: int = 200,
) -> list[TrackletRow]:
    """
    获取多个人员在指定时间范围内的所有轨迹记录
    
    Args:
        engine: 数据库引擎
        schema: 数据库schema
        person_ids: 人员ID列表
        start_ts: 开始时间
        end_ts: 结束时间
        limit: 最大返回数量
        
    Returns:
        TrackletRow 列表，按 person_id 和时间排序
    """
    if not person_ids:
        return []
    
    # 使用 ANY 或 IN 子句来查询多个 person_id
    sql = text(
        f"""
        select t.id, t.stream_id, t.start_ts, t.end_ts, t.gallery_target_id, t.gallery_similarity,
               t.query_asset_base64, t.frame_asset_base64, t.frame_end_base64, t.trajectory_points,
               x.episode_id
        from {schema}.tracklet t
        left join lateral (
          select l.episode_id
          from {schema}.episode_tracklet_link l
          where l.tracklet_id = t.id
          order by l.created_at, l.id
          limit 1
        ) x on true
        where t.gallery_target_id = ANY(:person_ids)
          and t.start_ts < :end_ts
          and coalesce(t.end_ts, t.start_ts) > :start_ts
        order by t.gallery_target_id, t.start_ts asc, t.id
        limit :limit
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {
                "person_ids": person_ids,
                "start_ts": start_ts,
                "end_ts": end_ts,
                "limit": int(limit),
            },
        ).mappings().all()

    return [
        TrackletRow(
            id=str(r["id"]),
            stream_id=str(r["stream_id"]),
            start_ts=r["start_ts"],
            end_ts=r["end_ts"],
            gallery_target_id=(str(r["gallery_target_id"]) if r["gallery_target_id"] is not None else None),
            gallery_similarity=(float(r["gallery_similarity"]) if r["gallery_similarity"] is not None else None),
            query_asset_base64=r["query_asset_base64"],
            frame_asset_base64=r["frame_asset_base64"],
            frame_end_base64=r["frame_end_base64"],
            trajectory_points=r["trajectory_points"],
            episode_id=(str(r["episode_id"]) if r["episode_id"] is not None else None),
        )
        for r in rows
    ]


def list_recent_tracklets_for_person(engine: Engine, schema: str, person_id: str, limit: int = 10) -> list[TrackletRow]:
    sql = text(
        f"""
        select t.id, t.stream_id, t.start_ts, t.end_ts, t.gallery_target_id, t.gallery_similarity,
               t.query_asset_base64, t.frame_asset_base64, t.frame_end_base64, t.trajectory_points,
               x.episode_id
        from {schema}.tracklet t
        left join lateral (
          select l.episode_id
          from {schema}.episode_tracklet_link l
          where l.tracklet_id = t.id
          order by l.created_at, l.id
          limit 1
        ) x on true
        where t.gallery_target_id = :person_id
        order by t.start_ts desc, t.id
        limit :limit
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(sql, {"person_id": person_id, "limit": int(limit)}).mappings().all()

    return [
        TrackletRow(
            id=str(r["id"]),
            stream_id=str(r["stream_id"]),
            start_ts=r["start_ts"],
            end_ts=r["end_ts"],
            gallery_target_id=(str(r["gallery_target_id"]) if r["gallery_target_id"] is not None else None),
            gallery_similarity=(float(r["gallery_similarity"]) if r["gallery_similarity"] is not None else None),
            query_asset_base64=r["query_asset_base64"],
            frame_asset_base64=r["frame_asset_base64"],
            frame_end_base64=r["frame_end_base64"],
            trajectory_points=r["trajectory_points"],
            episode_id=(str(r["episode_id"]) if r["episode_id"] is not None else None),
        )
        for r in rows
    ]
