import numpy as np
import torch
import cv2
import time
from .deep.feature_extractor import Extractor
from .sort.nn_matching import NearestNeighborDistanceMetric
from .sort.preprocessing import non_max_suppression
from .sort.detection import Detection
from .sort.tracker import Tracker
import os
import sys
import collections
import collections.abc

# 兼容 Python 3.10+ 中 collections/collections.abc 变更
# 一些旧代码会从 collections.abc 导入 OrderedDict，或从 collections 导入 Mapping
if not hasattr(collections.abc, "OrderedDict"):
    collections.abc.OrderedDict = collections.OrderedDict
if not hasattr(collections, "Mapping") and hasattr(collections.abc, "Mapping"):
    collections.Mapping = collections.abc.Mapping

# 添加Fast-ReID路径
FAST_REID_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'models', 'fast-reid')
if FAST_REID_ROOT not in sys.path:
    sys.path.append(FAST_REID_ROOT)

# 尝试导入Reid_feature
try:
    from demo.demo import Reid_feature

    print("成功导入Fast-ReID")
    USE_FAST_REID = True
except ImportError as e:
    print(f"无法导入Fast-ReID: {e}，将使用内置特征提取器")
    USE_FAST_REID = False

__all__ = ['DeepReid']


class DeepReid(object):
    def __init__(self, model_path, max_dist=0.2, min_confidence=0.3, nms_max_overlap=1.0, max_iou_distance=0.7,
                 max_age=70, n_init=3, nn_budget=100, use_cuda=True):
        self.min_confidence = min_confidence
        self.nms_max_overlap = nms_max_overlap

        # 根据是否成功导入Fast-ReID选择特征提取器
        if USE_FAST_REID:
            try:
                self.extractor = Reid_feature()
                print("使用Fast-ReID特征提取器")
            except Exception as e:
                print(f"初始化Reid_feature失败: {e}，回退到内置特征提取器")
                self.extractor = Extractor(model_path, use_cuda=use_cuda)
        else:
            # 使用内置的特征提取器
            print("使用内置特征提取器")
            self.extractor = Extractor(model_path, use_cuda=use_cuda)

        max_cosine_distance = max_dist
        nn_budget = 100
        metric = NearestNeighborDistanceMetric("cosine", max_cosine_distance, nn_budget)
        self.tracker = Tracker(metric, max_iou_distance=max_iou_distance, max_age=max_age, n_init=n_init)

    def update(self, bbox_xywh, confidences, ori_img):
        outputs = []  # 存储输出的跟踪结果
        features = []  # 存储提取的特征向量，改为列表方便与outputs一一对应

        if not len(confidences):  # 如果没有检测到目标，直接返回空结果
            return outputs, np.array([])

        try:
            self.height, self.width = ori_img.shape[:2]  # 获取图像尺寸
            # 提取目标特征
            all_features = self._get_features(bbox_xywh, ori_img)

            # 将边界框从xywh格式转换为tlwh格式
            bbox_tlwh = self._xywh_to_tlwh(bbox_xywh)
            # 创建检测对象，仅保留置信度高于阈值的检测结果
            detections = [Detection(bbox_tlwh[i], conf, all_features[i]) for i, conf in enumerate(confidences) if
                          conf > self.min_confidence]

            # 执行非极大值抑制
            boxes = np.array([d.tlwh for d in detections])
            scores = np.array([d.confidence for d in detections])
            indices = non_max_suppression(boxes, self.nms_max_overlap, scores)
            detections = [detections[i] for i in indices]

            # 保存这一帧的特征 - detection索引到特征的映射
            detection_features = {i: detections[i].feature for i in range(len(detections))}

            # 创建匹配结果的映射，用于后续查找track对应的特征
            track_to_detection = {}

            # 记录当前tracker中已有的tracks和它们的ID
            existing_tracks = {track.track_id: track for track in self.tracker.tracks}

            # 更新跟踪器
            self.tracker.predict()  # 预测阶段

            # 获取匹配结果
            matches, unmatched_tracks, unmatched_detections = self.tracker._match(detections)

            # 记录每个track匹配到哪个detection
            for track_idx, detection_idx in matches:
                track_id = self.tracker.tracks[track_idx].track_id
                track_to_detection[track_id] = detection_idx

            # 现在更新tracker
            self.tracker.update(detections)  # 更新阶段

            # 输出边界框和ID以及对应特征
            for track in self.tracker.tracks:
                # 跳过未确认或长时间未更新的轨迹
                if not track.is_confirmed() or track.time_since_update > 1:
                    continue
                box = track.to_tlwh()  # 获取跟踪框
                x1, y1, x2, y2 = self._tlwh_to_xyxy(box)  # 转换为xyxy格式
                track_id = track.track_id  # 获取跟踪ID

                # 添加跟踪结果
                outputs.append(np.array([x1, y1, x2, y2, track_id], dtype=np.int))

                # 寻找对应的特征
                if track_id in track_to_detection:
                    # 如果这个track匹配到了某个detection，使用该detection的特征
                    detection_idx = track_to_detection[track_id]
                    if detection_idx in detection_features:
                        features.append(detection_features[detection_idx])
                    else:
                        # 找不到对应detection的特征，检查track是否有已存特征
                        if hasattr(track, 'features') and len(track.features) > 0:
                            features.append(track.features[-1])
                        else:
                            # 实在没有特征，用零向量
                            if all_features.shape[0] > 0:
                                features.append(np.zeros_like(all_features[0]))
                            else:
                                # 完全没有参考，创建一个空特征
                                features.append(np.array([]))
                else:
                    # 如果是新track或未匹配track，检查是否存在于之前的tracks中
                    if track_id in existing_tracks and hasattr(existing_tracks[track_id], 'features') and len(
                            existing_tracks[track_id].features) > 0:
                        features.append(existing_tracks[track_id].features[-1])
                    else:
                        # 实在没有特征，用零向量
                        if all_features.shape[0] > 0:
                            features.append(np.zeros_like(all_features[0]))
                        else:
                            # 完全没有参考，创建一个空特征
                            features.append(np.array([]))

            # 将outputs和features转换为numpy数组
            if len(outputs) > 0:
                outputs = np.stack(outputs, axis=0)  # 将结果堆叠为数组
                if len(features) > 0:
                    try:
                        features = np.array(features)
                    except ValueError as e:
                        # 如果特征维度不一致，创建一个空特征数组
                        print(f"无法创建特征数组: {e}")
                        features = np.array([])
                else:
                    features = np.array([])
            else:
                outputs = np.array([])
                features = np.array([])

            # 确保outputs和features长度一致
            if len(outputs) != len(features) and len(outputs) > 0 and len(features) > 0:
                print(f"警告: outputs数量({len(outputs)})与features数量({len(features)})不匹配")
                # 如果数量不匹配，以较短的为准截断较长的
                min_len = min(len(outputs), len(features))
                outputs = outputs[:min_len]
                features = features[:min_len]

        except Exception as e:
            print(f"跟踪器更新时出错: {e}")  # 捕获并打印错误
            import traceback
            traceback.print_exc()
            outputs = np.array([])
            features = np.array([])

        return outputs, features  # 返回跟踪结果和特征

    """
    TODO:
        Convert bbox from xc_yc_w_h to xtl_ytl_w_h
    Thanks JieChen91@github.com for reporting this bug!
    """

    @staticmethod
    def _xywh_to_tlwh(bbox_xywh):
        if isinstance(bbox_xywh, np.ndarray):
            bbox_tlwh = bbox_xywh.copy()
        elif isinstance(bbox_xywh, torch.Tensor):
            bbox_tlwh = bbox_xywh.clone()
        bbox_tlwh[:, 0] = bbox_xywh[:, 0] - bbox_xywh[:, 2] / 2.
        bbox_tlwh[:, 1] = bbox_xywh[:, 1] - bbox_xywh[:, 3] / 2.
        return bbox_tlwh

    def _xywh_to_xyxy(self, bbox_xywh):
        x, y, w, h = bbox_xywh
        x1 = max(int(x - w / 2), 0)
        x2 = min(int(x + w / 2), self.width - 1)
        y1 = max(int(y - h / 2), 0)
        y2 = min(int(y + h / 2), self.height - 1)
        return x1, y1, x2, y2

    def _tlwh_to_xyxy(self, bbox_tlwh):
        """
        TODO:
            Convert bbox from xtl_ytl_w_h to xc_yc_w_h
        Thanks JieChen91@github.com for reporting this bug!
        """
        x, y, w, h = bbox_tlwh
        x1 = max(int(x), 0)
        x2 = min(int(x + w), self.width - 1)
        y1 = max(int(y), 0)
        y2 = min(int(y + h), self.height - 1)
        return x1, y1, x2, y2

    def _xyxy_to_tlwh(self, bbox_xyxy):
        x1, y1, x2, y2 = bbox_xyxy

        t = x1
        l = y1
        w = int(x2 - x1)
        h = int(y2 - y1)
        return t, l, w, h

    def _get_features(self, bbox_xywh, ori_img):
        try:
            im_crops = []
            for box in bbox_xywh:
                x1, y1, x2, y2 = self._xywh_to_xyxy(box)
                im = ori_img[y1:y2, x1:x2]

                # 确保裁剪区域有效
                if im.size == 0:
                    # 创建一个空白图像
                    im = np.zeros((128, 64, 3), dtype=np.uint8)

                # 根据使用的特征提取器进行不同的预处理
                if USE_FAST_REID:
                    # Fast-ReID预处理
                    im = im[:, :, ::-1]  # BGR转RGB
                    im = cv2.resize(im, (128, 256), interpolation=cv2.INTER_CUBIC)
                    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                    im_crops.append(torch.as_tensor(im.astype("float32").transpose(2, 0, 1), device=device)[None])
                else:
                    # 内置特征提取器预处理
                    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                    im_crops.append(torch.as_tensor(im.astype("float32").transpose(2, 0, 1), device=device)[None])

            # 提取特征
            if im_crops:
                features = self.extractor(im_crops)
            else:
                features = np.array([])

            return features

        except Exception as e:
            print(f"特征提取失败: {e}")
            # 返回空特征
            return np.array([])


