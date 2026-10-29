"""
回放 URL 构建工具
"""
from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

try:
    # 新版 LangChain (>=0.2.0)
    from langchain_core.tools import Tool
except ImportError:
    # 旧版 LangChain
    from langchain.tools import Tool

from llm_api_service.config import PlaybackConfig


def build_playback_url(
    config: PlaybackConfig,
    stream_id: str,
    start_ts: datetime,
    duration: int = 30,
) -> str:
    """
    构建视频回放 URL
    
    Args:
        config: 回放配置
        stream_id: 流ID (如 camera_1_reid)
        start_ts: 开始时间
        duration: 时长（秒）
        
    Returns:
        回放 URL
    
    URL 格式:
    http://192.168.108.238:9996/get?duration=4.559&path=live%2Fcamera_1_boxmot&start=2026-01-04T20%3A54%3A42.069246%2B08%3A00
    """
    # 从 stream_id 提取摄像头名称
    # camera_1_reid -> camera_1_boxmot
    if "_reid" in stream_id:
        path_name = stream_id.replace("_reid", "_boxmot")
    elif "_vad" in stream_id:
        path_name = stream_id.replace("_vad", "_boxmot")
    else:
        path_name = stream_id
    
    # 编码路径
    path = f"live/{path_name}"
    encoded_path = quote(path, safe="")
    
    # 编码时间
    start_iso = start_ts.isoformat()
    encoded_start = quote(start_iso, safe="")
    
    url = f"http://{config.host}:{config.port}/get?duration={duration}&path={encoded_path}&start={encoded_start}"
    
    return url


def build_playback_url_func(stream_id: str, start_ts: str, duration: int = 30) -> dict:
    """
    工具函数: 构建回放 URL
    
    Args:
        stream_id: 流ID
        start_ts: 开始时间 (ISO格式)
        duration: 时长（秒）
        
    Returns:
        包含 URL 的字典
    """
    # 使用默认配置
    config = PlaybackConfig()
    
    try:
        start = datetime.fromisoformat(start_ts)
    except ValueError as e:
        return {"error": f"时间格式错误: {e}"}
    
    url = build_playback_url(config, stream_id, start, duration)
    
    return {
        "url": url,
        "stream_id": stream_id,
        "start_ts": start_ts,
        "duration": duration,
    }


# LangChain Tool 定义
build_playback_url_tool = Tool(
    name="build_playback_url",
    func=lambda x: build_playback_url_func(**eval(x)) if isinstance(x, str) else build_playback_url_func(**x),
    description=(
        "构建视频回放URL。"
        "输入：{stream_id: 流ID, start_ts: ISO时间, duration: 时长秒数}。"
        "输出：{url: 回放URL}。"
        "一般不需要直接调用此工具，轨迹和异常查询会自动返回 playback_url。"
    ),
)

