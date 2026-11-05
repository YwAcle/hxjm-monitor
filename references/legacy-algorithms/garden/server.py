#!/usr/bin/env python3
"""
Garden AI 服务 - 独立的 Garden 处理服务
每个任务独立运行，拥有独立的 IPC 通道
"""
import os
import sys
import time
import base64

# 添加模块路径 (上级目录)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from base.server_base import BaseServer

# 默认 IPC 地址
DEFAULT_IPC_ADDR = "ipc:///tmp/py_ai_garden.ipc"
# 数据保存目录 (当前目录下的 data 文件夹)
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


class GardenServer(BaseServer):
    """Garden 专用服务器"""
    
    def __init__(self):
        # 使用独立的环境变量或默认地址
        addr = os.getenv("GARDEN_ZMQ_ADDR", DEFAULT_IPC_ADDR)
        super().__init__(addr)
    
    def process_frame(self, meta: dict, model_ctx: dict = None):
        """Garden 处理：保存帧到文件"""
        width = int(meta.get("width", 0))
        height = int(meta.get("height", 0))
        stride = int(meta.get("stride", width * 3))
        channels = int(meta.get("channels", 3))
        b64 = meta.get("base64", "")
        
        raw = base64.b64decode(b64) if b64 else b""
        row_bytes = width * channels
        buf_len = len(raw)
        
        rows = []
        for y in range(height):
            base = y * stride
            end = base + row_bytes
            if base >= buf_len:
                rows.append(b"\x00" * row_bytes)
                continue
            if end > buf_len:
                end = buf_len
            chunk = raw[base:end]
            if len(chunk) < row_bytes:
                chunk = chunk + (b"\x00" * (row_bytes - len(chunk)))
            rows.append(chunk)
        
        rgb = b"".join(rows)
        expected = width * height * channels
        if len(rgb) > expected:
            rgb = rgb[:expected]
        
        os.makedirs(DATA_DIR, exist_ok=True)
        name = time.strftime("%Y%m%d_%H%M%S") + ".ppm"
        path = os.path.join(DATA_DIR, name)
        header = f"P6\n{width} {height}\n255\n".encode("ascii")
        with open(path, "wb") as f:
            f.write(header)
            f.write(rgb)
            f.flush()
    
    def select_worker_key(self, meta: dict) -> str:
        """Garden 使用默认 worker key"""
        return "garden:default"


def main():
    print("[GardenServer] Starting Garden AI service...", flush=True)
    server = GardenServer()
    print(f"[GardenServer] Binding to {server.addr}", flush=True)
    print(f"[GardenServer] Waiting for requests...", flush=True)
    server.serve()


if __name__ == "__main__":
    main()
