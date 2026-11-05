#!/usr/bin/env python3
"""
FastSAM AI 服务 - TensorRT 高性能版
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

# TensorRT 相关
from FastSAMTrt.trt_loader import TrtModelNMS
from ultralytics.yolo.utils import ops

# 关闭多余日志
logging.getLogger("ultralytics").setLevel(logging.ERROR)

DEFAULT_IPC_ADDR = "ipc:///tmp/py_ai_fastsam.ipc"
DEFAULT_TRT_MODEL_PATH = "./weights/fast_sam_640.trt"
DEFAULT_INPUT_SIZE = 640

# TRT 后处理参数
TRT_CONF = 0.25
TRT_IOU = 0.7
TRT_AGNOSTIC_NMS = False

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
    """返回当前 GPU 显存占用 (MB) - 使用 nvidia-smi 级别统计"""
    if torch.cuda.is_available():
        # memory_reserved 包含 PyTorch 缓存 + TensorRT 等原生 CUDA 分配
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            return info.used / 1024 / 1024
        except:
            # fallback: 至少返回 PyTorch reserved
            return torch.cuda.memory_reserved() / 1024 / 1024
    return 0


# =========================
# TRT 预处理 & 后处理
# =========================
def trt_preprocess(img_origin, imgsz=640):
    """TensorRT 预处理：letterbox 缩放 + padding（简化版）"""
    h, w = img_origin.shape[:2]
    scale = min(imgsz / h, imgsz / w)
    nw = int(w * scale)
    nh = int(h * scale)
    
    # 居中 padding（与 YOLO letterbox 一致）
    inp = np.zeros((imgsz, imgsz, 3), dtype=np.uint8)
    top = (imgsz - nh) // 2
    left = (imgsz - nw) // 2
    
    # resize 并放置到中心
    resized = cv2.resize(img_origin, (nw, nh))
    inp[top:top+nh, left:left+nw, :] = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    
    # 转换为模型输入格式
    rgb = np.array([inp], dtype=np.float32) / 255.0
    tensor = np.transpose(rgb, (0, 3, 1, 2))
    
    # 返回 pad 信息用于后处理（简化）
    pad_info = {
        'orig_h': h, 'orig_w': w
    }
    return tensor, pad_info


def trt_postprocess(preds, img, pad_info, device, conf=0.25, iou=0.7, agnostic_nms=False):
    """
    TensorRT 后处理：NMS + GPU mask 生成（优化版）
    使用 process_mask_native 直接生成原图尺寸的 masks，避免中间 tensor
    返回原图尺寸的 masks (N, H, W) 和 boxes (N, 4)
    """
    detection_output = preds[0]  # (batch, 37, 8400)
    proto = preds[1]             # (batch, 32, 160, 160)
    
    # NMS
    p = ops.non_max_suppression(
        detection_output, conf, iou, agnostic_nms, max_det=100, nc=1
    )
    
    if not len(p[0]):
        return None, None
    
    pred = p[0].to(device)  # 移到 GPU
    proto_i = proto[0].to(device)  # (32, 160, 160) 移到 GPU
    
    orig_h, orig_w = pad_info['orig_h'], pad_info['orig_w']
    imgsz = img.shape[2]  # 640
    
    # ========== 先将 boxes 转换到原图坐标 ==========
    # scale_boxes 会自动处理 padding 和缩放
    pred[:, :4] = ops.scale_boxes((imgsz, imgsz), pred[:, :4], (orig_h, orig_w))
    
    # ========== 使用 process_mask_native 直接生成原图尺寸 mask ==========
    # 这样避免了创建 640x640 的中间 tensor，大幅减少显存占用
    masks = ops.process_mask_native(proto_i, pred[:, 6:], pred[:, :4], (orig_h, orig_w))
    
    boxes = pred[:, :4]  # 已经是原图坐标
    
    return masks, boxes


def render_masks_gpu(frame_bgr, masks, boxes, device, alpha=0.5, grid_size=64):
    """
    GPU 并行渲染 mask 颜色（优化版 - 减少颜色跳动）
    基于 box 中心位置的稳定哈希分配颜色
    masks: 已经是原图尺寸 (N, H, W)
    boxes: (N, 4) 原图坐标的 boxes
    
    grid_size=32 提供 1024 个颜色区域，减少颜色跳动
    """
    global COLOR_TABLE_GPU
    
    if COLOR_TABLE_GPU is None or COLOR_TABLE_GPU.device.type != device:
        COLOR_TABLE_GPU = torch.from_numpy(COLOR_TABLE_NP).to(device).float()
    
    h, w = frame_bgr.shape[:2]
    n_masks = masks.shape[0]
    
    if n_masks == 0:
        return frame_bgr
    
    # 限制 mask 数量
    if n_masks > 256:
        masks = masks[:256]
        boxes = boxes[:256]
        n_masks = 256
    
    # ========== 基于 box 中心 + 面积计算稳定的颜色索引 ==========
    cx = (boxes[:, 0] + boxes[:, 2]) * 0.5  # (N,)
    cy = (boxes[:, 1] + boxes[:, 3]) * 0.5  # (N,)
    area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])  # (N,) box 面积
    
    # 使用更细的网格，减少跳动（32x32 = 1024 个网格）
    gx = (cx * grid_size / w).long().clamp(0, grid_size - 1)
    gy = (cy * grid_size / h).long().clamp(0, grid_size - 1)
    
    # 加入面积信息，增加颜色稳定性
    # 面积相近的物体在相邻位置会有不同颜色
    area_idx = (area.sqrt() / 10).long().clamp(0, 7)  # 面积分 8 档
    
    # 混合位置和面积信息生成颜色索引
    # 使用质数混合避免规律性
    color_indices = ((gy * grid_size + gx) * 8 + area_idx) % 256 + 1
    color_indices = color_indices.view(-1, 1, 1)  # (N, 1, 1)
    
    # ========== GPU 并行渲染 ==========
    ann = (masks > 0.5).to(torch.int16)  # (N, H, W) int16
    index_map = (ann * color_indices.to(torch.int16)).max(dim=0).values  # (H, W)
    
    # 只在有 mask 的地方渲染
    covered = index_map > 0
    if not covered.any():
        return frame_bgr
    
    color_map = COLOR_TABLE_GPU[index_map[covered].long()]  # (num_covered, 3)
    
    # 转换 frame 到 GPU 并混合
    frame_gpu = torch.from_numpy(frame_bgr).to(device).float()
    frame_gpu[covered] = frame_gpu[covered] * (1 - alpha) + color_map * alpha
    
    result = frame_gpu.cpu().numpy().astype(np.uint8)
    
    return result


class FastSAMServer(BaseServer):
    def __init__(self):
        addr = os.getenv("FASTSAM_ZMQ_ADDR", DEFAULT_IPC_ADDR)
        super().__init__(addr)
    
    def serve(self):
        """优化版 serve：减少 poll 延迟，改善响应速度"""
        import zmq
        import multiprocessing as mp
        from base.server_base import WorkerPool
        
        ctx = zmq.Context()
        router = ctx.socket(zmq.ROUTER)
        try:
            router.bind(self.addr)
        except Exception:
            if self.addr.startswith("ipc://"):
                try:
                    os.unlink(self.addr.replace("ipc://", ""))
                except Exception:
                    pass
                router.bind(self.addr)
        
        out_q = mp.Queue()
        pool = WorkerPool(out_q, self.process_frame)
        poller = zmq.Poller()
        poller.register(router, zmq.POLLIN)
        
        pending_count = 0  # 队列中待处理的请求数
        
        while True:
            # 优化：减少 poll 超时到 1ms，提高响应速度
            events = dict(poller.poll(1))
            
            if router in events:
                frames = router.recv_multipart()
                if len(frames) < 2:
                    continue
                identity, payload = frames[0], frames[-1]
                try:
                    import json
                    import time
                    meta = json.loads(payload.decode("utf-8"))
                    # 添加服务器接收时间戳
                    meta["timestamp"] = time.time()
                except Exception:
                    router.send_multipart([identity, b"", b"ERR"])
                    continue
                
                key = self.select_worker_key(meta)
                w = pool.get(key)
                w.in_q.put((identity, meta))
                pending_count += 1
            
            # 优化：批量处理所有可用的结果，减少延迟
            processed = 0
            while not out_q.empty() and processed < 10:  # 最多一次处理 10 个结果
                try:
                    identity, res = out_q.get_nowait()
                    router.send_multipart([identity, b"", res])
                    pending_count = max(0, pending_count - 1)
                    processed += 1
                except Exception:
                    break
            
            # 监控队列积压（每 100 次循环打印一次）
            if pending_count > 5 and pending_count % 10 == 0:
                print(f"[FastSAMServer] Warning: {pending_count} requests pending in queue", flush=True)
    
    @staticmethod
    def init_model_context():
        print(f"[PID:{os.getpid()}] [FastSAM-TRT] CUDA: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"[PID:{os.getpid()}] [FastSAM-TRT] GPU: {torch.cuda.get_device_name(0)}")
        
        # 加载 TensorRT 模型
        model_path = os.getenv("FASTSAM_TRT_MODEL_PATH", DEFAULT_TRT_MODEL_PATH)
        input_size = int(os.getenv("FASTSAM_INPUT_SIZE", DEFAULT_INPUT_SIZE))
        script_dir = os.path.dirname(os.path.abspath(__file__))
        full_path = os.path.join(script_dir, model_path) if not os.path.isabs(model_path) else model_path
        
        print(f"[PID:{os.getpid()}] [FastSAM-TRT] Loading TRT model: {full_path}")
        model = TrtModelNMS(full_path, input_size)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # warm-up
        print(f"[PID:{os.getpid()}] [FastSAM-TRT] Warming up...")
        dummy = np.zeros((input_size, input_size, 3), dtype=np.uint8)
        dummy_inp, _ = trt_preprocess(dummy, input_size)
        for _ in range(3):
            _ = model.run(dummy_inp)
        
        torch.cuda.empty_cache()
        print(f"[PID:{os.getpid()}] [FastSAM-TRT] Ready, input_size={input_size}")
        
        return {"model": model, "device": device, "input_size": input_size}
    
    def process_frame(self, meta: dict, model_ctx: dict):
        import time as T
        t0 = T.time()
        mem0 = gpu_mem_mb()
        
        # 读取请求时间戳（用于计算端到端延迟）
        req_time = meta.get("timestamp", t0)
        
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
            t1 = T.time()
            
            model = model_ctx["model"]
            device = model_ctx["device"]
            input_size = model_ctx["input_size"]
            mem1 = gpu_mem_mb()
            
            # TRT 预处理
            inp, pad_info = trt_preprocess(frame, input_size)
            t_pre = T.time()
            
            # TRT 推理
            preds = model.run(inp)
            t2 = T.time()
            mem2 = gpu_mem_mb()
            
            # TRT 后处理（优化版：直接生成原图尺寸 mask，避免中间 tensor）
            detection_output = torch.from_numpy(preds[0])  # (1, 37, 8400)
            proto_masks = torch.from_numpy(preds[5])       # (1, 32, 160, 160)
            formatted_preds = [detection_output, proto_masks]
            
            masks, boxes = trt_postprocess(
                formatted_preds, inp, pad_info, device,
                conf=TRT_CONF, iou=TRT_IOU, agnostic_nms=TRT_AGNOSTIC_NMS
            )
            t3 = T.time()
            mem3 = gpu_mem_mb()
            
            # 获取 mask 数量
            n_masks = masks.shape[0] if masks is not None else 0
            
            # GPU 并行渲染（优化版）
            if n_masks > 0:
                result = render_masks_gpu(frame, masks, boxes, device, alpha=0.5)
            else:
                result = frame
            t4 = T.time()
            mem4 = gpu_mem_mb()
            
            # 清理 GPU 缓存
            del formatted_preds, detection_output, proto_masks
            if masks is not None:
                del masks, boxes
            torch.cuda.empty_cache()
            mem5 = gpu_mem_mb()
            
            # 写回
            flat = result.reshape(-1).tobytes()
            mm[:min(len(flat), shm_len)] = flat
            t5 = T.time()
            
            # 计算端到端延迟
            e2e_latency = (t5 - req_time) * 1000  # ms
            processing_time = (t5 - t0) * 1000     # ms
            
            print(f"[PID:{os.getpid()}] [FastSAM-TRT-OPT] masks={n_masks} | "
                  f"prep={t1-t0:.3f}s preproc={t_pre-t1:.3f}s infer={t2-t_pre:.3f}s post={t3-t2:.3f}s render={t4-t3:.3f}s write={t5-t4:.3f}s | "
                  f"process={processing_time:.0f}ms e2e={e2e_latency:.0f}ms | "
                  f"mem: base={mem0:.0f} pre={mem1:.0f} infer={mem2:.0f} post={mem3:.0f} render={mem4:.0f} clean={mem5:.0f}MB")
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
