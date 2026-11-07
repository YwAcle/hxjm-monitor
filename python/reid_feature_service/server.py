"""Standalone CLIP-ReID image and Chinese-CLIP text feature API; no database or tracking dependencies."""

import asyncio
import hashlib
import importlib
import json
import logging
import os
import re
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
# Shared, read-only deployment copy; override with REID_FEATURE_TEXT_MODEL.
DEFAULT_TEXT_MODEL = Path("/data/nfs_storage/hxjm_datas/models/reid/chinese-clip-vit-base-patch16")

_PATH_FIELDS = {"weights", "config", "yolo_weights", "text_model"}
_STRING_FIELDS = {"device", "text_space_id", "text_contract_id"}
_OPTIONAL_BLANK_FIELDS = {"text_model", "text_space_id", "text_contract_id"}


@dataclass(frozen=True)
class Settings:
    weights: Path = REID_ROOT / "weights/MSMT17_clipreid_RN50_120.pth"
    config: Path = REID_ROOT / "config/cnn_base.yml"
    yolo_weights: Path = REID_ROOT / "weights/yolov8n.pt"
    text_model: Path = DEFAULT_TEXT_MODEL
    detection_confidence: float = 0.4
    device: str = "auto"
    cpu_threads: int = 2
    max_image_bytes: int = 10 * 1024 * 1024
    max_request_bytes: int = 32 * 1024 * 1024
    max_pixels: int = 4096 * 4096
    max_frames: int = 32
    sample_frames: int = 8
    max_requests: int = 8
    text_max_chars: int = 200
    text_max_tokens: int = 0  # 0 derives the limit from the model configuration
    text_space_id: str = ""  # optional pinned override of the derived feature space
    text_contract_id: str = ""  # optional pinned override of the derived text contract

    def __post_init__(self):
        for name in ("cpu_threads", "max_image_bytes", "max_request_bytes", "max_pixels",
                     "max_frames", "sample_frames", "max_requests", "text_max_chars"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.text_max_tokens < 0:
            raise ValueError("text_max_tokens must not be negative")
        if self.sample_frames > self.max_frames:
            raise ValueError("sample_frames must not exceed max_frames")
        if not 0 < self.detection_confidence <= 1:
            raise ValueError("detection_confidence must be in (0, 1]")

    @classmethod
    def from_env(cls):
        values = {}
        for name in cls.__dataclass_fields__:
            raw = os.getenv(f"REID_FEATURE_{name.upper()}")
            if raw is None:
                continue
            if name in _OPTIONAL_BLANK_FIELDS and not raw.strip():
                continue
            if name in _PATH_FIELDS:
                values[name] = Path(raw).expanduser()
            elif name in _STRING_FIELDS:
                values[name] = raw
            elif name == "detection_confidence":
                values[name] = float(raw)
            else:
                values[name] = int(raw)
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


class TextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str
    language: str = "auto"
    template_id: str = Field(default="", max_length=128)
    metadata: dict = Field(default_factory=dict)


class TextTooLongError(ValueError):
    """The text cannot be encoded without truncation."""


_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LATIN = re.compile(r"[A-Za-z]")


def detect_language(text, requested):
    if requested and requested != "auto":
        return requested
    if _CJK.search(text):
        return "zh"
    if _LATIN.search(text):
        return "en"
    return "unknown"


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


def sha256_file(path):
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def canonical_definition_text(definition):
    """Serialize a feature-space definition exactly as it is hashed for its ID."""
    return json.dumps(definition, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def space_identity(definition_text, prefix, version, *, digest_chars=64):
    """Derive the feature-space ID from the complete definition digest.

    The business API only accepts ``fs-<sha256>`` for new spaces (and the legacy
    ``clipreid-rn50-<first 24 hex>`` for the existing CLIP-ReID space), so the ID is
    always derived from the exact text that is returned as ``definition_text``.
    """
    digest = hashlib.sha256(definition_text.encode("utf-8")).hexdigest()
    return prefix + digest[:digest_chars], digest, version


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
        digest = sha256_file(settings.weights)
        code_digest = hashlib.sha256((REID_ROOT / "CLIP-ReID/model/make_model.py").read_bytes()
                                     + (REID_ROOT / "CLIP-ReID/model/clip/model.py").read_bytes()).hexdigest()
        # Keep the legacy serialization (Python json defaults, sort_keys) so the derived
        # space ID remains clipreid-rn50-<24 hex> and existing 3072-d features stay valid.
        self.definition_text = json.dumps({"weights": digest, "model_code": code_digest,
                                           "config": cfg.dump(),
                                           "preprocess": "rgb_resize_tensor_v1"}, sort_keys=True)
        (self.feature_space_id, self.definition_sha256,
         self.definition_version) = space_identity(
            self.definition_text, "clipreid-rn50-", "legacy_python_json_v1", digest_chars=24)
        self.embedding_dim = 3072
        self.extract_features([Image.new("RGB", (128, 256))])

    def extract_features(self, images):
        batch = self.torch.stack([self.transform(image) for image in images]).to(self.device)
        with self.torch.inference_mode():
            result = self.model(batch).float().cpu().numpy()
        if result.shape != (len(images), self.embedding_dim):
            raise ValueError("unexpected CLIP-ReID output shape")
        return normalize_features(result)


class TextExtractor:
    """Chinese-CLIP text and image encoders sharing one projected feature space.

    This space is deliberately separate from CLIP-ReID: vectors from the two models are
    never compared or mixed. The model is loaded from a local directory only, so the
    service never downloads weights at runtime.
    """

    model_profile = "chinese_clip_text_reid"
    model_name = "Chinese-CLIP-ViT-B-16"

    def __init__(self, settings, device="auto"):
        import torch
        from transformers import ChineseCLIPConfig, ChineseCLIPModel, ChineseCLIPProcessor

        self.torch = torch
        self.model_path = Path(settings.text_model).expanduser()
        if not self.model_path.is_dir():
            raise FileNotFoundError(f"Chinese-CLIP model directory is missing: {self.model_path}")
        config_path = self.model_path / "config.json"
        if not config_path.is_file():
            raise FileNotFoundError(f"Chinese-CLIP config.json is missing: {config_path}")
        weight_files = sorted(path for path in self.model_path.iterdir()
                              if path.is_file() and path.suffix in {".bin", ".safetensors"})
        if not weight_files:
            raise FileNotFoundError(f"Chinese-CLIP weights are missing: {self.model_path}")
        weights_digest = hashlib.sha256()
        for path in weight_files:
            weights_digest.update(path.name.encode("utf-8"))
            weights_digest.update(bytes.fromhex(sha256_file(path)))
        hf_config = ChineseCLIPConfig.from_pretrained(str(self.model_path), local_files_only=True)
        self.embedding_dim = int(getattr(hf_config, "projection_dim", 0) or 0)
        if self.embedding_dim <= 0:
            raise ValueError("Chinese-CLIP config.json has no valid projection_dim")
        # The business API registers a new space only when its ID is fs-<full digest>
        # and the same digest is returned as definition_sha256. Keep this definition
        # independent of runtime knobs (device, request limits, token caps) so a
        # restart cannot silently move the space.
        self.definition_text = canonical_definition_text({
            "schema": "hxjm.feature-space.v1",
            "object_type": "person",
            "feature_kind": "text_reid",
            "model": "chinese-clip-vit-base-patch16",
            "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
            "weights_sha256": weights_digest.hexdigest(),
            "preprocess": "rgb_resize_224_v1",
            "text_contract": "single_text_projection_l2_v1",
            "dimensions": self.embedding_dim,
            "normalization": "l2",
            "metric": "cosine",
        })
        (derived_space, self.definition_sha256,
         self.definition_version) = space_identity(
            self.definition_text, "fs-", "canonical_json_v1")
        pinned_space = settings.text_space_id.strip()
        self.feature_space_id = pinned_space or derived_space
        if pinned_space and pinned_space != derived_space:
            LOG.warning("pinned text feature space %s does not match the definition digest %s",
                        pinned_space, derived_space)
        self.text_contract_id = settings.text_contract_id.strip() or f"{self.feature_space_id}-text-v1"
        self.max_tokens = int(getattr(getattr(hf_config, "text_config", None),
                                      "max_position_embeddings", 512) or 512)
        if settings.text_max_tokens:
            self.max_tokens = min(self.max_tokens, settings.text_max_tokens)
        self.device = device
        if self.device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.processor = ChineseCLIPProcessor.from_pretrained(str(self.model_path), local_files_only=True)
        if any(path.suffix == ".safetensors" for path in weight_files):
            model = ChineseCLIPModel.from_pretrained(str(self.model_path), local_files_only=True)
        else:
            model = self._load_bin_model(ChineseCLIPModel, hf_config, weight_files)
        self.model = model.float().to(self.device).eval()
        self.alignment_verified = False
        self._verify_alignment()

    def _load_bin_model(self, model_class, config, weight_files):
        """Load a trusted local .bin checkpoint when transformers refuses torch<2.6.

        transformers>=5 blocks torch.load even with weights_only=True below torch 2.6
        (CVE-2025-32434) and only waives the check for safetensors. The shared model
        directory is a read-only deployment copy, so load its tensors directly instead
        of upgrading the whole ReID environment. Missing or unexpected keys are still
        validated; only the harmless position_ids buffers may differ.
        """
        model = model_class(config)
        state = {}
        for path in weight_files:
            checkpoint = self.torch.load(str(path), map_location="cpu", weights_only=True)
            checkpoint = checkpoint.get("state_dict", checkpoint)
            state.update({key.removeprefix("module."): value for key, value in checkpoint.items()})
        result = model.load_state_dict(state, strict=False)
        parameters = dict(model.named_parameters())
        missing = sorted(key for key in result.missing_keys if key in parameters)
        if missing:
            raise ValueError(f"Chinese-CLIP checkpoint is missing parameters: {missing[:5]}")
        unexpected = [key for key in result.unexpected_keys if not key.endswith("position_ids")]
        if unexpected:
            LOG.warning("ignoring unexpected Chinese-CLIP checkpoint keys: %s", unexpected[:5])
        return model

    def _pooled(self, output):
        if isinstance(output, self.torch.Tensor):
            return output
        vector = getattr(output, "pooler_output", None)
        if not isinstance(vector, self.torch.Tensor):
            raise ValueError("Chinese-CLIP did not return a projected embedding")
        return vector

    def encode_text(self, text):
        """Return the normalized text vector and token count; never truncates silently."""
        inputs = self.processor(text=[text], return_tensors="pt", padding=True, truncation=False)
        inputs = {key: value.to(self.device) for key, value in dict(inputs).items()}
        if inputs["input_ids"].shape[1] > self.max_tokens:
            raise TextTooLongError("text exceeds the model's token limit")
        with self.torch.inference_mode():
            vector = self._pooled(self.model.get_text_features(**inputs)).float().cpu().numpy()
        features = normalize_features(vector)
        if features.shape != (1, self.embedding_dim):
            raise ValueError("unexpected Chinese-CLIP text output shape")
        return features[0], int(inputs["attention_mask"].sum().item())

    def encode_image(self, image):
        inputs = self.processor(images=image, return_tensors="pt")
        pixel_values = inputs["pixel_values"].to(self.device)
        with self.torch.inference_mode():
            vector = self._pooled(self.model.get_image_features(pixel_values=pixel_values)).float().cpu().numpy()
        features = normalize_features(vector)
        if features.shape != (1, self.embedding_dim):
            raise ValueError("unexpected Chinese-CLIP image output shape")
        return features[0]

    def _verify_alignment(self):
        """Probe both encoders before advertising readiness.

        This is a structural smoke check, not an accuracy evaluation: both projections
        must produce finite unit vectors of the configured dimension in one shared space.
        """
        probe_image = Image.new("RGB", (224, 224), (128, 128, 128))
        try:
            text_vector, _ = self.encode_text("一名穿着深色外套的行人")
            image_vector = self.encode_image(probe_image)
        finally:
            probe_image.close()
        if text_vector.shape != image_vector.shape or text_vector.shape != (self.embedding_dim,):
            raise ValueError("Chinese-CLIP text and image embeddings use different dimensions")
        if not np.isfinite(np.dot(text_vector, image_vector)):
            raise ValueError("Chinese-CLIP alignment probe produced a non-finite similarity")
        self.alignment_verified = True


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


def create_app(settings=None, extractor_factory=Extractor, detector_factory=PersonDetector,
               text_extractor_factory=TextExtractor):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="clipreid")
        app.state.ready = False
        app.state.executor = executor
        app.state.detector = None
        app.state.text_extractor = None
        app.state.text_ready = False
        app.state.text_error = None
        try:
            app.state.extractor = await asyncio.get_running_loop().run_in_executor(
                executor, extractor_factory, settings)
            app.state.ready = True
            if text_extractor_factory is not None:
                # Text ReID is optional: a missing or broken Chinese-CLIP model must not
                # take down the existing CLIP-ReID image endpoints.
                try:
                    app.state.text_extractor = await asyncio.get_running_loop().run_in_executor(
                        executor, text_extractor_factory, settings, app.state.extractor.device)
                except Exception:
                    LOG.exception("Chinese-CLIP text model initialization failed; "
                                  "text ReID endpoints will be unavailable")
                    app.state.text_error = "initialization_failed"
                else:
                    app.state.text_ready = True
            else:
                app.state.text_error = "disabled"
            yield
        finally:
            app.state.ready = False
            app.state.text_ready = False
            executor.shutdown(wait=True, cancel_futures=True)

    app = FastAPI(title="CLIP-ReID and Chinese-CLIP feature service", version="1.1.0",
                  lifespan=lifespan)
    app.state.ready = False
    app.state.text_extractor = None
    app.state.text_ready = False
    app.state.text_error = None
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

    def text_feature_response(extractor, text, language, metadata):
        vector, token_count = extractor.encode_text(text)
        if vector.shape != (extractor.embedding_dim,):
            raise ValueError("unexpected text embedding dimension")
        return {
            "request_id": str(uuid.uuid4()),
            "feature_type": "text",
            "model_profile": extractor.model_profile,
            "embedding": vector.tolist(),
            "embedding_dim": extractor.embedding_dim,
            "feature_space_id": extractor.feature_space_id,
            "text_contract_id": extractor.text_contract_id,
            "normalized": True,
            "dtype": "float32",
            "truncated": False,
            "language": language,
            "token_count": token_count,
            "text_chars": len(text),
            "source": metadata,
            "persistence_status": "not_requested",
        }

    def text_image_response(extractor, image):
        vector = extractor.encode_image(image)
        if vector.shape != (extractor.embedding_dim,):
            raise ValueError("unexpected image embedding dimension")
        return {
            "request_id": str(uuid.uuid4()),
            "feature_type": "image",
            "model_profile": extractor.model_profile,
            "embedding": vector.tolist(),
            "embedding_dim": extractor.embedding_dim,
            "feature_space_id": extractor.feature_space_id,
            "normalized": True,
            "dtype": "float32",
            "image_width": image.width,
            "image_height": image.height,
            "source": {},
            "persistence_status": "not_requested",
        }

    async def await_text_job(future):
        try:
            return await asyncio.shield(future)
        except TextTooLongError:
            fail(422, "TEXT_TOO_LONG", "text exceeds the model's encodable length; shorten the description")
        except asyncio.CancelledError:
            try:
                await asyncio.shield(future)
            except Exception:
                LOG.exception("cancelled text request's extraction failed")
            raise
        except HTTPException:
            raise
        except Exception:
            LOG.exception("Chinese-CLIP feature extraction failed")
            fail(500, "TEXT_EXTRACTION_FAILED", "text feature extraction failed; consult service logs")

    @app.get("/health")
    async def health():
        extractor = getattr(app.state, "extractor", None)
        text = getattr(app.state, "text_extractor", None)
        text_ready = bool(getattr(app.state, "text_ready", False) and text is not None)
        text_block = {
            "ready": text_ready,
            "alignment_verified": bool(getattr(text, "alignment_verified", False)) if text_ready else False,
            "model": getattr(text, "model_name", "Chinese-CLIP-ViT-B-16"),
            "feature_space_id": getattr(text, "feature_space_id", None),
            "embedding_dim": getattr(text, "embedding_dim", None),
            "text_contract_id": getattr(text, "text_contract_id", None),
            "definition_text": getattr(text, "definition_text", None),
            "definition_sha256": getattr(text, "definition_sha256", None),
            "definition_version": getattr(text, "definition_version", None),
            "device": getattr(text, "device", None),
        }
        if not text_ready and getattr(app.state, "text_error", None):
            text_block["error"] = app.state.text_error
        return JSONResponse({"ready": app.state.ready,
                             "model": "CLIP-ReID-RN50",
                             "feature_space_id": getattr(extractor, "feature_space_id", None),
                             "embedding_dim": getattr(extractor, "embedding_dim", None),
                             "definition_text": getattr(extractor, "definition_text", None),
                             "definition_sha256": getattr(extractor, "definition_sha256", None),
                             "definition_version": getattr(extractor, "definition_version", None),
                             "device": getattr(extractor, "device", None),
                             "detector_loaded": getattr(app.state, "detector", None) is not None,
                             "text_reid": text_block},
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

    @app.post("/v1/reid/text-features")
    async def text_features(request: TextRequest):
        """Encode a search description; vectors are comparable only within this text space."""
        if not app.state.text_ready:
            fail(503, "TEXT_MODEL_NOT_READY", "Chinese-CLIP text model is not ready; consult service logs")
        text = request.text.strip()
        if not text:
            fail(422, "TEXT_EMPTY", "text must not be empty")
        if len(text) > settings.text_max_chars:
            fail(422, "TEXT_TOO_LONG", f"text must not exceed {settings.text_max_chars} characters")
        language = detect_language(text, request.language)
        future = asyncio.get_running_loop().run_in_executor(
            app.state.executor, text_feature_response, app.state.text_extractor, text,
            language, request.metadata)
        return await await_text_job(future)

    @app.post("/v1/reid/text-reid-image-features")
    async def text_reid_image_features(file: UploadFile = File(...)):
        """Encode an enrolled-person image into the same space as the text encoder."""
        if not app.state.text_ready:
            fail(503, "TEXT_MODEL_NOT_READY", "Chinese-CLIP text model is not ready; consult service logs")
        try:
            data = await file.read(settings.max_image_bytes + 1)
            if len(data) > settings.max_image_bytes:
                fail(413, "IMAGE_TOO_LARGE", "image exceeds the configured byte limit")
            image = decode_image(data, settings)
            try:
                future = asyncio.get_running_loop().run_in_executor(
                    app.state.executor, text_image_response, app.state.text_extractor, image)
                return await await_text_job(future)
            finally:
                image.close()
        finally:
            await file.close()

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.getenv("REID_FEATURE_HOST", "127.0.0.1"),
                port=int(os.getenv("REID_FEATURE_PORT", "28024")), workers=1)
