import subprocess
import threading
import logging
import cv2
import numpy as np
from queue import Queue, Empty, Full
import time
import os
import shutil

from config.config import settings

# 尝试导入 GStreamer
HAS_GST = False
try:
    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst

    Gst.init(None)
    HAS_GST = True
except Exception as e:
    # 不强制要求 GStreamer 存在，后续根据配置降级为 ffmpeg
    Gst = None
    HAS_GST = False

# 创建logs目录（如果不存在）
if not os.path.exists('logs'):
    os.makedirs('logs')

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/rtmp_stream.log'),  # 写入文件
        logging.StreamHandler()  # 同时输出到控制台
    ]
)
logger = logging.getLogger(__name__)


class RTMPStreamer:
    """将处理后的视频帧转发到RTMP服务器"""

    def __init__(self, buffer_size=30):
        # 后端: "gstreamer" 或 "ffmpeg"
        self.backend = self._select_backend()

        # GStreamer 相关
        self.pipeline = None
        self.appsrc = None
        # ffmpeg 相关
        self.process = None

        self.is_running = False
        self.frame_queue = Queue(maxsize=buffer_size)
        self.stream_info = {}
        self.lock = threading.Lock()
        self.last_frame_time = time.time()
        self.fps = None  # 将在 start_stream 中设置
        self.frame_interval = None  # 将在 start_stream 中设置
        self.dropped_frames = 0
        self.total_frames = 0
        self.last_fps_check = time.time()
        self.fps_counter = 0
        self.reconnect_count = 0
        self.max_reconnects = 3
        self.last_write_time = time.time()
        self.write_timeout = 5.0  # 5秒没有写入则尝试重连
        self.frames_processed = 0
        self.frames_dropped = 0
        self.last_stats_time = time.time()
        # 添加线程活动标记
        self.thread_active = False
        self.thread_heartbeat = time.time()
        # 优化：批量写入缓冲区
        self.buffer_frames = []  # 批量写入的帧缓冲区
        self.buffer_size = 3  # 累积3帧再flush（约120ms @ 25fps）
        self.last_flush_time = time.time()
        self.flush_interval = 0.1  # 每100ms强制flush一次（保证低延迟）
        # 跳帧策略：取两帧，推一帧，丢一帧
        self.frame_counter = 0  # 帧计数器，用于实现跳帧
        # 时间戳
        self.timestamp_ns = 0
        self.frame_duration_ns = 0

    @staticmethod
    def _ffmpeg_available() -> bool:
        """检查 ffmpeg 是否可用"""
        exe = settings.FFMPEG_PATH or "ffmpeg"
        # 如果是绝对/相对路径，先直接判断文件是否存在，否则用 which
        if os.path.sep in exe:
            return os.path.exists(exe) and os.access(exe, os.X_OK)
        return shutil.which(exe) is not None

    def _select_backend(self) -> str:
        """根据配置和环境选择推流后端"""
        cfg = (getattr(settings, "STREAM_BACKEND", "auto") or "auto").lower()

        if cfg == "gstreamer":
            if HAS_GST:
                logger.info("RTMP 推流后端: 强制使用 GStreamer")
                return "gstreamer"
            logger.warning("配置要求使用 GStreamer，但环境中未检测到，降级为 ffmpeg")
            return "ffmpeg"

        if cfg == "ffmpeg":
            logger.info("RTMP 推流后端: 强制使用 ffmpeg")
            return "ffmpeg"

        # auto 模式: 优先 GStreamer，其次 ffmpeg
        if HAS_GST:
            logger.info("RTMP 推流后端(auto): 检测到 GStreamer，优先使用 GStreamer")
            return "gstreamer"
        if self._ffmpeg_available():
            logger.info("RTMP 推流后端(auto): 使用 ffmpeg")
            return "ffmpeg"

        # 都不可用，默认返回 ffmpeg 并在 start_stream 中再报错
        logger.error("未检测到可用的推流后端(GStreamer 或 ffmpeg)，请安装至少一个")
        return "ffmpeg"

    def start_stream(self, output_url: str, width: int, height: int, fps: int = 25) -> bool:
        """
        启动RTMP推流 - 创建单独的推流线程
        """
        try:
            with self.lock:
                if self.is_running:
                    return False

                # 记录当前线程信息
                current_thread = threading.current_thread()
                logger.info(f"启动推流的线程: {current_thread.name} (ID: {current_thread.ident})")

                self.stream_info = {
                    'url': output_url,
                    'width': width,
                    'height': height,
                    'fps': fps,
                    'id': f"{int(time.time())}"
                }

                # 设置FPS相关参数
                self.fps = fps
                self.frame_interval = 1.0 / fps if fps > 0 else 0.04
                self.frame_duration_ns = int(1e9 / fps) if fps > 0 else 0
                self.timestamp_ns = 0
                self.process = None

                if self.backend == "gstreamer":
                    # 使用 GStreamer appsrc 推流
                    if not HAS_GST:
                        logger.error("选择了 GStreamer 作为推流后端，但环境中未检测到 Gst")
                        return False

                    pipeline_str = (
                        "appsrc name=src is-live=true format=time do-timestamp=true block=true "
                        f"! video/x-raw,format=BGR,width={width},height={height},framerate={fps}/1 "

                        # 转为 x264 支持的 I420，更快，也减少延迟
                        "! videoconvert n-threads=1 ! video/x-raw,format=I420 "

                        # x264 极低延迟编码配置
                        "! x264enc "
                            "speed-preset=ultrafast "     # 最高编码速度(最低延迟)
                            "tune=zerolatency "           # 禁用 B 帧
                            "threads=1 "                  # 保证编码全程单帧处理
                            "sync-lookahead=0 "           # 禁用 Lookahead 避免缓存
                            "key-int-max=30 "             # 关键帧间隔（越小延迟越低）
                            "bframes=0 "                  # 禁用 B 帧，降低延迟
                            "byte-stream=true "

                        # 立即打包 FLV
                        "! video/x-h264,stream-format=byte-stream,alignment=au "
                        "! h264parse config-interval=-1 "

                        # FLV 流封装
                        "! flvmux streamable=true "

                        # RTMP 推流
                        f"! rtmpsink location={output_url} async=false"
                    )
                    logger.info(f"启动GStreamer管道: {pipeline_str}")

                    try:
                        self.pipeline = Gst.parse_launch(pipeline_str)
                        self.appsrc = self.pipeline.get_by_name("src")
                        if self.appsrc is None:
                            raise RuntimeError("GStreamer 管道中未找到 appsrc 元件 'src'")
                        ret = self.pipeline.set_state(Gst.State.PLAYING)
                        if ret == Gst.StateChangeReturn.FAILURE:
                            raise RuntimeError("GStreamer 管道无法进入 PLAYING 状态")
                    except Exception as e:
                        logger.error(f"启动GStreamer推流失败: {e}", exc_info=True)
                        self.pipeline = None
                        self.appsrc = None
                        return False
                else:
                    # 使用 ffmpeg stdin 推流
                    ffmpeg_exe = settings.FFMPEG_PATH or "ffmpeg"
                    if os.path.sep in ffmpeg_exe:
                        ffmpeg_cmd = ffmpeg_exe
                    else:
                        ffmpeg_cmd = shutil.which(ffmpeg_exe) or ffmpeg_exe

                    command = [
                        ffmpeg_cmd,
                        "-y",
                        "-f", "rawvideo",
                        "-vcodec", "rawvideo",
                        "-pix_fmt", "bgr24",
                        "-s", f"{width}x{height}",
                        "-r", str(fps),
                        "-i", "-",
                        "-c:v", "libx264",
                        "-pix_fmt", "yuv420p",
                        "-preset", "ultrafast",
                        "-tune", "zerolatency",
                        "-profile:v", "baseline",
                        "-level", "3.0",
                        "-g", "30",
                        "-bf", "0",
                        "-bufsize", "0",
                        "-maxrate", "2000k",
                        "-threads", "0",
                        "-f", "flv",
                        output_url,
                    ]
                    logger.info(f"启动ffmpeg命令: {' '.join(map(str, command))}")
                    try:
                        self.process = subprocess.Popen(
                            command,
                            stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                    except Exception as e:
                        logger.error(f"启动ffmpeg推流失败: {e}", exc_info=True)
                        self.process = None
                        return False

                # 清空队列
                while not self.frame_queue.empty():
                    try:
                        self.frame_queue.get_nowait()
                    except Empty:
                        pass

                # 重置计数器
                self.dropped_frames = 0
                self.total_frames = 0
                self.fps_counter = 0
                self.last_fps_check = time.time()
                self.reconnect_count = 0
                self.frames_processed = 0
                self.frames_dropped = 0
                self.last_stats_time = time.time()
                self.thread_active = True
                self.thread_heartbeat = time.time()
                self.frame_counter = 0  # 重置帧计数器，用于跳帧策略

                # 设置运行标志
                self.is_running = True
                
                # 创建单独的推流线程
                self.stream_thread = threading.Thread(
                    target=self._process_frames,
                    name=f"RTMP_Stream_{self.stream_info.get('id', 'unknown')}",
                    daemon=True
                )
                self.stream_thread.start()
                logger.info(f"推流线程已启动: {self.stream_thread.name} (ID: {self.stream_thread.ident})")
                
                return True

        except Exception as e:
            logger.error(f"启动RTMP推流失败: {e}", exc_info=True)
            self.stop()
            return False

    def _process_frames(self):
        """处理并推流帧 - 在当前线程中执行（优化版：批量写入）"""
        thread_id = threading.get_ident()
        current_thread = threading.current_thread()
        logger.info(f"推流线程开始运行: {current_thread.name} (ID: {thread_id})")
        
        start_time = time.time()
        last_frame_time = time.time()
        last_status_time = time.time()
        
        # 预分配缓冲区大小（避免重复分配）
        frame_size = None
        
        try:
            while self.is_running:
                # 更新心跳
                self.thread_heartbeat = time.time()

                # 检查推流后端是否仍然可用
                if self.backend == "gstreamer":
                    if self.pipeline is None or self.appsrc is None:
                        logger.error("GStreamer 管道未初始化或已释放")
                        break
                else:
                    if self.process is None or self.process.poll() is not None:
                        logger.error(f"ffmpeg 进程已退出，返回码: {self.process.returncode if self.process else 'None'}")
                        break
                
                try:
                    # 跳帧策略：取两帧，推一帧，丢一帧
                    # 每次循环都取2帧，推第1帧，丢第2帧
                    
                    # 从队列获取第一帧（用于推流）
                    frame = self.frame_queue.get(timeout=0.5)
                    
                    # # 从队列获取第二帧（丢弃）
                    # try:
                    #     frame2 = self.frame_queue.get(timeout=0.1)
                    #     # 丢弃第二帧
                    #     self.frames_dropped += 1
                    # except Empty:
                    #     # 如果队列为空，只有一帧，直接推流
                    #     pass
                    
                    self.last_frame_time = time.time()
                    
                    # 优化1: 使用更高效的内存拷贝方式
                    # 对于numpy数组，直接使用data属性访问底层缓冲区（避免额外检查）
                    if frame_size is None:
                        frame_size = frame.nbytes
                    
                    # 使用frame.data.tobytes()比frame.tobytes()稍快（跳过一些numpy检查）
                    # 但需要确保内存是连续的
                    if frame.flags['C_CONTIGUOUS']:
                        frame_bytes = frame.data.tobytes()  # 最快方式
                    else:
                        # 内存不连续，需要先拷贝为连续内存
                        frame = np.ascontiguousarray(frame)
                        frame_bytes = frame.data.tobytes()
                    
                    # 推流：根据后端分别处理
                    if self.backend == "gstreamer":
                        buf = Gst.Buffer.new_allocate(None, len(frame_bytes), None)
                        buf.fill(0, frame_bytes)

                        # 设置时间戳
                        buf.pts = self.timestamp_ns
                        buf.dts = self.timestamp_ns
                        buf.duration = self.frame_duration_ns
                        self.timestamp_ns += self.frame_duration_ns

                        ret = self.appsrc.emit("push-buffer", buf)
                        if ret != Gst.FlowReturn.OK:
                            logger.error(f"GStreamer push-buffer 返回错误: {ret}")
                            break
                    else:
                        # ffmpeg: 写入 stdin
                        try:
                            self.process.stdin.write(frame_bytes)
                            # 按间隔 flush，减少系统调用
                            current_time = time.time()
                            if current_time - self.last_flush_time >= self.flush_interval:
                                self.process.stdin.flush()
                                self.last_flush_time = current_time
                        except (BrokenPipeError, OSError) as e:
                            logger.error(f"写入ffmpeg失败: {e}，可能RTMP服务器断开连接")
                            break

                    self.frames_processed += 1
                    
                    # 优化2: 批量flush（对于GStreamer意义不大，这里仅保留节奏控制）
                    current_time = time.time()
                    time_since_flush = current_time - self.last_flush_time
                    should_flush = (
                        len(self.buffer_frames) >= self.buffer_size - 1 or  # 累积足够帧数
                        time_since_flush >= self.flush_interval  # 或超过时间间隔（保证低延迟）
                    )
                    
                    if should_flush:
                        self.last_flush_time = current_time
                        self.buffer_frames.clear()
                    else:
                        self.buffer_frames.append(1)  # 仅用于计数
                    
                    # 计算FPS和延迟
                    frame_time = current_time - last_frame_time
                    last_frame_time = current_time
                    
                    # 计算实际FPS
                    fps = 1.0 / frame_time if frame_time > 0 else 0
                    
                    # 计算队列延迟
                    queue_size = self.frame_queue.qsize()
                    queue_delay = queue_size / self.fps * 1000 if self.fps > 0 else 0
                    
                    # 计算丢帧率
                    drop_rate = self.frames_dropped / (self.total_frames + 0.001) * 100
                    
                    # 每秒输出一次状态
                    if current_time - last_status_time >= 1.0:
                        # logger.info(f"推流状态 - FPS: {int(fps)}/{self.fps}, 队列: {queue_size}/{self.frame_queue.maxsize}, 丢帧率: {drop_rate:.1f}%, 延迟: {int(queue_delay)}ms, 线程ID: {thread_id}")
                        last_status_time = current_time
                        
                        # 每5秒输出一次详细状态
                        if int(current_time) % 5 == 0:
                            thread_status = {
                                'thread_name': current_thread.name,
                                'thread_id': thread_id,
                                'is_alive': True,
                                'is_daemon': current_thread.daemon,
                                'last_frame_time': f"{time.time() - self.last_frame_time:.1f}s ago",
                                'queue_size': queue_size,
                                'process_alive': (
                                    (self.backend == "gstreamer" and self.pipeline is not None) or
                                    (self.backend == "ffmpeg" and self.process is not None and self.process.poll() is None)
                                ),
                                'is_running': self.is_running,
                                'running_time': f"{time.time() - start_time:.1f}s"
                            }
                            # logger.info(f"线程状态: {thread_status}")
                    
                except Empty:
                    # 队列为空，等待新帧
                    continue
                except Exception as e:
                    logger.error(f"处理帧时发生错误: {e}", exc_info=True)
                    break
                    
        except Exception as e:
            logger.error(f"推流线程发生严重错误: {e}", exc_info=True)
        finally:
            logger.info(f"推流线程结束运行: {current_thread.name}, ID: {thread_id}, 运行时间: {time.time() - start_time:.1f}s")
            # 清理资源
            self.is_running = False
            # 停止后端
            if self.backend == "gstreamer":
                if self.pipeline is not None:
                    try:
                        if self.appsrc is not None:
                            try:
                                self.appsrc.emit("end-of-stream")
                            except Exception:
                                pass
                        self.pipeline.set_state(Gst.State.NULL)
                    except Exception as e:
                        logger.error(f"停止GStreamer管道出错: {e}")
                    finally:
                        self.pipeline = None
                        self.appsrc = None
            else:
                if self.process is not None:
                    try:
                        if self.process.stdin:
                            try:
                                self.process.stdin.flush()
                                self.process.stdin.close()
                            except Exception:
                                pass
                        self.process.terminate()
                        self.process.wait(timeout=5)
                    except Exception as e:
                        logger.error(f"停止ffmpeg进程出错: {e}")
                    finally:
                        self.process = None

    def push_frame(self, frame: np.ndarray) -> bool:
        """推送一帧视频"""
        try:
            if not self.is_running:
                return False

        #     current_queue_size = self.frame_queue.qsize()

        #     # 队列过满时进行丢帧
        #     if current_queue_size >= self.frame_queue.maxsize * 0.8:
        #         # 丢弃一半的旧帧
        #         frames_to_drop = current_queue_size // 2
        #         for _ in range(frames_to_drop):
        #             try:
        #                 self.frame_queue.get_nowait()
        #                 self.frames_dropped += 1
        #             except Empty:
        #                 break
        #         current_thread = threading.current_thread()
        #         thread_status = {
        #             'thread_name': current_thread.name,
        #             'thread_id': current_thread.ident,
        #             'is_alive': current_thread.is_alive(),
        #             'is_daemon': current_thread.daemon,
        #             'queue_size': self.frame_queue.qsize(),
        #             'pipeline_alive': (
        #                 (self.backend == "gstreamer" and self.pipeline is not None) or
        #                 (self.backend == "ffmpeg" and self.process is not None and self.process.poll() is None)
        #             ),
        #             'is_running': self.is_running
        #         }   
        #         logger.info(f"线程状态: {thread_status}")
        #         print(f"队列过满，丢弃 {frames_to_drop} 帧")

        #     try:
        #         self.frame_queue.put_nowait(frame)
        #         self.total_frames += 1
        #         return True
        #     except Full:
        #         self.frames_dropped += 1
        #         return True
         # 实时优先：如果队列已满，直接丢弃旧帧，只保留最新帧
            if self.frame_queue.full():
                try:
                    # 丢掉一个最旧的帧
                    self.frame_queue.get_nowait()
                    self.frames_dropped += 1
                except Empty:
                    pass

            try:
                self.frame_queue.put_nowait(frame)
                self.total_frames += 1
                return True
            except Full:
                # 极端情况下仍然满，则丢弃本帧
                self.frames_dropped += 1
                return True
        except Exception as e:
            logger.error(f"推送帧失败: {e}")
            return False

    def stop(self):
        """停止推流"""
        self.is_running = False

        # 清空队列
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except Empty:
                pass

        # 停止后端
        if self.backend == "gstreamer":
            if self.pipeline is not None:
                try:
                    if self.appsrc is not None:
                        try:
                            self.appsrc.emit("end-of-stream")
                        except Exception:
                            pass
                    self.pipeline.set_state(Gst.State.NULL)
                except Exception as e:
                    logger.error(f"停止GStreamer管道出错: {e}")
                finally:
                    self.pipeline = None
                    self.appsrc = None
        else:
            if self.process is not None:
                try:
                    if self.process.stdin:
                        try:
                            self.process.stdin.flush()
                            self.process.stdin.close()
                        except Exception:
                            pass
                    self.process.terminate()
                    self.process.wait(timeout=5)
                except Exception as e:
                    logger.error(f"停止ffmpeg进程出错: {e}")
                finally:
                    self.process = None

        logger.info("RTMP推流已停止")
