import sys
import os
import time
import threading
from types import SimpleNamespace
from pathlib import Path

import cv2
import numpy as np
import torch
from sahi.models.ultralytics import UltralyticsDetectionModel
from sahi.predict import get_sliced_prediction

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT))

from base.server_base import BaseServer
from base.shm_utils import open_and_map, close_map


# 推理在后台线程执行，主视频路径复用最近检测框。默认使用一次完整
# YOLO 推理以降低四路并发开销；需要小目标召回率时可打开 SAHI。
SAHI_INTERVAL_SECONDS = float(os.getenv("DEEPSORT_SAHI_INTERVAL", "1.0"))
USE_SAHI = os.getenv("DEEPSORT_USE_SAHI", "false").strip().lower() in (
    "1", "true", "yes", "on"
)
SLICE_SIZE = int(os.getenv("DEEPSORT_SLICE_SIZE", "512"))
SLICE_OVERLAP = float(os.getenv("DEEPSORT_SLICE_OVERLAP", "0.15"))
CONFIDENCE_THRESHOLD = float(os.getenv("DEEPSORT_CONFIDENCE", "0.25"))
NMS_THRESHOLD = float(os.getenv("DEEPSORT_NMS", "0.45"))
CONTAINMENT_THRESHOLD = float(os.getenv("DEEPSORT_CONTAINMENT", "0.70"))


def _person_boxes(result):
    """Extract person boxes and apply a second NMS for overlapping slices."""
    boxes = []
    scores = []
    for prediction in result.object_prediction_list:
        category = prediction.category
        if (category.id != 0 and
                str(category.name).strip().lower() != "person"):
            continue
        score = float(prediction.score.value)
        if score < CONFIDENCE_THRESHOLD:
            continue
        x1, y1, x2, y2 = prediction.bbox.to_xyxy()
        if x2 <= x1 or y2 <= y1:
            continue
        boxes.append([int(x1), int(y1), int(x2 - x1), int(y2 - y1)])
        scores.append(score)

    if not boxes:
        return []

    # SAHI 已经做过合并，但切片边界仍可能留下一个大框和一个小框。
    # 先按置信度排序，再同时处理 IoU 和“较小框被包含”这两种重复情况。
    order = sorted(range(len(boxes)), key=lambda index: scores[index], reverse=True)
    selected = []
    for index in order:
        x, y, w, h = boxes[index]
        area = float(w * h)
        duplicate = False
        for kept_index in selected:
            kx, ky, kw, kh = boxes[kept_index]
            ix1, iy1 = max(x, kx), max(y, ky)
            ix2, iy2 = min(x + w, kx + kw), min(y + h, ky + kh)
            intersection = max(0, ix2 - ix1) * max(0, iy2 - iy1)
            if intersection <= 0:
                continue
            union = area + kw * kh - intersection
            iou = intersection / union if union else 0.0
            smaller_area = min(area, float(kw * kh))
            containment = intersection / smaller_area if smaller_area else 0.0
            if iou >= NMS_THRESHOLD or containment >= CONTAINMENT_THRESHOLD:
                duplicate = True
                break
        if not duplicate:
            selected.append(index)
    return [(boxes[index], scores[index]) for index in selected]


