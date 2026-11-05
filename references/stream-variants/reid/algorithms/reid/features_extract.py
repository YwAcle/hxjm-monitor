#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os
import sys
import cv2
import numpy as np
import base64
import logging
import time
import torch
from typing import List, Dict, Optional, Union, Tuple
from sklearn.metrics.pairwise import cosine_similarity

# 配置日志
logger = logging.getLogger(__name__)

# 添加项目根目录到Python路径以便正确导入模块
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, "../.."))
if root_dir not in sys.path:
    sys.path.append(root_dir)

# 导入全局模型管理器
from models.model_manager import model_manager

# 检查Fast-ReID是否可用
FAST_REID_ROOT = os.path.join(root_dir, 'models', 'fast-reid')
FAST_REID_AVAILABLE = os.path.exists(FAST_REID_ROOT)

# 如果Fast-ReID目录存在，添加到Python路径
if FAST_REID_AVAILABLE and FAST_REID_ROOT not in sys.path:
    sys.path.append(FAST_REID_ROOT)
    logger.info(f"Fast-ReID路径已添加到Python路径: {FAST_REID_ROOT}")

# 尝试导入Fast-ReID相关模块
try:
    from fastreid.config import get_cfg
    from demo.predictor import FeatureExtractionDemo

    REID_AVAILABLE = True
    logger.info("Fast-ReID模块导入成功")
except ImportError as e:
    REID_AVAILABLE = False
    logger.error(f"Fast-ReID模块导入失败: {e}")


def extract_image_features(img_list: List[Dict[str, str]], is_global: bool = True) -> Dict[str, Union[List, List]]:
    """
    提取图片特征

    Args:
        img_list: 图片列表，每个元素是包含data和name字段的字典
        is_global: 是否使用全局模型管理器获取模型，如果为False则使用传入的model参数

    Returns:
        Dict: 包含提取的特征列表和名称列表的字典，格式为{'features': [...], 'names': [...]}
    """
    try:
        start_time = time.time()

        features_list = []  # 存储提取的特征列表
        names_list = []  # 存储图片名称列表

        # 获取模型 - 根据is_global参数决定使用全局模型还是本地模型
        reid_model = None  # 模型实例
        model_id = None  # 模型ID

        if is_global:
            # 使用全局模型管理器获取模型
            logger.info("使用全局模型管理器获取ReID模型")
            reid_model, model_id = model_manager.get_model("reid")
        else:
            # 尝试本地加载模型
            logger.info("尝试自动加载本地ReID模型")
            reid_model = load_fast_reid_model()

        if reid_model is None:
            logger.info("再次尝试自动加载本地ReID模型")
            reid_model = load_fast_reid_model()
            if reid_model is None:
                logger.error("无法加载本地ReID模型")
                return {"features": [], "names": []}
        logger.info(f"开始处理 {len(img_list)} 张图片...")

        # 处理图片列表
        for i, img_item in enumerate(img_list):
            try:
                # 获取图片数据和名称
                img_data = img_item.get('data', '')
                img_name = img_item.get('name', f'未命名_{i}')

                # 去掉文件扩展名
                img_name = os.path.splitext(img_name)[0]

                # 判断 img_data 是否是存在的图片路径
                if os.path.isfile(img_data):
                    try:
                        with open(img_data, "rb") as f:
                            img_bytes = f.read()
                        img_base64 = base64.b64encode(img_bytes).decode("utf-8")
                        logger.info(f"图片 {img_name} 编码为 base64 成功")
                    except Exception as e:
                        logger.error(f"读取图片 {img_name} 失败: {e}")
                        continue
                else:
                    # 使用原来的 base64 数据
                    img_base64 = img_data
                    if not img_base64:
                        logger.warning(f"图片 {img_name} 的 base64 数据为空，跳过")
                        continue

                # 解码base64图片数据
                try:
                    img_data = base64.b64decode(img_base64.split(',')[1] if ',' in img_base64 else img_base64)
                    nparr = np.frombuffer(img_data, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)  # BGR格式

                    if img is None or img.size == 0:
                        logger.warning(f"图片 {img_name} 解码失败，跳过")
                        continue
                except Exception as e:
                    logger.error(f"解码图片 {img_name} 失败: {e}")
                    continue

                # 提取特征
                try:
                    # FeatureExtractionDemo类应该使用run_on_image方法
                    features = reid_model.run_on_image(img)
                    # 如果返回是torch.Tensor，需要转为numpy
                    if isinstance(features, torch.Tensor):
                        features = features.cpu().numpy()

                    # 确保特征向量已归一化
                    if features.ndim == 1:
                        # 一维向量，直接归一化
                        features_norm = features / (np.linalg.norm(features) + 1e-10)  # 添加小值防止除零
                    else:
                        # 二维向量，按行归一化
                        features_norm = features / (np.linalg.norm(features, axis=1, keepdims=True) + 1e-10)

                    # 存储特征和名称到列表
                    features_list.append(features_norm)
                    names_list.append(img_name)

                    logger.debug(f"成功提取图片 {img_name} 的特征，形状: {features_norm.shape}")

                except Exception as e:
                    logger.error(f"提取图片 {img_name} 特征失败: {e}")
                    continue

                # 每处理10张图片输出一次进度
                if (i + 1) % 10 == 0 or i == len(img_list) - 1:
                    elapsed = time.time() - start_time
                    logger.info(f"已处理 {i + 1}/{len(img_list)} 张图片，耗时: {elapsed:.2f}秒")

            except Exception as e:
                logger.error(f"处理图片 {i} 时发生错误: {e}")
                continue

        # 如果使用全局模型，记得释放模型
        if is_global and model_id:
            model_manager.release_model(model_id)
            logger.debug(f"释放ReID模型: {model_id}")

        # 输出结果信息
        logger.info(f"特征提取完成，共提取 {len(features_list)} 个有效特征，耗时: {time.time() - start_time:.2f}秒")

        return {
            "features": features_list,
            "names": names_list
        }

    except Exception as e:
        logger.error(f"特征提取过程发生错误: {e}")
        import traceback
        logger.error(traceback.format_exc())

        # 如果使用全局模型且模型ID不为空，确保释放模型
        if is_global and 'model_id' in locals() and model_id:
            try:
                model_manager.release_model(model_id)
            except:
                pass

        return {"features": [], "names": []}


