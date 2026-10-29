#!/usr/bin/env python3

import os
import sys
import cv2
import time
import numpy as np
import base64
import asyncio
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from base.server_base import BaseServer
from base.postgresql.db_session import DBSession
from base.postgresql.config import DBConfig
from vad.model.detector import BehaviorDetector

DEFAULT_IPC_ADDR = "ipc:///tmp/py_ai_vad.ipc"
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
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d')}\n")
            f.write(f"Model: Yolo_nano_weights.pt\n")
            f.write("================================\n\n")
        
        # 初始化数据库会话
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
        violence_model_path = "/home/guest/Documents/hxjm-monitor/mtx/python/models/Yolo_nano_weights.pt"
        violence_model = YOLO(violence_model_path)
        
        # 加载火灾检测模型
        fire_model_path = "/home/guest/Documents/hxjm-monitor/mtx/python/fire/best.pt"
        fire_model = YOLO(fire_model_path)
        
        # 加载跌倒检测模型（使用pose模型，因为需要关键点检测）
        fall_model_path = "/home/guest/Documents/hxjm-monitor/mtx/python/vad/model/yolov8n-pose.pt"
        fall_model = BehaviorDetector(model_path=fall_model_path, conf_threshold=0.3, iou_threshold=0.5)
        return {
            "fight_predictor": violence_model,  # 暴力检测模型（保持向后兼容）
            "fire_predictor": fire_model,  # 火灾检测模型
            "fall_predictor": fall_model  # 跌倒检测模型
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
        try:
            # ----------------------------
            # 1. YOLO 推理
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

                        color = (255,0, 0)

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
                                try:
                                    # 查询最接近但小于t0的media_asset记录
                                    media_asset_record = await self.db.select_media_asset_by_timestamp(t0)
                                    
                                    if media_asset_record and 'id' in media_asset_record:
                                        media_asset_id = str(media_asset_record['id'])
                                        self.write_log(f"  [VAD-Violence] 查询到media_asset_id: {media_asset_id}, 查询时间: {t0}")
                                        
                                        # 写入数据库
                                        # VAD检测到violence类别，对应异常名称为'fight'，异常等级为3（打架）
                                        db_id = await self.db.insert_vad(
                                            media_asset_id=media_asset_id,
                                            stream_id=stream_id,
                                            frame_vad_base64=frame_base64,
                                            anomaly_name='fight',
                                            anomaly_level=3
                                        )
                                        print(f"[VAD-Violence] 👍 VAD结果已保存到数据库，ID: {db_id}")
                                        self.write_log(f"  [VAD-Violence] VAD结果已保存到数据库，ID: {db_id}")
                                    else:
                                        print(f"[VAD-Violence] [WARN] 未找到符合条件的media_asset记录，查询时间: {t0}")
                                        self.write_log(f"  [VAD-Violence] [WARN] 未找到符合条件的media_asset记录，查询时间: {t0}")
                                except Exception as e:
                                    print(f"[VAD-Violence] [ERROR] Failed to save VAD result to database: {e}")
                                    self.write_log(f"  [VAD-Violence] [ERROR] Failed to save VAD result to database: {e}")
                            
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
                                try:
                                    # 查询最接近但小于t0的media_asset记录
                                    media_asset_record = await self.db.select_media_asset_by_timestamp(t0)
                                    
                                    if media_asset_record and 'id' in media_asset_record:
                                        media_asset_id = str(media_asset_record['id'])
                                        self.write_log(f"  查询到media_asset_id: {media_asset_id}, 查询时间: {t0}")
                                        
                                        # 写入数据库
                                        # 火灾检测，对应异常名称为'fire'，异常等级为4（火灾/烟雾）
                                        db_id = await self.db.insert_vad(
                                            media_asset_id=media_asset_id,
                                            stream_id=stream_id,
                                            frame_vad_base64=frame_base64,
                                            anomaly_name='fire',
                                            anomaly_level=4
                                        )
                                        print(f"[VAD-Fire] 👍 Fire VAD结果已保存到数据库，ID: {db_id}")
                                        self.write_log(f"  [VAD-Fire] Fire VAD结果已保存到数据库，ID: {db_id}")
                                    else:
                                        print(f"[VAD-Fire] [WARN] 未找到符合条件的media_asset记录，查询时间: {t0}")
                                        self.write_log(f"  [VAD-Fire] [WARN] 未找到符合条件的media_asset记录，查询时间: {t0}")
                                except Exception as e:
                                    print(f"[VAD-Fire] [ERROR] Failed to save Fire VAD result to database: {e}")
                                    self.write_log(f"  [VAD-Fire] [ERROR] Failed to save Fire VAD result to database: {e}")
                            
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
            print(f"[VAD-Fall] 推理结果: {result}")
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
                import torch
                device = "cuda:0" if torch.cuda.is_available() else "cpu"
                results = fall_model.model(
                    frame,
                    conf=fall_model.conf_threshold,
                    iou=fall_model.iou_threshold,
                    device=device,
                )
                
                # 调用可视化方法
                vis_image = fall_model._visualize_detection(frame, results, result)
                
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
                        try:
                            # 查询最接近但小于t0的media_asset记录
                            media_asset_record = await self.db.select_media_asset_by_timestamp(t0)
                            
                            if media_asset_record and 'id' in media_asset_record:
                                media_asset_id = str(media_asset_record['id'])
                                self.write_log(f"  [VAD-Fall] 查询到media_asset_id: {media_asset_id}, 查询时间: {t0}")
                                
                                # 写入数据库
                                # 跌倒检测，对应异常名称为'fall'，异常等级为2（跌倒）
                                db_id = await self.db.insert_vad(
                                    media_asset_id=media_asset_id,
                                    stream_id=stream_id,
                                    frame_vad_base64=frame_base64,
                                    anomaly_name='fall',
                                    anomaly_level=2
                                )
                                print(f"[VAD-Fall] 👍 Fall VAD结果已保存到数据库，ID: {db_id}")
                                self.write_log(f"  [VAD-Fall] Fall VAD结果已保存到数据库，ID: {db_id}")
                            else:
                                print(f"[VAD-Fall] [WARN] 未找到符合条件的media_asset记录，查询时间: {t0}")
                                self.write_log(f"  [VAD-Fall] [WARN] 未找到符合条件的media_asset记录，查询时间: {t0}")
                        except Exception as e:
                            print(f"[VAD-Fall] [ERROR] Failed to save Fall VAD result to database: {e}")
                            self.write_log(f"  [VAD-Fall] [ERROR] Failed to save Fall VAD result to database: {e}")
                    
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
            if yolo_violence_model:
                self._detect_violence(frame, yolo_violence_model, stream_id)
            
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
            print(f"[FATAL] Unexpected processing error: {e}")
            self.write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [FATAL] Unexpected processing error: {e}")

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