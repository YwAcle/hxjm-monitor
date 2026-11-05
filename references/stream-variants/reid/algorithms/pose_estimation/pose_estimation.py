import cv2
import base64
import numpy as np
from ultralytics import YOLO
import matplotlib.pyplot as plt
import io
from PIL import Image
class PoseEstimation():
    def __init__(self, model_path="./yolo11n-pose.pt"):
        """
        初始化姿态估计模型。
        :param model_path: YOLO 模型路径
        """
        self.model = YOLO(model_path)
    
    @staticmethod
    def convert_base64_to_img(base64_code):
        """将 Base64 编码的字符串转换为 OpenCV 图像格式。"""
        image_data = base64.b64decode(base64_code)
        nparr = np.frombuffer(image_data, np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    @staticmethod
    def convert_array_to_base64(array):
        """将 OpenCV 图像转换为 Base64 编码的字符串。"""
        _, buffer = cv2.imencode(".jpg", array)
        return base64.b64encode(buffer).decode("utf-8")

    def predict(self, image_base64,device="cuda:0"):
        """
        进行姿态估计并返回带有关键点的图像（Base64 编码）。
        :param image_base64: 输入图像的 Base64 编码
        :return: 带有预测结果的 Base64 编码图像
        """
        img = self.convert_base64_to_img(image_base64)
        results = self.model.predict(source=img,device = device)
        
        for r in results:
            plotted_img = r.plot()
            return self.convert_array_to_base64(plotted_img)  # 返回处理后的图片
        
        return None


if __name__ == "__main__":
    pose_estimation = PoseEstimation() # 参数用于放置模型文件
    with open("cxk.png", "rb") as f:
        img_base64 = base64.b64encode(f.read()).decode("utf-8")
    result_base64 = pose_estimation.predict(img_base64,device="cuda:0") # 参数用于指定设备
    print("姿态估计完成，结果的base64编码为:")
    print(result_base64)
    
    # 将base64编码转换为图像并显示
    print("\n正在显示处理后的图像...")
    img_data = base64.b64decode(result_base64)
    
    # 方法1：使用matplotlib显示
    img = Image.open(io.BytesIO(img_data))
    plt.figure(figsize=(10, 8))
    plt.imshow(np.array(img))
    plt.axis('off')
    plt.title('姿态估计结果')
    plt.show()
    
    # 方法2：保存为本地文件并提示
    output_path = "pose_estimation_result.jpg"
    with open(output_path, "wb") as f:
        f.write(img_data)
    print(f"处理后的图像已保存到: {output_path}")