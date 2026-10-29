#!/usr/bin/env python3
"""
FastSAM AI 服务 - pytorch 实现
"""

import os
import sys
import cv2
import logging
import colorsys
import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from base.server_base import BaseServer
from base.shm_utils import open_and_map, close_map

# 导入 FastSAM
try:
    from fastsam import FastSAM, FastSAMPrompt
except ImportError:
    from fastsam.fastsam import FastSAM, FastSAMPrompt

# 关闭多余日志
logging.getLogger("ultralytics").setLevel(logging.ERROR)

DEFAULT_IPC_ADDR = "ipc:///tmp/py_ai_fastsam.ipc"
DEFAULT_MODEL_PATH = "./weights/FastSAM-x.pt"

# =========================
# 预生成颜色表（GPU tensor，256种颜色）
# =========================
def _generate_color_table_gpu(n=256):
    """生成 GPU 上的 BGR 颜色表 (n+1, 3)，索引 0 是背景（不用）"""
    colors = np.zeros((n + 1, 3), dtype=np.uint8)
    for i in range(1, n + 1):
        h = ((i - 1) * 0.618033988749895 + 0.1 * ((i - 1) % 3)) % 1.0
        r, g, b = colorsys.hsv_to_rgb(h, 0.85, 0.95)
        colors[i] = [int(b * 255), int(g * 255), int(r * 255)]  # BGR
    return colors

COLOR_TABLE_NP = _generate_color_table_gpu(256)
COLOR_TABLE_GPU = None  # 延迟初始化到 GPU


def gpu_mem_mb():
    """返回当前 GPU 显存占用 (MB)"""
    if torch.cuda.is_available():
        return torch.cuda.memory_allocated() / 1024 / 1024
    return 0


def render_masks_gpu(frame_bgr, ann, device, alpha=0.5, grid_size=8):
    """
    GPU 并行渲染 mask 颜色，基于位置分配颜色以保证前后帧一致性
    """
    global COLOR_TABLE_GPU
    
    if COLOR_TABLE_GPU is None or COLOR_TABLE_GPU.device.type != device:
        COLOR_TABLE_GPU = torch.from_numpy(COLOR_TABLE_NP).to(device).float()
    
    h, w = frame_bgr.shape[:2]
    n_masks = min(ann.shape[0], 256)
    
    if n_masks == 0:
        return frame_bgr
    
    # 确保 ann 在 GPU
    if not isinstance(ann, torch.Tensor):
        ann = torch.from_numpy(ann).to(device)
    elif ann.device.type != device:
        ann = ann.to(device)
    
    ann = (ann[:n_masks] > 0.5)  # (N, H, W) bool
    
    # ========== 基于位置计算颜色索引 ==========
    # 为每个 mask 计算中心位置，映射到 grid_size x grid_size 网格
    # 创建坐标网格
    y_coords = torch.arange(h, device=device, dtype=torch.float32).view(1, h, 1)
    x_coords = torch.arange(w, device=device, dtype=torch.float32).view(1, 1, w)
    
    # 计算每个 mask 的中心 (N,)
    mask_float = ann.float()  # (N, H, W)
    mask_sum = mask_float.sum(dim=(1, 2)).clamp(min=1)  # (N,) 避免除零
    
    cy = (mask_float * y_coords).sum(dim=(1, 2)) / mask_sum  # (N,)
    cx = (mask_float * x_coords).sum(dim=(1, 2)) / mask_sum  # (N,)
    
    # 映射到网格
    gy = (cy * grid_size / h).long().clamp(0, grid_size - 1)  # (N,)
    gx = (cx * grid_size / w).long().clamp(0, grid_size - 1)  # (N,)
    
    # 颜色索引 = gy * grid_size + gx + 1 (避开 0 背景)
    color_indices = (gy * grid_size + gx + 1).view(-1, 1, 1)  # (N, 1, 1)
    
    del y_coords, x_coords, mask_float, mask_sum, cy, cx, gy, gx
    
    # ========== GPU 并行渲染 ==========
    # 每个像素取最后一个覆盖它的 mask 的颜色索引
    index_map = (ann.to(torch.int16) * color_indices.to(torch.int16)).max(dim=0).values  # (H, W)
    del ann, color_indices
    
    color_map = COLOR_TABLE_GPU[index_map.long()]  # (H, W, 3)
    covered = index_map > 0
    del index_map
    
    frame_gpu = torch.from_numpy(frame_bgr).to(device).float()
    frame_gpu[covered] = frame_gpu[covered] * (1 - alpha) + color_map[covered] * alpha
    del color_map, covered
    
    result = frame_gpu.cpu().numpy().astype(np.uint8)
    del frame_gpu
    
    return result


