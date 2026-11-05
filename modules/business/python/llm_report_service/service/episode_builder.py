from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from llm_report_service.db.episode_repo import EpisodeRow, TrackletRow
from llm_report_service.db.media_repo import MediaAssetRow
from llm_report_service.db.vad_repo import VadRow


@dataclass(frozen=True)
class EpisodeSemanticInput:
    episode_id: str
    time_range: dict
    camera_id: int | None
    person: dict
    trajectory: dict
    media: list[dict]


def _safe_get(d: Any, *keys: str):
    cur = d
    for k in keys:
        if cur is None:
            return None
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return None
    return cur


def _extract_base64(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        for k in ("image_base64", "base64", "data", "content"):
            vv = v.get(k)
            if isinstance(vv, str):
                return vv
    return None


def _normalize_points(v: Any, max_points: int = 64):
    if v is None:
        return None, 0
    points = v
    if isinstance(points, dict) and "points" in points:
        points = points.get("points")
    if not isinstance(points, list):
        return points, 0

    n = len(points)
    if n <= max_points:
        return points, n

    step = max(1, n // max_points)
    sampled = points[::step]
    if len(sampled) > max_points:
        sampled = sampled[:max_points]
    return sampled, n


def build_episode_semantic_input(
    episode: EpisodeRow,
    primary_tracklet: TrackletRow | None,
    media: list[dict],
    *,
    override_person_name: str | None = None,
) -> EpisodeSemanticInput:
    meta = episode.meta if isinstance(episode.meta, dict) else None

    camera_id = _safe_get(meta, "camera")
    person_name = override_person_name if override_person_name is not None else _safe_get(meta, "person_name")
    person_image = _extract_base64(_safe_get(meta, "person_image"))

    traj_color = _safe_get(meta, "trajectory_color")
    traj_points = _safe_get(meta, "trajectory_points", "points")

    if traj_color is None and primary_tracklet is not None:
        traj_color = primary_tracklet.color_rgb

    if traj_points is None and primary_tracklet is not None:
        traj_points = _safe_get(primary_tracklet.trajectory_points, "points")
        if traj_points is None:
            traj_points = primary_tracklet.trajectory_points

    if person_image is None and primary_tracklet is not None:
        person_image = _extract_base64(primary_tracklet.query_asset_base64)

    norm_points, point_count = _normalize_points(traj_points, max_points=64)

    return EpisodeSemanticInput(
        episode_id=episode.id,
        time_range={"start": episode.start_ts.isoformat(), "end": episode.end_ts.isoformat()},
        camera_id=int(camera_id) if camera_id is not None else None,
        person={"name": person_name, "image_base64": person_image},
        trajectory={"color_rgb": traj_color, "points": norm_points, "point_count": point_count},
        media=media,
    )


def build_vad_semantic_input(vad: VadRow, media_asset: MediaAssetRow | None, media: list[dict]) -> EpisodeSemanticInput:
    time_range = {"start": vad.created_at.isoformat(), "end": vad.created_at.isoformat()}

    return EpisodeSemanticInput(
        episode_id=str(vad.id),
        time_range=time_range,
        camera_id=None,
        person={
            "name": None,
            "image_base64": vad.frame_vad_base64,
            "anomaly_name": vad.anomaly_name,
            "anomaly_level": vad.anomaly_level,
        },
        trajectory={
            "color_rgb": None,
            "points": None,
            "point_count": 0,
            "anomaly_name": vad.anomaly_name,
            "anomaly_level": vad.anomaly_level,
        },
        media=media,
    )


def semantic_input_to_json_str(inp: EpisodeSemanticInput) -> str:
    def _redact_value(v: Any):
        if isinstance(v, str):
            if len(v) > 512:
                return f"[omitted len={len(v)}]"
            return v
        if isinstance(v, list):
            return [_redact_value(x) for x in v]
        if isinstance(v, dict):
            return {k: _redact_value(val) for k, val in v.items()}
        return v

    d = {
        "episode_id": inp.episode_id,
        "time_range": inp.time_range,
        "camera_id": inp.camera_id,
        "person": inp.person,
        "trajectory": inp.trajectory,
        "media": inp.media,
    }
    safe = _redact_value(d)
    return json.dumps(safe, ensure_ascii=False)
