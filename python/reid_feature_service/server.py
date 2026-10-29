"""Standalone CLIP-ReID feature API; no database or video tracking dependencies."""

import asyncio
import hashlib
import importlib
import json
import logging
import os
import sys
import types
import uuid
import warnings
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.responses import JSONResponse


LOG = logging.getLogger(__name__)
REID_ROOT = Path(__file__).resolve().parents[1] / "reid"


@dataclass(frozen=True)
class Settings:
    weights: Path = REID_ROOT / "weights/MSMT17_clipreid_RN50_120.pth"
    config: Path = REID_ROOT / "config/cnn_base.yml"
    yolo_weights: Path = REID_ROOT / "weights/yolov8n.pt"
    detection_confidence: float = 0.4
    device: str = "auto"
    cpu_threads: int = 2
    max_image_bytes: int = 10 * 1024 * 1024
    max_request_bytes: int = 32 * 1024 * 1024
    max_pixels: int = 4096 * 4096
    max_frames: int = 32
    sample_frames: int = 8
    max_requests: int = 8

    def __post_init__(self):
        for name in ("cpu_threads", "max_image_bytes", "max_request_bytes", "max_pixels",
                     "max_frames", "sample_frames", "max_requests"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.sample_frames > self.max_frames:
            raise ValueError("sample_frames must not exceed max_frames")
        if not 0 < self.detection_confidence <= 1:
            raise ValueError("detection_confidence must be in (0, 1]")

    @classmethod
    def from_env(cls):
        values = {}
        for name in cls.__dataclass_fields__:
            value = os.getenv(f"REID_FEATURE_{name.upper()}")
            if value is not None:
                values[name] = Path(value).expanduser() if name in {"weights", "config", "yolo_weights"} else (
                    value if name == "device" else float(value) if name == "detection_confidence" else int(value)
                )
        return cls(**values)


class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=1, max_length=128)
    source_asset_id: str | None = Field(default=None, max_length=256)
    camera_id: str | None = Field(default=None, max_length=128)
    stream_session_id: str | None = Field(default=None, max_length=128)
    track_id: str | None = Field(default=None, max_length=128)
    segment_id: str | None = Field(default=None, max_length=128)
    frame_ids: list[str] | None = None


def fail(status, code, message):
    raise HTTPException(status, detail={"error_code": code, "message": message})


def parse_metadata(raw, count):
    if len(raw.encode("utf-8")) > 8192:
        fail(413, "METADATA_TOO_LARGE", "metadata must not exceed 8 KiB")
    try:
        metadata = Metadata.model_validate_json(raw)
    except ValidationError:
        fail(422, "INVALID_METADATA", "metadata must be a JSON object matching the documented schema")
    if metadata.frame_ids is not None:
        ids = metadata.frame_ids
        if len(ids) != count or len(set(ids)) != count or any(not x or len(x) > 128 for x in ids):
            fail(422, "INVALID_FRAME_IDS", "frame_ids must be unique nonempty strings, one per image")
    return metadata


def decode_image(data, settings):
    if not data:
        fail(422, "INVALID_IMAGE", "image is empty")
    if len(data) > settings.max_image_bytes:
        fail(413, "IMAGE_TOO_LARGE", "image exceeds the configured byte limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"}:
                    fail(415, "UNSUPPORTED_IMAGE_FORMAT", "only JPEG, PNG and WebP are supported")
                if image.width * image.height > settings.max_pixels:
                    fail(413, "IMAGE_TOO_LARGE", "image exceeds the configured pixel limit")
                if getattr(image, "n_frames", 1) != 1:
                    fail(422, "INVALID_IMAGE", "animated images are not supported")
                image.verify()
            with Image.open(BytesIO(data)) as image:
                return ImageOps.exif_transpose(image).convert("RGB")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        fail(413, "IMAGE_TOO_LARGE", "image exceeds the decoder pixel limit")
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        fail(422, "INVALID_IMAGE", "image cannot be decoded")