class DetectionServer(BaseServer):

    def __init__(self, create_server_socket=True):
        super().__init__()

    @staticmethod
    def init_model_context():
        # 与离线检测保持一致
        default_model_path = (
            ROOT / "deep_sort-master" / "detection" / "yolov5mu.pt"
        )
        # 可通过环境变量切换到微调后的 best.pt，无需再次改代码。
        model_path = Path(os.getenv("DEEPSORT_MODEL", str(default_model_path)))

        device = "cuda" if torch.cuda.is_available() else "cpu"

        print("[Detection] loading SAHI + YOLO:", model_path)
        print("[Detection] device:", device)

        model = UltralyticsDetectionModel(
            model_path=str(model_path),
            confidence_threshold=CONFIDENCE_THRESHOLD,
            device=device,
        )

        return {
            "sahi": model,
            "last_infer_time": 0.0,
            "cached_boxes": [],
            "infer_lock": threading.Lock(),
            "infer_active": False,
        }

    def select_worker_key(self, meta):
        # 每个摄像头使用独立 worker
        path = meta.get("path", "")
        shm_name = meta.get("shmName", "")

        return "detection:" + (
            path or shm_name or "default"
        )

    def process_frame(self, meta, model_ctx):
        shm_name = meta["shmName"]
        width = int(meta["width"])
        height = int(meta["height"])
        stride = int(meta.get("stride", width * 3))

        fd, mm, _ = open_and_map(shm_name)

        try:
            # 1. 将共享内存转换为 OpenCV 图像
            buf = np.frombuffer(
                mm,
                dtype=np.uint8,
                count=height * stride,
            )

            frame = (
                buf.reshape(height, stride)
                   [:, :width * 3]
                   .reshape(height, width, 3)
            )

            # 推理是最慢的步骤，不能在这里同步等待，否则 ai_stream 会丢掉
            # 后续视频帧并把算法流降到推理吞吐量。每个 worker 只运行一个
            # 后台推理任务，当前帧立即使用最近一次检测结果返回。
            now = time.monotonic()
            with model_ctx["infer_lock"]:
                infer_due = (
                    not model_ctx["infer_active"]
                    and now - model_ctx["last_infer_time"] >= SAHI_INTERVAL_SECONDS
                )
                if infer_due:
                    model_ctx["infer_active"] = True
                    model_ctx["last_infer_time"] = now
                    threading.Thread(
                        target=self._infer_background,
                        args=(frame.copy(), model_ctx),
                        daemon=True,
                    ).start()
                cached_boxes = list(model_ctx["cached_boxes"])

            # 每帧绘制最近一次检测结果，避免算法流因推理间隔而断流。
            for box, score in cached_boxes:
                x, y, box_width, box_height = box
                x1, y1 = x, y
                x2, y2 = x + box_width, y + box_height

                x1 = max(0, min(x1, width - 1))
                y1 = max(0, min(y1, height - 1))
                x2 = max(0, min(x2, width - 1))
                y2 = max(0, min(y2, height - 1))

                cv2.rectangle(
                    frame,
                    (x1, y1),
                    (x2, y2),
                    (0, 255, 255),
                    2,
                )

                cv2.putText(
                    frame,
                    "person %.2f" % float(score),
                    (x1, max(20, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 255),
                    2,
                )

        finally:
            # 关闭 Python 对共享内存的映射
            close_map(fd, mm)

    @staticmethod
    def _infer_background(frame, model_ctx):
        """Run one inference without holding up the video ACK path."""
        try:
            detection_model = model_ctx["sahi"]
            if USE_SAHI:
                result = get_sliced_prediction(
                    frame,
                    detection_model,
                    slice_height=SLICE_SIZE,
                    slice_width=SLICE_SIZE,
                    overlap_height_ratio=SLICE_OVERLAP,
                    overlap_width_ratio=SLICE_OVERLAP,
                    perform_standard_pred=False,
                    verbose=0,
                )
                boxes = _person_boxes(result)
            else:
                detection_model.perform_inference(frame)
                detection_model.convert_original_predictions()
                boxes = _person_boxes(SimpleNamespace(
                    object_prediction_list=detection_model.object_prediction_list
                ))
            with model_ctx["infer_lock"]:
                model_ctx["cached_boxes"] = boxes
        except Exception as exc:
            print(f"[Detection] background inference failed: {exc}", flush=True)
        finally:
            with model_ctx["infer_lock"]:
                model_ctx["infer_active"] = False


if __name__ == "__main__":
    print("[DetectionServer] starting")

    server = DetectionServer()
    server.serve()
