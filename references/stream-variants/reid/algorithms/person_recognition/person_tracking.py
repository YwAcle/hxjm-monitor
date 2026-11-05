import numpy as np
import cv2
import logging
from typing import List, Dict, Any, Tuple, Optional
import threading
import time
from models import model_manager, get_model_context
import torch

# 配置日志
logger = logging.getLogger(__name__)


def optimize_bbox(bbox: List[int]) -> List[int]:
    """优化边界框，调整比例为更适合人形的区域"""
    x1, y1, x2, y2 = bbox
    width, height = x2 - x1, y2 - y1

    # 调整区域比例(宽高比约为1:3)
    if width > height / 2:
        # 如果太宽，减小宽度
        center_x = (x1 + x2) // 2
        new_width = int(height / 2)
        x1 = max(0, center_x - new_width // 2)
        x2 = x1 + new_width

    return [x1, y1, x2, y2]


class PersonTracker:
    """行人追踪器，使用YOLOv8进行检测，DeepSORT进行追踪"""

    def __init__(self, device_type: str = 'high_res', use_gpu: bool = True, thread_id: Optional[str] = None):
        """
        初始化行人追踪器

        Args:
            device_type: 设备类型配置
            use_gpu: 是否使用GPU
            thread_id: 线程ID，用于日志区分
        """
        # 基本参数
        self.thread_id = thread_id
        self.device = "cuda" if use_gpu and model_manager.default_device == "cuda" else "cpu"
        self.device_type = device_type

        # 跟踪参数
        self.conf_threshold = 0.4  # 置信度阈值
        self.iou_threshold = 0.45  # NMS阈值

        # 跟踪历史记录和特征
        self.track_history = {}  # {track_id: [bbox1, bbox2, ...]}
        self.track_features = {}  # {track_id: features}

        # 缓存上一次的结果
        self.last_frame = None
        self.last_results = []
        self.frame_since_last_compute = 0
        self.cache_max_age = 3  # 最多缓存3帧

        # 模型ID，用于记录模型使用
        self.yolo_model_id = ""
        self.deepsort_model_id = ""

        logger.info(f"初始化行人追踪器: thread_id={thread_id}, device={self.device}")

    def __del__(self):
        """析构函数，释放模型资源"""
        try:
            # 释放模型引用
            if self.yolo_model_id:
                model_manager.release_model(self.yolo_model_id)
            if self.deepsort_model_id:
                model_manager.release_model(self.deepsort_model_id)
        except Exception as e:
            logger.error(f"释放模型资源时出错: {e}")

    def update(self, frame: np.ndarray) -> List[Tuple]:
        """
        更新跟踪状态

        Args:
            frame: 输入图像帧

        Returns:
            List[Tuple]: 跟踪结果列表，每个元素是(x1, y1, x2, y2, track_id, features)
        """
        try:
            # 帧有效性检查
            if frame is None or not isinstance(frame, np.ndarray):
                logger.error(f"无效的帧类型: {type(frame)}")
                return []

            if len(frame.shape) != 3 or frame.shape[2] != 3:
                logger.error(f"帧格式不正确: {frame.shape}")
                return []

            # 使用上下文管理器加载YOLO模型
            with get_model_context("yolov8", device=self.device) as yolo:
                if yolo is None:
                    logger.error("无法加载YOLO模型")
                    return []

                # 配置检测参数
                detect_params = {
                    'conf': self.conf_threshold,
                    'iou': self.iou_threshold,
                    'classes': [0],  # 只检测人类
                    'verbose': False
                }
                with torch.no_grad():
                    # 执行检测
                    results = yolo(frame, **detect_params)
                    # 处理检测结果
                    detections = []
                    for result in results:
                        boxes = result.boxes
                        for i, box in enumerate(boxes):
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            conf = float(box.conf[0])
                            cls = int(box.cls[0])

                            # 确保坐标在图像范围内
                            x1 = max(0, x1)
                            y1 = max(0, y1)
                            x2 = min(frame.shape[1], x2)
                            y2 = min(frame.shape[0], y2)

                            # 过滤太小的检测框
                            if (x2 - x1) < 40 or (y2 - y1) < 80:
                                continue

                            # 只处理人类检测结果
                            if cls == 0 and conf > self.conf_threshold:
                                # 优化边界框比例
                                bbox = optimize_bbox([x1, y1, x2, y2])
                                x1, y1, x2, y2 = bbox
                                detections.append(([x1, y1, x2, y2], conf, cls))

            # 使用DeepSORT模型进行跟踪
            tracks = []
            if detections:
                # 转换检测结果为DeepSORT所需格式
                bbox_xywh = []
                confidences = []

                for (x1, y1, x2, y2), conf, cls in detections:
                    # 转换为xywh格式
                    w, h = x2 - x1, y2 - y1
                    center_x = (x1 + x2) / 2
                    center_y = (y1 + y2) / 2
                    bbox_xywh.append([center_x, center_y, w, h])
                    confidences.append(conf)

                # 转换为NumPy数组
                bbox_xywh = np.array(bbox_xywh)
                confidences = np.array(confidences)

                # 使用上下文管理器加载DeepSORT模型
                with get_model_context("deepsort", device=self.device) as deepsort:
                    if deepsort is None:
                        logger.error("无法加载DeepSORT模型")
                        return []

                    # 执行跟踪
                    outputs = deepsort.update(bbox_xywh, confidences, frame)

                    # 处理跟踪结果
                    current_track_ids = []
                    for track in outputs:
                        bbox = track[:4]  # [x1, y1, x2, y2]
                        track_id = track[4]  # ID
                        current_track_ids.append(track_id)

                        x1, y1, x2, y2 = map(int, bbox)
                        # 确保边界框在图像范围内
                        x1 = max(0, x1)
                        y1 = max(0, y1)
                        x2 = min(frame.shape[1], x2)
                        y2 = min(frame.shape[0], y2)

                        # 存储边界框历史
                        if track_id not in self.track_history:
                            self.track_history[track_id] = []
                        self.track_history[track_id].append([x1, y1, x2, y2])

                        # 限制历史长度
                        if len(self.track_history[track_id]) > 5:  # 保留最近5帧
                            self.track_history[track_id].pop(0)

                        # 平滑边界框
                        if len(self.track_history[track_id]) >= 3:
                            # 计算最近3帧的平均边界框
                            avg_bbox = np.mean(self.track_history[track_id][-3:], axis=0).astype(int)
                            # 平滑处理
                            smooth_bbox = [
                                int(0.7 * x1 + 0.3 * avg_bbox[0]),
                                int(0.7 * y1 + 0.3 * avg_bbox[1]),
                                int(0.7 * x2 + 0.3 * avg_bbox[2]),
                                int(0.7 * y2 + 0.3 * avg_bbox[3])
                            ]
                            x1, y1, x2, y2 = smooth_bbox

                        # 添加到跟踪结果
                        features = None
                        if track_id in self.track_features:
                            features = self.track_features[track_id]

                        tracks.append((x1, y1, x2, y2, track_id, features))

                    # 清理不再出现的跟踪ID
                    for track_id in list(self.track_history.keys()):
                        if track_id not in current_track_ids:
                            self.track_history.pop(track_id, None)
                            self.track_features.pop(track_id, None)

            # 缓存当前帧结果
            self.last_frame = frame.copy()
            self.last_results = tracks
            self.frame_since_last_compute = 0

            return tracks

        except Exception as e:
            logger.error(f"更新跟踪器失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def track(self, frame: np.ndarray) -> List[Dict]:
        """
        跟踪帧中的行人

        Args:
            frame: 输入帧

        Returns:
            List[Dict]: 跟踪结果列表，每个元素是字典 {'track_id': id, 'bbox': [x1, y1, x2, y2]}
        """
        try:
            # 添加缓存机制
            if self.last_frame is not None and self.last_results:
                # 如果缓存帧还不太旧，直接返回缓存结果
                self.frame_since_last_compute += 1
                if self.frame_since_last_compute <= self.cache_max_age:
                    return [{'track_id': track_id, 'bbox': [x1, y1, x2, y2]}
                            for x1, y1, x2, y2, track_id, _ in self.last_results]

            # 获取跟踪结果
            tracks = self.update(frame)

            # 转换为字典格式返回
            results = []
            for track in tracks:
                x1, y1, x2, y2, track_id, _ = track
                results.append({
                    'track_id': int(track_id),
                    'bbox': [int(x1), int(y1), int(x2), int(y2)]
                })

            return results

        except Exception as e:
            logger.error(f"跟踪失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return [] 