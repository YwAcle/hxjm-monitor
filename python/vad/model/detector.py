"""
人体异常行为检测器
基于YOLOv8 Pose模型
"""
import cv2
import numpy as np
import math
import os
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from ultralytics import YOLO
from vad.model.zone_detector import ZoneDetector
from PIL import Image, ImageDraw, ImageFont
# 配置参数
MODEL_PATH = "yolov8n-pose.pt"
CONFIDENCE_THRESHOLD = 0.7
IOU_THRESHOLD = 0.5
MODEL_DEVICE = "cuda:0"  # 或 "cuda:0"
DETECTION_FRAME_SKIP = 1  # 视频检测时每隔几帧检测一次

# 关键点索引映射



class BehaviorDetector:
    """人体异常行为检测器"""
    
    def __init__(self, model_path: str = MODEL_PATH, 
                 conf_threshold: float = CONFIDENCE_THRESHOLD,
                 iou_threshold: float = IOU_THRESHOLD):
        """
        初始化检测器
        
        参数:
            model_path: YOLO模型路径
            conf_threshold: 置信度阈值
            iou_threshold: IOU阈值
        """
        self.log_path = os.getenv(
            "VAD_LOG_PATH",
            str(Path(__file__).resolve().parent.parent / "log" / "vad_log.txt"),
        )
        # 初始化区域检测器
        self.zone_detector = ZoneDetector()
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.KEYPOINT_DICT = {
			'nose': 0,
			'left_eye': 1,
			'right_eye': 2,
			'left_ear': 3,
			'right_ear': 4,
			'left_shoulder': 5,
			'right_shoulder': 6,
			'left_elbow': 7,
			'right_elbow': 8,
			'left_wrist': 9,
			'right_wrist': 10,
			'left_hip': 11,
			'right_hip': 12,
			'left_knee': 13,
			'right_knee': 14,
			'left_ankle': 15,
			'right_ankle': 16
		}
        
        # 加载模型
        try:
            self.model = YOLO(model_path)
            print(f"成功加载模型: {model_path}")
        except Exception as e:
            print(f"加载模型失败: {e}")
            self.model = None
    
    def detect_image(self, image_path: str, visualize: bool = False, output_path: str = None) -> Dict[str, Any]:
        """
        检测图片中的异常行为
        
        参数:
            image_path: 图片路径
            visualize: 是否生成可视化图片
            output_path: 可视化图片保存路径
        
        返回:
            检测结果字典
        """
        # 读取图片
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"无法读取图片: {image_path}")
        
        # 进行检测
        results = self.model(
            image,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            device=MODEL_DEVICE,
        )
        
        # 分析结果
        result = self._analyze_results(results, image.shape)
		
        # 生成可视化图片
        if visualize and output_path:
            vis_image = self._visualize_detection(image, results, result)
            cv2.imwrite(output_path, vis_image)
            result['visualization_path'] = output_path
        print(result)
        return result

    def detect_frame(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        检测帧中的异常行为
        
        参数:
            frame: 输入图像帧（numpy数组，BGR格式）
        
        返回:
            检测结果字典（包含分析后的结果，不进行可视化）
        """
        if frame is None or frame.size == 0:
            raise ValueError("输入的frame为空或无效")
        
        # 进行检测
        # 自动检测设备（优先使用GPU，如果不可用则使用CPU）
        import torch
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        results = self.model(
            frame,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            device=device,
        )
        
        # 分析结果
        result = self._analyze_results(results, frame.shape)
        
        return result
    
    def _put_chinese_text(self, img: np.ndarray, text: str, pos: Tuple[int, int], 
                          color: Tuple[int, int, int] = (255, 255, 255), 
                          font_size: int = 16) -> np.ndarray:
        """
        在OpenCV图像上绘制中文文本（使用PIL）
        
        参数:
            img: OpenCV图像（BGR格式）
            text: 要绘制的文本
            pos: 文本位置 (x, y)
            color: 文本颜色 (B, G, R)
            font_size: 字体大小
        
        返回:
            绘制后的图像
        """
        # 将OpenCV图像转换为PIL图像
        img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img_pil)
        
        # 尝试加载指定大小的字体
        try:
            font_paths = [
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
                '/System/Library/Fonts/PingFang.ttc',
                'C:/Windows/Fonts/simhei.ttf',
                'C:/Windows/Fonts/msyh.ttc',
            ]
            font = None
            for font_path in font_paths:
                try:
                    font = ImageFont.truetype(font_path, font_size)
                    break
                except:
                    continue
            if font is None:
                font = ImageFont.load_default()
        except:
            font = ImageFont.load_default()
        
        # 绘制文本（PIL使用RGB颜色）
        rgb_color = (color[2], color[1], color[0])  # BGR转RGB
        draw.text(pos, text, font=font, fill=rgb_color)
        
        # 转换回OpenCV格式
        img_cv = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
        return img_cv
    
    def _visualize_detection(self, image, results, detection_result):
        """
        可视化检测结果（图片）
        
        参数:
            image: 原始图片
            results: YOLO检测结果
            detection_result: 分析后的检测结果
        
        返回:
            可视化后的图片
        """
        try:
            # 使用ultralytics内置的plot方法生成可视化图像
            if results and len(results) > 0 and detection_result['person_count'] > 0:
                try:
                    vis_image = results[0].plot(
                        conf=False,
                        line_width=2,
                        font_size=0.5,
                        pil=False,
                        labels=False,
                        boxes=True,
                        kpt_radius=5
                    )
                except Exception as plot_error:
                    print(f"使用内置plot方法失败: {plot_error}")
                    vis_image = image.copy()
            else:
                vis_image = image.copy()
            
            # 添加检测结果文本
            if detection_result['has_abnormal']:
                behavior_text = f"ABNORMAL: {detection_result['behavior_type']}"
                conf_text = f"Confidence: {detection_result['confidence']:.2f}"
                
                # 如果是跌倒检测，显示详细信息
                if detection_result['behavior_type'] == 'FALL':
                    lines = [behavior_text, conf_text]
                    
                    # 如果使用角度检测方法
                    if detection_result.get('fall_angle'):
                        fall_angle = detection_result['fall_angle']
                        angle_deg = fall_angle.get('angle_deg', 0)
                        angle_threshold = fall_angle.get('angle_threshold', 10.0)
                        lines.append(f"Angle: {angle_deg:.1f} (threshold: {angle_threshold:.1f})")
                    
                    # 如果使用多指标检测方法
                    elif detection_result.get('fall_details'):
                        fall_details = detection_result['fall_details']
                        lines.extend([
                            f"View: {'Side' if fall_details['is_side_view'] else 'Front'}",
                            f"Indicators: {fall_details['indicator_count']}/{fall_details['min_indicators']}"
                        ])
                        
                        # 添加指标详情
                        for ind in fall_details['indicators']:
                            # 根据指标类型格式化数值
                            value = ind['value']
                            indicator_name = ind['name']
                            # 格式化数值（指标名称已经是英文）
                            if 'angle' in indicator_name.lower() or 'anomaly' in indicator_name.lower():
                                value_str = f"{value:.1f}°"
                            elif 'ratio' in str(value).lower() or 'position' in indicator_name.lower() or 'gravity' in indicator_name.lower():
                                value_str = f"{value:.3f}"
                            else:
                                value_str = f"{value:.2f}"
                            lines.append(f"- {indicator_name}: {value_str} (conf: {ind['confidence']:.2f})")
                    
                    # 计算文本区域大小（使用cv2测量）
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    font_scale = 0.45
                    thickness = 1
                    line_height = 20
                    padding = 10
                    
                    max_width = 0
                    text_height = 0
                    for line in lines:
                        (text_width, text_height), _ = cv2.getTextSize(line, font, font_scale, thickness)
                        max_width = max(max_width, text_width)
                    
                    box_width = max_width + padding * 2
                    box_height = len(lines) * line_height + padding * 2
                    
                    # 计算右上角位置
                    img_width = vis_image.shape[1]
                    box_x = img_width - box_width - padding
                    box_y = padding
                    
                    # 添加半透明背景（右上角）
                    overlay = vis_image.copy()
                    cv2.rectangle(overlay, (box_x, box_y), (box_x + box_width, box_y + box_height), (0, 0, 0), -1)
                    cv2.addWeighted(overlay, 0.7, vis_image, 0.3, 0, vis_image)
                    
                    # 使用cv2.putText绘制英文文本（右上角对齐）
                    text_x = box_x + padding
                    y_pos = box_y + padding + text_height
                    for i, line in enumerate(lines):
                        color = (0, 0, 255) if i == 0 else ((255, 255, 255) if i < 4 else (200, 200, 200))
                        cv2.putText(vis_image, line, (text_x, y_pos),
                                   font, font_scale, color, thickness)
                        y_pos += line_height
                else:
                    # 其他异常行为，显示简单信息
                    overlay = vis_image.copy()
                    cv2.rectangle(overlay, (10, 10), (350, 70), (0, 0, 0), -1)
                    cv2.addWeighted(overlay, 0.6, vis_image, 0.4, 0, vis_image)
                    
                    # 使用cv2.putText绘制英文文本
                    cv2.putText(vis_image, behavior_text, (18, 33),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)
                    cv2.putText(vis_image, conf_text, (18, 55),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            else:
                # 正常状态
                overlay = vis_image.copy()
                cv2.rectangle(overlay, (10, 10), (200, 50), (0, 0, 0), -1)
                cv2.addWeighted(overlay, 0.6, vis_image, 0.4, 0, vis_image)
                
                # 使用cv2.putText绘制文本
                cv2.putText(vis_image, "Status: NORMAL", (18, 35),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
            
            # 添加人数统计
            person_count_text = f"Persons: {detection_result['person_count']}"
            text_size = cv2.getTextSize(person_count_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
            text_x = 18
            text_y = vis_image.shape[0] - 22
            
            overlay = vis_image.copy()
            cv2.rectangle(overlay, 
                         (text_x - 8, text_y - text_size[1] - 8),
                         (text_x + text_size[0] + 8, text_y + 8),
                         (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.6, vis_image, 0.4, 0, vis_image)
            
            cv2.putText(vis_image, person_count_text, (text_x, text_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            return vis_image
            
        except Exception as e:
            print(f"可视化失败: {e}")
            return image.copy()
    
    def _visualize_frame(self, frame, results, detection_result):
        """
        可视化单个视频帧
        
        参数:
            frame: 原始视频帧
            results: YOLO检测结果
            detection_result: 分析后的检测结果
        
        返回:
            可视化后的帧
        """
        try:
            # 使用ultralytics内置的plot方法生成可视化图像
            if results and len(results) > 0 and detection_result['person_count'] > 0:
                try:
                    vis_frame = results[0].plot(
                        conf=False,
                        line_width=2,
                        font_size=0.5,
                        pil=False,
                        labels=False,
                        boxes=True,
                        kpt_radius=5
                    )
                except Exception as plot_error:
                    vis_frame = frame.copy()
            else:
                vis_frame = frame.copy()
            
            # 添加检测结果文本
            if detection_result['has_abnormal']:
                behavior_text = f"ABNORMAL: {detection_result['behavior_type']}"
                conf_text = f"Confidence: {detection_result['confidence']:.2f}"
                
                # 如果是跌倒检测，显示详细信息
                if detection_result['behavior_type'] == 'FALL':
                    lines = [behavior_text, conf_text]
                    
                    # 如果使用角度检测方法
                    if detection_result.get('fall_angle'):
                        fall_angle = detection_result['fall_angle']
                        angle_deg = fall_angle.get('angle_deg', 0)
                        angle_threshold = fall_angle.get('angle_threshold', 30.0)
                        lines.append(f"Angle: {angle_deg:.1f}° (threshold: {angle_threshold:.1f}°)")
                    
                    # 如果使用多指标检测方法
                    elif detection_result.get('fall_details'):
                        fall_details = detection_result['fall_details']
                        lines.extend([
                            f"View: {'Side' if fall_details['is_side_view'] else 'Front'}",
                            f"Indicators: {fall_details['indicator_count']}/{fall_details['min_indicators']}"
                        ])
                        
                        # 添加指标详情
                        for ind in fall_details['indicators']:
                            # 根据指标类型格式化数值
                            value = ind['value']
                            indicator_name = ind['name']
                            # 格式化数值（指标名称已经是英文）
                            if 'angle' in indicator_name.lower() or 'anomaly' in indicator_name.lower():
                                value_str = f"{value:.1f}°"
                            elif 'ratio' in str(value).lower() or 'position' in indicator_name.lower() or 'gravity' in indicator_name.lower():
                                value_str = f"{value:.3f}"
                            else:
                                value_str = f"{value:.2f}"
                            lines.append(f"- {indicator_name}: {value_str} (conf: {ind['confidence']:.2f})")
                    
                    # 计算文本区域大小
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    font_scale = 0.45
                    thickness = 1
                    line_height = 20
                    padding = 10
                    
                    max_width = 0
                    for line in lines:
                        (text_width, text_height), _ = cv2.getTextSize(line, font, font_scale, thickness)
                        max_width = max(max_width, text_width)
                    
                    box_width = max_width + padding * 2
                    box_height = len(lines) * line_height + padding * 2
                    
                    # 添加半透明背景
                    overlay = vis_frame.copy()
                    cv2.rectangle(overlay, (10, 10), (10 + box_width, 10 + box_height), (0, 0, 0), -1)
                    cv2.addWeighted(overlay, 0.7, vis_frame, 0.3, 0, vis_frame)
                    
                    # 添加文字
                    y_pos = 30
                    for i, line in enumerate(lines):
                        color = (0, 0, 255) if i == 0 else ((255, 255, 255) if i < 4 else (200, 200, 200))
                        cv2.putText(vis_frame, line, (18, y_pos),
                                   font, font_scale, color, thickness)
                        y_pos += line_height
                else:
                    # 其他异常行为，显示简单信息
                    overlay = vis_frame.copy()
                    cv2.rectangle(overlay, (10, 10), (350, 70), (0, 0, 0), -1)
                    cv2.addWeighted(overlay, 0.6, vis_frame, 0.4, 0, vis_frame)
                    
                    cv2.putText(vis_frame, behavior_text, (18, 33),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)
                    cv2.putText(vis_frame, conf_text, (18, 55),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            else:
                overlay = vis_frame.copy()
                cv2.rectangle(overlay, (10, 10), (200, 50), (0, 0, 0), -1)
                cv2.addWeighted(overlay, 0.6, vis_frame, 0.4, 0, vis_frame)
                
                cv2.putText(vis_frame, "Status: NORMAL", (18, 35),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
            
            # 添加人数统计
            person_count_text = f"Persons: {detection_result['person_count']}"
            text_size = cv2.getTextSize(person_count_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
            text_x = 18
            text_y = vis_frame.shape[0] - 22
            
            overlay = vis_frame.copy()
            cv2.rectangle(overlay, 
                         (text_x - 8, text_y - text_size[1] - 8),
                         (text_x + text_size[0] + 8, text_y + 8),
                         (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.6, vis_frame, 0.4, 0, vis_frame)
            
            cv2.putText(vis_frame, person_count_text, (text_x, text_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            return vis_frame
            
        except Exception as e:
            print(f"帧可视化失败: {e}")
            return frame.copy()
    
    def detect_video(self, video_path: str, visualize: bool = False, output_path: str = None) -> Dict[str, Any]:
        """
        检测视频中的异常行为
        
        参数:
            video_path: 视频路径
            visualize: 是否生成可视化视频
            output_path: 可视化视频保存路径
        
        返回:
            检测结果字典
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"无法打开视频: {video_path}")
        
        # 获取视频属性
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # 创建视频写入器（使用浏览器兼容的H.264编码）
        video_writer = None
        if visualize and output_path:
            # 尝试使用不同的编码器，优先使用浏览器兼容的H.264
            codecs_to_try = [
                # ('avc1', 'H.264 (avc1)'),
                # ('H264', 'H.264 (H264)'),
                # ('X264', 'H.264 (X264)'),
                ('mp4v', 'MPEG-4 (mp4v)')  # 备用方案
            ]
            
            for fourcc_str, codec_name in codecs_to_try:
                try:
                    fourcc = cv2.VideoWriter_fourcc(*fourcc_str)
                    video_writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
                    if video_writer.isOpened():
                        print(f"✓ 成功创建视频写入器: {output_path}")
                        print(f"  编码器: {codec_name}, fps={fps}, size={width}x{height}")
                        break
                    else:
                        video_writer.release()
                        video_writer = None
                except Exception as e:
                    print(f"× 尝试编码器 {codec_name} 失败: {e}")
                    continue
            
            if video_writer is None or not video_writer.isOpened():
                raise RuntimeError("无法创建视频写入器，请检查OpenCV和编码器支持")
        
        frame_count = 0
        abnormal_frames = []  # 异常行为帧
        person_detected_frames = []  # 检测到人的帧
        all_detections = []  # 所有检测结果
        detection_segments = []  # 检测片段（连续检测到人的时间段）
        
        current_segment = None  # 当前检测片段
        
        # 检查VideoWriter是否成功创建
        if visualize and video_writer is None:
            print(f"× 警告：VideoWriter未创建，跳过可视化")
            visualize = False
        
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                frame_count += 1
                
                # 进行检测（不跳帧，确保视频完整）
                results = self.model(
                    frame,
                    conf=self.conf_threshold,
                    iou=self.iou_threshold,
                    device=MODEL_DEVICE,
                )
                frame_result = self._analyze_results(results, frame.shape)
                
                # 记录异常帧
                if frame_result['has_abnormal']:
                    abnormal_frames.append({
                        'frame_number': frame_count,
                        'timestamp': frame_count / fps,
                        'behavior_type': frame_result['behavior_type'],
                        'confidence': frame_result['confidence'],
                        'person_count': frame_result['person_count']
                    })
                
                # 记录检测到人的帧
                if frame_result['person_count'] > 0:
                    person_detected_frames.append({
                        'frame_number': frame_count,
                        'timestamp': frame_count / fps,
                        'person_count': frame_result['person_count'],
                        'has_abnormal': frame_result['has_abnormal'],
                        'behavior_type': frame_result['behavior_type'],
                        'confidence': frame_result['confidence']
                    })
                    
                    # 检测片段管理
                    if current_segment is None:
                        # 开始新片段
                        current_segment = {
                            'start_frame': frame_count,
                            'end_frame': frame_count,
                            'start_time': frame_count / fps,
                            'end_time': frame_count / fps,
                            'person_count_max': frame_result['person_count'],
                            'has_abnormal': frame_result['has_abnormal'],
                            'abnormal_count': 1 if frame_result['has_abnormal'] else 0,
                            'total_frames': 1
                        }
                    else:
                        # 继续当前片段
                        current_segment['end_frame'] = frame_count
                        current_segment['end_time'] = frame_count / fps
                        current_segment['person_count_max'] = max(
                            current_segment['person_count_max'],
                            frame_result['person_count']
                        )
                        current_segment['has_abnormal'] = current_segment['has_abnormal'] or frame_result['has_abnormal']
                        if frame_result['has_abnormal']:
                            current_segment['abnormal_count'] += 1
                        current_segment['total_frames'] += 1
                else:
                    # 未检测到人，结束当前片段
                    if current_segment is not None:
                        # 保存片段
                        current_segment['duration'] = current_segment['end_time'] - current_segment['start_time']
                        detection_segments.append(current_segment)
                        print(f"保存检测片段: 帧{current_segment['start_frame']}-{current_segment['end_frame']}, "
                              f"时长{current_segment['duration']:.1f}s, "
                              f"最多{current_segment['person_count_max']}人, "
                              f"异常帧{current_segment['abnormal_count']}帧")
                        current_segment = None
                
                all_detections.append(frame_result)
                
                # 生成可视化帧并写入
                if video_writer is not None and video_writer.isOpened():
                    vis_frame = self._visualize_frame(frame, results, frame_result)
                    # 确保帧尺寸正确
                    if vis_frame.shape[1] == width and vis_frame.shape[0] == height:
                        video_writer.write(vis_frame)
                    else:
                        # 如果尺寸不匹配，resize
                        vis_frame = cv2.resize(vis_frame, (width, height))
                        video_writer.write(vis_frame)
                
                # 每100帧打印一次进度
                if frame_count % 100 == 0:
                    print(f"  已处理 {frame_count} 帧...")
            
            # 处理最后一个片段
            if current_segment is not None:
                current_segment['duration'] = current_segment['end_time'] - current_segment['start_time']
                detection_segments.append(current_segment)
                print(f"保存最后检测片段: 帧{current_segment['start_frame']}-{current_segment['end_frame']}, "
                      f"时长{current_segment['duration']:.1f}s")
                    
        finally:
            cap.release()
            if video_writer is not None:
                video_writer.release()
                print(f"✓ 视频处理完成，共 {frame_count} 帧")
                if visualize and output_path:
                    import os
                    if os.path.exists(output_path):
                        file_size = os.path.getsize(output_path) / (1024 * 1024)
                        print(f"✓ 视频可视化完成: {output_path} ({file_size:.2f} MB)")
                    else:
                        print(f"× 警告：输出文件未生成: {output_path}")
        
        # 汇总结果（时序平滑：投票 + 平均置信度）
        has_abnormal = len(abnormal_frames) > 0
        if has_abnormal:
            behavior_types = [f['behavior_type'] for f in abnormal_frames]
            # 投票：最常出现的行为类型
            from collections import Counter
            behavior_type = Counter(behavior_types).most_common(1)[0][0]
            
            # 平均置信度
            confidence = np.mean([f['confidence'] for f in abnormal_frames])
            
            description = f"视频中检测到{len(abnormal_frames)}帧异常行为: {behavior_type}"
        else:
            behavior_type = None
            confidence = 0.0
            description = "未检测到异常行为"
        
        # 统计信息
        total_person_frames = len(person_detected_frames)
        total_segments = len(detection_segments)
        
        if total_person_frames > 0:
            description += f"，共{total_person_frames}帧检测到人，{total_segments}个检测片段"
        
        print(f"\n检测统计:")
        print(f"  总帧数: {frame_count}")
        print(f"  检测到人的帧数: {total_person_frames}")
        print(f"  异常帧数: {len(abnormal_frames)}")
        print(f"  检测片段数: {total_segments}")
        
        return {
            'has_abnormal': has_abnormal,
            'behavior_type': behavior_type,
            'confidence': float(confidence),
            'person_count': max([d['person_count'] for d in all_detections]) if all_detections else 0,
            'description': description,
            'frame_count': frame_count,
            'abnormal_frames': abnormal_frames,
            'person_detected_frames': person_detected_frames,  # 检测到人的所有帧
            'detection_segments': detection_segments,  # 检测片段
            'total_person_frames': total_person_frames,  # 检测到人的总帧数
            'total_segments': total_segments  # 检测片段总数
        }
    
    def _analyze_results(self, results, image_shape) -> Dict[str, Any]:
        """
        分析检测结果
        
        参数:
            results: YOLO检测结果
            image_shape: 图片尺寸
        
        返回:
            分析结果字典
        """
        result = results[0]
        
        # 提取关键点
        persons = []
        
        # 检查是否是pose模型（有关键点输出）
        if result.keypoints is not None and result.keypoints.data is not None:
            keypoints = result.keypoints.data.cpu().numpy()
            boxes = result.boxes.data.cpu().numpy() if result.boxes is not None else []
            
            # 确保keypoints数组不为空且有正确的维度
            if keypoints.size > 0 and len(keypoints.shape) >= 2:
                for i, kps in enumerate(keypoints):
                    person_data = {
                        'keypoints': kps.tolist(),
                        'box': boxes[i][:4].tolist() if i < len(boxes) else None
                    }
                    persons.append(person_data)
            else:
                print(f"关键点数组为空或维度不正确: shape={keypoints.shape}")
        else:
            # 如果不是pose模型，尝试从boxes中提取人员信息
            # 这对于非pose模型可能有boxes但没有keypoints
            if result.boxes is not None and result.boxes.data is not None:
                boxes = result.boxes.data.cpu().numpy()
                if boxes.size > 0:
                    print(f"[WARN] 检测到boxes但无keypoints，模型可能不是pose模型。boxes数量: {len(boxes)}")
                    # 如果没有keypoints，至少可以从boxes中知道检测到了对象
                    # 但由于没有关键点，无法进行跌倒检测，所以persons列表保持为空
        
        # 检测异常行为
        abnormal_behavior = self._detect_abnormal_behavior(persons, image_shape)
        
        result_dict = {
            'has_abnormal': abnormal_behavior['is_abnormal'],
            'behavior_type': abnormal_behavior['behavior_type'],
            'confidence': abnormal_behavior['confidence'],
            'person_count': len(persons),
            'persons': persons,
            'description': abnormal_behavior['description']
        }
        
        # 如果是跌倒检测，传递详细信息用于可视化
        if abnormal_behavior.get('fall_details'):
            result_dict['fall_details'] = abnormal_behavior['fall_details']
        
        # 如果是跌倒检测（使用角度检测方法），传递角度信息用于可视化
        if abnormal_behavior.get('fall_angle'):
            result_dict['fall_angle'] = abnormal_behavior['fall_angle']
        
        return result_dict
    
    def _detect_abnormal_behavior(self, persons: List[Dict], image_shape) -> Dict[str, Any]:
        """
        检测异常行为
        
        参数:
            persons: 检测到的人员列表
            image_shape: 图片尺寸
        
        返回:
            {
                'is_abnormal': bool,
                'behavior_type': str,
                'confidence': float,
                'description': str
            }
        """
        if len(persons) == 0:
            return {
                'is_abnormal': False,
                'behavior_type': None,
                'confidence': 0.0,
                'description': '未检测到人员'
            }
        
        # 1. 检测跌倒
        for person in persons:
            fall_result = self._detect_fall_angle(person['keypoints'], image_shape)
            if fall_result['is_fall']:
                return {
                    'is_abnormal': True,
                    'behavior_type': 'FALL',
                    'confidence': fall_result['confidence'],
                    'description': fall_result['description'],
                    'fall_details': fall_result.get('fall_details', None),  # 传递详细信息（如果存在）
                    'fall_angle': fall_result.get('fall_angle', None)  # 传递角度信息
                }
        
        # 2. 检测打架（需要多人）
        # if len(persons) >= 2:
        #     fight_result = self._detect_fight(persons, image_shape)
        #     if fight_result['is_fight']:
        #         return {
        #             'is_abnormal': True,
        #             'behavior_type': 'FIGHT',
        #             'confidence': fight_result['confidence'],
        #             'description': fight_result['description']
        #         }
        
        # 3. 检测异常姿态
        # for person in persons:
        #     abnormal_pose_result = self._detect_abnormal_pose(person['keypoints'], image_shape)
        #     if abnormal_pose_result['is_abnormal']:
        #         return {
        #             'is_abnormal': True,
        #             'behavior_type': 'ABNORMAL_POSE',
        #             'confidence': abnormal_pose_result['confidence'],
        #             'description': abnormal_pose_result['description']
        #         }
        
        # 未检测到异常行为
        # 计算正常行为的置信度（基于平均关键点置信度）
        normal_confidence = self._calculate_normal_confidence(persons)
        
        return {
            'is_abnormal': False,
            'behavior_type': None,
            'confidence': normal_confidence,
            'description': '未检测到异常行为'
        }
    
    def _calculate_normal_confidence(self, persons: List[Dict]) -> float:
        """
        计算正常行为的置信度
        基于检测到的人体关键点的平均置信度
        """
        if not persons:
            return 0.0
        
        total_confidence = 0.0
        total_keypoints = 0
        
        for person in persons:
            keypoints = np.array(person['keypoints'])
            if keypoints.size == 0 or len(keypoints.shape) < 2:
                continue
            
            # 提取置信度（第三列）
            confidences = keypoints[:, 2] if keypoints.shape[1] >= 3 else []
            valid_confidences = [c for c in confidences if c > 0]
            
            if valid_confidences:
                total_confidence += sum(valid_confidences)
                total_keypoints += len(valid_confidences)
        
        if total_keypoints > 0:
            avg_confidence = total_confidence / total_keypoints
            return float(avg_confidence)
        
        return 0.0
    
    def _detect_fall(self, keypoints, image_shape) -> Dict[str, Any]:
        """
        检测跌倒行为
        
        策略：
        1. 判断视角（正面/侧面）
        2. 检查身体重心高度
        3. 检查头部位置
        4. 检查身体宽高比（根据视角调整阈值）
        5. 检查身体角度（根据视角调整阈值）
        6. 检查膝盖位置
        7. 多指标综合判断（需要多个条件同时满足）
        
        参数:
            keypoints: 人体关键点 (17, 3) [x, y, confidence]
            image_shape: 图片尺寸 (height, width, channels)
        
        返回:
            检测结果字典
        """
        try:
            keypoints = np.array(keypoints)
            
            # 添加检查：确保keypoints不为空
            if keypoints.size == 0 or len(keypoints.shape) < 2:
                print(f"跌倒检测: 关键点数据无效: shape={keypoints.shape}")
                return {
                    'is_fall': False,
                    'confidence': 0.0,
                    'description': '关键点数据不足'
                }
            
            # 提取关键点
            nose = keypoints[self.KEYPOINT_DICT['nose']]
            left_shoulder = keypoints[self.KEYPOINT_DICT['left_shoulder']]
            right_shoulder = keypoints[self.KEYPOINT_DICT['right_shoulder']]
            left_hip = keypoints[self.KEYPOINT_DICT['left_hip']]
            right_hip = keypoints[self.KEYPOINT_DICT['right_hip']]
            left_knee = keypoints[self.KEYPOINT_DICT['left_knee']]
            right_knee = keypoints[self.KEYPOINT_DICT['right_knee']]
            left_ankle = keypoints[self.KEYPOINT_DICT['left_ankle']]
            right_ankle = keypoints[self.KEYPOINT_DICT['right_ankle']]
            left_wrist = keypoints[self.KEYPOINT_DICT['left_wrist']]
            right_wrist = keypoints[self.KEYPOINT_DICT['right_wrist']]
            left_elbow = keypoints[self.KEYPOINT_DICT['left_elbow']]
            right_elbow = keypoints[self.KEYPOINT_DICT['right_elbow']]
            
            # 检查关键点是否可见（置信度 > 0.3）
            if nose[2] < 0.3 or (left_shoulder[2] < 0.3 and right_shoulder[2] < 0.3):
                return {
                    'is_fall': False,
                    'confidence': 0.0,
                    'description': '关键点不可见'
                }
            
            # 计算肩膀和臀部中心点
            shoulder_center = ((left_shoulder + right_shoulder) / 2) if (left_shoulder[2] > 0.3 and right_shoulder[2] > 0.3) else left_shoulder if left_shoulder[2] > 0.3 else right_shoulder
            hip_center = ((left_hip + right_hip) / 2) if (left_hip[2] > 0.3 and right_hip[2] > 0.3) else left_hip if left_hip[2] > 0.3 else right_hip
            
            # ========== 新增：判断视角（正面/侧面） ==========
            is_side_view = False
            if left_shoulder[2] > 0.3 and right_shoulder[2] > 0.3:
                # 计算肩膀宽度（水平距离）
                shoulder_width = abs(left_shoulder[0] - right_shoulder[0])
                # 计算肩膀到臀部的垂直距离
                shoulder_hip_vertical = abs(shoulder_center[1] - hip_center[1]) if hip_center[2] > 0.3 else image_shape[0] * 0.3
                
                # 如果肩膀宽度相对于垂直距离较小，可能是侧面视角
                # 侧面视角：肩膀宽度/垂直距离 < 0.3
                if shoulder_hip_vertical > 0:
                    shoulder_ratio = shoulder_width / shoulder_hip_vertical
                    is_side_view = shoulder_ratio < 0.3
                    print(f"视角判断: 肩膀宽度={shoulder_width:.1f}px, 垂直距离={shoulder_hip_vertical:.1f}px, "
                          f"比例={shoulder_ratio:.3f}, 侧面视角={is_side_view}")
            
            # 根据视角调整阈值
            if is_side_view:
                # 侧面视角：更严格的阈值
                aspect_ratio_threshold = 1.8  # 侧面时宽高比自然更大
                angle_threshold = 100  # 侧面时角度阈值提高
                body_height_ratio_threshold = 0.6  # 重心阈值提高
                nose_y_ratio_threshold = 0.65  # 头部位置阈值提高
                min_indicators = 3  # 需要至少3个指标同时满足
            else:
                # 正面视角：原有阈值
                aspect_ratio_threshold = 1.2
                angle_threshold = 90
                body_height_ratio_threshold = 0.5
                nose_y_ratio_threshold = 0.55
                min_indicators = 2  # 需要至少2个指标同时满足
            
            # 初始化检测结果
            fall_detected = False
            confidence = 0.0
            detection_reason = ""
            
            # 用于多指标综合判断
            fall_indicators = []  # 记录满足的指标
            
            # 检查是否是坐姿或运动姿态（避免误判）
            is_sitting = False
            is_exercise_pose = False
            
            # ========== 改进坐姿判断 ==========
            # 坐姿判断：臀部在膝盖上方，且膝盖弯曲，且头部位置较高
            if (left_hip[2] > 0.3 and left_knee[2] > 0.3 and left_ankle[2] > 0.3):
                # 检查臀部是否明显在膝盖上方（y坐标较小）
                hip_knee_vertical = left_knee[1] - left_hip[1]
                if hip_knee_vertical > image_shape[0] * 0.08:  # 臀部明显在膝盖上方
                    # 检查膝盖弯曲（膝盖到脚踝的距离）
                    knee_ankle_dist = np.linalg.norm(left_knee[:2] - left_ankle[:2])
                    # 检查头部位置（坐姿时头部应该相对较高）
                    if nose[2] > 0.3:
                        head_relative_to_hip = nose[1] - left_hip[1]
                        # 坐姿：头部在臀部上方或接近
                        if head_relative_to_hip < image_shape[0] * 0.2:
                            is_sitting = True
                            print(f"检测到坐姿（左侧）：臀部-膝盖垂直距离={hip_knee_vertical:.1f}px, "
                                  f"头部相对臀部={head_relative_to_hip:.1f}px")
            
            if not is_sitting and (right_hip[2] > 0.3 and right_knee[2] > 0.3 and right_ankle[2] > 0.3):
                hip_knee_vertical = right_knee[1] - right_hip[1]
                if hip_knee_vertical > image_shape[0] * 0.08:
                    knee_ankle_dist = np.linalg.norm(right_knee[:2] - right_ankle[:2])
                    if nose[2] > 0.3:
                        head_relative_to_hip = nose[1] - right_hip[1]
                        if head_relative_to_hip < image_shape[0] * 0.2:
                            is_sitting = True
                            print(f"检测到坐姿（右侧）：臀部-膝盖垂直距离={hip_knee_vertical:.1f}px, "
                                  f"头部相对臀部={head_relative_to_hip:.1f}px")
            
            # 运动姿态判断（俯卧撑、平板支撑等）
            # 更严格的条件：双手都可见、在身体两侧支撑、身体相对水平
            if (left_shoulder[2] > 0.3 and right_shoulder[2] > 0.3 and 
                left_wrist[2] > 0.5 and right_wrist[2] > 0.5):
                
                # 计算身体中心点
                body_center_x = (left_shoulder[0] + right_shoulder[0]) / 2
                body_center_y = (left_shoulder[1] + right_shoulder[1]) / 2
                
                # 检查双手是否在身体两侧（左右分开）
                left_wrist_left = left_wrist[0] < body_center_x - image_shape[1] * 0.1
                right_wrist_right = right_wrist[0] > body_center_x + image_shape[1] * 0.1
                
                # 检查双手是否在肩膀下方支撑
                hands_below_shoulder = (left_wrist[1] > body_center_y and 
                                       right_wrist[1] > body_center_y)
                
                # 检查身体是否相对水平（肩膀和臀部高度差不大）
                if hip_center[2] > 0.3:
                    shoulder_hip_height = abs(shoulder_center[1] - hip_center[1])
                    body_horizontal = shoulder_hip_height < image_shape[0] * 0.2
                else:
                    body_horizontal = False
                
                # 同时满足：双手分开支撑 + 在肩膀下方 + 身体水平
                if left_wrist_left and right_wrist_right and hands_below_shoulder and body_horizontal:
                    is_exercise_pose = True
                    print(f"检测到运动姿态：双手支撑平板姿态")
            
            # 如果是坐姿或运动姿态，直接返回不判定为跌倒
            if is_sitting or is_exercise_pose:
                return {
                    'is_fall': False,
                    'confidence': 0.0,
                    'description': '检测到坐姿或运动姿态，非跌倒'
                }
            
            # ========== 方法1：计算人体重心高度 ==========
            body_center_y = (nose[1] + shoulder_center[1] + hip_center[1]) / 3
            body_height_ratio = body_center_y / image_shape[0]
            print(f"身体重心比例: {body_height_ratio:.3f} (阈值: {body_height_ratio_threshold:.2f})")
            
            if body_height_ratio > body_height_ratio_threshold:
                indicator_confidence = min(0.95, (body_height_ratio - body_height_ratio_threshold) / 0.4 * 0.6 + 0.35)
                fall_indicators.append({
                    'name': 'Low Center of Gravity',
                    'confidence': indicator_confidence,
                    'value': body_height_ratio
                })
                print(f"  ✓ 指标1满足：重心过低(ratio={body_height_ratio:.2f}), confidence={indicator_confidence:.2f}")
            
            # ========== 方法2：计算头部位置 ==========
            if nose[2] > 0.3:
                nose_y_ratio = nose[1] / image_shape[0]
                print(f"头部位置比例: {nose_y_ratio:.3f} (阈值: {nose_y_ratio_threshold:.2f})")
                
                if nose_y_ratio > nose_y_ratio_threshold:
                    indicator_confidence = min(0.92, (nose_y_ratio - nose_y_ratio_threshold) / 0.35 * 0.6 + 0.32)
                    fall_indicators.append({
                        'name': 'Low Head Position',
                        'confidence': indicator_confidence,
                        'value': nose_y_ratio
                    })
                    print(f"  ✓ 指标2满足：头部过低(ratio={nose_y_ratio:.2f}), confidence={indicator_confidence:.2f}")
            else:
                print(f"头部不可见，跳过头部位置检测")
            
            # ========== 方法3：计算人体宽高比（根据视角调整阈值） ==========
            all_x = [kpt[0] for kpt in keypoints if kpt[2] > 0.3]
            all_y = [kpt[1] for kpt in keypoints if kpt[2] > 0.3]
            
            if len(all_x) > 0 and len(all_y) > 0:
                body_width = max(all_x) - min(all_x)
                body_height = max(all_y) - min(all_y)
                
                if body_height > 0:
                    aspect_ratio = body_width / body_height
                    print(f"身体宽高比: {aspect_ratio:.2f} (阈值: {aspect_ratio_threshold:.2f}, "
                          f"width={body_width:.1f}, height={body_height:.1f})")
                    
                    if aspect_ratio > aspect_ratio_threshold:
                        indicator_confidence = min(0.90, (aspect_ratio - aspect_ratio_threshold) / 1.2 * 0.5 + 0.40)
                        fall_indicators.append({
                            'name': 'Horizontal Body',
                            'confidence': indicator_confidence,
                            'value': aspect_ratio
                        })
                        print(f"  ✓ 指标3满足：身体横向(ratio={aspect_ratio:.2f}), confidence={indicator_confidence:.2f}")
            
            # ========== 方法4：计算人体角度（根据视角调整阈值） ==========
            if hip_center[2] > 0.3:
                dx = shoulder_center[0] - hip_center[0]
                dy = shoulder_center[1] - hip_center[1]
                
                if abs(dy) > 1:  # 避免除零
                    angle = abs(math.atan2(dx, dy) * 180 / math.pi)
                    print(f"身体角度: {angle:.1f}° (阈值: {angle_threshold}°)")
                    
                    if angle > angle_threshold:
                        indicator_confidence = min(0.88, (angle - angle_threshold) / 45 * 0.6 + 0.28)
                        fall_indicators.append({
                            'name': 'Angle Anomaly',
                            'confidence': indicator_confidence,
                            'value': angle
                        })
                        print(f"  ✓ 指标4满足：角度异常({angle:.1f}°), confidence={indicator_confidence:.2f}")
            
            # ========== 方法5：检查膝盖位置 ==========
            if left_knee[2] > 0.3 or right_knee[2] > 0.3:
                knee_y = max(left_knee[1] if left_knee[2] > 0.3 else 0,
                            right_knee[1] if right_knee[2] > 0.3 else 0)
                knee_y_ratio = knee_y / image_shape[0]
                
                print(f"膝盖位置比例: {knee_y_ratio:.3f}")
                
                # 膝盖位置阈值保持0.7（不受视角影响）
                if knee_y_ratio > 0.7:
                    indicator_confidence = min(0.86, (knee_y_ratio - 0.7) / 0.25 * 0.4 + 0.46)
                    fall_indicators.append({
                        'name': 'Low Knee Position',
                        'confidence': indicator_confidence,
                        'value': knee_y_ratio
                    })
                    print(f"  ✓ 指标5满足：膝盖过低(ratio={knee_y_ratio:.2f}), confidence={indicator_confidence:.2f}")
            
            # ========== 多指标综合判断 ==========
            print(f"\n跌倒检测汇总: 满足指标数={len(fall_indicators)}, 需要至少{min_indicators}个指标")
            
            if len(fall_indicators) >= min_indicators:
                # 计算综合置信度（加权平均）
                total_confidence = sum([ind['confidence'] for ind in fall_indicators])
                avg_confidence = total_confidence / len(fall_indicators)
                
                # 根据满足的指标数量调整置信度
                indicator_bonus = (len(fall_indicators) - min_indicators) * 0.05
                confidence = min(0.95, avg_confidence + indicator_bonus)
                
                # 生成检测原因描述
                indicator_names = [ind['name'] for ind in fall_indicators]
                detection_reason = f"多指标检测({', '.join(indicator_names)})"
                
                fall_detected = True
                
                print("=" * 50)
                print(f"最终判定：跌倒检测成功！")
                print(f"视角：{'侧面' if is_side_view else '正面'}")
                print(f"满足指标：{len(fall_indicators)}/{min_indicators}")
                print(f"原因：{detection_reason}")
                print(f"置信度：{confidence:.2f}")
                print("=" * 50)
            else:
                print(f"未检测到跌倒：指标不足（{len(fall_indicators)}/{min_indicators}）")
            
            # 准备返回的详细信息（用于可视化）
            fall_details = None
            if fall_detected:
                fall_details = {
                    'is_side_view': is_side_view,
                    'indicators': fall_indicators,
                    'indicator_count': len(fall_indicators),
                    'min_indicators': min_indicators,
                    'detection_reason': detection_reason
                }
            
            return {
                'is_fall': fall_detected,
                'confidence': float(confidence),
                'description': f'检测到跌倒行为: {detection_reason}' if fall_detected else '未检测到跌倒',
                'fall_details': fall_details  # 添加详细信息用于可视化
            }
            
        except Exception as e:
            print(f"跌倒检测错误: {e}")
            import traceback
            traceback.print_exc()
            return {
                'is_fall': False,
                'confidence': 0.0,
                'description': f'检测失败: {str(e)}'
            }
    
    def _detect_fall_angle(self, keypoints, image_shape) -> Dict[str, Any]:
        """
        基于角度检测跌倒行为
        
        策略：
        1. 计算左右手腕的中点A
        2. 计算左右脚踝的中点B
        3. 连接AB是一条直线
        4. 计算AB直线与边界框下底边（水平线）的夹角
        5. 当夹角小于某个阈值时，则认为发生跌倒
        
        参数:
            keypoints: 人体关键点 (17, 3) [x, y, confidence]
            image_shape: 图片尺寸 (height, width, channels)
        
        返回:
            检测结果字典
        """
        try:
            keypoints = np.array(keypoints)
            
            # 添加检查：确保keypoints不为空
            if keypoints.size == 0 or len(keypoints.shape) < 2:
                print(f"跌倒角度检测: 关键点数据无效: shape={keypoints.shape}")
                return {
                    'is_fall': False,
                    'confidence': 0.0,
                    'description': '关键点数据不足'
                }
            
            # 提取关键点
            left_wrist = keypoints[self.KEYPOINT_DICT['left_wrist']]
            right_wrist = keypoints[self.KEYPOINT_DICT['right_wrist']]
            left_ankle = keypoints[self.KEYPOINT_DICT['left_ankle']]
            right_ankle = keypoints[self.KEYPOINT_DICT['right_ankle']]
            
            # 检查关键点是否可见（置信度 > 0.3）
            # 至少需要一只手腕和一只脚踝可见
            valid_wrist = []
            if left_wrist[2] > 0.3:
                valid_wrist.append(left_wrist)
            if right_wrist[2] > 0.3:
                valid_wrist.append(right_wrist)
            
            valid_ankle = []
            if left_ankle[2] > 0.3:
                valid_ankle.append(left_ankle)
            if right_ankle[2] > 0.3:
                valid_ankle.append(right_ankle)
            
            if len(valid_wrist) == 0 or len(valid_ankle) == 0:
                return {
                    'is_fall': False,
                    'confidence': 0.0,
                    'description': '手腕或脚踝关键点不可见'
                }
            
            # 计算手腕中点A
            if len(valid_wrist) == 2:
                # 两只手腕都可见，计算中点
                point_A = ((valid_wrist[0][0] + valid_wrist[1][0]) / 2.0,
                          (valid_wrist[0][1] + valid_wrist[1][1]) / 2.0)
            else:
                # 只有一只手腕可见，直接使用
                point_A = (valid_wrist[0][0], valid_wrist[0][1])
            
            # 计算脚踝中点B
            if len(valid_ankle) == 2:
                # 两只脚踝都可见，计算中点
                point_B = ((valid_ankle[0][0] + valid_ankle[1][0]) / 2.0,
                          (valid_ankle[0][1] + valid_ankle[1][1]) / 2.0)
            else:
                # 只有一只脚踝可见，直接使用
                point_B = (valid_ankle[0][0], valid_ankle[0][1])
            
            # 计算边界框的下底边位置
            # 从所有可见关键点中找到y坐标的最大值（最下方的点）
            all_valid_y = [kpt[1] for kpt in keypoints if kpt[2] > 0.3]
            if len(all_valid_y) == 0:
                return {
                    'is_fall': False,
                    'confidence': 0.0,
                    'description': '没有可见的关键点'
                }
            
            bottom_y = max(all_valid_y)
            
            # 计算AB直线的向量
            dx = point_B[0] - point_A[0]  # x方向的变化
            dy = point_B[1] - point_A[1]  # y方向的变化（注意y轴向下为正）
            
            # 处理边界情况：如果AB线完全水平（dy=0），角度为0度
            if abs(dy) < 1e-6:
                angle_deg = 0.0
            # 处理边界情况：如果AB线完全垂直（dx=0），角度为90度
            elif abs(dx) < 1e-6:
                angle_deg = 90.0
            else:
                # 计算AB直线与水平线的夹角（以度为单位）
                # 使用atan2计算角度，注意：图像坐标系中y轴向下
                # atan2(abs(dy), abs(dx)) 给出0-90度的角度
                # 角度越小，AB线越接近水平
                angle_rad = math.atan2(abs(dy), abs(dx))
                angle_deg = math.degrees(angle_rad)
            
            # AB与水平线的夹角：
            # - 角度接近0度：AB接近水平，可能跌倒（人体横躺）
            # - 角度接近90度：AB接近垂直，正常站立
            # 我们只需要0-90度的角度值，已经是正确的了
            
            print(f"跌倒角度检测: 手腕中点A=({point_A[0]:.1f}, {point_A[1]:.1f}), "
                  f"脚踝中点B=({point_B[0]:.1f}, {point_B[1]:.1f}), "
                  f"AB向量=({dx:.1f}, {dy:.1f}), "
                  f"AB与水平线夹角={angle_deg:.1f}°")
            self.write_log(f"跌倒角度检测: 手腕中点A=({point_A[0]:.1f}, {point_A[1]:.1f}), "
                  f"脚踝中点B=({point_B[0]:.1f}, {point_B[1]:.1f}), "
                  f"AB向量=({dx:.1f}, {dy:.1f}), "
                  f"AB与水平线夹角={angle_deg:.1f}°")
            # 设置角度阈值（度）
            # 当角度小于阈值时，认为AB接近水平，可能发生跌倒
            # 阈值可以设置为30度或更小
            angle_threshold = 10.0
            
            # 判断是否跌倒
            if angle_deg < angle_threshold:
                # 计算置信度：角度越小，置信度越高
                # 角度为0度时，置信度为0.95；角度为阈值时，置信度为0.6
                confidence = 0.95 - (angle_deg / angle_threshold) * 0.35
                confidence = max(0.6, min(0.95, confidence))
                
                return {
                    'is_fall': True,
                    'confidence': float(confidence),
                    'description': f'检测到跌倒行为：AB线与水平线夹角={angle_deg:.1f}°（阈值={angle_threshold}°）',
                    'fall_angle': {
                        'angle_deg': float(angle_deg),
                        'angle_threshold': angle_threshold,
                        'point_A': point_A,
                        'point_B': point_B,
                        'bottom_y': float(bottom_y)
                    }
                }
            else:
                return {
                    'is_fall': False,
                    'confidence': 0.0,
                    'description': f'未检测到跌倒：AB线与水平线夹角={angle_deg:.1f}°（阈值={angle_threshold}°）'
                }
            
        except Exception as e:
            print(f"跌倒角度检测错误: {e}")
            import traceback
            traceback.print_exc()
            return {
                'is_fall': False,
                'confidence': 0.0,
                'description': f'检测失败: {str(e)}'
            }
    def write_log(self, text):
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except:
            pass
    def _detect_abnormal_pose(self, keypoints, image_shape) -> Dict[str, Any]:
        """
        检测异常姿态
        """
        try:
            keypoints = np.array(keypoints)
            
            # 添加检查：确保keypoints不为空
            if keypoints.size == 0 or len(keypoints.shape) < 2:
                print(f"异常姿态检测: 关键点数据无效: shape={keypoints.shape}")
                return {
                    'is_abnormal': False,
                    'confidence': 0.0,
                    'description': '关键点数据不足'
                }
            
            # 这里可以添加其他异常姿态检测逻辑
            # 例如：蹲下、爬行、倒挂等
            
            return {
                'is_abnormal': False,
                'confidence': 0.0,
                'description': '姿态正常'
            }
        except Exception as e:
            print(f"异常姿态检测错误: {e}")
            return {
                'is_abnormal': False,
                'confidence': 0.0,
                'description': f'检测失败: {str(e)}'
            }
    
    def _detect_fight(self, persons: List[Dict], image_shape) -> Dict[str, Any]:
        """
        检测打架行为
        
        策略：
        1. 两人距离很近
        2. 身体有交叠
        3. 手臂有挥动动作（手腕位置异常）
        4. 身体姿态不稳定
        """
        try:
            if len(persons) < 2:
                return {
                    'is_fight': False,
                    'confidence': 0.0,
                    'description': '人数不足'
                }
            
            # 打架检测：检查每对人
            for i in range(len(persons)):
                for j in range(i + 1, len(persons)):
                    person1_kps = np.array(persons[i]['keypoints'])
                    person2_kps = np.array(persons[j]['keypoints'])
                    
                    # 添加检查：确保关键点数组不为空
                    if person1_kps.size == 0 or len(person1_kps.shape) < 2:
                        continue
                    if person2_kps.size == 0 or len(person2_kps.shape) < 2:
                        continue
                    
                    # 提取有效关键点
                    p1_valid_kps = person1_kps[person1_kps[:, 2] > 0.3][:, :2]
                    p2_valid_kps = person2_kps[person2_kps[:, 2] > 0.3][:, :2]
                    
                    if len(p1_valid_kps) == 0 or len(p2_valid_kps) == 0:
                        continue
                    
                    # 计算两人中心点距离
                    person1_center = np.mean(p1_valid_kps, axis=0)
                    person2_center = np.mean(p2_valid_kps, axis=0)
                    
                    center_distance = np.linalg.norm(person1_center - person2_center)
                    distance_ratio = center_distance / image_shape[1]
                    
                    print(f"两人距离: {center_distance:.1f}px, 比例: {distance_ratio:.3f}")
                    
                    # 条件1：两人距离很近（小于图片宽度的25%）
                    if distance_ratio > 0.25:
                        continue
                    
                    # 条件2：检查手臂位置（是否有挥动或推搡动作）
                    # 提取手腕关键点
                    p1_left_wrist = person1_kps[self.KEYPOINT_DICT['left_wrist']]
                    p1_right_wrist = person1_kps[self.KEYPOINT_DICT['right_wrist']]
                    p2_left_wrist = person2_kps[self.KEYPOINT_DICT['left_wrist']]
                    p2_right_wrist = person2_kps[self.KEYPOINT_DICT['right_wrist']]
                    
                    # 检查是否有手腕朝向对方（可能是推搡或击打）
                    arms_engaged = False
                    if p1_left_wrist[2] > 0.3 and p1_right_wrist[2] > 0.3:
                        # 检查手腕是否在肩膀前方且靠近对方
                        p1_shoulder_center = (person1_kps[self.KEYPOINT_DICT['left_shoulder']][:2] + 
                                            person1_kps[self.KEYPOINT_DICT['right_shoulder']][:2]) / 2
                        
                        # 检查任一手腕是否在向对方方向移动
                        wrist_to_p2_left = np.linalg.norm(p1_left_wrist[:2] - person2_center)
                        wrist_to_p2_right = np.linalg.norm(p1_right_wrist[:2] - person2_center)
                        shoulder_to_p2 = np.linalg.norm(p1_shoulder_center - person2_center)
                        
                        if wrist_to_p2_left < shoulder_to_p2 or wrist_to_p2_right < shoulder_to_p2:
                            arms_engaged = True
                            print(f"检测到person1手臂朝向person2")
                    
                    # 条件3：检查两人是否有身体接触（关键点重叠）
                    has_overlap = False
                    for kp1 in p1_valid_kps:
                        for kp2 in p2_valid_kps:
                            kp_distance = np.linalg.norm(kp1 - kp2)
                            if kp_distance < image_shape[1] * 0.05:  # 关键点距离很近
                                has_overlap = True
                                break
                        if has_overlap:
                            break
                    
                    # 综合判断
                    fight_confidence = 0.0
                    if distance_ratio < 0.15:  # 非常近
                        fight_confidence += 0.4
                    elif distance_ratio < 0.25:  # 很近
                        fight_confidence += 0.2
                    
                    if arms_engaged:
                        fight_confidence += 0.3
                    
                    if has_overlap:
                        fight_confidence += 0.3
                        print(f"检测到身体接触")
                    
                    print(f"打架置信度: {fight_confidence:.2f}")
                    
                    # 如果置信度超过0.6，判定为打架
                    if fight_confidence >= 0.6:
                        return {
                            'is_fight': True,
                            'confidence': min(0.95, fight_confidence),
                            'description': f'检测到打架行为（距离={distance_ratio:.2f}, 置信度={fight_confidence:.2f}）'
                        }
            
            return {
                'is_fight': False,
                'confidence': 0.0,
                'description': '未检测到打架'
            }
        except Exception as e:
            print(f"打架检测错误: {e}")
            import traceback
            traceback.print_exc()
            return {
                'is_fight': False,
                'confidence': 0.0,
                'description': f'检测失败: {str(e)}'
            }

if __name__ == "__main__":
    vadModel = BehaviorDetector()
    vadModel.detect_video("./data/fall.mp4",True,"./data/fall_output1.mp4")
    # vadModel.detect_image("./data/fall1.png",True,"./data/fall1_output.png")
