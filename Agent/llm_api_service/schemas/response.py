"""
响应数据结构定义
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from datetime import datetime


@dataclass
class TimeRange:
    """时间范围"""
    start: str  # ISO格式时间字符串
    end: str    # ISO格式时间字符串
    label: str  # 如 "今天"、"昨天"
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PersonInfo:
    """人员信息"""
    id: str
    name: str
    image_base64: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CameraStat:
    """摄像头统计"""
    camera_name: str
    stream_id: str
    location: Optional[str] = None
    count: int = 0
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TrackletInfo:
    """轨迹信息"""
    id: str
    stream_id: str
    start_ts: str
    end_ts: str
    duration_seconds: float
    thumbnail_base64: Optional[str] = None
    playback_url: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReIDResult:
    """ReID查询结果"""
    type: str = "reid_result"
    title: str = "REID行人结果如下"
    person: Optional[PersonInfo] = None
    time_range: Optional[TimeRange] = None
    summary: str = ""
    camera_stats: list[CameraStat] = field(default_factory=list)
    tracklets: list[TrackletInfo] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "title": self.title,
            "person": self.person.to_dict() if self.person else None,
            "time_range": self.time_range.to_dict() if self.time_range else None,
            "summary": self.summary,
            "camera_stats": [c.to_dict() for c in self.camera_stats],
            "tracklets": [t.to_dict() for t in self.tracklets],
        }


# 异常名称中英文映射
ANOMALY_NAME_MAP = {
    "fall": "跌倒",
    "fight": "打架",
    "fire": "火灾",
    "smoke": "烟雾",
    "intrusion": "入侵",
    "loitering": "徘徊",
    "roi_stay": "区域停留",
}


@dataclass
class AnomalyInfo:
    """异常信息"""
    id: str
    anomaly_name: str
    anomaly_name_cn: str
    anomaly_level: int
    time: str
    stream_id: str
    camera_name: Optional[str] = None
    location: Optional[str] = None
    thumbnail_base64: Optional[str] = None
    playback_url: Optional[str] = None
    report_text: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LevelStats:
    """异常等级统计"""
    level_1: int = 0  # ROI区域停留
    level_2: int = 0  # 跌倒
    level_3: int = 0  # 打架
    level_4: int = 0  # 火灾/烟雾
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VADResult:
    """VAD异常查询结果"""
    type: str = "vad_result"
    title: str = "VAD异常结果如下"
    time_range: Optional[TimeRange] = None
    summary: str = ""
    anomalies: list[AnomalyInfo] = field(default_factory=list)
    level_stats: LevelStats = field(default_factory=LevelStats)
    
    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "title": self.title,
            "time_range": self.time_range.to_dict() if self.time_range else None,
            "summary": self.summary,
            "anomalies": [a.to_dict() for a in self.anomalies],
            "level_stats": self.level_stats.to_dict(),
        }


@dataclass
class GeneralResult:
    """通用结果（用于非结构化回答）"""
    type: str = "general_result"
    title: str = "查询结果"
    summary: str = ""
    raw_data: Optional[dict] = None
    
    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "title": self.title,
            "summary": self.summary,
            "raw_data": self.raw_data,
        }

