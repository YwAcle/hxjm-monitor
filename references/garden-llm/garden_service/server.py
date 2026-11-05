#!/usr/bin/env python3
"""Runtime entrypoint and orchestration layer for Garden.

This module coordinates the long-lived service concerns: HTTP routes, ZeroMQ
ingestion, worker lifecycle, dashboard state, and robot-dog SSE sessions. It
delegates prompt handling, image decoding, and model inference to dedicated
modules so responsibilities remain explicit.
"""

import json
import os
import queue
import signal
import threading
import time
import traceback
import uuid
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import zmq
from PIL import Image

from garden_config import (
    DEFAULT_HTTP_HOST,
    DEFAULT_HTTP_PORT,
    DEFAULT_IPC_ADDR,
    DEFAULT_MODEL_PATH,
    DEFAULT_MODEL_WORKERS,
    DEFAULT_PROMPT_TEMPLATE,
    DEFAULT_REPLAY_BUFFER_SIZE,
    DEFAULT_REPLAY_WINDOW_MS,
    DEFAULT_SESSION_CLEANUP_INTERVAL_MS,
    DEFAULT_SESSION_IDLE_TIMEOUT_MS,
    DEFAULT_SESSION_QUEUE_SIZE,
    DEFAULT_SESSION_TTL_MS,
    DEFAULT_SSE_HEARTBEAT_SEC,
    DEFAULT_TASK_NAMESPACE,
    resolve_device_names,
    resolve_expected_streams,
)
from image_utils import image_to_data_url
from model_runner import GardenModelRunner, log
from prompting import normalize_camera_id, normalize_stream_name


# Small helpers used across multiple orchestration paths stay here instead of
# being duplicated in session, HTTP, and worker code.
def now_ms() -> int:
    return int(time.time() * 1000)


