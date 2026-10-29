#!/usr/bin/env python3

import os
import sys
import cv2
import time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from base.server_base import BaseServer
from base.shm_utils import open_and_map, close_map

DEFAULT_IPC_ADDR = "ipc:///tmp/py_ai_sam3.ipc"
DEFAULT_MODEL_PATH = "./model/sam3/sam3.pt"

# 固定颜色表，避免每帧随机颜色导致跳动
MASK_COLORS = np.array([
    [255, 0, 0],      # 红
    [0, 255, 0],      # 绿
    [0, 0, 255],      # 蓝
    [255, 255, 0],    # 黄
    [255, 0, 255],    # 品红
    [0, 255, 255],    # 青
    [255, 128, 0],    # 橙
    [128, 0, 255],    # 紫
    [0, 255, 128],    # 春绿
    [255, 0, 128],    # 玫红
    [128, 255, 0],    # 黄绿
    [0, 128, 255],    # 天蓝
], dtype=np.uint8)


class Sam3Server(BaseServer):
    def __init__(self):
        addr = os.getenv("SAM3_ZMQ_ADDR", DEFAULT_IPC_ADDR)
        super().__init__(addr)

    @staticmethod
    def init_model_context():
        import torch
        print(f"[PID:{os.getpid()}] [Sam3Server] CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"[PID:{os.getpid()}] [Sam3Server] GPU: {torch.cuda.get_device_name(0)}")
        
        from ultralytics.models.sam.predict import SAM3SemanticPredictor
        
        bpe_path = os.path.join(
            os.path.dirname(__file__),
            "assets", "bpe_simple_vocab_16e6.txt.gz"
        )
        
        # 模型路径从环境变量获取，默认本地路径
        model_path = os.getenv("SAM3_MODEL_PATH", DEFAULT_MODEL_PATH)
        
        overrides = dict(
            conf=0.25,
            task="segment",
            mode="predict",
            model=model_path,
            half=True,  # FP16 加速
        )
        predictor = SAM3SemanticPredictor(overrides=overrides, bpe_path=bpe_path)
        
        print(f"[PID:{os.getpid()}] [Sam3Server] Model: {model_path}")
        return {"predictor": predictor}

    def process_frame(self, meta: dict, model_ctx: dict):
        print(f"[PID:{os.getpid()}] start time: {time.time()}")
        shm_name = meta.get("shmName", "")
        shm_len = int(meta.get("shmLen", 0))
        width = int(meta.get("width", 0))
        height = int(meta.get("height", 0))
        stride = int(meta.get("stride", width * 3))

        fd, mm, map_len = open_and_map(shm_name)
        try:
            if shm_len <= 0 or shm_len > map_len:
                shm_len = map_len

            buf = np.frombuffer(mm, dtype=np.uint8, count=height * stride)
            frame = buf.reshape((height, stride))[:, : width * 3]
            frame = frame.reshape((height, width, 3)).copy()

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            predictor = model_ctx["predictor"]
            predictor.set_image(frame_rgb)
            results = predictor(text=["object"])
            
            if results and len(results) > 0 and results[0].masks is not None:
                masks = results[0].masks.data.cpu().numpy()
                for i, mask in enumerate(masks):
                    color = MASK_COLORS[i % len(MASK_COLORS)]
                    frame[mask > 0] = (frame[mask > 0] * 0.3 + color * 0.7).astype(np.uint8)
            else:
                print(f"[PID:{os.getpid()}] no detection, end time: {time.time()}")
                return

            flat = frame.reshape(-1).tobytes()
            mm[: min(len(flat), shm_len)] = flat
            print(f"[PID:{os.getpid()}] end time: {time.time()}")
        finally:
            close_map(fd, mm)

    def select_worker_key(self, meta: dict) -> str:
        shm_name = meta.get("shmName", "")
        if shm_name:
            return f"sam3:{shm_name}"
        return "sam3:default"


def main():
    print("[Sam3Server] Starting SAM3 AI service...", flush=True)
    server = Sam3Server()
    print(f"[Sam3Server] Binding to {server.addr}", flush=True)
    print(f"[Sam3Server] Waiting for requests...", flush=True)
    server.serve()


if __name__ == "__main__":
    main()