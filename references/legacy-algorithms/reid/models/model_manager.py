import time
import threading
import logging
import torch
import argparse
import gc
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
import weakref
import os
import sys
from utils.parser import get_config

# 导入模型类
try:
    from ultralytics import YOLO

    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    print("YOLO模型未安装")

try:
    from insightface.app import FaceAnalysis

    INSIGHTFACE_AVAILABLE = True
except ImportError:
    INSIGHTFACE_AVAILABLE = False
    print("InsightFace模型未安装")

try:
    from models.deep_sort import build_tracker

    DEEPSORT_AVAILABLE = True
except ImportError:
    DEEPSORT_AVAILABLE = False
    print("DeepReid模型未安装")

# 检查Fast-ReID是否可用
FAST_REID_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'models', 'fast-reid')
FAST_REID_AVAILABLE = os.path.exists(FAST_REID_ROOT)

# 如果Fast-ReID目录存在，添加到Python路径
if FAST_REID_AVAILABLE and FAST_REID_ROOT not in sys.path:
    sys.path.append(FAST_REID_ROOT)
    print(f"Fast-ReID路径已添加到Python路径: {FAST_REID_ROOT}")

# 尝试导入Fast-ReID相关模块
try:
    from fastreid.config import get_cfg
    from demo.predictor import FeatureExtractionDemo
    from demo.demo import setup_cfg, get_parser

    REID_AVAILABLE = True
    print("Fast-ReID模块导入成功")
except ImportError as e:
    REID_AVAILABLE = False
    print(f"Fast-ReID模块导入失败: {e}")

# 配置日志
logger = logging.getLogger(__name__)


class ModelInfo:
    """存储模型信息和使用状态"""

    def __init__(self, model_instance, model_type: str, device: str, config: Dict):
        self.model = model_instance
        self.model_type = model_type
        self.device = device
        self.config = config
        self.last_used_time = datetime.now()
        self.reference_count = 0
        self.lock = threading.RLock()

    def increment_ref(self):
        """增加引用计数"""
        with self.lock:
            self.reference_count += 1
            self.last_used_time = datetime.now()

    def decrement_ref(self):
        """减少引用计数"""
        with self.lock:
            if self.reference_count > 0:
                self.reference_count -= 1
            self.last_used_time = datetime.now()

    def is_idle(self, idle_threshold: timedelta) -> bool:
        """检查模型是否空闲"""
        with self.lock:
            return (self.reference_count == 0 and
                    datetime.now() - self.last_used_time > idle_threshold)


