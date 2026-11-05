#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import threading
import multiprocessing as mp
import logging
import torch
import atexit
import signal
from queue import Queue, Empty
import argparse
import numpy as np
import cv2

# 添加补丁，在运行时修复 np.float 和 np.int 问题
if not hasattr(np, 'float'):
    np.float = np.float64  # 为 np 添加 float 属性，指向 np.float64
if not hasattr(np, 'int'):
    np.int = np.int32  # 为
# 配置日志
logger = logging.getLogger(__name__)

# 添加项目根目录到Python路径以便正确导入模块
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, "../.."))
if root_dir not in sys.path:
    sys.path.append(root_dir)

# 导入相关模块
from utils.ffmpeg import RTMPStreamer
from algorithms.reid.person_detect_yolo8 import PersonDetectYOLO8
from models.model_manager import model_manager
from models.deep_sort import build_tracker

# 导入基于PyAV的VideoReader
try:
    import av
    from core.video_reader import VideoReader
except ImportError:
    # 如果无法导入，尝试直接从本地import
    sys.path.insert(0, root_dir)
    try:
        import av
        from core.video_reader import VideoReader

        logger.info(f"从{root_dir}导入VideoReader模块")
    except ImportError:
        logger.error("无法导入VideoReader模块和PyAV库，请确保已安装依赖")

# 导入相似度计算
from sklearn.metrics.pairwise import cosine_similarity

# 创建进程字典和锁
reid_processes = {}
reid_lock = threading.RLock()


# 自定义create_video_reader函数，替代旧的函数
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
    frame_queue = Queue(maxsize=kwargs.get('queue_size', 30))
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
    global reid_processes
    logger.info("程序退出，正在清理所有Reid子进程...")

    with reid_lock:
        process_ids = list(reid_processes.keys())

    for machine_id in process_ids:
        try:
            stop_reid_process(machine_id)
        except Exception as e:
            logger.error(f"清理进程 {machine_id} 时出错: {e}")

    logger.info("所有Reid子进程已清理完毕")


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


