"""
日志模块 - 支持文件和控制台输出（异步后台线程）
避免多进程环境下的 print() 阻塞问题
"""
import os
import logging
from logging.handlers import RotatingFileHandler, QueueHandler, QueueListener
from datetime import datetime
import queue
import threading
import atexit


# ========== 全局异步日志队列 ==========
_log_queue = queue.Queue(-1)  # 无限大小队列
_queue_listener = None
_listener_lock = threading.Lock()


def _get_or_create_queue_listener(handlers):
    """获取或创建全局队列监听器（单例）"""
    global _queue_listener
    
    with _listener_lock:
        if _queue_listener is None:
            # 创建后台监听线程
            _queue_listener = QueueListener(
                _log_queue,
                *handlers,
                respect_handler_level=True
            )
            _queue_listener.start()
            
            # 注册退出时停止监听器
            atexit.register(_queue_listener.stop)
    
    return _queue_listener


def get_logger(
    name: str,
    log_dir: str = None,
    level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    console: bool = True,
    async_mode: bool = True  # 🔥 新增：是否使用异步模式
) -> logging.Logger:
    """
    获取日志器（支持异步后台线程）
    
    Args:
        name: 日志器名称（通常用模块名）
        log_dir: 日志文件目录，None 则只输出到控制台
        level: 日志级别
        max_bytes: 单个日志文件最大大小
        backup_count: 保留的日志文件数量
        console: 是否同时输出到控制台
        async_mode: 是否使用异步模式（避免 I/O 阻塞）
    
    Returns:
        logging.Logger
    """
    logger = logging.getLogger(name)
    
    # 避免重复添加 handler
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    # 格式
    formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 收集所有 handler
    handlers = []
    
    # 控制台输出
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)
    
    # 文件输出
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"{name}.log")
        
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    
    if async_mode and handlers:
        # 🔥 异步模式：使用队列 handler + 后台监听线程
        # 主线程只负责往队列放日志，不会阻塞
        queue_handler = QueueHandler(_log_queue)
        queue_handler.setLevel(level)
        logger.addHandler(queue_handler)
        
        # 启动全局监听器（单例）
        _get_or_create_queue_listener(handlers)
    else:
        # 同步模式：直接添加 handler（传统方式）
        for handler in handlers:
            logger.addHandler(handler)
    
    return logger


class ServiceLogger:
    """
    服务日志器 - 便捷封装（支持异步后台线程）
    
    用法:
        logger = ServiceLogger("boxmot", __file__)
        logger.info("Processing frame", dets=5, time=0.1)
        logger.print("[DEBUG] Quick message")  # 替代 print()
    """
    
    def __init__(self, name: str, module_file: str, level: int = logging.INFO, async_mode: bool = True):
        """
        Args:
            name: 服务名称
            module_file: 模块文件路径 (__file__)，日志会保存在 logs 子目录，按时间命名
            level: 日志级别
            async_mode: 是否使用异步模式（默认 True，避免 I/O 阻塞）
        """
        self.name = name
        self.async_mode = async_mode
        
        # 创建 logs 子目录
        module_dir = os.path.dirname(os.path.abspath(module_file))
        log_dir = os.path.join(module_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        # 使用时间戳作为日志文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"{name}_{timestamp}.log"
        
        # 创建自定义 logger
        self._logger = self._create_timestamped_logger(name, log_dir, log_filename, level, async_mode)
    
    def _create_timestamped_logger(self, name: str, log_dir: str, log_filename: str, 
                                   level: int, async_mode: bool) -> logging.Logger:
        """创建带时间戳的日志器"""
        logger = logging.getLogger(f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
        # 避免重复添加 handler
        if logger.handlers:
            return logger
        
        logger.setLevel(level)
        
        # 格式
        formatter = logging.Formatter(
            fmt='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 收集所有 handler
        handlers = []
        
        # 控制台输出
        if os.getenv("BOXMOT_ASYNC_LOG_CONSOLE", "1") == "1":
            console_handler = logging.StreamHandler()
            console_handler.setLevel(level)
            console_handler.setFormatter(formatter)
            handlers.append(console_handler)
        
        # 文件输出
        log_file = os.path.join(log_dir, log_filename)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=50 * 1024 * 1024,  # 50MB
            backupCount=10,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
        
        if async_mode and handlers:
            # 异步模式：使用队列 handler + 后台监听线程
            queue_handler = QueueHandler(_log_queue)
            queue_handler.setLevel(level)
            logger.addHandler(queue_handler)
            
            # 启动全局监听器（单例）
            _get_or_create_queue_listener(handlers)
        else:
            # 同步模式：直接添加 handler
            for handler in handlers:
                logger.addHandler(handler)
        
        return logger
    
    def _format_kwargs(self, kwargs: dict) -> str:
        """格式化关键字参数"""
        if not kwargs:
            return ""
        parts = [f"{k}={v}" for k, v in kwargs.items()]
        return " | " + " ".join(parts)
    
    def debug(self, msg: str, **kwargs):
        self._logger.debug(msg + self._format_kwargs(kwargs))
    
    def info(self, msg: str, **kwargs):
        self._logger.info(msg + self._format_kwargs(kwargs))
    
    def warning(self, msg: str, **kwargs):
        self._logger.warning(msg + self._format_kwargs(kwargs))
    
    def error(self, msg: str, **kwargs):
        self._logger.error(msg + self._format_kwargs(kwargs))
    
    def exception(self, msg: str, **kwargs):
        self._logger.exception(msg + self._format_kwargs(kwargs))
    
    def print(self, msg: str, **kwargs):
        """
        替代 print() 的方法，使用 INFO 级别
        用于快速输出消息，不阻塞主线程
        
        Example:
            logger.print("[SHM-START] Opening shm=...", pid=123)
        """
        self.info(msg, **kwargs)
