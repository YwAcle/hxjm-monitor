# 设备配置字典,根据不同分辨率配置不同的参数
DEVICE_CONFIG = {
    # 高分辨率配置(1080p)
    "high_res": {
        "frame_size": (1920, 1080),  # 帧大小
        "yolo_imgsz": 640,  # 使用640x640输入保持细节
        "roi_ratio": 0.2,  # 适当扩大ROI范围
        "frame_queue_size": 150,  # 增大队列应对高分辨率延迟
        "drop_strategy": "smart",  # 智能丢帧保持关键帧
        "max_fps": 25,  # 匹配常见摄像头帧率
        "yolo_model_path": "models/yolov8n.pt"
    },
    
    # 中等分辨率配置(720p)
    "medium_res": {
        "frame_size": (1280, 720),
        "yolo_imgsz": 416,  # 平衡精度与速度    
        "roi_ratio": 0.15,  # 适度缩小ROI范围
        "frame_queue_size": 100,  # 中等队列长度
        "drop_strategy": "smart",  # 统一使用智能策略
        "max_fps": 20,  # 适度降低帧率
        "yolo_model_path": "models/yolov8n.pt"
    },
    
    # 低分辨率配置(480p)
    "low_res": {
        "frame_size": (640, 480),
        "yolo_imgsz": 320,  # 最小输入尺寸
        "roi_ratio": 0.1,  # 最小ROI范围
        "frame_queue_size": 50,  # 小队列低延迟
        "drop_strategy": "oldest",  # 简单策略
        "max_fps": 15,  # 低帧率
        "yolo_model_path": "models/yolov8n.pt"
    },
    
    # 超高分辨率配置(2K)
    "ultra_high_res": {
        "frame_size": (2560, 1440),
        "yolo_imgsz": 1280,  # 最大输入尺寸保持精度
        "roi_ratio": 0.3,  # 最大ROI范围
        "frame_queue_size": 200,  # 最大队列缓冲
        "drop_strategy": "smart",  # 智能策略
        "max_fps": 25,  # 降低帧率保证处理
        "yolo_model_path": "models/yolov8n.pt"      
    }
}