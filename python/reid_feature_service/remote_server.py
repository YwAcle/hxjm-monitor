"""Remote ReID HTTP contract (JSON + JPEG data URLs) for cross-server callers.

Implements ReID-接口规范.md as a thin, stateless adapter over the model loaders in
``server.py``. The local ``/v1/reid/*`` interface is not modified, so existing
callers keep working; only the ``/api/analysis/reid/*`` endpoints below are new.
"""

import asyncio
import base64
import binascii
import logging
import os
import sys
import time
import uuid
import warnings
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import Literal

import numpy as np
from fastapi import FastAPI, HTTPException
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

try:  # package import (tests) or direct script execution
    from . import server as core
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import server as core

LOG = logging.getLogger(__name__)

IMAGE_PREFIX = "data:image/jpeg;base64,"
MAX_IMAGE_CHARS = 3_000_000
MAX_REQUEST_BYTES = 32 * 1024 * 1024
MAX_PIXELS = 16_000_000
MAX_TARGETS = 8
MAX_TEXT_CHARS = 200
MIN_CROP_SIDE = 8
MIN_CROP_AREA = 256
INFERENCE_TIMEOUT = 60.0
EXIF_ORIENTATION_TAG = 0x0112


def fail(status, code, message):
    raise HTTPException(status, detail=f"{code}：{message}")


class Crop(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image: str
    box: list[float] = Field(min_length=4, max_length=4)


class Target(Crop):
    id: str = Field(min_length=1, max_length=32)


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()), max_length=96)
    query: Crop
    targets: list[Target] = Field(min_length=1, max_length=MAX_TARGETS)


class TextQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    language: Literal["auto", "zh", "en", "unknown"] = "auto"


class CompareTextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()), max_length=96)
    query: TextQuery
    targets: list[Target] = Field(min_length=1, max_length=MAX_TARGETS)


def decode_data_url(data_url):
    """Decode a JPEG data URL without applying EXIF rotation."""
    if not data_url.startswith("data:"):
        fail(422, "INVALID_IMAGE", "图片必须是 data:image/jpeg;base64,<Base64> 字符串")
    if len(data_url) > MAX_IMAGE_CHARS:
        fail(413, "IMAGE_TOO_LARGE", f"单张图片字符串超过 {MAX_IMAGE_CHARS} 字符上限")
    if not data_url.startswith(IMAGE_PREFIX):
        fail(415, "UNSUPPORTED_IMAGE_FORMAT", "仅支持 JPEG data URL")
    try:
        payload = base64.b64decode(data_url[len(IMAGE_PREFIX):], validate=True)
    except (binascii.Error, ValueError):
        fail(422, "INVALID_IMAGE", "图片 Base64 解码失败")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(payload)) as image:
                if image.format != "JPEG":
                    fail(415, "UNSUPPORTED_IMAGE_FORMAT", "仅支持 JPEG 图片")
                if image.width * image.height > MAX_PIXELS:
                    fail(413, "IMAGE_TOO_LARGE", "图片解码后超过 1600 万像素上限")
                if getattr(image, "n_frames", 1) != 1:
                    fail(422, "INVALID_IMAGE", "不支持动画图片")
                if image.getexif().get(EXIF_ORIENTATION_TAG, 1) != 1:
                    fail(422, "EXIF_ROTATION", "图片带 EXIF 旋转标记，请先按调用方坐标基准转正后再提交")
                image.load()
                return image.convert("RGB")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        fail(413, "IMAGE_TOO_LARGE", "图片解码像素超过上限")
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        fail(422, "INVALID_IMAGE", "图片无法解码")


def pixel_box(box, width, height):
    """Normalized box -> exclusive-pixel box, exactly as the contract defines."""
    left, top, right, bottom = box
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        fail(422, "INVALID_BOX",
             "box 必须是归一化坐标 [left, top, right, bottom]，满足 0 ≤ left < right ≤ 1、0 ≤ top < bottom ≤ 1")
    x1, y1 = round(left * width), round(top * height)
    x2, y2 = round(right * width), round(bottom * height)
    if x2 - x1 < MIN_CROP_SIDE or y2 - y1 < MIN_CROP_SIDE or (x2 - x1) * (y2 - y1) < MIN_CROP_AREA:
        fail(422, "BOX_TOO_SMALL",
             f"裁剪区域过小：宽、高均须 ≥ {MIN_CROP_SIDE} 像素且面积 ≥ {MIN_CROP_AREA} 像素")
    return x1, y1, x2, y2


def crop_payload(payload):
    with decode_data_url(payload.image) as image:
        return image.crop(pixel_box(payload.box, image.width, image.height))


def unit(vector):
    return core.normalize_features(np.asarray([vector], dtype=np.float32))[0]


def cosine(left, right):
    return round(float(np.clip(np.dot(left, right), -1.0, 1.0)), 6)


