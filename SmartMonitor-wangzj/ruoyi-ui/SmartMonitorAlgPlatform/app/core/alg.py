# 导入json模块用于处理JSON数据
import json
# 导入os模块用于文件和路径操作
import os
# 导入cv2模块用于图像处理
import cv2
# 导入numpy用于数值计算
import numpy as np
# 导入base64用于编码解码
import base64
# 导入类型提示
from typing import Dict, List, Any
# 导入ONNX运行时
import onnxruntime
# 导入PyTorch
import torch

# 定义模型处理器类
class ModelProcessor:
    # 初始化方法
    def __init__(self):
        # 加载模型配置
        self.models_config = self._load_models_config()
        # 初始化已加载模型字典
        self.loaded_models = {}


    # 加载模型配置文件方法
    def _load_models_config(self) -> Dict:
        """加载模型配置文件"""
        # 定义配置文件路径
        config_path = "resource/models_config.json"
        # 检查配置文件是否存在
        if not os.path.exists(config_path):
            raise FileNotFoundError("模型配置文件不存在")

        # 打开并读取配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    # 加载模型方法
    def _load_model(self, model_code: str):
        """根据模型代码加载对应的模型"""
        # 检查模型代码是否存在
        if model_code not in self.models_config:
            raise ValueError(f"未找到模型代码: {model_code}")

        # 获取模型信息
        model_info = self.models_config[model_code]
        model_path = model_info['path']

        # 检查模型文件是否存在
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"模型文件不存在: {model_path}")

        # 获取文件扩展名
        extension = os.path.splitext(model_path)[1].lower()

        # 根据扩展名选择加载方式
        if extension == '.onnx':
            return onnxruntime.InferenceSession(model_path)
        elif extension == '.pth':
            return torch.load(model_path)
        elif extension == '.py':
            # 动态导入Python脚本
            import importlib.util
            spec = importlib.util.spec_from_file_location("model_module", model_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module.Model()  # 假设脚本中定义了Model类
        else:
            raise ValueError(f"不支持的模型格式: {extension}")

    # 图像预处理方法
    def _preprocess_image(self, image_data: str) -> np.ndarray:
        """预处理图像数据"""
        # 从data URL中提取base64数据（兼容 base64, 与 base64: 两种格式）
        if isinstance(image_data, str):
            if 'base64:' in image_data:
                image_data = image_data.split('base64:', 1)[1]
            elif 'base64,' in image_data:
                image_data = image_data.split('base64,', 1)[1]
            elif ',' in image_data:
                image_data = image_data.split(',', 1)[1]
        # 解码base64数据
        image_bytes = base64.b64decode(image_data)
        # 转换为numpy数组
        nparr = np.frombuffer(image_bytes, np.uint8)
        # 解码图像
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # 调整图像大小为224x224
        image = cv2.resize(image, (224, 224))
        # 归一化像素值到0-1范围
        image = image.astype(np.float32) / 255.0
        # 调整维度顺序为(C,H,W)
        image = image.transpose(2, 0, 1)
        # 添加batch维度
        image = np.expand_dims(image, axis=0)

        return image

    # 图像后处理方法
    def _postprocess_image(self, output: np.ndarray) -> str:
        """后处理模型输出"""
        # 移除多余的维度
        output = output.squeeze()
        # 调整维度顺序为(H,W,C)
        output = output.transpose(1, 2, 0)
        # 将像素值缩放回0-255范围
        output = (output * 255).astype(np.uint8)

        # 将图像编码为JPEG格式
        _, buffer = cv2.imencode('.jpg', output)
        # 转换为base64字符串
        image_base64 = base64.b64encode(buffer).decode('utf-8')
        return f"data:image/jpeg;base64:{image_base64}"

    # 主处理方法
    def process(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:

        """处理输入数据并返回结果"""
        try:
            # 获取模型代码
            model_code = params['modelCode']
            # 如果模型未加载则加载模型
            if model_code not in self.loaded_models:
                self.loaded_models[model_code] = self._load_model(model_code)

            # 获取模型实例
            model = self.loaded_models[model_code]
            # 初始化结果列表
            results = []

            # 处理每张输入图片
            for img_base64 in params['imgBase64']:
                # 预处理图像
                input_data = self._preprocess_image(img_base64)

                # 根据模型类型执行推理
                # isinstance()是Python内置函数,用于判断一个对象是否是某个类型的实例
                # 这里判断model对象是否是onnxruntime.InferenceSession类型的实例
                if isinstance(model, onnxruntime.InferenceSession):
                    # ONNX模型推理
                    input_name = model.get_inputs()[0].name
                    output = model.run(None, {input_name: input_data})[0]
                else:
                    # PyTorch模型或其他模型推理
                    output = model(torch.from_numpy(input_data)).numpy()

                # 后处理输出图像
                processed_image = self._postprocess_image(output)

                # 构建结果字典
                result = {
                    "processed": True,
                    "imgBase64": processed_image,
                    "modelCode": model_code,
                    "modelName": self.models_config[model_code]['name']
                }
                # 添加到结果列表
                results.append(result)

            return results

        except Exception as e:
            # 处理异常
            raise Exception(f"模型处理失sdasad败: {str(e)}")

# 创建ModelProcessor的全局实例
model_processor = ModelProcessor()
