"""
时间解析工具 - 将自然语言时间描述转换为具体时间范围
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional

import pytz
try:
    # 新版 LangChain (>=0.2.0)
    from langchain_core.tools import Tool
except ImportError:
    # 旧版 LangChain
    from langchain.tools import Tool


@dataclass
class TimeRange:
    """时间范围"""
    start_ts: datetime
    end_ts: datetime
    label: str


def parse_time_range(
    query: str,
    now: Optional[datetime] = None,
    tz: str = "Asia/Shanghai",
) -> TimeRange:
    """
    解析时间范围
    
    支持的格式:
    - 今天、昨天、前天
    - 本周、上周
    - 本月、上月
    - 今年、去年
    - 最近N天/小时
    - 具体日期: 2026年1月4日、2026-01-04
    - 时间段: 今天上午、昨天下午
    
    Args:
        query: 包含时间信息的查询字符串
        now: 当前时间，默认使用系统时间
        tz: 时区
        
    Returns:
        TimeRange 对象
    """
    timezone = pytz.timezone(tz)
    
    if now is None:
        now = datetime.now(timezone)
    elif now.tzinfo is None:
        now = timezone.localize(now)
    
    # 获取当天开始时间
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1) - timedelta(microseconds=1)
    
    query_lower = query.lower().strip()
    
    # 今天
    if "今天" in query or "today" in query_lower:
        start_ts, end_ts = today_start, today_end
        label = "今天"
        # 检查是否有更具体的时间段
        if "上午" in query or "早上" in query:
            end_ts = today_start.replace(hour=12)
            label = "今天上午"
        elif "下午" in query:
            start_ts = today_start.replace(hour=12)
            end_ts = today_start.replace(hour=18)
            label = "今天下午"
        elif "晚上" in query:
            start_ts = today_start.replace(hour=18)
            label = "今天晚上"
        return TimeRange(start_ts=start_ts, end_ts=end_ts, label=label)
    
    # 昨天
    if "昨天" in query or "yesterday" in query_lower:
        yesterday_start = today_start - timedelta(days=1)
        yesterday_end = today_start - timedelta(microseconds=1)
        label = "昨天"
        if "上午" in query or "早上" in query:
            yesterday_end = yesterday_start.replace(hour=12)
            label = "昨天上午"
        elif "下午" in query:
            start_ts = yesterday_start.replace(hour=12)
            yesterday_end = yesterday_start.replace(hour=18)
            label = "昨天下午"
            return TimeRange(start_ts=start_ts, end_ts=yesterday_end, label=label)
        elif "晚上" in query:
            start_ts = yesterday_start.replace(hour=18)
            return TimeRange(start_ts=start_ts, end_ts=yesterday_end, label="昨天晚上")
        return TimeRange(start_ts=yesterday_start, end_ts=yesterday_end, label=label)
    
    # 前天
    if "前天" in query:
        day_before_yesterday = today_start - timedelta(days=2)
        return TimeRange(
            start_ts=day_before_yesterday,
            end_ts=day_before_yesterday + timedelta(days=1) - timedelta(microseconds=1),
            label="前天",
        )
    
    # 本周
    if "本周" in query or "这周" in query or "this week" in query_lower:
        weekday = now.weekday()  # 0=周一
        week_start = today_start - timedelta(days=weekday)
        week_end = week_start + timedelta(days=7) - timedelta(microseconds=1)
        return TimeRange(start_ts=week_start, end_ts=week_end, label="本周")
    
    # 上周
    if "上周" in query or "last week" in query_lower:
        weekday = now.weekday()
        this_week_start = today_start - timedelta(days=weekday)
        last_week_start = this_week_start - timedelta(days=7)
        last_week_end = this_week_start - timedelta(microseconds=1)
        return TimeRange(start_ts=last_week_start, end_ts=last_week_end, label="上周")
    
    # 本月
    if "本月" in query or "这个月" in query or "this month" in query_lower:
        month_start = today_start.replace(day=1)
        if now.month == 12:
            next_month_start = month_start.replace(year=now.year + 1, month=1)
        else:
            next_month_start = month_start.replace(month=now.month + 1)
        month_end = next_month_start - timedelta(microseconds=1)
        return TimeRange(start_ts=month_start, end_ts=month_end, label="本月")
    
    # 上月
    if "上月" in query or "上个月" in query or "last month" in query_lower:
        this_month_start = today_start.replace(day=1)
        if now.month == 1:
            last_month_start = this_month_start.replace(year=now.year - 1, month=12)
        else:
            last_month_start = this_month_start.replace(month=now.month - 1)
        last_month_end = this_month_start - timedelta(microseconds=1)
        return TimeRange(start_ts=last_month_start, end_ts=last_month_end, label="上月")
    
    # 最近N天
    match = re.search(r"最近\s*(\d+)\s*天", query)
    if match:
        days = int(match.group(1))
        start_ts = today_start - timedelta(days=days - 1)
        return TimeRange(start_ts=start_ts, end_ts=today_end, label=f"最近{days}天")
    
    # 最近N小时
    match = re.search(r"最近\s*(\d+)\s*(小时|h)", query)
    if match:
        hours = int(match.group(1))
        start_ts = now - timedelta(hours=hours)
        return TimeRange(start_ts=start_ts, end_ts=now, label=f"最近{hours}小时")
    
    # 具体日期: 2026年1月4日 或 2026-01-04
    match = re.search(r"(\d{4})\s*[年-]\s*(\d{1,2})\s*[月-]\s*(\d{1,2})\s*日?", query)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        try:
            date_start = timezone.localize(datetime(year, month, day))
            date_end = date_start + timedelta(days=1) - timedelta(microseconds=1)
            return TimeRange(
                start_ts=date_start,
                end_ts=date_end,
                label=f"{year}年{month}月{day}日",
            )
        except ValueError:
            pass
    
    # 默认: 今天
    return TimeRange(start_ts=today_start, end_ts=today_end, label="今天")


def parse_time_range_func(query: str) -> dict:
    """
    工具函数: 解析时间范围
    
    Args:
        query: 包含时间信息的查询字符串
        
    Returns:
        字典 {start_ts, end_ts, label}
    """
    tr = parse_time_range(query)
    return {
        "start_ts": tr.start_ts.isoformat(),
        "end_ts": tr.end_ts.isoformat(),
        "label": tr.label,
    }


# LangChain Tool 定义
parse_time_range_tool = Tool(
    name="parse_time_range",
    func=parse_time_range_func,
    description=(
        "解析时间范围，将自然语言时间描述转换为具体的开始时间和结束时间。"
        "支持：今天、昨天、本周、上周、本月、最近N天、具体日期（如2026年1月4日）等。"
        "输入：包含时间信息的字符串。"
        "输出：{start_ts: ISO时间, end_ts: ISO时间, label: 时间标签}"
    ),
)

