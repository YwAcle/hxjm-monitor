import multiprocessing as mp
import threading
import time
import logging
import cv2
import numpy as np
import os
import sys
from queue import Empty, Queue
import signal
import atexit
import base64
from config.device_config import DEVICE_CONFIG
from config.config import settings
from db.recognition_events import recognition_event_manager

try:
    import torch
except ImportError:
    torch = None
    print("警告: 未能导入torch，某些功能可能无法使用。")

from datetime import datetime

# 配置日志
logger = logging.getLogger(__name__)
handler = logging.FileHandler('logs/person_records.log', encoding='utf-8')
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# 确保使用 spawn 启动方式，以兼容 CUDA
try:
    if mp.get_start_method(allow_none=True) != 'spawn':
        mp.set_start_method('spawn', force=True)
        logger.info("multiprocessing 启动方式已设置为 'spawn' 以兼容 CUDA")
except RuntimeError:
    # 启动方法可能已在其他模块中设置，忽略即可
    pass

# 添加项目根目录到Python路径以便正确导入模块
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, "../.."))
if root_dir not in sys.path:
    sys.path.append(root_dir)

# 导入相关模块
from algorithms.reid.person_detect_yolo8 import PersonDetectYOLO8
from models.model_manager import model_manager
from models.deep_sort import build_tracker
from utils.ffmpeg import RTMPStreamer

try:
    import av
    from core.video_reader import VideoReader
except ImportError:
    try:
        import av
        from core.video_reader import VideoReader

        logger.info(f"从{root_dir}导入VideoReader模块")
    except ImportError:
        logger.error("无法导入VideoReader模块和PyAV库，请确保已安装依赖")

# 创建进程字典和锁
person_processes = {}
person_lock = threading.RLock()


# 辅助函数 - 创建视频读取器
def create_video_reader(video_url, machine_id="unknown", codec_type='h264', **kwargs):
    """
    创建并启动视频读取线程

    Args:
        video_url: 视频URL
        machine_id: 设备ID，用于日志
        codec_type: 编解码器类型
        **kwargs: 其他参数

    Returns:
        VideoReader: 视频读取线程实例
        Queue: 帧队列
        threading.Event: 停止事件
        threading.Event: 就绪事件
    """
    # 创建线程间通信对象
    # 为降低整体延迟，控制读取队列长度（实时优先）
    frame_queue = Queue(maxsize=kwargs.get('queue_size', 10))
    stop_event = threading.Event()
    ready_event = threading.Event()

    # 创建视频读取线程
    reader = VideoReader(
        video_url=video_url,
        frame_queue=frame_queue,
        stop_event=stop_event,
        ready_event=ready_event,
        codec_type=codec_type
    )

    # 启动线程
    reader.start()
    logger.info(f"已启动视频读取线程: {machine_id}")

    # 返回视频读取器和通信对象
    return reader, frame_queue, stop_event, ready_event


# 在程序退出时清理所有进程的函数
def cleanup_all_processes():
    """在程序退出时清理所有子进程"""
    global person_processes
    logger.info("程序退出，正在清理所有人脸识别子进程...")

    with person_lock:
        process_ids = list(person_processes.keys())

    for machine_id in process_ids:
        try:
            stop_person_process(machine_id)
        except Exception as e:
            logger.error(f"清理进程 {machine_id} 时出错: {e}")

    logger.info("所有人脸识别子进程已清理完毕")


# 注册退出处理函数
atexit.register(cleanup_all_processes)


# 注册信号处理函数
def signal_handler(sig, frame):
    """处理终止信号"""
    logger.info(f"收到信号 {sig}，正在清理进程...")
    cleanup_all_processes()
    sys.exit(0)


# 注册SIGINT和SIGTERM信号处理
try:
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    # Windows特有信号
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, signal_handler)
except (ValueError, AttributeError) as e:
    # 某些环境下可能无法注册信号
    logger.warning(f"无法注册信号处理函数: {e}")


