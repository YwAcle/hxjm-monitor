import os
import sys
import cv2
import numpy as np
import torch
import logging
import torchvision.transforms as T
from typing import Optional, List

logger = logging.getLogger(__name__)

# 更新 Fast-ReID 路径为 models/fast-reid
print(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
FAST_REID_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'models', 'fast-reid')
FAST_REID_CONFIG = os.path.join(FAST_REID_ROOT, 'configs', 'Market1501', 'bagtricks_R50-ibn.yml')  # 注意这里改为 R50-ibn
FAST_REID_WEIGHTS = os.path.join(FAST_REID_ROOT, 'models', 'market_bot_R50.pth')  # 权重文件路径可能需要调整

print("Fast-ReID 路径:", FAST_REID_ROOT)
print("配置文件路径:", FAST_REID_CONFIG)
print("权重文件路径:", FAST_REID_WEIGHTS)

# 添加 Fast-ReID 到 Python 路径
if FAST_REID_ROOT not in sys.path:
    sys.path.append(FAST_REID_ROOT)
    # 如果有 projects 目录，也需要添加
    projects_path = os.path.join(FAST_REID_ROOT, 'projects')
    if os.path.exists(projects_path):
        sys.path.append(projects_path)

try:
    from fastreid.config import get_cfg
    from fastreid.modeling.meta_arch import build_model
    from fastreid.utils.checkpoint import Checkpointer
    FAST_REID_AVAILABLE = True
    logger.info(f"Fast-ReID 导入成功")
except ImportError as e:
    logger.error(f"无法导入 Fast-ReID: {e}")
    FAST_REID_AVAILABLE = False

# 添加一个新的特征提取器类，使用预训练的ResNet50
class ResNet50Extractor:
    def __init__(self, device='cuda'):
        self.device = device
        self.model = self.load_model()
        self.size = (224, 224)  # ResNet50标准输入尺寸
        self.norm_mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        self.norm_std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        
    def load_model(self):
        """加载预训练的ResNet50模型"""
        print("加载预训练的ResNet50模型")
        from torchvision.models import resnet50, ResNet50_Weights
        model = resnet50(weights=ResNet50_Weights.IMAGENET1K_V2)
        
        # 移除最后的全连接层，使用特征提取器
        model = torch.nn.Sequential(*list(model.children())[:-1])
        model.to(self.device)
        model.eval()
        return model
        
    def __call__(self, img_list):
        """提取图像特征"""
        if not img_list:
            return np.array([])
            
        transform = T.Compose([
            T.ToTensor(),
            T.Normalize(mean=self.norm_mean, std=self.norm_std)
        ])
        
        batch = []
        for img in img_list:
            # BGR转RGB
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            # 调整大小
            img = cv2.resize(img, self.size)
            # 转换为张量并归一化
            img_tensor = transform(img)
            batch.append(img_tensor)
            
        # 堆叠为批次
        batch = torch.stack(batch, dim=0).to(self.device)
        
        # 提取特征
        with torch.no_grad():
            features = self.model(batch)
            features = features.squeeze(-1).squeeze(-1)  # 移除空间维度
            
        # 转换为NumPy数组
        features = features.cpu().numpy()
        
        return features

