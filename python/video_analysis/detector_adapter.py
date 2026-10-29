"""Reuse the existing YOLO model and person filtering, without its video server."""
import os
import sys
import time
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

from .config import CACHE_ROOT, PYTHON_ROOT


@lru_cache(maxsize=1)
def initialize_detector():
    model_path = Path(os.getenv("DEEPSORT_MODEL", str(PYTHON_ROOT / "deep_sort-master/detection/yolov5mu.pt")))
    if not model_path.is_file() or model_path.stat().st_size == 0:
        raise FileNotFoundError(f"Local model weights missing: {model_path}")
    os.environ["YOLO_AUTOINSTALL"] = "false"
    os.environ["YOLO_OFFLINE"] = "true"
    for variable, directory in (
        ("YOLO_CONFIG_DIR", "ultralytics"), ("MPLCONFIGDIR", "matplotlib"),
        ("CUDA_CACHE_PATH", "cuda"), ("TORCH_HOME", "torch"), ("XDG_CACHE_HOME", "cache"),
    ):
        path = CACHE_ROOT / directory
        path.mkdir(parents=True, exist_ok=True)
        os.environ[variable] = str(path)
    if str(PYTHON_ROOT) not in sys.path:
        sys.path.insert(0, str(PYTHON_ROOT))
    from deepsort import server
    return server, server.DetectionServer.init_model_context()


def detect_people(frame):
    import cv2
    server, context = initialize_detector()
    height, width = frame.shape[:2]
    # OpenCV capture is BGR; SAHI's ndarray API expects RGB in both modes.
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    model = context["sahi"]
    started = time.perf_counter()
    if server.USE_SAHI:
        result = server.get_sliced_prediction(
            rgb, model, slice_height=server.SLICE_SIZE, slice_width=server.SLICE_SIZE,
            overlap_height_ratio=server.SLICE_OVERLAP, overlap_width_ratio=server.SLICE_OVERLAP,
            perform_standard_pred=False, verbose=0,
        )
    else:
        model.perform_inference(rgb)
        model.convert_original_predictions(full_shape=[height, width])
        result = SimpleNamespace(object_prediction_list=model.object_prediction_list)
    boxes = server._person_boxes(result)
    inference_ms = round((time.perf_counter() - started) * 1000, 3)
    detections = []
    for (x, y, w, h), score in boxes:
        bbox = [max(0.0, min(1.0, value)) for value in (x / width, y / height, (x + w) / width, (y + h) / height)]
        if bbox[2] > bbox[0] and bbox[3] > bbox[1]:
            detections.append({"label": "person", "confidence": float(score), "bbox": bbox})
    return detections, inference_ms