# 行人重识别任务类，继承自multiprocessing.Process
class ReidTask(mp.Process):
    """
    行人重识别任务类，继承自multiprocessing.Process

    实现行人检测、跟踪和重识别功能
    """

    def __init__(self, machine_id: str, video_url: str,
                 resolution=None, codec_type='h264',
                 ptz_enabled=False, camera_params=None,
                 target_features=None, is_global=True,
                 queue_size=30, hardware_decode=False,
                 use_ffmpeg=True, conf_threshold=0.4,
                 rtmp_url=None):
        """
        初始化行人重识别任务

        Args:
            machine_id: 摄像头ID
            video_url: 视频URL
            resolution: 分辨率，格式为(width, height)
            codec_type: 编码类型
            ptz_enabled: 是否启用云台控制
            camera_params: 摄像头云台参数
            target_features: 目标行人特征，格式为:
                - 字典格式: {'features': [[特征1], [特征2], ...], 'names': ['名称1', '名称2', ...]}
            is_global: 是否使用全局模型
            queue_size: 帧队列大小
            hardware_decode: 是否使用硬件解码
            use_ffmpeg: 是否使用FFMPEG命令行
            conf_threshold: 置信度阈值，默认0.4
            rtmp_url: RTMP推流地址，如果为None则自动生成
        """
        super(ReidTask, self).__init__()

        # 设置进程为守护进程，确保主程序退出时自动清理
        self.daemon = True

        # 基本参数
        self.machine_id = machine_id
        self.video_url = video_url
        self.resolution = resolution
        self.codec_type = codec_type
        self.ptz_enabled = ptz_enabled
        self.camera_params = camera_params

        # 处理目标特征
        self.features_list = []  # 特征列表
        self.names_list = []  # 名称列表

        if target_features is not None:
            # 处理字典格式 {'features': [[特征1], [特征2], ...], 'names': ['名称1', '名称2', ...]}
            if isinstance(target_features, dict):
                if 'features' in target_features:
                    # 确保features_list是二维numpy数组格式，便于cosine_similarity直接计算
                    features = target_features.get('features', [])
                    if len(features) > 0:
                        # 处理特征数组维度，确保是二维数组 (n_samples, n_features)
                        # 如果是三维数组，将其转换为二维
                        features_array = np.array(features, dtype=np.float32)
                        if features_array.ndim == 3:
                            # 将三维数组 (n_samples, 1, n_features) 转换为二维 (n_samples, n_features)
                            features_array = features_array.reshape(features_array.shape[0], -1)
                        elif features_array.ndim > 3:
                            # 处理更高维度的情况
                            features_array = features_array.reshape(features_array.shape[0], -1)

                        self.features_list = features_array
                    else:
                        self.features_list = np.array([], dtype=np.float32).reshape(0, 0)

                    self.names_list = target_features.get('names', [])

                    # 确保名称列表长度与特征列表一致
                    if len(self.names_list) < len(self.features_list):
                        # 如果名称少于特征，用默认名称补充
                        for i in range(len(self.names_list), len(self.features_list)):
                            self.names_list.append(f"Person_{i}")

                    logger.info(f"从字典中提取了 {len(self.features_list)} 个特征和 {len(self.names_list)} 个名称")
                    logger.info(f"特征维度: {self.features_list.shape}")
                else:
                    logger.warning("特征字典格式不正确，需要包含'features'键")
                    # 创建空的二维数组
                    self.features_list = np.array([], dtype=np.float32).reshape(0, 0)
            else:
                logger.warning(f"无法识别的目标特征格式: {type(target_features)}")
                # 创建空的二维数组
                self.features_list = np.array([], dtype=np.float32).reshape(0, 0)

        self.is_global = is_global

        # 视频读取参数
        self.queue_size = queue_size
        self.hardware_decode = hardware_decode
        self.use_ffmpeg = use_ffmpeg

        # 检测参数
        self.conf_threshold = conf_threshold

        # 创建停止事件
        self.stop_event = mp.Event()

        # 初始化完成事件
        self.ready_event = mp.Event()

        # 流运行状态
        self.is_running = False
        self.error = None

        # 其他属性将在run方法中初始化
        # 这些对象不能在__init__中创建，因为它们不能被序列化到子进程
        self.person_detector = None
        self.deepsort = None
        self.video_reader = None
        self.frame_queue = None
        self.reader_stop_event = None
        self.reader_ready_event = None
        self.streamer = None

        # 跟踪和重识别相关变量
        self.track_features = {}  # 跟踪ID到特征向量的映射
        self.track_history = {}  # 跟踪ID到位置历史的映射
        self.track_match_status = {}  # 跟踪ID到匹配状态的映射（True表示已匹配，False表示未匹配）
        self.track_best_match = {}  # 跟踪ID到最佳匹配结果的映射
        self.track_last_match_frame = {}  # 跟踪ID到最后一次匹配帧号的映射
        self.match_interval = 25  # 匹配间隔帧数
        self.similarity_threshold = 0.5  # 相似度阈值
        # 新增：连续未匹配记忆
        self.track_unmatch_count = {}  # 跟踪ID到连续未匹配帧数的映射
        # 新增：ID锁定机制
        self.locked_target_id = None  # 当前锁定的目标track_id

        # RTMP推流相关
        self.rtmp_url = rtmp_url  # RTMP推流地址
        self.rtmp_streamer = None  # RTMP推流器实例

        # 设置进程名称
        self.name = f"ReidTask-{machine_id}"

        logger.info(f"已创建设备 {machine_id} 的行人重识别任务")

    def stop(self):
        """停止行人重识别任务"""
        logger.info(f"正在停止设备 {self.machine_id} 的行人重识别任务")
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

    def run(self):
        """
        运行行人重识别任务
        """
        logger.info("时间戳：{}, ReidTask.run()".format(int(time.time())))
        try:
            logger.info(f"设备 {self.machine_id} 的行人重识别任务开始运行")

            # 初始化模型 - 在子进程中加载模型
            if self.is_global:
                logger.info("时间戳：{}, 全局加载模型".format(int(time.time())))
                # 从全局模型管理器获取模型
                try:
                    # 正确初始化PersonDetectYOLO8，传入模型管理器和半精度参数
                    self.person_detector = PersonDetectYOLO8(
                        model_manager=model_manager
                        # fp16=torch.cuda.is_available()  # 如果CUDA可用，则启用半精度
                    )

                    # 获取DeepSORT跟踪器，处理返回的元组
                    deepsort_result = model_manager.get_model("deepsort")
                    if isinstance(deepsort_result, tuple) and len(deepsort_result) == 2:
                        self.deepsort = deepsort_result[0]
                        deepsort_model_id = deepsort_result[1]
                        logger.info(f"成功获取DeepSORT模型: {deepsort_model_id}")
                    else:
                        self.deepsort = deepsort_result

                    logger.info(f"设备 {self.machine_id} 已成功从全局模型管理器获取模型")
                except Exception as e:
                    logger.error(f"从全局模型管理器获取模型失败: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    self.error = str(e)
                    return
            else:
                # 本地创建模型
                logger.info("时间戳：{}, 本地加载模型".format(int(time.time())))
                try:
                    self.person_detector = PersonDetectYOLO8()
                    from utils.parser import get_config
                    parser = argparse.ArgumentParser()
                    # deep_sort
                    parser.add_argument("--sort", default=False, help='True: sort model or False: reid model')
                    parser.add_argument("--config_deepsort", type=str,
                                        default="/data/lkh/projects/hxjm/smart-monitor-alg-platform/config/deep_sort.yaml")
                    parser.add_argument("--display", default=True, help='show resule')
                    parser.add_argument("--frame_interval", type=int, default=1)
                    parser.add_argument("--cpu", dest="use_cuda", action="store_false", default=True)
                    args = parser.parse_args()
                    deepsort_config = get_config()
                    deepsort_config.merge_from_file(args.config_deepsort)
                    self.deepsort = build_tracker(deepsort_config, False, use_cuda=True)
                    logger.info(f"设备 {self.machine_id} 已创建本地模型实例")
                except Exception as e:
                    logger.error(f"创建本地模型实例失败: {e}")
                    self.error = str(e)
                    return
            logger.info("时间戳：{}, 加载模型完成".format(int(time.time())))
            self.use_half_precision = hasattr(self.person_detector, 'fp16') and self.person_detector.fp16
            if self.use_half_precision:
                logger.info(f"设备 {self.machine_id} 已启用半精度推理，可提高性能")

            # 验证模型
            if not self.person_detector or not self.deepsort:
                logger.error(f"设备 {self.machine_id} 无法获取所需模型，任务终止")
                self.error = "无法获取所需模型"
                return

            # 创建并启动基于PyAV的视频读取线程
            try:
                logger.info(f"正在创建视频读取器线程: {self.video_url}")
                logger.info("时间戳：{},多线程 create_video_reader()".format(int(time.time())))
                # 使用自定义的create_video_reader函数创建和启动视频读取器
                self.video_reader, self.frame_queue, self.reader_stop_event, self.reader_ready_event = create_video_reader(
                    video_url=self.video_url,
                    machine_id=self.machine_id,
                    codec_type=self.codec_type,
                    queue_size=self.queue_size
                )
                logger.info("时间戳：{},多线程后台 create_video_reader()".format(int(time.time())))
                # 等待视频读取器就绪或检查错误
                ready_timeout = 60  # 最多等待60秒
                ready = self.reader_ready_event.wait(timeout=ready_timeout)
                logger.info("时间戳：{},多线程wait ready create_video_reader()".format(int(time.time())))
                if not ready:
                    # 读取器启动失败
                    logger.error(f"视频读取器初始化失败或超时")
                    self.error = f"视频读取器初始化失败或超时"
                    return

                logger.info(f"视频读取器已就绪: {self.machine_id}")

            except Exception as e:
                logger.error(f"创建视频读取器失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
                self.error = f"创建视频读取器失败: {e}"
                return

            # 初始化RTMP推流器
            try:
                from utils.ffmpeg import RTMPStreamer

                # 如果未提供RTMP URL，则自动生成一个
                if self.rtmp_url is None:
                    from config.config import settings
                    if hasattr(settings, 'RTMP_SERVER'):
                        self.rtmp_url = f"{settings.RTMP_SERVER}{self.machine_id}"
                    else:
                        self.rtmp_url = f"rtmp://localhost/live/{self.machine_id}"

                logger.info(f"初始化RTMP推流器，URL: {self.rtmp_url}")

                # 获取视频的第一帧，用于初始化推流器
                try:
                    first_frame = self.frame_queue.get(timeout=5.0)
                    height, width = first_frame.shape[:2]

                    # 将第一帧放回队列
                    self.frame_queue.put(first_frame)
                    # 创建并启动RTMP推流器
                    self.rtmp_streamer = RTMPStreamer()
                    logger.info("时间戳：{},多线程 start_stream()".format(int(time.time())))
                    if self.rtmp_streamer.start_stream(
                            output_url=self.rtmp_url,
                            width=width,
                            height=height,
                            fps=25
                    ):
                        logger.info(f"RTMP推流器初始化成功: {self.rtmp_url}")
                    else:
                        logger.error("RTMP推流器初始化失败")
                        self.rtmp_enabled = False
                        self.rtmp_streamer = None
                    logger.info("时间戳：{},多线程 start_stream()".format(int(time.time())))
                except Exception as e:
                    logger.error(f"获取第一帧或初始化RTMP推流器失败: {e}")
                    self.rtmp_enabled = False
                    self.rtmp_streamer = None
            except Exception as e:
                logger.error(f"导入RTMPStreamer或初始化推流器失败: {e}")
                self.rtmp_enabled = False
                self.rtmp_streamer = None

            # 设置初始化完成标志
            self.is_running = True
            self.ready_event.set()

            # 帧计数器和时间标记
            frame_count = 0
            start_time = time.time()
            last_log_time = time.time()
            self.last_log_time = time.time()  # 用于FPS计算

            # 处理间隔（每隔几帧处理一次）
            self.process_interval = 1  # 增大处理间隔以提高FPS

            # 跟踪相关变量
            track_missing_count = {}  # 跟踪ID到消失帧数的映射
            missing_threshold = 30  # 消失阈值，超过此值认为目标已离开

            # 主循环
            while not self.stop_event.is_set():
                # 从视频读取器队列获取一帧
                try:
                    frame = self.frame_queue.get(timeout=1.0)
                except Empty:
                    # 如果队列为空，可能是视频读取线程已经停止
                    if not self.video_reader.is_alive() or self.reader_stop_event.is_set():
                        logger.error(f"视频读取器线程已停止")
                        break

                    # 等待一段时间后继续尝试
                    time.sleep(0.1)
                    continue

                # 增加帧计数
                frame_count += 1

                try:
                    # 处理当前帧
                    processed_frame = self.process_frame(frame, frame_count, track_missing_count)
                    self.rtmp_streamer.push_frame(processed_frame)

                    # 更新处理时间
                    last_log_time = time.time()
                except Exception as e:
                    logger.error(f"设备 {self.machine_id} 的行人重识别任务运行出错: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
        except Exception as e:
            logger.error(f"设备 {self.machine_id} 的行人重识别任务运行出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.error = str(e)
            if self.is_running:
                self.is_running = False
        finally:
            # 确保资源被释放
            self.cleanup()

    def process_frame(self, frame, frame_count, track_missing_count):
        """处理单帧图像，执行检测、跟踪和匹配"""
        vis_frame = frame.copy()
        missing_threshold = 30
        current_track_ids = set()
        with torch.no_grad():
            # 检测和跟踪每帧都做
            if frame_count % self.process_interval == 0:
                bbox_xywh, confidences, cls_ids, xyxy_list = self.person_detector.detect_with_optimize(frame,
                                                                                                       verbose=False)
                if len(bbox_xywh) > 0:
                    outputs, features = self.deepsort.update(bbox_xywh, confidences, frame)
                    if features.size == 0:
                        logger.warning("DeepSORT未返回特征，跳过此帧特征处理")
                        return vis_frame
                    person_cossim = cosine_similarity(features, self.features_list) if self.features_list.shape[
                                                                                           0] > 0 else np.zeros(
                        (features.shape[0], 0))
                    track_match_info = {}
                    match_candidates = {}
                    locked_found = False
                    for i, det in enumerate(outputs):
                        x1, y1, x2, y2, track_id = det
                        track_id = int(track_id)
                        current_track_ids.add(track_id)
                        if self.locked_target_id is not None and track_id == self.locked_target_id:
                            # 锁定ID，直接画框和标注，不做特征比对
                            locked_found = True
                            color = (0, 255, 0)
                            label = f"ID:{track_id}"
                            if self.track_best_match.get(track_id):
                                _, sim, name = self.track_best_match[track_id]
                                label += f" {name} ({sim:.2f})"
                            cv2.rectangle(vis_frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                            cv2.putText(vis_frame, label, (int(x1), int(y1) - 10),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                            continue
                        # 其他ID，正常特征比对
                        self.track_features[track_id] = features[i]
                        match_idx = -1
                        similarity = 0
                        match_name = None
                        if self.features_list.shape[0] > 0:
                            match_idx = int(np.argmax(person_cossim[i]))
                            similarity = float(np.max(person_cossim[i]))
                            track_match_info[track_id] = (match_idx, similarity)
                            if similarity > self.similarity_threshold:
                                if match_idx not in match_candidates or similarity > match_candidates[match_idx][1]:
                                    match_candidates[match_idx] = (track_id, similarity)
                        else:
                            track_match_info[track_id] = (-1, 0)
                    # 匹配状态更新（只针对非locked_target_id）
                    for track_id, (match_idx, similarity) in track_match_info.items():
                        if self.locked_target_id is not None and track_id == self.locked_target_id:
                            continue  # 锁定ID不再更新匹配状态
                        need_rematch = False
                        last_match_frame = self.track_last_match_frame.get(track_id, -self.match_interval)
                        if frame_count - last_match_frame >= self.match_interval:
                            need_rematch = True
                        if track_id not in self.track_match_status:
                            need_rematch = True
                        is_best = match_idx in match_candidates and match_candidates[match_idx][0] == track_id
                        if similarity > self.similarity_threshold and is_best:
                            if need_rematch or not self.track_match_status.get(track_id, False):
                                self.track_match_status[track_id] = True
                                match_name = self.names_list[match_idx] if match_idx < len(
                                    self.names_list) else f"Person_{match_idx}"
                                self.track_best_match[track_id] = (match_idx, similarity, match_name)
                                self.track_last_match_frame[track_id] = frame_count
                            self.track_unmatch_count[track_id] = 0
                            # 切换锁定ID逻辑：如果当前没有锁定，或新track_id相似度更高，可以切换锁定
                            if self.locked_target_id is None or similarity > \
                                    self.track_best_match.get(self.locked_target_id, (None, 0, None))[1]:
                                self.locked_target_id = track_id
                        else:
                            self.track_unmatch_count[track_id] = self.track_unmatch_count.get(track_id, 0) + 1
                            if self.track_unmatch_count[track_id] > 5:
                                if need_rematch or self.track_match_status.get(track_id, True):
                                    self.track_match_status[track_id] = False
                                    self.track_best_match[track_id] = None
                                    self.track_last_match_frame[track_id] = frame_count
                    # 画框和标注（非locked_target_id）
                    for i, det in enumerate(outputs):
                        x1, y1, x2, y2, track_id = det
                        track_id = int(track_id)
                        if self.locked_target_id is not None and track_id == self.locked_target_id:
                            continue  # 已画过
                        color = (0, 255, 0) if self.track_match_status.get(track_id, False) else (0, 0, 255)
                        cv2.rectangle(vis_frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                        label = f"ID:{track_id}"
                        if self.track_match_status.get(track_id, False) and self.track_best_match.get(track_id):
                            _, sim, name = self.track_best_match[track_id]
                            label += f" {name} ({sim:.2f})"
                        cv2.putText(vis_frame, label, (int(x1), int(y1) - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        # 更新消失计数
        for track_id in list(self.track_features.keys()):
            if track_id not in current_track_ids:
                track_missing_count[track_id] = track_missing_count.get(track_id, 0) + 1
                if track_missing_count[track_id] > missing_threshold:
                    del self.track_features[track_id]
                    if track_id in self.track_match_status:
                        del self.track_match_status[track_id]
                    if track_id in self.track_best_match:
                        del self.track_best_match[track_id]
                    if track_id in self.track_last_match_frame:
                        del self.track_last_match_frame[track_id]
                    if track_id in self.track_unmatch_count:
                        del self.track_unmatch_count[track_id]
                    if track_id == self.locked_target_id:
                        self.locked_target_id = None
                    if track_id in track_missing_count:
                        del track_missing_count[track_id]
        return vis_frame

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
            logger.info(f"已关闭所有OpenCV窗口")

            # 标记为未运行
            self.is_running = False
            logger.info(f"设备 {self.machine_id} 的行人重识别任务已清理资源")
        except Exception as e:
            logger.error(f"清理资源时出错: {e}")


def start_reid_process(machine_id: str, video_url: str, resolution=None, codec_type='h264',
                       ptz_enabled=False, camera_params=None, target_features=None, is_global=True,
                       queue_size=30, hardware_decode=False, use_ffmpeg=True, rtmp_url=None) -> bool:
    """
    启动行人重识别处理进程

    Args:
        machine_id: 摄像头ID
        video_url: 视频URL
        resolution: 分辨率，格式为(width, height)
        codec_type: 编码类型
        ptz_enabled: 是否启用云台控制
        camera_params: 摄像头云台参数
        target_features: 目标行人特征
        is_global: 是否使用全局模型
        queue_size: 帧队列大小
        hardware_decode: 是否使用硬件解码
        use_ffmpeg: 是否使用FFMPEG命令行
        rtmp_url: RTMP推流地址，如果为None则自动生成

    Returns:
        bool: 是否成功启动进程
    """
    global reid_processes

    try:
        # 检查参数
        if not machine_id or not video_url:
            logger.error(f"无效的参数: machine_id={machine_id}, video_url={video_url}")
            return False

        # 检查目标特征
        if not target_features or len(target_features) == 0:
            logger.warning(f"目标特征为空，将不进行特征匹配")

        # 检查进程是否已存在
        with reid_lock:
            if machine_id in reid_processes:
                logger.warning(f"设备 {machine_id} 的行人重识别任务已存在，先停止旧任务")
                stop_reid_process(machine_id)

        # 创建行人重识别任务
        logger.info("时间戳：{}, 多线程启动 ReidTask".format(int(time.time())))
        process = ReidTask(
            machine_id=machine_id,
            video_url=video_url,
            resolution=resolution,
            codec_type=codec_type,
            ptz_enabled=ptz_enabled,
            camera_params=camera_params,
            target_features=target_features,
            is_global=is_global,
            queue_size=queue_size,
            hardware_decode=hardware_decode,
            use_ffmpeg=use_ffmpeg,
            rtmp_url=rtmp_url
        )

        # 启动进程
        process.start()

        # 记录进程
        with reid_lock:
            reid_processes[machine_id] = process

        logger.info(f"已启动设备 {machine_id} 的行人重识别任务，进程ID: {process.pid}")

        # 等待进程初始化完成
        if not process.ready_event.wait(timeout=100):  # 增加等待时间，考虑到视频读取器的初始化
            logger.warning(f"等待设备 {machine_id} 的行人重识别任务初始化超时")

            # 检查进程是否仍在运行
            if not process.is_alive():
                error_msg = process.error if process.error else "未知错误"
                logger.error(f"设备 {machine_id} 的行人重识别任务启动失败: {error_msg}")

                # 清理进程记录
                with reid_lock:
                    if machine_id in reid_processes:
                        del reid_processes[machine_id]

                return False

            logger.info(f"虽然初始化超时，但设备 {machine_id} 的行人重识别任务仍在运行")
        else:
            logger.info(f"设备 {machine_id} 的行人重识别任务初始化完成")

        return True

    except Exception as e:
        logger.error(f"启动设备 {machine_id} 的行人重识别任务失败: {e}")
        import traceback
        logger.error(traceback.format_exc())

        # 清理
        with reid_lock:
            if machine_id in reid_processes:
                process = reid_processes[machine_id]
                try:
                    if process.is_alive():
                        process.terminate()
                except:
                    pass
                del reid_processes[machine_id]

        return False


def stop_reid_process(machine_id: str) -> bool:
    """
    停止行人重识别处理进程

    Args:
        machine_id: 摄像头ID

    Returns:
        bool: 是否成功停止进程
    """
    global reid_processes

    try:
        # 检查进程是否存在
        with reid_lock:
            if machine_id not in reid_processes:
                logger.warning(f"设备 {machine_id} 的行人重识别任务不存在")
                return False

            # 获取进程
            process = reid_processes[machine_id]

        # 发送停止信号
        process.stop()

        # 从字典中移除
        with reid_lock:
            if machine_id in reid_processes:
                del reid_processes[machine_id]

        logger.info(f"已停止设备 {machine_id} 的行人重识别任务")
        return True

    except Exception as e:
        logger.error(f"停止设备 {machine_id} 的行人重识别任务失败: {e}")
        import traceback
        logger.error(traceback.format_exc())

        # 尝试强制清除
        with reid_lock:
            if machine_id in reid_processes:
                try:
                    process = reid_processes[machine_id]
                    if process.is_alive():
                        process.terminate()
                except:
                    pass
                del reid_processes[machine_id]

        return False


# 添加测试函数
if __name__ == "__main__":

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    )

    import os
    import cv2
    import numpy as np
    import argparse
    from utils.parser import get_config

    # 获取项目根目录（用于正确解析配置文件路径）
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='行人重识别测试程序')
    parser.add_argument('--video', type=str, default='test.mp4', help='视频文件路径')
    parser.add_argument('--image', type=str, default='test.png', help='目标图片路径')
    parser.add_argument('--id', type=str, default='test', help='测试标识')
    parser.add_argument('--global_model', action='store_true', help='是否使用全局模型')
    parser.add_argument('--config_deepsort', type=str,
                        default=os.path.join(project_root, "config/deep_sort.yaml"),
                        help='DeepSORT配置文件路径')

    # 解析参数
    args = parser.parse_args()

    logger.info("开始测试行人重识别程序")

    # 设置测试资源路径
    video_path = args.video
    target_image_path = args.image
    machine_id = args.id
    use_global_model = args.global_model
    config_path = args.config_deepsort

    # 检查配置文件是否存在
    if not os.path.exists(config_path):
        logger.error(f"DeepSORT配置文件不存在: {config_path}")
        logger.info(f"尝试查找备选配置文件位置...")

        # 尝试不同的可能位置
        possible_paths = [
            "./config/deep_sort.yaml",
            "../config/deep_sort.yaml",
            "../../config/deep_sort.yaml",
            os.path.join(os.path.dirname(__file__), "../../config/deep_sort.yaml")
        ]

        for path in possible_paths:
            if os.path.exists(path):
                config_path = path
                logger.info(f"找到配置文件: {config_path}")
                break
        else:
            logger.error("无法找到DeepSORT配置文件，请确保config/deep_sort.yaml存在")
            sys.exit(1)

    # 检查文件是否存在
    if not os.path.exists(video_path):
        logger.error(f"视频文件不存在: {video_path}")
        sys.exit(1)

    if not os.path.exists(target_image_path):
        logger.error(f"目标图片不存在: {target_image_path}")
        sys.exit(1)

    try:
        # 加载目标图片
        target_image = cv2.imread(target_image_path)
        if target_image is None:
            logger.error(f"无法读取目标图片: {target_image_path}")
            sys.exit(1)

        logger.info(f"正在从目标图片提取特征: {target_image_path}")

        # 创建临时模型提取特征
        person_detector = PersonDetectYOLO8()

        # 创建DeepSORT跟踪器，使用绝对路径
        logger.info(f"正在使用配置文件: {config_path}")
        deepsort_config = get_config()
        deepsort_config.merge_from_file(config_path)
        deepsort = build_tracker(deepsort_config, False, 'cuda' if torch.cuda.is_available() else 'cpu')

        # 检测目标图片中的人物
        bbox_xywh, confidences, cls_ids, xyxy_list = person_detector.detect_with_optimize(target_image, verbose=True)
        if len(bbox_xywh) == 0:
            logger.error("目标图片中未检测到人物")
            sys.exit(1)

        logger.info(f"在目标图片中检测到 {len(bbox_xywh)} 个人物")

        # 提取特征
        _, target_features = deepsort.update(bbox_xywh, confidences, target_image)
        if target_features.size == 0:
            logger.error("无法提取目标特征")
            sys.exit(1)

        # 准备目标特征字典
        target_features_dict = {
            'features': target_features,
            'names': [f'目标人物_{i}' for i in range(len(target_features))]
        }

        logger.info(f"已成功提取目标特征，形状: {target_features.shape}")

        # 启动行人重识别程序
        logger.info(f"正在启动行人重识别程序，视频路径: {video_path}")
        success = start_reid_process(
            machine_id=machine_id,
            video_url=video_path,
            target_features=target_features_dict,
            is_global=False
        )

        if success:
            logger.info("行人重识别启动成功，按q键退出")
            try:
                # 等待用户输入q退出
                while True:
                    key = input()
                    if key.lower() == 'q':
                        break
            except KeyboardInterrupt:
                logger.info("收到键盘中断信号，正在退出...")

            # 停止行人重识别
            stop_reid_process(machine_id)
        else:
            logger.error("行人重识别启动失败")

    except Exception as e:
        logger.error(f"测试过程中出错: {e}")
        import traceback

        logger.error(traceback.format_exc())

    logger.info("测试完成")