class FastSAMServer(BaseServer):
    def __init__(self):
        addr = os.getenv("FASTSAM_ZMQ_ADDR", DEFAULT_IPC_ADDR)
        super().__init__(addr)
    
    @staticmethod
    def init_model_context():
        print(f"[PID:{os.getpid()}] [FastSAM] CUDA: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"[PID:{os.getpid()}] [FastSAM] GPU: {torch.cuda.get_device_name(0)}")
        
        model_path = os.getenv("FASTSAM_MODEL_PATH", DEFAULT_MODEL_PATH)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        full_path = os.path.join(script_dir, model_path) if not os.path.isabs(model_path) else model_path
        
        model = FastSAM(full_path)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # warm-up
        print(f"[PID:{os.getpid()}] [FastSAM] Warming up...")
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        for _ in range(3):
            _ = model(dummy, device=device, imgsz=640, verbose=False)
        
        torch.cuda.empty_cache()
        print(f"[PID:{os.getpid()}] [FastSAM] Ready, model: {full_path}")
        
        return {"model": model, "device": device}
    
    def process_frame(self, meta: dict, model_ctx: dict):
        import time as T
        t0 = T.time()
        mem0 = gpu_mem_mb()
        
        shm_name = meta.get("shmName", "")
        shm_len = int(meta.get("shmLen", 0))
        width = int(meta.get("width", 0))
        height = int(meta.get("height", 0))
        stride = int(meta.get("stride", width * 3))
        
        fd, mm, map_len = open_and_map(shm_name)
        
        try:
            if shm_len <= 0 or shm_len > map_len:
                shm_len = map_len
            
            # 读取帧
            buf = np.frombuffer(mm, dtype=np.uint8, count=height * stride)
            frame = buf.reshape((height, stride))[:, :width * 3].reshape((height, width, 3)).copy()
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            t1 = T.time()
            
            model = model_ctx["model"]
            device = model_ctx["device"]
            mem1 = gpu_mem_mb()
            
            # 推理（retina_masks=True 保证 mask 尺寸与原图一致）
            everything_results = model(
                frame_rgb,
                device=device,
                retina_masks=True,
                imgsz=640,
                conf=0.4,
                iou=0.9,
                verbose=False
            )
            t2 = T.time()
            mem2 = gpu_mem_mb()
            
            # 获取 masks
            if everything_results[0].masks is not None:
                ann = everything_results[0].masks.data  # GPU tensor (N, H, W)
                n_masks = ann.shape[0]
            else:
                ann = None
                n_masks = 0
            t3 = T.time()
            mem3 = gpu_mem_mb()
            
            # GPU 并行渲染
            if ann is not None and n_masks > 0:
                result = render_masks_gpu(frame, ann, device, alpha=0.5)
            else:
                result = frame
            t4 = T.time()
            mem4 = gpu_mem_mb()
            
            # 清理 GPU 缓存
            del everything_results
            if ann is not None:
                del ann
            torch.cuda.empty_cache()
            mem5 = gpu_mem_mb()
            
            # 写回
            flat = result.reshape(-1).tobytes()
            mm[:min(len(flat), shm_len)] = flat
            t5 = T.time()
            
            print(f"[PID:{os.getpid()}] [FastSAM] masks={n_masks} | "
                  f"prep={t1-t0:.3f}s model={t2-t1:.3f}s get={t3-t2:.3f}s render={t4-t3:.3f}s write={t5-t4:.3f}s total={t5-t0:.3f}s | "
                  f"mem: base={mem0:.0f} pre={mem1:.0f} model={mem2:.0f} get={mem3:.0f} render={mem4:.0f} clean={mem5:.0f}MB")
        finally:
            close_map(fd, mm)
    
    def select_worker_key(self, meta: dict) -> str:
        shm_name = meta.get("shmName", "")
        return f"fastsam:{shm_name}" if shm_name else "fastsam:default"


def main():
    print("[FastSAMServer] Starting...", flush=True)
    server = FastSAMServer()
    print(f"[FastSAMServer] Binding to {server.addr}", flush=True)
    server.serve()


if __name__ == "__main__":
    main()
