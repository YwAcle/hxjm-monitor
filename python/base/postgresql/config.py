"""
PostgreSQL 数据库配置类
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class DBConfig:
    """数据库配置"""
    host: str = "192.168.108.238"
    port: int = 5432
    database: str = "postgres"
    user: str = "root"
    password: str = "123456"
    
    # 连接池配置
    # AI servers run in multiple worker processes. Eagerly opening ten
    # connections per process exhausts PostgreSQL before any event can persist.
    min_size: int = 1
    max_size: int = 5
    max_queries: int = 50000  # 每个连接最大查询数
    max_inactive_connection_lifetime: float = 300.0  # 非活跃连接最大生存时间（秒）
    
    # 超时配置
    timeout: float = 10.0  # 连接超时时间（秒）
    command_timeout: Optional[float] = 60.0  # 命令执行超时时间（秒）
    
    def __post_init__(self):
        """验证配置"""
        if self.min_size > self.max_size:
            raise ValueError("min_size 不能大于 max_size")
        if self.min_size < 1:
            raise ValueError("min_size 必须至少为 1")
    
    def get_dsn(self) -> str:
        """获取数据库连接字符串"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
    
    @classmethod
    def from_dict(cls, config_dict: dict) -> 'DBConfig':
        """从字典创建配置对象"""
        return cls(**{k: v for k, v in config_dict.items() if k in cls.__annotations__})
