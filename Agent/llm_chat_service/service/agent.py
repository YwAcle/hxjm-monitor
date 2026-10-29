from __future__ import annotations

import json
from datetime import datetime

from llm_chat_service.config import DbConfig, ServiceConfig
from llm_chat_service.db.reid_repo import get_person_by_id, get_person_by_name
from llm_chat_service.db.report_repo import list_reports_for_person, list_reports_global
from llm_chat_service.db.tracklet_repo import list_recent_tracklets_for_person, list_tracklets_for_person
from llm_chat_service.llm.model import ChatSGLang
from llm_chat_service.service.summarizer import summarize
from llm_chat_service.tools.frequency import compute_frequency
from llm_chat_service.tools.image_identify import identify_person_by_image
from llm_chat_service.tools.person_guess import guess_person_name
from llm_chat_service.tools.playback import build_playbacks
from llm_chat_service.tools.time_parser import parse_time_range
from llm_report_service.llm.sglang_model import SGLangRequestError


def _json(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _truncate_text(s: str | None, max_chars: int) -> str | None:
    if s is None:
        return None
    s = str(s)
    if len(s) <= int(max_chars):
        return s
    return s[: int(max_chars)] + "..."


def _fallback_answer(prompt: str, person: dict | None, time_range: dict, reports_brief: list[dict]) -> dict:
    name = person.get("name") if isinstance(person, dict) else None
    head = f"{name}在{time_range.get('label')}的事件摘要" if name else f"{time_range.get('label')}的事件摘要"
    lines: list[str] = [head]
    for r in reports_brief[:20]:
        ts = r.get("ts") or ""
        summary = r.get("summary") or r.get("text") or ""
        summary = _truncate_text(str(summary), 200) or ""
        if summary.strip() != "":
            lines.append(f"- {ts} {summary}")

    if len(lines) == 1:
        lines.append("- 未找到可用的事件报告，请缩小时间范围或确认该人员是否有轨迹。")

    return {
        "answer_text": "\n".join(lines),
        "timeline": [],
        "anomalies": [],
    }


def run_chat(
    *,
    engine,
    db_cfg: DbConfig,
    svc_cfg: ServiceConfig,
    llm: ChatSGLang,
    prompt: str,
    person_name: str | None = None,
    time_hint: str | None = None,
    top_k: int | None = None,
    image_bytes: bytes | None = None,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now().astimezone()

    tr = parse_time_range(time_hint or prompt, now=now, tz=svc_cfg.tz)
    time_range = {"start_ts": tr.start_ts.isoformat(), "end_ts": tr.end_ts.isoformat(), "label": tr.label}

    if tr.start_ts > now:
        return {
            "query": prompt,
            "time_range": time_range,
            "person": None,
            "frequency": {"count": 0, "by_hour": [], "by_camera": [], "avg_dwell_s": 0.0, "total_dwell_s": 0.0},
            "timeline": [],
            "playbacks": [],
            "anomalies": [],
            "answer_text": "未来时间在监控系统中不适用哦，请调整为今天/昨天/前天等历史时间范围。",
        }

    name = (person_name or "").strip() or guess_person_name(prompt) or None
    person: dict | None = None

    image_hint: dict | None = None
    if image_bytes is not None:
        k = int(top_k) if top_k is not None else 3
        image_hint = identify_person_by_image(
            engine=engine,
            schema=db_cfg.schema,
            image_bytes=image_bytes,
            top_k=k,
        )

        if name is None and image_hint.get("type") == "gallery":
            name = image_hint.get("name")

    if name is not None:
        p = get_person_by_name(engine, db_cfg.schema, name)
        if p is not None:
            person = {
                "type": "gallery",
                "id": p.id,
                "name": p.name,
                "image_base64": p.image_base64,
                "candidates": (image_hint.get("candidates") if isinstance(image_hint, dict) else []) or [],
            }

    if person is None and isinstance(image_hint, dict) and image_hint.get("type") == "gallery":
        pid = image_hint.get("id")
        if pid is not None:
            p = get_person_by_id(engine, db_cfg.schema, str(pid))
            if p is not None:
                person = {
                    "type": "gallery",
                    "id": p.id,
                    "name": p.name,
                    "image_base64": p.image_base64,
                    "candidates": image_hint.get("candidates") or [],
                }

    is_global_anomaly = (person is None) and ("异常" in (prompt or ""))

    if person is None and not is_global_anomaly:
        return {
            "query": prompt,
            "time_range": time_range,
            "person": None,
            "frequency": {"count": 0, "by_hour": [], "by_camera": [], "avg_dwell_s": 0.0, "total_dwell_s": 0.0},
            "timeline": [],
            "playbacks": [],
            "anomalies": [],
            "answer_text": "未识别到要查询的人员，请补充姓名或上传图片。",
        }

    if person is None:
        reports = list_reports_global(engine, db_cfg.schema, tr.start_ts, tr.end_ts, limit=int(svc_cfg.report_limit))
        report_brief = [
            {
                "episode_id": r.episode_id,
                "ts": (r.episode_start_ts or r.created_at).isoformat() if (r.episode_start_ts or r.created_at) else None,
                "text": _truncate_text(r.report_text, 300),
                "summary": _truncate_text((r.report_json or {}).get("summary") if isinstance(r.report_json, dict) else None, 300),
                "risk_level": (r.report_json or {}).get("risk_level") if isinstance(r.report_json, dict) else None,
            }
            for r in reports
        ]

        llm_reports = report_brief[: min(50, int(svc_cfg.report_limit))]

        try:
            text, parsed = summarize(
                llm,
                query=prompt,
                time_range_json=_json(time_range),
                person_json=_json(None),
                frequency_json=_json({}),
                tracklet_brief_json=_json([]),
                report_brief_json=_json(llm_reports),
                tracklet_limit=0,
                report_limit=len(llm_reports),
                max_new_tokens=256,
            )
        except SGLangRequestError as exc:
            if not exc.is_out_of_memory:
                raise
            parsed = _fallback_answer(prompt, None, time_range, llm_reports)
            text = parsed.get("answer_text") or ""

        return {
            "query": prompt,
            "time_range": time_range,
            "person": None,
            "frequency": {"count": 0, "by_hour": [], "by_camera": [], "avg_dwell_s": 0.0, "total_dwell_s": 0.0},
            "timeline": parsed.get("timeline", []),
            "playbacks": [],
            "anomalies": parsed.get("anomalies", []),
            "answer_text": parsed.get("answer_text") or text,
        }

    pid = person.get("id")
    tracklets = list_tracklets_for_person(
        engine,
        db_cfg.schema,
        person_id=str(pid),
        start_ts=tr.start_ts,
        end_ts=tr.end_ts,
        limit=int(svc_cfg.tracklet_limit),
    )

    frequency = compute_frequency(tracklets)

    if top_k is None:
        top_k = int(svc_cfg.playback_top_n)

    recent_for_playback = list_recent_tracklets_for_person(engine, db_cfg.schema, person_id=str(pid), limit=int(top_k))
    playbacks = build_playbacks(engine, db_cfg.schema, recent_for_playback, cfg=svc_cfg, top_n=int(top_k))

    reports = list_reports_for_person(engine, db_cfg.schema, str(pid), tr.start_ts, tr.end_ts, limit=int(svc_cfg.report_limit))
    report_brief = [
        {
            "episode_id": r.episode_id,
            "ts": (r.episode_start_ts or r.created_at).isoformat() if (r.episode_start_ts or r.created_at) else None,
            "text": _truncate_text(r.report_text, 300),
            "summary": _truncate_text((r.report_json or {}).get("summary") if isinstance(r.report_json, dict) else None, 300),
            "risk_level": (r.report_json or {}).get("risk_level") if isinstance(r.report_json, dict) else None,
        }
        for r in reports
    ]

    tracklet_brief = [
        {
            "tracklet_id": t.id,
            "episode_id": t.episode_id,
            "start_ts": t.start_ts.isoformat(),
            "end_ts": (t.end_ts or t.start_ts).isoformat(),
            "stream_id": t.stream_id,
        }
        for t in tracklets
    ]

    llm_tracklets = tracklet_brief[: min(30, int(svc_cfg.tracklet_limit))]
    llm_reports = report_brief[: min(50, int(svc_cfg.report_limit))]

    try:
        text, parsed = summarize(
            llm,
            query=prompt,
            time_range_json=_json(time_range),
            person_json=_json(
                {
                    "type": person.get("type"),
                    "id": person.get("id"),
                    "name": person.get("name"),
                }
            ),
            frequency_json=_json(frequency),
            tracklet_brief_json=_json(llm_tracklets),
            report_brief_json=_json(llm_reports),
            tracklet_limit=len(llm_tracklets),
            report_limit=len(llm_reports),
            max_new_tokens=256,
        )
    except SGLangRequestError as exc:
        if not exc.is_out_of_memory:
            raise
        parsed = _fallback_answer(prompt, person, time_range, llm_reports)
        text = parsed.get("answer_text") or ""

    return {
        "query": prompt,
        "time_range": time_range,
        "person": person,
        "frequency": frequency,
        "timeline": parsed.get("timeline", []),
        "playbacks": playbacks,
        "anomalies": parsed.get("anomalies", []),
        "answer_text": parsed.get("answer_text") or text,
    }
