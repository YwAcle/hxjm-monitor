"""智慧监控纯 Agent Flask 应用。"""
from __future__ import annotations

import base64
import binascii
import json
import re
from io import BytesIO
from time import monotonic
from uuid import uuid4

from flask import Flask, Response, request, stream_with_context
from PIL import Image, UnidentifiedImageError
from sqlalchemy import text
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix

from llm_agent_service.config import DbConfig, ServiceConfig
from llm_agent_service.service.reid_service import ReidService
from llm_agent_service.agent.executor import AgentExecutor
from llm_agent_service.observability import emit_event
from llm_agent_service.service.agent_service import AgentService
from llm_agent_service.service.gallery_search import GallerySearchService
from llm_agent_service.service.image_assets import SessionImageAssets
from llm_agent_service.service.clipreid_client import ClipReIDClient
from llm_agent_service.service.text_reid_client import TextReIDClient
from llm_agent_service.tools.default_tools import build_default_registry


SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
IMAGE_MEDIA_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


class RequestValidationError(ValueError):
    """可直接转换为客户端 4xx 响应的输入错误。"""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _normalize_image(
    image_base64: str,
    *,
    max_bytes: int,
    max_pixels: int,
    max_side: int,
) -> tuple[str, int, tuple[int, int]]:
    """校验 Base64 图片并转换为标准 Data URL。"""

    encoded = image_base64.strip()
    if encoded.startswith("data:"):
        if "," not in encoded:
            raise RequestValidationError("INVALID_IMAGE", "图片 Data URL 格式无效")
        encoded = encoded.split(",", 1)[1]
    encoded = "".join(encoded.split())
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RequestValidationError("INVALID_IMAGE", "图片 Base64 编码无效") from exc
    if not image_bytes:
        raise RequestValidationError("INVALID_IMAGE", "图片内容为空")
    if len(image_bytes) > max_bytes:
        raise RequestValidationError(
            "IMAGE_TOO_LARGE",
            f"图片大小不能超过 {max_bytes // (1024 * 1024)} MB",
            413,
        )

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image_format = str(image.format or "").upper()
            width, height = image.size
            if image_format not in IMAGE_MEDIA_TYPES:
                raise RequestValidationError(
                    "UNSUPPORTED_IMAGE_FORMAT",
                    "仅支持 JPEG、PNG 和 WebP 图片",
                )
            if max(width, height) > max_side or width * height > max_pixels:
                raise RequestValidationError(
                    "IMAGE_DIMENSIONS_TOO_LARGE",
                    f"图片最长边不能超过 {max_side}，总像素不能超过 {max_pixels}",
                    413,
                )
            image.verify()
    except RequestValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise RequestValidationError("INVALID_IMAGE", "无法解析图片内容") from exc

    media_type = IMAGE_MEDIA_TYPES[image_format]
    normalized = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{media_type};base64,{normalized}", len(image_bytes), (width, height)

# 尝试导入 flask-cors，如果没有安装则使用手动 CORS
try:
    from flask_cors import CORS
    HAS_FLASK_CORS = True
except ImportError:
    HAS_FLASK_CORS = False
    print("[警告] flask-cors 未安装，将使用手动 CORS 支持")


def add_cors_headers(response: Response) -> Response:
    """手动添加 CORS 响应头"""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Session-ID, X-Trace-ID'
    response.headers['Access-Control-Expose-Headers'] = 'X-Trace-ID'
    response.headers['Access-Control-Max-Age'] = '3600'
    return response


