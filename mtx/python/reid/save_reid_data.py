#!/usr/bin/env python3
"""
Save ReID Data Server - base64 模式
接收 base64 图片，进行 YOLO 检测 + SORT 跟踪，保存行人图片到轨迹目录
"""
import os
import sys
import time
import base64
import cv2
import torch
import numpy as np
from pathlib import Path
from datetime import datetime

# YOLO
from ultralytics import YOLO

# SORT / HybridSORT
from boxmot import create_tracker

# 添加模块路径 (上级目录)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from base.server_base import BaseServer

# 默认 IPC 地址
DEFAULT_IPC_ADDR = "ipc:///tmp/py_ai_save_reid.ipc"
# 数据保存目录 (当前目录下的 save 文件夹)
SAVE_DIR = os.path.join(os.path.dirname(__file__), "save")


class DummyDB:
    """假的数据库对象，满足 BaseServer Worker 的检查，但不执行任何操作"""
    
    async def initialize(self):
        """空的初始化方法，不执行任何操作"""
        pass
    
    async def close(self):
        """空的关闭方法，不执行任何操作"""
        pass


class SaveReidDataServer(BaseServer):
    """保存 ReID 数据服务器 - base64 模式"""
    
    def __init__(self, create_server_socket: bool = True):
        """
        初始化 SaveReidDataServer
        
        Args:
            create_server_socket: 是否创建服务器 socket（子进程设为 False）
        """
        if create_server_socket:
            # 使用独立的环境变量或默认地址
            addr = os.getenv("SAVE_REID_ZMQ_ADDR", DEFAULT_IPC_ADDR)
            super().__init__(addr)
        else:
            # 子进程模式：不调用 super().__init__，避免创建 socket
            self.addr = None
        
        # 添加假的 db 对象，满足 BaseServer Worker 的检查，但不执行任何数据库操作
        self.db = DummyDB()
        
        # 创建保存目录
        os.makedirs(SAVE_DIR, exist_ok=True)
        print(f"[INIT] 数据保存目录: {SAVE_DIR}", flush=True)
        
        # 轨迹管理
        self.track_save_dirs = {}  # track_id -> 保存目录路径
        self.track_frame_count = {}  # track_id -> 已保存的帧数
        self.track_last_seen = {}  # track_id -> 最后出现的时间
        self.track_camera_id = {}  # track_id -> camera_id（用于区分摄像头）
        self.track_timeout = 2.0  # 轨迹超时时间（秒）
        
        if create_server_socket:
            print("[INIT] SaveReidDataServer 初始化完成", flush=True)
        else:
            print("[INIT] SaveReidDataServer (Worker进程) 初始化完成", flush=True)
    
    def letterbox(self, img, new_size=640):
        """YOLO 输入预处理"""
        h, w = img.shape[:2]
        r = min(new_size / h, new_size / w)
        nh, nw = int(h * r), int(w * r)

        resized = cv2.resize(img, (nw, nh))
        padw = (new_size - nw) // 2
        padh = (new_size - nh) // 2

        out = np.full((new_size, new_size, 3), 114, dtype=np.uint8)
        out[padh:padh + nh, padw:padw + nw] = resized

        return out, r, (padw, padh)
    
    def save_person_crop(self, track_id: int, frame: np.ndarray, bbox: tuple, camera_id: str = ""):
        """保存行人裁剪图片到对应轨迹目录
        
        Args:
            track_id: 轨迹ID
            frame: 原始帧
            bbox: 边界框坐标 (x1, y1, x2, y2)
            camera_id: 摄像头标识符（path 或 shmName，用于区分摄像头）
        """
        x1, y1, x2, y2 = bbox
        
        # 确保坐标在有效范围内
        h, w = frame.shape[:2]
        x1 = max(0, int(x1))
        y1 = max(0, int(y1))
        x2 = min(w, int(x2))
        y2 = min(h, int(y2))
        
        if x2 <= x1 or y2 <= y1:
            return
        
        # 裁剪行人区域
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return
        
        # 创建轨迹保存目录（包含摄像头标识符和日期文件夹）
        if track_id not in self.track_save_dirs:
            # 获取当前日期（格式：YYYY-MM-DD）
            date_str = datetime.now().strftime("%Y-%m-%d")
            # 创建日期文件夹路径
            date_dir = os.path.join(SAVE_DIR, date_str)
            
            # 清理 camera_id，移除特殊字符，只保留字母数字和下划线
            safe_camera_id = "".join(c if c.isalnum() or c in ('_', '-', '/') else '_' for c in camera_id) if camera_id else "unknown"
            # 替换路径分隔符为下划线
            safe_camera_id = safe_camera_id.replace('/', '_').replace('\\', '_')
            # 目录名格式：日期/{camera_id}_track_{track_id}
            track_dir = os.path.join(date_dir, f"{safe_camera_id}_track_{track_id}")
            os.makedirs(track_dir, exist_ok=True)
            self.track_save_dirs[track_id] = track_dir
            self.track_frame_count[track_id] = 0
            self.track_camera_id[track_id] = camera_id
            
            # 在目录中创建 info.txt 文件，记录摄像头标识符和创建时间
            info_file = os.path.join(track_dir, "info.txt")
            with open(info_file, "w", encoding="utf-8") as f:
                f.write(f"camera_id: {camera_id}\n")
                f.write(f"track_id: {track_id}\n")
                f.write(f"created_at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            
            print(f"[保存] 创建轨迹目录: {track_dir} (camera_id: {camera_id})", flush=True)
        
        track_dir = self.track_save_dirs[track_id]
        
        # 生成文件名（帧序号，6位数字，便于排序）
        frame_num = self.track_frame_count[track_id]
        filename = f"{frame_num:06d}.jpg"
        filepath = os.path.join(track_dir, filename)
        
        # 保存图片（JPEG质量95，保证图片质量）
        try:
            cv2.imwrite(filepath, crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
            self.track_frame_count[track_id] += 1
            # 首次保存或每保存100帧时输出提示
            if frame_num == 0 or (frame_num + 1) % 100 == 0:
                print(f"[保存成功] track_id={track_id}, 已保存 {self.track_frame_count[track_id]} 帧到 {track_dir}", flush=True)
        except Exception as e:
            print(f"[保存失败] track_id={track_id}, filepath={filepath}, error={e}", flush=True)
    
    def process_frame(self, meta: dict, model_ctx: dict = None):
        """处理单帧：base64 解码 -> YOLO检测 -> SORT跟踪 -> 保存行人图片"""
        
        total_start = time.perf_counter()
        current_time = time.time()
        
        # 获取标识符（用于区分摄像头）
        # base64 模式使用 path，shm 模式使用 shmName（作为备用）
        camera_id = meta.get("path", "") or meta.get("shmName", "") or "unknown"
        
        # 诊断：记录接收到的帧信息（每100帧记录一次，避免刷屏）
        if not hasattr(self, '_frame_counter'):
            self._frame_counter = 0
        self._frame_counter += 1
        if self._frame_counter % 100 == 1:
            print(f"[DIAG] 已接收 {self._frame_counter} 帧，camera_id={camera_id}, meta_keys={list(meta.keys())}", flush=True)
        
        # ============================================================
        #     1. base64 解码图片
        # ============================================================
        width = int(meta.get("width", 0))
        height = int(meta.get("height", 0))
        stride = int(meta.get("stride", width * 3))
        channels = int(meta.get("channels", 3))
        b64 = meta.get("base64", "")
        
        if not b64:
            # 每100帧才输出一次警告，避免刷屏
            if self._frame_counter % 100 == 1:
                print(f"[WARN] 未收到 base64 数据 (frame {self._frame_counter})", flush=True)
            return
        
        try:
            raw = base64.b64decode(b64)
            
            # 尝试作为 JPEG/PNG 图片解码（优先）
            try:
                nparr = np.frombuffer(raw, dtype=np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if frame is not None:
                    # JPEG/PNG 解码成功，frame 已经是 BGR 格式
                    height, width = frame.shape[:2]
                    print(f"[DEBUG] 使用 JPEG/PNG 解码，尺寸: {width}x{height}", flush=True)
                else:
                    raise ValueError("cv2.imdecode 返回 None")
            except:
                # 如果 JPEG/PNG 解码失败，尝试作为原始 RGB 数据解析
                row_bytes = width * channels
                buf_len = len(raw)
                
                # 按行重组数据
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
                
                # 转换为 numpy 数组 (BGR 格式，OpenCV 使用)
                frame = np.frombuffer(rgb, dtype=np.uint8).reshape(height, width, channels)
                # 如果是 RGB，转换为 BGR
                if channels == 3:
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                print(f"[DEBUG] 使用原始 RGB 数据解析，尺寸: {width}x{height}", flush=True)
        except Exception as e:
            print(f"[ERROR] base64 解码失败: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return
        
        # ============================================================
        #     2. YOLO 行人检测
        # ============================================================
        t0 = time.perf_counter()
        
        yolo = model_ctx["yolo"]
        img_resize, r, (padw, padh) = self.letterbox(frame, 640)
        
        img = torch.from_numpy(img_resize).to(model_ctx["device"])
        img = img.permute(2, 0, 1).float() / 255.0
        img = img.unsqueeze(0)
        
        with torch.no_grad():
            results = yolo(img, conf=0.4, iou=0.5, classes=[0], verbose=False)
        
        boxes = results[0].boxes
        dets = np.empty((0, 6))
        
        detect_count = 0
        if boxes is not None and len(boxes) > 0:
            xyxy = boxes.xyxy.cpu().numpy()
            conf = boxes.conf.cpu().numpy()
            cls = boxes.cls.cpu().numpy()
            
            detect_count = len(xyxy)
            
            # 反变换
            xyxy[:, [0, 2]] -= padw
            xyxy[:, [1, 3]] -= padh
            xyxy /= r
            
            xyxy[:, 0] = np.clip(xyxy[:, 0], 0, width - 1)
            xyxy[:, 1] = np.clip(xyxy[:, 1], 0, height - 1)
            xyxy[:, 2] = np.clip(xyxy[:, 2], 0, width - 1)
            xyxy[:, 3] = np.clip(xyxy[:, 3], 0, height - 1)
            
            dets = np.concatenate([xyxy, conf.reshape(-1, 1), cls.reshape(-1, 1)], axis=1)
        
        t_yolo = (time.perf_counter() - t0) * 1000
        
        # ============================================================
        #     3. SORT 跟踪
        # ============================================================
        t0 = time.perf_counter()
        tracker = model_ctx["tracker"]
        tracks = tracker.update(dets, frame)
        t_sort = (time.perf_counter() - t0) * 1000
        track_count = len(tracks)
        
        # ============================================================
        #     4. 保存每个轨迹的行人图片
        # ============================================================
        active_tracks = set()
        
        for t in tracks:
            t = t.astype(int)
            x1, y1, x2, y2, track_id = t[:5]
            
            # 更新最后出现时间
            self.track_last_seen[track_id] = current_time
            active_tracks.add(track_id)
            
            # 保存行人裁剪图片（传递摄像头标识符）
            self.save_person_crop(track_id, frame, (x1, y1, x2, y2), camera_id)
        
        # 诊断：如果没有检测到行人，记录日志（每100帧一次）
        if detect_count == 0 and self._frame_counter % 100 == 1:
            print(f"[DIAG] 帧 {self._frame_counter}: 未检测到行人 (YOLO conf=0.4, classes=[0])", flush=True)
        elif track_count == 0 and detect_count > 0:
            print(f"[DIAG] 帧 {self._frame_counter}: 检测到 {detect_count} 个行人，但未成功跟踪", flush=True)
        
        # ============================================================
        #     5. 清理超时的轨迹
        # ============================================================
        expired_tracks = []
        for track_id, last_seen in self.track_last_seen.items():
            if track_id not in active_tracks:
                if current_time - last_seen > self.track_timeout:
                    expired_tracks.append(track_id)
        
        for track_id in expired_tracks:
            self.track_last_seen.pop(track_id, None)
            if track_id in self.track_save_dirs:
                saved_count = self.track_frame_count.get(track_id, 0)
                track_dir = self.track_save_dirs[track_id]
                camera_id = self.track_camera_id.get(track_id, "unknown")
                print(f"[轨迹结束] track_id={track_id}, camera_id={camera_id}, 已保存 {saved_count} 帧, 目录: {track_dir}", flush=True)
                self.track_save_dirs.pop(track_id, None)
                self.track_frame_count.pop(track_id, None)
                self.track_camera_id.pop(track_id, None)
        
        # ============================================================
        #     6. 日志（base64 模式不需要写回）
        # ============================================================
        total_cost = (time.perf_counter() - total_start) * 1000
        
        if detect_count > 0:
            log_perf = (
                f"[Perf] total={total_cost:.2f}ms | "
                f"yolo={t_yolo:.2f}ms | sort={t_sort:.2f}ms | "
                f"det={detect_count} | track={track_count}"
            )
            print(log_perf, flush=True)
        else:
            # 即使没有检测到目标，也输出日志（每100帧一次，避免刷屏）
            if int(time.time() * 10) % 100 == 0:  # 约每10秒输出一次
                print(f"[Perf] total={total_cost:.2f}ms | det=0 | track=0 (no detection)", flush=True)
    
    @staticmethod
    def init_model_context(
            yolo_weights="/home/guest/Documents/hxjm-monitor/mtx/python/models/yolov8n.pt",
            reid_weights="/home/guest/Documents/hxjm-monitor/mtx/python/models/osnet_x0_25_msmt17.pt",
            device=""
    ):
        """初始化模型上下文"""
        print("[SaveReidDataServer] [Worker] 开始初始化模型上下文...", flush=True)
        ctx = {}
        
        device = torch.device(device if device else ("cuda:0" if torch.cuda.is_available() else "cpu"))
        ctx["device"] = device
        print(f"[SaveReidDataServer] [Worker] 使用设备: {device}", flush=True)
        
        print("[SaveReidDataServer] [Worker] Loading YOLOv8 ...", flush=True)
        yolo = YOLO(yolo_weights)
        yolo.to(device)
        ctx["yolo"] = yolo
        print("[SaveReidDataServer] [Worker] YOLOv8 加载完成", flush=True)
        
        print("[SaveReidDataServer] [Worker] Loading HybridSORT ...", flush=True)
        tracker = create_tracker(
            tracker_type="hybridsort",
            tracker_config=None,
            reid_weights=Path(reid_weights),
            device=device,
            half=False,
            per_class=False,
        )
        ctx["tracker"] = tracker
        print("[SaveReidDataServer] [Worker] HybridSORT 加载完成", flush=True)
        
        print("[SaveReidDataServer] [Worker] 模型上下文初始化完成", flush=True)
        return ctx
    
    def select_worker_key(self, meta: dict) -> str:
        """根据 stream_id 分配不同的 worker"""
        # 优先使用 path（base64 模式），如果没有则使用 shmName（shm 模式）
        camera_id = meta.get("path", "") or meta.get("shmName", "")
        if camera_id:
            return f"save_reid:{camera_id}"
        return "save_reid:default"


def main():
    print("[SaveReidDataServer] Starting YOLO + SORT tracking service (base64 mode)...", flush=True)
    server = SaveReidDataServer()
    print(f"[SaveReidDataServer] Listening on {server.addr}", flush=True)
    print(f"[SaveReidDataServer] Saving person crops to: {SAVE_DIR}", flush=True)
    print(f"[SaveReidDataServer] 保存条件：", flush=True)
    print(f"  - 必须接收到包含 base64 数据的消息", flush=True)
    print(f"  - YOLO 检测到行人 (conf>=0.4, class=0)", flush=True)
    print(f"  - SORT 跟踪器分配了 track_id", flush=True)
    print(f"[SaveReidDataServer] 如果未保存数据，请检查：", flush=True)
    print(f"  1. 主程序是否向 {server.addr} 发送数据", flush=True)
    print(f"  2. 视频流中是否有行人出现", flush=True)
    print(f"  3. 查看日志中的 [DIAG] 和 [WARN] 信息", flush=True)
    try:
        server.serve()
    except KeyboardInterrupt:
        print("\n[SaveReidDataServer] Shutting down...", flush=True)


if __name__ == "__main__":
    main()
