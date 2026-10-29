from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone


@dataclass(frozen=True)
class TimeRange:
    start_ts: datetime
    end_ts: datetime
    label: str


def _at(d: datetime, hh: int, mm: int = 0, ss: int = 0) -> datetime:
    return datetime.combine(d.date(), time(hh, mm, ss), tzinfo=d.tzinfo)


def parse_time_range(query: str, now: datetime, tz: str) -> TimeRange:
    def _load_tzinfo(name: str):
        try:
            from zoneinfo import ZoneInfo  # type: ignore

            return ZoneInfo(name)
        except ModuleNotFoundError:
            try:
                from backports.zoneinfo import ZoneInfo  # type: ignore

                return ZoneInfo(name)
            except ModuleNotFoundError:
                if name in {"Asia/Shanghai", "PRC", "China Standard Time"}:
                    return timezone(timedelta(hours=8))
                return None

    z = _load_tzinfo(tz)
    if z is not None:
        now = now.astimezone(z)
    q = (query or "").strip()
    tzinfo = now.tzinfo or timezone.utc

    def _label(day_label: str | None, part_label: str | None) -> str:
        day_label = (day_label or "").strip()
        part_label = (part_label or "").strip()
        if day_label and part_label:
            return f"{day_label}{part_label}"
        return day_label or part_label or "今天"

    def _min_now(dt: datetime) -> datetime:
        return dt if dt <= now else now

    def _part_of_day(text: str) -> tuple[int, int, int, int, int, int, str] | None:
        if re.search(r"凌晨", text):
            return (0, 0, 0, 6, 0, 0, "凌晨")
        if re.search(r"早上", text):
            return (6, 0, 0, 12, 0, 0, "早上")
        if re.search(r"上午", text):
            return (6, 0, 0, 12, 0, 0, "上午")
        if re.search(r"中午", text):
            return (11, 0, 0, 13, 0, 0, "中午")
        if re.search(r"下午", text):
            return (12, 0, 0, 18, 0, 0, "下午")
        if re.search(r"傍晚|晚上|夜里|夜晚", text):
            return (18, 0, 0, 23, 59, 59, "晚上")
        return None

    def _relative_day(text: str) -> tuple[int | None, str | None]:
        if re.search(r"大前天", text):
            return (3, "大前天")
        if re.search(r"前天", text):
            return (2, "前天")
        if re.search(r"昨天", text):
            return (1, "昨天")
        if re.search(r"今天", text):
            return (0, "今天")
        if re.search(r"大后天", text):
            return (-3, "大后天")
        if re.search(r"后天", text):
            return (-2, "后天")
        if re.search(r"明天", text):
            return (-1, "明天")
        m = re.search(r"(\d+)\s*天前", text)
        if m:
            n = int(m.group(1))
            return (n, f"{n}天前")
        return (None, None)

    def today_range() -> TimeRange:
        start = _at(now, 0, 0, 0)
        end = now
        return TimeRange(start_ts=start, end_ts=end, label="今天")

    def _day_range(d: datetime, *, label: str, pod: tuple[int, int, int, int, int, int, str] | None) -> TimeRange:
        if pod is None:
            return TimeRange(start_ts=_at(d, 0, 0, 0), end_ts=_at(d, 23, 59, 59), label=label)
        sh, sm, ss, eh, em, es, part_label = pod
        start = _at(d, sh, sm, ss)
        end = _at(d, eh, em, es)
        return TimeRange(start_ts=start, end_ts=end, label=_label(label, part_label))

    def _week_start(d: datetime) -> datetime:
        return _at(d - timedelta(days=d.weekday()), 0, 0, 0)

    def _shift_ym(y: int, m: int, delta_months: int) -> tuple[int, int]:
        t = y * 12 + (m - 1) + delta_months
        ny = t // 12
        nm = t % 12 + 1
        return ny, nm

    def _month_range(*, months_ago: int, label: str) -> TimeRange:
        y, m = _shift_ym(now.year, now.month, -int(months_ago))
        start = datetime(y, m, 1, 0, 0, 0, tzinfo=tzinfo)
        y2, m2 = _shift_ym(y, m, 1)
        next_start = datetime(y2, m2, 1, 0, 0, 0, tzinfo=tzinfo)
        end = next_start - timedelta(seconds=1)
        if int(months_ago) == 0:
            end = _min_now(end)
        return TimeRange(start_ts=start, end_ts=end, label=label)

    def _week_range(*, weeks_ago: int, label: str) -> TimeRange:
        this_start = _week_start(now)
        start = this_start - timedelta(days=7 * int(weeks_ago))
        end = start + timedelta(days=7) - timedelta(seconds=1)
        if int(weeks_ago) == 0:
            end = now
        return TimeRange(start_ts=start, end_ts=end, label=label)

    if q == "":
        return today_range()

    pod = _part_of_day(q)

    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", q)
    if m:
        y, mo, da = m.groups()
        d = datetime(int(y), int(mo), int(da), 0, 0, 0, tzinfo=tzinfo)
        return _day_range(d, label=f"{y}-{mo}-{da}", pod=pod)

    m = re.search(r"(\d{1,2})月(\d{1,2})日", q)
    if m:
        mo, da = m.groups()
        d = datetime(int(now.year), int(mo), int(da), 0, 0, 0, tzinfo=tzinfo)
        return _day_range(d, label=f"{mo}月{da}日", pod=pod)

    if re.search(r"(本月|这月)", q):
        return _month_range(months_ago=0, label="本月")
    if re.search(r"上上个月", q):
        return _month_range(months_ago=2, label="上上个月")
    if re.search(r"上个月", q):
        return _month_range(months_ago=1, label="上个月")
    if re.search(r"下下个月", q):
        return _month_range(months_ago=-2, label="下下个月")
    if re.search(r"下个月", q):
        return _month_range(months_ago=-1, label="下个月")
    if re.search(r"(这个月)", q):
        return _month_range(months_ago=0, label="本月")

    m = re.search(r"(?:(本周|这周)|(?:(上上周|上周))|(?:(下下周|下周)))\s*(?:周|星期)?\s*([一二三四五六日天])", q)
    if m:
        this_prefix, past_prefix, future_prefix, weekday_text = m.groups()
        weeks_ago = 0
        if past_prefix == "上周":
            weeks_ago = 1
        elif past_prefix == "上上周":
            weeks_ago = 2
        elif future_prefix == "下周":
            weeks_ago = -1
        elif future_prefix == "下下周":
            weeks_ago = -2

        weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
        wi = weekday_map.get(weekday_text)
        if wi is not None:
            base = _week_start(now) - timedelta(days=7 * int(weeks_ago))
            day = base + timedelta(days=int(wi))
            prefix = past_prefix or this_prefix or future_prefix or ""
            label = f"{prefix}{weekday_text}" if prefix else ("周" + weekday_text)

            tr = _day_range(day, label=label, pod=pod)
            if weeks_ago == 0 and day.date() == now.date():
                tr = TimeRange(start_ts=tr.start_ts, end_ts=_min_now(tr.end_ts), label=tr.label)
                if tr.end_ts < tr.start_ts:
                    tr = TimeRange(start_ts=tr.start_ts, end_ts=tr.start_ts, label=tr.label)
            return tr

    m = re.search(r"(?:周|星期)\s*([一二三四五六日天])", q)
    if m:
        weekday_text = m.group(1)
        weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
        wi = weekday_map.get(weekday_text)
        if wi is not None:
            base = _week_start(now)
            day = base + timedelta(days=int(wi))
            if _at(day, 0, 0, 0) > now:
                day = day - timedelta(days=7)
            label = "周" + weekday_text
            tr = _day_range(day, label=label, pod=pod)
            if day.date() == now.date():
                tr = TimeRange(start_ts=tr.start_ts, end_ts=_min_now(tr.end_ts), label=tr.label)
                if tr.end_ts < tr.start_ts:
                    tr = TimeRange(start_ts=tr.start_ts, end_ts=tr.start_ts, label=tr.label)
            return tr

    if re.search(r"(本周|这周|这个星期|这星期)", q):
        return _week_range(weeks_ago=0, label="本周")
    if re.search(r"上上周", q):
        return _week_range(weeks_ago=2, label="上上周")
    if re.search(r"上周", q):
        return _week_range(weeks_ago=1, label="上周")
    if re.search(r"下下周", q):
        return _week_range(weeks_ago=-2, label="下下周")
    if re.search(r"下周", q):
        return _week_range(weeks_ago=-1, label="下周")

    offset, day_label = _relative_day(q)
    if pod is not None and offset is None:
        offset, day_label = (0, "今天")

    if offset is not None:
        if int(offset) == 0 and pod is None:
            return today_range()
        d = now - timedelta(days=int(offset))
        tr = _day_range(d, label=str(day_label or ""), pod=pod)
        if int(offset) == 0:
            tr = TimeRange(start_ts=tr.start_ts, end_ts=_min_now(tr.end_ts), label=tr.label)
            if tr.end_ts < tr.start_ts:
                tr = TimeRange(start_ts=tr.start_ts, end_ts=tr.start_ts, label=tr.label)
        return tr

    return today_range()
