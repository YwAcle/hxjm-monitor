"""
PostgreSQL 数据库会话保持类（同步版本）

提供完全同步（阻塞I/O）的数据库操作方法，使用 psycopg2
主要用于需要同步执行的场景，避免事件循环冲突
"""

import psycopg2
from psycopg2.extras import Json, register_default_json
from psycopg2.pool import SimpleConnectionPool
from typing import Dict, Any, Optional, List
from datetime import datetime
from uuid import uuid4
import logging
import json
from .config import DBConfig
import uuid
logger = logging.getLogger(__name__)

# 尝试导入 pgvector 支持（如果可用）
try:
    from pgvector.psycopg2 import register_vector
    PGVECTOR_AVAILABLE = True
except ImportError:
    PGVECTOR_AVAILABLE = False
    logger.warning("pgvector.psycopg2 不可用，将使用字符串格式处理 vector 类型")


class DBSessionSync:
    """
    数据库会话保持类（同步版本）
    
    使用 psycopg2 提供完全同步的数据库操作，避免事件循环冲突
    """
    
    def __init__(self, config: Optional[DBConfig] = None):
        """初始化数据库连接池"""
        self.config = config or DBConfig()
        self.pool: Optional[SimpleConnectionPool] = None
        self._initialized = False
    
    def initialize(self):
        """初始化连接池"""
        if self._initialized:
            logger.warning("数据库连接池已经初始化")
            return
        
        try:
            # 使用 psycopg2 创建连接池
            self.pool = SimpleConnectionPool(
                minconn=1,
                maxconn=10,
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.user,
                password=self.config.password,
                connect_timeout=int(self.config.timeout)
            )
            
            # 在每个连接上注册 pgvector（如果可用）
            # 注意：需要在每个连接上都注册，因为连接池可能使用不同的连接
            if PGVECTOR_AVAILABLE:
                logger.debug("pgvector 可用，将在连接使用时注册")
            
            self._initialized = True
            logger.info(f"同步数据库连接池初始化成功: {self.config.host}:{self.config.port}/{self.config.database}")
        except Exception as e:
            logger.error(f"初始化同步数据库连接池失败: {e}")
            self._initialized = False
            raise
    
    def close(self):
        """关闭连接池"""
        if self.pool:
            self.pool.closeall()
            self._initialized = False
            logger.info("同步数据库连接池已关闭")
    
    def _ensure_initialized(self):
        """确保连接池已初始化"""
        if not self._initialized or not self.pool:
            raise RuntimeError("数据库连接池未初始化，请先调用 initialize() 方法")
    
    def _preview(self, v: Any, n: int = 120) -> str:
        """打印值预览，避免日志太长"""
        if v is None:
            return "None"
        s = str(v)
        if len(s) > n:
            return s[:n] + f"...(len={len(s)})"
        return s
    import uuid

    def _adapt_value(self, val):
        if isinstance(val, uuid.UUID):
            return str(val)
        return val

    def _execute_insert_sync(self, table: str, data: Dict[str, Any]) -> Optional[str]:
        """
        执行插入操作（同步版本）
        
        Args:
            table: 表名
            data: 数据字典
            
        Returns:
            插入记录的ID（UUID字符串）
        """
        self._ensure_initialized()
        
        # 如果没有id，自动生成UUID（vad表使用bigserial自增，不需要UUID）
        if 'id' not in data and table != "vad":
            data['id'] = uuid4()
        
        # 如果没有created_at，自动添加当前时间
        if 'created_at' not in data and table != "episode":
            data['created_at'] = datetime.now()
        
        # 如果没有updated_at，自动添加当前时间
        if 'updated_at' not in data and table not in ["reid_match", "episode", "episode_tracklet_link", "episode_media_link", "vad"]:
            data['updated_at'] = datetime.now()
        
        # 构建SQL
        columns = list(data.keys())
        values = []
        
        # 处理值，将 dict/list 转换为 JSON，embedding 保持为 list（psycopg2 会自动处理）
        for col, val in data.items():
            if isinstance(val, (dict, list)):
                # 对于 embedding 字段（vector 类型），如果是 list，保持原样
                # psycopg2 配合 pgvector 会自动处理，如果没有 pgvector 则使用字符串格式
                if col == 'embedding' and isinstance(val, list):
                    # 对于 vector 类型，pgvector 会自动处理 list
                    # 如果有 pgvector 包，直接使用 list；否则需要使用字符串格式
                    if PGVECTOR_AVAILABLE:
                        values.append(val)  # pgvector 会自动处理
                    else:
                        # 如果没有 pgvector，使用字符串格式 '[1.0,2.0,3.0]'
                        # PostgreSQL vector 类型期望这种格式
                        vector_str = '[' + ','.join(str(float(v)) for v in val) + ']'
                        values.append(vector_str)
                else:
                    values.append(Json(val))
            else:
                values.append(val)
        
        # psycopg2 使用 %s 占位符，而不是 $1, $2 等
        placeholders = ['%s'] * len(values)
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(placeholders)}) RETURNING id"
        
        try:
            logger.debug(f"[INSERT SYNC] SQL={sql}")
            for i, (col, val) in enumerate(zip(columns, values), start=1):
                val_type = type(val).__name__
                extra = ""
                if isinstance(val, (str, bytes, bytearray)):
                    extra = f", len={len(val)}"
                logger.debug(f"[INSERT SYNC] param {i} col={col} type={val_type}{extra} val={self._preview(val)}")
            
            # 从连接池获取连接
            conn = self.pool.getconn()
            try:
                # 如果使用 pgvector，需要在连接上注册（每个连接都需要）
                if PGVECTOR_AVAILABLE:
                    try:
                        register_vector(conn)
                    except Exception:
                        pass  # 如果已经注册过，忽略错误
                
                cur = conn.cursor()
                adapted_values = [self._adapt_value(v) for v in values]
                cur.execute(sql, adapted_values)
                record_id = cur.fetchone()[0]
                conn.commit()
                logger.debug(f"成功插入 {table} 表，ID: {record_id}")
                return str(record_id)
            finally:
                # 归还连接到池
                self.pool.putconn(conn)
        except Exception as e:
            logger.error(f"插入 {table} 表失败: {e}")
            raise
    
    def insert_stranger_target_sync(self, status: str, embedding: List[float],
                                    embedding_model: str, is_active: bool = True,
                                    promoted_target_id: Optional[str] = None, **kwargs) -> str:
        """
        同步插入陌生人库记录（完全同步版本，使用 psycopg2）
        
        Args:
            status: 状态
            embedding: 特征向量（List[float]）
            embedding_model: 模型名称
            is_active: 是否激活
            promoted_target_id: 升级目标ID
            **kwargs: 其他字段（如 image_base64）
            
        Returns:
            插入记录的ID（UUID字符串）
        """
        data = {
            'status': status,
            'embedding': embedding,  # psycopg2 会自动处理 vector 类型
            'embedding_model': embedding_model,
            'is_active': is_active,
            'promoted_target_id': promoted_target_id,
            **kwargs
        }
        data = {k: v for k, v in data.items() if v is not None}
        return self._execute_insert_sync('stranger_target', data)
