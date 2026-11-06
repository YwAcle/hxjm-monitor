"""
VAD 异常数据访问层 - vad 表
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class VADRow:
    """VAD 数据行"""
    id: int
    created_at: datetime
    media_asset_id: Optional[str]
    stream_id: str
    frame_vad_base64: Optional[str]
    anomaly_name: Optional[str]
    anomaly_level: Optional[int]
    # 关联的摄像头信息
    camera_id: Optional[str] = None
    camera_name: Optional[str] = None
    camera_location: Optional[str] = None


# 异常等级说明
ANOMALY_LEVEL_MAP = {
    1: "ROI区域停留",
    2: "跌倒",
    3: "打架",
    4: "火灾/烟雾",
}

# 异常名称中英文映射
ANOMALY_NAME_CN_MAP = {
    "fall": "跌倒",
    "fight": "打架",
    "fire": "火灾",
    "smoke": "烟雾",
    "intrusion": "入侵",
    "loitering": "徘徊",
    "roi_stay": "区域停留",
}


def list_vad_anomalies(
    engine: Engine,
    schema: str,
    start_ts: datetime,
    end_ts: datetime,
    anomaly_name: Optional[str] = None,
    min_level: Optional[int] = None,
    limit: int = 100,
) -> list[VADRow]:
    """
    获取时间范围内的 VAD 异常记录
    
    Args:
        engine: 数据库引擎
        schema: 数据库schema
        start_ts: 开始时间
        end_ts: 结束时间
        anomaly_name: 可选，按异常类型筛选
        min_level: 可选，最低异常等级
        limit: 最大返回数量
        
    Returns:
        VADRow 列表
    """
    where_clauses = [
        "v.created_at >= :start_ts",
        "v.created_at < :end_ts",
    ]
    params = {
        "start_ts": start_ts,
        "end_ts": end_ts,
        "limit": limit,
    }
    
    if anomaly_name:
        where_clauses.append("v.anomaly_name = :anomaly_name")
        params["anomaly_name"] = anomaly_name
    
    if min_level is not None:
        where_clauses.append("v.anomaly_level >= :min_level")
        params["min_level"] = min_level
    
    where_sql = " AND ".join(where_clauses)
    
    sql = text(
        f"""
        SELECT 
            v.id,
            v.created_at,
            v.media_asset_id,
            v.stream_id,
            v.frame_vad_base64,
            v.anomaly_name,
            v.anomaly_level,
            cs.camera_id,
            c.camera_code as camera_name,
            c.location as camera_location
        FROM {schema}.vad v
        LEFT JOIN {schema}.camera_stream cs ON cs.id::text = v.stream_id
        LEFT JOIN {schema}.camera c ON c.id = cs.camera_id
        WHERE {where_sql}
        ORDER BY v.created_at DESC
        LIMIT :limit
        """
    )
    
    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()
    
    return [
        VADRow(
            id=int(row["id"]),
            created_at=row["created_at"],
            media_asset_id=str(row["media_asset_id"]) if row["media_asset_id"] else None,
            stream_id=str(row["stream_id"]) if row["stream_id"] else "",
            frame_vad_base64=str(row["frame_vad_base64"]) if row["frame_vad_base64"] else None,
            anomaly_name=str(row["anomaly_name"]) if row["anomaly_name"] else None,
            anomaly_level=int(row["anomaly_level"]) if row["anomaly_level"] else None,
            camera_id=str(row["camera_id"]) if row["camera_id"] else None,
            camera_name=str(row["camera_name"]) if row["camera_name"] else None,
            camera_location=str(row["camera_location"]) if row["camera_location"] else None,
        )
        for row in rows
    ]


def list_recent_vad_anomalies(
    engine: Engine,
    schema: str,
    limit: int = 20,
) -> list[VADRow]:
    """跨日期按时间倒序查询最近的异常事件。"""

    sql = text(
        f"""
        SELECT
            v.id, v.created_at, v.media_asset_id, v.stream_id,
            v.frame_vad_base64, v.anomaly_name, v.anomaly_level,
            cs.camera_id, c.camera_code AS camera_name, c.location AS camera_location
        FROM {schema}.vad v
        LEFT JOIN {schema}.camera_stream cs ON cs.id::text = v.stream_id
        LEFT JOIN {schema}.camera c ON c.id = cs.camera_id
        ORDER BY v.created_at DESC
        LIMIT :limit
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"limit": limit}).mappings().all()
    return [
        VADRow(
            id=int(row["id"]),
            created_at=row["created_at"],
            media_asset_id=str(row["media_asset_id"]) if row["media_asset_id"] else None,
            stream_id=str(row["stream_id"]) if row["stream_id"] else "",
            frame_vad_base64=str(row["frame_vad_base64"]) if row["frame_vad_base64"] else None,
            anomaly_name=str(row["anomaly_name"]) if row["anomaly_name"] else None,
            anomaly_level=int(row["anomaly_level"]) if row["anomaly_level"] else None,
            camera_id=str(row["camera_id"]) if row["camera_id"] else None,
            camera_name=str(row["camera_name"]) if row["camera_name"] else None,
            camera_location=str(row["camera_location"]) if row["camera_location"] else None,
        )
        for row in rows
    ]


def get_anomaly_stats(
    engine: Engine,
    schema: str,
    start_ts: datetime,
    end_ts: datetime,
) -> dict:
    """
    获取时间范围内的异常统计
    
    Args:
        engine: 数据库引擎
        schema: 数据库schema
        start_ts: 开始时间
        end_ts: 结束时间
        
    Returns:
        统计字典 {level_1: count, level_2: count, ...}
    """
    sql = text(
        f"""
        SELECT 
            anomaly_level,
            COUNT(*) as count
        FROM {schema}.vad
        WHERE created_at >= :start_ts
          AND created_at < :end_ts
          AND anomaly_level IS NOT NULL
        GROUP BY anomaly_level
        ORDER BY anomaly_level
        """
    )
    
    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {"start_ts": start_ts, "end_ts": end_ts},
        ).mappings().all()
    
    stats = {"level_1": 0, "level_2": 0, "level_3": 0, "level_4": 0}
    for row in rows:
        level = row["anomaly_level"]
        if 1 <= level <= 4:
            stats[f"level_{level}"] = int(row["count"])
    
    return stats


def get_anomaly_count_by_type(
    engine: Engine,
    schema: str,
    start_ts: datetime,
    end_ts: datetime,
) -> dict:
    """
    按异常类型统计数量
    
    Args:
        engine: 数据库引擎
        schema: 数据库schema
        start_ts: 开始时间
        end_ts: 结束时间
        
    Returns:
        统计字典 {anomaly_name: count}
    """
    sql = text(
        f"""
        SELECT 
            anomaly_name,
            COUNT(*) as count
        FROM {schema}.vad
        WHERE created_at >= :start_ts
          AND created_at < :end_ts
          AND anomaly_name IS NOT NULL
        GROUP BY anomaly_name
        ORDER BY count DESC
        """
    )
    
    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {"start_ts": start_ts, "end_ts": end_ts},
        ).mappings().all()
    
    return {
        str(row["anomaly_name"]): int(row["count"])
        for row in rows
    }
