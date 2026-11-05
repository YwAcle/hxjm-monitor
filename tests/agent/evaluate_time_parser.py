"""Evaluate natural-language time parsing with fixed, independently labeled cases.

Run: PYTHONPATH=. /data1/userhome/va/miniconda3/envs/monitor/bin/python tests/evaluate_time_parser.py
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from llm_agent_service.tools.time_parser import parse_time


ZONE = ZoneInfo("Asia/Shanghai")
REFERENCE = datetime(2026, 9, 17, 10, 0, tzinfo=ZONE)  # Thursday


@dataclass(frozen=True)
class Case:
    category: str
    text: str
    kind: str | None
    start: str | None = None
    end: str | None = None


CASES = (
    Case("relative day", "今天", "range", "2026-09-17", "2026-09-18"),
    Case("relative day", "查询昨天的异常事件", "range", "2026-09-16", "2026-09-17"),
    Case("relative day", "大后天", "range", "2026-09-20", "2026-09-21"),
    Case("relative day", "三天后", "datetime", "2026-09-20T10:00", "2026-09-20T10:00"),
    Case("relative day", "十一天后", "datetime", "2026-09-28T10:00", "2026-09-28T10:00"),
    Case("week/month", "下周一", "range", "2026-09-21", "2026-09-22"),
    Case("week/month", "本周末", "range", "2026-09-19", "2026-09-21"),
    Case("week/month", "下周", "range", "2026-09-21", "2026-09-28"),
    Case("week/month", "上周", "range", "2026-09-07", "2026-09-14"),
    Case("week/month", "下个月", "range", "2026-10-01", "2026-11-01"),
    Case("week/month", "2024年2月", "range", "2024-02-01", "2024-03-01"),
    Case("rolling window", "最近三天", "duration", "2026-09-14T10:00", "2026-09-17T10:00"),
    Case("rolling window", "过去24小时", "duration", "2026-09-16T10:00", "2026-09-17T10:00"),
    Case("rolling window", "近一个月", "duration", "2026-08-17T10:00", "2026-09-17T10:00"),
    Case("rolling window", "最近十二个月", "duration", "2025-09-17T10:00", "2026-09-17T10:00"),
    Case("rolling window", "最近12个月", "duration", "2025-09-17T10:00", "2026-09-17T10:00"),
    Case("rolling window", "过去半小时", "duration", "2026-09-17T09:30", "2026-09-17T10:00"),
    Case("future offset", "3小时后", "datetime", "2026-09-17T13:00", "2026-09-17T13:00"),
    Case("future offset", "2天后", "datetime", "2026-09-19T10:00", "2026-09-19T10:00"),
    Case("future offset", "30分钟后", "datetime", "2026-09-17T10:30", "2026-09-17T10:30"),
    Case("future offset", "两周后", "datetime", "2026-10-01T10:00", "2026-10-01T10:00"),
    Case("clock", "明天下午3点", "datetime", "2026-09-18T15:00", "2026-09-18T15:00"),
    Case("clock", "晚上8点30分", "datetime", "2026-09-17T20:30", "2026-09-17T20:30"),
    Case("clock", "下午三点", "datetime", "2026-09-17T15:00", "2026-09-17T15:00"),
    Case("clock", "下午3点半", "datetime", "2026-09-17T15:30", "2026-09-17T15:30"),
    Case("clock", "今天下午3点15分30秒", "datetime", "2026-09-17T15:15:30", "2026-09-17T15:15:30"),
    Case("absolute date", "2026-08-18", "range", "2026-08-18", "2026-08-19"),
    Case("absolute date", "8月18日", "range", "2026-08-18", "2026-08-19"),
    Case("absolute date", "2026年9月18日下午3点", "datetime", "2026-09-18T15:00", "2026-09-18T15:00"),
    Case("absolute date", "2026-09-18 15:30", "datetime", "2026-09-18T15:30", "2026-09-18T15:30"),
    Case("date range", "8月18日至22日", "range", "2026-08-18", "2026-08-23"),
    Case("date range", "8月18日到8月22日", "range", "2026-08-18", "2026-08-23"),
    Case("date range", "2026年9月18日到2026年9月20日", "range", "2026-09-18", "2026-09-21"),
    Case("date range", "2026年9月18日到2026年10月2日", "range", "2026-09-18", "2026-10-03"),
    Case("date range", "12月31日到1月2日", "range", "2026-12-31", "2027-01-03"),
    Case("date range", "明天到后天", "range", "2026-09-18", "2026-09-20"),
    Case("date range", "明天下午3点到5点", "range", "2026-09-18T15:00", "2026-09-18T17:00"),
    Case("invalid/ambiguous", "9点", None),
    Case("invalid/ambiguous", "2026年2月30日", None),
    Case("invalid/ambiguous", "8月22日至8月18日", None),
    Case("invalid/ambiguous", "比较8月18日和8月22日", None),
    Case("invalid/ambiguous", "春节期间", None),
    Case("invalid/ambiguous", "", None),
)


def expected_iso(value: str | None) -> str | None:
    return datetime.fromisoformat(value).replace(tzinfo=ZONE).isoformat() if value else None


def main() -> None:
    counts = {"correct": 0, "rejected": 0, "wrong": 0, "false_accept": 0, "valid": 0, "invalid": 0}
    categories: dict[str, list[int]] = {}
    print(f"Reference: {REFERENCE.isoformat()} | timezone: Asia/Shanghai")
    for case in CASES:
        result = parse_time(case.text, reference_time=REFERENCE, timezone="Asia/Shanghai")
        if case.kind is None:
            counts["invalid"] += 1
            status = "correct" if not result.success else "false_accept"
        else:
            counts["valid"] += 1
            if not result.success:
                status = "rejected"
            elif (result.type, result.start.isoformat(), result.end.isoformat()) == (
                case.kind, expected_iso(case.start), expected_iso(case.end)
            ):
                status = "correct"
            else:
                status = "wrong"
        counts[status] += 1
        if case.kind is not None:
            category_counts = categories.setdefault(case.category, [0, 0])
            category_counts[1] += 1
            category_counts[0] += status == "correct"
        if status != "correct":
            expected = (case.kind, expected_iso(case.start), expected_iso(case.end))
            actual = (result.type, result.start.isoformat() if result.start else None,
                      result.end.isoformat() if result.end else None)
            print(f"{status:12} [{case.category}] {case.text!r}")
            print(f"  expected={expected}; actual={actual}; error={result.error}")

    valid_correct = counts["valid"] - counts["rejected"] - counts["wrong"]
    print(f"Valid expressions: {valid_correct}/{counts['valid']} exact"
          f" ({valid_correct / counts['valid']:.1%}); {counts['rejected']} rejected; {counts['wrong']} wrong")
    print(f"Invalid expressions: {counts['invalid'] - counts['false_accept']}"
          f"/{counts['invalid']} correctly rejected; {counts['false_accept']} falsely accepted")
    print("By category:")
    for category, (correct, total) in categories.items():
        print(f"  {category:16} {correct}/{total} exact")


if __name__ == "__main__":
    main()
