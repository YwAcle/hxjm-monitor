#!/usr/bin/env python3
"""
BoxMOT 行人跟踪 AI 服务
"""

import os
import sys
import cv2
import logging
import numpy as np
import torch
import torchvision
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from base.server_base import BaseServer
from base.shm_utils import open_and_map, close_map
from boxmot import create_tracker, get_tracker_config

# 关闭多余日志
logging.getLogger("ultralytics").setLevel(logging.ERROR)

DEFAULT_IPC_ADDR = "ipc:///tmp/py_ai_boxmot.ipc"
DEFAULT_TRACKER_TYPE = "hybridsort"
DEFAULT_REID_WEIGHTS = "./weights/osnet_x0_25_msmt17.pt"
DEFAULT_CONFIDENCE_THRESHOLD = 0.4


def gpu_mem_mb():
    """返回当前 GPU 显存占用 (MB)"""
    if torch.cuda.is_available():
        return torch.cuda.memory_allocated() / 1024 / 1024
    return 0


def create_optimized_tracker(tracker_type, reid_weights, device):
    """创建优化参数的跟踪器"""
    reid_path = Path(reid_weights)
    
    # BoxMOT 需要 device=0 而不是 device="cuda"
    if device == "cuda" or device == torch.device("cuda"):
        device = 0
    
    if tracker_type == 'hybridsort':
        return create_tracker(
            tracker_type='hybridsort',
            tracker_config=None,
            reid_weights=reid_path,
            device=device,
            half=False,
            per_class=False,
        )
    elif tracker_type == 'deepocsort':
        tracker_conf = get_tracker_config('deepocsort')
        return create_tracker(
            tracker_type='deepocsort',
            tracker_config=tracker_conf,
            reid_weights=reid_path,
            device=device,
            half=False,
            per_class=False,
        )
    elif tracker_type == 'boosttrack':
        return create_tracker(
            tracker_type='boosttrack',
            tracker_config=None,
            reid_weights=reid_path,
            device=device,
            half=False,
            per_class=False,
        )
    elif tracker_type == 'strongsort':
        return create_tracker(
            tracker_type='strongsort',
            tracker_config=None,
            reid_weights=reid_path,
            device=device,
            half=False,
        )
    elif tracker_type == 'bytetrack':
        return create_tracker(
            tracker_type='bytetrack',
            tracker_config=None,
            reid_weights=reid_path,
            device=device,
            half=False,
        )
    else:  # botsort
        from boxmot import BotSort
        return BotSort(
            reid_weights=reid_path,
            device=device,
            half=False,
            track_high_thresh=0.5,
            track_low_thresh=0.05,
            new_track_thresh=0.8,
            track_buffer=50,
            match_thresh=0.85,
            proximity_thresh=0.6,
            appearance_thresh=0.2,
            cmc_method='ecc',
            with_reid=True,
            max_age=50,
            min_hits=2,
            iou_threshold=0.2,
        )


def apply_nms(dets, nms_thresh=0.4):
    """应用NMS去除重复检测"""
    if len(dets) == 0:
        return dets
    
    boxes = dets[:, :4]
    scores = dets[:, 4]
    
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        
        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter)
        
        inds = np.where(iou <= nms_thresh)[0]
        order = order[inds + 1]
    
    return dets[keep]


def id_to_color(track_id):
    """ID到颜色"""
    np.random.seed(int(track_id))
    return tuple(np.random.randint(0, 255, 3).tolist())