def random_token(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"

# HTTP 请求处理器：处理 REST API 和 SSE 请求
class GardenHttpHandler(BaseHTTPRequestHandler):
    """Thin HTTP adapter that forwards requests into GardenService."""

    service = None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        #   可视化仪表盘（Garden Vision Console）
        if path in ("/", "/index.html"):
            html = self.service.render_dashboard_html()
            payload = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        # 获取最新检测结果
        if path == "/api/latest":
            payload = json.dumps(
                self.service.get_latest_result(),
                ensure_ascii=False
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        # 获取所有摄像头流状态
        if path == "/api/streams":
            payload = json.dumps(
                self.service.get_dashboard_payload(),
                ensure_ascii=False
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        # 查询会话状态
        if path.startswith("/api/robot-dog/sessions/") and not path.endswith("/events"):
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[:3] == ["api", "robot-dog", "sessions"]:
                session_id = parts[3]
                ok, auth_error = self.service.authorize_request(self)
                if not ok:
                    self._send_json(auth_error["http_status"], auth_error["body"])
                    return
                payload, status_code = self.service.get_robot_dog_session_info(
                    session_id,
                    self.headers.get("X-Session-Token", "")
                )
                self._send_json(status_code, payload)
                return
        # SSE 事件流订阅
        if path.startswith("/api/robot-dog/sessions/") and path.endswith("/events"):
            session_id = path.split("/")[4]
            self.service.stream_robot_dog_events(self, session_id)
            return

        self.send_response(404)
        self.end_headers()
    # 创建机器人订阅会话
    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/robot-dog/sessions":
            ok, auth_error = self.service.authorize_request(self)
            if not ok:
                self._send_json(auth_error["http_status"], auth_error["body"])
                return
            body = self._read_json_body()
            payload, status_code = self.service.create_robot_dog_session(body)
            self._send_json(status_code, payload)
            return

        self.send_response(404)
        self.end_headers()
    # 关闭会话
    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/robot-dog/sessions/"):
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[:3] == ["api", "robot-dog", "sessions"]:
                session_id = parts[3]
                ok, auth_error = self.service.authorize_request(self)
                if not ok:
                    self._send_json(auth_error["http_status"], auth_error["body"])
                    return
                payload, status_code = self.service.close_robot_dog_session(
                    session_id,
                    self.headers.get("X-Session-Token", "")
                )
                self._send_json(status_code, payload)
                return

        self.send_response(404)
        self.end_headers()

    def _read_json_body(self) -> Dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, status_code: int, payload: Dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format, *args):
        return

# 机器人会话管理 维护每个机器人的订阅状态
class RobotDogSession:
    """In-memory subscription state for one robot-dog SSE consumer."""
    def __init__(
        self,
        session_id: str,
        session_token: str,
        client_name: str,
        camera_ids: List[str],
        task_names: List[str],
        alert_only: bool,
        ttl_ms: int,
        idle_timeout_ms: int,
        heartbeat_interval_ms: int,
        replay_window_ms: int,
        replay_buffer_size: int,
        event_queue_size: int = DEFAULT_SESSION_QUEUE_SIZE
    ):
        self.session_id = session_id
        self.session_token = session_token
        self.client_name = client_name
        self.camera_ids = set(camera_ids)
        self.task_names = set(task_names)
        self.alert_only = alert_only
        self.status = "INIT"
        self.created_at_ms = now_ms()
        self.last_active_at_ms = self.created_at_ms
        self.closed_at_ms: Optional[int] = None
        self.expires_at_ms = self.created_at_ms + ttl_ms
        self.ttl_ms = ttl_ms
        self.idle_timeout_ms = idle_timeout_ms
        self.heartbeat_interval_ms = heartbeat_interval_ms
        self.replay_window_ms = replay_window_ms
        self.replay_buffer_size = replay_buffer_size
        self.last_event_id = "0"
        self.connection_count = 0
        self.queue: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue(maxsize=event_queue_size)
        self.replay_buffer: "deque[Dict[str, Any]]" = deque(maxlen=replay_buffer_size)

    def accepts(self, payload: Dict[str, Any]) -> bool:
        if self.camera_ids and normalize_camera_id(payload) not in self.camera_ids:
            return False
        if self.task_names and str(payload.get("task", "")) not in self.task_names:
            return False
        result = payload.get("result", {})
        if self.alert_only and not result.get("has_target", False):
            return False
        return True

    def enqueue(self, event: Optional[Dict[str, Any]]) -> None:
        try:
            self.queue.put_nowait(event)
            return
        except queue.Full:
            pass

        try:
            self.queue.get_nowait()
        except queue.Empty:
            pass

        try:
            self.queue.put_nowait(event)
        except queue.Full:
            pass

    def touch(self) -> None:
        self.last_active_at_ms = now_ms()

    def is_expired(self, current_ms: int) -> bool:
        if self.status in ("CLOSED", "EXPIRED"):
            return True
        if current_ms >= self.expires_at_ms:
            return True
        if current_ms - self.last_active_at_ms >= self.idle_timeout_ms:
            return True
        return False

    def mark_active(self) -> None:
        self.status = "ACTIVE"
        self.connection_count += 1
        self.touch()

    def mark_closed(self) -> None:
        self.status = "CLOSED"
        self.closed_at_ms = now_ms()
        self.touch()

    def mark_expired(self) -> None:
        self.status = "EXPIRED"
        self.closed_at_ms = now_ms()
        self.touch()

    def append_replay_event(self, event: Dict[str, Any]) -> None:
        self.replay_buffer.append(event)
        self.last_event_id = str(event["id"])
        self._prune_replay_buffer()

    def _prune_replay_buffer(self) -> None:
        cutoff_ms = now_ms() - self.replay_window_ms
        while self.replay_buffer and int(self.replay_buffer[0].get("timestamp_ms", 0)) < cutoff_ms:
            self.replay_buffer.popleft()

    def replay_events_after(self, last_event_id: str) -> Optional[List[Dict[str, Any]]]:
        self._prune_replay_buffer()
        if not self.replay_buffer:
            return []
        try:
            requested = int(last_event_id)
        except ValueError:
            return None

        first_id = int(self.replay_buffer[0]["id"])
        latest_id = int(self.replay_buffer[-1]["id"])
        if requested > latest_id:
            return None
        if requested < first_id - 1:
            return None

        return [item for item in self.replay_buffer if int(item["id"]) > requested]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "client_name": self.client_name,
            "created_at_ms": self.created_at_ms,
            "last_active_at_ms": self.last_active_at_ms,
            "expires_at_ms": self.expires_at_ms,
            "ttl_ms": self.ttl_ms,
            "idle_timeout_ms": self.idle_timeout_ms,
            "heartbeat_interval_ms": self.heartbeat_interval_ms,
            "replay_window_ms": self.replay_window_ms,
            "replay_buffer_size": self.replay_buffer_size,
            "last_event_id": self.last_event_id,
            "camera_ids": sorted(self.camera_ids),
            "task_names": sorted(self.task_names),
            "alert_only": self.alert_only
        }

# 服务核心协调器 管理整个服务生命周期
class GardenService:
    """Coordinate frame ingestion, model workers, dashboard state, and SSE."""

    def __init__(self):
        self.addr = os.getenv("GARDEN_ZMQ_ADDR", DEFAULT_IPC_ADDR)
        self.model_path = os.getenv("GARDEN_MODEL_PATH", DEFAULT_MODEL_PATH)
        self.prompt_template_path = os.getenv(
            "GARDEN_PROMPT_TEMPLATE", DEFAULT_PROMPT_TEMPLATE
        )
        self.running = True
        self.normal_log_interval = float(os.getenv("GARDEN_NORMAL_LOG_INTERVAL", "10"))
        self.model_workers = max(
            1,
            int(os.getenv("GARDEN_MODEL_WORKERS", str(DEFAULT_MODEL_WORKERS)))
        )
        self.device_names = resolve_device_names()
        self.expected_streams = resolve_expected_streams()
        self.runners: List[GardenModelRunner] = []
        self.runner_locks: List[threading.Lock] = []
        self.last_normal_log_time: Dict[str, float] = {}
        self.last_ingress_log_time: Dict[str, float] = {}
        self.http_host = os.getenv("GARDEN_HTTP_HOST", DEFAULT_HTTP_HOST)
        self.http_port = int(os.getenv("GARDEN_HTTP_PORT", str(DEFAULT_HTTP_PORT)))
        self.latest_result_lock = threading.Lock()
        self.latest_result: Dict = self._empty_result("waiting")
        self.stream_results: Dict[str, Dict] = {}
        for stream_name in self.expected_streams:
            self.stream_results[stream_name] = self._empty_result(stream_name)
        self.http_server: Optional[ThreadingHTTPServer] = None
        self.http_thread: Optional[threading.Thread] = None
        self.result_queue: "queue.Queue[Tuple[bytes, bytes]]" = queue.Queue()
        self.worker_threads: List[threading.Thread] = []
        self.stream_slots_lock = threading.Lock()
        self.stream_slots: Dict[str, Tuple[bytes, Dict]] = {}
        self.stream_order: List[str] = []
        self.next_stream_index = 0
        self.robot_sessions_lock = threading.Lock()
        self.robot_sessions: Dict[str, RobotDogSession] = {}
        self.robot_event_seq = 0
        self.sse_heartbeat_sec = max(5, int(os.getenv("GARDEN_SSE_HEARTBEAT_SEC", str(DEFAULT_SSE_HEARTBEAT_SEC))))
        self.api_bearer_token = os.getenv("GARDEN_API_BEARER_TOKEN", "").strip()
        self.default_session_ttl_ms = max(60000, int(os.getenv("GARDEN_SESSION_TTL_MS", str(DEFAULT_SESSION_TTL_MS))))
        self.default_session_idle_timeout_ms = max(
            10000, int(os.getenv("GARDEN_SESSION_IDLE_TIMEOUT_MS", str(DEFAULT_SESSION_IDLE_TIMEOUT_MS)))
        )
        self.default_session_cleanup_interval_ms = max(
            5000, int(os.getenv("GARDEN_SESSION_CLEANUP_INTERVAL_MS", str(DEFAULT_SESSION_CLEANUP_INTERVAL_MS)))
        )
        self.default_replay_window_ms = max(
            10000, int(os.getenv("GARDEN_REPLAY_WINDOW_MS", str(DEFAULT_REPLAY_WINDOW_MS)))
        )
        self.default_replay_buffer_size = max(
            10, int(os.getenv("GARDEN_REPLAY_BUFFER_SIZE", str(DEFAULT_REPLAY_BUFFER_SIZE)))
        )
        self.cleanup_thread: Optional[threading.Thread] = None

    # --- lifecycle and shared state ---
    def stop(self, *_args) -> None:
        self.running = False
        with self.robot_sessions_lock:
            for session in self.robot_sessions.values():
                session.enqueue(None)
        if self.http_server is not None:
            self.http_server.shutdown()

    def _empty_result(self, stream_name: str) -> Dict:
        return {
            "stream_name": stream_name,
            "timestamp": "",
            "status": "BOOTING",
            "has_garbage": False,
            "confidence": None,
            "garbage_type": "",
            "scene_description": "Waiting for first frame...",
            "reason": "",
            "suggestion": "",
            "raw_text": "",
            "preview_data_url": "",
            "updated_at": "",
            "latency_ms": None
        }

    # --- logging and dashboard state ---
    def _normal_summary(self, meta: Dict, parsed: Optional[Dict], raw_text: str) -> str:
        if parsed:
            scene = str(parsed.get("scene_description", "")).strip()
            reason = str(parsed.get("reason", "")).strip()
            confidence = parsed.get("confidence")
            summary = scene or reason or json.dumps(parsed, ensure_ascii=False)
            if confidence is not None:
                return f"{summary} | confidence={confidence}"
            return summary
        return raw_text.strip().replace("\n", " ")

    def maybe_log_normal(self, meta: Dict, parsed: Optional[Dict], raw_text: str) -> None:
        stream_name = normalize_stream_name(meta)
        now = time.time()
        last_time = self.last_normal_log_time.get(stream_name, 0.0)
        if now - last_time < self.normal_log_interval:
            return
        self.last_normal_log_time[stream_name] = now
        summary = self._normal_summary(meta, parsed, raw_text)
        print(
            f"[GardenNormal] stream={stream_name} timestamp={meta.get('timestamp', '')} {summary}",
            flush=True
        )

    def maybe_log_ingress(self, meta: Dict) -> None:
        stream_name = normalize_stream_name(meta)
        now = time.time()
        last_time = self.last_ingress_log_time.get(stream_name, 0.0)
        if now - last_time < self.normal_log_interval:
            return
        self.last_ingress_log_time[stream_name] = now
        print(
            f"[GardenIngress] stream={stream_name} timestamp={meta.get('timestamp', '')} frame received",
            flush=True
        )

    def update_latest_result(
        self,
        meta: Dict,
        parsed: Optional[Dict],
        raw_text: str,
        alerted: bool,
        image: Image.Image,
        latency_ms: float
    ) -> None:
        preview_data_url = image_to_data_url(image)
        stream_name = normalize_stream_name(meta)
        payload = {
            "stream_name": stream_name,
            "timestamp": meta.get("timestamp", ""),
            "status": "ALERT" if alerted else str((parsed or {}).get("status", "NORMAL")).upper(),
            "has_garbage": bool(alerted or (parsed or {}).get("has_garbage", False)),
            "confidence": (parsed or {}).get("confidence"),
            "garbage_type": str((parsed or {}).get("garbage_type", "")).strip(),
            "scene_description": str((parsed or {}).get("scene_description", "")).strip(),
            "reason": str((parsed or {}).get("reason", "")).strip(),
            "suggestion": str((parsed or {}).get("suggestion", "")).strip(),
            "raw_text": raw_text.strip(),
            "preview_data_url": preview_data_url,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "latency_ms": round(latency_ms, 1)
        }
        with self.latest_result_lock:
            self.latest_result = payload
            self.stream_results[stream_name] = payload
        self.publish_robot_dog_result(meta, payload)

    def get_latest_result(self) -> Dict:
        with self.latest_result_lock:
            return dict(self.latest_result)

    def get_dashboard_payload(self) -> Dict:
        with self.latest_result_lock:
            ordered = sorted(
                self.stream_results.values(),
                key=lambda item: item.get("stream_name", "")
            )
            latest = dict(self.latest_result)
        return {
            "latest": latest,
            "streams": ordered,
            "worker_count": self.model_workers,
            "device_names": list(self.device_names),
            "expected_streams": list(self.expected_streams),
            "active_streams": sum(
                1 for item in ordered
                if item.get("updated_at")
            )
        }

    def _ensure_stream_placeholder(self, stream_name: str) -> None:
        with self.latest_result_lock:
            if stream_name not in self.stream_results:
                self.stream_results[stream_name] = self._empty_result(stream_name)

    # --- robot dog session management ---
    def _error_response(self, error_code: str, message: str, http_status: int) -> Dict[str, Any]:
        return {
            "http_status": http_status,
            "body": {
                "error_code": error_code,
                "message": message,
                "request_id": uuid.uuid4().hex,
                "timestamp_ms": now_ms()
            }
        }

    def authorize_request(self, handler: BaseHTTPRequestHandler) -> Tuple[bool, Optional[Dict[str, Any]]]:
        if not self.api_bearer_token:
            return True, None
        if handler.headers.get("Authorization", "") == f"Bearer {self.api_bearer_token}":
            return True, None
        return False, self._error_response("UNAUTHORIZED", "missing or invalid bearer token", 401)

    def _parse_session_request(self, request: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        client_name = str(request.get("client_name") or "robot_dog").strip() or "robot_dog"
        delivery = request.get("delivery") or {}
        subscriptions = request.get("subscriptions") or []

        camera_ids: List[str] = []
        task_names: List[str] = []
        if subscriptions:
            for item in subscriptions:
                camera_id = str(item.get("camera_id") or "").strip()
                task_name = str(item.get("task") or DEFAULT_TASK_NAMESPACE).strip()
                if camera_id:
                    camera_ids.append(camera_id)
                if task_name:
                    task_names.append(task_name)
        else:
            camera_ids = [str(item).strip() for item in (request.get("camera_ids") or []) if str(item).strip()]
            task_names = [str(request.get("task") or DEFAULT_TASK_NAMESPACE).strip()]

        ttl_ms = int(delivery.get("ttl_ms", request.get("ttl_ms", self.default_session_ttl_ms)))
        idle_timeout_ms = int(
            delivery.get("idle_timeout_ms", request.get("idle_timeout_ms", self.default_session_idle_timeout_ms))
        )
        heartbeat_interval_ms = int(
            delivery.get("heartbeat_interval_ms", request.get("heartbeat_interval_ms", self.sse_heartbeat_sec * 1000))
        )
        replay_buffer_size = int(
            delivery.get("replay_buffer_size", request.get("replay_buffer_size", self.default_replay_buffer_size))
        )
        replay_window_ms = int(
            delivery.get("replay_window_ms", request.get("replay_window_ms", self.default_replay_window_ms))
        )
        alert_only = bool(delivery.get("alert_only", request.get("alert_only", False)))

        if not camera_ids:
            return None, self._error_response("INVALID_ARGUMENT", "subscriptions must not be empty", 400)
        if ttl_ms <= 0 or idle_timeout_ms <= 0 or heartbeat_interval_ms <= 0:
            return None, self._error_response("INVALID_ARGUMENT", "ttl and interval values must be positive", 400)

        return {
            "client_name": client_name,
            "camera_ids": sorted(set(camera_ids)),
            "task_names": sorted(set(task_names or [DEFAULT_TASK_NAMESPACE])),
            "ttl_ms": ttl_ms,
            "idle_timeout_ms": idle_timeout_ms,
            "heartbeat_interval_ms": heartbeat_interval_ms,
            "replay_buffer_size": replay_buffer_size,
            "replay_window_ms": replay_window_ms,
            "alert_only": alert_only
        }, None

    def create_robot_dog_session(self, request: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        parsed, error = self._parse_session_request(request)
        if error is not None:
            return error["body"], error["http_status"]

        session = RobotDogSession(
            session_id=random_token("sess"),
            session_token=random_token("st"),
            client_name=parsed["client_name"],
            camera_ids=parsed["camera_ids"],
            task_names=parsed["task_names"],
            alert_only=parsed["alert_only"],
            ttl_ms=parsed["ttl_ms"],
            idle_timeout_ms=parsed["idle_timeout_ms"],
            heartbeat_interval_ms=parsed["heartbeat_interval_ms"],
            replay_window_ms=parsed["replay_window_ms"],
            replay_buffer_size=parsed["replay_buffer_size"]
        )
        with self.robot_sessions_lock:
            self.robot_sessions[session.session_id] = session

        payload = session.to_dict()
        payload.update({
            "session_token": session.session_token,
            "events_url": f"/api/robot-dog/sessions/{session.session_id}/events",
            "close_url": f"/api/robot-dog/sessions/{session.session_id}",
            "request_id": uuid.uuid4().hex,
            "timestamp_ms": now_ms()
        })
        return payload, 201

    def get_robot_dog_session_info(self, session_id: str, session_token: str) -> Tuple[Dict[str, Any], int]:
        session = self._get_robot_session(session_id)
        if session is None:
            error = self._error_response("SESSION_NOT_FOUND", "session does not exist", 404)
            return error["body"], error["http_status"]
        if session_token and session.session_token != session_token:
            error = self._error_response("FORBIDDEN", "invalid session token", 403)
            return error["body"], error["http_status"]
        payload = session.to_dict()
        payload.update({"request_id": uuid.uuid4().hex, "timestamp_ms": now_ms()})
        return payload, 200

    def close_robot_dog_session(self, session_id: str, session_token: str = "") -> Tuple[Dict[str, Any], int]:
        with self.robot_sessions_lock:
            session = self.robot_sessions.get(session_id)
            if session is None:
                error = self._error_response("SESSION_NOT_FOUND", "session does not exist", 404)
                return error["body"], error["http_status"]
            if session_token and session.session_token != session_token:
                error = self._error_response("FORBIDDEN", "invalid session token", 403)
                return error["body"], error["http_status"]
            session.mark_closed()
            session.enqueue(None)

        return {
            "session_id": session.session_id,
            "status": session.status,
            "closed_at_ms": session.closed_at_ms,
            "request_id": uuid.uuid4().hex,
            "timestamp_ms": now_ms()
        }, 200

    def _get_robot_session(self, session_id: str) -> Optional[RobotDogSession]:
        with self.robot_sessions_lock:
            return self.robot_sessions.get(session_id)

    def _remove_robot_session(self, session_id: str) -> None:
        with self.robot_sessions_lock:
            self.robot_sessions.pop(session_id, None)

    def _next_robot_event_id(self) -> str:
        with self.robot_sessions_lock:
            self.robot_event_seq += 1
            return str(self.robot_event_seq)

    def _build_robot_dog_payload(self, meta: Dict, result: Dict[str, Any], session: RobotDogSession) -> Dict[str, Any]:
        confidence = result.get("confidence")
        confidence_milli = None
        if confidence is not None:
            try:
                confidence_milli = int(round(float(confidence) * 1000))
            except (TypeError, ValueError):
                confidence_milli = None

        latency_ms = ""
        if result.get("latency_ms") is not None:
            try:
                latency_ms = str(int(round(float(result["latency_ms"]))))
            except (TypeError, ValueError):
                latency_ms = ""

        return {
            "session_id": session.session_id,
            "timestamp_ms": now_ms(),
            "source": "garden_service",
            "camera_id": normalize_stream_name(meta),
            "task": DEFAULT_TASK_NAMESPACE,
            "frame": {
                "timestamp_ms": int(meta.get("timestamp") or 0),
                "index": str(meta.get("frameIndex", "")) if meta.get("frameIndex") is not None else "",
                "pts": str(meta.get("pts", "")) if meta.get("pts") is not None else "",
                "video_path": str(meta.get("path", ""))
            },
            "result": {
                "status": str(result.get("status", "NORMAL")),
                "has_target": bool(result.get("has_garbage", False)),
                "target_type": str(result.get("garbage_type", "")),
                "confidence_milli": confidence_milli,
                "scene_description": str(result.get("scene_description", "")),
                "reason": str(result.get("reason", "")),
                "suggestion": str(result.get("suggestion", ""))
            },
            "metrics": {
                "latency_ms": latency_ms
            }
        }

    def publish_robot_dog_result(self, meta: Dict, result: Dict[str, Any]) -> None:
        with self.robot_sessions_lock:
            sessions = list(self.robot_sessions.values())

        for session in sessions:
            if session.status in ("CLOSED", "EXPIRED"):
                continue
            payload = self._build_robot_dog_payload(meta, result, session)
            if not session.accepts(payload):
                continue
            event = self._make_sse_event("inference.result", payload)
            with self.robot_sessions_lock:
                session.append_replay_event(event)
            session.enqueue(event)

    def stream_robot_dog_events(self, handler: BaseHTTPRequestHandler, session_id: str) -> None:
        ok, auth_error = self.authorize_request(handler)
        if not ok:
            handler._send_json(auth_error["http_status"], auth_error["body"])
            return

        session = self._get_robot_session(session_id)
        if session is None:
            error = self._error_response("SESSION_NOT_FOUND", "session does not exist", 404)
            handler._send_json(error["http_status"], error["body"])
            return

        query = parse_qs(urlparse(handler.path).query)
        session_token = handler.headers.get("X-Session-Token", "") or query.get("session_token", [""])[0]
        if session_token and session.session_token != session_token:
            error = self._error_response("FORBIDDEN", "invalid session token", 403)
            handler._send_json(error["http_status"], error["body"])
            return
        if session.status == "CLOSED":
            error = self._error_response("SESSION_CLOSED", "session already closed", 410)
            handler._send_json(error["http_status"], error["body"])
            return
        if session.is_expired(now_ms()):
            session.mark_expired()
            error = self._error_response("SESSION_EXPIRED", "session has expired", 410)
            handler._send_json(error["http_status"], error["body"])
            return

        last_event_id = handler.headers.get("Last-Event-ID", "").strip()
        replay_events: Optional[List[Dict[str, Any]]] = []
        if last_event_id:
            replay_events = session.replay_events_after(last_event_id)
            if replay_events is None:
                error = self._error_response(
                    "EVENT_REPLAY_UNAVAILABLE",
                    "requested replay range is no longer available",
                    409
                )
                handler._send_json(error["http_status"], error["body"])
                return

        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Connection", "keep-alive")
        handler.send_header("X-Accel-Buffering", "no")
        handler.end_headers()

        try:
            session.mark_active()
            hello = self._make_sse_event("session.ready", {
                "session_id": session.session_id,
                "status": session.status,
                "created_at_ms": session.created_at_ms,
                "expires_at_ms": session.expires_at_ms,
                "timestamp_ms": now_ms()
            }, store=False)
            self._write_sse_event(handler, hello)

            if last_event_id:
                resumed = self._make_sse_event("stream.resumed", {
                    "session_id": session.session_id,
                    "resume_from_event_id": last_event_id,
                    "replay_start_event_id": replay_events[0]["id"] if replay_events else session.last_event_id,
                    "timestamp_ms": now_ms()
                }, store=False)
                self._write_sse_event(handler, resumed)
                for event in replay_events or []:
                    self._write_sse_event(handler, event)
                    session.touch()

            while self.running and session.status == "ACTIVE":
                try:
                    event = session.queue.get(timeout=max(1, int(session.heartbeat_interval_ms / 1000)))
                except queue.Empty:
                    heartbeat = self._make_sse_event("heartbeat", {
                        "session_id": session.session_id,
                        "timestamp_ms": now_ms()
                    }, store=False)
                    self._write_sse_event(handler, heartbeat)
                    continue

                if event is None:
                    close_event_name = "session.expired" if session.status == "EXPIRED" else "session.closed"
                    closing = self._make_sse_event(close_event_name, {
                        "session_id": session.session_id,
                        "timestamp_ms": now_ms()
                    }, store=False)
                    self._write_sse_event(handler, closing)
                    break

                self._write_sse_event(handler, event)
                session.touch()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            error_event = self._make_sse_event("error", {
                "session_id": session.session_id,
                "error_code": "INTERNAL_ERROR",
                "message": str(exc),
                "timestamp_ms": now_ms()
            }, store=False)
            try:
                self._write_sse_event(handler, error_event)
            except Exception:
                pass
        finally:
            session.touch()

    def _make_sse_event(self, event_name: str, payload: Dict[str, Any], store: bool = True) -> Dict[str, Any]:
        return {
            "id": self._next_robot_event_id(),
            "event": event_name,
            "data": payload,
            "timestamp_ms": now_ms(),
            "store": store
        }

    def _write_sse_event(self, handler: BaseHTTPRequestHandler, event: Dict[str, Any]) -> None:
        body = json.dumps(event["data"], ensure_ascii=False, separators=(",", ":"))
        message = f"id: {event['id']}\nevent: {event['event']}\ndata: {body}\n\n"
        handler.wfile.write(message.encode("utf-8"))
        handler.wfile.flush()

    # --- frame scheduling and inference workers ---
    def cleanup_expired_sessions(self) -> None:
        while self.running:
            current_ms = now_ms()
            removable: List[str] = []
            with self.robot_sessions_lock:
                for session_id, session in list(self.robot_sessions.items()):
                    if session.status in ("CLOSED", "EXPIRED"):
                        if session.closed_at_ms and current_ms - session.closed_at_ms >= self.default_session_cleanup_interval_ms:
                            removable.append(session_id)
                        continue
                    if session.is_expired(current_ms):
                        session.mark_expired()
                        session.enqueue(None)
                for session_id in removable:
                    self.robot_sessions.pop(session_id, None)
            time.sleep(self.default_session_cleanup_interval_ms / 1000.0)

    def enqueue_latest_frame(self, identity: bytes, meta: Dict) -> None:
        stream_name = normalize_stream_name(meta)
        with self.stream_slots_lock:
            if stream_name not in self.stream_slots:
                self.stream_order.append(stream_name)
            self.stream_slots[stream_name] = (identity, meta)

    def pop_next_frame(self) -> Optional[Tuple[bytes, Dict]]:
        with self.stream_slots_lock:
            if not self.stream_order:
                return None

            total = len(self.stream_order)
            for _ in range(total):
                if not self.stream_order:
                    return None
                self.next_stream_index %= len(self.stream_order)
                stream_name = self.stream_order[self.next_stream_index]
                self.next_stream_index = (self.next_stream_index + 1) % len(self.stream_order)
                payload = self.stream_slots.pop(stream_name, None)
                if payload is not None:
                    return payload
            return None

    def inference_worker(self, worker_id: int) -> None:
        runner_index = worker_id % len(self.runners)
        runner = self.runners[runner_index]
        runner_lock = self.runner_locks[runner_index]
        log(f"starting inference worker-{worker_id} on {runner.device_name}")
        while self.running:
            try:
                payload = self.pop_next_frame()
                if payload is None:
                    time.sleep(0.05)
                    continue
                identity, meta = payload
            except Exception:
                continue

            try:
                started_at = time.time()
                with runner_lock:
                    raw_text, alerted, parsed, image = runner.infer(meta)
                latency_ms = (time.time() - started_at) * 1000.0
                self.update_latest_result(meta, parsed, raw_text, alerted, image, latency_ms)
                if alerted:
                    log(
                        f"alert finished for stream={normalize_stream_name(meta)} "
                        f"in {latency_ms / 1000.0:.3f}s on worker-{worker_id} ({runner.device_name})"
                    )
                else:
                    self.maybe_log_normal(meta, parsed, raw_text)
                self.result_queue.put((identity, b"OK"))
            except Exception as exc:
                log(f"request failed on worker-{worker_id} ({runner.device_name}): {exc}")
                traceback.print_exc()
                self.result_queue.put((identity, b"ERR"))

    # --- dashboard rendering ---
    def render_dashboard_html(self) -> str:
        return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Garden Vision Console</title>
  <style>
    :root {
      --bg: #f3efe7;
      --panel: rgba(255,255,255,0.72);
      --panel-strong: rgba(255,255,255,0.9);
      --ink: #1f2a2a;
      --muted: #5f6b6b;
      --line: rgba(31,42,42,0.10);
      --alert: #c74b32;
      --ok: #2e7d5b;
      --accent: #195c63;
      --card-bg: rgba(252, 250, 246, 0.88);
      --shadow: 0 24px 80px rgba(31,42,42,0.10);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", "Noto Sans SC", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(25,92,99,0.16), transparent 28%),
        radial-gradient(circle at top right, rgba(199,75,50,0.16), transparent 24%),
        linear-gradient(180deg, #f8f5ef 0%, var(--bg) 100%);
      min-height: 100vh;
    }
    .shell {
      width: min(1180px, calc(100vw - 32px));
      margin: 24px auto;
      display: grid;
      gap: 18px;
    }
    .hero, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(20px);
    }
    .hero {
      padding: 22px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
    }
    .title {
      font-size: clamp(28px, 4vw, 42px);
      line-height: 1;
      margin: 0 0 10px;
      letter-spacing: -0.04em;
    }
    .subtitle {
      margin: 0;
      color: var(--muted);
      font-size: 14px;
    }
    .badges {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .badge {
      border-radius: 999px;
      padding: 10px 14px;
      background: var(--panel-strong);
      border: 1px solid var(--line);
      font-size: 13px;
      color: var(--muted);
    }
    .status-alert { color: var(--alert); border-color: rgba(199,75,50,0.24); }
    .status-normal { color: var(--ok); border-color: rgba(46,125,91,0.22); }
    .grid {
      display: grid;
      gap: 18px;
    }
    .camera-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }
    .camera-card {
      border-radius: 22px;
      border: 1px solid var(--line);
      background: var(--card-bg);
      transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
      overflow: hidden;
    }
    .camera-card:hover {
      transform: translateY(-2px);
      box-shadow: 0 18px 40px rgba(31,42,42,0.08);
    }
    .camera-top {
      position: relative;
      aspect-ratio: 16 / 9;
      background: #1d2323;
      display: grid;
      place-items: center;
      overflow: hidden;
    }
    .camera-top img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }
    .camera-overlay {
      position: absolute;
      left: 12px;
      right: 12px;
      bottom: 12px;
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: center;
    }
    .pill {
      border-radius: 999px;
      padding: 8px 12px;
      font-size: 12px;
      background: rgba(255,255,255,0.88);
      border: 1px solid rgba(255,255,255,0.45);
      backdrop-filter: blur(12px);
    }
    .pill.alert {
      color: var(--alert);
    }
    .pill.normal {
      color: var(--ok);
    }
    .camera-body {
      padding: 14px;
      display: grid;
      gap: 10px;
    }
    .camera-name {
      font-size: 18px;
      font-weight: 700;
    }
    .camera-desc {
      font-size: 14px;
      color: var(--muted);
      min-height: 40px;
      line-height: 1.5;
    }
    .camera-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      color: var(--muted);
      font-size: 12px;
    }
    .camera-panels {
      display: grid;
      gap: 10px;
    }
    .camera-panel {
      padding: 12px 13px;
      border-radius: 16px;
      background: rgba(255,255,255,0.72);
      border: 1px solid var(--line);
    }
    .camera-panel .label {
      font-size: 11px;
      color: var(--muted);
      margin-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .camera-panel .value {
      font-size: 14px;
      line-height: 1.55;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .camera-panel.raw-panel {
      background: #172020;
      color: #eff7f4;
      border-color: rgba(255,255,255,0.08);
    }
    .camera-panel.raw-panel .label {
      color: rgba(239,247,244,0.65);
    }
    .camera-panel.raw-panel .value {
      font-family: "SFMono-Regular", "Consolas", monospace;
      font-size: 12px;
      max-height: 180px;
      overflow: auto;
    }
    .panel {
      padding: 18px;
    }
    .panel h2 {
      margin: 0 0 14px;
      font-size: 15px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .empty {
      color: var(--muted);
      font-size: 14px;
      letter-spacing: 0.02em;
    }
    @media (max-width: 860px) {
      .hero { flex-direction: column; align-items: flex-start; }
      .badges { justify-content: flex-start; }
      .camera-grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 560px) {
      .shell { width: min(100vw - 16px, 1180px); margin: 16px auto; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div>
        <h1 class="title">Garden Vision Console</h1>
        <p class="subtitle">四路摄像头的最新帧和大模型输出同时展示，方便直接横向对比每一路结果。</p>
      </div>
      <div class="badges">
        <div class="badge" id="workerBadge">Workers: booting</div>
        <div class="badge" id="deviceBadge">Devices: booting</div>
        <div class="badge" id="streamBadge">Streams: waiting</div>
        <div class="badge" id="timeBadge">Updated: waiting</div>
      </div>
    </section>

    <section class="panel">
      <h2>Live Multi-Camera Results</h2>
      <div class="camera-grid" id="cameraGrid"></div>
    </section>
  </main>

  <script>
    const els = {
      cameraGrid: document.getElementById("cameraGrid"),
      workerBadge: document.getElementById("workerBadge"),
      deviceBadge: document.getElementById("deviceBadge"),
      streamBadge: document.getElementById("streamBadge"),
      timeBadge: document.getElementById("timeBadge")
    };

    function fillText(element, value, fallback = "-") {
      element.textContent = value && String(value).trim() ? value : fallback;
    }

    function renderCameraGrid(streams) {
      els.cameraGrid.innerHTML = "";
      if (!streams.length) {
        els.cameraGrid.innerHTML = '<div class="empty">Waiting for camera frames...</div>';
        return;
      }

      streams.forEach((item) => {
        const card = document.createElement("article");
        card.className = "camera-card";

        const statusClass = (item.status || "").toUpperCase() === "ALERT" ? "alert" : "normal";
        const imageHtml = item.preview_data_url
          ? `<img src="${item.preview_data_url}" alt="${item.stream_name}" />`
          : `<div class="empty">Waiting for frame...</div>`;

        card.innerHTML = `
          <div class="camera-top">
            ${imageHtml}
            <div class="camera-overlay">
              <div class="pill ${statusClass}">${item.status || "BOOTING"}</div>
              <div class="pill">${item.latency_ms != null ? item.latency_ms + " ms" : "..."}</div>
            </div>
          </div>
          <div class="camera-body">
            <div class="camera-name">${item.stream_name || "-"}</div>
            <div class="camera-desc">${item.scene_description || "Waiting for model summary..."}</div>
            <div class="camera-meta">
              <span>Garbage: ${item.has_garbage ? "YES" : "NO"}</span>
              <span>Confidence: ${item.confidence != null ? item.confidence : "-"}</span>
              <span>Type: ${item.garbage_type || "-"}</span>
              <span>Updated: ${item.updated_at || "-"}</span>
            </div>
            <div class="camera-panels">
              <div class="camera-panel">
                <div class="label">Reason</div>
                <div class="value">${item.reason || "-"}</div>
              </div>
              <div class="camera-panel">
                <div class="label">Suggestion</div>
                <div class="value">${item.suggestion || "-"}</div>
              </div>
              <div class="camera-panel raw-panel">
                <div class="label">Raw Output</div>
                <div class="value">${item.raw_text || "Waiting for model output..."}</div>
              </div>
            </div>
          </div>
        `;
        els.cameraGrid.appendChild(card);
      });
    }

    async function refresh() {
      try {
        const res = await fetch("/api/streams", { cache: "no-store" });
        const payload = await res.json();
        const streams = payload.streams || [];
        const latest = payload.latest || {};

        els.workerBadge.textContent = `Workers: ${payload.worker_count || 0}`;
        els.deviceBadge.textContent = `Devices: ${(payload.device_names || []).join(", ") || "unknown"}`;
        els.streamBadge.textContent = `Streams: ${payload.active_streams || 0}/${streams.length || 0}`;
        els.timeBadge.textContent = `Updated: ${latest.updated_at || "waiting"}`;
        renderCameraGrid(streams);

      } catch (error) {
        els.cameraGrid.innerHTML = `<div class="empty">Dashboard fetch failed: ${error}</div>`;
      }
    }

    refresh();
    setInterval(refresh, 1500);
  </script>
</body>
</html>
"""

    # --- process startup and transport loops ---
    def start_http_server(self) -> None:
        GardenHttpHandler.service = self
        self.http_server = ThreadingHTTPServer(
            (self.http_host, self.http_port),
            GardenHttpHandler
        )
        self.http_thread = threading.Thread(
            target=self.http_server.serve_forever,
            daemon=True
        )
        self.http_thread.start()
        log(f"dashboard ready at http://{self.http_host}:{self.http_port}")

    def start_cleanup_worker(self) -> None:
        if self.cleanup_thread is not None:
            return
        self.cleanup_thread = threading.Thread(
            target=self.cleanup_expired_sessions,
            daemon=True
        )
        self.cleanup_thread.start()
        log("session cleanup worker started")

    def start_model_runners(self) -> None:
        if self.runners:
            return
        for device_name in self.device_names:
            self.runners.append(
                GardenModelRunner(
                    self.model_path,
                    self.prompt_template_path,
                    device_name
                )
            )
            self.runner_locks.append(threading.Lock())
        log(f"model runners ready on devices: {', '.join(self.device_names)}")

    def start_inference_workers(self) -> None:
        self.start_model_runners()
        for worker_id in range(self.model_workers):
            thread = threading.Thread(
                target=self.inference_worker,
                args=(worker_id,),
                daemon=True
            )
            thread.start()
            self.worker_threads.append(thread)
        log(
            f"inference worker pool ready with {self.model_workers} workers "
            f"across devices: {', '.join(self.device_names)}"
        )

    def _bind_router(self):
        context = zmq.Context()
        router = context.socket(zmq.ROUTER)
        try:
            router.bind(self.addr)
        except Exception:
            if self.addr.startswith("ipc://"):
                ipc_path = self.addr.replace("ipc://", "", 1)
                if os.path.exists(ipc_path):
                    os.unlink(ipc_path)
                router.bind(self.addr)
            else:
                raise
        return context, router

    def serve(self) -> None:
        context, router = self._bind_router()
        poller = zmq.Poller()
        poller.register(router, zmq.POLLIN)
        self.start_inference_workers()
        self.start_http_server()
        self.start_cleanup_worker()

        log(f"service ready on {self.addr}")
        log(f"prompt template: {self.prompt_template_path}")

        try:
            while self.running:
                events = dict(poller.poll(500))
                processed = 0
                while not self.result_queue.empty() and processed < 32:
                    try:
                        identity, result = self.result_queue.get_nowait()
                        router.send_multipart([identity, b"", result])
                        processed += 1
                    except queue.Empty:
                        break

                if router not in events:
                    continue

                frames = router.recv_multipart()
                if len(frames) < 2:
                    continue
                identity = frames[0]
                payload = frames[-1]

                try:
                    meta = json.loads(payload.decode("utf-8"))
                    stream_name = normalize_stream_name(meta)
                    self._ensure_stream_placeholder(stream_name)
                    self.maybe_log_ingress(meta)
                    self.enqueue_latest_frame(identity, meta)
                except Exception as exc:
                    log(f"request failed: {exc}")
                    traceback.print_exc()
                    router.send_multipart([identity, b"", b"ERR"])
        finally:
            poller.unregister(router)
            router.close(0)
            context.term()
            if self.http_server is not None:
                self.http_server.server_close()
            log("service stopped")


def main() -> None:
    """Create the service, register signal handlers, and start serving."""
    service = GardenService()
    signal.signal(signal.SIGINT, service.stop)
    signal.signal(signal.SIGTERM, service.stop)
    service.serve()


if __name__ == "__main__":
    main()
