"""自然语言时间解析 Tool 测试。"""

from datetime import datetime
import unittest
from zoneinfo import ZoneInfo

from llm_agent_service.tools.time_parser import parse_time


class TimeParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.zone = "Asia/Shanghai"
        self.reference = datetime(2026, 9, 17, 10, 0, tzinfo=ZoneInfo(self.zone))

    def parse(self, text: str):
        return parse_time(text, reference_time=self.reference, timezone=self.zone)

    def assert_range(self, text: str, start: str, end: str) -> None:
        result = self.parse(text)
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.start.isoformat(), start)
        self.assertEqual(result.end.isoformat(), end)

    def test_today(self) -> None:
        self.assert_range("今天", "2026-09-17T00:00:00+08:00", "2026-09-18T00:00:00+08:00")

    def test_tomorrow(self) -> None:
        self.assert_range("明天", "2026-09-18T00:00:00+08:00", "2026-09-19T00:00:00+08:00")

    def test_day_after_tomorrow(self) -> None:
        self.assert_range("后天", "2026-09-19T00:00:00+08:00", "2026-09-20T00:00:00+08:00")

    def test_three_days_after_tomorrow(self) -> None:
        self.assert_range("大后天", "2026-09-20T00:00:00+08:00", "2026-09-21T00:00:00+08:00")

    def test_hours_later(self) -> None:
        result = self.parse("3小时后")
        self.assertEqual(result.type, "datetime")
        self.assertEqual(result.start.isoformat(), "2026-09-17T13:00:00+08:00")
        self.assertEqual(result.end, result.start)

    def test_days_later(self) -> None:
        result = self.parse("2天后")
        self.assertEqual(result.type, "datetime")
        self.assertEqual(result.start.isoformat(), "2026-09-19T10:00:00+08:00")

    def test_afternoon_clock(self) -> None:
        result = self.parse("下午3点")
        self.assertEqual(result.type, "datetime")
        self.assertEqual(result.start.isoformat(), "2026-09-17T15:00:00+08:00")

    def test_evening_clock(self) -> None:
        self.assertEqual(self.parse("晚上8点").start.isoformat(), "2026-09-17T20:00:00+08:00")

    def test_tomorrow_afternoon_clock(self) -> None:
        self.assertEqual(self.parse("明天下午3点").start.isoformat(), "2026-09-18T15:00:00+08:00")

    def test_next_monday(self) -> None:
        self.assert_range("下周一", "2026-09-21T00:00:00+08:00", "2026-09-22T00:00:00+08:00")

    def test_next_monday_morning_clock(self) -> None:
        result = self.parse("下周一上午10点")
        self.assertEqual(result.type, "datetime")
        self.assertEqual(result.start.isoformat(), "2026-09-21T10:00:00+08:00")

    def test_this_weekend(self) -> None:
        self.assert_range("本周末", "2026-09-19T00:00:00+08:00", "2026-09-21T00:00:00+08:00")

    def test_next_month(self) -> None:
        self.assert_range("下个月", "2026-10-01T00:00:00+08:00", "2026-11-01T00:00:00+08:00")

    def test_recent_three_days(self) -> None:
        result = self.parse("最近三天")
        self.assertEqual(result.type, "duration")
        self.assertEqual(result.start.isoformat(), "2026-09-14T10:00:00+08:00")
        self.assertEqual(result.end.isoformat(), "2026-09-17T10:00:00+08:00")

    def test_recent_twelve_months_in_chinese_and_digits(self) -> None:
        for text in ("最近十二个月", "最近12个月"):
            with self.subTest(text=text):
                result = self.parse(text)
                self.assertTrue(result.success, result.error)
                self.assertEqual(result.type, "duration")
                self.assertEqual(result.start.isoformat(), "2025-09-17T10:00:00+08:00")
                self.assertEqual(result.end.isoformat(), "2026-09-17T10:00:00+08:00")

    def test_chinese_compound_day_count(self) -> None:
        result = self.parse("二十三天后")
        self.assertEqual(result.type, "datetime")
        self.assertEqual(result.start.isoformat(), "2026-10-10T10:00:00+08:00")

    def test_ambiguous_clock(self) -> None:
        result = self.parse("9点")
        self.assertFalse(result.success)
        self.assertEqual(result.error, "无法确定是上午还是晚上")

    def test_unrecognized_text(self) -> None:
        result = self.parse("春节期间")
        self.assertFalse(result.success)
        self.assertEqual(result.error, "无法解析该时间表达")


if __name__ == "__main__":
    unittest.main()
