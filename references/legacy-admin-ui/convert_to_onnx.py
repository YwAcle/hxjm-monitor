import torch
import torch.nn as nn
import onnx
import onnxruntime
import cv2
import numpy as np

class ImageProcessor(nn.Module):
    def __init__(self):
        super(ImageProcessor, self).__init__()
        # 定义你的模型结构
        self.conv1 = nn.Conv2d(3, 3, kernel_size=5, padding=2)
        
    def forward(self, x):
        # 定义模型的前向传播
        return self.conv1(x)

def convert_model():
    # 创建模型实例
    model = ImageProcessor()
    model.eval()
    
    # 创建示例输入
    dummy_input = torch.randn(1, 3, 224, 224)
    
    # 导出ONNX模型
    torch.onnx.export(
        model,
        dummy_input,
        "image_processor.onnx",
        export_params=True,
        opset_version=11,
        input_names=['input'],
        output_names=['output'],
        dynamic_axes={
            'input': {0: 'batch_size', 2: 'height', 3: 'width'},
            'output': {0: 'batch_size', 2: 'height', 3: 'width'}
        }
    )
    print("Model converted to ONNX format successfully!")

def test_onnx_model():
    # 测试ONNX模型
    onnx_model = onnx.load("image_processor.onnx")
    onnx.checker.check_model(onnx_model)
    
    # 创建推理会话
    ort_session = onnxruntime.InferenceSession("image_processor.onnx")
    
    # 测试图片
    img = cv2.imread("test.jpg")
    img = cv2.resize(img, (224, 224))
    img = img.transpose(2, 0, 1)
    img = np.expand_dims(img, axis=0)
    img = img.astype(np.float32)
    
    # 运行推理
    ort_inputs = {'input': img}
    ort_outputs = ort_session.run(None, ort_inputs)
    print("Model tested successfully!")

if __name__ == "__main__":
    convert_model()
    test_onnx_model() 