def draw_tracks(frame, tracks):
    """绘制跟踪结果"""
    if len(tracks) == 0:
        return frame
    
    for track in tracks:
        x1, y1, x2, y2 = track[:4].astype('int')
        track_id = int(track[4])
        conf = track[5] if len(track) > 5 else 1.0
        
        color = id_to_color(track_id)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        
        label = f'ID:{track_id} {conf:.2f}'
        label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(frame, (x1, y1 - label_size[1] - 10), 
                     (x1 + label_size[0], y1), color, -1)
        cv2.putText(frame, label, (x1, y1 - 5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    
    return frame


class BoxMOTServer(BaseServer):
    def __init__(self):
        addr = os.getenv("BOXMOT_ZMQ_ADDR", DEFAULT_IPC_ADDR)
        super().__init__(addr)
    
    @staticmethod
    def init_model_context():
        print(f"[PID:{os.getpid()}] [BoxMOT] CUDA: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"[PID:{os.getpid()}] [BoxMOT] GPU: {torch.cuda.get_device_name(0)}")
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # 加载检测模型
        print(f"[PID:{os.getpid()}] [BoxMOT] Loading detector (FasterRCNN)...")
        detector = torchvision.models.detection.fasterrcnn_resnet50_fpn(pretrained=True)
        detector.eval().to(device)
        
        # 加载跟踪器
        tracker_type = os.getenv("BOXMOT_TRACKER_TYPE", DEFAULT_TRACKER_TYPE)
        reid_weights = os.getenv("BOXMOT_REID_WEIGHTS", DEFAULT_REID_WEIGHTS)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        reid_path = os.path.join(script_dir, reid_weights) if not os.path.isabs(reid_weights) else reid_weights
        
        print(f"[PID:{os.getpid()}] [BoxMOT] Loading tracker: {tracker_type}, reid: {reid_path}")
        tracker = create_optimized_tracker(tracker_type, reid_path, device)
        
        conf_thresh = float(os.getenv("BOXMOT_CONFIDENCE_THRESHOLD", DEFAULT_CONFIDENCE_THRESHOLD))
        
        # warm-up
        print(f"[PID:{os.getpid()}] [BoxMOT] Warming up...")
        dummy = np.zeros((480, 640, 3), dtype=np.uint8)
        dummy_tensor = torchvision.transforms.functional.to_tensor(dummy).unsqueeze(0).to(device)
        with torch.no_grad():
            _ = detector(dummy_tensor)
        
        torch.cuda.empty_cache()
        print(f"[PID:{os.getpid()}] [BoxMOT] Ready, tracker={tracker_type}")
        
        return {
            "detector": detector,
            "tracker": tracker,
            "device": device,
            "conf_thresh": conf_thresh
        }
    
    def process_frame(self, meta: dict, model_ctx: dict):
        import time as T
        t0 = T.time()
        mem0 = gpu_mem_mb()
        
        shm_name = meta.get("shmName", "")
        shm_len = int(meta.get("shmLen", 0))
        width = int(meta.get("width", 0))
        height = int(meta.get("height", 0))
        stride = int(meta.get("stride", width * 3))
        
        # fd, mm, map_len = open_and_map(shm_name)
        
        # try:
        #     if shm_len <= 0 or shm_len > map_len:
        #         shm_len = map_len
            
        #     # 读取帧
        #     buf = np.frombuffer(mm, dtype=np.uint8, count=height * stride)
        #     frame = buf.reshape((height, stride))[:, :width * 3].reshape((height, width, 3)).copy()
        #     t1 = T.time()
            
        #     detector = model_ctx["detector"]
        #     tracker = model_ctx["tracker"]
        #     device = model_ctx["device"]
        #     conf_thresh = model_ctx["conf_thresh"]
        #     mem1 = gpu_mem_mb()
            
        #     # 检测
        #     frame_tensor = torchvision.transforms.functional.to_tensor(frame).unsqueeze(0).to(device)
        #     with torch.no_grad():
        #         results = detector(frame_tensor)[0]
        #     t2 = T.time()
        #     mem2 = gpu_mem_mb()
            
        #     # 提取行人检测 (label=1 为行人)
        #     dets = []
        #     for i, (label, score) in enumerate(zip(results['labels'], results['scores'])):
        #         if label == 1 and score >= conf_thresh:
        #             x1, y1, x2, y2 = results['boxes'][i].cpu().numpy()
        #             dets.append([x1, y1, x2, y2, score.item(), 0])
        #     dets = np.array(dets) if len(dets) > 0 else np.empty((0, 6))
            
        #     # 应用NMS
        #     if len(dets) > 0:
        #         dets = apply_nms(dets, nms_thresh=0.4)
        #     n_dets = len(dets)
        #     t3 = T.time()
            
        #     # 跟踪更新
        #     tracks = tracker.update(dets, frame)
        #     n_tracks = len(tracks)
        #     t4 = T.time()
        #     mem3 = gpu_mem_mb()
            
        #     # 绘制跟踪结果
        #     result = draw_tracks(frame, tracks)
        #     t5 = T.time()
            
        #     # 清理 GPU 缓存
        #     del frame_tensor, results
        #     torch.cuda.empty_cache()
        #     mem4 = gpu_mem_mb()
            
            # 写回
            # flat = result.reshape(-1).tobytes()
            # mm[:min(len(flat), shm_len)] = flat
            # t6 = T.time()
            
            # print(f"[PID:{os.getpid()}] [BoxMOT] dets={n_dets} tracks={n_tracks} | "
            #       f"prep={t1-t0:.3f}s detect={t2-t1:.3f}s nms={t3-t2:.3f}s track={t4-t3:.3f}s draw={t5-t4:.3f}s write={t6-t5:.3f}s total={t6-t0:.3f}s | "
            #       f"mem: base={mem0:.0f} pre={mem1:.0f} detect={mem2:.0f} track={mem3:.0f} clean={mem4:.0f}MB")
        # finally:
        #     close_map(fd, mm)
    
    def select_worker_key(self, meta: dict) -> str:
        shm_name = meta.get("shmName", "")
        return f"boxmot:{shm_name}" if shm_name else "boxmot:default"


def main():
    print("[BoxMOTServer] Starting...", flush=True)
    
    # 预加载模型验证（可选）
    if os.getenv("BOXMOT_PRELOAD", "1") == "1":
        print("[BoxMOTServer] Preloading model...", flush=True)
        _ = BoxMOTServer.init_model_context()
        print("[BoxMOTServer] Preload done.", flush=True)
        torch.cuda.empty_cache()
    
    server = BoxMOTServer()
    print(f"[BoxMOTServer] Binding to {server.addr}", flush=True)
    server.serve()


if __name__ == "__main__":
    main()
