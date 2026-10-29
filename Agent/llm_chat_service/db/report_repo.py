from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class LlmReportRow:
    id: str
    episode_id: str
    prompt_type: str | None
    report_text: str | None
    report_json: Any
    created_at: datetime | None
    episode_start_ts: datetime | None
    episode_end_ts: datetime | None


def list_reports_for_person(
    engine: Engine,
    schema: str,
    person_id: str,
    start_ts: datetime,
    end_ts: datetime,
    limit: int = 200,
) -> list[LlmReportRow]:
    sql = text(
        f"""
        select r.id as report_id, r.episode_id, r.prompt_type, r.report_text, r.report_json, r.created_at,
               e.start_ts as episode_start_ts, e.end_ts as episode_end_ts
        from {schema}.tracklet t
        join {schema}.episode_tracklet_link l on l.tracklet_id = t.id
        join {schema}.episode e on e.id = l.episode_id
        join {schema}.llm_report r on r.episode_id = e.id
        where t.gallery_target_id = :person_id
          and t.start_ts < :end_ts
          and coalesce(t.end_ts, t.start_ts) > :start_ts
        order by e.start_ts asc, r.created_at asc, r.id
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

    out: list[LlmReportRow] = []
    for r in rows:
        report_json = r["report_json"]
        if isinstance(report_json, str):
            try:
                report_json = json.loads(report_json)
            except Exception:
                pass
        out.append(
            LlmReportRow(
                id=str(r["report_id"]),
                episode_id=str(r["episode_id"]),
                prompt_type=(str(r["prompt_type"]) if r["prompt_type"] is not None else None),
                report_text=(str(r["report_text"]) if r["report_text"] is not None else None),
                report_json=report_json,
                created_at=r["created_at"],
                episode_start_ts=r["episode_start_ts"],
                episode_end_ts=r["episode_end_ts"],
            )
        )

    return out


def list_reports_for_persons(
    engine: Engine,
    schema: str,
    person_ids: list[str],
    start_ts: datetime,
    end_ts: datetime,
    limit: int = 200,
) -> list[dict]:
    """
    获取多个人员在指定时间范围内的事件报告
    
    Args:
        engine: 数据库引擎
        schema: 数据库schema
        person_ids: 人员ID列表
        start_ts: 开始时间
        end_ts: 结束时间
        limit: 最大返回数量
        
    Returns:
        字典列表，每个字典包含 {"report": LlmReportRow, "person_id": str}，按 person_id 和时间排序
    """
    if not person_ids:
        return []
    
    sql = text(
        f"""
        select r.id as report_id, r.episode_id, r.prompt_type, r.report_text, r.report_json, r.created_at,
               e.start_ts as episode_start_ts, e.end_ts as episode_end_ts, t.gallery_target_id
        from {schema}.tracklet t
        join {schema}.episode_tracklet_link l on l.tracklet_id = t.id
        join {schema}.episode e on e.id = l.episode_id
        join {schema}.llm_report r on r.episode_id = e.id
        where t.gallery_target_id = ANY(:person_ids)
          and t.start_ts < :end_ts
          and coalesce(t.end_ts, t.start_ts) > :start_ts
        order by t.gallery_target_id, e.start_ts asc, r.created_at asc, r.id
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

    # 对于多人员查询，我们需要返回 person_id，但 LlmReportRow 不支持
    # 所以返回一个包含 person_id 的字典列表
    out: list[dict] = []
    for r in rows:
        report_json = r["report_json"]
        if isinstance(report_json, str):
            try:
                report_json = json.loads(report_json)
            except Exception:
                pass
        report_row = LlmReportRow(
            id=str(r["report_id"]),
            episode_id=str(r["episode_id"]),
            prompt_type=(str(r["prompt_type"]) if r["prompt_type"] is not None else None),
            report_text=(str(r["report_text"]) if r["report_text"] is not None else None),
            report_json=report_json,
            created_at=r["created_at"],
            episode_start_ts=r["episode_start_ts"],
            episode_end_ts=r["episode_end_ts"],
        )
        # 包含 person_id 信息
        out.append({
            "report": report_row,
            "person_id": str(r["gallery_target_id"]) if r["gallery_target_id"] is not None else None,
        })

    return out


def list_reports_global(engine: Engine, schema: str, start_ts: datetime, end_ts: datetime, limit: int = 200) -> list[LlmReportRow]:
    sql = text(
        f"""
        select r.id as report_id, r.episode_id, r.prompt_type, r.report_text, r.report_json, r.created_at,
               e.start_ts as episode_start_ts, e.end_ts as episode_end_ts
        from {schema}.llm_report r
        left join {schema}.episode e on e.id = r.episode_id
        left join {schema}.vad v on v.id = r.vad_id
        where (
            e.start_ts < :end_ts and e.end_ts > :start_ts
        ) or (
            r.vad_id is not null and v.created_at >= :start_ts and v.created_at < :end_ts
        ) or (
            r.episode_id is null and r.vad_id is null
            and r.created_at >= :start_ts and r.created_at < :end_ts
        )
        order by coalesce(e.start_ts, v.created_at, r.created_at) asc, r.created_at asc, r.id
        limit :limit
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {
                "start_ts": start_ts,
                "end_ts": end_ts,
                "limit": int(limit),
            },
        ).mappings().all()

    out: list[LlmReportRow] = []
    for r in rows:
        report_json = r["report_json"]
        if isinstance(report_json, str):
            try:
                report_json = json.loads(report_json)
            except Exception:
                pass
        out.append(
            LlmReportRow(
                id=str(r["report_id"]),
                episode_id=str(r["episode_id"]) if r["episode_id"] is not None else "",
                prompt_type=(str(r["prompt_type"]) if r["prompt_type"] is not None else None),
                report_text=(str(r["report_text"]) if r["report_text"] is not None else None),
                report_json=report_json,
                created_at=r["created_at"],
                episode_start_ts=r["episode_start_ts"],
                episode_end_ts=r["episode_end_ts"],
            )
        )

    return out
