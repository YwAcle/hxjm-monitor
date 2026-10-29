from typing import List, ClassVar
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    API_V1_STR: str = "/algPlatform"
    PROJECT_NAME: str = "智慧监控算法平台"

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