class FastReIDExtractor:
    """Fast-ReID 特征提取器"""
    
    def __init__(self, config_file: str, model_weights: str, device: Optional[str] = 'cuda'):
        """
        初始化 Fast-ReID 特征提取器
        
        Args:
            config_file: Fast-ReID 配置文件路径
            model_weights: 模型权重文件路径
            device: 使用的设备 ('cuda' 或 'cpu')
        """
        if torch.cuda.is_available():
            self.device = 'cuda'
        else:
            self.device = 'cpu'
            print("警告：CUDA 不可用，使用 CPU 模式")
        self.initialized = False
        
        try:
            # 配置 Fast-ReID
            cfg = get_cfg()
            cfg.merge_from_file(config_file)
            cfg.MODEL.WEIGHTS = model_weights
            cfg.MODEL.DEVICE = self.device
            
            # 构建模型
            self.model = build_model(cfg)
            self.model.to(self.device)
            
            # 加载权重
            Checkpointer(self.model).load(model_weights)
            
            # 设置为评估模式
            self.model.eval()
            
            # 设置预处理参数
            self.size = cfg.INPUT.SIZE_TEST
            self.norm_mean = np.array(cfg.INPUT.PIXEL_MEAN, dtype=np.float32)
            self.norm_std = np.array(cfg.INPUT.PIXEL_STD, dtype=np.float32)
            
            self.initialized = True
            print(f"Fast-ReID 特征提取器初始化成功，使用设备: {self.device}")
        except Exception as e:
            print(f"Fast-ReID 特征提取器初始化失败: {e}")
            import traceback
            print(traceback.format_exc())
    
    def preprocess(self, image):
        """
        预处理图像
        
        Args:
            image: 输入图像 (BGR 格式)
            
        Returns:
            预处理后的图像张量
        """
        # 调整大小
        image = cv2.resize(image, self.size)
        
        # BGR 转 RGB
        image = image[:, :, ::-1]
        
        # 转换为浮点数并归一化
        image = image.astype(np.float32) / 255.0
        
        # 减均值除以标准差
        image = (image - self.norm_mean / 255.0) / (self.norm_std / 255.0)
        
        # 转换为 PyTorch 张量，并调整维度顺序
        image = torch.from_numpy(image).permute(2, 0, 1).unsqueeze(0)
        
        # 移动到指定设备
        image = image.to(self.device)
        
        return image
    
    def extract_features(self, image):
        """
        提取图像特征
        
        Args:
            image: 输入图像 (BGR 格式)
            
        Returns:
            特征向量 (numpy 数组)
        """
        if not self.initialized:
            raise RuntimeError("Fast-ReID 特征提取器未初始化")
            
        with torch.no_grad():
            tensor = self.preprocess(image)
            features = self.model(tensor)
            return features.cpu().numpy()[0]


def get_reid_extractor(device='cuda'):
    """
    获取 ReID 特征提取器，如果 Fast-ReID 不可用则返回 None
    """
    if not FAST_REID_AVAILABLE:
        logger.warning("Fast-ReID 不可用，将使用 ResNet50 特征提取器")
        return ResNet50Extractor(device)
        
    try:
        # 检查配置文件和权重文件是否存在
        if not os.path.exists(FAST_REID_CONFIG):
            logger.error(f"配置文件不存在: {FAST_REID_CONFIG}")
            logger.warning("将使用 ResNet50 特征提取器")
            return ResNet50Extractor(device)
            
        if not os.path.exists(FAST_REID_WEIGHTS):
            logger.error(f"权重文件不存在: {FAST_REID_WEIGHTS}")
            # 如果权重文件不存在，使用备用方案
            logger.warning("将使用 ResNet50 特征提取器")
            return ResNet50Extractor(device)
        
        extractor = FastReIDExtractor(
            config_file=FAST_REID_CONFIG,
            model_weights=FAST_REID_WEIGHTS,
            device=device
        )
        
        if extractor.initialized:
            logger.info("Fast-ReID 特征提取器初始化成功")
            return extractor
        else:
            logger.warning("Fast-ReID 特征提取器初始化失败，将使用 ResNet50 特征提取器")
            return ResNet50Extractor(device)
    except Exception as e:
        logger.error(f"创建 Fast-ReID 特征提取器时发生错误: {e}")
        logger.warning("将使用 ResNet50 特征提取器")
        return ResNet50Extractor(device)

if __name__ == "__main__":
    extractor = get_reid_extractor(device='cuda')
    if extractor:
        print("ReID 特征提取器初始化成功")
    else:
        print("ReID 特征提取器初始化失败")

