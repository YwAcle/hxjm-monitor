#!/usr/bin/env python3
"""
Reid AI 服务 - 独立的 ReID 处理服务
每个任务独立运行，拥有独立的 IPC 通道
"""
import os
import sys
import time
import cv2
import torch
import logging
from pathlib import Path
from datetime import datetime

# from models.model_manager import model_manager
from typing import List, Dict, Optional, Union, Tuple
import numpy as np
# np.float = float
# np.int = int
# np.bool = bool
import base64
from algorithms.reid.person_detect_yolo8 import PersonDetectYOLO8
from algorithms.reid.my_yolo8 import YOLODetector
from sklearn.metrics.pairwise import cosine_similarity
from ultralytics import YOLO
from datetime import datetime
from PIL import Image
import torchreid
# ===strong SORT 的依赖====
from yolov7.models.experimental import attempt_load
from yolov7.utils.general import non_max_suppression, scale_coords, xyxy2xywh
from yolov7.utils.torch_utils import time_synchronized
from strong_sort.strong_sort import StrongSORT
from strong_sort.utils.parser import get_config
# ----线程池----
import threading
from collections import deque
# 配置日志
logger = logging.getLogger(__name__)
# 检查Fast-ReID是否可用
FAST_REID_ROOT = os.path.join('./', 'models', 'fast-reid')
FAST_REID_AVAILABLE = os.path.exists(FAST_REID_ROOT)

# 添加模块路径 (上级目录)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from base.server_base import BaseServer
from base.shm_utils import open_and_map, close_map

# 默认 IPC 地址
DEFAULT_IPC_ADDR = "ipc:///tmp/py_ai_boxmot.ipc"
REID_SLEEP_MS = 100
from ultralytics import YOLO
from boxmot import create_tracker

import torchreid
from sklearn.metrics.pairwise import cosine_similarity