def create_app(*, engine, db_cfg: DbConfig, svc_cfg: ServiceConfig, llm) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = svc_cfg.max_request_bytes
    
    # 配置 CORS
    if HAS_FLASK_CORS:
        CORS(
            app,
            resources={r"/*": {"origins": "*"}},
            allow_headers=["Content-Type", "Authorization", "X-Session-ID", "X-Trace-ID"],
            expose_headers=["X-Trace-ID"],
        )
        print("[信息] 使用 flask-cors 支持跨域请求")
    else:
        # 手动添加 CORS 支持
        @app.after_request
        def after_request(response):
            return add_cors_headers(response)
        
        @app.before_request
        def handle_preflight():
            if request.method == "OPTIONS":
                response = Response(status=200)
                response.headers.add("Access-Control-Allow-Origin", "*")
                response.headers.add('Access-Control-Allow-Headers', "Content-Type, Authorization, X-Requested-With, X-Session-ID, X-Trace-ID")
                response.headers.add('Access-Control-Allow-Methods', "GET, POST, PUT, DELETE, OPTIONS")
                response.headers.add('Access-Control-Expose-Headers', "X-Trace-ID")
                response.headers.add('Access-Control-Max-Age', "3600")
                return response
        print("[信息] 使用手动 CORS 支持跨域请求")
    
    # 配置代理支持
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,
        x_proto=1,
        x_host=1,
        x_port=1,
        x_prefix=1,
    )
    
    # 自定义 JSON 响应，确保中文可读
    def json_response(data, status_code=200, trace_id: str | None = None):
        """返回不转义 Unicode 的 JSON 响应"""
        response_data = dict(data) if isinstance(data, dict) else data
        if trace_id and isinstance(response_data, dict):
            response_data.setdefault("trace_id", trace_id)
        response = Response(
            json.dumps(response_data, ensure_ascii=False, indent=2),
            status=status_code,
            mimetype='application/json; charset=utf-8'
        )
        if trace_id:
            response.headers["X-Trace-ID"] = trace_id
        return response

    def sse_event(event: str, data: dict) -> str:
        """编码单条 SSE 事件；data 统一为 JSON，避免正文换行破坏事件边界。"""
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return f"event: {event}\ndata: {payload}\n\n"

    @app.errorhandler(RequestEntityTooLarge)
    def request_too_large(_error):
        """请求体超限时返回可追踪的 413 响应。"""

        raw_trace_id = str(request.headers.get("X-Trace-ID", "")).strip()
        trace_id = raw_trace_id if TRACE_ID_PATTERN.fullmatch(raw_trace_id) else uuid4().hex
        emit_event(
            "request_rejected",
            trace_id=trace_id,
            path=request.path,
            error_code="REQUEST_TOO_LARGE",
            max_request_bytes=svc_cfg.max_request_bytes,
        )
        return json_response(
            {
                "error": "请求体过大",
                "error_code": "REQUEST_TOO_LARGE",
            },
            413,
            trace_id,
        )
    
    # 初始化 ReID 服务
    reid_service = ReidService(
        engine=engine,
        schema=db_cfg.schema,
        llm=llm,
        tz=svc_cfg.tz,
        playback_base_url=svc_cfg.playback_base_url,
        memory_max_sessions=svc_cfg.memory_max_sessions,
        memory_max_messages=svc_cfg.memory_max_messages,
    )
    gallery_search = GallerySearchService(
        engine=engine, schema=db_cfg.schema,
        feature_client=ClipReIDClient(
            svc_cfg.reid_feature_base_url,
            svc_cfg.reid_timeout_s,
            svc_cfg.reid_feature_space_id,
        ),
        text_feature_client=TextReIDClient(
            svc_cfg.reid_feature_base_url,
            svc_cfg.reid_timeout_s,
            svc_cfg.reid_text_feature_space_id,
            svc_cfg.reid_text_contract_id,
            svc_cfg.reid_text_max_chars,
        ),
        text_max_chars=svc_cfg.reid_text_max_chars,
    )
    tool_registry = build_default_registry(reid_service, gallery_search)
    image_assets = SessionImageAssets(
        ttl_s=svc_cfg.image_asset_ttl_s,
        max_per_session=svc_cfg.image_asset_max_per_session,
        max_bytes_per_session=svc_cfg.image_asset_max_bytes_per_session,
        max_total_bytes=svc_cfg.image_asset_max_total_bytes,
    )
    agent_service = AgentService(
        gallery_search=gallery_search,
        executor=AgentExecutor(
            llm=llm,
            registry=tool_registry,
            max_steps=3,
            request_timeout_s=svc_cfg.agent_request_timeout_s,
            max_tool_result_chars=12000,
            answer_max_new_tokens=svc_cfg.agent_answer_max_new_tokens,
            memory=reid_service.memory,
            image_assets=image_assets,
        ),
    )
    print("[App] Agent 模式：agent")

    @app.get("/tools")
    def list_tools():
        """列出已注册工具及参数 Schema，不返回处理函数。"""
        return json_response({"tools": tool_registry.describe()})

    @app.post("/chat")
    def chat():
        """接收文本或单张图片，并统一交给纯 Agent。"""

        started = monotonic()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            payload = {}
        prompt = payload.get("prompt")
        image_base64 = payload.get("image")
        raw_session_id = (
            payload.get("session_id")
            or request.form.get("session_id")
            or request.args.get("session_id")
            or request.headers.get("X-Session-ID")
        )
        raw_trace_id = (
            payload.get("trace_id")
            or request.form.get("trace_id")
            or request.args.get("trace_id")
            or request.headers.get("X-Trace-ID")
        )
        trace_id = str(raw_trace_id).strip() if raw_trace_id is not None else uuid4().hex
        if not TRACE_ID_PATTERN.fullmatch(trace_id):
            fallback_trace_id = uuid4().hex
            emit_event(
                "request_rejected",
                trace_id=fallback_trace_id,
                path=request.path,
                error_code="INVALID_TRACE_ID",
            )
            return json_response(
                {
                    "error": "trace_id 无效；长度须为 1-128，且只能包含字母、数字、'.'、'_'、':' 或 '-'",
                    "error_code": "INVALID_TRACE_ID",
                },
                400,
                fallback_trace_id,
            )

        session_id_source = "client" if raw_session_id is not None else "generated"
        session_id = (
            str(raw_session_id).strip() if raw_session_id is not None else uuid4().hex
        )
        if not SESSION_ID_PATTERN.fullmatch(session_id):
            emit_event(
                "request_rejected",
                trace_id=trace_id,
                error_code="INVALID_SESSION_ID",
            )
            return json_response(
                {
                    "error": (
                        "session_id 无效；长度须为 1-128，且只能包含字母、数字、'.'、'_'、':' 或 '-'"
                    ),
                    "error_code": "INVALID_SESSION_ID",
                },
                400,
                trace_id,
            )

        if prompt is None:
            prompt = request.form.get("prompt") or request.args.get("prompt")

        if not image_base64:
            file = request.files.get("file")
            if file:
                image_bytes = file.read()
                image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            else:
                image_base64 = request.form.get("image")
                if not image_base64:
                    image_base64 = request.form.get("image_base64") or request.form.get("base64")

        has_image = image_base64 is not None and str(image_base64).strip() != ""
        prompt = str(prompt).strip() if prompt is not None else ""
        # 允许纯图片请求，不再人为注入默认提示词，由 Agent 结合会话自行判断。
        if not prompt and not has_image:
            emit_event(
                "request_rejected",
                trace_id=trace_id,
                session_id=session_id,
                error_code="MISSING_PROMPT",
            )
            return json_response(
                {"error": "缺少 prompt", "error_code": "MISSING_PROMPT"},
                400,
                trace_id,
            )
        if len(prompt) > svc_cfg.max_prompt_chars:
            emit_event(
                "request_rejected",
                trace_id=trace_id,
                session_id=session_id,
                error_code="PROMPT_TOO_LONG",
                prompt_chars=len(prompt),
            )
            return json_response(
                {
                    "error": f"prompt 长度不能超过 {svc_cfg.max_prompt_chars} 个字符",
                    "error_code": "PROMPT_TOO_LONG",
                },
                400,
                trace_id,
            )

        image_bytes = 0
        image_size: tuple[int, int] | None = None
        if has_image:
            try:
                image_base64, image_bytes, image_size = _normalize_image(
                    str(image_base64),
                    max_bytes=svc_cfg.max_image_bytes,
                    max_pixels=svc_cfg.max_image_pixels,
                    max_side=svc_cfg.max_image_side,
                )
            except RequestValidationError as exc:
                emit_event(
                    "request_rejected",
                    trace_id=trace_id,
                    session_id=session_id,
                    error_code=exc.code,
                )
                return json_response(
                    {"error": exc.message, "error_code": exc.code},
                    exc.status_code,
                    trace_id,
                )

        emit_event(
            "request_start",
            trace_id=trace_id,
            session_id=session_id,
            session_id_source=session_id_source,
            method=request.method,
            path=request.path,
            content_type=request.mimetype,
            content_length=request.content_length,
            prompt_chars=len(prompt),
            prompt=prompt,
            has_image=has_image,
            image_bytes=image_bytes if has_image else None,
            image_width=image_size[0] if image_size else None,
            image_height=image_size[1] if image_size else None,
        )

        try:
            result = agent_service.process(
                prompt,
                image_base64=image_base64 if has_image else None,
                session_id=session_id,
                trace_id=trace_id,
            )
            result["session_id"] = session_id
            emit_event(
                "request_end",
                trace_id=trace_id,
                session_id=session_id,
                status="success",
                response_type=result.get("type", "unknown"),
                response_chars=len(str(result.get("text", ""))),
                response_text=str(result.get("text", "")),
                finish_reason=(result.get("agent") or {}).get("finish_reason"),
                elapsed_ms=max(0, int((monotonic() - started) * 1000)),
            )
            return json_response(result, trace_id=trace_id)
        except Exception as exc:
            emit_event(
                "request_end",
                trace_id=trace_id,
                session_id=session_id,
                status="error",
                error_code="INTERNAL_ERROR",
                exception_type=type(exc).__name__,
                elapsed_ms=max(0, int((monotonic() - started) * 1000)),
            )
            return json_response(
                {"error": "处理请求失败", "error_code": "INTERNAL_ERROR"},
                500,
                trace_id,
            )

    @app.post("/chat/stream")
    def chat_stream():
        """接收 JSON 或文件表单，完成工具决策后实时输出最终正文。"""
        started = monotonic()
        if request.mimetype == "multipart/form-data":
            payload = request.form
        else:
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                return json_response(
                    {"error": "请求体必须是 JSON 对象或 multipart/form-data", "error_code": "INVALID_JSON"},
                    400,
                )

        raw_trace_id = payload.get("trace_id") or request.headers.get("X-Trace-ID")
        trace_id = str(raw_trace_id).strip() if raw_trace_id is not None else uuid4().hex
        if not TRACE_ID_PATTERN.fullmatch(trace_id):
            fallback_trace_id = uuid4().hex
            emit_event(
                "request_rejected",
                trace_id=fallback_trace_id,
                path=request.path,
                error_code="INVALID_TRACE_ID",
            )
            return json_response(
                {
                    "error": "trace_id 无效；长度须为 1-128，且只能包含字母、数字、'.'、'_'、':' 或 '-'",
                    "error_code": "INVALID_TRACE_ID",
                },
                400,
                fallback_trace_id,
            )

        raw_session_id = payload.get("session_id") or request.headers.get("X-Session-ID")
        session_id_source = "client" if raw_session_id is not None else "generated"
        session_id = str(raw_session_id).strip() if raw_session_id is not None else uuid4().hex
        if not SESSION_ID_PATTERN.fullmatch(session_id):
            emit_event(
                "request_rejected",
                trace_id=trace_id,
                error_code="INVALID_SESSION_ID",
            )
            return json_response(
                {
                    "error": "session_id 无效；长度须为 1-128，且只能包含字母、数字、'.'、'_'、':' 或 '-'",
                    "error_code": "INVALID_SESSION_ID",
                },
                400,
                trace_id,
            )

        prompt = str(payload.get("prompt") or "").strip()
        image_base64 = payload.get("image")
        if request.mimetype == "multipart/form-data":
            image_base64 = image_base64 or payload.get("image_base64") or payload.get("base64")
        files = request.files.getlist("file")
        has_encoded_image = image_base64 is not None and str(image_base64).strip() != ""
        if len(files) > 1 or (files and has_encoded_image):
            emit_event(
                "request_rejected", trace_id=trace_id, session_id=session_id,
                error_code="MULTIPLE_IMAGES",
            )
            return json_response(
                {"error": "每次请求仅支持一张图片，请选择 file 或 Base64 图片", "error_code": "MULTIPLE_IMAGES"},
                400, trace_id,
            )
        has_image = bool(files) or has_encoded_image
        if not prompt and not has_image:
            return json_response(
                {"error": "缺少 prompt", "error_code": "MISSING_PROMPT"},
                400,
                trace_id,
            )
        if len(prompt) > svc_cfg.max_prompt_chars:
            return json_response(
                {
                    "error": f"prompt 长度不能超过 {svc_cfg.max_prompt_chars} 个字符",
                    "error_code": "PROMPT_TOO_LONG",
                },
                400,
                trace_id,
            )

        image_bytes = 0
        image_size: tuple[int, int] | None = None
        if has_image:
            try:
                if files:
                    image_base64 = base64.b64encode(
                        files[0].read(svc_cfg.max_image_bytes + 1)
                    ).decode("ascii")
                image_base64, image_bytes, image_size = _normalize_image(
                    str(image_base64),
                    max_bytes=svc_cfg.max_image_bytes,
                    max_pixels=svc_cfg.max_image_pixels,
                    max_side=svc_cfg.max_image_side,
                )
            except RequestValidationError as exc:
                emit_event(
                    "request_rejected",
                    trace_id=trace_id,
                    session_id=session_id,
                    error_code=exc.code,
                )
                return json_response(
                    {"error": exc.message, "error_code": exc.code},
                    exc.status_code,
                    trace_id,
                )

        emit_event(
            "request_start",
            trace_id=trace_id,
            session_id=session_id,
            session_id_source=session_id_source,
            method=request.method,
            path=request.path,
            content_type=request.mimetype,
            content_length=request.content_length,
            prompt_chars=len(prompt),
            prompt=prompt,
            has_image=has_image,
            image_bytes=image_bytes if has_image else None,
            image_width=image_size[0] if image_size else None,
            image_height=image_size[1] if image_size else None,
        )

        @stream_with_context
        def generate():
            response_chars = 0
            response_parts: list[str] = []
            completed = False
            stream = agent_service.stream(
                prompt,
                image_base64=image_base64 if has_image else None,
                session_id=session_id,
                trace_id=trace_id,
            )
            try:
                for item in stream:
                    event = str(item.get("event", "error"))
                    data = item.get("data")
                    if not isinstance(data, dict):
                        data = {}
                    if event == "delta":
                        text = str(data.get("text", ""))
                        response_parts.append(text)
                        response_chars += len(text)
                    if event == "done":
                        completed = True
                        emit_event(
                            "request_end",
                            trace_id=trace_id,
                            session_id=session_id,
                            status="success",
                            response_type="agent",
                            response_chars=response_chars,
                            response_text="".join(response_parts),
                            finish_reason=data.get("finish_reason"),
                            elapsed_ms=max(0, int((monotonic() - started) * 1000)),
                        )
                    yield sse_event(event, data)
            except GeneratorExit:
                if not completed:
                    emit_event(
                        "request_end", trace_id=trace_id, session_id=session_id,
                        status="error", response_chars=response_chars,
                        response_text="".join(response_parts), error_code="STREAM_INTERRUPTED",
                        elapsed_ms=max(0, int((monotonic() - started) * 1000)),
                    )
                raise
            except Exception as exc:
                emit_event(
                    "request_end",
                    trace_id=trace_id,
                    session_id=session_id,
                    status="error",
                    response_chars=response_chars,
                    response_text="".join(response_parts),
                    error_code="INTERNAL_ERROR",
                    exception_type=type(exc).__name__,
                    elapsed_ms=max(0, int((monotonic() - started) * 1000)),
                )
                yield sse_event(
                    "error",
                    {"error": "处理请求失败", "error_code": "INTERNAL_ERROR"},
                )
            finally:
                close = getattr(stream, "close", None)
                if callable(close):
                    close()

        response = Response(generate(), mimetype="text/event-stream")
        response.headers["Cache-Control"] = "no-cache"
        response.headers["X-Accel-Buffering"] = "no"
        response.headers["X-Trace-ID"] = trace_id
        return response

    @app.post("/reload_persons")
    def reload_persons():
        """重新加载熟人列表"""
        try:
            reid_service.reload_known_persons()
            return json_response({
                "status": "ok",
                "count": len(reid_service.known_persons)
            })
        except Exception as e:
            return json_response({"error": str(e)}, 500)

    @app.delete("/sessions/<session_id>/memory")
    def clear_session_memory(session_id: str):
        """清除指定会话在当前进程中的聊天历史和会话图片。"""

        if not SESSION_ID_PATTERN.fullmatch(session_id):
            return json_response({"error": "session_id 无效"}, 400)
        selection_cleared = agent_service.selections.clear(session_id) if agent_service.selections else False
        asset_cleared = image_assets.clear(session_id)
        cleared = reid_service.clear_memory(session_id) or selection_cleared or asset_cleared
        return json_response(
            {
                "status": "ok",
                "session_id": session_id,
                "cleared": cleared,
            }
        )
    
    @app.route("/persons", methods=["GET", "OPTIONS"])
    def list_persons():
        """列出所有熟人
        返回格式:
        {
            "count": 人数,
            "persons": [
                {
                    "name": "姓名",
                    "person_ids": ["uuid1", "uuid2", ...]
                },
                ...
            ]
        }
        """
        if request.method == "OPTIONS":
            response = Response(status=200)
            response.headers.add("Access-Control-Allow-Origin", "*")
            response.headers.add('Access-Control-Allow-Headers', "Content-Type, Authorization, X-Requested-With")
            response.headers.add('Access-Control-Allow-Methods', "GET, POST, PUT, DELETE, OPTIONS")
            return response
        
        try:
            persons_list = []
            for name, person_ids in reid_service.known_persons.items():
                persons_list.append({
                    "name": name,
                    "person_ids": person_ids
                })
            
            return json_response({
                "count": len(reid_service.known_persons),
                "persons": persons_list
            })
        except Exception as e:
            return json_response({"error": str(e)}, 500)
    
    @app.get("/health")
    def health():
        """检查 Flask 进程是否存活。"""
        return json_response({"status": "ok"})

    @app.get("/ready")
    def ready():
        """检查 PostgreSQL 和已配置的 LLM 后端是否就绪。"""

        checks = {"database": "ok", "llm": "ok"}
        errors: dict[str, str] = {}
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as exc:
            checks["database"] = "error"
            errors["database"] = str(exc)

        llm_status = None
        try:
            check_llm = getattr(llm, "check_health", None)
            llm_status = check_llm() if callable(check_llm) else None
        except Exception as exc:
            checks["llm"] = "error"
            errors["llm"] = str(exc)

        result = {
            "status": "ok" if not errors else "not_ready",
            **checks,
        }
        if isinstance(llm_status, dict):
            result["llm_model"] = llm_status.get("model")
            if llm_status.get("healthcheck") == "skipped":
                result["llm_healthcheck"] = "skipped"
        if errors:
            result["errors"] = errors
        return json_response(result, 200 if not errors else 503)

    return app
