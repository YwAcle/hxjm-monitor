import os
import random
import re

import cv2
import torch
import numpy as np
import time, json
import base64
from collections import deque
from datetime import datetime
from pathlib import Path
from sklearn.metrics.pairwise import cosine_similarity
from uuid import uuid4
# CLIP-ReID 模型路径
import sys

sys.path.insert(0, "/home/guest/Documents/hxjm-monitor/mtx/python/reid/CLIP-ReID")

from config import cfg_base as cfg
from model.make_model import make_model

# YOLO
from ultralytics import YOLO
from typing import Optional

# SORT / HybridSORT
from boxmot import create_tracker

# BaseServer & shared memory
# 添加模块路径 (上级目录)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from base.server_base import BaseServer
from base.shm_utils import open_and_map, close_map
from base.postgresql.db_session import DBSession
from base.postgresql.config import DBConfig
import asyncio
MAX_ERR_LEN = 100

# ============================================================
#                     ReidServer 主类
# ============================================================
class ReidServer(BaseServer):

    def __init__(self, create_server_socket: bool = True):
        """
        初始化 ReidServer
        
        Args:
            create_server_socket: 是否创建服务器 socket（子进程设为 False）
        """
        if create_server_socket:
            addr = os.getenv("REID_ZMQ_ADDR", "ipc:///tmp/py_ai_boxmot.ipc")
            super().__init__(addr)
        else:
            # 子进程模式：不调用 super().__init__，避免创建 socket
            self.addr = None

        # ========== 日志 ==========
        os.makedirs("./log", exist_ok=True)
        self.log_path = "./log/reid_log.txt"

        # ========== CLIP-ReID 初始化 ==========
        print("[INIT] 初始化 CLIP-ReID ...")

        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        cfg.merge_from_file(
            "/home/guest/Documents/hxjm-monitor/mtx/python/reid/config/vit_base.yml"
        )
        cfg.freeze()
        with open(self.log_path, "w", encoding="utf-8") as f:
            f.write("====== ReID Tracking Log ======\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d')}\n")
            f.write(f"Model: {cfg.MODEL.NAME}\n")
            f.write("================================\n\n")
        # 构建模型
        self.reid_model = make_model(
            cfg,
            num_class=1,
            camera_num=1,
            view_num=1
        )
        self.reid_model.to(self.device)
        self.reid_model.eval()
        # 匹配模型
        self.reid_model_match = make_model(
            cfg,
            num_class=1,
            camera_num=1,
            view_num=1
        )
        self.reid_model_match.to(self.device)
        self.reid_model_match.eval()
        # 找到权重文件
        latest_weight = Path(
            "/home/guest/Documents/hxjm-monitor/mtx/python/reid/weights/MSMT17_clipreid_ViT-B-16_60.pth")
        print(f"[CLIP-ReID-目标模型] 加载模型权重: {latest_weight}")
        self.reid_model.load_param(str(latest_weight))
        latest_weight = Path(
            "/home/guest/Documents/hxjm-monitor/mtx/python/reid/weights/Market1501_clipreid_ViT-B-16_60.pth")
        print(f"[CLIP-ReID-匹配模型] 加载模型权重: {latest_weight}")
        self.reid_model_match.load_param(str(latest_weight))
        print("[CLIP-ReID] 初始化完成")

        # transform
        import torchvision.transforms as T
        self.reid_transform = T.Compose([
            T.ToPILImage(),
            T.Resize((cfg.INPUT.SIZE_TRAIN[0], cfg.INPUT.SIZE_TRAIN[1])),
            T.ToTensor(),
            T.Normalize(mean=cfg.INPUT.PIXEL_MEAN, std=cfg.INPUT.PIXEL_STD)
        ])

        # ========== 初始化数据库会话 ==========
        db_config = DBConfig(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "postgres"),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", "123456")
        )
        self.db = DBSession(config=db_config)
        # 注意：数据库连接池初始化移到子进程中（Worker.run）
        # 父进程不初始化，避免 pickle 问题
        if create_server_socket:
            # 只在主进程（创建 socket 时）初始化数据库
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            loop.run_until_complete(self.db.initialize())
            print("[INIT] 数据库连接池初始化完成")
        else:
            # 子进程模式：不在这里初始化，由 Worker.run 初始化
            print("[INIT] 子进程模式：数据库将在 Worker 中初始化")
        
        # ========== submit helper 用于后台执行数据库操作 ==========
        self._loop = None  # 在 Worker 中设置

        # ========== 加载目标人物库 ==========
        self.target_names = []  # 初始化name列表
        self.target_name_to_id = {}  # name -> reid_target.id 映射
        
        # ========== 多帧稳定匹配缓存 ==========
        self.track_stable_count = {}  # track_id → 连续命中次数
        self.track_is_target = {}  # track_id → True/False（锁定后永不解除）

        # ========== ReID 缓存：只在 track 出生时做一次 ReID ==========
        self.track_reid_cache = {}  # sort_tid → {sim_score, is_target, feature}
        self.track_last_seen = {}  # sort_tid → 最后出现的时间（用于清理过期缓存）

        # ========== 全局行人特征库（从数据库加载） ==========
        self.person_features = {}  # person_id → feature (numpy array)
        self.person_last_seen = {}  # person_id → 最后出现时间
        self.person_id_to_db_id = {}  # person_id → database_id (stranger_target.id)
        self.next_person_id = 1  # 下一个person_id
        
        # 只在主进程或子进程初始化完成后加载数据
        # 子进程模式：在 Worker.run 中初始化数据库后调用
        if create_server_socket:
            self.load_target_features()
            self.load_person_features_from_db()
        else:
            # 子进程模式：延迟到数据库初始化后
            self.target_feats = None

        # ========== 匹配参数 ==========
        self.reid_match_threshold = 0.85  # 特征匹配阈值
        self.sync_interval = 5.0  # 同步到文件的间隔（秒）
        self.last_sync_time = time.time()
        # 锁定判定参数：窗口大小和命中次数
        self.lock_window = 10
        self.lock_hits = 5
        self.lock_sim_threshold = 0.85
        self.track_match_history = {}  # pid -> deque 命中历史
        self.locked_ids = []  # 已锁定的person_id列表
        self.deleted_stranger_pids = set()  # 已删除stranger_target记录的pid集合
        
        # ========== 轨迹记录相关 ==========
        self.stream_id = None  # stream_id从process_frame的meta参数中获取
        self.tracklet_tracks = {}  # sort_tid -> {start_ts, trajectory_points, keyframes, pid, gallery_target_id, stranger_target_id, gallery_similarity, feature, query_asset_base64, frame_asset_base64, tracklet_id, frame_count, color}
        self.tracklet_max_duration = 180  # 最大轨迹时长（秒），3分钟
        self.tracklet_timeout = 2  # 轨迹超时时间（秒），30秒内没有出现该id就结束轨迹
        self.last_target_update_time = time.time()  # 上次更新目标人物特征的时间
        self.target_update_interval = 30.0  # 更新目标人物特征的间隔（秒）
        self.trajectory_update_interval = 25  # 每25帧更新一次轨迹点
        self.next_tracklet_color = 0.0  # 下一个轨迹记录的颜色值（float8）
        self.pid_to_tracklet_color = {}  # person_id -> color 映射，用于复用颜色
        
        print("[INIT] ReidServer 初始化完成\n")

    def submit(self, coro):
        """
        将协程提交到事件循环后台执行（不阻塞）
        
        如果在事件循环线程中调用：使用 create_task
        如果在其他线程中调用：使用 run_coroutine_threadsafe
        
        Args:
            coro: 要执行的协程对象
        
        Returns:
            task/future 对象（可用于 done_callback），如果无法提交则返回 None
        """
        if self._loop is None:
            # 如果没有设置 loop，尝试获取当前 loop
            try:
                loop = asyncio.get_running_loop()
                self._loop = loop  # 保存引用
            except RuntimeError:
                # 没有运行中的 loop，无法提交
                print(f"[WARN] submit called but no event loop available", flush=True)
                return None
        else:
            loop = self._loop
        
        def _handle_exception(fut):
            """处理后台任务的异常"""
            try:
                exc = fut.exception()
                if exc is not None:
                    err = f"{type(exc).__name__}: {exc}"
                    if len(err) > MAX_ERR_LEN:
                        err = err[:MAX_ERR_LEN] + "…(truncated)"
                    print(f"[WARN] 后台数据库操作失败: {err}", flush=True)
                    self.write_log(f"[后台数据库操作失败] {err}")
            except Exception:
                pass
        
        # 判断当前是否在 loop 所在的线程
        try:
            # 尝试获取当前运行的 loop
            current_loop = asyncio.get_running_loop()
            if current_loop is loop:
                # 在同一个线程，使用 create_task
                task = asyncio.create_task(coro)
                task.add_done_callback(_handle_exception)
                return task
            else:
                # 在不同的线程，使用 run_coroutine_threadsafe
                future = asyncio.run_coroutine_threadsafe(coro, loop)
                future.add_done_callback(_handle_exception)
                return future
        except RuntimeError:
            # 没有运行中的 loop（在非 async 上下文中，例如 process_frame 在线程池中）
            # 使用 run_coroutine_threadsafe
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            future.add_done_callback(_handle_exception)
            return future

    # ============================================================
    #     加载/保存行人特征库（从数据库）
    # ============================================================
    def load_person_features_from_db(self):
        """从数据库加载陌生人特征库到内存"""
        try:
            # 使用主 event loop（通过 self._loop）来执行数据库查询
            # 这样可以确保使用正确的连接池，避免连接复用问题
            if not hasattr(self, '_loop') or self._loop is None:
                raise RuntimeError("_loop is not set, cannot load person features from db")
            
            main_loop = self._loop
            
            # 使用 run_coroutine_threadsafe 在主 loop 中执行数据库查询
            # 这样可以确保使用主 loop 的连接池，每次操作都会 acquire 新连接
            future = asyncio.run_coroutine_threadsafe(
                self.db.select_stranger_target(is_active=True),
                main_loop
            )
            records = future.result()  # 等待结果（会阻塞当前线程，这是预期的）

            self.person_features = {}
            self.person_id_to_db_id = {}
            self.next_person_id = 1

            for record in records:
                db_id = str(record['id'])
                # vector类型处理：asyncpg返回的vector可能是数组或列表
                embedding = record['embedding']
                if hasattr(embedding, 'tolist'):
                    embedding = embedding.tolist()
                elif not isinstance(embedding, list):
                    embedding = list(embedding)

                person_id = self.next_person_id
                self.next_person_id += 1

                self.person_features[person_id] = np.array(embedding)
                self.person_id_to_db_id[person_id] = db_id

            print(f"[ReID] 从数据库加载了 {len(self.person_features)} 个陌生人特征")
            self.write_log(f"[ReID] 从数据库加载了 {len(self.person_features)} 个陌生人特征")
        except Exception as e:
            print(f"[ReID] 从数据库加载陌生人特征失败: {e}")
            import traceback
            traceback.print_exc()
            self.person_features = {}
            self.person_id_to_db_id = {}
            self.next_person_id = 1

    def match_person_by_feature(self, feature: np.ndarray):
        """
        通过特征匹配已有行人，返回匹配的person_id，如果未匹配则返回None
        使用批量计算提高性能

        Args:
            feature: ReID特征向量（已归一化）
        Returns:
            person_id: 匹配到的person_id，如果未匹配则返回None
        """
        if len(self.person_features) == 0:
            return None

        # 将输入特征展平并reshape为 (1, -1)
        feature = feature.flatten().reshape(1, -1)
        
        # 将所有存储的特征堆叠成矩阵，同时记录pid到索引的映射
        pids = list(self.person_features.keys())
        stored_features = np.vstack([self.person_features[pid].flatten() for pid in pids])
        
        # 批量计算余弦相似度 (1, N)，其中N是特征库大小
        similarities = cosine_similarity(feature, stored_features)[0]  # shape: (N,)
        
        # 找到最大相似度和对应的索引
        best_idx = np.argmax(similarities)
        best_sim = similarities[best_idx]
        
        # 如果最大相似度超过阈值，返回对应的person_id
        if best_sim > self.reid_match_threshold:
            best_id = pids[best_idx]
            self.write_log(f"[批量匹配] 匹配到已有行人 P{best_id}，相似度: {best_sim:.4f}")
            return best_id
        
        return None

    def match_persons_by_features_batch(self, features: np.ndarray) -> list:
        """
        批量匹配多个特征到已有行人特征库，返回匹配的person_id列表
        
        Args:
            features: 特征矩阵，shape为 (N, D)，其中N是特征数量，D是特征维度
        
        Returns:
            matched_pids: person_id列表，如果某个特征未匹配则对应位置为None
        """
        if features is None or len(features) == 0:
            return []
        
        if len(self.person_features) == 0:
            return [None] * len(features)
        
        # 确保features是2D数组
        if features.ndim == 1:
            features = features.reshape(1, -1)
        
        # 展平每个特征
        num_features = len(features)
        features = features.reshape(num_features, -1)
        
        # 将所有存储的特征堆叠成矩阵，同时记录pid到索引的映射
        pids = list(self.person_features.keys())
        stored_features = np.vstack([self.person_features[pid].flatten() for pid in pids])
        
        # 批量计算余弦相似度 (N, M)，其中N是输入特征数，M是特征库大小
        similarities = cosine_similarity(features, stored_features)  # shape: (N, M)
        
        # 对每个输入特征，找到最大相似度和对应的索引
        best_indices = np.argmax(similarities, axis=1)  # shape: (N,)
        best_sims = similarities[np.arange(num_features), best_indices]  # shape: (N,)
        
        # 根据阈值筛选匹配结果
        matched_pids = []
        for i in range(num_features):
            if best_sims[i] > self.reid_match_threshold:
                matched_pid = pids[best_indices[i]]
                matched_pids.append(matched_pid)
                self.write_log(f"[批量匹配] 特征 {i} 匹配到已有行人 P{matched_pid}，相似度: {best_sims[i]:.4f}")
            else:
                matched_pids.append(None)
        
        return matched_pids

    # ============================================================
    #     批量加载人物库（从数据库）
    # ============================================================
    def load_target_features(self):
        """从数据库加载目标人物库（reid_target表）"""
        try:
            # 使用主 event loop（通过 self._loop）来执行数据库查询
            # 这样可以确保使用正确的连接池，避免连接复用问题
            if not hasattr(self, '_loop') or self._loop is None:
                raise RuntimeError("_loop is not set, cannot load target features")
            
            main_loop = self._loop
            
            # 使用 run_coroutine_threadsafe 在主 loop 中执行数据库查询
            # 这样可以确保使用主 loop 的连接池，每次操作都会 acquire 新连接
            future = asyncio.run_coroutine_threadsafe(
                self.db.select_reid_target(is_active=True),
                main_loop
            )
            records = future.result()  # 等待结果（会阻塞当前线程，这是预期的）

            feats = []
            names = []  # 保存每个特征对应的name
            self.target_name_to_id = {}  # name -> reid_target.id 映射

            self.write_log(f"[ReID] 从数据库加载目标人物库，共 {len(records)} 条记录...")

            for record in records:
                # vector类型处理：asyncpg返回的vector可能是数组或列表
                embedding = record['embedding']
                if hasattr(embedding, 'tolist'):
                    embedding = embedding.tolist()
                elif not isinstance(embedding, list):
                    embedding = list(embedding)

                feat = np.array(embedding).reshape(1, -1)
                feats.append(feat)

                # 记录对应的name和id
                name = record.get('name', 'Unknown')
                target_id = str(record['id'])
                names.append(name)
                # 建立name到id的映射（如果多个name相同，使用最后一个）
                self.target_name_to_id[name] = target_id

            if len(feats) > 0:
                self.target_feats = np.vstack(feats)
                self.target_names = names  # 保存name列表，与target_feats一一对应
                print(self.target_names)
                print(f"[ReID] 成功加载 {self.target_feats.shape[0]} 个目标特征，对应 {len(set(names))} 个不同的人员\n")
            else:
                print("[ReID] 警告：未加载到任何目标特征")
                self.target_feats = None
                self.target_names = []
        except Exception as e:
            self.write_log(f"[ReID] 从数据库加载目标人物库失败: {e}")
            import traceback
            traceback.print_exc()
            self.target_feats = None
            self.target_names = []
            self.target_name_to_id = {}

    # ============================================================
    #     单张特征提取
    # ============================================================
    def extract_feature(self, img_bgr, match=False):
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        tensor = self.reid_transform(img_rgb).unsqueeze(0).to(self.device)

        with torch.no_grad():
            feat = self.reid_model(tensor)
            feat = feat / feat.norm(dim=1, keepdim=True)

        return feat.cpu().numpy()

    # ============================================================
    #     批量特征提取
    # ============================================================
    def extract_features_batch(self, crops, match=False):
        if len(crops) == 0:
            return None, []

        batch = []
        valid_idx = []

        for idx, c in enumerate(crops):
            if c is None or c.size == 0:
                continue
            img_rgb = cv2.cvtColor(c, cv2.COLOR_BGR2RGB)
            t = self.reid_transform(img_rgb)
            batch.append(t)
            valid_idx.append(idx)

        if len(batch) == 0:
            return None, []

        batch = torch.stack(batch).to(self.device)
        if match:
            with torch.no_grad():
                feats = self.reid_model_match(batch)
                feats = feats / feats.norm(dim=1, keepdim=True)
        else:
            with torch.no_grad():
                feats = self.reid_model(batch)
                feats = feats / feats.norm(dim=1, keepdim=True)

        return feats.cpu().numpy(), valid_idx

    # ============================================================
    #     YOLO 输入 reshape
    # ============================================================
    def letterbox(self, img, new_size=640):
        h, w = img.shape[:2]
        r = min(new_size / h, new_size / w)
        nh, nw = int(h * r), int(w * r)

        resized = cv2.resize(img, (nw, nh))
        padw = (new_size - nw) // 2
        padh = (new_size - nh) // 2

        out = np.full((new_size, new_size, 3), 114, dtype=np.uint8)
        out[padh:padh + nh, padw:padw + nw] = resized

        return out, r, (padw, padh)

    # ============================================================
    #     日志写入
    # ============================================================
    def write_log(self, text):
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except:
            pass

    def random_bright_color_rgb(self,min_v: int = 80) -> list[int]:
        return [random.randint(min_v, 255), random.randint(min_v, 255), random.randint(min_v, 255)]
    # ============================================================
    #     Core: 处理单帧
    # ============================================================
    def process_frame(self, meta, model_ctx):

        total_start = time.perf_counter()

        # -------------------------
        # 从meta获取stream_id
        # -------------------------
        self.stream_id = str(meta["path"])

        # -------------------------
        # 共享内存读取
        # -------------------------
        shm_name = meta["shmName"]
        shm_len = int(meta["shmLen"])
        width = int(meta["width"])
        height = int(meta["height"])
        stride = int(meta.get("stride", width * 3))

        fd, mm, _ = open_and_map(shm_name)
        try:
            buf = np.frombuffer(mm, dtype=np.uint8, count=height * stride)
            frame = buf.reshape(height, stride)[:, :width * 3].reshape(height, width, 3)
        except:
            close_map(fd, mm)
            return

        # ============================================================
        #     1.YOLO 行人检测
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
        #     2.SORT 跟踪
        # ============================================================
        t0 = time.perf_counter()
        tracker = model_ctx["tracker"]
        tracks = tracker.update(dets, frame)
        t_sort = (time.perf_counter() - t0) * 1000
        track_count = len(tracks)
        # ============================================================
        #     3. ID 分配 + 识别新出现的 track
        # ============================================================
        id_manager = model_ctx["id_manager"]
        objects = id_manager["objects"]
        next_id = id_manager["next_id"]

        result_tracks = []
        new_tracks = []  # 新出现的 track (sort_tid, bbox)

        current_time = time.time()

        for t in tracks:
            t = t.astype(int)
            x1, y1, x2, y2, sort_tid = t[:5]

            if sort_tid not in objects:
                # 新出现的 track，先标记，稍后通过ReID匹配决定person_id
                new_tracks.append((sort_tid, (x1, y1, x2, y2)))
                # 暂时不分配person_id，等ReID匹配后再分配

            # 如果已分配person_id，直接使用
            if sort_tid in objects:
                pid = objects[sort_tid]
                result_tracks.append((x1, y1, x2, y2, pid, sort_tid))
                # 更新最后出现时间
                self.track_last_seen[sort_tid] = current_time
                if pid in self.person_features:
                    self.person_last_seen[pid] = current_time

        id_manager["next_id"] = next_id

        # ============================================================
        #     4. 只对新出现的 track 做 ReID + 特征匹配
        # ============================================================
        t_reid_start = time.perf_counter()
        reid_count = 0

        if len(new_tracks) > 0:
            # 提取新 track 的特征
            new_crops = []
            new_coords_map = {}  # idx → (sort_tid, bbox)

            for idx, (sort_tid, bbox) in enumerate(new_tracks):
                x1, y1, x2, y2 = bbox
                crop = frame[y1:y2, x1:x2]
                if crop.size > 0:
                    new_crops.append(crop)
                    new_coords_map[len(new_crops) - 1] = (sort_tid, bbox)
            feats, valid_idx = self.extract_features_batch(new_crops, match=True)
            self.write_log(f"==========可能出现了新行人Track，共 {len(new_tracks)} 个新track==========")
            
            # 批量匹配所有新track的特征（在for循环之前）
            matched_pids_list = self.match_persons_by_features_batch(feats) if feats is not None else []
            
            # 对每个新track的特征进行后续处理
            for feat_idx, crop_idx in enumerate(valid_idx):
                if crop_idx not in new_coords_map:
                    continue

                sort_tid, bbox = new_coords_map[crop_idx]
                x1, y1, x2, y2 = bbox
                feature = feats[feat_idx]

                # 1. 使用批量匹配的结果
                matched_pid = matched_pids_list[feat_idx] if feat_idx < len(matched_pids_list) else None

                # 检查匹配到的person_id是否已经在当前画面中被其他track使用
                pid_conflict = False
                if matched_pid is not None:
                    # 检查该person_id是否已经被当前画面中的其他track使用
                    for existing_sort_tid, existing_pid in objects.items():
                        if existing_pid == matched_pid:
                            # 该person_id已经在画面中被使用，发生冲突
                            pid_conflict = True
                            self.write_log(f"[冲突检测] Track {sort_tid} 匹配到已有person_id P{matched_pid}，但该id已被Track {existing_sort_tid}使用，强制创建新person_id")
                            break

                if matched_pid is not None and not pid_conflict:
                    # 匹配成功且无冲突，复用已有的person_id
                    pid = matched_pid
                    # 更新最后出现时间
                    self.person_last_seen[pid] = current_time
                    self.write_log(f"[匹配成功] Track {sort_tid} 复用已有person_id P{pid} | 数据库ID：{self.person_id_to_db_id[pid]}")
                    
                    # 保存匹配信息，等tracklet创建后再记录（因为此时tracklet还未创建）
                    stranger_target_id = self.person_id_to_db_id.get(pid)
                    if stranger_target_id:
                        # 计算相似度（使用匹配时的相似度）
                        matched_feat = self.person_features[pid]
                        matched_sim = cosine_similarity(feature.reshape(1, -1), matched_feat.reshape(1, -1))[0][0]
                        # 保存匹配信息到缓存，等tracklet创建后再记录
                        if sort_tid not in self.tracklet_tracks:
                            # 如果tracklet还未创建，先保存匹配信息
                            # 这个信息会在tracklet创建后使用
                            pass  # tracklet会在后面创建，匹配记录会在tracklet创建后处理
                else:
                    # 未匹配或发生冲突，创建新的person_id并插入到数据库
                    pid = self.next_person_id
                    self.next_person_id += 1

                    # 插入到stranger_target表
                    try:
                        # 使用保存的 loop（子进程）或获取当前 loop（主进程）
                        if hasattr(self, '_loop') and self._loop is not None:
                            loop = self._loop
                        else:
                            try:
                                loop = asyncio.get_event_loop()
                            except RuntimeError:
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                        # 编码行人的base64（首帧行人的crop图片）
                        crop = frame[y1:y2, x1:x2]
                        image_base64 = None
                        if crop.size > 0:
                            success, buffer = cv2.imencode('.jpg', crop)
                            if success:
                                image_base64 = base64.b64encode(buffer).decode('utf-8')

                        # 先保存到内存（使用临时标识）
                        self.person_features[pid] = feature
                        self.person_last_seen[pid] = current_time
                        
                        # 后台插入数据库（需要获取 max_code_num，但可以在后台执行整个流程）
                        async def _insert_stranger():
                            try:
                                # 从数据库获取最大code编号，自增生成新code（防止冲突）
                                max_code_num = await self.db.get_max_stranger_code()
                                next_code_num = max_code_num + 1
                                code = f"STR-{next_code_num:06d}"
                                
                                # 插入数据库
                                db_id = await self.db.insert_stranger_target(
                                    code=code,
                                    status="new",
                                    embedding=feature.flatten().tolist(),
                                    embedding_model="CLIP-ReID-ViT-B-16",
                                    is_active=True,
                                    image_base64=image_base64
                                )
                                
                                # 更新内存中的映射
                                self.person_id_to_db_id[pid] = db_id
                                
                                if pid_conflict:
                                    self.write_log(f"[冲突解决] 创建新行人 P{pid}（原匹配P{matched_pid}发生冲突），数据库ID: {db_id}")
                                else:
                                    self.write_log(f"[无] 无匹配行人，创建新行人 P{pid}，数据库ID: {db_id}")
                                self.write_log(f"[person_id_to_db_id] 当前Pid映射数据库id记录：{self.person_id_to_db_id}")
                            except Exception as e:
                                # 异常已在 submit 的 done_callback 中处理
                                pass
                        
                        self.submit(_insert_stranger())
                    except Exception as e:
                        err = f"{type(e).__name__}: {e}"
                        if len(err) > MAX_ERR_LEN:
                            err = err[:MAX_ERR_LEN] + "…(truncated)"
                        # 即使数据库插入失败，也保存到内存
                        self.person_features[pid] = feature
                        self.person_last_seen[pid] = current_time
                        if pid_conflict:
                            self.write_log(f"[创建新行人] {err} 创建新行人 P{pid}（原匹配P{matched_pid}发生冲突，仅内存，数据库插入将在后台执行）")
                        else:
                            self.write_log(f"[创建新行人] {err} 无匹配行人，创建新行人 P{pid}（仅内存，数据库插入将在后台执行）")

                # 分配person_id到sort_tid
                objects[sort_tid] = pid
                id_manager["next_id"] = next_id

                # 2. 与目标库匹配（用于显示）
                target_sim = 0.0
                target_name = None  # 最匹配的name
                if self.target_feats is not None:
                    target_sim_matrix = cosine_similarity(feature.reshape(1, -1), self.target_feats)
                    target_sim = float(target_sim_matrix.max())
                    # 找到最匹配的特征索引，获取对应的name
                    best_feat_idx = int(target_sim_matrix.argmax())
                    if best_feat_idx < len(self.target_names):
                        target_name = self.target_names[best_feat_idx]

                # 缓存结果
                self.track_reid_cache[sort_tid] = {
                    'sim_score': target_sim,
                    'target_name': target_name,  # 最匹配的name
                    'is_target': False,  # 初始未锁定
                    'feature': feature
                }
                self.write_log(self.track_reid_cache[sort_tid])
                # 添加到result_tracks
                result_tracks.append((x1, y1, x2, y2, pid, sort_tid))
                self.track_last_seen[sort_tid] = current_time
                reid_count += 1
                
                # 初始化轨迹记录
                if sort_tid not in self.tracklet_tracks:
                    # 编码行人的base64（裁剪区域）
                    crop = frame[y1:y2, x1:x2]
                    query_asset_base64 = None
                    if crop.size > 0:
                        success, buffer = cv2.imencode('.jpg', crop)
                        if success:
                            query_asset_base64 = base64.b64encode(buffer).decode('utf-8')
                    
                    # 编码整个frame的base64
                    frame_asset_base64 = None
                    success, buffer = cv2.imencode('.jpg', frame)
                    if success:
                        frame_asset_base64 = base64.b64encode(buffer).decode('utf-8')
                    
                    # 生成或获取颜色（确保不同轨迹记录的颜色都不一样）
                    # 如果该pid之前有轨迹记录，可以复用颜色，否则生成新颜色
                    if pid in self.pid_to_tracklet_color:
                        tracklet_color = self.pid_to_tracklet_color[pid]
                    else:
                        # 生成新颜色（使用递增的浮点数）
                        tracklet_color = self.next_tracklet_color
                        self.next_tracklet_color += 1.0
                        self.pid_to_tracklet_color[pid] = tracklet_color


                    # 计算第一个轨迹点（中心点）
                    center_x = (x1 + x2) / 2
                    center_y = (y1 + y2) / 2
                    first_trajectory_point = {
                        'x': float(center_x),
                        'y': float(center_y),
                        'ts': datetime.fromtimestamp(current_time).isoformat()
                    }
                    
                    self.tracklet_tracks[sort_tid] = {
                        'start_ts': datetime.fromtimestamp(current_time),
                        'trajectory_points': [first_trajectory_point],  # 初始化时添加第一个轨迹点
                        'keyframes': [],
                        'pid': pid,
                        'gallery_target_id': None,
                        'stranger_target_id': None,
                        'gallery_similarity': None,
                        'feature': feature,
                        'first_bbox': (x1, y1, x2, y2),
                        'query_asset_base64': query_asset_base64,
                        'frame_asset_base64': frame_asset_base64,
                        'tracklet_id': None,  # 初始插入后保存tracklet_id
                        'frame_count': 0,  # 帧计数器
                        'color': tracklet_color,  # 轨迹颜色
                        'color_rgb': None
                    }
                    # 如果是陌生人，记录stranger_target_id
                    if pid in self.person_id_to_db_id:
                        self.tracklet_tracks[sort_tid]['stranger_target_id'] = self.person_id_to_db_id[pid]
                    
                    # 立即创建轨迹记录到数据库（此时已包含第一个轨迹点）
                    self._create_tracklet_in_db(sort_tid, current_time, frame)


        # 清理过期的缓存和轨迹（超过30秒未出现的 track）
        expire_time = self.tracklet_timeout  # 30秒
        expired_tracks = [tid for tid, last_seen in self.track_last_seen.items()
                          if current_time - last_seen > expire_time]
        for tid in expired_tracks:
            self.track_reid_cache.pop(tid, None)
            self.track_last_seen.pop(tid, None)
            # 轨迹结束，更新数据库记录（30秒内没有出现该id）
            if tid in self.tracklet_tracks:
                track_info = self.tracklet_tracks[tid]
                if track_info.get('tracklet_id'):
                    # 更新结束时间（注意：这里frame可能不是最后一帧，但至少记录当前帧）
                    self._update_tracklet_end_time(tid, current_time, frame)
                else:
                    # 如果还没有创建记录，则创建并设置end_ts
                    self._save_tracklet_to_db(tid, current_time, frame)
                # 清理内存中的轨迹数据
                del self.tracklet_tracks[tid]

        # 不再需要同步到文件，数据已保存在数据库

        t_reid = (time.perf_counter() - t_reid_start) * 1000

        # ============================================================
        #     5. 更新轨迹信息并检查是否需要保存
        # ============================================================
        current_datetime = datetime.fromtimestamp(current_time)
        for (x1, y1, x2, y2, pid, sort_tid) in result_tracks:
            # 更新轨迹信息
            if sort_tid in self.tracklet_tracks:
                track_info = self.tracklet_tracks[sort_tid]
                # 检查是否达到最大时长（3分钟）
                duration = (current_time - track_info['start_ts'].timestamp())
                if duration >= self.tracklet_max_duration:
                    # 达到最大时长，结束轨迹（不再记录）
                    if track_info.get('tracklet_id'):
                        # 更新结束时间（超过3min上限）
                        self._update_tracklet_end_time(sort_tid, current_time, frame)
                    # 清理内存中的轨迹数据
                    del self.tracklet_tracks[sort_tid]
                    continue
                
                # 更新帧计数器
                track_info['frame_count'] += 1
                
                # 每25帧记录一次轨迹点（调用数据库接口更新）
                if track_info['frame_count'] % self.trajectory_update_interval == 0:
                    center_x = (x1 + x2) / 2
                    center_y = (y1 + y2) / 2
                    trajectory_point = {
                        'x': float(center_x),
                        'y': float(center_y),
                        'ts': current_datetime.isoformat()
                    }
                    track_info['trajectory_points'].append(trajectory_point)
                    
                    # 调用数据库接口更新轨迹点
                    if track_info.get('tracklet_id'):
                        self._update_tracklet_trajectory(sort_tid, trajectory_point)
        
        # ============================================================
        #     6. 稳定匹配 + 目标人物锁定（使用缓存结果）
        # ============================================================
        for (x1, y1, x2, y2, pid, sort_tid) in result_tracks:
            # 默认颜色
            color = (50, 255, 50)
            # label = f"ID:{pid}"
            label = f"Stranger"
            # 从缓存中获取 ReID 结果
            if sort_tid in self.track_reid_cache:
                cache = self.track_reid_cache[sort_tid]
                # 先准备历史记录容器
                history = self.track_match_history.get(pid)
                if history is None:
                    history = deque(maxlen=self.lock_window)
                    self.track_match_history[pid] = history

                sim = cache.get("sim_score", 0.0)
                target_name = cache.get("target_name")  # 获取最匹配的name
                # 仅在窗口未满时重新提取特征并计算相似度；窗口满后不再计算
                if (not cache.get("is_target")) and (len(history) < self.lock_window):
                    if self.target_feats is not None:
                        # 从当前帧重新提取特征（窗口内每帧都重新计算）
                        crop = frame[y1:y2, x1:x2]
                        if crop.size > 0:
                            # 提取当前帧的特征
                            current_feature = self.extract_feature(crop)
                            if current_feature is not None:
                                # 用新特征计算相似度
                                sim_matrix = cosine_similarity(current_feature.reshape(1, -1), self.target_feats)
                                sim = float(sim_matrix.max())
                                cache["sim_score"] = sim  # 更新缓存
                                # 找到最匹配的特征索引，更新对应的name
                                best_feat_idx = int(sim_matrix.argmax())
                                if best_feat_idx < len(self.target_names):
                                    target_name = self.target_names[best_feat_idx]
                                    cache["target_name"] = target_name  # 更新缓存中的name
                    history.append(1 if sim >= self.lock_sim_threshold else 0)

                    self.write_log(
                        f"[ReID] Track {sort_tid} | sim={sim:.3f}, "
                        f"is_target={cache.get('is_target')}, hits={sum(history) if history else 0}/{len(history)}"
                    )

                # 如果已经锁定 → 显示匹配的name
                if cache['is_target'] or pid in self.locked_ids:
                    color = (0, 0, 255)
                    # 使用最匹配的name，如果没有则使用默认值
                    label = target_name if target_name else "Stranger"
                    self.write_log(f"[锁定] Track {sort_tid} 匹配到: {label}")
                    # 更新轨迹信息：如果是目标人物，需要从reid_target表获取gallery_target_id
                    if sort_tid in self.tracklet_tracks:
                        if target_name and target_name != "Stranger":
                            # 更新相似度
                            self.tracklet_tracks[sort_tid]['gallery_similarity'] = sim
                            # 根据target_name获取gallery_target_id（确保对应reid_target表的id）
                            if hasattr(self, 'target_name_to_id') and target_name in self.target_name_to_id:
                                gallery_target_id = self.target_name_to_id[target_name]
                                self.tracklet_tracks[sort_tid]['gallery_target_id'] = gallery_target_id
                                # 如果匹配到目标人物，清除stranger_target_id（不能同时有值）
                                self.tracklet_tracks[sort_tid]['stranger_target_id'] = None
                                
                                # 如果轨迹已经创建，更新数据库中的gallery_target_id（后台执行）
                                if self.tracklet_tracks[sort_tid].get('tracklet_id'):
                                    tracklet_id = self.tracklet_tracks[sort_tid]['tracklet_id']
                                    def _update_callback(fut):
                                        try:
                                            fut.result()
                                            self.write_log(f"[轨迹更新] 已更新轨迹 {sort_tid} 的gallery_target_id: {gallery_target_id}")
                                        except Exception as e:
                                            pass  # 异常已在 submit 的 done_callback 中处理
                                    
                                    future = self.submit(
                                        self.db.update_tracklet(
                                            tracklet_id,
                                            gallery_target_id=gallery_target_id,
                                            gallery_similarity=sim,
                                            stranger_target_id=None
                                        )
                                    )
                                    if future:
                                        future.add_done_callback(_update_callback)
                                
                                # 记录ReID匹配结果（匹配到reid_target）- 只在首次锁定时记录
                                if not cache.get('reid_match_recorded', False):
                                    crop = frame[y1:y2, x1:x2]
                                    self._record_reid_match(
                                        sort_tid=sort_tid,
                                        current_time=current_time,
                                        similarity=sim,
                                        matched=True,
                                        target_id=gallery_target_id,
                                        evidence_crop=crop
                                    )
                                    cache['reid_match_recorded'] = True
                    # 在10帧之后确定了 某个行人是 目标人物，则删除 pid 对应的 stranger_target（陌生人表）数据库条目
                    if pid in self.locked_ids and pid not in self.deleted_stranger_pids:
                        # 从person_id_to_db_id获取数据库id并删除
                        if pid in self.person_id_to_db_id:
                            db_id = self.person_id_to_db_id[pid]
                            # 删除stranger_target表中的记录（后台执行）
                            def _delete_callback(fut):
                                try:
                                    fut.result()
                                    self.deleted_stranger_pids.add(pid)
                                    self.write_log(f"[删除stranger_target] 已删除pid {pid} 对应的数据库记录，db_id: {db_id}")
                                except Exception as e:
                                    pass  # 异常已在 submit 的 done_callback 中处理
                            
                            future = self.submit(self.db.delete_stranger_target(db_id))
                            if future:
                                future.add_done_callback(_delete_callback)
                            else:
                                # 如果 submit 失败，直接标记（避免重复删除）
                                self.deleted_stranger_pids.add(pid)
                        else:
                            self.write_log(f"[删除stranger_target] pid {pid} 没有对应的数据库记录")

                else:
                    # 未锁定 → 使用窗口内命中次数
                    if sum(history) >= self.lock_hits:
                        cache['is_target'] = True
                        self.track_is_target[pid] = True
                        color = (0, 0, 255)
                        # 使用最匹配的name
                        label = target_name if target_name else "Stranger"
                        self.locked_ids.append(pid)
                        # 更新轨迹信息：如果是目标人物，需要从reid_target表获取gallery_target_id
                        if sort_tid in self.tracklet_tracks:
                            if target_name and target_name != "Unknown":
                                # 更新相似度
                                self.tracklet_tracks[sort_tid]['gallery_similarity'] = sim
                                # 根据target_name获取gallery_target_id（确保对应reid_target表的id）
                                if hasattr(self, 'target_name_to_id') and target_name in self.target_name_to_id:
                                    gallery_target_id = self.target_name_to_id[target_name]
                                    self.tracklet_tracks[sort_tid]['gallery_target_id'] = gallery_target_id
                                    # 如果匹配到目标人物，清除stranger_target_id（不能同时有值）
                                    self.tracklet_tracks[sort_tid]['stranger_target_id'] = None
                                    
                                    # 如果轨迹已经创建，更新数据库中的gallery_target_id
                                    if self.tracklet_tracks[sort_tid].get('tracklet_id'):
                                        try:
                                            if hasattr(self, '_loop') and self._loop is not None:
                                                loop = self._loop
                                            else:
                                                try:
                                                    loop = asyncio.get_event_loop()
                                                except RuntimeError:
                                                    loop = asyncio.new_event_loop()
                                                    asyncio.set_event_loop(loop)
                                            loop.run_until_complete(
                                                self.db.update_tracklet(
                                                    self.tracklet_tracks[sort_tid]['tracklet_id'],
                                                    gallery_target_id=gallery_target_id,
                                                    gallery_similarity=sim,
                                                    stranger_target_id=None
                                                )
                                            )
                                            self.write_log(f"[轨迹更新] 已更新轨迹 {sort_tid} 的gallery_target_id: {gallery_target_id}")
                                        except Exception as e:
                                            print(f"[ReID] 更新轨迹 {sort_tid} 失败: {e}")
                                    
                                    # 记录ReID匹配结果（匹配到reid_target）- 锁定判定成功时记录
                                    crop = frame[y1:y2, x1:x2]
                                    self._record_reid_match(
                                        sort_tid=sort_tid,
                                        current_time=current_time,
                                        similarity=sim,
                                        matched=True,
                                        target_id=gallery_target_id,
                                        evidence_crop=crop
                                    )
                                    cache['reid_match_recorded'] = True
                        
                        # 确认锁定后，立即删除stranger_target表中的记录
                        if pid not in self.deleted_stranger_pids and pid in self.person_id_to_db_id:
                            self.write_log(f"[锁定] Track {sort_tid} 匹配到: {label}")
                            db_id = self.person_id_to_db_id[pid]
                            # 删除stranger_target表中的记录（后台执行）
                            def _delete_callback(fut):
                                try:
                                    fut.result()
                                    self.deleted_stranger_pids.add(pid)
                                    self.write_log(f"[删除stranger_target] 已删除pid {pid} 对应的数据库记录，db_id: {db_id}")
                                except Exception as e:
                                    pass  # 异常已在 submit 的 done_callback 中处理
                            
                            future = self.submit(self.db.delete_stranger_target(db_id))
                            if future:
                                future.add_done_callback(_delete_callback)
                            else:
                                # 如果 submit 失败，直接标记（避免重复删除）
                                self.deleted_stranger_pids.add(pid)


            # 绘制
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, label, (x1, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        # ============================================================
        #     7. 定时更新目标人物特征（每30秒）
        # ============================================================
        # if current_time - self.last_target_update_time >= self.target_update_interval:
        #     self.last_target_update_time = current_time
        #     try:
        #         self.load_target_features()
        #         self.write_log(
        #             f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [定时更新] 已更新目标人物特征库，共 {len(self.target_names)} 个目标"
        #         )
        #     except Exception as e:
        #         print(f"[ReID] 定时更新目标人物特征失败: {e}")
        #         self.write_log(f"[定时更新失败] {e}")

        # ============================================================
        #     8. 写回共享内存
        # ============================================================
        for y in range(height):
            mm[y * stride:y * stride + width * 3] = frame[y].tobytes()

        close_map(fd, mm)

        # ==========================================================
        # 8. 日志
        # ==========================================================
        if boxes is not None and len(boxes) > 0:
            total_cost = (time.perf_counter() - total_start) * 1000

            log_perf = (
                f"[Perf] total={total_cost:.2f}ms | "
                f"yolo={t_yolo:.2f}ms | sort={t_sort:.2f}ms | reid={t_reid:.2f}ms | "
                f"det={detect_count} | track={track_count} | new_reid={reid_count}"
            )

            print(log_perf)
            # self.write_log(log_perf)
            # ---------------------------
            # 相似度日志（仅记录新做的 ReID）
            # ---------------------------
            # 记录新 track 的相似度
            new_sim_scores = []
            for sort_tid, _ in new_tracks:
                if sort_tid in self.track_reid_cache:
                    new_sim_scores.append(self.track_reid_cache[sort_tid]["sim_score"])

            if len(new_sim_scores) > 0:
                score_text = "[SIM] new_tracks_scores=" + np.array2string(
                    np.round(np.array(new_sim_scores), 3),
                    separator=", "
                )
                print(score_text)
                # self.write_log(score_text)

    # ============================================================
    #     创建轨迹记录到数据库
    # ============================================================
    def _create_tracklet_in_db(self, sort_tid: int, current_time: float, frame: np.ndarray):
        """创建轨迹记录到数据库（初始化时调用）"""
        if sort_tid not in self.tracklet_tracks:
            return
        
        if not self.stream_id:
            self.write_log(f"[轨迹记录] 跳过轨迹 {sort_tid}：stream_id 未设置")
            return
        
        track_info = self.tracklet_tracks[sort_tid]
        
        # 准备meta信息
        meta = {
            'sort_tid': sort_tid,
            'person_id': track_info['pid'],
            'algorithm_version': 'CLIP-ReID-ViT-B-16'
        }
        
        # 获取特征向量
        repr_embedding = track_info['feature'].flatten().tolist() if track_info.get('feature') is not None else None
        
        # 确保gallery_target_id和stranger_target_id正确对应数据库表的id
        gallery_target_id = track_info.get('gallery_target_id')
        stranger_target_id = track_info.get('stranger_target_id')
        
        # 如果stranger_target_id存在，确保它对应stranger_target表的id
        if stranger_target_id and track_info['pid'] in self.person_id_to_db_id:
            # 确保使用正确的stranger_target表的id
            stranger_target_id = self.person_id_to_db_id[track_info['pid']]
            track_info['stranger_target_id'] = stranger_target_id
        
        # 获取颜色
        tracklet_color = track_info.get('color', self.next_tracklet_color)
        
        # 准备轨迹点数据（包含初始化时的第一个轨迹点）
        trajectory_points = {
            'points': track_info['trajectory_points']
        } if track_info['trajectory_points'] else {'points': []}
        
        # 插入轨迹记录（后台执行，需要 tracklet_id，使用回调更新）
        async def _insert_tracklet_async():
            try:
                tracklet_id = await self.db.insert_tracklet(
                    stream_id=self.stream_id,
                    start_ts=track_info['start_ts'],
                    cls_name='person',
                    end_ts=None,  # 初始化时end_ts为None，后续根据情况更新
                    color_rgb=self.random_bright_color_rgb(),
                    query_asset_base64=track_info.get('query_asset_base64'),
                    frame_asset_base64=track_info.get('frame_asset_base64'),
                    gallery_target_id=gallery_target_id,
                    gallery_similarity=track_info.get('gallery_similarity'),
                    stranger_target_id=stranger_target_id,
                    repr_embedding=repr_embedding,
                    embedding_model='CLIP-ReID-ViT-B-16',
                    trajectory_points=trajectory_points,  # 使用当前的轨迹点（包含第一个点）
                    meta=meta
                )
                
                # 保存tracklet_id
                track_info['tracklet_id'] = tracklet_id
                self.write_log(f"[轨迹记录] 已创建轨迹 {sort_tid} 到数据库，tracklet_id: {tracklet_id}, gallery_target_id: {gallery_target_id}, stranger_target_id: {stranger_target_id}")
                
                # 如果tracklet创建时已经有stranger_target_id，记录匹配结果
                if stranger_target_id:
                    # 获取匹配时的相似度（使用默认相似度，因为匹配成功才会复用person_id）
                    matched_sim = 0.85  # 默认相似度，因为匹配成功才会复用person_id
                    # 获取evidence_crop（从track_info中获取query_asset_base64对应的crop）
                    evidence_crop = None
                    if track_info.get('query_asset_base64'):
                        # 从base64解码获取crop图片
                        try:
                            img_data = base64.b64decode(track_info['query_asset_base64'])
                            nparr = np.frombuffer(img_data, dtype=np.uint8)
                            evidence_crop = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        except:
                            pass
                    
                    # 记录ReID匹配结果（匹配到stranger_target）
                    self._record_reid_match(
                        sort_tid=sort_tid,
                        current_time=current_time,
                        similarity=matched_sim,
                        matched=True,
                        stranger_target_id=stranger_target_id,
                        evidence_crop=evidence_crop
                    )
            except Exception as e:
                # 异常已在 submit 的 done_callback 中处理
                pass
        
        self.submit(_insert_tracklet_async())

    # ============================================================
    #     记录ReID匹配结果
    # ============================================================
    def _record_reid_match(self, sort_tid: int, current_time: float, similarity: float, 
                           matched: bool, target_id: Optional[str] = None, 
                           stranger_target_id: Optional[str] = None, 
                           evidence_crop: np.ndarray = None):
        """
        记录ReID匹配结果到数据库
        
        Args:
            sort_tid: 跟踪ID
            current_time: 当前时间戳
            similarity: 相似度
            matched: 是否匹配成功
            target_id: reid_target表的id（如果匹配到内部人员）
            stranger_target_id: stranger_target表的id（如果匹配到陌生人）
            evidence_crop: 匹配成功时刻的行人证据图（crop图片）
        """
        if sort_tid not in self.tracklet_tracks:
            return
        
        track_info = self.tracklet_tracks[sort_tid]
        tracklet_id = track_info.get('tracklet_id')
        if not tracklet_id:
            return
        
        try:
            # 使用保存的 loop（子进程）或获取当前 loop（主进程）
            if hasattr(self, '_loop') and self._loop is not None:
                loop = self._loop
            else:
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            
            # 获取query_asset_base64（从数据库查询）
            query_asset_base64 = None
            if target_id:
                # 匹配到内部人员，从reid_target表获取image_base64
                records = loop.run_until_complete(
                    self.db.select_reid_target("id = $1", True, target_id)
                )

                if records and len(records) > 0:
                    query_asset_base64 = records[0].get('image_base64')
            elif stranger_target_id:
                # 匹配到陌生人，从stranger_target表获取image_base64
                records = loop.run_until_complete(
                    self.db.select_stranger_target("id = $1", True, stranger_target_id)
                )
                if records and len(records) > 0:
                    query_asset_base64 = records[0].get('image_base64')
            
            # 编码evidence_asset_base64（匹配成功时刻的行人证据图）
            evidence_asset_base64 = None
            if evidence_crop is not None and evidence_crop.size > 0:
                success, buffer = cv2.imencode('.jpg', evidence_crop)
                if success:
                    evidence_asset_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # 插入reid_match记录
            loop.run_until_complete(
                self.db.insert_reid_match(
                    tracklet_id=tracklet_id,
                    ts=datetime.fromtimestamp(current_time),
                    similarity=similarity,
                    threshold=self.reid_match_threshold,
                    matched=matched,
                    target_id=target_id,
                    stranger_target_id=stranger_target_id,
                    query_asset_base64=query_asset_base64,
                    evidence_asset_base64=evidence_asset_base64
                )
            )
            
            self.write_log(f"[ReID匹配记录] 已记录匹配结果，sort_tid: {sort_tid}, tracklet_id: {tracklet_id}, matched: {matched}, similarity: {similarity:.3f}")
            
        except Exception as e:
            print(f"[ReID] 记录匹配结果失败 (sort_tid={sort_tid}): {e}")
            self.write_log(f"[记录匹配结果失败] sort_tid {sort_tid}, 错误: {e}")
            import traceback
            traceback.print_exc()

    # ============================================================
    #     更新轨迹点
    # ============================================================
    def _update_tracklet_trajectory(self, sort_tid: int, trajectory_point: dict):
        """更新轨迹点（每25帧调用一次）"""
        if sort_tid not in self.tracklet_tracks:
            return
        
        track_info = self.tracklet_tracks[sort_tid]
        tracklet_id = track_info.get('tracklet_id')
        if not tracklet_id:
            return
        
        # 获取当前的轨迹点列表
        trajectory_points = {
            'points': track_info['trajectory_points']
        }
        
        # 更新轨迹点（后台执行）
        self.submit(
            self.db.update_tracklet(
                tracklet_id,
                trajectory_points=trajectory_points
            )
        )

    # ============================================================
    #     更新轨迹结束时间
    # ============================================================
    def _update_tracklet_end_time(self, sort_tid: int, current_time: float, frame: np.ndarray = None):
        """更新轨迹结束时间"""
        if sort_tid not in self.tracklet_tracks:
            return
        
        track_info = self.tracklet_tracks[sort_tid]
        tracklet_id = track_info.get('tracklet_id')
        if not tracklet_id:
            return
        
        end_ts = datetime.fromtimestamp(current_time)
        
        # 编码轨迹尾帧的base64
        frame_end_base64 = None
        if frame is not None:
            success, buffer = cv2.imencode('.jpg', frame)
            if success:
                frame_end_base64 = base64.b64encode(buffer).decode('utf-8')
        
        # 确保gallery_target_id和stranger_target_id正确对应数据库表的id
        gallery_target_id = track_info.get('gallery_target_id')
        stranger_target_id = track_info.get('stranger_target_id')
        
        # 如果stranger_target_id存在，确保它对应stranger_target表的id
        if stranger_target_id and track_info['pid'] in self.person_id_to_db_id:
            stranger_target_id = self.person_id_to_db_id[track_info['pid']]
        
        # 如果gallery_target_id存在，确保它对应reid_target表的id
        # 这里假设gallery_target_id已经通过target_name_to_id正确设置
        
        # 获取最终的轨迹点
        trajectory_points = {
            'points': track_info['trajectory_points']
        } if track_info['trajectory_points'] else None
        
        # 后台执行：更新结束时间、轨迹尾帧和最终轨迹点，然后创建episode记录
        async def _update_end_time_and_create_episode_async():
            try:
                # 更新结束时间、轨迹尾帧和最终轨迹点
                await self.db.update_tracklet(
                    tracklet_id,
                    end_ts=end_ts,
                    frame_end_base64=frame_end_base64,
                    trajectory_points=trajectory_points,
                    gallery_target_id=gallery_target_id,
                    gallery_similarity=track_info.get('gallery_similarity'),
                    stranger_target_id=stranger_target_id
                )
                
                self.write_log(f"[轨迹记录] 已更新轨迹 {sort_tid} 结束时间，tracklet_id: {tracklet_id}")
                
                # 创建episode记录
                await self._create_episode_for_tracklet_async(tracklet_id, track_info, end_ts)
            except Exception as e:
                # 异常已在 submit 的 done_callback 中处理
                pass
        
        self.submit(_update_end_time_and_create_episode_async())
    # ============================================================
    # 查询media_asset_id
    # ============================================================
    def get_media_asset_id_by_time(self, t0: datetime) -> Optional[str]:
        """
        根据时间点 t0 查询最近的 media_asset_id
        规则：找到 ts <= t0 的最新 media_asset

        参数:
            t0: datetime (timestamptz)

        返回:
            media_asset_id (str) 或 None
        """
        if not t0:
            self.write_log("[WARN] t0为空，跳过media_asset查询")
            return None

        loop = asyncio.get_event_loop()

        media_asset_record = loop.run_until_complete(
            self.db.select_media_asset_by_timestamp(t0)
        )

        if not media_asset_record or 'id' not in media_asset_record:
            self.write_log(f"[WARN] 未找到media_asset，查询时间: {t0}")
            return None

        media_asset_id = str(media_asset_record['id'])
        self.write_log(f"[OK] 查询到media_asset_id={media_asset_id}, t0={t0}")

        return media_asset_id
    # ============================================================
    #     为轨迹创建Episode记录
    # ============================================================
    async def _create_episode_for_tracklet_async(self, tracklet_id: str, track_info: dict, end_ts: datetime):
        """
        为轨迹创建Episode记录（异步版本）
        
        Args:
            tracklet_id: 轨迹ID
            track_info: 轨迹信息字典
            end_ts: 轨迹结束时间
        """
        try:
            # 从数据库查询tracklet记录，获取完整信息
            tracklet_records = await self.db.select_tracklet("id = $1", tracklet_id)
            
            if not tracklet_records or len(tracklet_records) == 0:
                self.write_log(f"[Episode] 无法找到轨迹记录，tracklet_id: {tracklet_id}")
                return
            
            tracklet_record = tracklet_records[0]
            
            # 获取轨迹信息
            start_ts = track_info.get('start_ts')
            if not isinstance(start_ts, datetime):
                start_ts = tracklet_record.get('start_ts')
                if isinstance(start_ts, str):
                    # 如果是字符串，尝试解析
                    try:
                        start_ts = datetime.fromisoformat(start_ts.replace('Z', '+00:00'))
                    except:
                        start_ts = tracklet_record.get('start_ts')
            
            gallery_target_id = tracklet_record.get('gallery_target_id')
            stranger_target_id = tracklet_record.get('stranger_target_id')
            query_asset_base64 = tracklet_record.get('query_asset_base64')
            trajectory_points = tracklet_record.get('trajectory_points')
            color_rgb = tracklet_record.get('color_rgb')
            
            # 获取行人姓名
            person_name = None
            if gallery_target_id:
                # 匹配到内部人员，从reid_target表查询name
                reid_records = await self.db.select_reid_target("id = $1", True, gallery_target_id)
                if reid_records and len(reid_records) > 0:
                    person_name = reid_records[0].get('name')
            elif stranger_target_id:
                # 匹配到陌生人，使用stranger_target_id
                person_name = str(stranger_target_id)
            
            # 查询media_asset_id列表（根据start_ts和end_ts分别查询）
            # 一个轨迹可能跨越多个media_asset切片
            media_asset_id_list = []
            
            # 查询开始时间对应的media_asset_id
            start_media_asset_record = await self.db.select_media_asset_by_timestamp(start_ts)
            start_media_asset_id = None
            if start_media_asset_record and 'id' in start_media_asset_record:
                start_media_asset_id = str(start_media_asset_record['id'])
                media_asset_id_list.append(start_media_asset_id)
            
            # 查询结束时间对应的media_asset_id
            end_media_asset_record = await self.db.select_media_asset_by_timestamp(end_ts)
            end_media_asset_id = None
            if end_media_asset_record and 'id' in end_media_asset_record:
                end_media_asset_id = str(end_media_asset_record['id'])
                # 如果结束时间对应的media_asset_id与开始时间不同，则添加到列表中
                if end_media_asset_id != start_media_asset_id:
                    media_asset_id_list.append(end_media_asset_id)
            
            # 如果列表为空，说明都没有查询到，保持为空列表
            # 如果列表只有一个元素，说明开始和结束在同一切片
            # 如果列表有两个元素，说明轨迹跨越了两个切片
            
            # TODO: 异常检测：多算法继承（打架，摔倒，跳跃）
            # TODO: UUID -> 自增ID
            # 从stream_id中提取camera编号（使用正则表达式）
            # 例如：'live/camera_1_boxmot' -> camera = 1
            camera = 0  # 默认值
            if self.stream_id:
                match = re.search(r'camera_(\d+)', str(self.stream_id))
                if match:
                    try:
                        camera = int(match.group(1))
                    except (ValueError, IndexError):
                        camera = 0  # 提取失败，使用默认值
                        self.write_log(f"[WARN] 无法从stream_id '{self.stream_id}' 中提取camera编号，使用默认值0")
            
            # 构建meta信息
            meta = {
                'camera': camera,  # 从stream_id中提取的真实camera编号
                'stream_id': self.stream_id,
                'media_asset_id': media_asset_id_list,  # media_asset_id列表，包含开始和结束对应的切片ID
                'stream_task': os.getenv("REID_ZMQ_ADDR", "ipc:///tmp/py_ai_boxmot.ipc"),  # 流任务
                'start_ts': start_ts.isoformat() if isinstance(start_ts, datetime) else str(start_ts),
                'end_ts': end_ts.isoformat() if isinstance(end_ts, datetime) else str(end_ts),
                'person_name': person_name,
                'person_image': query_asset_base64,  # 行人照片
                'trajectory_points': trajectory_points,  # 轨迹序列
                'trajectory_color': color_rgb  # 轨迹线条颜色
            }
            meta_log = {**meta, "person_image": None}
            self.write_log(f"=========事件记录========\n{meta_log}")
            
            # 创建episode记录
            episode_id = await self.db.insert_episode(
                start_ts=start_ts,
                end_ts=end_ts,
                target_id=gallery_target_id,
                stranger_target_id=stranger_target_id,
                meta=meta
            )
            
            # 创建episode_tracklet_link记录
            await self.db.insert_episode_tracklet_link(
                episode_id=episode_id,
                tracklet_id=tracklet_id
            )

            self.write_log(f"[Episode] 已创建Episode记录，episode_id: {episode_id}, tracklet_id: {tracklet_id}")
            
        except Exception as e:
            # 异常已在 submit 的 done_callback 中处理
            pass

    # ============================================================
    #     保存轨迹到数据库（轨迹结束时调用）
    # ============================================================
    def _save_tracklet_to_db(self, sort_tid: int, current_time: float, frame: np.ndarray = None):
        """保存轨迹到数据库"""
        if sort_tid not in self.tracklet_tracks:
            return
        
        if not self.stream_id:
            self.write_log(f"[轨迹记录] 跳过轨迹 {sort_tid}：stream_id 未设置")
            return
        
        track_info = self.tracklet_tracks[sort_tid]
        end_ts = datetime.fromtimestamp(current_time)
        
        try:
            # 使用保存的 loop（子进程）或获取当前 loop（主进程）
            if hasattr(self, '_loop') and self._loop is not None:
                loop = self._loop
            else:
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            
            # 准备轨迹数据
            trajectory_points = {
                'points': track_info['trajectory_points']
            } if track_info['trajectory_points'] else None
            
            keyframes = {
                'frames': track_info['keyframes']
            } if track_info['keyframes'] else None
            
            # 准备meta信息
            meta = {
                'sort_tid': sort_tid,
                'person_id': track_info['pid'],
                'algorithm_version': 'CLIP-ReID-ViT-B-16'
            }
            
            # 获取特征向量
            repr_embedding = track_info['feature'].flatten().tolist() if track_info.get('feature') is not None else None
            
            # 确保gallery_target_id和stranger_target_id正确对应数据库表的id
            gallery_target_id = track_info.get('gallery_target_id')
            stranger_target_id = track_info.get('stranger_target_id')
            
            # 如果stranger_target_id存在，确保它对应stranger_target表的id
            if stranger_target_id and track_info['pid'] in self.person_id_to_db_id:
                stranger_target_id = self.person_id_to_db_id[track_info['pid']]
            
            # 获取颜色
            tracklet_color = track_info.get('color', self.next_tracklet_color)
            
            # 编码轨迹尾帧的base64
            frame_end_base64 = None
            if frame is not None:
                success, buffer = cv2.imencode('.jpg', frame)
                if success:
                    frame_end_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # 如果已经有tracklet_id，只更新结束时间和轨迹点
            if track_info.get('tracklet_id'):
                loop.run_until_complete(
                    self.db.update_tracklet(
                        track_info['tracklet_id'],
                        end_ts=end_ts,
                        frame_end_base64=frame_end_base64,
                        trajectory_points=trajectory_points,
                        keyframes=keyframes,
                        gallery_target_id=gallery_target_id,
                        gallery_similarity=track_info.get('gallery_similarity'),
                        stranger_target_id=stranger_target_id
                    )
                )
                tracklet_id = track_info['tracklet_id']
            else:
                # 插入轨迹记录（如果之前没有创建，这种情况应该很少见）
                tracklet_id = loop.run_until_complete(
                    self.db.insert_tracklet(
                        stream_id=self.stream_id,
                        start_ts=track_info['start_ts'],
                        end_ts=end_ts,  # 30秒超时或3分钟上限时设置end_ts
                        cls_name='person',
                        color_rgb=self.random_bright_color_rgb(),
                        query_asset_base64=track_info.get('query_asset_base64'),
                        frame_asset_base64=track_info.get('frame_asset_base64'),
                        frame_end_base64=frame_end_base64,  # 轨迹尾帧
                        gallery_target_id=gallery_target_id,
                        gallery_similarity=track_info.get('gallery_similarity'),
                        stranger_target_id=stranger_target_id,
                        repr_embedding=repr_embedding,
                        embedding_model='CLIP-ReID-ViT-B-16',
                        trajectory_points=trajectory_points,
                        keyframes=keyframes,
                        meta=meta
                    )
                )
            
            self.write_log(f"[轨迹记录] 已保存轨迹 {sort_tid} 到数据库，tracklet_id: {tracklet_id}")
            
            # 创建episode记录
            self._create_episode_for_tracklet(tracklet_id, track_info, end_ts, loop)
            
            # 清理内存中的轨迹数据
            del self.tracklet_tracks[sort_tid]
            
        except Exception as e:
            print(f"[ReID] 保存轨迹到数据库失败 (sort_tid={sort_tid}): {e}")
            self.write_log(f"[轨迹记录失败] sort_tid {sort_tid}, 错误: {e}")
            import traceback
            traceback.print_exc()

    # ============================================================
    #     init_model_context
    # ============================================================
    @staticmethod
    def init_model_context(
            yolo_weights="/home/guest/Documents/hxjm-monitor/mtx/python/models/yolov8n.pt",
            reid_weights="/home/guest/Documents/hxjm-monitor/mtx/python/models/osnet_x0_25_msmt17.pt",
            device=""
    ):
        ctx = {}

        device = torch.device(device if device else ("cuda:0" if torch.cuda.is_available() else "cpu"))
        ctx["device"] = device

        print("[INIT] Loading YOLOv8 ...")
        yolo = YOLO(yolo_weights)
        yolo.to(device)
        ctx["yolo"] = yolo

        print("[INIT] Loading HybridSORT ...")

        tracker = create_tracker(
            tracker_type="hybridsort",
            tracker_config=None,
            reid_weights=Path(reid_weights),
            device=device,
            half=False,
            per_class=False,
        )
        ctx["tracker"] = tracker

        ctx["id_manager"] = {
            "objects": {},  # sort_id → person_id
            "next_id": 1
        }

        return ctx

    def select_worker_key(self, meta: dict) -> str:
        """
        根据 stream_id 分配不同的 worker，确保每个流有独立的模型实例
        
        Args:
            meta: 包含流信息的元数据字典
            
        Returns:
            worker key 字符串，格式为 "reid:{stream_id}"
        """
        # 从 meta 中获取 stream_id（path 字段）
        stream_id = meta.get("path", "")
        if stream_id:
            return f"reid:{stream_id}"
        # 如果没有 path，尝试使用 shmName 作为备用
        shm_name = meta.get("shmName", "")
        if shm_name:
            return f"reid:{shm_name}"
        return "reid:default"


# ===========================================================
def main():

    print("[ReidServer] Starting HybridSORT ReID service...")
    server = ReidServer()
    print(f"[ReidServer] Listening on {server.addr}")
    try:
        server.serve()
    finally:
        # 关闭数据库连接
        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(server.db.close())
        except:
            pass


if __name__ == "__main__":
    main()