def check_target_ids(targets):
    ids = [target.id for target in targets]
    if len(set(ids)) != len(ids):
        fail(422, "DUPLICATE_TARGET_ID", "targets[].id 必须在本次请求内唯一")


def file_sha256(path):
    try:
        return core.sha256_file(Path(path))
    except OSError:
        return None


def main_weight_file(directory):
    """The file the text model actually loads: safetensors if present, else .bin."""
    files = sorted(path for path in Path(directory).iterdir()
                   if path.is_file() and path.suffix in {".bin", ".safetensors"})
    if not files:
        raise FileNotFoundError(f"no weight file in {directory}")
    safetensors = [path for path in files if path.suffix == ".safetensors"]
    return max(safetensors or files, key=lambda path: path.stat().st_size)


def text_metadata(text):
    directory = getattr(text, "model_path", None)
    model = Path(directory).name if directory else getattr(text, "model_name", "chinese-clip")
    try:
        weights = main_weight_file(directory)
    except (OSError, TypeError):
        return model, None
    LOG.info("text model_sha256 is taken from %s", weights.name)
    return model, file_sha256(weights)


class BodyLimit:
    """Reject request bodies over 32 MiB before FastAPI parses them."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        declared = -1
        try:
            declared = int(dict(scope["headers"]).get(b"content-length", b"0"))
        except ValueError:
            pass
        if declared < 0 or declared > MAX_REQUEST_BYTES:
            return await JSONResponse(
                {"detail": "REQUEST_TOO_LARGE：请求体超过 32 MiB 上限"},
                413)(scope, receive, send)
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > MAX_REQUEST_BYTES:
                fail(413, "REQUEST_TOO_LARGE", "请求体超过 32 MiB 上限")
            return message

        await self.app(scope, bounded_receive, send)


def create_app(settings=None, extractor_factory=core.Extractor, text_extractor_factory=core.TextExtractor):
    settings = settings or core.Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="reid-remote")
        app.state.executor = executor
        app.state.ready = False
        app.state.text_ready = False
        app.state.text_error = None
        app.state.image_model = None
        app.state.image_sha = None
        app.state.text_model = None
        app.state.text_sha = None
        try:
            loop = asyncio.get_running_loop()
            app.state.extractor = await loop.run_in_executor(executor, extractor_factory, settings)
            app.state.image_model = Path(settings.weights).name
            app.state.image_sha = file_sha256(settings.weights)
            app.state.ready = True
            try:
                # A broken text model must not take down the image endpoint.
                text = await loop.run_in_executor(
                    executor, text_extractor_factory, settings, app.state.extractor.device)
            except Exception:
                LOG.exception("Chinese-CLIP text model initialization failed; compare-text will be unavailable")
                app.state.text_error = "initialization_failed"
            else:
                app.state.text_extractor = text
                app.state.text_ready = True
                app.state.text_model, app.state.text_sha = text_metadata(text)
            yield
        finally:
            app.state.ready = False
            app.state.text_ready = False
            executor.shutdown(wait=True, cancel_futures=True)

    app = FastAPI(title="ReID remote contract service", version="1.0.0", lifespan=lifespan)
    app.state.ready = False
    app.state.text_ready = False
    app.state.text_error = None
    app.state.extractor = None
    app.state.text_extractor = None
    app.add_middleware(BodyLimit)

    busy = asyncio.Lock()

    def release_when_done(done):
        if not done.cancelled():
            done.exception()
        busy.release()

    async def run(job):
        """One in-flight inference at a time; excess callers get an immediate 429."""
        if busy.locked():
            fail(429, "SERVICE_BUSY", "已有推理任务在运行，请稍后重试")
        await busy.acquire()
        future = asyncio.get_running_loop().run_in_executor(app.state.executor, job)
        try:
            result = await asyncio.wait_for(asyncio.shield(future), INFERENCE_TIMEOUT)
        except asyncio.TimeoutError:
            # shortcut: a thread cannot be interrupted; keep the slot busy until the job ends
            future.add_done_callback(release_when_done)
            fail(500, "INFERENCE_TIMEOUT", "推理超过 60 秒上限，本次请求失败")
        except asyncio.CancelledError:
            future.add_done_callback(release_when_done)
            raise
        except BaseException:
            busy.release()
            raise
        busy.release()
        return result

    async def infer(job, request_id, summary):
        try:
            result = await run(job)
        except HTTPException as error:
            LOG.info("request_id=%s %s status=%d detail=%s", request_id, summary,
                     error.status_code, error.detail)
            raise
        except core.TextTooLongError:
            LOG.info("request_id=%s %s status=422 code=TEXT_TOO_LONG", request_id, summary)
            fail(422, "TEXT_TOO_LONG", "文本超出模型可编码长度，请缩短描述")
        except Exception:
            LOG.exception("request_id=%s %s status=500", request_id, summary)
            fail(500, "INFERENCE_FAILED", "推理异常，请联系服务方查看日志")
        return result

    def image_space_id(extractor):
        if extractor is None:
            return None
        digest = getattr(extractor, "definition_sha256", "")
        return f"clipreid-rn50-{digest}" if digest else getattr(extractor, "feature_space_id", None)

    def compare_job(request):
        extractor = app.state.extractor
        crops = []
        try:
            crops.append(crop_payload(request.query))
            crops.extend(crop_payload(target) for target in request.targets)
            vectors = core.normalize_features(extractor.extract_features(crops))
            if vectors.shape != (len(crops), extractor.embedding_dim):
                raise ValueError("unexpected embedding shape")
            return [{"id": target.id, "similarity": cosine(vectors[0], vectors[index + 1])}
                    for index, target in enumerate(request.targets)]
        finally:
            for crop in crops:
                crop.close()

    def compare_text_job(text, targets):
        extractor = app.state.text_extractor
        text_vector = unit(extractor.encode_text(text)[0])
        matches = []
        for target in targets:
            with crop_payload(target) as crop:
                vector = unit(extractor.encode_image(crop))
            matches.append({"id": target.id, "similarity": cosine(text_vector, vector)})
        return matches

    @app.get("/api/health")
    async def health():
        extractor = getattr(app.state, "extractor", None)
        text = getattr(app.state, "text_extractor", None)
        text_ready = bool(app.state.text_ready and text is not None)
        body = {
            "service": "reid",
            "ready": bool(app.state.ready and extractor is not None),
            "model": app.state.image_model,
            "model_sha256": app.state.image_sha,
            "feature_space_id": image_space_id(extractor),
            "embedding_dim": getattr(extractor, "embedding_dim", None),
            "device": getattr(extractor, "device", None),
            "text_reid": {
                "ready": text_ready,
                "model": app.state.text_model,
                "model_sha256": app.state.text_sha,
                "feature_space_id": getattr(text, "feature_space_id", None) if text_ready else None,
                "text_contract_id": getattr(text, "text_contract_id", None) if text_ready else None,
                "embedding_dim": getattr(text, "embedding_dim", None) if text_ready else None,
                "device": getattr(text, "device", None) if text_ready else None,
            },
        }
        if not body["ready"]:
            body["error"] = "MODEL_NOT_READY"
        if not text_ready:
            body["text_reid"]["error"] = app.state.text_error or "MODEL_NOT_READY"
        return JSONResponse(body, status_code=200 if body["ready"] else 503)

    @app.post("/api/analysis/reid/compare")
    async def compare(request: CompareRequest):
        if not app.state.ready:
            fail(503, "MODEL_NOT_READY", "图像特征模型未就绪")
        check_target_ids(request.targets)
        started = time.perf_counter()
        matches = await infer(lambda: compare_job(request), request.request_id,
                              f"compare targets={len(request.targets)}")
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        LOG.info("request_id=%s compare targets=%d duration_ms=%s", request.request_id,
                 len(request.targets), duration_ms)
        return {
            "request_id": request.request_id,
            "metric": "cosine",
            "model": app.state.image_model,
            "model_sha256": app.state.image_sha,
            "feature_space_id": image_space_id(app.state.extractor),
            "embedding_dim": app.state.extractor.embedding_dim,
            "duration_ms": duration_ms,
            "cold_start": False,
            "matches": matches,
        }

    @app.post("/api/analysis/reid/compare-text")
    async def compare_text(request: CompareTextRequest):
        text = request.query.text.strip()
        if not text:
            fail(422, "TEXT_EMPTY", "文字描述不能为空")
        if len(text) > MAX_TEXT_CHARS:
            fail(422, "TEXT_TOO_LONG", f"文字描述不能超过 {MAX_TEXT_CHARS} 个字符")
        if not app.state.text_ready:
            fail(503, "TEXT_MODEL_NOT_READY", "文字特征模型未就绪；compare 接口不受影响")
        check_target_ids(request.targets)
        language = core.detect_language(text, request.query.language)
        started = time.perf_counter()
        matches = await infer(lambda: compare_text_job(text, request.targets), request.request_id,
                              f"compare-text targets={len(request.targets)} chars={len(text)}")
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        LOG.info("request_id=%s compare-text targets=%d chars=%d duration_ms=%s",
                 request.request_id, len(request.targets), len(text), duration_ms)
        extractor = app.state.text_extractor
        return {
            "request_id": request.request_id,
            "metric": "cosine",
            "query_type": "text",
            "model": app.state.text_model,
            "model_sha256": app.state.text_sha,
            "feature_space_id": extractor.feature_space_id,
            "text_contract_id": extractor.text_contract_id,
            "embedding_dim": extractor.embedding_dim,
            "language": language,
            "duration_ms": duration_ms,
            "cold_start": False,
            "matches": matches,
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.getenv("REID_REMOTE_HOST", "127.0.0.1"),
                port=int(os.getenv("REID_REMOTE_PORT", "28025")), workers=1)