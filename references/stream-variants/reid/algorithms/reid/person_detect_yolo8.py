#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os
import time
import cv2
import torch
import numpy as np
import logging
from typing import List, Tuple
import sys

# 配置日志
logger = logging.getLogger(__name__)

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class PersonDetectYOLO8:
    """
    基于YOLOv8的行人检测类，使用模型管理池获取模型实例
    """

    def __init__(self,
                 model_manager=None,
                 model_name: str = 'yolov8',
                 device: str = 'cuda' if torch.cuda.is_available() else 'cpu',
                 conf_thres: float = 0.4,
                 iou_thres: float = 0.45,
                 classes: List[int] = [],  # 默认只检测人(类别0)
                 img_size: int = 640,
                 fp16: bool = False):  # 添加半精度参数
        """
        初始化YOLOv8行人检测器，从模型管理池获取模型

        Args:
            model_manager: 模型管理器实例
            model_name: 模型名称，用于从模型池中获取
            device: 运行设备，'cuda'或'cpu'
            conf_thres: 置信度阈值
            iou_thres: NMS IOU阈值
            classes: 需要检测的类别ID列表，默认只检测人[0]
            img_size: 输入图像大小
            fp16: 是否使用半精度(FP16)推理，仅在CUDA可用时生效
        """
        self.device = device
        self.conf_thres = conf_thres
        self.iou_thres = iou_thres
        self.classes = classes
        self.img_size = img_size
        self.model_name = model_name
        self.model_manager = model_manager
        self.fp16 = fp16 and device == 'cuda' and torch.cuda.is_available()  # 确保只在CUDA可用时启用半精度

        # 初始化时间统计
        self.inference_time = 0
        self.preprocess_time = 0
        self.postprocess_time = 0

        # 从模型管理池获取模型
        try:
            # 检查模型管理器是否提供
            if self.model_manager is None:
                # 从本地获取模型
                from ultralytics import YOLO
                self.model = YOLO("models/yolov8n.pt")
                self.model.to(device)
            else:
                # 从模型池获取模型
                logger.info(f"从模型管理池获取YOLOv8模型: {model_name}")
                start_time = time.time()

                # 通过模型管理器获取模型实例
                model_result = self.model_manager.get_model(model_name)

                # 模型管理器返回的是(model, model_id)元组
                if isinstance(model_result, tuple) and len(model_result) == 2:
                    self.model = model_result[0]  # 获取模型对象
                    self.model_id = model_result[1]  # 获取模型ID
                    logger.info(f"成功获取模型: {self.model_id}")
                else:
                    self.model = model_result  # 直接使用返回结果作为模型
                    self.model_id = f"{model_name}_{device}"

                # 确保模型移动到指定设备
                if hasattr(self.model, 'to') and hasattr(self.model, 'device') and self.model.device != device:
                    self.model.to(device)

                # 如果启用半精度，转换模型为FP16
                if self.fp16:
                    try:
                        # 尝试将模型转换为半精度
                        if hasattr(self.model, 'model') and hasattr(self.model.model, 'half'):
                            logger.info("启用半精度(FP16)推理")
                            self.model.model.half()
                        else:
                            logger.warning("模型不支持半精度转换，将使用全精度")
                            self.fp16 = False
                    except Exception as e:
                        logger.warning(f"启用半精度推理失败: {e}，将使用全精度")
                        self.fp16 = False

                # 获取模型的类别名称
                self.names = self.model.names if hasattr(self.model, 'names') else None
                logger.info(f"YOLOv8模型获取成功，耗时: {time.time() - start_time:.2f}秒")

                if self.names:
                    logger.info(f"检测类别: {[self.names[c] for c in classes]}")

        except Exception as e:
            logger.error(f"获取YOLOv8模型失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    def detect(self,
               frame: np.ndarray,
               verbose: bool = False) -> Tuple[np.ndarray, List[float], List[int], List]:
        """
        在图像中检测行人

        Args:
            frame: 输入图像(BGR格式)
            verbose: 是否打印详细信息

        Returns:
            Tuple包含:
                bbox_xywh: 行人边界框(x_center, y_center, width, height)
                confs: 每个行人的置信度
                cls_ids: 每个行人的类别ID
                xyxy: 原始的(x1, y1, x2, y2)坐标
        """
        t1 = time.time()
        orig_height, orig_width = frame.shape[:2]

        # 确保模型可用
        if self.model is None:
            logger.error("YOLOv8模型未加载，无法执行检测")
            return np.array([]), [], [], []
        # print("检测类别：",self.classes)
        # 使用YOLOv8 API进行预测
        try:
            # YOLOv8的predict方法会自动处理图像预处理、推理和后处理
            results = self.model.predict(
                source=frame,
                conf=self.conf_thres,
                iou=self.iou_thres,
                classes=self.classes,
                verbose=verbose,
                imgsz=self.img_size,
                device=self.device,
                half=self.fp16  # 使用半精度参数
            )

            # 提取检测结果
            bbox_xywh = []
            confs = []
            cls_ids = []
            xyxy_list = []

            # 处理检测结果
            if len(results) > 0:
                boxes = results[0].boxes

                # 获取边界框、置信度、类别
                for box in boxes:
                    # 获取xyxy格式的边界框
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()

                    # 转换为xywh格式(中心点坐标, 宽, 高)
                    center_x = (x1 + x2) / 2
                    center_y = (y1 + y2) / 2
                    width = x2 - x1
                    height = y2 - y1

                    # 添加到结果列表
                    bbox_xywh.append([center_x, center_y, width, height])
                    confs.append(float(box.conf[0]))
                    cls_ids.append(int(box.cls[0]))
                    xyxy_list.append([x1, y1, x2, y2])

            # 更新时间统计
            self.inference_time = time.time() - t1
            if verbose:
                logger.info(f"检测到 {len(bbox_xywh)} 个行人，耗时: {self.inference_time * 1000:.2f}ms")

            return np.array(bbox_xywh), confs, cls_ids, xyxy_list

        except Exception as e:
            logger.error(f"YOLOv8检测失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return np.array([]), [], [], []

    def detect_with_optimize(self,
                             frame: np.ndarray,
                             verbose: bool = False) -> Tuple[np.ndarray, List[float], List[int], List]:
        """
        在图像中检测行人，并对检测结果进行优化

        Args:
            frame: 输入图像(BGR格式)
            verbose: 是否打印详细信息

        Returns:
            Tuple包含:
                bbox_xywh: 行人边界框(x_center, y_center, width, height)
                confs: 每个行人的置信度
                cls_ids: 每个行人的类别ID
                xyxy: 原始的(x1, y1, x2, y2)坐标
        """
        # 检测行人
        bbox_xywh, confs, cls_ids, xyxy_list = self.detect(frame, verbose)

        # 优化结果 - 过滤掉太小的边界框
        optimized_results = self._optimize_detections(
            bbox_xywh, confs, cls_ids, xyxy_list,
            min_width=40, min_height=80,
            min_conf=self.conf_thres
        )

        return optimized_results

    def _optimize_detections(self,
                             bbox_xywh: np.ndarray,
                             confs: List[float],
                             cls_ids: List[int],
                             xyxy_list: List,
                             min_width: int = 40,
                             min_height: int = 80,
                             min_conf: float = 0.4) -> Tuple[np.ndarray, List[float], List[int], List]:
        """
        优化检测结果，过滤掉不符合条件的检测框

        Args:
            bbox_xywh: 边界框(x_center, y_center, width, height)
            confs: 每个框的置信度
            cls_ids: 每个框的类别ID
            xyxy_list: 原始的(x1, y1, x2, y2)坐标
            min_width: 最小宽度
            min_height: 最小高度
            min_conf: 最小置信度

        Returns:
            优化后的检测结果
        """
        if len(bbox_xywh) == 0:
            return np.array([]), [], [], []

        filtered_bbox_xywh = []
        filtered_confs = []
        filtered_cls_ids = []
        filtered_xyxy = []

        for i, (bbox, conf, cls_id, xyxy) in enumerate(zip(bbox_xywh, confs, cls_ids, xyxy_list)):
            x_c, y_c, w, h = bbox

            # 过滤条件: 宽高和置信度
            if w >= min_width and h >= min_height and conf >= min_conf:
                filtered_bbox_xywh.append(bbox)
                filtered_confs.append(conf)
                filtered_cls_ids.append(cls_id)
                filtered_xyxy.append(xyxy)

        return np.array(filtered_bbox_xywh), filtered_confs, filtered_cls_ids, filtered_xyxy

    def __call__(self, frame: np.ndarray, verbose: bool = False):
        """
        使类实例可以直接调用，执行行人检测

        Args:
            frame: 输入图像(BGR格式)
            verbose: 是否打印详细信息

        Returns:
            检测结果
        """
        # 如果启用半精度，使用半精度推理
        if self.fp16 and torch.cuda.is_available():
            try:
                with torch.cuda.amp.autocast():
                    return self.model(frame)
            except Exception as e:
                logger.warning(f"半精度推理失败: {e}，回退到全精度")
                return self.model(frame)
        else:
            return self.model(frame)