def parse_bbox(raw):
    if raw is None:
        return None
    try:
        if len(raw) > 256:
            raise ValueError("bbox is too long")
        bbox = json.loads(raw)
        if not isinstance(bbox, list) or len(bbox) != 4 or any(type(x) is not int for x in bbox):
            raise ValueError("bbox must contain four integers")
        return bbox
    except (ValueError, TypeError):
        fail(422, "INVALID_BBOX", "bbox must be a JSON array of four integer pixel coordinates [x1,y1,x2,y2]")


def crop_person(image, bbox):
    x1, y1, x2, y2 = bbox
    if not (0 <= x1 < x2 <= image.width and 0 <= y1 < y2 <= image.height):
        fail(422, "INVALID_BBOX", "bbox must have positive area and lie inside the EXIF-corrected image")
    return image.crop(tuple(bbox))


class PersonDetector:
    """A resident YOLOv8n detector, loaded only on the first screenshot request."""

    def __init__(self, settings, device):
        if not settings.yolo_weights.is_file():
            raise FileNotFoundError("local YOLO weights are missing")
        cache = Path(__file__).resolve().parents[2] / ".run/reid-feature-cache"
        cache.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("YOLO_CONFIG_DIR", str(cache))
        os.environ.setdefault("YOLO_AUTOINSTALL", "false")
        os.environ.setdefault("YOLO_OFFLINE", "true")
        from ultralytics import YOLO

        self.model = YOLO(str(settings.yolo_weights))
        self.device = device
        self.confidence = settings.detection_confidence

    def detect(self, image):
        # PIL input is RGB; Ultralytics returns boxes in original image coordinates.
        result = self.model.predict(source=image, classes=[0], conf=self.confidence,
                                    iou=0.5, imgsz=640, max_det=101,
                                    device=self.device, verbose=False)[0]
        candidates = []
        for box, confidence in zip(result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy()):
            if not np.isfinite(box).all() or not np.isfinite(confidence):
                raise ValueError("detector returned invalid boxes")
            x1, y1 = np.floor(box[:2]).astype(int)
            x2, y2 = np.ceil(box[2:]).astype(int)
            bbox = [int(np.clip(x1, 0, image.width)), int(np.clip(y1, 0, image.height)),
                    int(np.clip(x2, 0, image.width)), int(np.clip(y2, 0, image.height))]
            if bbox[2] > bbox[0] and bbox[3] > bbox[1]:
                candidates.append({"bbox": bbox, "confidence": float(confidence)})
        if len(candidates) > 100:
            fail(422, "TOO_MANY_PEOPLE", "more than 100 people detected; upload a smaller region")
        candidates.sort(key=lambda candidate: tuple(candidate["bbox"]))
        return [{"candidate_id": str(i + 1), **candidate} for i, candidate in enumerate(candidates)]


def normalize_features(features):
    features = np.asarray(features, dtype=np.float32)
    if features.ndim != 2 or not features.shape[0] or not features.shape[1] or not np.isfinite(features).all():
        raise ValueError("model returned invalid features")
    norms = np.linalg.norm(features, axis=1, keepdims=True)
    if not np.isfinite(norms).all() or np.any(norms <= 1e-12):
        raise ValueError("model returned zero or invalid feature norms")
    return features / norms


def pool_features(features):
    return normalize_features(normalize_features(features).mean(axis=0, keepdims=True))[0]


def legacy_modules():
    # An isolated package name avoids collisions with other modules named config/model.
    name = "_hxjm_feature_clipreid"
    if name not in sys.modules:
        package = types.ModuleType(name)
        package.__path__ = [str(REID_ROOT / "CLIP-ReID")]
        sys.modules[name] = package
    config = importlib.import_module(f"{name}.config")
    model = importlib.import_module(f"{name}.model.make_model")
    visual = importlib.import_module(f"{name}.model.clip.model")
    return config, model, visual