class ModelManager:
    """全局模型管理器，负责模型的加载、共享和释放"""
    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ModelManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # 模型存储和配置
        self.models: Dict[str, ModelInfo] = {}
        self.model_configs = {}

        # 需要初始化的模型列表
        self.need_init = [
            "yolov8",
            "face_recognition",
            "deepsort",
            "reid"  # 添加reid模型
        ]

        # 模型清理配置
        self.cleanup_interval = 60  # 秒
        self.idle_threshold = timedelta(minutes=5)  # 5分钟不使用则释放

        # 自动清理线程
        self.cleanup_thread = None
        self.stop_event = threading.Event()

        # 优先使用的设备
        self.default_device = "cuda" if torch.cuda.is_available() else "cpu"

        # 完成初始化
        self._initialized = True

        # 启动自动清理线程
        self._start_cleanup_thread()

    def _start_cleanup_thread(self):
        """启动自动清理线程"""
        if self.cleanup_thread is None or not self.cleanup_thread.is_alive():
            self.stop_event.clear()
            self.cleanup_thread = threading.Thread(
                target=self._cleanup_task,
                daemon=True
            )
            self.cleanup_thread.start()
            logger.info("模型管理器清理线程已启动")

    def _cleanup_task(self):
        """模型清理任务"""
        while not self.stop_event.is_set():
            try:
                self.cleanup_idle_models()
            except Exception as e:
                logger.error(f"模型清理出错: {e}")

            # 等待下一次清理
            self.stop_event.wait(self.cleanup_interval)

    def cleanup_idle_models(self):
        """清理闲置模型"""
        with self._lock:
            # 找出所有闲置模型
            idle_models = []
            for model_id, model_info in list(self.models.items()):
                if model_info.is_idle(self.idle_threshold):
                    idle_models.append(model_id)

            # 释放闲置模型
            for model_id in idle_models:
                self._release_model(model_id)

            # 如果释放了模型，触发垃圾回收
            if idle_models:
                logger.info(f"释放了 {len(idle_models)} 个空闲模型: {idle_models}")
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                gc.collect()

    def _release_model(self, model_id: str):
        """释放特定模型"""
        with self._lock:
            if model_id in self.models:
                model_info = self.models[model_id]
                logger.info(f"释放模型: {model_id} ({model_info.model_type})")

                # 特定模型的清理逻辑
                try:
                    if model_info.model_type == "yolov8":
                        # YOLOv8模型特定清理
                        del model_info.model
                    elif model_info.model_type == "face_recognition":
                        # 人脸识别模型特定清理
                        del model_info.model
                    elif model_info.model_type == "deepsort":
                        # DeepSORT模型特定清理
                        del model_info.model
                    elif model_info.model_type == "reid":
                        # Fast-ReID模型特定清理
                        del model_info.model

                    # 从管理器中移除
                    del self.models[model_id]

                except Exception as e:
                    logger.error(f"释放模型 {model_id} 时出错: {e}")

    def get_model(self, model_type: str, config: Optional[Dict] = None, device: Optional[str] = None) -> Tuple[
        Any, str]:
        """
        获取模型实例（如果不存在则初始化）

        Args:
            model_type: 模型类型
            config: 模型配置
            device: 运行设备

        Returns:
            Tuple[模型实例, 模型ID]
        """
        with self._lock:
            # 确定使用的设备
            if device is None:
                device = self.default_device

            # 创建模型ID
            config_hash = hash(str(config)) if config else 0
            model_id = f"{model_type}_{device}_{config_hash}"

            # 如果模型已存在，直接返回
            if model_id in self.models:
                model_info = self.models[model_id]
                model_info.increment_ref()
                return model_info.model, model_id

            # 加载模型
            model = self._load_model(model_type, config, device)
            if model:
                # 创建模型信息对象
                model_info = ModelInfo(model, model_type, device, config)
                model_info.increment_ref()

                # 保存到模型字典
                self.models[model_id] = model_info
                logger.info(f"成功加载模型: {model_id}")

                return model, model_id
            else:
                logger.error(f"加载模型失败: {model_type}")
                return None, ""

    def _load_model(self, model_type: str, config: Optional[Dict], device: str) -> Any:
        """
        加载特定类型的模型

        Args:
            model_type: 模型类型
            config: 模型配置
            device: 设备

        Returns:
            模型实例
        """
        try:
            if model_type == "yolov8":
                return self._load_yolov8(config, device)
            elif model_type == "face_recognition":
                return self._load_face_recognition(config, device)
            elif model_type == "deepsort":
                return self._load_deepsort(config, device)
            elif model_type == "reid":
                return self._load_reid(config, device)
            else:
                logger.warning(f"未知的模型类型: {model_type}")
                return None
        except Exception as e:
            logger.error(f"加载模型 {model_type} 时出错: {e}")
            return None

    def _load_yolov8(self, config: Optional[Dict], device: str) -> Any:
        """加载YOLOv8模型"""
        if not YOLO_AVAILABLE:
            logger.error("YOLOv8未安装")
            return None

        try:
            # 默认配置
            if config is None:
                config = {
                    "model_path": "models/yolov8n.pt",
                    "imgsz": 640,
                    "conf": 0.25,
                    "iou": 0.45
                }

            # 加载模型
            model = YOLO(config.get("model_path", "models/yolov8n.pt"))
            model.to(device)

            logger.info(f"YOLOv8模型加载成功，设备: {device}")
            return model

        except Exception as e:
            logger.error(f"加载YOLOv8模型失败: {e}")
            return None

    def _load_face_recognition(self, config: Optional[Dict], device: str) -> Any:
        """加载人脸识别模型"""
        if not INSIGHTFACE_AVAILABLE:
            logger.error("InsightFace未安装")
            return None

        try:
            # 默认配置
            if config is None:
                config = {
                    "name": "buffalo_l",
                    "root": "~/.insightface/models",
                    "det_size": (640, 640),
                    "det_thresh": 0.5,
                    "min_face_size": 100,
                    "max_face_count": 10
                }

            # 设置CUDA提供程序
            providers = []
            if device == "cuda" and torch.cuda.is_available():
                providers.append('CUDAExecutionProvider')
            providers.append('CPUExecutionProvider')

            # 初始化模型
            model = FaceAnalysis(
                name=config.get("name", "buffalo_l"),
                root=os.path.expanduser(config.get("root", "~/.insightface/models")),
                providers=providers,
                allowed_modules=['detection', 'recognition', 'genderage']
            )

            # 准备模型
            det_size = config.get("det_size", (640, 640))
            model.prepare(
                ctx_id=0 if device == "cuda" and torch.cuda.is_available() else -1,
                det_size=det_size,
                det_thresh=config.get("det_thresh", 0.5)
            )

            # 设置GPU相关参数
            if device == "cuda" and torch.cuda.is_available():
                torch.backends.cudnn.benchmark = True
                torch.set_num_threads(1)

            logger.info(f"人脸识别模型加载成功，设备: {device}, 模型: {config.get('name', 'buffalo_l')}")

            # 检查模型文件
            model_root = os.path.expanduser(
                f"{config.get('root', '~/.insightface/models')}/{config.get('name', 'buffalo_l')}")
            required_models = {
                'det_10g.onnx': '人脸检测模型',
                'w600k_r50.onnx': '人脸识别模型',
                'genderage.onnx': '性别年龄模型'
            }

            for model_file, desc in required_models.items():
                model_path = os.path.join(model_root, model_file)
                if not os.path.exists(model_path):
                    logger.warning(f"缺少{desc}文件: {model_path}")

            return model

        except Exception as e:
            logger.error(f"加载人脸识别模型失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _load_deepsort(self, config: Optional[Dict], device: str) -> Any:
        """加载DeepSORT模型"""
        if not DEEPSORT_AVAILABLE:
            logger.error("DeepSORT未安装")
            return None

        try:
            parser = argparse.ArgumentParser()
            # deep_sort
            parser.add_argument("--sort", default=False, help='True: sort model or False: reid model')
            parser.add_argument("--config_deepsort", type=str, default="./config/deep_sort.yaml")
            parser.add_argument("--display", default=True, help='show resule')
            parser.add_argument("--frame_interval", type=int, default=1)
            parser.add_argument("--cpu", dest="use_cuda", action="store_false", default=True)
            args = parser.parse_args()
            # 默认配置
            if config is None:
                config = get_config()
                config.merge_from_file(args.config_deepsort)

            # 加载模型
            model = build_tracker(
                config,
                False,
                use_cuda=(device == "cuda" and torch.cuda.is_available())
            )

            logger.info(f"DeepSORT模型加载成功，设备: {device}")
            return model

        except Exception as e:
            logger.error(f"加载DeepSORT模型失败: {e}")
            return None

    def _load_reid(self, config: Optional[Dict], device: str) -> Any:
        """加载Fast-ReID模型"""
        if not FAST_REID_AVAILABLE or not REID_AVAILABLE:
            logger.error("Fast-ReID模块未安装或导入失败")
            return None

        try:
            # 默认配置
            if config is None:
                config = {
                    "config_file": os.path.join(FAST_REID_ROOT, "models/config-test.yaml"),
                    "weights": os.path.join(FAST_REID_ROOT, "models/reid.pth"),
                    "parallel": False,
                    "device": device
                }

            # 通过get_parser获取默认参数
            parser = get_parser()

            # 更新参数
            args = parser.parse_args([])
            args.config_file = config.get("config_file", args.config_file)
            args.parallel = config.get("parallel", args.parallel)

            # 设置模型权重
            weights_path = config.get("weights", os.path.join(FAST_REID_ROOT, "models/reid.pth"))
            args.opts = ['MODEL.WEIGHTS', weights_path]

            # 设置设备
            if device == "cpu":
                args.opts.extend(['MODEL.DEVICE', 'cpu'])

            # 加载模型配置
            cfg = setup_cfg(args)

            # 创建特征提取器
            model = FeatureExtractionDemo(cfg, parallel=args.parallel)

            logger.info(f"Fast-ReID模型加载成功，设备: {device}")
            return model

        except Exception as e:
            logger.error(f"加载Fast-ReID模型失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def release_model(self, model_id: str):
        """
        释放模型（减少引用计数）

        Args:
            model_id: 模型ID
        """
        with self._lock:
            if model_id in self.models:
                self.models[model_id].decrement_ref()
                logger.debug(f"减少模型引用计数: {model_id}")

    def preload_models(self):
        """预加载需要初始化的模型"""
        with self._lock:
            for model_type in self.need_init:
                try:
                    model, model_id = self.get_model(model_type)
                    if model:
                        logger.info(f"成功预加载模型: {model_type} -> {model_id}")
                        # 立即释放引用，让它进入闲置状态但保持加载
                        self.release_model(model_id)
                except Exception as e:
                    logger.error(f"预加载模型 {model_type} 失败: {e}")

    def shutdown(self):
        """关闭模型管理器，释放所有资源"""
        with self._lock:
            # 停止清理线程
            self.stop_event.set()
            if self.cleanup_thread and self.cleanup_thread.is_alive():
                self.cleanup_thread.join(timeout=2.0)

            # 释放所有模型
            for model_id in list(self.models.keys()):
                self._release_model(model_id)

            # 清理GPU内存
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # 触发垃圾回收
            gc.collect()

            logger.info("模型管理器已关闭，所有资源已释放")


# 创建全局单例实例
model_manager = ModelManager()


# 模型使用示例
def get_model_context(model_type: str, config: Optional[Dict] = None, device: Optional[str] = None):
    """
    创建一个上下文管理器来自动获取和释放模型

    示例:
    ```
    with get_model_context("yolov8") as yolo:
        results = yolo(frame)
    ```

    Args:
        model_type: 模型类型
        config: 模型配置
        device: 设备

    Returns:
        上下文管理器
    """
    return ModelContext(model_type, config, device)


class ModelContext:
    """模型上下文管理器，自动处理模型的获取和释放"""

    def __init__(self, model_type: str, config: Optional[Dict] = None, device: Optional[str] = None):
        self.model_type = model_type
        self.config = config
        self.device = device
        self.model = None
        self.model_id = ""

    def __enter__(self):
        """获取模型"""
        self.model, self.model_id = model_manager.get_model(self.model_type, self.config, self.device)
        return self.model

    def __exit__(self, exc_type, exc_val, exc_tb):
        """释放模型"""
        if self.model_id:
            model_manager.release_model(self.model_id)
            self.model = None
            self.model_id = ""