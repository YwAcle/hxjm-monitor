#!/usr/bin/env python3

import os
import sys
import cv2
import time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from base.server_base import BaseServer
from base.shm_utils import open_and_map, close_map

DEFAULT_IPC_ADDR = "ipc:///tmp/py_ai_fire.ipc"
from ultralytics import YOLO


class FireServer(BaseServer):
    def __init__(self):
        addr = os.getenv("FIRE_ZMQ_ADDR", DEFAULT_IPC_ADDR)
        super().__init__(addr)
        # self.model = YOLO("/home/guest/Documents/hxjm-monitor/mtx/python/fire/best.pt")

    @staticmethod
    def init_model_context():
        # model_path = "/home/guest/Documents/hxjm-monitor/mtx/python/models/yolov8n.pt"
        model_path = "/home/guest/Documents/hxjm-monitor/mtx/python/fire/best.pt"
        model = YOLO(model_path)
        return {"predictor": model}

    def process_frame(self, meta: dict, model_ctx: dict):
        # print(f"[PID:{os.getpid()}] start time: {time.time()}")
        """
           读取共享内存 → YOLO 检测 → 绘制 → 写回共享内存
        """
        yolo_fire_model = model_ctx["predictor"]
        shm_name = meta.get("shmName", "")
        shm_len = int(meta.get("shmLen", 0))
        width = int(meta.get("width", 0))
        height = int(meta.get("height", 0))
        stride = int(meta.get("stride", width * 3))
        # print(shm_name,shm_len,width,height,stride)
        fd, mm, map_len = open_and_map(shm_name)

        try:
            if shm_len <= 0 or shm_len > map_len:
                print(f"[WARN] shm_len({shm_len}) invalid, using map_len({map_len})")
                shm_len = map_len

            # ----------------------------
            # 1. 读取共享内存帧
            # ----------------------------
            try:
                buf = np.frombuffer(mm, dtype=np.uint8, count=height * stride)
                frame = buf.reshape((height, stride))[:, :width * 3]
                frame = frame.reshape((height, width, 3))
            except Exception as e:
                print(f"[ERROR] Failed to decode frame from shared memory: {e}")
                print(f" height={height}, width={width}, stride={stride}, shm_len={shm_len}")
                return  # 不处理该帧，但不中断主循环

            # ----------------------------
            # 2. YOLO 推理
            # ----------------------------
            try:
                results = yolo_fire_model(frame, conf=0.5, verbose=False)
                dets = results[0].boxes
                print(f"[INFO] YOLO 检测到 {len(dets)} 个目标")
            except Exception as e:
                print(f"[ERROR] YOLO inference failed: {e}")
                return

            # ----------------------------
            # 3. 绘制检测框
            # ----------------------------
            try:
                if dets is not None and len(dets) > 0:

                    xyxy = dets.xyxy.cpu().numpy()
                    confs = dets.conf.cpu().numpy()
                    cls_ids = dets.cls.cpu().numpy()

                    names = yolo_fire_model.model.names  # YOLO 类别名称字典

                    for i, box in enumerate(xyxy):
                        x1, y1, x2, y2 = box.astype(int)
                        cls_id = int(cls_ids[i])
                        conf = float(confs[i])

                        # 获取类别名
                        cls_name = names.get(cls_id, str(cls_id))

                        color = (0, 255, 0)

                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                        cv2.putText(frame,
                                    f"{cls_name} {conf:.2f}",
                                    (x1, y1 - 5),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            except Exception as e:
                print(f"[ERROR] Failed to draw YOLO results: {e}")

            # ----------------------------
            # 4. 写回共享内存（按照 stride）
            # ----------------------------
            try:
                for y in range(height):
                    row = frame[y].tobytes()

                    start = y * stride
                    end = start + width * 3
                    if end > shm_len:
                        print(f"[WARN] Write exceeds shared memory: y={y}, end={end}, shm_len={shm_len}")
                        break

                    mm[start:end] = row
                    # print(f"[PID:{os.getpid()}] end time: {time.time()}")
            except Exception as e:
                print(f"[ERROR] Failed to write back to shared memory: {e}")

        except Exception as e:
            print(f"[FATAL] Unexpected processing error: {e}")

        finally:
            close_map(fd, mm)

    def select_worker_key(self, meta: dict) -> str:
        shm_name = meta.get("shmName", "")
        if shm_name:
            return f"Fire:{shm_name}"
        return "Fire:default"


def main():
    print("[FireServer] Starting Fire AI service...", flush=True)
    server = FireServer()
    print(f"[FireServer] Binding to {server.addr}", flush=True)
    print(f"[FireServer] Waiting for requests...", flush=True)
    server.serve()


if __name__ == "__main__":
    main()