class Extractor:
    """Reuse the legacy RN50 architecture with a complete local visual checkpoint."""

    def __init__(self, settings):
        import torch
        import torchvision.transforms as T

        self.torch = torch
        if not settings.weights.is_file() or not settings.config.is_file():
            raise FileNotFoundError("CLIP-ReID weights or configuration is missing")
        config_module, model_module, visual_module = legacy_modules()
        cfg = config_module.cfg_base.clone()
        cfg.merge_from_file(str(settings.config))
        cfg.freeze()
        if cfg.MODEL.NAME != "RN50" or cfg.MODEL.SIE_CAMERA or cfg.MODEL.SIE_VIEW:
            raise ValueError("this service supports RN50 without camera/view embeddings")
        if list(cfg.INPUT.SIZE_TEST) != list(cfg.INPUT.SIZE_TRAIN):
            raise ValueError("RN50 train/test input dimensions must agree")
        self.device = settings.device
        if self.device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            if self.device == "cuda":
                try:
                    torch.empty(1, device="cuda")
                except RuntimeError:
                    LOG.warning("CUDA initialization failed; using CPU", exc_info=True)
                    self.device = "cpu"
        if self.device == "cpu":
            torch.set_num_threads(settings.cpu_threads)
        checkpoint = torch.load(str(settings.weights), map_location="cpu", weights_only=True)
        checkpoint = checkpoint.get("state_dict", checkpoint)
        checkpoint = {k.removeprefix("module."): v for k, v in checkpoint.items()}

        def local_visual(backbone, h_resolution, w_resolution, stride):
            # The ReID checkpoint already contains every image_encoder parameter.
            # Reuse ModifiedResNet directly, avoiding the legacy internet download.
            clip_model = torch.nn.Module()
            clip_model.visual = visual_module.ModifiedResNet(
                layers=(3, 4, 6, 3), output_dim=1024, heads=32,
                input_resolution=h_resolution * w_resolution, width=64,
            )
            return clip_model

        original_loader = model_module.load_clip_to_cpu
        try:
            model_module.load_clip_to_cpu = local_visual
            self.model = model_module.make_model(cfg, num_class=1, camera_num=None,
                                                 view_num=None, device="cpu")
        finally:
            model_module.load_clip_to_cpu = original_loader
        # Skip training heads/text parameters, but strictly require every inference parameter.
        state = self.model.state_dict()
        required = {k: checkpoint[k] for k in state if not k.startswith("classifier") and k in checkpoint}
        missing = set(state) - set(required) - {k for k in state if k.startswith("classifier")}
        if missing:
            raise ValueError(f"checkpoint is missing inference parameters: {sorted(missing)[:5]}")
        state.update(required)
        self.model.load_state_dict(state, strict=True)
        self.model = self.model.float().to(self.device).eval()
        self.transform = T.Compose([
            T.Resize(tuple(cfg.INPUT.SIZE_TEST)), T.ToTensor(),
            T.Normalize(mean=cfg.INPUT.PIXEL_MEAN, std=cfg.INPUT.PIXEL_STD),
        ])
        with settings.weights.open("rb") as weights_file:
            digest = hashlib.file_digest(weights_file, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else None
        if digest is None:  # Python 3.10, used by the existing ReID environment.
            hasher = hashlib.sha256()
            with settings.weights.open("rb") as weights_file:
                for chunk in iter(lambda: weights_file.read(1024 * 1024), b""):
                    hasher.update(chunk)
            digest = hasher.hexdigest()
        code_digest = hashlib.sha256((REID_ROOT / "CLIP-ReID/model/make_model.py").read_bytes()
                                     + (REID_ROOT / "CLIP-ReID/model/clip/model.py").read_bytes()).hexdigest()
        pipeline = json.dumps({"weights": digest, "model_code": code_digest, "config": cfg.dump(),
                               "preprocess": "rgb_resize_tensor_v1"}, sort_keys=True)
        self.definition_text = pipeline
        self.definition_sha256 = hashlib.sha256(pipeline.encode()).hexdigest()
        self.feature_space_id = "clipreid-rn50-" + self.definition_sha256[:24]
        self.embedding_dim = 3072
        self.extract_features([Image.new("RGB", (128, 256))])

    def extract_features(self, images):
        batch = self.torch.stack([self.transform(image) for image in images]).to(self.device)
        with self.torch.inference_mode():
            result = self.model(batch).float().cpu().numpy()
        if result.shape != (len(images), self.embedding_dim):
            raise ValueError("unexpected CLIP-ReID output shape")
        return normalize_features(result)


class RequestLimits:
    """Bound uploads and admission before FastAPI parses multipart bodies."""

    def __init__(self, app, settings):
        self.app, self.settings, self.active = app, settings, 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = -1
        if declared < 0 or declared > self.settings.max_request_bytes:
            return await JSONResponse({"detail": {"error_code": "REQUEST_TOO_LARGE", "message": "request byte limit exceeded"}}, 413)(scope, receive, send)
        if self.active >= self.settings.max_requests:
            return await JSONResponse({"detail": {"error_code": "SERVICE_BUSY", "message": "request capacity reached"}}, 503)(scope, receive, send)
        self.active += 1
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > self.settings.max_request_bytes:
                fail(413, "REQUEST_TOO_LARGE", "request byte limit exceeded")
            return message

        try:
            await self.app(scope, bounded_receive, send)
        finally:
            self.active -= 1


def create_app(settings=None, extractor_factory=Extractor, detector_factory=PersonDetector):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="clipreid")
        app.state.ready = False
        app.state.executor = executor
        app.state.detector = None
        try:
            app.state.extractor = await asyncio.get_running_loop().run_in_executor(
                executor, extractor_factory, settings)
            app.state.ready = True
            yield
        finally:
            app.state.ready = False
            executor.shutdown(wait=True, cancel_futures=True)

    app = FastAPI(title="CLIP-ReID feature service", version="1.0.0", lifespan=lifespan)
    app.state.ready = False
    app.add_middleware(RequestLimits, settings=settings)

    def feature_response(images, metadata, count, selected, aggregate):
        extractor = app.state.extractor
        features = extractor.extract_features(images)
        vector = pool_features(features) if aggregate else normalize_features(features)[0]
        if vector.shape != (extractor.embedding_dim,):
            raise ValueError("unexpected embedding dimension")
        frame_ids = metadata.frame_ids or [str(i) for i in range(count)]
        return {
            "request_id": metadata.request_id, "feature_type": "tracklet" if aggregate else "image",
            "embedding": vector.tolist(), "embedding_dim": extractor.embedding_dim,
            "feature_space_id": extractor.feature_space_id, "normalized": True, "dtype": "float32",
            "aggregation": "mean_l2_v1" if aggregate else "none",
            "input_count": count, "used_count": len(selected),
            "selected_frame_ids": [frame_ids[i] for i in selected],
            "source": metadata.model_dump(exclude={"request_id", "frame_ids"}, exclude_none=True),
            "persistence_status": "not_requested",
        }

    def crop_features(image, bbox, metadata):
        with crop_person(image, bbox) as crop:
            result = feature_response([crop], metadata, 1, [0], False)
        result["crop"] = {"bbox": bbox, "image_width": image.width, "image_height": image.height,
                          "coordinate_system": "xyxy_pixels_exif_corrected"}
        return result

    def process(payloads, metadata, aggregate, bbox, detect):
        # Validate every input, including frames not selected for inference.
        count = len(payloads)
        selected = np.linspace(0, count - 1, min(count, settings.sample_frames), dtype=int).tolist() if aggregate else [0]
        images = []
        try:
            for index, data in enumerate(payloads):
                image = decode_image(data, settings)
                if index in selected:
                    images.append(image)
                else:
                    image.close()
            if detect:
                if app.state.detector is None:
                    try:
                        app.state.detector = detector_factory(settings, app.state.extractor.device)
                    except Exception:
                        LOG.exception("person detector initialization failed")
                        fail(503, "DETECTOR_UNAVAILABLE", "person detector is unavailable; consult service logs")
                image = images[0]
                candidates = app.state.detector.detect(image)
                count = len(candidates)
                return {
                    "request_id": metadata.request_id,
                    "status": "no_person" if count == 0 else "extracted" if count == 1 else "selection_required",
                    "image_width": image.width, "image_height": image.height,
                    "coordinate_system": "xyxy_pixels_exif_corrected",
                    "person_count": count, "selection_required": count > 1,
                    "candidates": candidates,
                    "selected_candidate_id": candidates[0]["candidate_id"] if count == 1 else None,
                    "feature": crop_features(image, candidates[0]["bbox"], metadata) if count == 1 else None,
                }
            if bbox is not None:
                return crop_features(images[0], bbox, metadata)
            return feature_response(images, metadata, count, selected, aggregate)
        finally:
            for image in images:
                image.close()

    async def extract(files, raw_metadata, aggregate, raw_bbox=None, detect=False):
        try:
            if not app.state.ready:
                fail(503, "MODEL_NOT_READY", "model is not ready")
            if not 1 <= len(files) <= settings.max_frames:
                fail(422, "INVALID_FRAME_COUNT", f"provide 1 to {settings.max_frames} images")
            metadata = parse_metadata(raw_metadata, len(files))
            bbox = parse_bbox(raw_bbox)
            payloads = []
            for file in files:
                data = await file.read(settings.max_image_bytes + 1)
                if len(data) > settings.max_image_bytes:
                    fail(413, "IMAGE_TOO_LARGE", "image exceeds the configured byte limit")
                payloads.append(data)
            future = asyncio.get_running_loop().run_in_executor(
                app.state.executor, process, payloads, metadata, aggregate, bbox, detect)
            try:
                return await asyncio.shield(future)
            except asyncio.CancelledError:
                # Retain admission until the running GPU/CPU job really finishes.
                # Cancelling a coroutine cannot terminate a PyTorch forward call.
                try:
                    await asyncio.shield(future)
                except Exception:
                    LOG.exception("cancelled request's extraction failed")
                raise
        except HTTPException:
            raise
        except Exception:
            LOG.exception("feature extraction failed")
            fail(500, "EXTRACTION_FAILED", "feature extraction failed; consult service logs")
        finally:
            for file in files:
                await file.close()

    @app.get("/health")
    async def health():
        extractor = getattr(app.state, "extractor", None)
        return JSONResponse({"ready": app.state.ready,
                             "model": "CLIP-ReID-RN50",
                             "feature_space_id": getattr(extractor, "feature_space_id", None),
                             "embedding_dim": getattr(extractor, "embedding_dim", None),
                             "definition_text": getattr(extractor, "definition_text", None),
                             "definition_sha256": getattr(extractor, "definition_sha256", None),
                             "definition_version": "1",
                             "device": getattr(extractor, "device", None),
                             "detector_loaded": getattr(app.state, "detector", None) is not None},
                            status_code=200 if app.state.ready else 503)

    @app.post("/v1/reid/person-crops")
    async def person_crops(file: UploadFile = File(...), metadata: str = Form("{}")):
        """Detect screenshot people: one returns crop features; multiple return boxes for Agent selection.

        No image/session is retained. For multiple people, submit the same original file and the
        selected candidate's bbox to /v1/reid/image-features after the user chooses.
        """
        return await extract([file], metadata, False, detect=True)

    @app.post("/v1/reid/image-features")
    async def image_features(file: UploadFile = File(...), metadata: str = Form("{}"),
                             bbox: str | None = Form(None, description="Optional JSON [x1,y1,x2,y2], integer pixels in the EXIF-corrected original image")):
        """Extract a person crop, or crop the original screenshot using bbox. Does not run YOLO."""
        return await extract([file], metadata, False, raw_bbox=bbox)

    @app.post("/v1/reid/tracklet-features")
    async def tracklet_features(files: list[UploadFile] = File(...), metadata: str = Form("{}")):
        """Pool one person's crops; files and frame_ids must be in chronological order."""
        return await extract(files, metadata, True)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.getenv("REID_FEATURE_HOST", "127.0.0.1"),
                port=int(os.getenv("REID_FEATURE_PORT", "28024")), workers=1)
