import os
import sys
import time
import base64
import glob
import threading
import queue
from pathlib import Path

# OpenCV：用于图像解码/裁剪/保存
try:
    import cv2
except ModuleNotFoundError as e:
    raise ModuleNotFoundError(
        "Missing dependency: cv2. Install opencv-python (e.g. use the same environment as python/reid where opencv-python is listed in requirements)."
    ) from e
import numpy as np
import torch

from ultralytics import YOLO
from boxmot import create_tracker

# 引入项目内部 BaseServer（ZMQ ROUTER + worker pool 框架）
_PY_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
if _PY_ROOT not in sys.path:
    sys.path.insert(0, _PY_ROOT)
from base.server_base import BaseServer

# 默认 IPC 地址（不配环境变量时使用）
DEFAULT_IPC_ADDR = "ipc:///tmp/py_ai_face_sr.ipc"

# 输入/输出目录：按 track 维度落盘
SERVICE_DIR = os.path.dirname(__file__)
INPUT_DIR = os.path.join(SERVICE_DIR, "person_save_input")
OUTPUT_DIR = os.path.join(SERVICE_DIR, "person_save_output")


class DummyDB:
    # BaseServer worker 会尝试初始化 db；这里用空实现占位
    async def initialize(self):
        pass

    async def close(self):
        pass


