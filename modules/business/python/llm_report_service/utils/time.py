from __future__ import annotations

from datetime import datetime, timedelta


def parse_ts(v: str | datetime) -> datetime:
    if isinstance(v, datetime):
        return v
    return datetime.fromisoformat(v.replace("Z", "+00:00"))


def overlap_ms(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> int:
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if end <= start:
        return 0
    return int((end - start).total_seconds() * 1000)


def add_ms(ts: datetime, duration_ms: int) -> datetime:
    return ts + timedelta(milliseconds=duration_ms)
