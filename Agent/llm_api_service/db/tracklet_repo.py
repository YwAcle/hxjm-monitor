"""
轨迹数据访问层 - tracklet 表
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class TrackletRow:
    """轨迹数据行"""
    id: str
    stream_id: str
    start_ts: datetime
    end_ts: Optional[datetime]
    cls_name: str
    query_asset_base64: Optional[str]
    frame_asset_base64: Optional[str]
    gallery_target_id: Optional[str]
    gallery_similarity: Optional[float]
    # 关联的摄像头信息
    camera_id: Optional[str] = None
    camera_name: Optional[str] = None
    camera_location: Optional[str] = None


@dataclass
class CameraStatRow:
    """摄像头统计"""
    stream_id: str
    camera_name: str
    location: Optional[str]
    count: int


def list_tracklets_for_person(
    engine: Engine,
    schema: str,
    person_id: str,
    start_ts: datetime,
    end_ts: datetime,
    limit: int = 100,
) -> list[TrackletRow]:
    """
    获取指定人员在时间范围内的轨迹
    
    Args:
        engine: 数据库引擎
        schema: 数据库schema
        person_id: 人员ID (gallery_target_id)
        start_ts: 开始时间
        end_ts: 结束时间
        limit: 最大返回数量
        
    Returns:
        TrackletRow 列表
    """
    sql = text(
        f"""
        SELECT 
            t.id,
            t.stream_id,
            t.start_ts,
            t.end_ts,
            t.cls_name,
            t.query_asset_base64,
            t.frame_asset_base64,
            t.gallery_target_id,
            t.gallery_similarity,
            cs.camera_id,
            c.camera_code as camera_name,
            c.location as camera_location
        FROM {schema}.tracklet t
        LEFT JOIN {schema}.camera_stream cs ON cs.id = t.stream_id
        LEFT JOIN {schema}.camera c ON c.id = cs.camera_id
        WHERE t.gallery_target_id = :person_id
          AND t.start_ts < :end_ts
          AND COALESCE(t.end_ts, t.start_ts) > :start_ts
        ORDER BY t.start_ts ASC
        LIMIT :limit
        """
    )
    
    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {
                "person_id": person_id,
                "start_ts": start_ts,
                "end_ts": end_ts,
                "limit": limit,
            },
        ).mappings().all()
    
    return [
        TrackletRow(
            id=str(row["id"]),
            stream_id=str(row["stream_id"]) if row["stream_id"] else "",
            start_ts=row["start_ts"],
            end_ts=row["end_ts"],
            cls_name=str(row["cls_name"]) if row["cls_name"] else "person",
            query_asset_base64=str(row["query_asset_base64"]) if row["query_asset_base64"] else None,
            frame_asset_base64=str(row["frame_asset_base64"]) if row["frame_asset_base64"] else None,
            gallery_target_id=str(row["gallery_target_id"]) if row["gallery_target_id"] else None,
            gallery_similarity=float(row["gallery_similarity"]) if row["gallery_similarity"] else None,
            camera_id=str(row["camera_id"]) if row["camera_id"] else None,
            camera_name=str(row["camera_name"]) if row["camera_name"] else None,
            camera_location=str(row["camera_location"]) if row["camera_location"] else None,
        )
        for row in rows
    ]


def get_camera_stats_for_person(
    engine: Engine,
    schema: str,
    person_id: str,
    start_ts: datetime,
    end_ts: datetime,
) -> list[CameraStatRow]:
    """
    获取指定人员在时间范围内各摄像头的轨迹统计
    
    Args:
        engine: 数据库引擎
        schema: 数据库schema
        person_id: 人员ID
        start_ts: 开始时间
        end_ts: 结束时间
        
    Returns:
        CameraStatRow 列表
    """
    sql = text(
        f"""
        SELECT 
            t.stream_id,
            COALESCE(c.camera_code, t.stream_id) as camera_name,
            c.location,
            COUNT(*) as count
        FROM {schema}.tracklet t
        LEFT JOIN {schema}.camera_stream cs ON cs.id = t.stream_id
        LEFT JOIN {schema}.camera c ON c.id = cs.camera_id
        WHERE t.gallery_target_id = :person_id
          AND t.start_ts < :end_ts
          AND COALESCE(t.end_ts, t.start_ts) > :start_ts
        GROUP BY t.stream_id, c.camera_code, c.location
        ORDER BY count DESC
        """
    )
    
    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {
                "person_id": person_id,
                "start_ts": start_ts,
                "end_ts": end_ts,
            },
        ).mappings().all()
    
    return [
        CameraStatRow(
            stream_id=str(row["stream_id"]) if row["stream_id"] else "",
            camera_name=str(row["camera_name"]) if row["camera_name"] else "",
            location=str(row["location"]) if row["location"] else None,
            count=int(row["count"]),
        )
        for row in rows
    ]


def list_recent_tracklets_for_person(
    engine: Engine,
    schema: str,
    person_id: str,
    limit: int = 10,
) -> list[TrackletRow]:
    """
    获取指定人员最近的轨迹
    
    Args:
        engine: 数据库引擎
        schema: 数据库schema
        person_id: 人员ID
        limit: 最大返回数量
        
    Returns:
        TrackletRow 列表
    """
    sql = text(
        f"""
        SELECT 
            t.id,
            t.stream_id,
            t.start_ts,
            t.end_ts,
            t.cls_name,
            t.query_asset_base64,
            t.frame_asset_base64,
            t.gallery_target_id,
            t.gallery_similarity,
            cs.camera_id,
            c.camera_code as camera_name,
            c.location as camera_location
        FROM {schema}.tracklet t
        LEFT JOIN {schema}.camera_stream cs ON cs.id = t.stream_id
        LEFT JOIN {schema}.camera c ON c.id = cs.camera_id
        WHERE t.gallery_target_id = :person_id
        ORDER BY t.start_ts DESC
        LIMIT :limit
        """
    )
    
    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {"person_id": person_id, "limit": limit},
        ).mappings().all()
    
    return [
        TrackletRow(
            id=str(row["id"]),
            stream_id=str(row["stream_id"]) if row["stream_id"] else "",
            start_ts=row["start_ts"],
            end_ts=row["end_ts"],
            cls_name=str(row["cls_name"]) if row["cls_name"] else "person",
            query_asset_base64=str(row["query_asset_base64"]) if row["query_asset_base64"] else None,
            frame_asset_base64=str(row["frame_asset_base64"]) if row["frame_asset_base64"] else None,
            gallery_target_id=str(row["gallery_target_id"]) if row["gallery_target_id"] else None,
            gallery_similarity=float(row["gallery_similarity"]) if row["gallery_similarity"] else None,
            camera_id=str(row["camera_id"]) if row["camera_id"] else None,
            camera_name=str(row["camera_name"]) if row["camera_name"] else None,
            camera_location=str(row["camera_location"]) if row["camera_location"] else None,
        )
        for row in rows
    ]

