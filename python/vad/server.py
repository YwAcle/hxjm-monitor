#!/usr/bin/env python3

import os
import sys
import cv2
import time
import numpy as np
import base64
import asyncio
import math
import torch
import clip
from datetime import datetime
from PIL import Image
import traceback
from pathlib import Path
import yaml
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from base.server_base import BaseServer
from base.postgresql.db_session import DBSession
from base.postgresql.config import DBConfig
from vad.model.detector import BehaviorDetector

DEFAULT_IPC_ADDR = "ipc:///tmp/py_ai_vad.ipc"
PYTHON_DIR = Path(__file__).resolve().parent.parent
DEFAULT_STREAM_CONFIG = PYTHON_DIR.parent / "mtx" / "config.yaml"
from ultralytics import YOLO


class VadServer(BaseServer):
    def __init__(self,create_server_socket: bool = True):
        addr = os.getenv("VAD_ZMQ_ADDR", DEFAULT_IPC_ADDR)
        super().__init__(addr)
        
        # ========== 日志 ==========
        os.makedirs("./log", exist_ok=True)
        self.log_path = "./log/vad_log.txt"
        with open(self.log_path, "w", encoding="utf-8") as f:
            f.write("====== VAD Detection Log ======\n")
            f.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Model: Yolo_nano_weights.pt\n")
            f.write("================================\n\n")
        yolo_model_path = Path(os.getenv(
            "VAD_YOLO_MODEL_PATH",
            str(PYTHON_DIR / "models" / "yolov8n.pt"),
        ))
        yolo_model = YOLO(str(yolo_model_path))
        self.yolo_model = yolo_model
        # 初始化数据库会话
        db_config = DBConfig(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "postgres"),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", "123456")
        )
        self.db = DBSession(config=db_config)
        self.recording_stream_map = self._load_recording_stream_map()
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
            # 初始化数据库操作并发控制信号量（主进程也需要）
            self._db_semaphore = asyncio.Semaphore(10)  # 最多10个并发数据库操作
            print("[INIT] 数据库连接池初始化完成")
        else:
            # 子进程模式：不在这里初始化，由 Worker.run 初始化
            print("[INIT] 子进程模式：数据库将在 Worker 中初始化")
        
        # ========== submit helper 用于后台执行数据库操作 ==========
        self._loop = None  # 在 Worker 中设置
        # 数据库操作并发控制信号量（限制同时执行的数据库操作数量）
        self._db_semaphore = None  # 在 Worker 中初始化为 asyncio.Semaphore(10)

    def _load_recording_stream_map(self):
        """Read VAD input-to-recording mappings from the ai_stream config."""
        config_path = Path(os.getenv("VAD_STREAM_CONFIG", str(DEFAULT_STREAM_CONFIG)))
        try:
            with config_path.open("r", encoding="utf-8") as stream:
                config = yaml.safe_load(stream) or {}
        except Exception as exc:
            raise RuntimeError(f"Unable to load VAD stream configuration: {config_path}: {exc}")

        mapping = {}
        streams = config.get("streams", [])
        for stream_config in streams:
            stream_name = str(stream_config.get("name", "")).strip()
            if not stream_name:
                continue
            for task in stream_config.get("ai_tasks", []):
                if str(task.get("type", "")).strip().lower() != "vad":
                    continue
                recording_stream = str(task.get("recording_stream", "")).strip()
                if not recording_stream:
                    raise RuntimeError(
                        f"VAD input stream '{stream_name}' is missing recording_stream in {config_path}"
                    )
                mapping[f"live/{stream_name}_vad"] = recording_stream

        if not mapping:
            raise RuntimeError(f"No VAD recording_stream mappings found in {config_path}")
        return mapping

    async def _select_recording_asset(self, vad_stream_id, event_ts):
        normalized_stream_id = str(vad_stream_id or "").strip()
        if normalized_stream_id and not normalized_stream_id.startswith("live/"):
            normalized_stream_id = "live/" + normalized_stream_id
        recording_stream_id = self.recording_stream_map.get(normalized_stream_id)
        if not recording_stream_id:
            self.write_log(
                f"  [VAD] [WARN] No recording stream mapping for input stream: {vad_stream_id}"
            )
            return None

        # MediaMTX publishes an index only when a segment closes. Keep the
        # original detection timestamp and wait briefly for that index instead
        # of linking the event to an arbitrary preceding segment.
        wait_seconds = max(0.0, float(os.getenv("VAD_MEDIA_ASSET_WAIT_SECONDS", "35")))
        retry_seconds = max(0.1, float(os.getenv("VAD_MEDIA_ASSET_RETRY_SECONDS", "0.5")))
        deadline = time.monotonic() + wait_seconds
        while True:
            asset = await self.db.select_media_asset_for_event(recording_stream_id, event_ts)
            if asset:
                return asset
            if time.monotonic() >= deadline:
                return None
            await asyncio.sleep(min(retry_seconds, max(0.0, deadline - time.monotonic())))

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
                    if len(err) > 100:
                        err = err[:100] + "…(truncated)"
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

    @staticmethod
    def init_model_context():
        # 加载暴力检测模型（打架检测）
        violence_model_path = Path(os.getenv(
            "VAD_VIOLENCE_MODEL_PATH",
            str(PYTHON_DIR / "models" / "Yolo_nano_weights.pt"),
        ))
        violence_model = YOLO(str(violence_model_path))
        
        # 加载火灾检测模型
        fire_model_path = Path(os.getenv(
            "VAD_FIRE_MODEL_PATH",
            str(PYTHON_DIR / "fire" / "best.pt"),
        ))
        fire_model = YOLO(str(fire_model_path))
        
        # 加载跌倒检测模型（使用pose模型，因为需要关键点检测）
        fall_model_path = Path(os.getenv(
            "VAD_FALL_MODEL_PATH",
            str(PYTHON_DIR / "vad" / "model" / "yolov8n-pose.pt"),
        ))
        fall_model = BehaviorDetector(
            model_path=str(fall_model_path),
            conf_threshold=0.3,
            iou_threshold=0.5,
        )
        
        # 加载CLIP模型（用于CLIP暴力检测）
        device = "cuda" if torch.cuda.is_available() else "cpu"
        clip_model, clip_preprocess = clip.load("ViT-B/32", device=device)
        clip_model.eval()
        
        # CLIP prompts（正 / 负类）
        fight_prompts = [
            "a violent fight between two people",
            "two people hitting each other",
            "two people fighting violently",
            "two people physically attacking each other",
            "two people punching and hitting each other",
            "two people engaged in violent physical combat"
        ]
        
        normal_prompts = [
            "people walking side by side",
            "people walking alongside each other",
            "people walking together peacefully"
        ]
        
        # 预先编码prompt文本特征
        with torch.no_grad():
            fight_text_features = clip_model.encode_text(
                clip.tokenize(fight_prompts).to(device)
            )
            fight_text_features /= fight_text_features.norm(dim=-1, keepdim=True)
            
            normal_text_features = clip_model.encode_text(
                clip.tokenize(normal_prompts).to(device)
            )
            normal_text_features /= normal_text_features.norm(dim=-1, keepdim=True)
        
        return {
            "fight_predictor": violence_model,  # 暴力检测模型（保持向后兼容）
            "fire_predictor": fire_model,  # 火灾检测模型
            "fall_predictor": fall_model,  # 跌倒检测模型
            "clip_model": clip_model,  # CLIP模型
            "clip_preprocess": clip_preprocess,  # CLIP预处理函数
            "clip_fight_text_features": fight_text_features,  # CLIP fight prompt特征
            "clip_normal_text_features": normal_text_features,  # CLIP normal prompt特征
            "clip_device": device  # CLIP设备
        }
    
    # ============================================================
    #     日志写入
    # ============================================================
    def write_log(self, text):
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except:
            pass

    def _detect_violence(self, frame: np.ndarray, yolo_model, stream_id: str) -> bool:
        """
        暴力检测算法（打架检测）
        
        Args:
            frame: 输入图像帧（BGR格式）
            yolo_model: YOLO模型实例
            stream_id: 流ID
            
        Returns:
            bool: 如果检测到violence并成功保存到数据库，返回True；否则返回False
        """
        # ----------------------------
        # 0. 预筛选规则：使用通用YOLO模型检测，检查是否有多个person且框有重叠
        # ----------------------------
        try:
            # 使用通用YOLO模型进行预检测
            pre_results = self.yolo_model(frame, conf=0.5, verbose=False)
            pre_dets = pre_results[0].boxes
            
            if pre_dets is None or len(pre_dets) == 0:
                # 未检测到任何目标，跳过暴力检测
                print(f"[VAD-Violence] ⚠️ 预检测未检测到目标，跳过暴力检测")
                self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VAD-Violence] 预检测未检测到目标，跳过暴力检测")
                return False
            
            # 获取类别名映射
            pre_names_attr = getattr(self.yolo_model, 'names', getattr(self.yolo_model.model, 'names', None))
            if isinstance(pre_names_attr, (list, tuple)):
                pre_names = {i: n for i, n in enumerate(pre_names_attr)}
            elif isinstance(pre_names_attr, dict):
                pre_names = pre_names_attr
            else:
                pre_names = {0: 'person'}  # 默认person类别ID为0
            
            # 获取所有检测结果
            pre_xyxy = pre_dets.xyxy.cpu().numpy()
            pre_confs = pre_dets.conf.cpu().numpy()
            pre_cls_ids = pre_dets.cls.cpu().numpy()
            
            # 筛选出person类别的目标
            person_boxes = []
            for i, cls_id in enumerate(pre_cls_ids):
                cls_id_int = int(cls_id)
                cls_name = pre_names.get(cls_id_int, str(cls_id_int))
                if cls_name == 'person':
                    person_boxes.append(pre_xyxy[i])
            
            # 检查是否有至少2个person目标
            if len(person_boxes) < 2:
                print(f"[VAD-Violence] ⚠️ 预检测到 {len(person_boxes)} 个person目标（需要>=2个），跳过暴力检测")
                self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VAD-Violence] 预检测到 {len(person_boxes)} 个person目标（需要>=2个），跳过暴力检测")
                return False
            
            # 计算两个框的中心点距离
            def calculate_center_distance(box1, box2):
                """计算两个框的中心点欧氏距离"""
                x1_1, y1_1, x2_1, y2_1 = box1
                x1_2, y1_2, x2_2, y2_2 = box2
                
                # 计算中心点
                cx1 = (x1_1 + x2_1) / 2.0
                cy1 = (y1_1 + y2_1) / 2.0
                cx2 = (x1_2 + x2_2) / 2.0
                cy2 = (y1_2 + y2_2) / 2.0
                
                # 计算欧氏距离
                distance = np.sqrt((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2)
                return distance
            
            # 设置中心点距离阈值（像素）
            # 可以根据实际场景调整，这里设置为200像素
            # 如果两个person的中心点距离小于阈值，认为他们距离较近，可能发生冲突
            center_distance_threshold = 200.0
            
            # 检查是否有任何两个person框的中心点距离小于阈值
            has_close_persons = False
            min_distance = float('inf')
            for i in range(len(person_boxes)):
                for j in range(i + 1, len(person_boxes)):
                    distance = calculate_center_distance(person_boxes[i], person_boxes[j])
                    min_distance = min(min_distance, distance)
                    if distance < center_distance_threshold:
                        has_close_persons = True
                        break
                if has_close_persons:
                    break
            
            if not has_close_persons:
                print(f"[VAD-Violence] ⚠️ 预检测到 {len(person_boxes)} 个person目标，但中心点距离均大于阈值 {center_distance_threshold}px（最小距离: {min_distance:.1f}px），跳过暴力检测")
                self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VAD-Violence] 预检测到 {len(person_boxes)} 个person目标，但中心点距离均大于阈值 {center_distance_threshold}px（最小距离: {min_distance:.1f}px），跳过暴力检测")
                return False
            
            # 预筛选通过，继续进行暴力检测
            print(f"[VAD-Violence] ✅ 预检测通过：检测到 {len(person_boxes)} 个person目标，且存在中心点距离小于阈值 {center_distance_threshold}px 的目标对（最小距离: {min_distance:.1f}px），继续进行暴力检测")
            self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VAD-Violence] 预检测通过：检测到 {len(person_boxes)} 个person目标，且存在中心点距离小于阈值 {center_distance_threshold}px 的目标对（最小距离: {min_distance:.1f}px），继续进行暴力检测")
            
        except Exception as e:
            print(f"[VAD-Violence] [ERROR] 预检测失败: {e}")
            self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VAD-Violence] [ERROR] 预检测失败: {e}")
            # 预检测失败时，可以选择跳过或继续，这里选择继续（保守策略）
            print(f"[VAD-Violence] ⚠️ 预检测失败，继续执行暴力检测（保守策略）")
        
        try:
            # ----------------------------
            # 1. YOLO 推理（暴力检测模型）
            # ----------------------------
            results = yolo_model(frame, conf=0.5, verbose=False)
            dets = results[0].boxes
        except Exception as e:
            print(f"[ERROR] YOLO inference failed: {e}")
            self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] YOLO inference failed: {e}")
            return False

        # ----------------------------
        # 2. 检查是否包含'violence'类别，只有存在violence时才绘制和保存
        # ----------------------------
        if dets is not None and len(dets) > 0:
            # 获取类别名映射（参考提供的代码逻辑）
            names_attr = getattr(yolo_model, 'names', getattr(yolo_model.model, 'names', None))
            if isinstance(names_attr, (list, tuple)):
                names = {i: n for i, n in enumerate(names_attr)}
            elif isinstance(names_attr, dict):
                names = names_attr
            else:
                names = {0: 'non_violence', 1: 'violence'}
            
            # 获取所有检测结果
            xyxy = dets.xyxy.cpu().numpy()
            confs = dets.conf.cpu().numpy()
            cls_ids = dets.cls.cpu().numpy()
            
            # 检查是否有'violence'类别
            has_violence = False
            for cls_id in cls_ids:
                cls_id_int = int(cls_id)
                cls_name = names.get(cls_id_int, str(cls_id_int))
                if cls_name == 'violence':
                    has_violence = True
                    break
            
            # 只有当存在'violence'类别时才进行后续操作
            if has_violence:
                try:
                    print(f"[VAD-Violence] ✅ YOLO 检测到 {len(dets)} 个目标，其中包含violence类别")
                    self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VAD-Violence] YOLO 检测到 {len(dets)} 个目标，其中包含violence类别")
                    
                    for i, box in enumerate(xyxy):
                        x1, y1, x2, y2 = box.astype(int)
                        cls_id = int(cls_ids[i])
                        conf = float(confs[i])

                        # 获取类别名
                        cls_name = names.get(cls_id, str(cls_id))

                        # 只绘制'violence'类别的框，跳过'non_violence'
                        if cls_name != 'violence':
                            continue

                        color = (0 ,0, 255)

                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                        cv2.putText(frame,
                                    f"{cls_name} {conf:.2f}",
                                    (x1, y1 - 5),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                        self.write_log(f"  [VAD-Violence] 检测到目标 {i+1}: {cls_name}, 置信度: {conf:.2f}, 位置: ({x1}, {y1}, {x2}, {y2})")
                    
                    # ----------------------------
                    # 3. 保存为base64并写入数据库（后台执行）
                    # ----------------------------
                    try:
                        # 将绘制好的图片编码为base64
                        success, buffer = cv2.imencode('.jpg', frame)
                        if success:
                            frame_base64 = base64.b64encode(buffer).decode('utf-8')
                            
                            # 记录当前时刻
                            t0 = datetime.now()
                            
                            # 后台执行：查询media_asset并写入数据库
                            async def _save_violence_vad():
                                max_retries = 3
                                retry_delay = 0.5
                                
                                for attempt in range(max_retries):
                                    try:
                                        if hasattr(self, '_db_semaphore') and self._db_semaphore is not None:
                                            async with self._db_semaphore:
                                                media_asset_record = await self._select_recording_asset(stream_id, t0)
                                                if media_asset_record and 'id' in media_asset_record:
                                                    media_asset_id = str(media_asset_record['id'])
                                                    self.write_log(f"  [VAD-Violence] 查询到media_asset_id: {media_asset_id}, 查询时间: {t0}")
                                                    db_id = await self.db.insert_vad(
                                                        media_asset_id=media_asset_id,
                                                        stream_id=stream_id,
                                                        frame_vad_base64=frame_base64,
                                                        anomaly_name='fight',
                                                        anomaly_level=3,
                                                        created_at=t0
                                                    )
                                                    print(f"[VAD-Violence] 👍 VAD结果已保存到数据库，ID: {db_id}")
                                                    self.write_log(f"  [VAD-Violence] VAD结果已保存到数据库，ID: {db_id}")
                                                    return
                                                else:
                                                    print(f"[VAD-Violence] [WARN] 未找到符合条件的media_asset记录，查询时间: {t0}")
                                                    self.write_log(f"  [VAD-Violence] [WARN] 未找到符合条件的media_asset记录，查询时间: {t0}")
                                                    return
                                        else:
                                            media_asset_record = await self._select_recording_asset(stream_id, t0)
                                            if media_asset_record and 'id' in media_asset_record:
                                                media_asset_id = str(media_asset_record['id'])
                                                self.write_log(f"  [VAD-Violence] 查询到media_asset_id: {media_asset_id}, 查询时间: {t0}")
                                                db_id = await self.db.insert_vad(
                                                    media_asset_id=media_asset_id,
                                                    stream_id=stream_id,
                                                    frame_vad_base64=frame_base64,
                                                    anomaly_name='fight',
                                                    anomaly_level=3,
                                                    created_at=t0
                                                )
                                                print(f"[VAD-Violence] 👍 VAD结果已保存到数据库，ID: {db_id}")
                                                self.write_log(f"  [VAD-Violence] VAD结果已保存到数据库，ID: {db_id}")
                                                return
                                            else:
                                                print(f"[VAD-Violence] [WARN] 未找到符合条件的media_asset记录，查询时间: {t0}")
                                                self.write_log(f"  [VAD-Violence] [WARN] 未找到符合条件的media_asset记录，查询时间: {t0}")
                                                return
                                    except Exception as e:
                                        error_str = str(e).lower()
                                        if 'too many clients' in error_str or 'connection' in error_str or 'timeout' in error_str:
                                            if attempt < max_retries - 1:
                                                wait_time = retry_delay * (2 ** attempt)
                                                print(f"[VAD-Violence] [WARN] 数据库连接错误（尝试 {attempt + 1}/{max_retries}），{wait_time:.1f}秒后重试: {e}")
                                                self.write_log(f"  [VAD-Violence] [WARN] 数据库连接错误（尝试 {attempt + 1}/{max_retries}），{wait_time:.1f}秒后重试: {e}")
                                                await asyncio.sleep(wait_time)
                                                continue
                                            else:
                                                print(f"[VAD-Violence] [ERROR] Failed to save VAD result to database after {max_retries} attempts: {e}")
                                                self.write_log(f"  [VAD-Violence] [ERROR] Failed to save VAD result to database after {max_retries} attempts: {e}")
                                                return
                                        else:
                                            print(f"[VAD-Violence] [ERROR] Failed to save VAD result to database: {e}")
                                            self.write_log(f"  [VAD-Violence] [ERROR] Failed to save VAD result to database: {e}")
                                            return
                            
                            # 提交后台任务
                            self.submit(_save_violence_vad())
                            return True
                        else:
                            print(f"[VAD-Violence] [ERROR] Failed to encode frame to base64")
                            self.write_log(f"  [ERROR] Failed to encode frame to base64")
                            return False
                    except Exception as e:
                        print(f"[ERROR] Failed to save VAD result to database: {e}")
                        self.write_log(f"  [ERROR] Failed to save VAD result to database: {e}")
                        return False
                        
                except Exception as e:
                    print(f"[ERROR] Failed to draw YOLO results: {e}")
                    self.write_log(f"  [ERROR] Failed to draw YOLO results: {e}")
                    return False
            else:
                # 检测到目标但没有violence类别，跳过处理
                print(f"[VAD-Violence] ❌ YOLO 检测到 {len(dets)} 个目标，但不包含violence类别，跳过处理")
                self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] YOLO 检测到 {len(dets)} 个目标，但不包含violence类别，跳过处理")
                return False
        else:
            print(f"[VAD-Violence] ❌ Violence YOLO 未检测到目标，跳过处理")
            self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] YOLO 未检测到目标，跳过处理")
            return False

    def _detect_violence_clip(self, frame: np.ndarray, model_ctx: dict, stream_id: str) -> bool:
        """
        CLIP暴力检测算法（打架检测）
        
        Args:
            frame: 输入图像帧（BGR格式）
            model_ctx: 模型上下文字典，包含CLIP模型和相关特征
            stream_id: 流ID
            
        Returns:
            bool: 如果检测到violence并成功保存到数据库，返回True；否则返回False
        """
        # 获取CLIP相关模型和特征
        clip_model = model_ctx.get("clip_model")
        clip_preprocess = model_ctx.get("clip_preprocess")
        fight_text_features = model_ctx.get("clip_fight_text_features")
        normal_text_features = model_ctx.get("clip_normal_text_features")
        device = model_ctx.get("clip_device", "cpu")
        
        # 检查CLIP模型和特征是否已加载（避免对Tensor使用all()导致布尔值歧义错误）
        if clip_model is None or clip_preprocess is None or fight_text_features is None or normal_text_features is None:
            print(f"[VAD-Violence-CLIP] ⚠️ CLIP模型或特征未加载，跳过CLIP暴力检测")
            return False
        
        try:
            # 工具函数
            def center(box):
                x1, y1, x2, y2 = box
                return ((x1 + x2) / 2, (y1 + y2) / 2)
            
            def calculate_distance(b1, b2):
                c1, c2 = center(b1), center(b2)
                return math.hypot(c1[0] - c2[0], c1[1] - c2[1])
            
            def merge_boxes(b1, b2):
                return [
                    min(b1[0], b2[0]),
                    min(b1[1], b2[1]),
                    max(b1[2], b2[2]),
                    max(b1[3], b2[3]),
                ]
            
            # YOLO推理（只检测person）
            results = self.yolo_model(frame, conf=0.5, classes=[0], verbose=False)
            dets = results[0].boxes
            
            if dets is None or len(dets) == 0:
                print(f"[VAD-Violence-CLIP] ⚠️ 未检测到person目标，跳过CLIP暴力检测")
                return False
            
            # 获取person框
            persons = []
            for box in dets:
                x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                persons.append([x1, y1, x2, y2])
            
            if len(persons) < 2:
                print(f"[VAD-Violence-CLIP] ⚠️ 检测到 {len(persons)} 个person目标（需要>=2个），跳过CLIP暴力检测")
                return False
            
            # 找交互对（距离小于阈值的person对）
            candidate_boxes = []
            
            # 使用相对距离阈值（基于图像对角线长度的比例）
            frame_height, frame_width = frame.shape[:2]
            frame_diagonal = math.sqrt(frame_width ** 2 + frame_height ** 2)
            # 使用图像对角线的15%作为相对距离阈值
            distance_threshold_ratio = 0.10
            distance_threshold = frame_diagonal * distance_threshold_ratio
            
            min_distance = float('inf')
            for i in range(len(persons)):
                for j in range(i + 1, len(persons)):
                    dist = calculate_distance(persons[i], persons[j])
                    min_distance = min(min_distance, dist)
                    if dist < distance_threshold:
                        candidate_boxes.append(merge_boxes(persons[i], persons[j]))
            
            if not candidate_boxes:
                print(f"[VAD-Violence-CLIP] ⚠️ 最近相距{min_distance:.1f}px（相对阈值：{distance_threshold:.1f}px，图像对角线{distance_threshold_ratio*100:.0f}%），跳过CLIP暴力检测")
                self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VAD-Violence-CLIP] ⚠️ 最近相距{min_distance:.1f}px（相对阈值：{distance_threshold:.1f}px，图像对角线{distance_threshold_ratio*100:.0f}%），跳过CLIP暴力检测")
                return False
            
            # CLIP判断
            has_fight = False
            max_diff_score = -float('inf')
            best_box = None
            
            for box in candidate_boxes:
                x1, y1, x2, y2 = map(int, box)
                roi = frame[y1:y2, x1:x2]
                if roi.size == 0:
                    continue
                
                # 转换为PIL图像并预处理
                roi_pil = Image.fromarray(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB))
                roi_tensor = clip_preprocess(roi_pil).unsqueeze(0).to(device)
                
                with torch.no_grad():
                    image_features = clip_model.encode_image(roi_tensor)
                    image_features /= image_features.norm(dim=-1, keepdim=True)
                    
                    fight_sim = (image_features @ fight_text_features.T)[0]
                    normal_sim = (image_features @ normal_text_features.T)[0]
                    
                    # 确保转换为Python标量
                    fight_score = float(fight_sim.mean().item())
                    normal_score = float(normal_sim.mean().item())
                    diff_score = float(fight_score - normal_score)
                    self.write_log(
                        f"[CLIP] fight={fight_score:.3f}, "
                        f"normal={normal_score:.3f}, "
                        f"diff={diff_score:.3f}"
                    )
                # 判定阈值（Demo推荐0.08左右）
                threshold = 0.065
                if diff_score > threshold:
                    has_fight = True
                    if diff_score > max_diff_score:
                        max_diff_score = diff_score
                        best_box = (x1, y1, x2, y2)
            
            # 如果检测到violence，绘制并保存
            if has_fight and best_box:
                try:
                    x1, y1, x2, y2 = best_box
                    color = (0, 0, 255)
                    label = f"FIGHT {max_diff_score:.2f}"
                    
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
                    cv2.putText(frame, label, (x1, y1 - 10),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                    
                    print(f"[VAD-Violence-CLIP] ✅ 检测到violence，diff_score: {max_diff_score:.3f}")
                    self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VAD-Violence-CLIP] 检测到violence，diff_score: {max_diff_score:.3f}, 距离: {min_distance:.1f}px （阈值：{distance_threshold:.1f}px）")
                    
                    # 保存为base64并写入数据库（后台执行）
                    try:
                        success, buffer = cv2.imencode('.jpg', frame)
                        if success:
                            frame_base64 = base64.b64encode(buffer).decode('utf-8')
                            t0 = datetime.now()
                            
                            # 后台执行：查询media_asset并写入数据库
                            async def _save_violence_clip_vad():
                                max_retries = 3
                                retry_delay = 0.5  # 初始延迟0.5秒
                                
                                for attempt in range(max_retries):
                                    try:
                                        # 使用信号量限制并发数据库操作（如果已初始化）
                                        if hasattr(self, '_db_semaphore') and self._db_semaphore is not None:
                                            async with self._db_semaphore:
                                                media_asset_record = await self._select_recording_asset(stream_id, t0)
                                                
                                                if media_asset_record and 'id' in media_asset_record:
                                                    media_asset_id = str(media_asset_record['id'])
                                                    self.write_log(f"  [VAD-Violence-CLIP] 查询到media_asset_id: {media_asset_id}, 查询时间: {t0}")
                                                    
                                                    db_id = await self.db.insert_vad(
                                                        media_asset_id=media_asset_id,
                                                        stream_id=stream_id,
                                                        frame_vad_base64=frame_base64,
                                                        anomaly_name='fight',
                                                        anomaly_level=3,
                                                        created_at=t0
                                                    )
                                                    print(f"[VAD-Violence-CLIP] ✅ VAD结果已保存到数据库，ID: {db_id}")
                                                    self.write_log(f"  [VAD-Violence-CLIP] VAD结果已保存到数据库，ID: {db_id}")
                                                    return  # 成功，退出重试循环
                                                else:
                                                    print(f"[VAD-Violence-CLIP] [WARN] 未找到符合条件的media_asset记录，查询时间: {t0}")
                                                    self.write_log(f"  [VAD-Violence-CLIP] [WARN] 未找到符合条件的media_asset记录，查询时间: {t0}")
                                                    return  # 不是数据库连接错误，不重试
                                        else:
                                            # 没有信号量时直接执行（向后兼容）
                                            media_asset_record = await self._select_recording_asset(stream_id, t0)
                                            
                                            if media_asset_record and 'id' in media_asset_record:
                                                media_asset_id = str(media_asset_record['id'])
                                                self.write_log(f"  [VAD-Violence-CLIP] 查询到media_asset_id: {media_asset_id}, 查询时间: {t0}")
                                                
                                                db_id = await self.db.insert_vad(
                                                    media_asset_id=media_asset_id,
                                                    stream_id=stream_id,
                                                frame_vad_base64=frame_base64,
                                                anomaly_name='fight',
                                                anomaly_level=3,
                                                created_at=t0
                                                )
                                                print(f"[VAD-Violence-CLIP] ✅ VAD结果已保存到数据库，ID: {db_id}")
                                                self.write_log(f"  [VAD-Violence-CLIP] VAD结果已保存到数据库，ID: {db_id}")
                                                return  # 成功，退出重试循环
                                            else:
                                                print(f"[VAD-Violence-CLIP] [WARN] 未找到符合条件的media_asset记录，查询时间: {t0}")
                                                self.write_log(f"  [VAD-Violence-CLIP] [WARN] 未找到符合条件的media_asset记录，查询时间: {t0}")
                                                return  # 不是数据库连接错误，不重试
                                    except Exception as e:
                                        error_str = str(e).lower()
                                        # 检查是否是连接池相关的错误
                                        if 'too many clients' in error_str or 'connection' in error_str or 'timeout' in error_str:
                                            if attempt < max_retries - 1:
                                                wait_time = retry_delay * (2 ** attempt)  # 指数退避
                                                print(f"[VAD-Violence-CLIP] [WARN] 数据库连接错误（尝试 {attempt + 1}/{max_retries}），{wait_time:.1f}秒后重试: {e}")
                                                self.write_log(f"  [VAD-Violence-CLIP] [WARN] 数据库连接错误（尝试 {attempt + 1}/{max_retries}），{wait_time:.1f}秒后重试: {e}")
                                                await asyncio.sleep(wait_time)
                                                continue
                                            else:
                                                print(f"[VAD-Violence-CLIP] [ERROR] Failed to save VAD result to database after {max_retries} attempts: {e}")
                                                self.write_log(f"  [VAD-Violence-CLIP] [ERROR] Failed to save VAD result to database after {max_retries} attempts: {e}")
                                                return
                                        else:
                                            # 其他错误不重试
                                            print(f"[VAD-Violence-CLIP] [ERROR] Failed to save VAD result to database: {e}")
                                            self.write_log(f"  [VAD-Violence-CLIP] [ERROR] Failed to save VAD result to database: {e}")
                                            return
                            
                            # 提交后台任务
                            self.submit(_save_violence_clip_vad())
                            return True
                        else:
                            print(f"[VAD-Violence-CLIP] [ERROR] Failed to encode frame to base64")
                            self.write_log(f"  [ERROR] Failed to encode frame to base64")
                            return False
                    except Exception as e:
                        print(f"[VAD-Violence-CLIP] [ERROR] Failed to save VAD result: {e}")
                        self.write_log(f"  [ERROR] Failed to save VAD result: {e}")
                        return False
                        
                except Exception as e:
                    print(f"[VAD-Violence-CLIP] [ERROR] Failed to draw CLIP results: {e}")
                    self.write_log(f"  [ERROR] Failed to draw CLIP results: {e}")
                    return False
            else:
                print(f"[VAD-Violence-CLIP] ❌ 目标相距{min_distance:.1f}px（相对阈值：{distance_threshold:.1f}px，图像对角线{distance_threshold_ratio*100:.0f}%），未检测到violence（所有candidate的diff_score <= 0.08）")
                self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VAD-Violence-CLIP] ❌ 目标相距{min_distance:.1f}px（相对阈值：{distance_threshold:.1f}px，图像对角线{distance_threshold_ratio*100:.0f}%），未检测到violence（所有candidate的diff_score <= 0.08）")
                return False
                
        except Exception as e:
            print(f"[VAD-Violence-CLIP] [ERROR] CLIP violence detection failed: {e}")
            self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VAD-Violence-CLIP] [ERROR] CLIP violence detection failed: {e}")
            return False

    def _detect_fire(self, frame: np.ndarray, yolo_model, stream_id: str) -> bool:
        """
        火灾检测算法
        
        Args:
            frame: 输入图像帧（BGR格式）
            yolo_model: YOLO模型实例（火灾检测模型）
            stream_id: 流ID
            
        Returns:
            bool: 如果检测到火灾并成功保存到数据库，返回True；否则返回False
        """
        try:
            # ----------------------------
            # 1. YOLO 推理
            # ----------------------------
            results = yolo_model(frame, conf=0.5, verbose=False)
            dets = results[0].boxes
        except Exception as e:
            print(f"[ERROR] Fire YOLO inference failed: {e}")
            self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] Fire YOLO inference failed: {e}")
            return False

        # ----------------------------
        # 2. 检查是否包含火灾相关类别，只有存在时才绘制和保存
        # ----------------------------
        if dets is not None and len(dets) > 0:
            # 获取类别名映射
            names_attr = getattr(yolo_model, 'names', getattr(yolo_model.model, 'names', None))
            if isinstance(names_attr, (list, tuple)):
                names = {i: n for i, n in enumerate(names_attr)}
            elif isinstance(names_attr, dict):
                names = names_attr
            else:
                names = yolo_model.model.names if hasattr(yolo_model, 'model') else {}
            
            # 获取所有检测结果
            xyxy = dets.xyxy.cpu().numpy()
            confs = dets.conf.cpu().numpy()
            cls_ids = dets.cls.cpu().numpy()
            
            # 检查是否有火灾相关类别（fire, smoke等）
            has_fire = False
            fire_keywords = ['fire', 'smoke', 'flame']  # 可能的火灾相关关键词
            
            for cls_id in cls_ids:
                cls_id_int = int(cls_id)
                cls_name = names.get(cls_id_int, str(cls_id_int))
                cls_name_lower = str(cls_name).lower()
                # 检查类别名是否包含火灾关键词
                if any(keyword in cls_name_lower for keyword in fire_keywords):
                    has_fire = True
                    break
            
            # 只有当存在火灾相关类别时才进行后续操作
            if has_fire:
                try:
                    print(f"[VAD-Fire] ✅ Fire YOLO 检测到 {len(dets)} 个目标，其中包含火灾类别")
                    self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Fire YOLO 检测到 {len(dets)} 个目标，其中包含火灾类别")
                    
                    for i, box in enumerate(xyxy):
                        x1, y1, x2, y2 = box.astype(int)
                        cls_id = int(cls_ids[i])
                        conf = float(confs[i])

                        # 获取类别名
                        cls_name = names.get(cls_id, str(cls_id))

                        color = (0, 255, 0)  # 绿色框表示火灾

                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                        cv2.putText(frame,
                                    f"{cls_name} {conf:.2f}",
                                    (x1, y1 - 5),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                        self.write_log(f"  检测到目标 {i+1}: {cls_name}, 置信度: {conf:.2f}, 位置: ({x1}, {y1}, {x2}, {y2})")
                    
                    # ----------------------------
                    # 3. 保存为base64并写入数据库（后台执行）
                    # ----------------------------
                    try:
                        # 将绘制好的图片编码为base64
                        success, buffer = cv2.imencode('.jpg', frame)
                        if success:
                            frame_base64 = base64.b64encode(buffer).decode('utf-8')
                            
                            # 记录当前时刻
                            t0 = datetime.now()
                            
                            # 后台执行：查询media_asset并写入数据库
                            async def _save_fire_vad():
                                max_retries = 3
                                retry_delay = 0.5
                                
                                for attempt in range(max_retries):
                                    try:
                                        if hasattr(self, '_db_semaphore') and self._db_semaphore is not None:
                                            async with self._db_semaphore:
                                                media_asset_record = await self._select_recording_asset(stream_id, t0)
                                                if media_asset_record and 'id' in media_asset_record:
                                                    media_asset_id = str(media_asset_record['id'])
                                                    self.write_log(f"  查询到media_asset_id: {media_asset_id}, 查询时间: {t0}")
                                                    db_id = await self.db.insert_vad(
                                                        media_asset_id=media_asset_id,
                                                        stream_id=stream_id,
                                                        frame_vad_base64=frame_base64,
                                                        anomaly_name='fire',
                                                        anomaly_level=4,
                                                        created_at=t0
                                                    )
                                                    print(f"[VAD-Fire] 👍 Fire VAD结果已保存到数据库，ID: {db_id}")
                                                    self.write_log(f"  [VAD-Fire] Fire VAD结果已保存到数据库，ID: {db_id}")
                                                    return
                                                else:
                                                    print(f"[VAD-Fire] [WARN] 未找到符合条件的media_asset记录，查询时间: {t0}")
                                                    self.write_log(f"  [VAD-Fire] [WARN] 未找到符合条件的media_asset记录，查询时间: {t0}")
                                                    return
                                        else:
                                            media_asset_record = await self._select_recording_asset(stream_id, t0)
                                            if media_asset_record and 'id' in media_asset_record:
                                                media_asset_id = str(media_asset_record['id'])
                                                self.write_log(f"  查询到media_asset_id: {media_asset_id}, 查询时间: {t0}")
                                                db_id = await self.db.insert_vad(
                                                    media_asset_id=media_asset_id,
                                                    stream_id=stream_id,
                                                frame_vad_base64=frame_base64,
                                                anomaly_name='fire',
                                                anomaly_level=4,
                                                created_at=t0
                                                )
                                                print(f"[VAD-Fire] 👍 Fire VAD结果已保存到数据库，ID: {db_id}")
                                                self.write_log(f"  [VAD-Fire] Fire VAD结果已保存到数据库，ID: {db_id}")
                                                return
                                            else:
                                                print(f"[VAD-Fire] [WARN] 未找到符合条件的media_asset记录，查询时间: {t0}")
                                                self.write_log(f"  [VAD-Fire] [WARN] 未找到符合条件的media_asset记录，查询时间: {t0}")
                                                return
                                    except Exception as e:
                                        error_str = str(e).lower()
                                        if 'too many clients' in error_str or 'connection' in error_str or 'timeout' in error_str:
                                            if attempt < max_retries - 1:
                                                wait_time = retry_delay * (2 ** attempt)
                                                print(f"[VAD-Fire] [WARN] 数据库连接错误（尝试 {attempt + 1}/{max_retries}），{wait_time:.1f}秒后重试: {e}")
                                                self.write_log(f"  [VAD-Fire] [WARN] 数据库连接错误（尝试 {attempt + 1}/{max_retries}），{wait_time:.1f}秒后重试: {e}")
                                                await asyncio.sleep(wait_time)
                                                continue
                                            else:
                                                print(f"[VAD-Fire] [ERROR] Failed to save Fire VAD result to database after {max_retries} attempts: {e}")
                                                self.write_log(f"  [VAD-Fire] [ERROR] Failed to save Fire VAD result to database after {max_retries} attempts: {e}")
                                                return
                                        else:
                                            print(f"[VAD-Fire] [ERROR] Failed to save Fire VAD result to database: {e}")
                                            self.write_log(f"  [VAD-Fire] [ERROR] Failed to save Fire VAD result to database: {e}")
                                            return
                            
                            # 提交后台任务
                            self.submit(_save_fire_vad())
                            return True
                        else:
                            print(f"[ERROR] Failed to encode frame to base64")
                            self.write_log(f"  [ERROR] Failed to encode frame to base64")
                            return False
                    except Exception as e:
                        print(f"[VAD-Fire] [ERROR] Failed to save Fire VAD result to database: {e}")
                        self.write_log(f"  [VAD-Fire] [ERROR] Failed to save Fire VAD result to database: {e}")
                        return False
                        
                except Exception as e:
                    print(f"[VAD-Fire] [ERROR] Failed to draw Fire YOLO results: {e}")
                    self.write_log(f"  [VAD-Fire] [ERROR] Failed to draw Fire YOLO results: {e}")
                    return False
            else:
                # 检测到目标但没有火灾类别，跳过处理
                print(f"[VAD-Fire] ❌ Fire YOLO 检测到 {len(dets)} 个目标，但不包含火灾类别，跳过处理")
                self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VAD-Fire]  Fire YOLO 检测到 {len(dets)} 个目标，但不包含火灾类别，跳过处理")
                return False
        else:
            print(f"[VAD-Fire] ❌ Fire YOLO 未检测到目标，跳过处理")
            self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VAD-Fire] Fire YOLO 未检测到目标，跳过处理")
            return False
    def _detect_fall(self, frame: np.ndarray, fall_model: BehaviorDetector, stream_id: str) -> bool:
        """
        跌倒检测算法
        
        Args:
            frame: 输入图像帧（BGR格式）
            fall_model: BehaviorDetector模型实例
            stream_id: 流ID
            
        Returns:
            bool: 如果检测到跌倒并成功保存到数据库，返回True；否则返回False
        """
        try:
            # ----------------------------
            # 1. 调用detect_frame方法获取推理结果
            # ----------------------------
            # 检查模型是否已加载
            if fall_model.model is None:
                print(f"[VAD-Fall] [ERROR] 模型未加载")
                self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VAD-Fall] [ERROR] 模型未加载")
                return False
            
            result = fall_model.detect_frame(frame)
            # print(f"[VAD-Fall] 推理结果: {result}")
            self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VAD-Fall] 推理结果: person_count={result.get('person_count', 0)}, has_abnormal={result.get('has_abnormal', False)}, behavior_type={result.get('behavior_type')}")
            
            # 检查是否检测到跌倒事件
            if not result.get('has_abnormal', False) or result.get('behavior_type') != 'FALL':
                # 未检测到跌倒，跳过处理
                if result.get('person_count', 0) == 0:
                    print(f"[VAD-Fall] ❌ 未检测到人员")
                else:
                    print(f"[VAD-Fall] ❌ 检测到 {result.get('person_count', 0)} 人，但未检测到跌倒行为")
                return False
            
            try:
                print(f"[VAD-Fall] ✅ Fall检测到跌倒行为，置信度: {result.get('confidence', 0.0):.2f}")
                self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VAD-Fall] Fall检测到跌倒行为: {result.get('description', '')}, 置信度: {result.get('confidence', 0.0):.2f}")
                
                # ----------------------------
                # 2. 调用_visualize_detection方法获取可视化图片
                # ----------------------------
                # 需要重新进行推理以获取原始的results对象用于可视化
                # 注意：这里需要重新推理，因为detect_frame没有返回原始的results
                # 自动检测设备（优先使用GPU，如果不可用则使用CPU）
                device = "cuda:0" if torch.cuda.is_available() else "cpu"
                results = fall_model.model(
                    frame,
                    conf=fall_model.conf_threshold,
                    iou=fall_model.iou_threshold,
                    device=device,
                )
                
                # 调用可视化方法
                vis_image = fall_model._visualize_detection(frame, results, result)
                self.write_log(f"[FALL-result] {result}")
                # 将可视化图片编码为base64
                success, buffer = cv2.imencode('.jpg', vis_image)
                if not success:
                    print(f"[VAD-Fall] [ERROR] Failed to encode fall visualization frame to base64")
                    self.write_log(f"  [VAD-Fall] [ERROR] Failed to encode fall visualization frame to base64")
                    return False
                
                frame_base64 = base64.b64encode(buffer).decode('utf-8')
                
                # ----------------------------
                # 3. 保存为base64并写入数据库（后台执行）
                # ----------------------------
                try:
                    # 记录当前时刻
                    t0 = datetime.now()
                    
                    # 后台执行：查询media_asset并写入数据库
                    async def _save_fall_vad():
                        max_retries = 3
                        retry_delay = 0.5
                        
                        for attempt in range(max_retries):
                            try:
                                if hasattr(self, '_db_semaphore') and self._db_semaphore is not None:
                                    async with self._db_semaphore:
                                        media_asset_record = await self._select_recording_asset(stream_id, t0)
                                        if media_asset_record and 'id' in media_asset_record:
                                            media_asset_id = str(media_asset_record['id'])
                                            self.write_log(f"  [VAD-Fall] 查询到media_asset_id: {media_asset_id}, 查询时间: {t0}")
                                            db_id = await self.db.insert_vad(
                                                media_asset_id=media_asset_id,
                                                stream_id=stream_id,
                                                frame_vad_base64=frame_base64,
                                                anomaly_name='fall',
                                                anomaly_level=2,
                                                created_at=t0
                                            )
                                            print(f"[VAD-Fall] 👍 Fall VAD结果已保存到数据库，ID: {db_id}")
                                            self.write_log(f"  [VAD-Fall] Fall VAD结果已保存到数据库，ID: {db_id}")
                                            return
                                        else:
                                            print(f"[VAD-Fall] [WARN] 未找到符合条件的media_asset记录，查询时间: {t0}")
                                            self.write_log(f"  [VAD-Fall] [WARN] 未找到符合条件的media_asset记录，查询时间: {t0}")
                                            return
                                else:
                                    media_asset_record = await self._select_recording_asset(stream_id, t0)
                                    if media_asset_record and 'id' in media_asset_record:
                                        media_asset_id = str(media_asset_record['id'])
                                        self.write_log(f"  [VAD-Fall] 查询到media_asset_id: {media_asset_id}, 查询时间: {t0}")
                                        db_id = await self.db.insert_vad(
                                            media_asset_id=media_asset_id,
                                            stream_id=stream_id,
                                        frame_vad_base64=frame_base64,
                                        anomaly_name='fall',
                                        anomaly_level=2,
                                        created_at=t0
                                        )
                                        print(f"[VAD-Fall] 👍 Fall VAD结果已保存到数据库，ID: {db_id}")
                                        self.write_log(f"  [VAD-Fall] Fall VAD结果已保存到数据库，ID: {db_id}")
                                        return
                                    else:
                                        print(f"[VAD-Fall] [WARN] 未找到符合条件的media_asset记录，查询时间: {t0}")
                                        self.write_log(f"  [VAD-Fall] [WARN] 未找到符合条件的media_asset记录，查询时间: {t0}")
                                        return
                            except Exception as e:
                                error_str = str(e).lower()
                                if 'too many clients' in error_str or 'connection' in error_str or 'timeout' in error_str:
                                    if attempt < max_retries - 1:
                                        wait_time = retry_delay * (2 ** attempt)
                                        print(f"[VAD-Fall] [WARN] 数据库连接错误（尝试 {attempt + 1}/{max_retries}），{wait_time:.1f}秒后重试: {e}")
                                        self.write_log(f"  [VAD-Fall] [WARN] 数据库连接错误（尝试 {attempt + 1}/{max_retries}），{wait_time:.1f}秒后重试: {e}")
                                        await asyncio.sleep(wait_time)
                                        continue
                                    else:
                                        print(f"[VAD-Fall] [ERROR] Failed to save Fall VAD result to database after {max_retries} attempts: {e}")
                                        self.write_log(f"  [VAD-Fall] [ERROR] Failed to save Fall VAD result to database after {max_retries} attempts: {e}")
                                        return
                                else:
                                    print(f"[VAD-Fall] [ERROR] Failed to save Fall VAD result to database: {e}")
                                    self.write_log(f"  [VAD-Fall] [ERROR] Failed to save Fall VAD result to database: {e}")
                                    return
                    
                    # 提交后台任务
                    self.submit(_save_fall_vad())
                    return True
                except Exception as e:
                    print(f"[VAD-Fall] [ERROR] Failed to submit Fall VAD save task: {e}")
                    self.write_log(f"  [VAD-Fall] [ERROR] Failed to submit Fall VAD save task: {e}")
                    return False
                    
            except Exception as e:
                print(f"[VAD-Fall] [ERROR] Failed to visualize or save Fall detection results: {e}")
                self.write_log(f"  [ERROR] Failed to visualize or save Fall detection results: {e}")
                return False
                
        except Exception as e:
            print(f"[ERROR] Fall detection failed: {e}")
            self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] Fall detection failed: {e}")
            return False
    def process_frame(self, meta: dict, model_ctx: dict):
        """
           读取base64 → YOLO 检测 → 绘制 → 保存为base64 → 写入数据库
        """
        width = int(meta.get("width", 0))
        height = int(meta.get("height", 0))
        stride = int(meta.get("stride", width * 3))
        channels = int(meta.get("channels", 3))
        b64 = meta.get("base64", "")
        stream_id = meta.get("path", "vad")
        try:
            # ----------------------------
            # 1. 从base64解码帧
            # ----------------------------
            try:
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
                
                # 转换为numpy数组
                buf = np.frombuffer(rgb, dtype=np.uint8)
                frame = buf.reshape((height, width, channels))
                
                # BGR格式（如果是RGB需要转换）
                if channels == 3:
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            except Exception as e:
                print(f"[ERROR] Failed to decode frame from base64: {e}")
                self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] Failed to decode frame from base64: {e}")
                return  # 不处理该帧，但不中断主循环

            # ----------------------------
            # 2. 调用各种检测算法
            # ----------------------------
            # 调用暴力检测算法（打架检测）
            print(f"[INFO] 开始推理异常检测算法，当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            yolo_violence_model = model_ctx.get("fight_predictor")
            # if yolo_violence_model:
            #     self._detect_violence(frame, yolo_violence_model, stream_id)
            # clip 暴力检测算法
            self._detect_violence_clip(frame, model_ctx, stream_id)

            # 调用火灾检测算法
            yolo_fire_model = model_ctx.get("fire_predictor")
            if yolo_fire_model:
                self._detect_fire(frame, yolo_fire_model, stream_id)
                
            # 调用跌倒检测算法
            fall_model = model_ctx.get("fall_predictor")
            if fall_model:
                self._detect_fall(frame, fall_model, stream_id)
            
            # TODO: 后续可以在这里集成其他检测算法，例如：
            # - self._detect_fall(frame, fall_model, stream_id)  # 跌倒检测
            # - self._detect_intrusion(frame, intrusion_model, stream_id)  # 入侵检测

        except Exception as e:
            print(f"[FATAL] Unexpected processing error: {traceback.format_exc()}")
            self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [FATAL] Unexpected processing error: {traceback.format_exc()}")

    def select_worker_key(self, meta: dict) -> str:
        stream_name = meta.get("streamName", "")
        if stream_name:
            return f"VAD:{stream_name}"
        return "VAD:default"


def main():
    print("[VadServer] Starting VAD AI service...", flush=True)
    server = VadServer()
    print(f"[VadServer] Binding to {server.addr}", flush=True)
    print(f"[VadServer] Waiting for requests...", flush=True)
    try:
        server.serve()
    finally:
        # 关闭数据库连接（只在主进程中关闭）
        try:
            if hasattr(server, 'db') and server.db:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果事件循环正在运行，使用 submit 方法
                    server.submit(server.db.close())
                else:
                    loop.run_until_complete(server.db.close())
        except:
            pass


if __name__ == "__main__":
    main()
