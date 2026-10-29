"""面向 Agent 的自然语言时间解析 Tool。"""

from __future__ import annotations

import re
from calendar import monthrange
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, tzinfo
from typing import Literal
from zoneinfo import ZoneInfo

from dateparser import parse as parse_date


ParseType = Literal["datetime", "range", "duration"]


@dataclass(frozen=True)
class TimeParseResult:
    success: bool
    type: ParseType | None
    start: datetime | None
    end: datetime | None
    original_text: str
    error: str | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["start"] = self.start.isoformat() if self.start else None
        data["end"] = self.end.isoformat() if self.end else None
        return data


_DAY_OFFSETS = {
    "大前天": -3,
    "前天": -2,
    "昨天": -1,
    "今日": 0,
    "今天": 0,
    "明天": 1,
    "大后天": 3,
    "后天": 2,
}
_WEEKDAYS = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
_PERIODS = {
    "凌晨": (0, 0, 6, 0),
    "早上": (6, 0, 12, 0),
    "上午": (6, 0, 12, 0),
    "中午": (11, 0, 13, 0),
    "下午": (12, 0, 18, 0),
    "傍晚": (18, 0, 20, 0),
    "晚上": (18, 0, 24, 0),
    "夜里": (18, 0, 24, 0),
}
_CHINESE_NUMBERS = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def parse_time(
    text: str,
    reference_time: datetime | None = None,
    timezone: str | None = None,
) -> TimeParseResult:
    """将常见中文自然语言时间表达规范化为稳定的结构化结果。"""
    original_text = text if isinstance(text, str) else ""
    query = original_text.strip()
    if not query:
        return _failure(original_text, "无法解析空时间表达")

    try:
        zone = ZoneInfo(timezone or "Asia/Shanghai")
    except Exception:
        return _failure(original_text, "时区无效")
    now = _normalize_reference(reference_time, zone)

    explicit_range = _explicit_range(query, now)
    if explicit_range is not None:
        if explicit_range[0] >= explicit_range[1]:
            return _failure(original_text, "日期范围结束时间早于开始时间")
        return _success("range", explicit_range[0], explicit_range[1], original_text)
    if len(_numeric_days(query)) > 1:
        return _failure(original_text, "存在多个日期，请使用明确的日期范围表达")

    duration = _duration(query, now)
    if duration is not None:
        return _success(duration[2], duration[0], duration[1], original_text)

    month_range = _month_range(query, now)
    if month_range is not None:
        return _success("range", month_range[0], month_range[1], original_text)

    week_range = _week_range(query, now)
    if week_range is not None:
        return _success("range", week_range[0], week_range[1], original_text)

    day = _day_anchor(query, now)
    if day is None:
        day = _week_anchor(query, now)
    if day is None:
        day = _absolute_day(query, now, zone)

    period = _period(query)
    clock = _clock(query, period)
    if clock == "ambiguous":
        return _failure(original_text, "无法确定是上午还是晚上")

    if day is not None and clock is not None:
        return _success("datetime", _at(day, *clock), _at(day, *clock), original_text)
    if day is not None and period is not None:
        start, end = _period_range(day, period)
        return _success("range", start, end, original_text)
    if day is not None:
        start = _day_start(day)
        return _success("range", start, start + timedelta(days=1), original_text)
    if clock is not None:
        value = _at(now, *clock)
        return _success("datetime", value, value, original_text)
    if period is not None:
        start, end = _period_range(now, period)
        return _success("range", start, end, original_text)

    return _failure(original_text, "无法解析该时间表达")


def _normalize_reference(value: datetime | None, zone: tzinfo) -> datetime:
    value = value or datetime.now(zone)
    return value.replace(tzinfo=zone) if value.tzinfo is None else value.astimezone(zone)


def _success(kind: ParseType, start: datetime, end: datetime, text: str) -> TimeParseResult:
    return TimeParseResult(True, kind, start, end, text)


def _failure(text: str, error: str) -> TimeParseResult:
    return TimeParseResult(False, None, None, None, text, error)


def _day_start(value: datetime) -> datetime:
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def _at(day: datetime, hour: int, minute: int = 0) -> datetime:
    if hour == 24:
        return _day_start(day) + timedelta(days=1)
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _day_anchor(text: str, now: datetime) -> datetime | None:
    for phrase, offset in _DAY_OFFSETS.items():
        if phrase in text:
            return _day_start(now) + timedelta(days=offset)
    match = re.search(r"([一二三四五六七八九十两\d]+)\s*天(?:后|之后)", text)
    if match:
        count = _count(match.group(1))
        return _day_start(now) + timedelta(days=count) if count else None
    return None


def _week_anchor(text: str, now: datetime) -> datetime | None:
    week_start = _day_start(now) - timedelta(days=now.weekday())
    match = re.search(r"(?:(本|这|下)周|(?:本|这|下)星期)\s*([一二三四五六日天])", text)
    if match:
        week_offset = 1 if match.group(1) == "下" else 0
        return week_start + timedelta(days=week_offset * 7 + _WEEKDAYS[match.group(2)])
    return None


def _week_range(text: str, now: datetime) -> tuple[datetime, datetime] | None:
    week_start = _day_start(now) - timedelta(days=now.weekday())
    if "本周末" in text or "这个周末" in text:
        start = week_start + timedelta(days=5)
        return start, start + timedelta(days=2)
    if re.search(r"(?:(本|这|下)周|(?:本|这|下)星期)\s*[一二三四五六日天]", text):
        return None
    if "下周" in text or "下星期" in text:
        start = week_start + timedelta(days=7)
        return start, start + timedelta(days=7)
    if "本周" in text or "这周" in text or "本星期" in text:
        return week_start, week_start + timedelta(days=7)
    return None


