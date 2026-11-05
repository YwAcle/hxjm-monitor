# -*- coding: utf-8 -*-
# pip install -i https://pypi.doubanio.com/simple/ 包名
# pip install -i https://pypi.tuna.tsinghua.edu.cn/simple 包名
# @Time    : 2025/12/12 15:10
# @Author  : beidanci

import numpy as np

class YOLODetector:
    def __init__(self, model_path, device="cuda", conf=0.5, iou=0.5, classes=None):
        """
        官方 YOLOv8 检测器（兼容原 Fast-ReID detect_with_optimize 输出格式）

        Args:
            model_path: yolov8s.pt / yolov8s-seg.pt
            device: cpu / cuda
            conf: 置信度阈值
            iou: IOU 阈值
            classes: 要检测的类别列表，例如 [0] 表示只检测行人
        """
        from ultralytics import YOLO
        self.model = YOLO(model_path)
        self.device = device
        self.conf = conf
        self.iou = iou
        self.classes = classes  # ⭐ 用户可自定义类别 如行人 class=0

    def detect_with_optimize(self, frame, verbose=False):
        """
        返回格式严格兼容 Fast-ReID detect_with_optimize：

        bbox_xywh: (N, 4) cx, cy, w, h
        confidences: list of conf
        cls_ids: list of int
        xyxy_list: list of [x1, y1, x2, y2]
        """

        # YOLOv8 推理
        results = self.model(
            frame,
            conf=self.conf,
            iou=self.iou,
            verbose=verbose,
            classes=self.classes  # ⭐ 只输出指定类别
        )[0]
        # print("yolov8 推理结果：",results)
        boxes = results.boxes

        if boxes is None or len(boxes) == 0:
            return np.array([]), [], [], []

        xyxy = boxes.xyxy.cpu().numpy()        # (N, 4)
        cls_ids = boxes.cls.cpu().numpy().astype(int)
        confs = boxes.conf.cpu().numpy()

        # 转换成 DeepSORT 格式 xywh (cx, cy, w, h)
        bbox_xywh = []
        xyxy_list = []

        for box in xyxy:
            x1, y1, x2, y2 = box
            w = x2 - x1
            h = y2 - y1
            cx = x1 + w / 2
            cy = y1 + h / 2

            bbox_xywh.append([cx, cy, w, h])
            xyxy_list.append([x1, y1, x2, y2])

        return (
            np.array(bbox_xywh, dtype=np.float32),
            confs,
            cls_ids,
            xyxy_list,
        )
