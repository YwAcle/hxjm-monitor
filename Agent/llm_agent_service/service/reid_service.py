"""
基于规则的 ReID 服务
检测输入是否包含熟人名字，执行相应的查询和分析
"""
from __future__ import annotations

import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

import pytz
from PIL import Image
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from sqlalchemy import text
from sqlalchemy.engine import Engine

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from llm_chat_service.db.reid_repo import list_reid_targets, list_persons_by_name
from llm_chat_service.db.tracklet_repo import list_tracklets_for_persons, TrackletRow
from llm_chat_service.db.report_repo import list_reports_for_persons
from llm_api_service.db.vad_repo import list_vad_anomalies, VADRow
from llm_agent_service.service.memory import SessionMemoryStore
from llm_agent_service.tools.time_parser import parse_time
from llm_report_service.llm.vision import decode_base64_image, image_to_data_url


@dataclass
class TimeRange:
    """时间范围"""
    start_ts: datetime
    end_ts: datetime
    label: str


class TimeRangeParseError(ValueError):
    """无法将用户输入转换为确定的监控查询时间范围。"""


class ReidService:
    """基于规则的 ReID 服务"""
    
    def __init__(
        self,
        engine: Engine,
        schema: str,
        llm: BaseChatModel,
        tz: str = "Asia/Shanghai",
        playback_base_url: str = "http://192.168.109.191:9996",
        auto_reload_interval: int = 60,
        memory_max_sessions: int = 1000,
        memory_max_messages: int = 20,
    ):
        self.engine = engine
        self.schema = schema
        self.llm = llm
        self.tz = tz
        self.playback_base_url = playback_base_url or "http://192.168.109.191:9996"
        self.timezone = pytz.timezone(tz)
        self.auto_reload_interval = auto_reload_interval  # 自动重新加载间隔（秒）
        self.memory = SessionMemoryStore(
            max_sessions=memory_max_sessions,
            max_messages=memory_max_messages,
        )
        
        # 从数据库加载熟人列表
        self.known_persons: dict[str, list[str]] = {}  # name -> [person_id, ...]
        self._known_persons_lock = threading.Lock()  # 线程锁，保护 known_persons
        self._load_known_persons()
        
        # 启动自动检查线程
        self._stop_checking = False
        self._check_thread = None
        self._start_auto_check()

    @staticmethod
    def _message_text(message: BaseMessage) -> str:
        content = message.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and block.get("text") is not None:
                    parts.append(str(block["text"]))
            return "".join(parts)
        return str(content)

    def _invoke_text(
        self,
        prompt: str,
        *,
        max_new_tokens: int,
        history: list[BaseMessage] | None = None,
    ) -> str:
        response = self.llm.invoke(
            [*(history or []), HumanMessage(content=prompt)],
            max_new_tokens=max_new_tokens,
        )
        return self._message_text(response).strip()

    def _invoke_image(
        self,
        prompt: str,
        image,
        *,
        max_new_tokens: int,
        history: list[BaseMessage] | None = None,
    ) -> str:
        messages = list(history or [])
        if getattr(self.llm, "_llm_type", "") in {"sglang_openai", "vllm_openai"}:
            messages.append(
                HumanMessage(
                    content=[
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_to_data_url(image)},
                        },
                    ]
                )
            )
            response = self.llm.invoke(
                messages,
                max_new_tokens=max_new_tokens,
            )
            return self._message_text(response).strip()

        raise RuntimeError("图片 ReID 当前仅支持 SGLang 或 vLLM 多模态接口")
    
    def _load_known_persons(self):
        """从数据库加载所有熟人（reid_target）"""
        try:
            targets = list_reid_targets(self.engine, self.schema, limit=2000, active_only=True)
            new_known_persons: dict[str, list[str]] = {}
            for t in targets:
                name = t.name.strip()
                if name:
                    if name not in new_known_persons:
                        new_known_persons[name] = []
                    new_known_persons[name].append(t.id)
            
            with self._known_persons_lock:
                old_count = len(self.known_persons)
                self.known_persons = new_known_persons
                new_count = len(self.known_persons)
                
            print(f"[ReidService] 加载了 {new_count} 个熟人" + (f"（从 {old_count} 更新）" if old_count != new_count else ""))
            return True
        except Exception as e:
            print(f"[ReidService] 加载熟人列表失败: {e}")
            return False
    
    def reload_known_persons(self):
        """重新加载熟人列表（手动触发）"""
        return self._load_known_persons()
    
    def _check_and_reload_persons(self):
        """检查数据库是否有变化，如果有则重新加载"""
        try:
            # 获取当前数据库中的熟人
            targets = list_reid_targets(self.engine, self.schema, limit=2000, active_only=True)
            current_persons: dict[str, list[str]] = {}
            for t in targets:
                name = t.name.strip()
                if name:
                    if name not in current_persons:
                        current_persons[name] = []
                    current_persons[name].append(t.id)
            
            # 比较是否有变化
            with self._known_persons_lock:
                old_persons = self.known_persons.copy()
            
            # 检查是否有变化（比较名字列表和对应的ID列表）
            if current_persons != old_persons:
                print(f"[ReidService] 检测到熟人列表变化，正在更新...")
                self._load_known_persons()
            else:
                # 只在调试时打印（可以注释掉减少日志）
                pass
                
        except Exception as e:
            print(f"[ReidService] 检查熟人列表变化失败: {e}")
    
    def _auto_check_loop(self):
        """自动检查循环（在后台线程运行）"""
        while not self._stop_checking:
            time.sleep(self.auto_reload_interval)
            if not self._stop_checking:
                self._check_and_reload_persons()
    
    def _start_auto_check(self):
        """启动自动检查线程"""
        if self.auto_reload_interval > 0:
            self._check_thread = threading.Thread(target=self._auto_check_loop, daemon=True)
            self._check_thread.start()
            print(f"[ReidService] 已启动自动检查线程，每 {self.auto_reload_interval} 秒检查一次熟人列表")
    
    def stop_auto_check(self):
        """停止自动检查"""
        self._stop_checking = True
        if self._check_thread and self._check_thread.is_alive():
            self._check_thread.join(timeout=2)
            print("[ReidService] 已停止自动检查线程")
    
    def _parse_time_range(self, prompt: str, now: datetime | None = None) -> TimeRange:
        """适配统一 parse_time 结果到旧查询接口所需的时间范围。"""
        result = parse_time(prompt, reference_time=now, timezone=self.timezone.zone)
        if not result.success or result.start is None or result.end is None:
            raise TimeRangeParseError(result.error or "无法识别时间范围")
        # 查询 SQL 使用 < :end_ts；具体时刻查询其后一分钟，避免空区间。
        end_ts = result.start + timedelta(minutes=1) if result.type == "datetime" else result.end
        return TimeRange(start_ts=result.start, end_ts=end_ts, label=prompt.strip())
    
    def _detect_person_names(self, prompt: str) -> list[str]:
        """
        检测输入中是否包含熟人名字
        返回匹配到的名字列表
        """
        matched_names = []
        # 使用锁保护读取操作
        with self._known_persons_lock:
            person_names = list(self.known_persons.keys())
        for name in person_names:
            if name in prompt:
                matched_names.append(name)
        return matched_names
    
    def _get_person_ids(self, names: list[str]) -> list[str]:
        """根据名字获取所有对应的 person_id"""
        person_ids = []
        # 使用锁保护读取操作
        with self._known_persons_lock:
            for name in names:
                ids = self.known_persons.get(name, [])
                person_ids.extend(ids)
        return list(set(person_ids))  # 去重
    
    def _get_camera_from_stream_id(self, stream_id: str) -> str:
        """
        从 stream_id 获取摄像头名称（如 camera_1, camera_2）
        stream_id 可能是 UUID 或字符串路径（如 "live/camera_4_boxmot"）
        """
        # 首先尝试从 stream_id 字符串中直接提取 camera_X
        # 例如: "live/camera_4_boxmot" -> "camera_4"
        match = re.search(r"camera_(\d+)", str(stream_id), re.IGNORECASE)
        if match:
            return f"camera_{match.group(1)}"
        
        # 如果 stream_id 是 UUID，尝试查询数据库
        # 检查是否是 UUID 格式（8-4-4-4-12 的十六进制字符串）
        uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        if re.match(uuid_pattern, str(stream_id), re.IGNORECASE):
            try:
                sql = text(
                    f"""
                    SELECT stream_name
                    FROM {self.schema}.camera_stream
                    WHERE id = :stream_id
                    LIMIT 1
                    """
                )
                with self.engine.connect() as conn:
                    row = conn.execute(sql, {"stream_id": stream_id}).mappings().first()
                    if row and row.get("stream_name"):
                        stream_name = str(row["stream_name"])
                        # 从 stream_name 中提取 camera_X
                        match = re.search(r"camera_(\d+)", stream_name, re.IGNORECASE)
                        if match:
                            return f"camera_{match.group(1)}"
            except Exception as e:
                print(f"[ReidService] 查询 stream_name 失败: {e}")
        
        # 如果都失败，使用简单规则
        try:
            hash_val = hash(str(stream_id)) % 4 + 1
            return f"camera_{hash_val}"
        except:
            return "camera_1"
    
    def _build_playback_url_from_vad(self, vad: VADRow, playback_base_url: str | None = None) -> str:
        """
        从 VAD 记录构建回放 URL。

        优先返回媒体索引中保存的 play_url。该 URL 已包含正确的流名、
        录像起始时间和时长，不能用 VAD 的创建时间重新拼接。
        """
        duration_seconds = 30.0
        if vad.media_asset_id:
            try:
                sql = text(
                    f"""
                    SELECT play_url, duration_ms
                    FROM {self.schema}.media_asset
                    WHERE id = :media_asset_id
                    LIMIT 1
                    """
                )
                with self.engine.connect() as conn:
                    row = conn.execute(sql, {"media_asset_id": vad.media_asset_id}).mappings().first()
                    if row and row.get("play_url"):
                        return str(row["play_url"])
                    if row and row.get("duration_ms"):
                        duration_seconds = float(row["duration_ms"]) / 1000.0
            except Exception as e:
                print(f"[ReidService] 查询 media_asset 回放地址失败: {e}")

        stream_path = str(vad.stream_id or "").strip().lstrip("/")
        if stream_path == "":
            stream_path = f"live/{self._get_camera_from_stream_id(vad.stream_id)}"
        elif not stream_path.startswith("live/"):
            stream_path = f"live/{stream_path}"

        path_encoded = quote(stream_path, safe="")
        start_encoded = quote(vad.created_at.isoformat(), safe="")

        duration_str = f"{duration_seconds:.3f}"
        base_url = playback_base_url or self.playback_base_url
        return f"{base_url}/get?path={path_encoded}&start={start_encoded}&duration={duration_str}"
    
    def _build_playback_url(self, tracklet: TrackletRow, playback_base_url: str | None = None) -> str:
        """
        构建回放 URL
        格式: http://192.168.108.238:9996/get?path=live%2Fcamera_2&start=2026-01-05T14%3A08%3A32.000000%2B08%3A00&duration=111.631
        """
        # 获取摄像头名称
        camera = self._get_camera_from_stream_id(tracklet.stream_id)
        
        # path: live/camera_X (URL编码后是 live%2Fcamera_X)
        path = f"live/{camera}"
        path_encoded = quote(path, safe="")
        
        # start: 使用 start_ts，精确到时分秒，毫秒设为 000000
        start_ts_clean = tracklet.start_ts.replace(microsecond=0)
        start_str = start_ts_clean.isoformat()
        start_encoded = quote(start_str, safe="")
        
        # duration: end_ts - start_ts 的秒数（浮点数）
        end_ts = tracklet.end_ts if tracklet.end_ts else tracklet.start_ts
        duration_seconds = (end_ts - tracklet.start_ts).total_seconds()
        duration_str = f"{duration_seconds:.3f}"  # 保留3位小数
        
        # 使用传入的 base_url 或默认值
        base_url = playback_base_url or self.playback_base_url
        
        # 构建完整 URL
        url = f"{base_url}/get?path={path_encoded}&start={start_encoded}&duration={duration_str}"
        return url
    
    def _summarize_reports(self, reports_text: list[str], person_names: list[str]) -> str:
        """使用大模型总结多段报告"""
        if not reports_text:
            return "该时间段内没有相关的行为分析报告。"
        
        # 合并所有报告文本
        combined_text = "\n---\n".join(reports_text[:10])  # 最多取 10 段
        
        prompt = f"""请简要总结以下关于人员【{', '.join(person_names)}】的多段行为分析报告，用一段简短的话概括主要活动和情况：

{combined_text}

请用中文简要总结（不超过100字）："""
        
        try:
            return self._invoke_text(prompt, max_new_tokens=256)
        except Exception as e:
            print(f"[ReidService] 总结报告失败: {e}")
            return "行为分析报告总结失败。"
    
    def _process_person_query(self, prompt: str, person_names: list[str], time_range: TimeRange, image_base64: str | None = None) -> dict:
        """处理行人查询"""
        print(f"[ReidService] 处理行人查询: names={person_names}, time_range={time_range.label}")
        
        # 1. 获取所有 person_id
        person_ids = self._get_person_ids(person_names)
        if not person_ids:
            # 如果有图片，先分析图片内容，然后拼接固定文本
            text_content = "Reid分析结果如下"
            if image_base64:
                image_description = self._analyze_image(image_base64, "这张图片有什么内容")
                text_content = f"{image_description}\n\n{text_content}"
            
            return {
                "type": "reid",
                "text": text_content,
                "tracklet": {"total": 0, "camera_1": 0, "camera_2": 0, "camera_3": 0, "camera_4": 0},
                "summary": f"未找到名为【{', '.join(person_names)}】的人员记录。",
                "data": {}
            }
        
        print(f"[ReidService] 找到 person_ids: {person_ids}")
        
        # 2. 查询轨迹
        tracklets = list_tracklets_for_persons(
            self.engine, self.schema, person_ids,
            time_range.start_ts, time_range.end_ts,
            limit=200
        )
        print(f"[ReidService] 查询到 {len(tracklets)} 条轨迹")
        
        # 3. 统计各摄像头轨迹数
        camera_counts = defaultdict(int)
        for t in tracklets:
            camera = self._get_camera_from_stream_id(t.stream_id)
            camera_counts[camera] += 1
        
        tracklet_stats = {
            "total": len(tracklets),
            "camera_1": camera_counts.get("camera_1", 0),
            "camera_2": camera_counts.get("camera_2", 0),
            "camera_3": camera_counts.get("camera_3", 0),
            "camera_4": camera_counts.get("camera_4", 0),
        }
        
        # 4. 获取最新 20 条轨迹的详细信息
        # 按时间倒序排列
        sorted_tracklets = sorted(tracklets, key=lambda x: x.start_ts, reverse=True)[:20]
        
        data = {}
        for i, t in enumerate(sorted_tracklets, 1):
            # 构建回放 URL
            playback_url = self._build_playback_url(t)
            data[f"tracklet{i}"] = {
                "image": t.frame_asset_base64 or t.query_asset_base64 or "",
                "recording": playback_url,
                "start_ts": t.start_ts.isoformat() if t.start_ts else None,
                "camera": self._get_camera_from_stream_id(t.stream_id),
            }
        
        # 5. 查询报告
        reports_data = list_reports_for_persons(
            self.engine, self.schema, person_ids,
            time_range.start_ts, time_range.end_ts,
            limit=50
        )
        print(f"[ReidService] 查询到 {len(reports_data)} 条报告")
        
        # 提取报告文本
        reports_text = []
        for item in reports_data:
            r = item["report"]
            if r.report_text:
                reports_text.append(r.report_text)
            elif r.report_json and isinstance(r.report_json, dict):
                summary = r.report_json.get("summary", "")
                if summary:
                    reports_text.append(summary)
        
        # 6. 使用大模型总结报告
        summary = self._summarize_reports(reports_text, person_names)
        
        # 7. 如果有图片，先分析图片内容，然后拼接固定文本
        text_content = "Reid分析结果如下"
        if image_base64:
            image_description = self._analyze_image(image_base64, "这张图片有什么内容")
            text_content = f"{image_description}\n\n{text_content}"
        
        return {
            "type": "reid",
            "text": text_content,
            "tracklet": tracklet_stats,
            "summary": summary,
            "data": data,
            "time_range": {
                "label": time_range.label,
                "start_ts": time_range.start_ts.isoformat(),
                "end_ts": time_range.end_ts.isoformat(),
            },
            "person_names": person_names,
            "person_ids": person_ids,
        }
    
    def _query_vad_anomalies_simple(self, start_ts: datetime, end_ts: datetime, limit: int = 100) -> list[VADRow]:
        """
        简化版本的 VAD 查询，避免 JOIN 时的类型转换问题
        直接查询 VAD 表，然后单独获取摄像头信息
        """
        sql = text(
            f"""
            SELECT 
                v.id,
                v.created_at,
                v.media_asset_id,
                v.stream_id,
                v.frame_vad_base64,
                v.anomaly_name,
                v.anomaly_level
            FROM {self.schema}.vad v
            WHERE v.created_at >= :start_ts
              AND v.created_at < :end_ts
            ORDER BY v.created_at DESC
            LIMIT :limit
            """
        )
        
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {
                "start_ts": start_ts,
                "end_ts": end_ts,
                "limit": limit,
            }).mappings().all()
        
        # 转换结果
        vads = []
        for row in rows:
            vad = VADRow(
                id=int(row["id"]),
                created_at=row["created_at"],
                media_asset_id=str(row["media_asset_id"]) if row["media_asset_id"] else None,
                stream_id=str(row["stream_id"]) if row["stream_id"] else "",
                frame_vad_base64=str(row["frame_vad_base64"]) if row["frame_vad_base64"] else None,
                anomaly_name=str(row["anomaly_name"]) if row["anomaly_name"] else None,
                anomaly_level=int(row["anomaly_level"]) if row["anomaly_level"] else None,
                camera_id=None,
                camera_name=None,
                camera_location=None,
            )
            vads.append(vad)
        
        return vads
    
    def _process_vad_query(self, prompt: str, time_range: TimeRange, image_base64: str | None = None) -> dict:
        """处理异常查询（包含'异常'关键词）"""
        print(f"[ReidService] 处理异常查询: time_range={time_range.label}")
        
        # 1. 查询 VAD 异常记录
        # 注意：由于 stream_id 可能是字符串，需要处理类型转换问题
        try:
            vad_records = list_vad_anomalies(
                self.engine, self.schema,
                time_range.start_ts, time_range.end_ts,
                limit=100
            )
        except Exception as e:
            # 如果查询失败，尝试直接查询 VAD 表（不 JOIN camera_stream）
            print(f"[ReidService] 查询 VAD 异常失败，尝试简化查询: {e}")
            vad_records = self._query_vad_anomalies_simple(
                time_range.start_ts, time_range.end_ts, limit=100
            )
        print(f"[ReidService] 查询到 {len(vad_records)} 条异常记录")
        
        if not vad_records:
            # 格式化为标准日期：YYYY-MM-DD
            date_str = time_range.start_ts.strftime("%Y-%m-%d")
            
            # 如果有图片，先分析图片内容，然后拼接固定文本
            text_content = "根据您的查询，我发现了以下异常情况："
            if image_base64:
                image_description = self._analyze_image(image_base64, "这张图片有什么内容")
                text_content = f"{image_description}\n\n{text_content}"
            
            return {
                "type": "vad",
                "text": text_content,
                "date": date_str,
                "summary": "该时间段内未检测到异常事件。",
                "tracklet": {"total": 0, "camera_1": 0, "camera_2": 0, "camera_3": 0, "camera_4": 0},
                "data": {}
            }
        
        # 2. 统计各摄像头异常数
        camera_counts = defaultdict(int)
        for vad in vad_records:
            camera = self._get_camera_from_stream_id(vad.stream_id)
            camera_counts[camera] += 1
        
        tracklet_stats = {
            "total": len(vad_records),
            "camera_1": camera_counts.get("camera_1", 0),
            "camera_2": camera_counts.get("camera_2", 0),
            "camera_3": camera_counts.get("camera_3", 0),
            "camera_4": camera_counts.get("camera_4", 0),
        }
        
        # 3. 获取最新 20 条异常记录的详细信息
        sorted_vads = sorted(vad_records, key=lambda x: x.created_at, reverse=True)[:20]
        
        # 4. 查询对应的 llm_report
        vad_ids = [vad.id for vad in vad_records]
        reports_text = []
        
        # 通过 vad_id 查询报告
        for vad_id in vad_ids[:50]:  # 最多查询50个
            try:
                sql = text(
                    f"""
                    SELECT report_text, report_json
                    FROM {self.schema}.llm_report
                    WHERE vad_id = :vad_id
                    LIMIT 1
                    """
                )
                with self.engine.connect() as conn:
                    row = conn.execute(sql, {"vad_id": vad_id}).mappings().first()
                    if row:
                        if row.get("report_text"):
                            reports_text.append(row["report_text"])
                        elif row.get("report_json"):
                            report_json = row["report_json"]
                            if isinstance(report_json, str):
                                import json
                                try:
                                    report_json = json.loads(report_json)
                                except:
                                    pass
                            if isinstance(report_json, dict):
                                summary = report_json.get("summary", "")
                                if summary:
                                    reports_text.append(summary)
            except Exception as e:
                print(f"[ReidService] 查询 VAD {vad_id} 的报告失败: {e}")
        
        # 5. 使用大模型总结报告
        summary = self._summarize_vad_reports(reports_text, time_range.label)
        
        # 6. 构建返回数据
        data = {}
        for i, vad in enumerate(sorted_vads, 1):
            playback_url = self._build_playback_url_from_vad(vad)
            data[f"tracklet{i}"] = {
                "image": vad.frame_vad_base64 or "",
                "recording": playback_url,
                "start_ts": vad.created_at.isoformat() if vad.created_at else None,
                "camera": self._get_camera_from_stream_id(vad.stream_id),
            }
        
        # 格式化为标准日期：YYYY-MM-DD
        date_str = time_range.start_ts.strftime("%Y-%m-%d")
        
        # 如果有图片，先分析图片内容，然后拼接固定文本
        text_content = "根据您的查询，我发现了以下异常情况："
        if image_base64:
            image_description = self._analyze_image(image_base64, "这张图片有什么内容")
            text_content = f"{image_description}\n\n{text_content}"
        
        return {
            "type": "vad",
            "text": text_content,
            "date": date_str,
            "summary": summary,
            "tracklet": tracklet_stats,
            "data": data,
        }
    
    def _summarize_vad_reports(self, reports_text: list[str], date_label: str) -> str:
        """使用大模型总结异常报告"""
        if not reports_text:
            return f"{date_label}未检测到异常事件。"
        
        # 合并所有报告文本
        combined_text = "\n---\n".join(reports_text[:10])  # 最多取 10 段
        
        prompt = f"""请简要总结以下{date_label}的多段异常分析报告，用一段简短的话概括主要异常情况和类型：

{combined_text}

请用中文简要总结（不超过100字）："""
        
        try:
            return self._invoke_text(prompt, max_new_tokens=256)
        except Exception as e:
            print(f"[ReidService] 总结异常报告失败: {e}")
            return f"{date_label}检测到 {len(reports_text)} 起异常事件。"
    
    def _analyze_image(self, image_base64: str, query: str = "这张图片有什么内容") -> str:
        """使用大模型分析图片内容"""
        try:
            image = decode_base64_image(image_base64)
            if image is None:
                return "无法解析图片。"
            prompt = f"{query}？请用中文描述。"
            return self._invoke_image(
                prompt,
                image,
                max_new_tokens=512,
            )
        except Exception as e:
            print(f"[ReidService] 图片分析失败: {e}")
            return f"图片分析失败：{str(e)}"
    
    def _process_general_query(
        self,
        prompt: str,
        image_base64: str | None = None,
        history: list[BaseMessage] | None = None,
    ) -> dict:
        """处理普通问题（不包含人名）"""
        print(f"[ReidService] 处理普通问题")
        
        try:
            if image_base64:
                image = decode_base64_image(image_base64)
                if image is not None:
                    response = self._invoke_image(
                        prompt,
                        image,
                        max_new_tokens=1024,
                        history=history,
                    )
                else:
                    response = self._invoke_text(
                        prompt,
                        max_new_tokens=1024,
                        history=history,
                    )
            else:
                response = self._invoke_text(
                    prompt,
                    max_new_tokens=1024,
                    history=history,
                )
            
            return {
                "type": "normal",
                "text": response
            }
        except Exception as e:
            print(f"[ReidService] 调用大模型失败: {e}")
            return {
                "type": "normal",
                "text": f"抱歉，处理您的问题时出错了：{str(e)}"
            }
    
    def _process_super_resolution_query(self, prompt: str, image_base64: str | None = None) -> dict:
        """处理超分查询"""
        print(f"[ReidService] 处理超分查询")

        if not image_base64:
            return {
                "type": "super_resolution",
                "navigate_to": "super_resolution",
                "text": "请上传需要超分的图片。",
                "data": {"status": "missing_image", "description": "未提供输入图片"},
            }

        image = decode_base64_image(image_base64)
        if image is None:
            return {
                "type": "super_resolution",
                "navigate_to": "super_resolution",
                "text": "图片解码失败，请重新上传。",
                "data": {"status": "invalid_image", "description": "无法读取输入图片"},
            }

        # Pillow 的 bicubic 插值不依赖额外模型，适合在线请求中的低延迟放大。
        scale_match = re.search(r"(?:放大|超分|upscale)?\s*([24])\s*[xX倍]", prompt)
        scale = int(scale_match.group(1)) if scale_match else 2
        original_width, original_height = image.size
        max_side = 4096
        scale = min(scale, max_side / max(original_width, original_height))
        scale = max(1.0, scale)
        output_size = (
            max(1, round(original_width * scale)),
            max(1, round(original_height * scale)),
        )
        result_image = image.resize(output_size, resample=Image.Resampling.BICUBIC)
        result_data_url = image_to_data_url(
            result_image,
            max_side=max_side,
            jpeg_quality=92,
        )

        return {
            "type": "super_resolution",
            "navigate_to": "super_resolution",
            "text": f"图片超分完成：{output_size[0]}×{output_size[1]}。",
            "data": {
                "status": "success",
                "description": "图片已完成快速超分",
                "image_base64": result_data_url,
                "original_size": [original_width, original_height],
                "result_size": list(output_size),
                "scale": scale,
            }
        }

    @staticmethod
    def _memory_response_text(result: dict[str, Any]) -> str:
        text_value = result.get("text")
        visible_text = str(text_value).strip() if text_value is not None else ""
        summary_value = result.get("summary")
        summary = str(summary_value).strip() if summary_value is not None else ""

        if visible_text and summary and summary not in visible_text:
            return f"{visible_text}\n\n业务摘要：{summary}"
        return visible_text or summary

    def clear_memory(self, session_id: str) -> bool:
        return self.memory.clear(session_id)

    def process(
        self,
        prompt: str,
        image_base64: str | None = None,
        session_id: str | None = None,
    ) -> dict:
        """
        处理输入请求
        
        Args:
            prompt: 用户输入的问题
            image_base64: 可选的 base64 编码的图片
            
        返回：
            响应字典
        """
        prompt = (prompt or "").strip()
        if not prompt:
            return {"text": "请输入您的问题。"}

        if session_id:
            with self.memory.conversation(session_id) as conversation:
                result = self._process_request(
                    prompt,
                    image_base64=image_base64,
                    history=conversation.messages(),
                )
                memory_prompt = (
                    f"{prompt}\n[用户上传了一张图片]"
                    if image_base64
                    else prompt
                )
                conversation.add_exchange(
                    memory_prompt,
                    self._memory_response_text(result),
                )
                return result

        return self._process_request(prompt, image_base64=image_base64, history=[])

    def _process_request(
        self,
        prompt: str,
        *,
        image_base64: str | None,
        history: list[BaseMessage],
    ) -> dict:
        has_image = image_base64 is not None and str(image_base64).strip() != ""
        print(f"[ReidService] 收到请求: prompt='{prompt}', has_image={has_image}")
        
        # 0. 检测是否包含"超分"关键词 (新增)
        if "超分" in prompt:
            print(f"[ReidService] 检测到'超分'关键词，处理超分查询")
            return self._process_super_resolution_query(prompt, image_base64)
        
        # 1. 检测是否包含"异常"关键词
        if "异常" in prompt:
            print(f"[ReidService] 检测到'异常'关键词，处理异常查询")
            # 解析时间范围
            time_range = self._parse_time_range(prompt)
            # 处理异常查询（传入图片）
            result = self._process_vad_query(prompt, time_range, image_base64)
            result["navigate_to"] = "vad"
            result["page_index"] = 4
            return result
        
        # 2. 检测是否包含熟人名字
        person_names = self._detect_person_names(prompt)
        print(f"[ReidService] 检测到的熟人名字: {person_names}")
        
        if person_names:
            print(f"[ReidService] 检测到熟人名字，处理行人查询")
            # 解析时间范围
            time_range = self._parse_time_range(prompt)
            # 处理行人查询（传入图片）
            result = self._process_person_query(prompt, person_names, time_range, image_base64)
            result["navigate_to"] = "reid"
            return result
        else:
            print(f"[ReidService] 未检测到异常或熟人，处理普通问题")
            # 处理普通问题（传入图片，直接多模态分析）
            return self._process_general_query(
                prompt,
                image_base64,
                history=history,
            )