def _month_range(text: str, now: datetime) -> tuple[datetime, datetime] | None:
    explicit = re.search(
        r"(?<!\d)(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月(?:份)?(?!\s*\d)",
        text,
    )
    if explicit:
        year, month = int(explicit.group(1) or now.year), int(explicit.group(2))
    elif "下个月" in text or "下月" in text:
        year, month = _shift_month(now.year, now.month, 1)
    elif "上个月" in text or "上月" in text:
        year, month = _shift_month(now.year, now.month, -1)
    elif "本月" in text or "这个月" in text or "当月" in text:
        year, month = now.year, now.month
    else:
        return None
    try:
        start = datetime(year, month, 1, tzinfo=now.tzinfo)
    except ValueError:
        return None
    next_year, next_month = _shift_month(year, month, 1)
    return start, datetime(next_year, next_month, 1, tzinfo=now.tzinfo)


def _explicit_range(text: str, now: datetime) -> tuple[datetime, datetime] | None:
    match = re.search(
        r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?\s*(?:到|至|~|～|-)\s*"
        r"(?:(\d{1,2})\s*月\s*)?(\d{1,2})\s*[日号]?",
        text,
    )
    if match is None:
        return None
    start_month, start_day = int(match.group(1)), int(match.group(2))
    end_month, end_day = int(match.group(3) or start_month), int(match.group(4))
    try:
        start = datetime(now.year, start_month, start_day, tzinfo=now.tzinfo)
        end = datetime(now.year, end_month, end_day, tzinfo=now.tzinfo) + timedelta(days=1)
    except ValueError:
        return None
    return start, end


def _numeric_days(text: str) -> list[re.Match[str]]:
    return list(re.finditer(
        r"(?:(\d{4})\s*[年/-]\s*)?(\d{1,2})\s*[月/-]\s*(\d{1,2})\s*[日号]?",
        text,
    ))


def _duration(text: str, now: datetime) -> tuple[datetime, datetime, ParseType] | None:
    match = re.search(
        r"(?:最近|近|过去)\s*([一二三四五六七八九十两\d]+)\s*个?\s*(小时|天|周|星期|个月|月)",
        text,
    )
    if match is None:
        match = re.search(r"([一二三四五六七八九十两\d]+)\s*(小时|天)(?:后|之后)", text)
        if match is None:
            return None
        count = _count(match.group(1))
        if not count:
            return None
        delta = timedelta(hours=count) if match.group(2) == "小时" else timedelta(days=count)
        target = now + delta
        return target, target, "datetime"

    count = _count(match.group(1))
    if not count:
        return None
    unit = match.group(2)
    if unit == "小时":
        start = now - timedelta(hours=count)
    elif unit == "天":
        start = now - timedelta(days=count)
    elif unit in {"周", "星期"}:
        start = now - timedelta(weeks=count)
    else:
        year, month = _shift_month(now.year, now.month, -count)
        start = now.replace(day=min(now.day, monthrange(year, month)[1]), year=year, month=month)
    return start, now, "duration"


def _absolute_day(text: str, now: datetime, zone: tzinfo) -> datetime | None:
    numeric = next(iter(_numeric_days(text)), None)
    if numeric:
        year = int(numeric.group(1) or now.year)
        try:
            return datetime(year, int(numeric.group(2)), int(numeric.group(3)), tzinfo=zone)
        except ValueError:
            return None
    parsed = parse_date(
        text,
        languages=["zh", "en"],
        settings={
            "RELATIVE_BASE": now,
            "TIMEZONE": str(getattr(zone, "key", "Asia/Shanghai")),
            "TO_TIMEZONE": str(getattr(zone, "key", "Asia/Shanghai")),
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DATES_FROM": "future",
        },
    )
    return _day_start(parsed.astimezone(zone)) if parsed else None


def _period(text: str) -> tuple[int, int, int, int] | None:
    for name, value in _PERIODS.items():
        if name in text:
            return value
    return None


def _period_range(day: datetime, period: tuple[int, int, int, int]) -> tuple[datetime, datetime]:
    start_hour, start_minute, end_hour, end_minute = period
    return _at(day, start_hour, start_minute), _at(day, end_hour, end_minute)


def _clock(text: str, period: tuple[int, int, int, int] | None) -> tuple[int, int] | Literal["ambiguous"] | None:
    match = re.search(r"(?<!\d)(\d{1,2})\s*(?:点|时)(?:\s*(\d{1,2})\s*分?)?", text)
    if match is None:
        match = re.search(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)", text)
    if match is None:
        return None
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    if not 0 <= minute < 60 or not 0 <= hour <= 24:
        return "ambiguous"
    if period is None and 1 <= hour <= 12:
        return "ambiguous"
    if period is not None and hour < 12 and period[0] >= 12:
        hour += 12
    if hour == 24 and minute:
        return "ambiguous"
    return hour, minute


def _count(value: str) -> int | None:
    if value.isdigit():
        count = int(value)
        return count if count > 0 else None
    if value in _CHINESE_NUMBERS:
        return _CHINESE_NUMBERS[value]
    match = re.fullmatch(r"([一二两三四五六七八九])?十([一二两三四五六七八九])?", value)
    if match:
        tens = _CHINESE_NUMBERS[match.group(1)] if match.group(1) else 1
        ones = _CHINESE_NUMBERS[match.group(2)] if match.group(2) else 0
        return tens * 10 + ones
    return None


def _shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
    value = year * 12 + month - 1 + offset
    return value // 12, value % 12 + 1


__all__ = ["TimeParseResult", "parse_time"]
