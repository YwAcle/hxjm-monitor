from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime

from llm_chat_service.db.tracklet_repo import TrackletRow


def _ts_to_hour_key(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:00")


def compute_frequency(tracklets: list[TrackletRow]) -> dict:
    count = len(tracklets)

    by_hour = Counter()
    by_stream = Counter()

    dwell_s_total = 0.0
    dwell_s_list: list[float] = []

    for t in tracklets:
        by_hour[_ts_to_hour_key(t.start_ts)] += 1
        by_stream[str(t.stream_id)] += 1

        end_ts = t.end_ts or t.start_ts
        dur = max(0.0, (end_ts - t.start_ts).total_seconds())
        dwell_s_total += dur
        dwell_s_list.append(dur)

    avg_dwell_s = (dwell_s_total / count) if count > 0 else 0.0

    return {
        "count": count,
        "by_hour": [{"hour": k, "count": int(v)} for k, v in sorted(by_hour.items())],
        "by_camera": [{"stream_id": k, "count": int(v)} for k, v in sorted(by_stream.items())],
        "avg_dwell_s": avg_dwell_s,
        "total_dwell_s": dwell_s_total,
    }