class FaceSRServer(BaseServer):
    def __init__(self, create_server_socket: bool = True):
        """服务初始化

        - 主进程：创建 ZMQ socket 并监听
        - worker 进程：create_server_socket=False，不创建 socket，只做推理/保存
        """
        if create_server_socket:
            # 允许通过环境变量覆写监听地址
            addr = os.getenv("FACE_SR_ZMQ_ADDR", DEFAULT_IPC_ADDR)
            super().__init__(addr)
        else:
            self.addr = None

        # 按 BaseServer 框架约定提供 db 对象
        self.db = DummyDB()

        # 创建输入/输出目录
        os.makedirs(INPUT_DIR, exist_ok=True)
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        # track 管理：track_id -> 目录/计数/最后出现时间/摄像头标识
        self.track_save_dirs = {}
        self.track_frame_count = {}
        self.track_last_seen = {}
        self.track_camera_id = {}
        # 超时阈值：轨迹在该时间内未出现，则认为结束并触发超分处理
        self.track_timeout = float(os.getenv("FACE_SR_TRACK_TIMEOUT", "2.0"))
        # 避免同一个 track 重复触发 SR 线程
        self.processing_tracks = set()
        # GFPGANer 内部有状态（face_helper），用锁避免多线程同时 enhance
        self._gfpgan_lock = threading.Lock()
        
        # 异步处理队列
        self.sr_queue = queue.Queue()
        
        # 调试用：统计收到的请求数，避免日志刷屏
        self._recv_count = 0

    def _ensure_sr_thread(self, restorer):
        """确保 SR 消费线程已启动"""
        if hasattr(self, "_sr_thread") and self._sr_thread.is_alive():
            return
        
        # 启动消费线程
        self._sr_thread = threading.Thread(
            target=self._sr_worker_loop,
            args=(restorer,),
            daemon=True
        )
        self._sr_thread.start()
        print("[FaceSR] Async SR worker thread started.", flush=True)

    def _sr_worker_loop(self, restorer):
        """后台消费线程：从队列取任务并执行超分"""
        while True:
            try:
                task = self.sr_queue.get()
                track_dir = task["track_dir"]
                img_path = task["img_path"]
                out_dir = task["out_dir"]
                
                try:
                    self._process_single_image_sr(track_dir, img_path, out_dir, restorer)
                except Exception as e:
                    print(f"[FaceSR] Worker failed to process {img_path}: {e}", flush=True)
                finally:
                    self.sr_queue.task_done()
            except Exception as e:
                print(f"[FaceSR] Worker loop error: {e}", flush=True)
                time.sleep(1)

    def _process_single_image_sr(self, track_dir, img_path, out_dir, restorer):
        """处理单张图片的超分任务"""
        img_name = os.path.basename(img_path)
        basename, ext = os.path.splitext(img_name)

        # 1. 准备目录
        # 仅在第一次处理该 track 时创建 info.txt，或者每次覆盖都行（开销不大）
        if not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
            # 写入 info.txt
            info_file = os.path.join(out_dir, "info.txt")
            with open(info_file, "w", encoding="utf-8") as f:
                f.write(f"source: {track_dir}\n")
                f.write(f"first_processed_at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

        os.makedirs(os.path.join(out_dir, 'cropped_faces'), exist_ok=True)
        os.makedirs(os.path.join(out_dir, 'restored_faces'), exist_ok=True)
        os.makedirs(os.path.join(out_dir, 'cmp'), exist_ok=True)
        os.makedirs(os.path.join(out_dir, 'restored_imgs'), exist_ok=True)

        # 2. 检查是否已处理 (去重)
        if os.path.exists(os.path.join(out_dir, 'restored_imgs', img_name)):
            return

        img = cv2.imread(img_path, cv2.IMREAD_COLOR)
        if img is None:
            return

        # 3. 调用 GFPGAN
        # GFPGANer 有内部状态，串行调用更安全
        with self._gfpgan_lock:
            cropped_faces, restored_faces, restored_img = restorer.enhance(
                img,
                has_aligned=False,
                only_center_face=False,
                paste_back=True,
                weight=0.5,
            )

        # 4. 保存结果
        # (1) 保存从原图裁剪出的人脸 & 修复后的人脸 & 对比图
        for idx, (cropped_face, restored_face) in enumerate(zip(cropped_faces, restored_faces)):
            # save cropped face
            save_crop_path = os.path.join(out_dir, 'cropped_faces', f'{basename}_{idx:02d}.png')
            cv2.imwrite(save_crop_path, cropped_face)

            # save restored face
            save_restore_path = os.path.join(out_dir, 'restored_faces', f'{basename}_{idx:02d}.png')
            cv2.imwrite(save_restore_path, restored_face)

            # save comparison image
            h1, w1 = cropped_face.shape[:2]
            h2, w2 = restored_face.shape[:2]
            if h1 != h2 or w1 != w2:
                restored_face = cv2.resize(restored_face, (w1, h1))
            
            cmp_img = np.concatenate((cropped_face, restored_face), axis=1)
            cv2.imwrite(os.path.join(out_dir, 'cmp', f'{basename}_{idx:02d}.png'), cmp_img)

        # (2) 保存直接对原图（Person Crop）做超分的结果
        if restored_img is not None:
            save_full_path = os.path.join(out_dir, 'restored_imgs', img_name)
            cv2.imwrite(save_full_path, restored_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        
        print(f"[FaceSR] Async processed {img_name}: found {len(cropped_faces)} faces", flush=True)

    def letterbox(self, img, new_size=640):
        """YOLO 输入预处理：等比例缩放并 padding 到正方形"""
        h, w = img.shape[:2]
        r = min(new_size / h, new_size / w)
        nh, nw = int(h * r), int(w * r)

        resized = cv2.resize(img, (nw, nh))
        padw = (new_size - nw) // 2
        padh = (new_size - nh) // 2

        out = np.full((new_size, new_size, 3), 114, dtype=np.uint8)
        out[padh:padh + nh, padw:padw + nw] = resized
        # 返回：处理后图、缩放比、padding
        return out, r, (padw, padh)

    @staticmethod
    def _decode_frame_from_meta(meta: dict):
        """从 meta 中解码帧

        优先尝试：JPEG/PNG（cv2.imdecode）
        失败后回退：按 width/height/stride/channels 解析原始 RGB buffer
        """
        width = int(meta.get("width", 0))
        height = int(meta.get("height", 0))
        stride = int(meta.get("stride", width * 3))
        channels = int(meta.get("channels", 3))
        b64 = meta.get("base64", "")

        if not b64:
            return None

        raw = base64.b64decode(b64)

        try:
            # 1) 尝试按压缩图片解码
            nparr = np.frombuffer(raw, dtype=np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if frame is not None:
                return frame
        except Exception:
            pass

        # 2) 回退：按 stride 逐行拼接，重建 RGB 数据
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

        frame = np.frombuffer(rgb, dtype=np.uint8).reshape(height, width, channels)
        if channels == 3:
            # OpenCV 默认 BGR，这里把 RGB 转成 BGR
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        return frame

    @staticmethod
    def _safe_camera_id(camera_id: str) -> str:
        """清洗 camera_id：用于落盘目录名，避免路径/特殊字符污染"""
        if not camera_id:
            return "unknown"
        safe = "".join(c if c.isalnum() or c in ('_', '-', '/') else '_' for c in camera_id)
        safe = safe.replace('/', '_').replace('\\', '_')
        return safe

    def save_person_crop(self, track_id: int, frame: np.ndarray, bbox: tuple, camera_id: str = ""):
        """保存当前轨迹的裁剪图到输入目录（以 track 为单位落盘）"""
        x1, y1, x2, y2 = bbox
        h, w = frame.shape[:2]
        # 坐标裁剪到图像范围内
        x1 = max(0, int(x1))
        y1 = max(0, int(y1))
        x2 = min(w, int(x2))
        y2 = min(h, int(y2))

        if x2 <= x1 or y2 <= y1:
            return

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return

        if track_id not in self.track_save_dirs:
            # 第一次见到该 track：创建保存目录并写入 info.txt
            safe_camera_id = self._safe_camera_id(camera_id)
            track_dir = os.path.join(INPUT_DIR, f"{safe_camera_id}_track_{track_id}")
            os.makedirs(track_dir, exist_ok=True)
            self.track_save_dirs[track_id] = track_dir
            self.track_frame_count[track_id] = 0
            self.track_camera_id[track_id] = camera_id

            info_file = os.path.join(track_dir, "info.txt")
            with open(info_file, "w", encoding="utf-8") as f:
                f.write(f"camera_id: {camera_id}\n")
                f.write(f"track_id: {track_id}\n")
                f.write(f"created_at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

        track_dir = self.track_save_dirs[track_id]

        frame_num = self.track_frame_count[track_id]
        # 用 6 位序号命名，保证自然排序
        filename = f"{frame_num:06d}.jpg"
        filepath = os.path.join(track_dir, filename)

        try:
            # 保存裁剪图（高质量 JPEG）
            cv2.imwrite(filepath, crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
            self.track_frame_count[track_id] += 1
            
            # 异步触发超分
            out_dir = os.path.join(OUTPUT_DIR, f"{safe_camera_id}_track_{track_id}")
            self.sr_queue.put({
                "track_dir": track_dir,
                "img_path": filepath,
                "out_dir": out_dir
            })
            
        except Exception as e:
            print(f"[FaceSR] save failed track_id={track_id} filepath={filepath} error={e}", flush=True)

    def _process_track_sr(self, track_dir: str, out_dir: str, restorer):
        """[DEPRECATED] 批量处理函数，已改为 per-image 异步处理"""
        pass

    def process_frame(self, meta: dict, model_ctx: dict = None):
        """核心：处理单帧

        - base64 解码
        - YOLO 检测（这里复用 yolo person 类别 0）
        - HybridSORT 跟踪
        - 保存裁剪图
        - track 超时后触发 SR 批处理
        """
        # 确保消费线程已启动
        self._ensure_sr_thread(model_ctx["gfpgan"])

        total_start = time.perf_counter()
        current_time = time.time()

        # ========== 调试：确认是否真的收到了上游请求 ==========
        self._recv_count += 1
        if self._recv_count <= 5 or self._recv_count % 200 == 0:
            try:
                b64_len = len(meta.get("base64", "") or "")
                print(
                    f"[FaceSR] recv#{self._recv_count} task={meta.get('task')} stream={meta.get('streamName')} "
                    f"path={meta.get('path')} w={meta.get('width')} h={meta.get('height')} stride={meta.get('stride')} "
                    f"b64_len={b64_len}",
                    flush=True,
                )
            except Exception:
                pass

        # 用 path/shmName 作为摄像头标识，用于区分不同输入源
        camera_id = meta.get("path", "") or meta.get("shmName", "") or "unknown"

        # 解码输入帧
        frame = self._decode_frame_from_meta(meta)
        if frame is None:
            if self._recv_count <= 5 or self._recv_count % 200 == 0:
                print(f"[FaceSR] decode failed recv#{self._recv_count}", flush=True)
            return

        height, width = frame.shape[:2]

        # 1) YOLO 检测（推理输入做 letterbox）
        yolo = model_ctx["yolo"]
        img_resize, r, (padw, padh) = self.letterbox(frame, 640)

        img = torch.from_numpy(img_resize).to(model_ctx["device"])
        img = img.permute(2, 0, 1).float() / 255.0
        img = img.unsqueeze(0)

        with torch.no_grad():
            results = yolo(img, conf=0.4, iou=0.5, classes=[0], verbose=False)

        boxes = results[0].boxes
        dets = np.empty((0, 6))

        if boxes is not None and len(boxes) > 0:
            xyxy = boxes.xyxy.cpu().numpy()
            conf = boxes.conf.cpu().numpy()
            cls = boxes.cls.cpu().numpy()

            # 反变换：从 letterbox 坐标映射回原图坐标
            xyxy[:, [0, 2]] -= padw
            xyxy[:, [1, 3]] -= padh
            xyxy /= r

            xyxy[:, 0] = np.clip(xyxy[:, 0], 0, width - 1)
            xyxy[:, 1] = np.clip(xyxy[:, 1], 0, height - 1)
            xyxy[:, 2] = np.clip(xyxy[:, 2], 0, width - 1)
            xyxy[:, 3] = np.clip(xyxy[:, 3], 0, height - 1)

            dets = np.concatenate([xyxy, conf.reshape(-1, 1), cls.reshape(-1, 1)], axis=1)

        # 2) 跟踪：dets -> track boxes + track_id
        tracker = model_ctx["tracker"]
        tracks = tracker.update(dets, frame)

        # 3) 保存每个 track 的裁剪图
        active_tracks = set()
        for t in tracks:
            t = t.astype(int)
            x1, y1, x2, y2, track_id = t[:5]

            self.track_last_seen[track_id] = current_time
            active_tracks.add(track_id)

            self.save_person_crop(track_id, frame, (x1, y1, x2, y2), camera_id)

        # 4) 超时清理：仅清理内存状态，超分已改为实时异步触发
        expired_tracks = []
        for track_id, last_seen in list(self.track_last_seen.items()):
            if track_id not in active_tracks and (current_time - last_seen > self.track_timeout):
                expired_tracks.append(track_id)

        for track_id in expired_tracks:
            self.track_last_seen.pop(track_id, None)
            self.track_save_dirs.pop(track_id, None)
            self.track_camera_id.pop(track_id, None)
            self.track_frame_count.pop(track_id, None)

        total_cost = (time.perf_counter() - total_start) * 1000
        if int(time.time() * 10) % 100 == 0:
            print(f"[FaceSR] total={total_cost:.2f}ms tracks={len(tracks)}", flush=True)

    @staticmethod
    def init_model_context(
        yolo_weights="/home/guest/Documents/hxjm-monitor/mtx/python/models/yolov8n.pt",
        reid_weights="/home/guest/Documents/hxjm-monitor/mtx/python/models/osnet_x0_25_msmt17.pt",
        gfpgan_model_path="",
        device="",
    ):
        """初始化 worker 侧模型上下文

        说明：BaseServer 的每个 worker 进程会调用一次该方法，得到独立的模型实例。
        """
        ctx = {}

        # 设备选择：优先 CUDA
        device = torch.device(device if device else ("cuda:0" if torch.cuda.is_available() else "cpu"))
        ctx["device"] = device

        # YOLO：这里沿用 person 类别检测（classes=[0]）
        yolo = YOLO(yolo_weights)
        yolo.to(device)
        ctx["yolo"] = yolo

        # HybridSORT：复用 reid_weights 作为 tracker 内部 ReID 权重
        tracker_config = os.getenv("FACE_SR_TRACKER_CONFIG", "").strip()
        if not tracker_config:
            local_candidate = os.path.join(SERVICE_DIR, "configs", "trackers", "hybridsort.yaml")
            if os.path.exists(local_candidate):
                tracker_config = local_candidate

        if not tracker_config:
            candidate = os.path.join(_PY_ROOT, "boxmot", "boxmot", "configs", "trackers", "hybridsort.yaml")
            if os.path.exists(candidate):
                tracker_config = candidate

        if not tracker_config:
            # 回退：从已安装的 boxmot 包目录中搜索 hybridsort.yaml
            try:
                import boxmot as _boxmot

                pkg_dir = os.path.dirname(_boxmot.__file__)
                matches = glob.glob(os.path.join(pkg_dir, "**", "hybridsort.yaml"), recursive=True)
                if matches:
                    tracker_config = matches[0]
            except Exception:
                tracker_config = ""

        if not tracker_config:
            raise FileNotFoundError(
                "Cannot find HybridSORT tracker config (hybridsort.yaml). "
                "Set env FACE_SR_TRACKER_CONFIG to the yaml path."
            )

        tracker = create_tracker(
            tracker_type="hybridsort",
            tracker_config=tracker_config,
            reid_weights=Path(reid_weights),
            device=device,
            half=False,
            per_class=False,
        )
        ctx["tracker"] = tracker

        # GFPGAN：将 GFPGAN-master 加入 sys.path，直接 import GFPGANer
        gfpgan_root = os.path.join(os.path.dirname(SERVICE_DIR), "GFPGAN-master")
        if gfpgan_root not in sys.path:
            sys.path.insert(0, gfpgan_root)

        if not gfpgan_model_path:
            gfpgan_model_path = os.path.join(gfpgan_root, "experiments/pretrained_models/GFPGANv1.4.pth")

        try:
            # 一些 GFPGAN 依赖会使用相对路径（如 weights），切到其工程根目录更稳
            os.chdir(gfpgan_root)
        except Exception:
            pass

        from gfpgan import GFPGANer

        gfpgan = GFPGANer(
            model_path=gfpgan_model_path,
            upscale=int(os.getenv("FACE_SR_UPSCALE", "2")),
            arch=os.getenv("FACE_SR_GFPGAN_ARCH", "clean"),
            channel_multiplier=int(os.getenv("FACE_SR_CHANNEL_MULTIPLIER", "2")),
            bg_upsampler=None,
            device=device,
        )
        ctx["gfpgan"] = gfpgan

        return ctx

    def select_worker_key(self, meta: dict) -> str:
        """worker 分流策略：按摄像头/流 ID 分配不同 worker，减少互相影响"""
        camera_id = meta.get("path", "") or meta.get("shmName", "")
        if camera_id:
            return f"face_sr:{camera_id}"
        return "face_sr:default"


def main():
    # 主进程入口：启动 BaseServer 的 ZMQ ROUTER 循环
    server = FaceSRServer()
    print(f"[FaceSR] Listening on {server.addr}", flush=True)
    print(f"[FaceSR] Input dir: {INPUT_DIR}", flush=True)
    print(f"[FaceSR] Output dir: {OUTPUT_DIR}", flush=True)
    server.serve()


if __name__ == "__main__":
    main()
