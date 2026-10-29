import onnxruntime
import numpy as np
import cv2

class ImageProcessorONNX:
    def __init__(self, model_path):
        """
        初始化ONNX模型
        :param model_path: ONNX模型文件路径
        """
        self.session = onnxruntime.InferenceSession(model_path)
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name

    def preprocess(self, image):
        """
        图像预处理
        :param image: OpenCV格式的图像
        :return: 预处理后的图像
        """
        # 调整图像大小
        image = cv2.resize(image, (224, 224))
        # 转换为RGB格式
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        # 调整维度顺序
        image = image.transpose(2, 0, 1)
        # 添加batch维度
        image = np.expand_dims(image, axis=0)
        # 转换为float32类型
        image = image.astype(np.float32)
        return image

    def postprocess(self, output):
        """
        后处理输出结果
        :param output: 模型输出
        :return: 处理后的结果
        """
        # 根据需要处理输出
        output = output[0]
        output = output.transpose(1, 2, 0)
        output = cv2.cvtColor(output, cv2.COLOR_RGB2BGR)
        return output

    def process_image(self, image):
        """
        处理单张图片
        :param image: OpenCV格式的图像
        :return: 处理后的图像
        """
        # 预处理
        input_data = self.preprocess(image)
        
        # 运行推理
        outputs = self.session.run(None, {self.input_name: input_data})
        
        # 后处理
        result = self.postprocess(outputs[0])
        
        return result

# 使用示例
if __name__ == "__main__":
    # 初始化模型
    processor = ImageProcessorONNX("image_processor.onnx")
    
    # 读取测试图片
    image = cv2.imread("test.jpg")
    
    # 处理图片
    result = processor.process_image(image)
    
    # 保存结果
    cv2.imwrite("result.jpg", result) 