# ===========================================================
#                 ReidServer（HybridSORT + BatchReID）
# ===========================================================
class ReidServer(BaseServer):

    def __init__(self):
        addr = os.getenv("REID_ZMQ_ADDR", DEFAULT_IPC_ADDR)
        super().__init__(addr)
        # ========== 日志目录初始化 ==========
        os.makedirs("./log", exist_ok=True)
        self.log_path = "./log/reid_log.txt"

        # 清空日志并写入当天日期
        with open(self.log_path, "w", encoding="utf-8") as f:
            f.write("====== ReID Tracking Log ======\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d')}\n")
            f.write("================================\n\n")

    def write_log(self, text: str):
        """安全追加写日志"""
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception as e:
            print(f"[WARN] Failed to write log: {e}")
    # ===========================================================
    #               初始化 YOLO + HybridSORT + ReID
    # ===========================================================
    @staticmethod
    def init_model_context(
            yolo_weights="/home/guest/Documents/hxjm-monitor/mtx/python/models/yolov8n.pt",
            reid_weights="/home/guest/Documents/hxjm-monitor/mtx/python/models/osnet_x0_25_msmt17.pt",
            device=""
    ):

        ctx = {}

        # ----------------------------
        # 选择设备
        # ----------------------------
        device = torch.device(device if device else ("cuda:0" if torch.cuda.is_available() else "cpu"))
        ctx["device"] = device

        # ----------------------------
        # 加载 YOLOv8
        # ----------------------------
        print("[INIT] Loading YOLOv8...")
        yolo = YOLO(yolo_weights)
        yolo.to(device)
        ctx["yolo"] = yolo

        # ----------------------------
        # HybridSORT（最强 ID 稳定性）
        # ----------------------------
        print("[INIT] Loading HybridSORT...")

        tracker = create_tracker(
            tracker_type="hybridsort",
            tracker_config=None,
            reid_weights=Path(reid_weights),
            device=device,
            half=False,
            per_class=False,
        )
        ctx["tracker"] = tracker

        # ----------------------------
        # ReID 特征模型（OSNet）
        # ----------------------------
        print("[INIT] Loading OSNet ReID model...")

        reid_model = torchreid.models.build_model(
            name='osnet_x0_25',
            num_classes=1000,
            pretrained=True
        )
        reid_model.to(device).eval()
        ctx["reid_model"] = reid_model

        # ReID transform
        _, transform = torchreid.data.transforms.build_transforms(
            height=256, width=128, is_train=False
        )
        ctx["reid_transform"] = transform

        # ----------------------------
        # 加载目标图片特征（你的目标）
        # ----------------------------
        target_img = "/home/guest/Documents/hxjm-monitor/mtx/python/reid/data/zjh1.png"
        ctx["target_feat"] = ReidServer.extract_feature_single(
            reid_model, transform, target_img, device
        )

        print("[INIT] Model context initialized successfully.\n")
        return ctx

    # ===========================================================
    #       单张图片提取特征（路径输入）
    # ===========================================================
    @staticmethod
    def extract_feature_single(model, transform, img_path, device):
        img = cv2.imread(img_path)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(img)

        tensor = transform(pil).unsqueeze(0).to(device)
        with torch.no_grad():
            feat = model(tensor).detach().cpu().numpy()

        feat = feat / np.linalg.norm(feat)
        return feat.reshape(1, -1)

    # ===========================================================
    #         批量多行人 ReID 特征提取（关键）
    # ===========================================================
    @staticmethod
    def extract_features_batch(model, transform, crops, device):
        """
        输入：
            crops  = [numpy(HWC), numpy(HWC), ...]
        输出：
            feats      = numpy(N, D)
            valid_idx  = 对应有效 crop 的下标
        """
        batch_tensors = []
        valid_idx = []

        for i, crop in enumerate(crops):
            if crop is None or crop.size == 0:
                continue

            try:
                rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                pil = Image.fromarray(rgb)

                tensor = transform(pil).unsqueeze(0)  # shape (1,3,H,W)
                batch_tensors.append(tensor)
                valid_idx.append(i)

            except Exception:
                continue

        if len(batch_tensors) == 0:
            return None, []

        batch = torch.cat(batch_tensors, dim=0).to(device)

        with torch.no_grad():
            feats = model(batch).detach().cpu().numpy()

        feats = feats / np.linalg.norm(feats, axis=1, keepdims=True)

        return feats, valid_idx

    # ===========================================================
    #                 YOLO Letterbox
    # ===========================================================
    def letterbox(self, img, new_shape=640, color=(114, 114, 114)):
        h, w = img.shape[:2]
        if isinstance(new_shape, int):
            new_shape = (new_shape, new_shape)

        r = min(new_shape[0] / h, new_shape[1] / w)
        new_unpad = (int(w * r), int(h * r))
        resized = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)

        dw = new_shape[1] - new_unpad[0]
        dh = new_shape[0] - new_unpad[1]
        top, bottom = dh // 2, dh - dh // 2
        left, right = dw // 2, dw - dw // 2

        padded = cv2.copyMakeBorder(resized, top, bottom, left, right,
                                    cv2.BORDER_CONSTANT, value=color)

        return padded, r, (left, top)
    @staticmethod
    def _id_to_color(track_id):
        """ID到颜色"""
        np.random.seed(int(track_id))
        return tuple(np.random.randint(0, 255, 3).tolist())
    # ===========================================================
    #            主流程（共享内存 → YOLO → SORT → ReID → 写回）
    # ===========================================================
    def process_frame(self, meta, model_ctx):

        total_start = time.perf_counter()

        # ==========================================
        # 1. 共享内存读取
        # ==========================================
        shm_name = meta["shmName"]
        shm_len = int(meta["shmLen"])
        width = int(meta["width"])
        height = int(meta["height"])
        stride = int(meta.get("stride", width * 3))

        fd, mm, _ = open_and_map(shm_name)

        try:
            buf = np.frombuffer(mm, dtype=np.uint8, count=height * stride)
            frame = buf.reshape((height, stride))[:, :width * 3].reshape(height, width, 3)
        except Exception as e:
            print(f"[ERROR] Shared memory read failed: {e}")
            close_map(fd, mm)
            return

        # ==========================================
        # 2. YOLOv8 检测
        # ==========================================
        t0 = time.perf_counter()

        yolo = model_ctx["yolo"]
        device = model_ctx["device"]

        img_resize, r, (padw, padh) = self.letterbox(frame, 640)
        img = torch.from_numpy(img_resize).to(device)
        img = img.permute(2, 0, 1).float() / 255.0
        img = img.unsqueeze(0)

        with torch.no_grad():
            # results = yolo(img, conf=0.4, iou=0.5, verbose=False) # 全类别
            results = yolo(img, conf=0.4, iou=0.5, classes=[0], verbose=False)

        boxes = results[0].boxes
        dets = np.empty((0, 6))
        detect_count = 0

        if boxes is not None and len(boxes) > 0:
            xyxy = boxes.xyxy.detach().cpu().numpy()
            conf = boxes.conf.detach().cpu().numpy()
            cls = boxes.cls.detach().cpu().numpy()
            detect_count = len(xyxy)

            # --- 反变换 ---
            xyxy[:, [0, 2]] -= padw
            xyxy[:, [1, 3]] -= padh
            xyxy /= r

            xyxy[:, 0] = np.clip(xyxy[:, 0], 0, width - 1)
            xyxy[:, 1] = np.clip(xyxy[:, 1], 0, height - 1)
            xyxy[:, 2] = np.clip(xyxy[:, 2], 0, width - 1)
            xyxy[:, 3] = np.clip(xyxy[:, 3], 0, height - 1)

            dets = np.concatenate([xyxy, conf.reshape(-1, 1), cls.reshape(-1, 1)], axis=1)

        t_yolo = (time.perf_counter() - t0) * 1000

        # -------- YOLO 日志 --------
        print(f"[YOLO] det_count={detect_count}", flush=True)
        if detect_count > 0:
            for i in range(detect_count):
                x1, y1, x2, y2 = xyxy[i]
                print(f"  det[{i}] box=({x1:.1f},{y1:.1f},{x2:.1f},{y2:.1f}) "
                      f"conf={conf[i]:.2f} cls={int(cls[i])}", flush=True)
            log_text = f"[DETECT] count={detect_count}"
            self.write_log(log_text)

            # 写每个检测框
            for i in range(detect_count):
                x1, y1, x2, y2 = xyxy[i]
                cls_id = int(cls[i])
                log_box = (
                    f"  det[{i}] box=({x1:.1f},{y1:.1f},{x2:.1f},{y2:.1f}) "
                    f"conf={conf[i]:.2f} cls={cls_id}"
                )
                self.write_log(log_box)

        # ==========================================
        # 3. HybridSORT 跟踪
        # ==========================================
        t0 = time.perf_counter()
        tracker = model_ctx["tracker"]
        tracks = tracker.update(dets, frame)
        track_count = len(tracks)
        t_sort = (time.perf_counter() - t0) * 1000

        # ------- 跟踪日志 --------
        print(f"[TRACK] track_count={track_count}", flush=True)
        for i, t in enumerate(tracks):
            t = t.astype(int)
            x1, y1, x2, y2, tid = t[:5]
            print(f"  track[{i}] ID={tid} box=({x1},{y1},{x2},{y2})", flush=True)

        # ==========================================
        # 4. 批量 ReID 特征提取
        # ==========================================
        reid_model = model_ctx["reid_model"]
        transform = model_ctx["reid_transform"]
        target_feat = model_ctx["target_feat"]

        crops = []
        coords = []

        for t in tracks:
            t = t.astype(int)
            x1, y1, x2, y2, tid = t[:5]
            crop = frame[y1:y2, x1:x2]
            crops.append(crop)
            coords.append((x1, y1, x2, y2, tid))

        # --- 批量特征提取 ---
        t0 = time.perf_counter()
        feats, valid_idx = self.extract_features_batch(
            reid_model, transform, crops, device
        )
        t_reid = (time.perf_counter() - t0) * 1000

        # ==========================================
        # 5. ReID 相似度判定 + 绘制框
        # ==========================================
        reid_hit_count = 0

        if feats is not None:
            sims = cosine_similarity(feats, target_feat)  # (N,1)

            for j, idx in enumerate(valid_idx):
                sim = sims[j][0]
                x1, y1, x2, y2, track_id = coords[idx]

                if sim > 0.75:
                    color = (0, 0, 255)
                    reid_hit_count += 1
                    print(f"[REID] HIT track_id={track_id} sim={sim:.3f}", flush=True)

                    # 保存裁剪
                    # save_dir = "./reid_cords"
                    # os.makedirs(save_dir, exist_ok=True)
                    # ts = int(time.time() * 1000)
                    # cv2.imwrite(f"{save_dir}/tid{track_id}_sim{sim:.2f}_{ts}.jpg",
                    #             crops[idx])
                else:
                    color = (50, 255, 50)
                    print(f"[REID] track_id={track_id} sim={sim:.3f}", flush=True)

                # 绘制
                color = self._id_to_color(track_id)
                label = f"ID:{track_id} SIM:{sim:.2f}"
                # 边界框
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                # 文字
                cv2.putText(frame, label, (x1, y1 - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                # cv2.putText(frame, label, (x1, y1 - 5),
                #             cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        # ==========================================
        # 6. 写回共享内存
        # ==========================================
        for y in range(height):
            mm[y * stride: y * stride + width * 3] = frame[y].tobytes()

        close_map(fd, mm)

        # ==========================================
        # 7. 时间 & 汇总日志
        # ==========================================
        total_cost = (time.perf_counter() - total_start) * 1000

        log_perf = (
            f"[Perf] total={total_cost:.2f}ms | "
            f"yolo={t_yolo:.2f}ms | sort={t_sort:.2f}ms | reid={t_reid:.2f}ms | "
            f"det={detect_count} | track={track_count} | reid_hit={reid_hit_count}"
        )

        # 控制台打印
        print(log_perf, flush=True)

        # 写入日志文件
        self.write_log(log_perf)


    # ===========================================================
    # worker key 用于多摄像头区分
    def select_worker_key(self, meta: dict) -> str:
        shm_name = meta.get("shmName","")
        return f"reid:{shm_name}" if shm_name else "reid:default"


# ===========================================================
def main():
    print("[ReidServer] Starting HybridSORT ReID service...")
    server = ReidServer()
    print(f"[ReidServer] Listening on {server.addr}")
    server.serve()


if __name__ == "__main__":
    main()