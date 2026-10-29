"""
报告数据访问层 - llm_report 和 episode 表
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class LlmReportRow:
    """LLM 报告数据行"""
    id: str
    episode_id: str
    prompt_version: Optional[str]
    report_text: Optional[str]
    report_json: Optional[dict]
    created_at: Optional[datetime]
    # episode 信息
    episode_title: Optional[str] = None
    episode_start_ts: Optional[datetime] = None
    episode_end_ts: Optional[datetime] = None
    target_id: Optional[str] = None
    stranger_target_id: Optional[str] = None


def list_reports_by_time(
    engine: Engine,
    schema: str,
    start_ts: datetime,
    end_ts: datetime,
    limit: int = 50,
) -> list[LlmReportRow]:
    """
    获取时间范围内的 LLM 报告
    
    Args:
        engine: 数据库引擎
        schema: 数据库schema
        start_ts: 开始时间
        end_ts: 结束时间
        limit: 最大返回数量
        
    Returns:
        LlmReportRow 列表
    """
    sql = text(
        f"""
        SELECT 
            r.id as report_id,
            r.episode_id,
            r.prompt_version,
            r.report_text,
            r.report_json,
            r.created_at,
            e.title as episode_title,
            e.start_ts as episode_start_ts,
            e.end_ts as episode_end_ts,
            e.target_id,
            e.stranger_target_id
        FROM {schema}.llm_report r
        LEFT JOIN {schema}.episode e ON e.id = r.episode_id
        LEFT JOIN {schema}.vad v ON v.id = r.vad_id
        WHERE (e.start_ts < :end_ts AND e.end_ts > :start_ts)
           OR (r.vad_id IS NOT NULL AND v.created_at >= :start_ts AND v.created_at < :end_ts)
           OR (r.episode_id IS NULL AND r.vad_id IS NULL
               AND r.created_at >= :start_ts AND r.created_at < :end_ts)
        ORDER BY COALESCE(e.start_ts, v.created_at, r.created_at) DESC, r.created_at DESC
        LIMIT :limit
        """
    )
    
    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {"start_ts": start_ts, "end_ts": end_ts, "limit": limit},
        ).mappings().all()
    
    result = []
    for row in rows:
        report_json = row["report_json"]
        if isinstance(report_json, str):
            try:
                report_json = json.loads(report_json)
            except Exception:
                report_json = None
        
        result.append(
            LlmReportRow(
                id=str(row["report_id"]),
                episode_id=str(row["episode_id"]) if row["episode_id"] is not None else "",
                prompt_version=str(row["prompt_version"]) if row["prompt_version"] else None,
                report_text=str(row["report_text"]) if row["report_text"] else None,
                report_json=report_json,
                created_at=row["created_at"],
                episode_title=str(row["episode_title"]) if row["episode_title"] else None,
                episode_start_ts=row["episode_start_ts"],
                episode_end_ts=row["episode_end_ts"],
                target_id=str(row["target_id"]) if row["target_id"] else None,
                stranger_target_id=str(row["stranger_target_id"]) if row["stranger_target_id"] else None,
            )
        )
    
    return result


def list_reports_for_person(
    engine: Engine,
    schema: str,
    person_id: str,
    start_ts: datetime,
    end_ts: datetime,
    limit: int = 50,
) -> list[LlmReportRow]:
    """
    获取指定人员在时间范围内的 LLM 报告
    
    Args:
        engine: 数据库引擎
        schema: 数据库schema
        person_id: 人员ID
        start_ts: 开始时间
        end_ts: 结束时间
        limit: 最大返回数量
        
    Returns:
        LlmReportRow 列表
    """
    sql = text(
        f"""
        SELECT DISTINCT
            r.id as report_id,
            r.episode_id,
            r.prompt_version,
            r.report_text,
            r.report_json,
            r.created_at,
            e.title as episode_title,
            e.start_ts as episode_start_ts,
            e.end_ts as episode_end_ts,
            e.target_id,
            e.stranger_target_id
        FROM {schema}.llm_report r
        JOIN {schema}.episode e ON e.id = r.episode_id
        JOIN {schema}.episode_tracklet_link etl ON etl.episode_id = e.id
        JOIN {schema}.tracklet t ON t.id = etl.tracklet_id
        WHERE t.gallery_target_id = :person_id
          AND e.start_ts < :end_ts
          AND e.end_ts > :start_ts
        ORDER BY e.start_ts DESC, r.created_at DESC
        LIMIT :limit
        """
    )
    
    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {"person_id": person_id, "start_ts": start_ts, "end_ts": end_ts, "limit": limit},
        ).mappings().all()
    
    result = []
    for row in rows:
        report_json = row["report_json"]
        if isinstance(report_json, str):
            try:
                report_json = json.loads(report_json)
            except Exception:
                report_json = None
        
        result.append(
            LlmReportRow(
                id=str(row["report_id"]),
                episode_id=str(row["episode_id"]),
                prompt_version=str(row["prompt_version"]) if row["prompt_version"] else None,
                report_text=str(row["report_text"]) if row["report_text"] else None,
                report_json=report_json,
                created_at=row["created_at"],
                episode_title=str(row["episode_title"]) if row["episode_title"] else None,
                episode_start_ts=row["episode_start_ts"],
                episode_end_ts=row["episode_end_ts"],
                target_id=str(row["target_id"]) if row["target_id"] else None,
                stranger_target_id=str(row["stranger_target_id"]) if row["stranger_target_id"] else None,
            )
        )
    
    return result


def get_reports_with_risk_level(
    engine: Engine,
    schema: str,
    start_ts: datetime,
    end_ts: datetime,
    min_risk_level: int = 1,
    limit: int = 50,
) -> list[LlmReportRow]:
    """
    获取带有风险等级的报告（用于异常查询）
    
    Args:
        engine: 数据库引擎
        schema: 数据库schema
        start_ts: 开始时间
        end_ts: 结束时间
        min_risk_level: 最低风险等级
        limit: 最大返回数量
        
    Returns:
        LlmReportRow 列表
    """
    # 注意：report_json 中的 risk_level 需要在应用层过滤
    reports = list_reports_by_time(engine, schema, start_ts, end_ts, limit * 2)
    
    # 过滤出有风险等级的报告
    filtered = []
    for report in reports:
        if report.report_json and isinstance(report.report_json, dict):
            risk_level = report.report_json.get("risk_level")
            if risk_level is not None and risk_level >= min_risk_level:
                filtered.append(report)
                if len(filtered) >= limit:
                    break
    
    return filtered
