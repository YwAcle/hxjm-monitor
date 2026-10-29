import cv2  
import threading
import time
import logging
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
import queue
import os
import base64
from datetime import datetime
from algorithms.person_recognition.face_recognition import FaceRecognizer
from db.device_status import DeviceStatusManager
from config.device_config import DEVICE_CONFIG
import av
from db.recognition_events import recognition_event_manager
from algorithms.person_recognition.person_tracking import PersonTracker
from utils.ffmpeg import RTMPStreamer  # 添加导入

def setup_logger():
    """设置日志配置"""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    # 创建一个文件处理器，指定编码为 utf-8
    file_handler = logging.FileHandler('logs/rtmp_stream.log', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # 创建一个格式化器
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', 
                                datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)
    
    # 添加处理器到日志记录器
    if not logger.handlers:
        logger.addHandler(file_handler)
    
    return logger

# 在类外初始化日志记录器
logger = setup_logger()

# 全局 GPU 跟踪器实例
global_person_tracker = None
global_tracker_lock = threading.RLock()

class VideoStreamProcessor:
    def __init__(self, device_type: str = 'high_res'):
        self._streams = {}
        self._lock = threading.Lock()
        self.device_type = device_type
        self.logger = logger

        # 初始化多流处理
        self.streams = {}
        self.stream_lock = threading.Lock()
        
        # 初始化全局跟踪器
        global global_person_tracker
        if global_person_tracker is None:
            with global_tracker_lock:
                if global_person_tracker is None:
                    global_person_tracker = PersonTracker(device_type=self.device_type, use_gpu=True, thread_id='global')
                    logger.info("初始化全局 GPU 跟踪器")
        
   

    def start_stream(self, machine_id: str, video_url: str,  resolution: Optional[Tuple[int, int]] = (1920, 1080), codec_type: Optional[str] = 'h264') -> bool:
        """
        启动视频流处理线程
        
        Args:
            machine_id (str): 设备唯一标识符
            video_url (str): 视频流的URL地址
            resolution (tuple, optional): 视频分辨率，格式为(宽,高)。默认为(1920,1080)
            codec_type (str, optional): 视频编码格式。默认为'h264'
            
        Returns:
            bool: 启动成功返回True，失败返回False
        """    
        try:
            with self._lock:
                if machine_id in self._streams:
                    return False

                # 根据分辨率动态选择配置
                if resolution:
                    width, height = resolution
                    if width >= 2560 or height >= 1440:
                        self.device_type = 'ultra_high_res'
                    elif width >= 1920 or height >= 1080:
                        self.device_type = 'high_res'
                    elif width >= 1280 or height >= 720:
                        self.device_type = 'medium_res'
                    else:
                        self.device_type = 'low_res'
                    
                    # 应用配置
                    self.config = DEVICE_CONFIG[self.device_type]
                    self.frame_queue_size = self.config['frame_queue_size']
                    self.drop_strategy = self.config['drop_strategy']
                    self.max_fps = self.config['max_fps']   
                    print("--------------------------------")
                    print(self.device_type)
                    print(self.config)
                    print("--------------------------------")
                    logger.info(f"为设备 {machine_id} 选择配置: {self.device_type}, 分辨率: {resolution}")                    
                
                # 创建停止事件
                stop_event = threading.Event()
                
                # 创建并启动新线程
                main_thread = threading.Thread(
                    target=self.process_stream,
                    args=(machine_id, video_url, stop_event, codec_type),
                    daemon=True
                )
                
                self._streams[machine_id] = {
                    "active": True,
                    "main_thread": main_thread,
                    "stop_event": stop_event,  # 在这里保存stop_event
                    "url": video_url,
                    "codec": codec_type,
                    "resolution": resolution,
                    "device_type": self.device_type,
                    "start_time": time.time()
                }               
                main_thread.start()
                return True 

        except Exception as e:
            logger.error(f"启动设备 {machine_id} 失败: {str(e)}")
            return False

    def stop_stream(self, machine_id: str) -> Dict:
        """停止视频流处理"""
        result = {
            "status": False,
            "message": ""
        }
        try:
            with self._lock:
                if machine_id not in self._streams:
                    result["message"] = "设备未启动"
                    return result   

                # 首先设置stop_event来通知所有子线程停止
                if "stop_event" in self._streams[machine_id]:
                    self._streams[machine_id]["stop_event"].set()
                
                print("--------------------------------")
                print(self._streams[machine_id])
                print("--------------------------------")
                
                # 等待线程结束
                try:
                    # 先等待解码线程结束
                    if "decode_thread" in self._streams[machine_id]:
                        self._streams[machine_id]["decode_thread"].join(timeout=1.0)
                    
                    # 再等待处理线程结束
                    if "process_thread" in self._streams[machine_id]:
                        self._streams[machine_id]["process_thread"].join(timeout=2.0)
                    
                    # 最后等待主线程结束
                    if "main_thread" in self._streams[machine_id]:
                        self._streams[machine_id]["main_thread"].join(timeout=1.0)

                    # 检查线程是否真的结束
                    if (("decode_thread" in self._streams[machine_id] and 
                         self._streams[machine_id]["decode_thread"].is_alive()) or
                        ("process_thread" in self._streams[machine_id] and 
                         self._streams[machine_id]["process_thread"].is_alive()) or
                        ("main_thread" in self._streams[machine_id] and 
                         self._streams[machine_id]["main_thread"].is_alive())):
                        result["message"] = "线程无法正常停止"
                        return result

                    # 设置停止标志
                    self._streams[machine_id]["active"] = False
                    
                    # 更新设备状态
                    DeviceStatusManager.update_device_status(machine_id, 'inactive')
                    
                    # 清理资源
                    if "frame_queue" in self._streams[machine_id]:
                        self._streams[machine_id]["frame_queue"].queue.clear()
                    
                    # 删除流信息
                    del self._streams[machine_id]
                    
                    result["status"] = True
                    result["message"] = "设备停止成功"
                    return result
                    
                except TimeoutError:
                    result["message"] = "等待线程结束超时"
                    return result

        except Exception as e:
            logger.error(f"停止设备 {machine_id} 失败: {str(e)}")
            result["message"] = str(e)
            return result    

    def list_running_streams(self):
        """列出当前运行的视频流"""
        return [machine_id for machine_id, stream in self._streams.items() if stream["active"]]

    def list_running_threads(self):
        """获取所有正在运行的视频流信息"""
        active_streams = []
        with self._lock:
            for machine_id, stream_info in self._streams.items():
                if stream_info['main_thread'].is_alive():
                    url = stream_info.get('url', '未知')
                    active_streams.append({
                        'machine_id': machine_id,
                        'url': url,
                        'start_time': stream_info.get('start_time', '未知'),
                        'status': 'running'
                    })
        return active_streams

    def process_stream(self, machine_id: str, video_url: str, stop_event: threading.Event, codec_type: Optional[str] = 'h264'):   
        """处理视频流的主函数"""
        try:
            # 创建一个独立的人员跟踪器实例，为每个摄像头使用独立的模型
            person_tracker = PersonTracker(device_type=self.device_type, use_gpu=True, thread_id=machine_id)
            face_recognizer = FaceRecognizer(imgsz=self.config['yolo_imgsz'])
            # 创建帧队列
            frame_queue = queue.Queue(maxsize=self.frame_queue_size)
            # 启动解码线程
            decoder = threading.Thread(
                target=self.decode_thread,
                args=(video_url, frame_queue, stop_event, codec_type),
                daemon=True
            )
            processor = threading.Thread(
                target=self.process_thread,
                args=(machine_id, frame_queue, stop_event, person_tracker, face_recognizer),
                daemon=True
            )
            
            self._streams[machine_id].update({
                "decode_thread": decoder,
                "process_thread": processor,
                "frame_queue": frame_queue
            })
            
            decoder.start()
            processor.start()
            
            # 等待线程结束
            decoder.join()
            processor.join()

        except Exception as e:
            logger.error(f"视频流处理错误: {str(e)}")
        finally:
            stop_event.set()

    def decode_thread(self, video_url: str, frame_queue: queue.Queue, stop_event: threading.Event, codec_type: str = 'h264'):
        """
        视频解码线程
        Args:
            video_url: 视频流地址
            frame_queue: 帧队列
            stop_event: 停止事件
            codec_type: 编解码类型，默认'h264'
        """
        logger.info(f"开始解码视频流: {video_url}, 编码类型: {codec_type}")
        
        try:
            # 配置解码器
            if codec_type.lower() == 'h264':
                # 使用 FFMPEG 的 H264 解码器
                container = av.open(video_url, options={
                    'rtsp_transport': 'udp',  # 使用UDP传输RTSP
                    'fflags': 'nobuffer',     # 禁用缓冲
                    'flags': 'low_delay',     # 低延迟模式
                    'max_delay': '500000',    # 最大延迟500ms
                    'codec': 'h264'           # 指定解码器
                })
            elif codec_type.lower() == 'h265':
                # 使用 HEVC/H265 解码器
                container = av.open(video_url, options={
                    'rtsp_transport': 'udp',
                    'fflags': 'nobuffer',
                    'flags': 'low_delay',
                    'max_delay': '500000',
                    'codec': 'hevc'
                })
            else:
                # 默认配置
                container = av.open(video_url)
            # 获取视频流
            stream = container.streams.video[0]
            
            # 设置线程数和解码器参数
            stream.codec_context.thread_type = av.codec.context.ThreadType.FRAME
            stream.codec_context.thread_count = 4 # 使用4个线程解码
            
            # 帧率控制
            frame_count = 0
            last_time = time.time()
            fps_limit = self.max_fps
            
            for frame in container.decode(stream):
                if stop_event.is_set():
                    break
                    
                # 控制帧率
                current_time = time.time()
                time_diff = current_time - last_time
                target_interval = 1.0/self.max_fps  # 目标帧间隔时间

                if time_diff < target_interval:
                    # 计算需要等待的时间
                    sleep_time = target_interval - time_diff
                    time.sleep(sleep_time)  # 精确等待
                    continue

                # 更新时间和计数
                frame_count += 1
                last_time = time.time()  # 使用新的时间戳

                # 每100帧输出一次实际帧率
                if frame_count % 100 == 0:
                    actual_fps = 1.0 / time_diff    

                # 转换为OpenCV格式
                img = frame.to_ndarray(format='bgr24')
                
                # 检查队列大小，执行丢帧策略
                if frame_queue.qsize() >= self.frame_queue_size:
                    if self.drop_strategy == 'oldest':
                        try:
                            frame_queue.get_nowait()  # 丢弃最老的帧
                        except queue.Empty:
                            pass
                    elif self.drop_strategy == 'newest':
                        continue  # 丢弃当前帧
                
                try:
                    frame_data = {
                        'frame': img,
                        'timestamp': current_time,
                        'frame_count': frame_count
                    }
                    frame_queue.put(frame_data, timeout=0.1)
                except queue.Full:
                    continue
                
        except av.error.OSError as e:
            logger.error(f"视频流打开失败: {str(e)}")
        except av.error.InvalidDataError as e:
            logger.error(f"无效的视频数据: {str(e)}")
        except Exception as e:
            logger.error(f"视频解码错误: {str(e)}")
        finally:
            try:
                container.close()
            except:
                pass
            logger.info("视频解码线程结束")

    def process_thread(self, machine_id: str, frame_queue: queue.Queue, stop_event: threading.Event, person_tracker: Optional[PersonTracker] = None, face_recognizer: Optional[FaceRecognizer] = None):
        """处理视频帧线程"""
        rtmp_streamer = RTMPStreamer()
        
        # 使用全局跟踪器
        global global_person_tracker
        
        try:
            # 跟踪状态记录
            track_records = {}
            face_to_tracks = {}
            
            # 初始化RTMP推流
            rtmp_initialized = False
            
            while not stop_event.is_set():
                try:
                    # 从队列获取帧数据,超时1秒
                    frame_data = frame_queue.get(timeout=1.0)
                    if frame_data is None:
                        self.logger.warning("收到空帧，跳过处理")
                        continue

                   # 处理字典形式的帧数据
                    if isinstance(frame_data, dict):
                        # 尝试从字典中获取帧
                        frame = frame_data.get('frame')
                        if frame is None:
                            logger.warning(f"帧字典中没有 'frame' 键: {frame_data.keys()}")
                            continue
                    else:
                        # 直接使用帧数据
                        frame = frame_data

                    current_time = datetime.now()
                    
                    # 处理帧
                    if person_tracker:
                        tracking_results = person_tracker.track(frame)
                    # else:
                    #     # 使用全局跟踪器
                    #     with global_tracker_lock:
                    #         tracking_results = global_person_tracker.update(frame)
                    
                    # 初始化RTMP推流(如果还未初始化)
                    if not rtmp_initialized:
                        height, width = frame.shape[:2]
                        rtmp_url = f'rtmp://192.168.109.191:1935/live/{machine_id}'
                        print(f"推流地址: {rtmp_url}")
                        if rtmp_streamer.start_stream(
                            output_url=rtmp_url,
                            width=width,
                            height=height,
                            fps=self.max_fps 
                        ):
                            rtmp_initialized = True
                        else:
                            logger.error("启动RTMP推流失败")
                            return
                    
                    # 创建可视化帧的副本
                    vis_frame = frame.copy()
                    
                    # 更新跟踪器获取当前帧的所有跟踪目标
                    current_track_ids = set()
                    
                    # 处理每个跟踪到的人
                    for track in tracking_results:
                        # 确保 track 是字典类型
                        if not isinstance(track, dict):
                            logger.warning(f"跟踪结果格式不正确: {track}")
                            continue
                        
                        # 安全地获取 track_id 和 bbox
                        track_id = track.get('track_id')
                        bbox = track.get('bbox')                       
                        # 确保 track_id 和 bbox 都存在               
                        if track_id is None or bbox is None:
                            logger.warning(f"跟踪结果缺少必要字段: {track}")
                            continue
                        
                        # 确保 track_id 是整数类型
                        if not isinstance(track_id, int):
                            try:
                                track_id = int(track_id)
                            except (ValueError, TypeError):
                                logger.warning(f"无法将 track_id 转换为整数: {track_id}")
                                continue
                        
                        # 确保 bbox 是包含 4 个元素的列表或元组
                        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                            logger.warning(f"bbox 格式不正确: {bbox}")
                            continue
                        # 解包边界框坐标
                        x1, y1, x2, y2 = bbox
                        
                        # 确保坐标是整数
                        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                        # 确保坐标在图像范围内
                        x1 = max(0, x1)
                        y1 = max(0, y1)
                        x2 = min(frame.shape[1], x2)
                        y2 = min(frame.shape[0], y2)    
                        
                        # 确保边界框有效（宽度和高度大于0）
                        if x2 <= x1 or y2 <= y1:
                            logger.warning(f"无效的边界框: {bbox}")
                            continue
                        # 添加到当前帧的跟踪ID集合
                        current_track_ids.add(track_id)

                        # 处理新出现的跟踪目标
                        if track_id not in track_records:
                            track_records[track_id] = {
                                'face_id': None,
                                'first_seen': current_time,
                                'last_seen': current_time,
                                'confidence': 0.0,
                                'missing_count': 0
                            }
                        else:
                            # 更新已有记录的最后见到时间
                            track_records[track_id]['last_seen'] = current_time
                            track_records[track_id]['missing_count'] = 0
                        
                        # 对未识别的目标进行人脸识别
                        if not track_records[track_id]['face_id'] and face_recognizer:
                            try:
                            # 裁剪人物区域
                                person_roi = frame[y1:y2, x1:x2]
                                
                                # 确保ROI有效
                                if person_roi is not None and person_roi.size > 0 and person_roi.shape[0] > 0 and person_roi.shape[1] > 0:
                                    # 编码为base64
                                    _, buffer = cv2.imencode('.jpg', person_roi)
                                    person_roi_base64 = base64.b64encode(buffer).decode('utf-8')
                                    
                                    # 识别人脸
                                    face_result = face_recognizer.recognize([person_roi_base64])
                                    
                                    # 如果识别成功且有匹配
                                    if face_result.get("success", False) and face_result.get("matches") and len(face_result["matches"]) > 0:
                                        match = face_result["matches"][0]
                                        face_id = match["face_id"]
                                        confidence = match["confidence"]
                                        
                                        # 检查是否已有活跃的跟踪(missing_count<30)
                                        if face_id in face_to_tracks:
                                            active_tracks = {t for t in face_to_tracks[face_id] 
                                                            if t in track_records and 
                                                            track_records[t]['missing_count'] < 30}
                                            if active_tracks:
                                                continue
                                        
                                        # 更新跟踪记录
                                        track_records[track_id].update({
                                            'face_id': face_id,
                                            'confidence': confidence
                                        })
                                        
                                        # 更新face_id到track_id的映射
                                        if face_id not in face_to_tracks:
                                            face_to_tracks[face_id] = set()
                                        face_to_tracks[face_id].add(track_id)
                                        
                                        # 记录识别事件到数据库
                                        recognition_event_manager.record_recognition(
                                            machine_id=int(machine_id),
                                            track_id=track_id,
                                            face_id=face_id,
                                            confidence=confidence,
                                            recognition_time=track_records[track_id]['first_seen'].isoformat(),
                                            detection_img=person_roi_base64
                                        )
                                        
                                        logger.info(f"识别成功: Track {track_id} -> Face {face_id}")
                            except Exception as e:
                                logger.error(f"处理ROI失败: {str(e)}")
                        
                        # 在可视化帧上绘制跟踪框和标签
                        color = (0, 255, 0) if track_records[track_id]['face_id'] else (0, 255, 255)
                        label = f"ID:{track_records[track_id]['face_id']}" if track_records[track_id]['face_id'] else f"Track:{track_id}"
                        
                        # 如果有置信度,添加到标签中
                        if track_records[track_id]['confidence'] > 0:
                            label += f" ({track_records[track_id]['confidence']:.2f})"
                        
                        cv2.rectangle(vis_frame, (x1, y1), (x2, y2), color, 2)
                        cv2.putText(vis_frame, label, (x1, y1 - 10),
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                    
                    # 处理消失的目标
                    for track_id in list(track_records.keys()):
                        if track_id not in current_track_ids:
                            record = track_records[track_id]
                            record['missing_count'] += 1
                            
                            # 如果目标消失超过30帧且有face_id,记录离开事件
                            if record['missing_count'] >= 30 and record['face_id']:
                                try:
                                    # 记录离开事件到数据库
                                    recognition_event_manager.record_departure(
                                        machine_id=int(machine_id),
                                        track_id=track_id,
                                        face_id=record['face_id'],
                                        departure_time=record['last_seen'].isoformat()
                                    )
                                    
                                    # 清理face_id到track_id的映射
                                    if record['face_id'] in face_to_tracks:
                                        face_to_tracks[record['face_id']].discard(track_id)
                                        if not face_to_tracks[record['face_id']]:
                                            del face_to_tracks[record['face_id']]
                                    
                                    del track_records[track_id]
                                    logger.info(f"目标离开: Track {track_id}")
                                    
                                except Exception as e:
                                    logger.error(f"记录离开事件失败: {str(e)}")
                    
                    # 在可视化帧上显示状态信息
                    status_text = f"Tracks: {len(current_track_ids)} | Identified: {sum(1 for r in track_records.values() if r['face_id'])}"
                    cv2.putText(vis_frame, status_text, (10, 30),
                              cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                                    
                    # 推送可视化帧到RTMP流
                    if rtmp_initialized:
                        rtmp_streamer.push_frame(vis_frame)
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"处理帧失败: {str(e)}")
                    continue
                
        except Exception as e:
            logger.error(f"处理线程异常: {str(e)}")
        finally:
            # 清理资源
            # cv2.destroyWindow(window_name)
            if rtmp_initialized:
                rtmp_streamer.stop()
            logger.info(f"设备 {machine_id} 处理线程结束")


