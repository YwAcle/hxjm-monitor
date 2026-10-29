"""Agent 时间范围解析测试。"""

import unittest
from datetime import datetime

import pytz

from llm_agent_service.service.reid_service import ReidService
from llm_agent_service.service.reid_service import TimeRangeParseError


class AgentTimeRangeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ReidService.__new__(ReidService)
        self.service.timezone = pytz.timezone("Asia/Shanghai")
        self.now = self.service.timezone.localize(datetime(2026, 9, 16, 12, 0, 0))

    def test_parses_month_day_range(self) -> None:
        result = self.service._parse_time_range("8月18日到8月22日", now=self.now)
        self.assertEqual(result.start_ts.isoformat(), "2026-08-18T00:00:00+08:00")
        self.assertEqual(result.end_ts.isoformat(), "2026-08-23T00:00:00+08:00")

    def test_parses_same_month_short_range(self) -> None:
        result = self.service._parse_time_range("8月18日至22日", now=self.now)
        self.assertEqual(result.start_ts.day, 18)
        self.assertEqual(result.end_ts.isoformat(), "2026-08-23T00:00:00+08:00")

    def test_parses_month_to_natural_month_range(self) -> None:
        result = self.service._parse_time_range("8月份", now=self.now)
        self.assertEqual(result.start_ts.isoformat(), "2026-08-01T00:00:00+08:00")
        self.assertEqual(result.end_ts.isoformat(), "2026-09-01T00:00:00+08:00")

    def test_parses_month_from_full_query(self) -> None:
        result = self.service._parse_time_range("查询8月份的异常事件", now=self.now)
        self.assertEqual(result.start_ts.month, 8)

    def test_parses_explicit_year_month(self) -> None:
        result = self.service._parse_time_range("2024年2月", now=self.now)
        self.assertEqual(result.start_ts.isoformat(), "2024-02-01T00:00:00+08:00")
        self.assertEqual(result.end_ts.isoformat(), "2024-03-01T00:00:00+08:00")

    def test_parses_relative_month(self) -> None:
        result = self.service._parse_time_range("上个月", now=self.now)
        self.assertEqual(result.label, "上个月")
        self.assertEqual(result.start_ts.isoformat(), "2026-08-01T00:00:00+08:00")
        self.assertEqual(result.end_ts.isoformat(), "2026-09-01T00:00:00+08:00")

    def test_parses_recent_one_month_as_rolling_window(self) -> None:
        result = self.service._parse_time_range("近一个月", now=self.now)
        self.assertEqual(result.start_ts.isoformat(), "2026-08-16T12:00:00+08:00")
        self.assertEqual(result.end_ts.isoformat(), "2026-09-16T12:00:00+08:00")

    def test_parses_recent_days_from_full_query(self) -> None:
        result = self.service._parse_time_range("查询最近三天的异常", now=self.now)
        self.assertEqual(result.start_ts.isoformat(), "2026-09-13T12:00:00+08:00")
        self.assertEqual(result.end_ts.isoformat(), "2026-09-16T12:00:00+08:00")

    def test_parses_recent_hours(self) -> None:
        result = self.service._parse_time_range("过去24小时", now=self.now)
        self.assertEqual(result.start_ts.isoformat(), "2026-09-15T12:00:00+08:00")
        self.assertEqual(result.end_ts.isoformat(), "2026-09-16T12:00:00+08:00")

    def test_queries_specific_clock_as_one_minute(self) -> None:
        result = self.service._parse_time_range("明天下午3点", now=self.now)
        self.assertEqual(result.start_ts.isoformat(), "2026-09-17T15:00:00+08:00")
        self.assertEqual(result.end_ts.isoformat(), "2026-09-17T15:01:00+08:00")

    def test_queries_future_offset_as_one_minute(self) -> None:
        result = self.service._parse_time_range("3小时后", now=self.now)
        self.assertEqual(result.start_ts.isoformat(), "2026-09-16T15:00:00+08:00")
        self.assertEqual(result.end_ts.isoformat(), "2026-09-16T15:01:00+08:00")

    def test_uses_dateparser_for_relative_day(self) -> None:
        result = self.service._parse_time_range("昨天", now=self.now)
        self.assertEqual(result.start_ts.isoformat(), "2026-09-15T00:00:00+08:00")
        self.assertEqual(result.end_ts.isoformat(), "2026-09-16T00:00:00+08:00")

    def test_extracts_relative_day_from_full_query(self) -> None:
        result = self.service._parse_time_range("查询昨天的异常事件", now=self.now)
        self.assertEqual(result.start_ts.isoformat(), "2026-09-15T00:00:00+08:00")
        self.assertEqual(result.end_ts.isoformat(), "2026-09-16T00:00:00+08:00")

    def test_uses_dateparser_for_iso_date(self) -> None:
        result = self.service._parse_time_range("2026-08-18", now=self.now)
        self.assertEqual(result.start_ts.isoformat(), "2026-08-18T00:00:00+08:00")
        self.assertEqual(result.end_ts.isoformat(), "2026-08-19T00:00:00+08:00")

    def test_uses_dateparser_for_month_day(self) -> None:
        result = self.service._parse_time_range("8月18日", now=self.now)
        self.assertEqual(result.start_ts.isoformat(), "2026-08-18T00:00:00+08:00")
        self.assertEqual(result.end_ts.isoformat(), "2026-08-19T00:00:00+08:00")

    def test_rejects_reversed_date_range(self) -> None:
        with self.assertRaises(TimeRangeParseError):
            self.service._parse_time_range("8月22日至8月18日", now=self.now)

    def test_rejects_multiple_unrelated_dates(self) -> None:
        with self.assertRaises(TimeRangeParseError):
            self.service._parse_time_range("比较8月18日和8月22日的异常", now=self.now)

    def test_rejects_unrecognized_time_instead_of_querying_today(self) -> None:
        with self.assertRaises(TimeRangeParseError):
            self.service._parse_time_range("春节期间", now=self.now)


if __name__ == "__main__":
    unittest.main()
