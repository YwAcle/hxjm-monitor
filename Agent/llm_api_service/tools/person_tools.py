"""
人员相关工具 - 查询人员信息和轨迹
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

try:
    # 新版 LangChain (>=0.2.0)
    from langchain_core.tools import Tool, StructuredTool
except ImportError:
    # 旧版 LangChain
    from langchain.tools import Tool, StructuredTool

from pydantic import BaseModel, Field

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


def get_person_by_name_func(name: str) -> dict:
    """
    根据姓名查找人员
    
    Args:
        name: 人员姓名
        
    Returns:
        人员信息字典
    """
    if _engine is None:
        return {"error": "数据库未初始化"}
    
    from llm_api_service.db.reid_repo import get_person_by_name
    
    person = get_person_by_name(_engine, _schema, name)
    
    if person is None:
        return {
            "found": False,
            "message": f"未找到姓名包含'{name}'的人员",
        }
    
    return {
        "found": True,
        "id": person.id,
        "name": person.name,
        "employee_id": person.employee_id,
        # 不返回 image_base64 以节省 token
    }


class ListTrackletsInput(BaseModel):
    """list_tracklets_for_person 的输入参数"""
    person_id: str = Field(description="人员ID（从 get_person_by_name 获取）")
    start_ts: str = Field(description="开始时间，ISO格式（从 parse_time_range 获取）")
    end_ts: str = Field(description="结束时间，ISO格式（从 parse_time_range 获取）")


def list_tracklets_for_person_func(person_id: str, start_ts: str, end_ts: str) -> dict:
    """
    获取指定人员在时间范围内的轨迹
    
    Args:
        person_id: 人员ID
        start_ts: 开始时间 (ISO格式)
        end_ts: 结束时间 (ISO格式)
        
    Returns:
        轨迹信息字典
    """
    if _engine is None:
        return {"error": "数据库未初始化"}
    
    from llm_api_service.db.tracklet_repo import (
        list_tracklets_for_person,
        get_camera_stats_for_person,
    )
    from llm_api_service.tools.playback import build_playback_url
    
    try:
        start = datetime.fromisoformat(start_ts)
        end = datetime.fromisoformat(end_ts)
    except ValueError as e:
        return {"error": f"时间格式错误: {e}"}
    
    # 获取轨迹
    tracklets = list_tracklets_for_person(_engine, _schema, person_id, start, end, limit=100)
    
    # 获取摄像头统计
    camera_stats = get_camera_stats_for_person(_engine, _schema, person_id, start, end)
    
    # 构建结果
    tracklet_list = []
    for t in tracklets[:20]:  # 限制返回数量
        duration_seconds = 0
        if t.end_ts and t.start_ts:
            duration_seconds = (t.end_ts - t.start_ts).total_seconds()
        
        playback_url = None
        if _playback_config and t.stream_id:
            playback_url = build_playback_url(
                _playback_config,
                t.stream_id,
                t.start_ts,
                int(duration_seconds) if duration_seconds > 0 else 30,
            )
        
        tracklet_list.append({
            "id": t.id,
            "stream_id": t.stream_id,
            "start_ts": t.start_ts.isoformat() if t.start_ts else None,
            "end_ts": t.end_ts.isoformat() if t.end_ts else None,
            "duration_seconds": duration_seconds,
            "camera_name": t.camera_name,
            "location": t.camera_location,
            "thumbnail_base64": t.query_asset_base64,
            "playback_url": playback_url,
        })
    
    camera_stats_list = [
        {
            "stream_id": cs.stream_id,
            "camera_name": cs.camera_name,
            "location": cs.location,
            "count": cs.count,
        }
        for cs in camera_stats
    ]
    
    return {
        "total_count": len(tracklets),
        "returned_count": len(tracklet_list),
        "camera_stats": camera_stats_list,
        "tracklets": tracklet_list,
    }


# LangChain Tool 定义
get_person_by_name_tool = Tool(
    name="get_person_by_name",
    func=get_person_by_name_func,
    description=(
        "根据姓名查找人员信息。"
        "输入：人员姓名（支持模糊匹配）。"
        "输出：{found: bool, id: 人员ID, name: 姓名}。"
        "如果用户问'张嘉豪今天做了什么'，应该用'张嘉豪'作为输入。"
    ),
)

list_tracklets_for_person_tool = StructuredTool.from_function(
    func=list_tracklets_for_person_func,
    name="list_tracklets_for_person",
    description=(
        "获取指定人员在时间范围内的所有轨迹记录。"
        "需要先调用 get_person_by_name 获取 person_id，"
        "以及 parse_time_range 获取 start_ts 和 end_ts。"
        "返回：轨迹列表、各摄像头统计。"
    ),
    args_schema=ListTrackletsInput,
)