class PersonRecordsTask(mp.Process):
    def __init__(self, machine_id: str, video_url: str, queue_size=30, device_type: str = 'high_res',
                 codec_type: str = 'h264', is_global: bool = True):
        """
        初始化人员识别统计进程
        Args:
            machine_id: 设备ID
            video_url: 视频流地址
            queue_size: 帧队列大小
            device_type: 设备类型
            codec_type: 视频编码类型
        """
        super().__init__()
        # 基本参数
        self.is_global = is_global
        self.machine_id = machine_id
        self.video_url = video_url
        self.queue_size = queue_size
        self.device_type = device_type
        self.codec_type = codec_type
        self.daemon = True
        self.stop_event = mp.Event()
        self.ready_event = mp.Event()
        self.name = f"PersonRecordsTask-{machine_id}"
        self.is_running = False
        self.error = None
        # 从配置中读取设置
        self.config = DEVICE_CONFIG.get(device_type, DEVICE_CONFIG['high_res'])
        # 跟踪状态记录
        self.track_records = {}  # 存储每个人脸ID的记录信息

        self.face_to_tracks = {}  # 存储人脸ID到轨迹ID的映射
        self.frame_count = 0
        self.processed_frames = 0
        self.last_log_time = time.time()
        self.start_time = time.time()
        self.similarity_threshold = 0.4  # 人脸匹配阈值
        self.leave_threshold_frames = 30  # 人脸离开阈值帧数
        self.auto_record_strangers = False  # 是否自动记录陌生人
        self.max_strangers_per_day = 100  # 每天最大陌生人记录数

        # 这些对象将在run方法中初始化
        self.person_detector = None
        self.deepsort = None
        self.face_recognizer = None  # 人脸识别器
        self.video_reader = None  # 视频读取器
        self.frame_queue = None  # 帧队列
        self.reader_stop_event = None  # 读取器停止事件
        self.reader_ready_event = None  # 读取器就绪事件
        self.rtmp_streamer = None  # RTMP推流器

        # RTMP推流相关
        self.rtmp_url = f"{settings.RTMP_SERVER}{self.machine_id}"  # RTMP推流地址
        self.rtmp_enabled = True

        logger.info(f"已创建设备 {machine_id} 的人脸识别统计任务")

    def run(self):
        """进程主循环，负责视频读取、识别、统计等"""
        try:
            logger.info(f"设备 {self.machine_id} 的人脸识别统计任务开始运行")
            if self.is_global:
                # 1. 初始化所要使用的模型
                try:
                    # 加载行人检测模型
                    self.person_detector = PersonDetectYOLO8(
                        model_manager=model_manager
                    )
                    # 获取DeepSORT跟踪器，处理返回的元组
                    deepsort_result = model_manager.get_model("deepsort")
                    if isinstance(deepsort_result, tuple) and len(deepsort_result) == 2:
                        self.deepsort = deepsort_result[0]
                        deepsort_model_id = deepsort_result[1]
                        logger.info(f"成功获取DeepSORT模型: {deepsort_model_id}")
                    else:
                        self.deepsort = deepsort_result
                    # 获取人脸识别器
                    from algorithms.person_recognition.face_recognition import FaceRecognizer
                    self.face_recognizer = FaceRecognizer(imgsz=self.config['yolo_imgsz'])

                    logger.info(f"设备 {self.machine_id} 已成功加载人脸识别和跟踪模型")
                except Exception as e:
                    logger.error(f"从全局模型管理器获取模型失败: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    self.error = str(e)
                    return
            else:
                # 本地创建模型
                try:
                    self.person_detector = PersonDetectYOLO8()
                    self.deepsort = build_tracker()
                    logger.info(f"设备 {self.machine_id} 已创建本地模型实例")
                except Exception as e:
                    logger.error(f"创建本地模型实例失败: {e}")
                    self.error = str(e)
                    return
                    # 2. 初始化视频读取器
            try:
                logger.info(f"正在创建视频读取器线程: {self.video_url}")
                self.video_reader, self.frame_queue, self.reader_stop_event, self.reader_ready_event = create_video_reader(
                    video_url=self.video_url,
                    machine_id=self.machine_id,
                    codec_type=self.codec_type,
                    queue_size=self.queue_size
                )

                # 等待视频读取器就绪
                ready_timeout = 60  # 最多等待60秒
                ready = self.reader_ready_event.wait(timeout=ready_timeout)

                if not ready:
                    logger.error(f"视频读取器初始化失败或超时")
                    self.error = "视频读取器初始化失败或超时"
                    return

                logger.info(f"视频读取器已就绪: {self.machine_id}")
            except Exception as e:
                logger.error(f"创建视频读取器失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
                self.error = f"创建视频读取器失败: {e}"
                return

            # 3. 初始化RTMP推流器
            try:
                from utils.ffmpeg import RTMPStreamer

                logger.info(f"初始化RTMP推流器，URL: {self.rtmp_url}")

                # 获取视频的第一帧，用于初始化推流器
                try:
                    first_frame = self.frame_queue.get(timeout=5.0)
                    height, width = first_frame.shape[:2]

                    # 将第一帧放回队列
                    self.frame_queue.put(first_frame)

                    # 创建并启动RTMP推流器
                    self.rtmp_streamer = RTMPStreamer()
                    if self.rtmp_streamer.start_stream(
                            output_url=self.rtmp_url,
                            width=width,
                            height=height,
                            fps=self.config['max_fps']
                    ):
                        logger.info(f"RTMP推流器初始化成功: {self.rtmp_url}")
                    else:
                        logger.error("RTMP推流器初始化失败")
                        self.rtmp_enabled = False
                        self.rtmp_streamer = None
                except Exception as e:
                    logger.error(f"获取第一帧或初始化RTMP推流器失败: {e}")
                    self.rtmp_enabled = False
                    self.rtmp_streamer = None
            except Exception as e:
                logger.error(f"导入RTMPStreamer或初始化推流器失败: {e}")
                self.rtmp_enabled = False
                self.rtmp_streamer = None

            # 4. 设置初始化完成标志
            self.is_running = True
            self.ready_event.set()

            # 5. 初始化统计变量
            frame_count = 0
            start_time = time.time()
            last_log_time = time.time()
            # 处理间隔（每隔几帧处理一次）
            self.process_interval = 1  # 增大处理间隔以提高FPS

            # 7. 主循环 - 处理视频帧
            while not self.stop_event.is_set():
                try:
                    # 为降低延迟，总是取队列中最新的一帧，丢弃旧帧
                    frame_data = self.frame_queue.get(timeout=1.0)
                    # 把队列中剩余帧全部取出，只保留最后一帧
                    while True:
                        try:
                            frame_data = self.frame_queue.get_nowait()
                        except Empty:
                            break

                    if isinstance(frame_data, dict):
                        frame = frame_data.get('frame')
                    else:
                        frame = frame_data
                except Empty:
                    # 如果队列为空，检查视频读取器状态
                    if not self.video_reader.is_alive() or self.reader_stop_event.is_set():
                        logger.error(f"视频读取器线程已停止")
                        break
                    time.sleep(0.1)
                    continue

                # 增加帧计数
                frame_count += 1

                try:
                    # 处理当前帧 - 人脸检测、识别、统计
                    processed_frame = self.process_frame(frame, frame_count)

                    # 推流处理后的帧
                    if self.rtmp_enabled and self.rtmp_streamer:
                        self.rtmp_streamer.push_frame(processed_frame)

                    # 定期输出日志
                    current_time = time.time()
                    if current_time - last_log_time >= 10:  # 每10秒输出一次
                        elapsed = current_time - start_time
                        fps = frame_count / elapsed if elapsed > 0 else 0
                        logger.info(f"设备 {self.machine_id} 处理帧数: {frame_count}, FPS: {fps:.1f}")
                        last_log_time = current_time

                except Exception as e:
                    logger.error(f"设备 {self.machine_id} 处理帧出错: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

            logger.info(f"设备 {self.machine_id} 人脸识别统计任务停止")

        except Exception as e:
            logger.error(f"设备 {self.machine_id} 的人脸识别统计任务运行出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.error = str(e)
            if self.is_running:
                self.is_running = False
        finally:
            # 确保资源被释放
            self.cleanup()

    def process_frame(self, frame, frame_count):
        """
        处理单帧图像，执行人脸检测、识别和统计

        Args:
            frame: 输入帧
            frame_count: 帧计数

        Returns:
            处理后的帧
        """
        # 创建可视化帧的副本
        vis_frame = frame.copy()

        # 记录当前帧检测到的ID
        current_track_ids = set()
        try:
            with torch.no_grad():
                # 1. 行人检测
                if frame_count % self.process_interval == 0:
                    bbox_xywh, confidences, cls_ids, xyxy_list = self.person_detector.detect_with_optimize(frame,
                                                                                                           verbose=False)
                    if len(bbox_xywh) > 0:
                        outputs, features = self.deepsort.update(bbox_xywh, confidences, frame)
                        if len(outputs) > 0:
                            # 处理每个跟踪到的人
                            for i, track in enumerate(outputs):
                                bbox = track[:4]
                                track_id = track[4]  # ID
                                x1, y1, x2, y2 = map(int, bbox)
                                # 确保边界框在图像范围内
                                x1 = max(0, x1)
                                y1 = max(0, y1)
                                x2 = min(frame.shape[1], x2)
                                y2 = min(frame.shape[0], y2)
                                current_track_ids.add(track_id)
                                # 生成临时跟踪ID字符串
                                database_track_id = f"track_{track_id}_{frame_count}"

                                # 处理新出现的跟踪目标或更新现有目标
                                if track_id not in self.track_records:
                                    self.track_records[track_id] = {
                                        'face_id': None,
                                        'first_seen': datetime.now(),
                                        'last_seen': datetime.now(),
                                        'confidence': 0.0,
                                        'missing_count': 0,
                                        'bbox': (x1, y1, x2, y2),
                                        'is_unknown': False,
                                        'database_track_id': database_track_id
                                    }
                                else:
                                    # 更新已有记录的最后见到时间和位置
                                    self.track_records[track_id]['last_seen'] = datetime.now()
                                    self.track_records[track_id]['missing_count'] = 0
                                    self.track_records[track_id]['bbox'] = (x1, y1, x2, y2)

                                # 裁剪人物区域进行人脸识别
                                person_roi = frame[y1:y2, x1:x2]
                                # 对未识别的目标进行人脸识别
                                if not self.track_records[track_id]['face_id'] and person_roi.size > 0:
                                    try:
                                        # 编码为base64用于识别
                                        success, buffer = cv2.imencode('.jpg', person_roi)
                                        if success:
                                            person_roi_base64 = base64.b64encode(buffer).decode('utf-8')

                                            # 使用人脸识别器进行识别 - 不使用with语句，直接调用
                                            face_result = self.face_recognizer.recognize([person_roi_base64])

                                            # 如果识别成功且有匹配
                                            if (face_result.get("success", False) and
                                                    face_result.get("matches") and
                                                    len(face_result["matches"]) > 0):

                                                match = face_result["matches"][0]
                                                face_id = match.get("face_id")
                                                confidence = match.get("confidence", 0.0)

                                                if face_id and confidence > self.similarity_threshold:
                                                    # 更新跟踪记录
                                                    self.track_records[track_id].update({
                                                        'face_id': face_id,
                                                        'confidence': confidence
                                                    })

                                                    # 记录识别事件
                                                    logger.info(
                                                        f"识别成功: Track {track_id} -> Face {face_id}, 置信度={confidence:.2f}")

                                                    # 记录识别事件到数据库
                                                    event_id = recognition_event_manager.record_recognition(
                                                        machine_id=int(self.machine_id),
                                                        track_id=database_track_id,
                                                        face_id=face_id,
                                                        confidence=confidence,
                                                        recognition_time=self.track_records[track_id][
                                                            'first_seen'].isoformat(),
                                                        detection_img=person_roi_base64
                                                    )

                                                    # 更新事件ID和映射
                                                    self.track_records[track_id]['event_id'] = event_id
                                                    if face_id not in self.face_to_tracks:
                                                        self.face_to_tracks[face_id] = set()
                                                    self.face_to_tracks[face_id].add(track_id)

                                                    # 添加到当前人脸ID集合
                                                    current_track_ids.add(track_id)
                                            else:
                                                # 未识别出身份，标记为未知人
                                                self.track_records[track_id]['is_unknown'] = True
                                    except Exception as e:
                                        logger.warning(f"人脸识别过程中出错: {e}")

                                # 有识别结果的情况下，添加到当前人脸ID集合
                                if self.track_records[track_id]['face_id']:
                                    current_track_ids.add(track_id)

                                # 绘制跟踪框和标签
                                color = (0, 255, 0) if self.track_records[track_id]['face_id'] else (0, 255, 255)
                                label = f"ID:{self.track_records[track_id]['face_id']}" if self.track_records[track_id][
                                    'face_id'] else f"Track:{track_id}"

                                # 如果有置信度，添加到标签中
                                if self.track_records[track_id]['confidence'] > 0:
                                    label += f" ({self.track_records[track_id]['confidence']:.2f})"

                                cv2.rectangle(vis_frame, (x1, y1), (x2, y2), color, 2)
                                cv2.putText(vis_frame, label, (x1, y1 - 10),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

                    for tid in list(self.track_records.keys()):
                        if tid not in current_track_ids:
                            # 增加消失计数
                            self.track_records[tid]['missing_count'] += 1
                            # 如果消失帧数超过阈值，标记为待移除
                            if self.track_records[tid]['missing_count'] > self.leave_threshold_frames:
                                try:
                                    # 如果有人脸ID，记录离开事件
                                    if self.track_records[tid]['face_id']:
                                        face_id = self.track_records[tid]['face_id']
                                        # 记录离开事件到数据库
                                        recognition_event_manager.record_departure(
                                            machine_id=int(self.machine_id),
                                            track_id=self.track_records[tid]['database_track_id'],
                                            face_id=face_id,
                                            departure_time=self.track_records[tid]['last_seen'].isoformat()
                                        )

                                    logger.info(f"目标 {tid} 离开视野")
                                    del self.track_records[tid]
                                except Exception as e:
                                    logger.error(f"记录离开事件失败: {e}")

                # 添加状态信息到图像
                frame_status = f"跟踪目标: {len(self.track_records)} | 帧: {frame_count}"
                cv2.putText(vis_frame, frame_status, (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            return vis_frame

        except Exception as e:
            logger.error(f"处理帧时出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return frame  # 发生错误时返回原始帧

    def stop(self):
        """停止人脸识别统计任务"""
        logger.info(f"正在停止设备 {self.machine_id} 的人脸识别统计任务")
        self.stop_event.set()

        # 先停止视频读取器
        if hasattr(self, 'reader_stop_event') and self.reader_stop_event:
            try:
                logger.info(f"正在停止视频读取器: {self.machine_id}")
                self.reader_stop_event.set()
            except Exception as e:
                logger.error(f"停止视频读取器出错: {e}")

        # 等待进程自然结束
        if self.is_alive():
            logger.info(f"等待进程 {self.machine_id} 正常结束...")
            self.join(timeout=5)

            # 如果进程仍然存活，发送更强的终止信号
            if self.is_alive():
                logger.warning(f"进程 {self.machine_id} 未响应正常停止信号，将强制终止")
                self.terminate()
                self.join(timeout=2)

    def cleanup(self):
        """清理资源"""
        try:
            # 停止视频读取器线程
            if hasattr(self, 'reader_stop_event') and self.reader_stop_event is not None:
                logger.info(f"正在停止视频读取器: {self.machine_id}")
                try:
                    self.reader_stop_event.set()
                    logger.info(f"视频读取器停止信号已发送: {self.machine_id}")
                except Exception as e:
                    logger.error(f"停止视频读取器时出错: {e}")

            # 清空队列
            if hasattr(self, 'frame_queue') and self.frame_queue is not None:
                while True:
                    try:
                        self.frame_queue.get_nowait()
                    except Empty:
                        break

            # 停止RTMP推流器
            if hasattr(self, 'rtmp_streamer') and self.rtmp_streamer is not None:
                try:
                    logger.info(f"正在停止RTMP推流器: {self.machine_id}")
                    self.rtmp_streamer.stop()
                    logger.info(f"RTMP推流器已停止: {self.machine_id}")
                except Exception as e:
                    logger.error(f"停止RTMP推流器时出错: {e}")
                self.rtmp_streamer = None

            # 关闭所有OpenCV窗口
            cv2.destroyAllWindows()

            # 标记为未运行
            self.is_running = False
            logger.info(f"设备 {self.machine_id} 的人脸识别统计任务已清理资源")
        except Exception as e:
            logger.error(f"清理资源时出错: {e}")

    def calculate_similarity(self, feature1, feature2):
        """
        计算两个特征向量之间的余弦相似度

        Args:
            feature1: 第一个特征向量
            feature2: 第二个特征向量

        Returns:
            float: 相似度得分 (0-1)
        """
        try:
            if feature1 is None or feature2 is None:
                return 0.0

            # 确保特征是平坦的一维数组
            if hasattr(feature1, 'ndim') and feature1.ndim > 1:
                feature1 = feature1.flatten()
            if hasattr(feature2, 'ndim') and feature2.ndim > 1:
                feature2 = feature2.flatten()

            # 计算余弦相似度
            from sklearn.metrics.pairwise import cosine_similarity
            similarity = cosine_similarity(
                feature1.reshape(1, -1),
                feature2.reshape(1, -1)
            )[0][0]

            return float(similarity)
        except Exception as e:
            logger.error(f"计算特征相似度时出错: {e}")
            return 0.0

    def set_target_features(self, image_path=None, feature_dict=None):
        """
        设置目标特征，可以从图像路径或直接提供特征字典

        Args:
            image_path: 目标图像路径，如果提供则从图像中提取特征
            feature_dict: 特征字典，直接提供目标ID到特征的映射

        Returns:
            bool: 是否成功设置目标特征
        """
        try:
            # 如果提供了特征字典，直接使用
            if feature_dict is not None and isinstance(feature_dict, dict):
                self.target_features = feature_dict
                logger.info(f"已设置 {len(feature_dict)} 个目标特征")
                return True

            # 如果提供了图像路径，尝试提取特征
            if image_path and os.path.exists(image_path):
                import cv2
                import numpy as np

                # 读取图像
                image = cv2.imread(image_path)
                if image is None:
                    logger.error(f"无法读取图像: {image_path}")
                    return False

                # 检测人物
                if self.person_detector is None:
                    logger.error("人物检测器未初始化")
                    return False

                bbox_xywh, confidences, _, xyxy_list = self.person_detector.detect_with_optimize(
                    image, verbose=True
                )

                if len(bbox_xywh) == 0:
                    logger.warning(f"图像中未检测到人物: {image_path}")
                    return False

                # 提取特征
                if self.deepsort is None:
                    logger.error("DeepSORT跟踪器未初始化")
                    return False

                # 使用DeepSORT提取特征
                _, features = self.deepsort.update(bbox_xywh, confidences, image)

                # 保存特征
                if features.size == 0:
                    logger.warning(f"未能从图像中提取特征: {image_path}")
                    return False

                # 将特征与ID关联
                self.target_features = {}
                for i, feat in enumerate(features):
                    target_id = f"target_{i}"
                    self.target_features[target_id] = feat

                logger.info(f"已从图像 {image_path} 中提取并设置 {len(self.target_features)} 个目标特征")
                return True

            return False
        except Exception as e:
            logger.error(f"设置目标特征时出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False


def start_person_process(machine_id, video_url, resolution=None, codec_type='h264', target_image_path=None):
    """
    启动人脸识别统计进程

    Args:
        machine_id: 设备ID
        video_url: 视频URL
        resolution: 分辨率，暂不使用但保留接口一致性
        codec_type: 编码类型
        target_image_path: 目标图像路径，用于特征匹配

    Returns:
        bool: 是否成功启动进程
    """
    global person_processes

    try:
        # 检查参数
        if not machine_id or not video_url:
            logger.error(f"无效的参数: machine_id={machine_id}, video_url={video_url}")
            return False

        # 检查进程是否已存在
        with person_lock:
            if machine_id in person_processes:
                logger.warning(f"设备 {machine_id} 的人脸识别统计任务已存在，先停止旧任务")
                stop_person_process(machine_id)

        # 创建人脸识别统计任务
        # 为降低整体延迟，减小进程内部帧队列
        queue_size = 10  # 可以从配置中读取
        process = PersonRecordsTask(
            machine_id=machine_id,
            video_url=video_url,
            queue_size=queue_size,
            codec_type=codec_type
        )

        # 启动进程
        process.start()

        # 记录进程
        with person_lock:
            person_processes[machine_id] = process

        logger.info(f"已启动设备 {machine_id} 的人脸识别统计任务，进程ID: {process.pid}")

        # 等待进程初始化完成
        if not process.ready_event.wait(timeout=60):
            logger.warning(f"等待设备 {machine_id} 的人脸识别统计任务初始化超时")

            # 检查进程是否仍在运行
            if not process.is_alive():
                error_msg = process.error if process.error else "未知错误"
                logger.error(f"设备 {machine_id} 的人脸识别统计任务启动失败: {error_msg}")

                # 清理进程记录
                with person_lock:
                    if machine_id in person_processes:
                        del person_processes[machine_id]

                return False

            logger.info(f"虽然初始化超时，但设备 {machine_id} 的人脸识别统计任务仍在运行")
        else:
            logger.info(f"设备 {machine_id} 的人脸识别统计任务初始化完成")

            # 如果提供了目标图像路径，设置目标特征
            if target_image_path:
                if process.set_target_features(image_path=target_image_path):
                    logger.info(f"已为设备 {machine_id} 设置目标特征，来源: {target_image_path}")
                else:
                    logger.warning(f"为设备 {machine_id} 设置目标特征失败，图像路径: {target_image_path}")

        return True

    except Exception as e:
        logger.error(f"启动设备 {machine_id} 的人脸识别统计任务失败: {e}")
        import traceback
        logger.error(traceback.format_exc())

        # 清理
        with person_lock:
            if machine_id in person_processes:
                process = person_processes[machine_id]
                try:
                    if process.is_alive():
                        process.terminate()
                except:
                    pass
                del person_processes[machine_id]

        return False


def stop_person_process(machine_id):
    """
    停止人脸识别统计进程

    Args:
        machine_id: 设备ID

    Returns:
        bool: 是否成功停止进程
    """
    global person_processes

    try:
        # 检查进程是否存在
        with person_lock:
            if machine_id not in person_processes:
                logger.warning(f"设备 {machine_id} 的人脸识别统计任务不存在")
                return False

            # 获取进程
            process = person_processes[machine_id]

        # 发送停止信号
        process.stop()

        # 从字典中移除
        with person_lock:
            if machine_id in person_processes:
                del person_processes[machine_id]

        logger.info(f"已停止设备 {machine_id} 的人脸识别统计任务")
        return True

    except Exception as e:
        logger.error(f"停止设备 {machine_id} 的人脸识别统计任务失败: {e}")
        import traceback
        logger.error(traceback.format_exc())

        # 尝试强制清除
        with person_lock:
            if machine_id in person_processes:
                try:
                    process = person_processes[machine_id]
                    if process.is_alive():
                        process.terminate()
                except:
                    pass
                del person_processes[machine_id]

        return False


def list_running_processes():
    """
    列出所有正在运行的人脸识别统计进程

    Returns:
        List: 正在运行的进程ID列表
    """
    with person_lock:
        return list(person_processes.keys())
