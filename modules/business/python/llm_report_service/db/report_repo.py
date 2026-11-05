from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine


def has_llm_report(
    engine: Engine,
    schema: str,
    *,
    prompt_type: str,
    episode_id: str | None = None,
    vad_id: int | None = None,
) -> bool:
    if (episode_id is None and vad_id is None) or (episode_id is not None and vad_id is not None):
        raise ValueError("Exactly one of episode_id or vad_id must be provided")

    if episode_id is not None:
        sql = text(
            f"""
            select 1
            from {schema}.llm_report
            where episode_id = :episode_id
              and coalesce(prompt_type, '') = :prompt_type
            limit 1
            """
        )
        params = {"episode_id": episode_id, "prompt_type": prompt_type}
    else:
        sql = text(
            f"""
            select 1
            from {schema}.llm_report
            where vad_id = :vad_id
              and coalesce(prompt_type, '') = :prompt_type
            limit 1
            """
        )
        params = {"vad_id": vad_id, "prompt_type": prompt_type}

    with engine.connect() as conn:
        v = conn.execute(sql, params).scalar()

    return v is not None


def save_llm_report(
    engine: Engine,
    schema: str,
    *,
    prompt_type: str,
    episode_id: str | None = None,
    vad_id: int | None = None,
    report_json: dict,
    report_text: str | None,
) -> str:
    if (episode_id is None and vad_id is None) or (episode_id is not None and vad_id is not None):
        raise ValueError("Exactly one of episode_id or vad_id must be provided")

    if episode_id is not None:
        check_sql = text(
            f"""
            select id
            from {schema}.llm_report
            where episode_id = :episode_id
              and coalesce(prompt_type, '') = :prompt_type
            limit 1
            """
        )
        check_params = {"episode_id": episode_id, "prompt_type": prompt_type}
    else:
        check_sql = text(
            f"""
            select id
            from {schema}.llm_report
            where vad_id = :vad_id
              and coalesce(prompt_type, '') = :prompt_type
            limit 1
            """
        )
        check_params = {"vad_id": vad_id, "prompt_type": prompt_type}

    with engine.connect() as conn:
        existed = conn.execute(check_sql, check_params).scalar()

    if existed is not None:
        return str(existed)

    new_id = str(uuid4())
    now = datetime.now(timezone.utc)
    insert_sql = text(
        f"""
        insert into {schema}.llm_report (id, episode_id, vad_id, prompt_type, report_json, report_text, created_at)
        values (:id, :episode_id, :vad_id, :prompt_type, cast(:report_json as jsonb), :report_text, :created_at)
        """
    )

    payload = {
        "id": new_id,
        "episode_id": episode_id,
        "vad_id": vad_id,
        "prompt_type": prompt_type,
        "report_json": json.dumps(report_json, ensure_ascii=False),
        "report_text": report_text,
        "created_at": now,
    }

    with engine.begin() as conn:
        conn.execute(insert_sql, payload)

    return new_id