# 本地加载FastReID模型
def load_fast_reid_model(model_path: str = None, device: str = 'cuda' if torch.cuda.is_available() else 'cpu') -> \
Optional[FeatureExtractionDemo]:
    """
    加载FastReID模型

    Args:
        model_path: 模型路径，如果为None则使用默认路径
        device: 运行设备

    Returns:
        FeatureExtractionDemo实例或None
    """
    try:
        # 如果FastReID不可用，直接返回None
        if not REID_AVAILABLE:
            logger.error("FastReID模块不可用，无法加载模型")
            return None

        # 设置默认模型路径
        if model_path is None:
            model_path = os.path.join(FAST_REID_ROOT, 'models/reid.pth')

        # 检查模型文件是否存在
        if not os.path.exists(model_path):
            logger.error(f"模型文件不存在: {model_path}")
            return None

        logger.info(f"开始加载FastReID模型: {model_path}, 设备: {device}")
        start_time = time.time()

        # 配置模型
        cfg = get_cfg()
        config_file = os.path.join(FAST_REID_ROOT, 'models/config-test.yaml')

        if os.path.exists(config_file):
            cfg.merge_from_file(config_file)
        else:
            logger.warning(f"配置文件不存在: {config_file}，使用默认配置")

        # 设置模型参数
        cfg.MODEL.WEIGHTS = model_path
        cfg.MODEL.DEVICE = device

        # 创建特征提取器
        model = FeatureExtractionDemo(cfg)

        logger.info(f"FastReID模型加载成功，耗时: {time.time() - start_time:.2f}秒")
        return model

    except Exception as e:
        logger.error(f"加载FastReID模型失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


# 测试特征提取函数
if __name__ == "__main__":
    # 设置日志级别
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # 测试图像路径
    # test_image_path = "D:\project\SmartMonitorAlgPlatform\\test.jpg"
    test_image_path = "/data/lkh/projects/hxjm/smart-monitor-alg-platform/data/reid_test/img/person1.png"

    # 检查测试图像是否存在
    if not os.path.exists(test_image_path):
        logger.error(f"测试图像不存在: {test_image_path}")
        sys.exit(1)

    # 读取测试图像
    test_image = cv2.imread(test_image_path)
    if test_image is None:
        logger.error(f"无法读取测试图像: {test_image_path}")
        sys.exit(1)

    logger.info(f"成功读取测试图像: {test_image_path}, 尺寸: {test_image.shape}")

    # 将图像转换为base64
    _, img_encoded = cv2.imencode('.jpg', test_image)
    img_base64 = base64.b64encode(img_encoded).decode('utf-8')

    # 准备测试数据 - 符合函数要求的格式
    test_data = [
        {
            "data": img_base64,
            "name": os.path.basename(test_image_path)
        }
    ]

    # 测试本地模型
    print("测试使用本地模型提取特征...")
    result = extract_image_features(test_data, is_global=False)
    print(f"提取到 {len(result['features'])} 个特征")

    # 输出特征和名称
    if len(result['features']) > 0:
        print(f"特征形状: {result['features'][0].shape}")
        print(f"特征名称: {result['names'][0]}")

        # 测试特征相似度
        if len(result['features']) > 1:
            similarity = \
            cosine_similarity(result['features'][0].reshape(1, -1), result['features'][1].reshape(1, -1))[0][0]
            print(f"特征1和特征2的相似度: {similarity:.4f}")
    else:
        print("未提取到有效特征")
