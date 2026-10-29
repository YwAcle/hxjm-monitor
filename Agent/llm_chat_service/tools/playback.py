from __future__ import annotations

from pathlib import Path

from llm_report_service.db.media_repo import select_episode_media

from llm_chat_service.config import ServiceConfig
from llm_chat_service.db.tracklet_repo import TrackletRow


def _build_local_path(base_dir: str, path: str) -> str:
    p = (path or "").strip()
    if p == "":
        return ""

    pp = Path(p)
    if pp.is_absolute():
        return str(pp)

    bd = (base_dir or "").strip()
    if bd == "":
        return p

    return str((Path(bd) / pp).resolve())


def build_playbacks(engine, schema: str, tracklets: list[TrackletRow], cfg: ServiceConfig, top_n: int = 10) -> list[dict]:
    out: list[dict] = []

    for t in tracklets[: int(top_n)]:
        if t.episode_id is None:
            out.append(
                {
                    "tracklet_id": t.id,
                    "episode_id": None,
                    "preview_base64": t.query_asset_base64,
                    "play_urls": [],
                    "start_ts": t.start_ts.isoformat(),
                    "end_ts": (t.end_ts or t.start_ts).isoformat(),
                }
            )
            continue

        media = select_episode_media(
            engine=engine,
            schema=schema,
            episode_id=t.episode_id,
            stream_id=t.stream_id,
            start_ts=t.start_ts,
            end_ts=(t.end_ts or t.start_ts),
            limit=int(cfg.media_limit_per_episode),
        )

        urls = [_build_local_path(cfg.media_base_dir, m.path) for m in media if m.path is not None]

        out.append(
            {
                "tracklet_id": t.id,
                "episode_id": t.episode_id,
                "preview_base64": t.query_asset_base64,
                "play_urls": urls,
                "start_ts": t.start_ts.isoformat(),
                "end_ts": (t.end_ts or t.start_ts).isoformat(),
            }
        )

    return out
