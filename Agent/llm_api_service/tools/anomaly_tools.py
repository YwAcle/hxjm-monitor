"""
异常相关工具 - 查询 VAD 异常和 LLM 报告
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

try:
    # 新版 LangChain (>=0.2.0)
    from langchain_core.tools import StructuredTool
except ImportError:
    # 旧版 LangChain
    from langchain.tools import StructuredTool

from pydantic import BaseModel, Field

from llm_api_service.schemas.response import ANOMALY_NAME_MAP

# 全局变量，在应用启动时设置
_engine = None
_schema = "public"
_playback_config = None


def set_db_context(engine, schema: str, playback_config=None):
    """设置数据库上下文"""
    global _engine, _schema, _playback_config
    _engine = engine
    _schema = schema
    _playback_config = playback_config


class TimeRangeInput(BaseModel):
    """时间范围输入参数"""
    start_ts: str = Field(description="开始时间，ISO格式（从 parse_time_range 获取）")
    end_ts: str = Field(description="结束时间，ISO格式（从 parse_time_range 获取）")


def list_vad_anomalies_func(start_ts: str, end_ts: str) -> dict:
    """
    获取时间范围内的 VAD 异常检测结果
    
    Args:
        start_ts: 开始时间 (ISO格式)
        end_ts: 结束时间 (ISO格式)
        
    Returns:
        异常信息字典
    """
    if _engine is None:
        return {"error": "数据库未初始化"}
    
    from llm_api_service.db.vad_repo import (
        list_vad_anomalies,
        get_anomaly_stats,
        get_anomaly_count_by_type,
        ANOMALY_NAME_CN_MAP,
    )
    from llm_api_service.tools.playback import build_playback_url
    
    try:
        start = datetime.fromisoformat(start_ts)
        end = datetime.fromisoformat(end_ts)
    except ValueError as e:
        return {"error": f"时间格式错误: {e}"}
    
    # 获取异常记录
    vad_records = list_vad_anomalies(_engine, _schema, start, end, limit=100)
    
    # 获取统计
    level_stats = get_anomaly_stats(_engine, _schema, start, end)
    type_stats = get_anomaly_count_by_type(_engine, _schema, start, end)
    
    # 构建结果
    anomaly_list = []
    for v in vad_records[:30]:  # 限制返回数量
        anomaly_name_cn = ANOMALY_NAME_CN_MAP.get(v.anomaly_name, v.anomaly_name) if v.anomaly_name else "未知"
        
        playback_url = None
        if _playback_config and v.stream_id:
            playback_url = build_playback_url(
                _playback_config,
                v.stream_id,
                v.created_at,
                30,  # 默认30秒
            )
        
        anomaly_list.append({
            "id": str(v.id),
            "anomaly_name": v.anomaly_name,
            "anomaly_name_cn": anomaly_name_cn,
            "anomaly_level": v.anomaly_level,
            "time": v.created_at.isoformat() if v.created_at else None,
            "stream_id": v.stream_id,
            "camera_name": v.camera_name,
            "location": v.camera_location,
            "thumbnail_base64": v.frame_vad_base64,
            "playback_url": playback_url,
        })
    
    # 构建类型统计的中文描述
    type_stats_cn = {
        ANOMALY_NAME_CN_MAP.get(k, k): v
        for k, v in type_stats.items()
    }
    
    return {
        "total_count": len(vad_records),
        "returned_count": len(anomaly_list),
        "level_stats": level_stats,
        "type_stats": type_stats_cn,
        "anomalies": anomaly_list,
    }


def list_reports_by_time_func(start_ts: str, end_ts: str) -> dict:
    """
    获取时间范围内的 LLM 事件报告
    
    Args:
        start_ts: 开始时间 (ISO格式)
        end_ts: 结束时间 (ISO格式)
        
    Returns:
        报告信息字典
    """
    if _engine is None:
        return {"error": "数据库未初始化"}
    
    from llm_api_service.db.report_repo import list_reports_by_time
    
    try:
        start = datetime.fromisoformat(start_ts)
        end = datetime.fromisoformat(end_ts)
    except ValueError as e:
        return {"error": f"时间格式错误: {e}"}
    
    # 获取报告
    reports = list_reports_by_time(_engine, _schema, start, end, limit=50)
    
    # 构建结果
    report_list = []
    for r in reports[:20]:  # 限制返回数量
        # 提取风险等级和摘要
        risk_level = None
        summary = None
        if r.report_json and isinstance(r.report_json, dict):
            risk_level = r.report_json.get("risk_level")
            summary = r.report_json.get("summary", "")[:200]  # 限制长度
        
        report_list.append({
            "id": r.id,
            "episode_id": r.episode_id,
            "episode_title": r.episode_title,
            "episode_start_ts": r.episode_start_ts.isoformat() if r.episode_start_ts else None,
            "episode_end_ts": r.episode_end_ts.isoformat() if r.episode_end_ts else None,
            "report_text": (r.report_text or "")[:300],  # 限制长度
            "summary": summary,
            "risk_level": risk_level,
            "target_id": r.target_id,
            "stranger_target_id": r.stranger_target_id,
        })
    
    # 统计风险等级
    risk_stats = {}
    for r in reports:
        if r.report_json and isinstance(r.report_json, dict):
            level = r.report_json.get("risk_level")
            if level is not None:
                key = f"risk_{level}"
                risk_stats[key] = risk_stats.get(key, 0) + 1
    
    return {
        "total_count": len(reports),
        "returned_count": len(report_list),
        "risk_stats": risk_stats,
        "reports": report_list,
    }


# LangChain Tool 定义
list_vad_anomalies_tool = StructuredTool.from_function(
    func=list_vad_anomalies_func,
    name="list_vad_anomalies",
    description=(
        "获取时间范围内的异常检测结果（VAD）。"
        "包括：跌倒(fall)、打架(fight)、烟雾(smoke)、火灾(fire)、入侵(intrusion)等。"
        "需要先调用 parse_time_range 获取 start_ts 和 end_ts。"
        "返回：异常列表、等级统计、类型统计。"
    ),
    args_schema=TimeRangeInput,
)

list_reports_by_time_tool = StructuredTool.from_function(
    func=list_reports_by_time_func,
    name="list_reports_by_time",
    description=(
        "获取时间范围内的详细事件报告（LLM生成）。"
        "这些报告包含事件的详细描述、风险等级分析。"
        "需要先调用 parse_time_range 获取 start_ts 和 end_ts。"
        "返回：报告列表、风险等级统计。"
    ),
    args_schema=TimeRangeInput,
)

