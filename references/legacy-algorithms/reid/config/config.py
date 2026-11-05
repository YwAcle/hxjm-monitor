from typing import List, ClassVar
class Settings:
    # API配置
    API_VERSION = "/algPlatform"
    API_TITLE = "智慧监控算法平台"
    
    # 模型配置
    DETECTION_CONFIDENCE = 0.5
    TRACKING_CONFIDENCE = 0.5
    
    # 视频处理配置
    MAX_VIDEO_LENGTH = 60  # 最大视频长度（秒）
    MAX_FRAME_WIDTH = 640  # 最大帧宽度
    
    # 流媒体服务器配置
    # RTMP_SERVER = "rtmp://192.168.108.238:1935/live/"
    # HTTP_STREAM_PREFIX = "http://192.168.108.238:82/live.flv?app=live&stream="
    RTMP_SERVER = "rtmp://127.0.0.1:1935/live/"
    HTTP_STREAM_PREFIX = "http://127.0.0.1:82/live.flv?app=live&stream="

    # 推流后端配置: "auto" / "gstreamer" / "ffmpeg"
    STREAM_BACKEND: str = "ffmpeg"
    # ffmpeg 可执行文件路径，默认按环境 PATH 搜索
    FFMPEG_PATH: str = "/usr/local/bin/ffmpeg"
    # 模型配置
    MODEL_PATH: str = "models"
    ALLOWED_EXTENSIONS: ClassVar[set] = {'mp4', 'jpg', 'gif', 'png', 'jpeg', 'avi'}

    # 上传配置
    MAX_CONTENT_LENGTH: int = 2000 * 1024 * 1024  # 2000MB
    CHUNK_SIZE: int = 1024 * 1024  # 1MB 分块大小
    UPLOAD_TIMEOUT: int = 3600  # 1小时超时

    # CORS 配置
    CORS_ORIGINS: List[str] = [
        "http://localhost",
        "http://localhost:80",
        "http://localhost:8080",
        "*"  # 开发环境允许所有源
    ]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = [
        "Content-Type",
        "Authorization",
        "Accept",
        "Origin",
        "X-Requested-With"
    ]

    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings() 
