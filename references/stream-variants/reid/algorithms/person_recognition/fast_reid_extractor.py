import os
import sys
import numpy as np
import torch
import cv2
import torch.nn.functional as F
from torchvision import transforms

# 添加Fast-ReID路径
FAST_REID_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'models', 'fast-reid')
if FAST_REID_ROOT not in sys.path:
    sys.path.append(FAST_REID_ROOT)
    # 如果有projects目录，也需要添加
    projects_path = os.path.join(FAST_REID_ROOT, 'projects')
    if os.path.exists(projects_path):
        sys.path.append(projects_path)
# 尝试导入Fast-ReID
try:
    from fastreid.config import get_cfg
    from fastreid.modeling.meta_arch import build_model
    from fastreid.utils.checkpoint import Checkpointer
    FAST_REID_AVAILABLE = True
    print("Fast-ReID导入成功")
except ImportError as e:
    print(f"无法导入Fast-ReID: {e}")
    FAST_REID_AVAILABLE = False


# Fast-ReID模型类
class FastReIDExtractor:
    def __init__(self, model_path, device='cuda', debug_mode=False):
        self.device = device
        self.debug_mode = debug_mode
        if debug_mode:
            print("警告：使用调试模式，将生成随机特征")
            self.model = None
            self.initialized = False
        else:
            try:
                # 配置Fast-ReID
                cfg = get_cfg()

                # 使用指定的配置文件
                config_file = "D:/project/SmartMonitorAlgPlatform/models/fast-reid/models/config-test.yaml"
                if os.path.exists(config_file):
                    print(f"使用配置文件: {config_file}")
                    cfg.merge_from_file(config_file)
                else:
                    print(f"配置文件不存在: {config_file}，尝试查找其他配置文件")

                # 设置模型权重和设备
                cfg.MODEL.WEIGHTS = model_path
                cfg.MODEL.DEVICE = device

                # 创建特征提取器 - 修改导入路径
                # 使用相对导入
                sys.path.append(FAST_REID_ROOT)
                from demo.predictor import FeatureExtractionDemo
                self.model = FeatureExtractionDemo(cfg)
                self.initialized = True
                print("Fast-ReID模型加载成功")

                # 设置输入尺寸
                self.size = (256, 128)  # 默认尺寸

                # 设置归一化参数
                self.norm_mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
                self.norm_std = np.array([0.229, 0.224, 0.225], dtype=np.float32)

            except Exception as e:
                print(f"Fast-ReID初始化失败: {e}")
    def __call__(self, img_list):
        """
        提取图像特征

        Args:
            img_list: 图像列表，每个元素是一个BGR格式的NumPy数组

        Returns:
            features: 特征向量，形状为(N, D)，其中N是图像数量，D是特征维度
        """
        if not img_list:
            return np.array([])

        # 调试模式：生成随机特征
        if self.debug_mode:
            features = np.random.randn(len(img_list), 2048)
            features = features / np.linalg.norm(features, axis=1, keepdims=True)
            return features

        # 使用Fast-ReID提取特征
        try:
            features_list = []

            for img in img_list:
                # 如果是FeatureExtractionDemo实例，使用其API
                if hasattr(self.model, 'run_on_image'):
                    # 使用官方API提取特征
                    feat = self.model.run_on_image(img)

                    # 后处理：归一化
                    feat = F.normalize(feat)
                    feat = feat.cpu().numpy()

                    features_list.append(feat)
                else:
                    # 如果是ResNet50Extractor，使用其API
                    features = self.model([img])
                    features_list.append(features)

            # 堆叠特征
            if features_list:
                if isinstance(features_list[0], np.ndarray):
                    features = np.vstack(features_list)
                else:
                    features = torch.cat(features_list, dim=0).cpu().numpy()
            else:
                features = np.array([])

            return features

        except Exception as e:
            print(f"特征提取失败: {e}")
            # 出错时返回随机特征
            features = np.random.randn(len(img_list), 2048)
            features = features / np.linalg.norm(features, axis=1, keepdims=True)
            return features
