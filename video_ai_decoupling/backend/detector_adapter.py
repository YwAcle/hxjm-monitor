import os
import sys
import time
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

from .config import DEMO_ROOT, PYTHON_ROOT


def load_existing_detection():
    runtime_root = DEMO_ROOT / ".runtime"
    os.environ["YOLO_AUTOINSTALL"] = "false"
    os.environ["YOLO_OFFLINE"] = "true"
    for variable, directory in (
        ("YOLO_CONFIG_DIR", "ultralytics"),
        ("MPLCONFIGDIR", "matplotlib"),
        ("CUDA_CACHE_PATH", "cuda"),
        ("TORCH_HOME", "torch"),
        ("XDG_CACHE_HOME", "cache"),
    ):
        path = runtime_root / directory
        path.mkdir(parents=True, exist_ok=True)
        os.environ[variable] = str(path)

    sys.dont_write_bytecode = True
    python_path = str(PYTHON_ROOT)
    if python_path not in sys.path:
        sys.path.insert(0, python_path)

    from deepsort import server as existing_detection

    return existing_detection


@lru_cache(maxsize=1)
def _load_model_context():
    default_model = PYTHON_ROOT / "deep_sort-master" / "detection" / "yolov5mu.pt"
    model_path = Path(os.getenv("DEEPSORT_MODEL", str(default_model))).expanduser().resolve()
    if not model_path.is_file() or model_path.stat().st_size == 0:
        raise FileNotFoundError(f"Local model weights missing or empty: {model_path}")
    if model_path.suffix.lower() != ".pt":
        raise ValueError(f"Expected local PyTorch .pt weights: {model_path}")
    os.environ["DEEPSORT_MODEL"] = str(model_path)

    existing_detection = load_existing_detection()
    model_context = existing_detection.DetectionServer.init_model_context()
    return existing_detection, model_context


def initialize_detector():
    _load_model_context()


def detect_people(frame):
    import cv2

    height, width = frame.shape[:2]
    if height <= 0 or width <= 0:
        raise ValueError("Cannot detect an empty frame")

    existing_detection, model_context = _load_model_context()
    model = model_context["sahi"]
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    started_at = time.perf_counter()
    model.perform_inference(rgb_frame)
    model.convert_original_predictions(full_shape=[height, width])
    boxes = existing_detection._person_boxes(SimpleNamespace(
        object_prediction_list=model.object_prediction_list,
    ))
    inference_ms = (time.perf_counter() - started_at) * 1000

    detections = []
    for box, score in boxes:
        left, top, box_width, box_height = box
        normalized_box = [
            max(0.0, min(1.0, left / width)),
            max(0.0, min(1.0, top / height)),
            max(0.0, min(1.0, (left + box_width) / width)),
            max(0.0, min(1.0, (top + box_height) / height)),
        ]
        if normalized_box[2] <= normalized_box[0] or normalized_box[3] <= normalized_box[1]:
            continue
        detections.append({
            "label": "person",
            "confidence": float(score),
            "bbox": normalized_box,
        })

    return detections, round(inference_ms, 3)
