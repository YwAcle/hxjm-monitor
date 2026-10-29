import os
import random
import re

import cv2
import torch
import numpy as np
import time, json
import base64
# from collections import deque  # 不再使用窗口命中逻辑，删除deque
from datetime import datetime
from pathlib import Path
from sklearn.metrics.pairwise import cosine_similarity
from uuid import uuid4
from PIL import Image, ImageDraw, ImageFont
# CLIP-ReID 模型路径
import sys
import onnxruntime as ort
sys.path.insert(0, "/home/guest/Documents/hxjm-monitor/mtx/python/reid/CLIP-ReID")

from config import cfg_base as cfg
from model.make_model import make_model

# YOLO
from ultralytics import YOLO
from typing import Optional, Any, Dict, List, Tuple

# SORT / HybridSORT - 已删除，不再使用跟踪
# from boxmot import create_tracker

# BaseServer & shared memory
# 添加模块路径 (上级目录)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from base.server_base import BaseServer
from base.shm_utils import open_and_map, close_map
from base.postgresql.db_session import DBSession
from base.postgresql.db_session_syn import DBSessionSync
from base.postgresql.config import DBConfig
import asyncio
MAX_ERR_LEN = 100
STRANGER_NAME = "陌生人"

# ========== ReID 模型配置常量 ==========
# 可选值: "vit" (ViT-B-16) 或 "rs50" (ResNet50)
REID_MODEL = "rs50"  # 默认使用ViT模型
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
        self.log_path_time = "./log/reid_log_time.txt"
        
        # ========== 帧保存 ==========
        os.makedirs("./output", exist_ok=True)
        self.last_frame_save_time = time.time()  # 上次保存帧的时间
        self.frame_save_interval = 5.0  # 每5秒保存一帧
        # ========== CLIP-ReID 初始化 ==========
        print("[INIT] 初始化 CLIP-ReID ...")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # 根据REID_MODEL常量选择配置文件和权重
        if REID_MODEL.lower() == "vit":
            # ViT-B-16 模型配置
            cfg.merge_from_file(
                "/home/guest/Documents/hxjm-monitor/mtx/python/reid/config/vit_base.yml"
            )
            target_weight = "/home/guest/Documents/hxjm-monitor/mtx/python/reid/weights/MSMT17_clipreid_ViT-B-16_60.pth"
            match_weight = "/home/guest/Documents/hxjm-monitor/mtx/python/reid/weights/ViT-B-16_60_trained_2.pth"
            model_name = "ViT-B-16"
        elif REID_MODEL.lower() == "rs50":
            # ResNet50 模型配置
            cfg.merge_from_file(
                "/home/guest/Documents/hxjm-monitor/mtx/python/reid/config/cnn_base.yml"
            )
            target_weight = "/home/guest/Documents/hxjm-monitor/mtx/python/reid/weights/MSMT17_clipreid_RN50_120.pth"
            match_weight = "/home/guest/Documents/hxjm-monitor/mtx/python/reid/weights/MSMT17_clipreid_RN50_120.pth"
            model_name = "ResNet50"
        else:
            raise ValueError(f"不支持的REID_MODEL值: {REID_MODEL}，仅支持 'vit' 或 'rs50'")
        
        cfg.freeze()
        print(f"[CLIP-ReID] 使用模型: {model_name} (REID_MODEL={REID_MODEL})")
        
        # 写入日志文件（在cfg.freeze()之后，确保cfg.MODEL.NAME已设置）
        with open(self.log_path, "w", encoding="utf-8") as f:
            f.write("====== ReID Tracking Log ======\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d')}\n")
            f.write(f"Model: {model_name} (REID_MODEL={REID_MODEL})\n")
            f.write(f"Config Model Name: {cfg.MODEL.NAME}\n")
            f.write("================================\n\n")
        with open(self.log_path_time, "w", encoding="utf-8") as f:
            f.write("====== ReID Tracking Log ======\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d')}\n")
            f.write(f"Model: {model_name} (REID_MODEL={REID_MODEL})\n")
            f.write(f"Config Model Name: {cfg.MODEL.NAME}\n")
            f.write("================================\n\n")
        
        # 构建模型
        self.reid_model = make_model(
            cfg,
            num_class=21, camera_num=None, view_num = None,
            device=self.device
        )
        self.reid_model.to(self.device)
        self.reid_model.eval()
        
        # 匹配模型
        self.reid_model_match = make_model(
            cfg,
            num_class=21, camera_num=None, view_num = None,
            device=self.device
        )
        self.reid_model_match.to(self.device)
        self.reid_model_match.eval()
        
        # 加载权重文件
        target_weight_path = Path(target_weight)
        print(f"[CLIP-ReID-目标模型] 加载模型权重: {target_weight_path}")
        if not target_weight_path.exists():
            raise FileNotFoundError(f"权重文件不存在: {target_weight_path}")
        self.reid_model.load_param(str(target_weight_path))
        
        match_weight_path = Path(match_weight)
        print(f"[CLIP-ReID-匹配模型] 加载模型权重: {match_weight_path}")
        if not match_weight_path.exists():
            raise FileNotFoundError(f"权重文件不存在: {match_weight_path}")
        self.reid_model_match.load_param(str(match_weight_path))
        
        print(f"[CLIP-ReID] {model_name} 模型初始化完成")

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
        
        # ========== 初始化同步数据库会话（用于同步插入操作）==========
        self.db_sync = DBSessionSync(config=db_config)
        try:
            self.db_sync.initialize()
            print("[INIT] 同步数据库连接池初始化完成")
        except Exception as e:
            print(f"[INIT] 同步数据库连接池初始化失败: {e}")
            self.db_sync = None
        
        # ========== submit helper 用于后台执行数据库操作 ==========
        self._loop = None  # 在 Worker 中设置

        # ========== 加载目标人物库 ==========
        self.target_names = []  # 初始化name列表
        self.target_name_to_id = {}  # name -> reid_target.id 映射
        
        # ========== ReID 缓存：每帧对检测框进行ReID ==========
        self.det_last_seen = {}  # det_id → 最后出现的时间（用于清理过期缓存）
        self.det_reid_cache = {}  # det_id → (target_sim, target_name, is_target) 缓存上一次的ReID结果

        # ========== SORT跟踪相关 ==========
        # 已删除SORT跟踪，不再使用sort_id相关变量

        # ========== 全局行人特征库（从数据库加载） ==========
        self.person_features = {}  # person_id → feature (numpy array)
        self.person_last_seen = {}  # person_id → 最后出现时间
        self.person_id_to_db_id = {}  # person_id → database_id (stranger_target.id)
        self.next_person_id = 1  # 下一个person_id
        
        # 只在主进程或子进程初始化完成后加载数据
        # 子进程模式：在 Worker.run 中初始化数据库后调用
        if create_server_socket:
            # 程序启动时，加载目标人物特征库
            self.load_target_features()
            # 不再加载陌生人特征库（不再进行匹配）
            # self.load_person_features_from_db()
        else:
            # 子进程模式：延迟到数据库初始化后
            self.target_feats = None

        # ========== 匹配参数 ==========
        self.target_sim_threshold = 0.835  # 目标人物相似度阈值，单帧超过此阈值即为目标人物
        
        # ========== 特征通过率统计（仅针对"冷佳旭"） ==========
        self.lengjiaxu_feat_stats = {}  # feat_idx -> {"total": 0, "pass": 0}，统计每条特征的通过率
        self.lengjiaxu_total_detections = 0  # 最大相似度大于阈值时的总检测次数
        
        # ========== 定期ReID相关 ==========
        # 已删除定期ReID功能（因为不再使用SORT跟踪，每帧都重新计算）
        
        # ========== 缓存清理相关 ==========
        self.det_timeout = 3  # 缓存超时时间（秒），n秒内没有出现该检测框就清理缓存
        
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

    def _put_chinese_text(self, img: np.ndarray, text: str, pos: tuple, 
                          color: tuple = (255, 255, 255), font_size: int = 22) -> np.ndarray:
        """
        在OpenCV图像上绘制中文文本（使用PIL）
        
        参数:
            img: OpenCV图像（RGB格式）
            text: 要绘制的文本（支持中文）
            pos: 文本位置 (x, y)，y坐标应该是框的上方位置
            color: 文本颜色 (B, G, R) - 注意：虽然传入的是BGR格式，但会转换为RGB用于PIL
            font_size: 字体大小
        
        返回:
            绘制后的图像（RGB格式）
        """
        # 将OpenCV图像转换为PIL图像
        # img 已经是RGB格式（frame在读取时就转换为RGB了）
        img_pil = Image.fromarray(img)
        draw = ImageDraw.Draw(img_pil)
        
        # 加载指定的中文字体
        font_path = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
        try:
            font = ImageFont.truetype(font_path, font_size)
        except Exception as e:
            # 如果指定字体加载失败，尝试使用默认字体
            print(f"[WARN] 无法加载字体 {font_path}: {e}，使用默认字体", flush=True)
            try:
                font = ImageFont.load_default()
            except:
                font = None
        
        # 计算文本高度（用于调整位置）
        if font:
            try:
                # 获取文本边界框
                bbox = draw.textbbox((0, 0), text, font=font)
                text_height = bbox[3] - bbox[1]
            except:
                # 如果textbbox不可用，使用getsize（旧版PIL）
                try:
                    text_width, text_height = draw.textsize(text, font=font)
                except:
                    text_height = font_size
        else:
            text_height = font_size
        
        # 调整y坐标：让文本在框的上方，考虑文本高度
        x, y = pos
        # y是框的顶部，我们需要将文本放在框的上方，所以减去文本高度和间距
        y_adjusted = y - text_height - 5
        
        # 确保y坐标不为负
        y_adjusted = max(5, y_adjusted)
        
        # 绘制文本（PIL使用RGB颜色，color参数已经是RGB格式）
        # color参数：传入时是(B, G, R)格式（BGR），需要转换为RGB
        # rgb_color = (color[2], color[1], color[0])  # BGR转RGB
        draw.text((x, y_adjusted), text, font=font, fill=color)
        
        # 转换回numpy数组（保持RGB格式）
        img_rgb = np.array(img_pil)
        return img_rgb

    # ============================================================
    #     清理未结束的轨迹记录（已删除，不再创建轨迹）
    # ============================================================
    def cleanup_incomplete_tracklets(self):
        """不再需要，因为不再创建轨迹"""
        pass
        """在程序启动时清理 tracklet 表中 end_ts 为空的记录（未结束的轨迹）"""
        try:
            # 使用主 event loop 来执行数据库操作
            if not hasattr(self, '_loop') or self._loop is None:
                # 如果没有 loop，尝试获取或创建一个
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # 如果 loop 正在运行，无法使用 run_until_complete
                        print("[WARN] 事件循环正在运行，无法同步清理未结束的轨迹记录")
                        return
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                # 如果没有运行中的 loop，直接执行
                async def _delete_incomplete():
                    try:
                        # 查询所有 end_ts 为空的记录
                        records = await self.db.select_tracklet("end_ts IS NULL")
                        count = len(records)
                        
                        if count > 0:
                            # 删除所有 end_ts 为空的记录
                            result = await self.db._execute_delete('tracklet', "end_ts IS NULL")
                            print(f"[清理] 已删除 {count} 条未结束的轨迹记录（end_ts 为空）")
                            self.write_log(f"[清理] 程序启动时，已删除 {count} 条未结束的轨迹记录（end_ts 为空）")
                        else:
                            print("[清理] 没有未结束的轨迹记录需要清理")
                    except Exception as e:
                        print(f"[WARN] 清理未结束的轨迹记录失败: {e}")
                        self.write_log(f"[清理失败] 清理未结束的轨迹记录失败: {e}")
                
                loop.run_until_complete(_delete_incomplete())
            else:
                # 如果有 loop，使用 run_coroutine_threadsafe
                main_loop = self._loop
                
                async def _delete_incomplete():
                    try:
                        # 查询所有 end_ts 为空的记录
                        records = await self.db.select_tracklet("end_ts IS NULL")
                        count = len(records)
                        
                        if count > 0:
                            # 删除所有 end_ts 为空的记录
                            result = await self.db._execute_delete('tracklet', "end_ts IS NULL")
                            print(f"[清理] 已删除 {count} 条未结束的轨迹记录（end_ts 为空）")
                            self.write_log(f"[清理] 程序启动时，已删除 {count} 条未结束的轨迹记录（end_ts 为空）")
                        else:
                            print("[清理] 没有未结束的轨迹记录需要清理")
                    except Exception as e:
                        print(f"[WARN] 清理未结束的轨迹记录失败: {e}")
                        self.write_log(f"[清理失败] 清理未结束的轨迹记录失败: {e}")
                
                future = asyncio.run_coroutine_threadsafe(_delete_incomplete(), main_loop)
                future.result(timeout=10)  # 等待完成，最多10秒
                
        except Exception as e:
            print(f"[WARN] 清理未结束的轨迹记录时发生异常: {e}")
            import traceback
            traceback.print_exc()

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
            self.write_log(f"[单个匹配] 匹配到已有行人 P{best_id}，相似度: {best_sim:.4f}")
            return best_id
        self.write_log(f"[单个匹配] 未匹配到已有行人，最高相似度: {best_sim:.4f}")
        return None

    def match_persons_by_features_batch(self, features: np.ndarray) -> list:
        """
        批量匹配多个特征到已有行人特征库，返回匹配的person_id列表
        
        Args:
            features: 特征矩阵，shape为 (N, D)，其中N是特征数量，D是特征维度
        
        Returns:
            matched_pids: person_id列表，如果某个特征未匹配则对应位置为None
        """
        self.write_log(f"[批量匹配] 开始批量匹配 match_persons_by_features_batch， 一共 {len(features)} 个特征")
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
        match_num = 0
        for i in range(num_features):
            if best_sims[i] > self.reid_match_threshold:
                matched_pid = pids[best_indices[i]]
                matched_pids.append(matched_pid)
                match_num += 1
                self.write_log(f"[批量匹配] 特征 {i} 匹配到已有行人 P{matched_pid}，相似度: {best_sims[i]:.4f}")
            else:
                matched_pids.append(None)
        if match_num == 0:
            self.write_log(f"[批量匹配] 未匹配到已有行人，最高相似度: {best_sims[i]:.4f}")
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
            
            # 根据REID_MODEL选择表名
            table_name = "reid_target" if REID_MODEL.lower() == "rs50" else "reid_target_vit"
            
            # 使用 run_coroutine_threadsafe 在主 loop 中执行数据库查询
            # 这样可以确保使用主 loop 的连接池，每次操作都会 acquire 新连接
            # 直接使用_execute_select以支持动态表名
            future = asyncio.run_coroutine_threadsafe(
                self.db._execute_select(table_name, "*", "is_active = $1", True),
                main_loop
            )
            records = future.result()  # 等待结果（会阻塞当前线程，这是预期的）

            feats = []
            names = []  # 保存每个特征对应的name
            self.target_name_to_id = {}  # name -> reid_target.id 映射
            self.target_name_to_indices = {}  # name -> [特征索引列表] 映射，用于多特征匹配
            self.index_to_db_id = {}  # 特征索引 -> 数据库ID 映射，用于记录和删除负面特征
            self.index_to_employee_id = {}  # 特征索引 -> employee_id (图片名称) 映射，用于日志记录

            self.write_log(f"[ReID] 从数据库加载目标人物库，共 {len(records)} 条记录...")

            for idx, record in enumerate(records):
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
                employee_id = record.get('employee_id', '')  # 获取employee_id（图片名称）
                names.append(name)
                # 建立name到id的映射（如果多个name相同，使用最后一个）
                self.target_name_to_id[name] = target_id
                # 建立name到特征索引列表的映射（用于多特征匹配）
                if name not in self.target_name_to_indices:
                    self.target_name_to_indices[name] = []
                self.target_name_to_indices[name].append(idx)
                # 建立特征索引到数据库ID的映射（用于记录和删除负面特征）
                self.index_to_db_id[idx] = target_id
                # 建立特征索引到employee_id的映射（用于日志记录）
                self.index_to_employee_id[idx] = employee_id

            if len(feats) > 0:
                self.target_feats = np.vstack(feats)
                self.target_names = names  # 保存name列表，与target_feats一一对应
                # 将目标特征转换为GPU tensor（用于GPU上的相似度计算）
                # 确保使用float32类型，与模型输出的feats类型一致
                self.target_feats_tensor = torch.from_numpy(self.target_feats).float().to(self.device)
                self.write_log(self.target_names)
                print(f"[ReID] 成功加载 {self.target_feats.shape[0]} 个目标特征，对应 {len(set(names))} 个不同的人员\n")
                # 打印每个目标人物的特征数量
                for name, indices in self.target_name_to_indices.items():
                    print(f"  - {name}: {len(indices)} 条特征")
            else:
                print("[ReID] 警告：未加载到任何目标特征")
                self.target_feats = None
                self.target_feats_tensor = None
                self.target_names = []
                self.target_name_to_indices = {}
                self.index_to_db_id = {}
                self.index_to_employee_id = {}
        except Exception as e:
            self.write_log(f"[ReID] 从数据库加载目标人物库失败: {e}")
            import traceback
            traceback.print_exc()
            self.target_feats = None
            self.target_feats_tensor = None
            self.target_names = []
            self.target_name_to_id = {}
            self.index_to_db_id = {}
            self.index_to_employee_id = {}

    # ============================================================
    #     单张特征提取
    # ============================================================
    def extract_feature(self, img_rgb, match=False):
        # img_rgb 已经是RGB格式（从frame裁剪得到，frame在读取时就转换为RGB了）
        tensor = self.reid_transform(img_rgb).unsqueeze(0).to(self.device)

        with torch.no_grad():
            feat = self.reid_model(tensor)
            feat = feat / feat.norm(dim=1, keepdim=True)

        return feat.cpu().numpy()

    # ============================================================
    #     批量特征提取
    # ============================================================
    def extract_features_batch(self, crops, match=False):
        """
        优化的批量特征提取函数，针对实时GPU推理管道优化
        
        优化点：
        1. 使用cv2.resize（比PIL快）进行CPU预处理
        2. 批量tensor转换和GPU传输（一次性）
        3. 预计算归一化参数（避免每帧重复创建）
        4. 延迟CPU同步：只在最后返回时同步一次
        5. 使用torch.nn.functional.normalize（比手动除法更快）
        
        预期性能提升：从~15ms降低到~5-8ms（取决于batch size和GPU）
        """
        if len(crops) == 0:
            return None, []

        # 快速过滤有效crops并收集索引
        valid_crops = []
        valid_idx = []
        for idx, c in enumerate(crops):
            if c is not None and c.size > 0:
                valid_crops.append(c)
                valid_idx.append(idx)  # 只记录有效crop的索引

        if len(valid_crops) == 0:
            return None, []

        # 批量预处理：使用cv2.resize（比PIL快）在CPU上预处理
        target_h, target_w = cfg.INPUT.SIZE_TRAIN[0], cfg.INPUT.SIZE_TRAIN[1]
        batch_tensors = []
        
        # 1. CPU预处理：resize和tensor转换（cv2比PIL快，且避免PIL对象创建开销）
        t_preprocess_start = time.perf_counter()
        for c in valid_crops:
            # cv2.resize比PIL快，且c已经是RGB格式
            resized = cv2.resize(c, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
            # 转换为tensor (H, W, C) -> (C, H, W)，值范围[0, 1]
            t = torch.from_numpy(resized).permute(2, 0, 1).float() / 255.0
            batch_tensors.append(t)
        t_preprocess = (time.perf_counter() - t_preprocess_start) * 1000
        
        # 2. 堆叠并移到GPU（一次性传输，使用non_blocking减少等待）
        t_transfer_start = time.perf_counter()
        batch = torch.stack(batch_tensors).to(self.device, non_blocking=True)
        t_transfer = (time.perf_counter() - t_transfer_start) * 1000
        
        # 3. 批量归一化（在GPU上，使用预计算的tensor避免重复创建）
        t_normalize_start = time.perf_counter()
        if not hasattr(self, '_norm_mean'):
            self._norm_mean = torch.tensor(cfg.INPUT.PIXEL_MEAN, device=self.device, dtype=torch.float32).view(1, 3, 1, 1)
            self._norm_std = torch.tensor(cfg.INPUT.PIXEL_STD, device=self.device, dtype=torch.float32).view(1, 3, 1, 1)
        batch = (batch - self._norm_mean) / self._norm_std
        t_normalize = (time.perf_counter() - t_normalize_start) * 1000

        # 4. 模型推理（保持所有操作在GPU上）
        import torch.nn.functional as F
        model = self.reid_model_match if match else self.reid_model
        t_inference_start = time.perf_counter()
        with torch.no_grad():
            feats = model(batch)
            # 使用F.normalize比手动除法更快
            feats = F.normalize(feats, p=2, dim=1)
        t_inference = (time.perf_counter() - t_inference_start) * 1000

        # 5. 不再同步到CPU，直接返回GPU tensor（避免CPU同步开销）
        # 相似度计算将在GPU上完成，只在最后需要numpy结果时才同步
        
        # 记录各阶段耗时（不包括CPU同步）
        total_time = t_preprocess + t_transfer + t_normalize + t_inference
        self.write_log(
            f"[特征提取耗时] batch_size={len(valid_crops)} | "
            f"预处理={t_preprocess:.2f}ms | "
            f"GPU传输={t_transfer:.2f}ms | "
            f"归一化={t_normalize:.2f}ms | "
            f"推理={t_inference:.2f}ms | "
            f"总计={total_time:.2f}ms (GPU上，未同步CPU)"
        )
        
        # 返回GPU tensor而不是numpy数组
        return feats, valid_idx

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
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {text}\n")
        except Exception:
            pass


    def write_log_time(self, text):
        try:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            with open(self.log_path_time, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {text}\n")
        except Exception:
            pass
    def random_bright_color_rgb(self,min_v: int = 80) -> list[int]:
        return [random.randint(min_v, 255), random.randint(min_v, 255), random.randint(min_v, 255)]
    # ============================================================
    #     Core: 处理单帧
    # ============================================================
    def process_frame(self, meta, model_ctx):

        total_start = time.perf_counter()

        # stream_id不再需要（不再创建轨迹）

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
            # 一开始就将BGR转换为RGB，后续所有操作都基于RGB格式
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        except:
            close_map(fd, mm)
            return

        # ============================================================
        #     1.YOLO 行人检测（TensorRT 版本，等价替换）
        # ============================================================
        t0 = time.perf_counter()

        yolo = model_ctx["yolo_trt"]

        # ---------- 1. letterbox ----------
        img_resize, r, (padw, padh) = self.letterbox(frame, 640)

        # ---------- 2. TensorRT 推理 ----------
        # ⚠️ TensorRT 版 YOLO 直接吃 numpy / cv2 image（HWC, uint8 / float32 都可）
        results = yolo(
            img_resize,
            conf=0.4,
            iou=0.5,
            classes=[0],     # person
            verbose=False
        )

        boxes = results[0].boxes
        dets = np.empty((0, 6), dtype=np.float32)

        detect_count = 0
        if boxes is not None and len(boxes) > 0:
            # ---------- 3. 取结果（与原版一致） ----------
            xyxy = boxes.xyxy.cpu().numpy()
            conf = boxes.conf.cpu().numpy()
            cls  = boxes.cls.cpu().numpy()

            detect_count = len(xyxy)

            # ---------- 4. 反 letterbox（完全一致） ----------
            xyxy[:, [0, 2]] -= padw
            xyxy[:, [1, 3]] -= padh
            xyxy /= r

            xyxy[:, 0] = np.clip(xyxy[:, 0], 0, width - 1)
            xyxy[:, 1] = np.clip(xyxy[:, 1], 0, height - 1)
            xyxy[:, 2] = np.clip(xyxy[:, 2], 0, width - 1)
            xyxy[:, 3] = np.clip(xyxy[:, 3], 0, height - 1)

            # ---------- 5. 拼 dets（结构完全一致） ----------
            dets = np.concatenate(
                [xyxy, conf.reshape(-1, 1), cls.reshape(-1, 1)],
                axis=1
            ).astype(np.float32)

        
        # --------------------------------- 删除
        # for det in dets:
        #     x1, y1, x2, y2, conf, cls_id = det

        #     x1, y1, x2, y2 = map(int, [x1, y1, x2, y2])
        #     cls_id = int(cls_id)
        #     # label 文本（可加置信度）
        #     label = f"persong {conf:.2f}"

        #     cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
        #     frame = self._put_chinese_text(
        #         frame,
        #         label,
        #         (x1, y1),
        #         (0, 0, 255),
        #         font_size=22
        #     )
        # ------------------------------------- 删除
        torch.cuda.synchronize()
        t_yolo = (time.perf_counter() - t0) * 1000
        
        # ============================================================
        #     2. 直接对检测结果进行ReID特征匹配
        # ============================================================
        t_reid_start = time.perf_counter()
        current_time = time.time()

        # 获取当前流的key（用于区分不同流）
        stream_key = meta.get("shmName", "default")  # 使用shmName作为流的唯一标识

        # 直接对检测框进行ReID，不使用SORT跟踪
        detections = []  # (x1, y1, x2, y2, target_sim, target_name, is_target)

        if detect_count > 0:
            # 直接对检测框进行特征提取和相似度计算
            crops = []
            crop_to_det = []  # 记录crop对应的检测框索引和bbox

            for det_idx, det in enumerate(dets):
                x1, y1, x2, y2, conf, cls_id = det
                x1, y1, x2, y2 = map(int, [x1, y1, x2, y2])
                crop = frame[y1:y2, x1:x2]
                if crop.size > 0:
                    crops.append(crop)
                    crop_to_det.append((det_idx, x1, y1, x2, y2))
            # crops = crops * 20
            # 批量提取特征
            if len(crops) > 0:
                t_batch = time.perf_counter()
                feats, valid_idx = self.extract_features_batch(crops, match=False)
                self.write_log(f"[ReID] stream={stream_key} 特征个数：{len(crops)}；batch特征提取耗时：{(time.perf_counter() - t_batch) * 1000}ms")
                
                # 批量计算所有特征与目标库的相似度（在GPU上计算，避免CPU同步）
                if self.target_feats_tensor is not None and len(feats) > 0:
                    # 在GPU上计算余弦相似度矩阵 (N, M)，其中N是检测框数量，M是目标库大小
                    import torch.nn.functional as F
                    t_sim_batch = time.perf_counter()
                    # feats 和 self.target_feats_tensor 都是GPU tensor，且已归一化
                    # 余弦相似度 = 点积（因为已归一化）
                    sim_matrix = torch.mm(feats, self.target_feats_tensor.t())  # shape: (N, M)
                    t_sim_gpu = (time.perf_counter() - t_sim_batch) * 1000
                    
                    # 在GPU上获取每个检测框的最大相似度和对应的索引
                    max_sims_tensor, best_indices_tensor = torch.max(sim_matrix, dim=1)  # shape: (N,)
                    
                    # 只在需要时同步到CPU（获取numpy数组）
                    t_sync_start = time.perf_counter()
                    # 同步整个相似度矩阵到CPU，用于多特征匹配
                    sim_matrix_cpu = sim_matrix.cpu().numpy()  # shape: (N, M)
                    max_sims = max_sims_tensor.cpu().numpy()  # shape: (N,)
                    best_indices = best_indices_tensor.cpu().numpy()  # shape: (N,)
                    t_sync = (time.perf_counter() - t_sync_start) * 1000
                    
                    self.write_log(f"[ReID] stream={stream_key} 特征个数：{len(feats)}；GPU相似度计算={t_sim_gpu:.2f}ms | CPU同步={t_sync:.2f}ms")
                    
                    # 对每个检测框进行多特征匹配
                    for feat_idx in range(len(valid_idx)):
                        crop_idx = valid_idx[feat_idx]
                        if crop_idx >= len(crop_to_det):
                            continue
                        
                        det_idx, x1, y1, x2, y2 = crop_to_det[crop_idx]
                        target_sim = float(max_sims[feat_idx])
                        best_idx = int(best_indices[feat_idx])
                        target_name = self.target_names[best_idx] if best_idx < len(self.target_names) else None
                        # feat_idx: 检测框在feats中的索引（0到N-1）
                        # best_idx: 目标库中的索引（0到M-1），与数据库记录顺序一致
                        
                        # 多特征匹配逻辑：检查该目标人物的所有特征中大于阈值的比例
                        # 如果是"冷佳旭"，多特征匹配比例设置为0.4，否则为0.5
                        multi_feature_threshold_ratio = 0.35 if target_name == "冷佳旭" else 0.5
                        
                        is_target = False
                        if target_sim >= self.target_sim_threshold and target_name and target_name != STRANGER_NAME:
                            # 获取该目标人物的所有特征索引
                            if target_name in self.target_name_to_indices:
                                target_indices = self.target_name_to_indices[target_name]
                                # 获取当前检测框与这些特征的相似度
                                target_sims = sim_matrix_cpu[feat_idx, target_indices]
                                # 计算大于阈值的特征数量
                                above_threshold_count = np.sum(target_sims >= self.target_sim_threshold)
                                # 计算比例
                                ratio = above_threshold_count / len(target_indices) if len(target_indices) > 0 else 0.0
                                
                                # 如果目标人物是"冷佳旭"且最大相似度大于阈值，统计每条特征的通过情况
                                if target_name == "冷佳旭" and target_sim >= self.target_sim_threshold:
                                    # 增加总检测次数
                                    self.lengjiaxu_total_detections += 1
                                    
                                    # 初始化统计（如果还没有）并更新每条特征的通过情况
                                    for i, target_idx in enumerate(target_indices):
                                        if target_idx not in self.lengjiaxu_feat_stats:
                                            self.lengjiaxu_feat_stats[target_idx] = {"total": 0, "pass": 0}
                                        # 更新统计
                                        self.lengjiaxu_feat_stats[target_idx]["total"] += 1
                                        if target_sims[i] >= self.target_sim_threshold:
                                            self.lengjiaxu_feat_stats[target_idx]["pass"] += 1
                                    
                                    # 输出每条特征的通过率（每条特征一行日志）
                                    if self.lengjiaxu_total_detections > 0:
                                        self.write_log(f"[冷佳旭特征通过率统计] 最大相似度大于阈值时，一共{self.lengjiaxu_total_detections}条记录：")
                                        for target_idx in sorted(target_indices):
                                            if target_idx in self.lengjiaxu_feat_stats:
                                                stats = self.lengjiaxu_feat_stats[target_idx]
                                                pass_rate = (stats["pass"] / stats["total"] * 100) if stats["total"] > 0 else 0.0
                                                image_name = self.index_to_employee_id.get(target_idx, "unknown")
                                                self.write_log(f"  feat_idx={target_idx} image_name={image_name}: 通过率={pass_rate:.2f}% ({stats['pass']}/{stats['total']})")
                                
                                # 记录所有特征的相似度，便于删除负面特征
                                sim_details = []
                                for i, sim_val in enumerate(target_sims):
                                    target_idx = target_indices[i]  # 在target_feats中的索引
                                    db_id = self.index_to_db_id.get(target_idx, "unknown")
                                    image_name = self.index_to_employee_id.get(target_idx, "unknown")
                                    is_above_threshold = "✓" if sim_val >= self.target_sim_threshold else "✗"
                                    # 显示完整的数据库ID和图片名称，便于后续删除负面特征
                                    sim_details.append(f"feat_idx={target_idx} image_name={image_name} sim={sim_val:.3f} {is_above_threshold}")
                                sim_details_str = " \n | ".join(sim_details)
                                self.write_log(f"[特征相似度详情] target={target_name} | 总特征数={len(target_indices)} | 大于阈值={above_threshold_count} | 比例={ratio:.2f} | \n 详情: {sim_details_str}")
                                
                                # 如果比例达到要求（例如50%），才认为是匹配
                                if ratio >= multi_feature_threshold_ratio:
                                    is_target = True
                                    self.write_log(f"[多特征匹配成功] target={target_name}, max_sim={target_sim:.3f}, ratio={ratio:.2f} ({above_threshold_count}/{len(target_indices)})")
                                else:
                                    self.write_log(f"[多特征匹配失败] target={target_name}, max_sim={target_sim:.3f}, ratio={ratio:.2f} ({above_threshold_count}/{len(target_indices)}) < {multi_feature_threshold_ratio}")
                            else:
                                # 如果目标人物没有其他特征，则只依赖最大相似度
                                is_target = True
                                self.write_log(f"[多特征匹配成功] target={target_name}, max_sim={target_sim:.3f}, 无其他特征")
                        
                        # 添加到detections列表
                        detections.append((x1, y1, x2, y2, target_sim, target_name, is_target))
                else:
                    # 如果没有目标库，所有检测框都是陌生人
                    for feat_idx in range(len(valid_idx)):
                        crop_idx = valid_idx[feat_idx]
                        if crop_idx >= len(crop_to_det):
                            continue
                        
                        det_idx, x1, y1, x2, y2 = crop_to_det[crop_idx]
                        detections.append((x1, y1, x2, y2, 0.0, None, False))
        
        t_reid = (time.perf_counter() - t_reid_start) * 1000
        
        # ============================================================
        #     3. 显示（单帧相似度判断，不创建轨迹）
        # ============================================================
        for det_item in detections:
            x1, y1, x2, y2, target_sim, target_name, is_target = det_item
            
            # 根据单帧相似度判断：超过阈值即为目标人物
            if is_target:
                color = (0, 255, 0)  # 绿色
                label = target_name if target_name else STRANGER_NAME
                self.write_log(f"[目标人物] sim={target_sim:.3f}, name={target_name}")
            else:
                color = (0, 0, 255)  # 红色
                label = STRANGER_NAME
                if target_sim > 0:
                    self.write_log(f"[陌生人] sim={target_sim:.3f} < 阈值 {self.target_sim_threshold}")
            if label == "冷佳旭1": # 正面特征
                label = "冷佳旭"
            # 绘制
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            frame = self._put_chinese_text(frame, label, (x1, y1), color, font_size=22)
        
        # ============================================================
        #     4. 写回共享内存
        # ============================================================
        # 写回共享内存前，将RGB转换回BGR（共享内存期望BGR格式）
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        for y in range(height):
            mm[y * stride:y * stride + width * 3] = frame_bgr[y].tobytes()

        close_map(fd, mm)
        self.write_log_time(f"yolo:{t_yolo:.2f}ms | det:{detect_count} | reid:{t_reid:.2f}ms | total: {((time.perf_counter() - total_start) * 1000):.2f}ms")

    # ============================================================
    #     init_model_context
    # ============================================================
    @staticmethod
    def init_model_context(
            yolo_weights="/home/guest/Documents/hxjm-monitor/mtx/python/models/yolov8n.pt",
            yolo_trt = "/home/guest/Documents/hxjm-monitor/mtx/python/reid/models/yolov8n.engine",
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
        print("[INIT] Loading YOLOv8 TRT ...")
        yolo_trt = YOLO(yolo_trt)
        ctx["yolo_trt"] = yolo_trt

        # SORT跟踪已删除，不再初始化tracker
        # print("[INIT] Loading HybridSORT ...")
        # tracker = create_tracker(...)
        # ctx["tracker"] = tracker

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
        #stream_id = meta.get("path", "")
        #if stream_id:
        #    return f"reid:{stream_id}"
        # 如果没有 path，尝试使用 shmName 作为备用
        shm_name = meta.get("shmName", "")
        if shm_name:
            return f"reid:{shm_name}"
        return "reid:default"


# ===========================================================
def main():

    print("[ReidServer] Starting ReID service...")
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
