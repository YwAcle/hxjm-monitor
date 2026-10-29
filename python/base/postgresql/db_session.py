"""
PostgreSQL 数据库会话保持类（异步版本）

提供每个表的数据增删改查功能，支持会话保持和直接传参调用
参考 db_client.py 和 config.py 的异步实现
"""

import asyncpg
import asyncio
from asyncpg.pool import Pool
from typing import Dict, Any, Optional, List
from datetime import datetime
from uuid import uuid4
import logging
import asyncio
from contextlib import asynccontextmanager
from pgvector.asyncpg import register_vector  # ✅ 新增
from .config import DBConfig
import re,json
logger = logging.getLogger(__name__)

MAX_LEN = 300  # 你想要的最大长度
class DBSession:
    """
    数据库会话保持类（异步版本）
    
    使用连接池保持数据库连接，为每个表提供增删改查方法
    支持直接传参调用，自动处理UUID和时间戳
    单例模式，全局共享连接池
    """
    
    _instance = None
    _lock = asyncio.Lock()
    
    def __new__(cls, config: Optional[DBConfig] = None):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super(DBSession, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, config: Optional[DBConfig] = None):
        """初始化数据库连接池（单例模式，首次调用时初始化）"""
        if hasattr(self, '_initialized'):
            logger.debug("数据库连接池已初始化，使用现有连接")
            return
        
        self.config = config or DBConfig()
        self.pool: Optional[Pool] = None
        self._initialized = False

    import asyncpg
    from pgvector.asyncpg import register_vector  # ✅ 新增

    async def initialize(self):
        """初始化连接池"""
        if self._initialized:
            logger.warning("数据库连接池已经初始化")
            return

        # ✅ 每个连接创建时自动注册 pgvector
        async def _init_conn(conn: asyncpg.Connection):
            # pgvector（如需）
            await register_vector(conn)

            # json/jsonb：让 asyncpg 接受 dict/list，并自动 dumps/loads
            await conn.set_type_codec(
                "json",
                encoder=lambda v: json.dumps(v, ensure_ascii=False, default=str),
                decoder=json.loads,
                schema="pg_catalog",
            )
            await conn.set_type_codec(
                "jsonb",
                encoder=lambda v: json.dumps(v, ensure_ascii=False, default=str),
                decoder=json.loads,
                schema="pg_catalog",
            )

        try:
            self.pool = await asyncpg.create_pool(
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.user,
                password=self.config.password,
                min_size=self.config.min_size,
                max_size=self.config.max_size,
                max_queries=self.config.max_queries,
                max_inactive_connection_lifetime=self.config.max_inactive_connection_lifetime,
                timeout=self.config.timeout,
                command_timeout=self.config.command_timeout,
                init=_init_conn,  # ✅ 新增这一行
            )
            self._initialized = True
            logger.info(f"数据库连接池初始化成功: {self.config.host}:{self.config.port}/{self.config.database}")
        except ModuleNotFoundError as e:
            # 如果没装 pgvector 会在 import 时报错（你也可以不加这个 except）
            logger.error("缺少依赖 pgvector，请先 pip install pgvector")
            self._initialized = False
            raise
        except Exception as e:
            logger.error(f"初始化数据库连接池失败: {e}")
            self._initialized = False
            raise

    async def close(self):
        """关闭连接池"""
        if self.pool:
            await self.pool.close()
            self._initialized = False
            logger.info("数据库连接池已关闭")
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close()
    
    def _ensure_initialized(self):
        """确保连接池已初始化"""
        if not self._initialized or not self.pool:
            raise RuntimeError("数据库连接池未初始化，请先调用 initialize() 方法")
    
    @asynccontextmanager
    async def acquire(self):
        """获取数据库连接"""
        self._ensure_initialized()
        async with self.pool.acquire() as connection:
            yield connection

    def _preview(self,v: Any, n: int = 120) -> str:
        """打印值预览，避免日志太长"""
        if v is None:
            return "None"
        s = str(v)
        if len(s) > n:
            return s[:n] + f"...(len={len(s)})"
        return s
    async def _execute_insert(self, table: str, data: Dict[str, Any]) -> Optional[str]:
        """
        执行插入操作
        
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
        if 'updated_at' not in data and table not in ["reid_match","episode","episode_tracklet_link","episode_media_link","vad"]: # reid_match 没有 更新字段，vad 也没有
            data['updated_at'] = datetime.now()
        
        # 构建SQL
        columns = list(data.keys())
        values = list(data.values())
        placeholders = [f"${i+1}" for i in range(len(values))]
        
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(placeholders)}) RETURNING id"

        try:
            logger.error("[INSERT] SQL=%s", sql)
            for i, (col, val) in enumerate(zip(columns, values), start=1):
                val_type = type(val).__name__
                extra = ""
                if isinstance(val, (str, bytes, bytearray)):
                    extra = f", len={len(val)}"
                logger.error("[INSERT] $%d col=%s type=%s%s val=%s", i, col, val_type, extra, self._preview(val))

            async with self.pool.acquire() as conn:
                record_id = await conn.fetchval(sql, *values)
                logger.debug(f"成功插入 {table} 表，ID: {record_id}")
                return str(record_id)
        except Exception as e:
            logger.error(f"插入 {table} 表失败: {e}")
            raise

    async def _execute_update(self, table: str, data: Dict[str, Any], where: str, *where_args) -> str:
        """
        执行更新操作

        Args:
            table: 表名
            data: 要更新的数据字典
            where: WHERE 条件（使用 $1, $2, ... 作为占位符）
            *where_args: WHERE 条件的参数

        Returns:
            执行结果状态字符串
        """
        self._ensure_initialized()

        if not data:
            raise ValueError("data 不能为空")

        if "updated_at" not in data:
            data["updated_at"] = datetime.now()

        set_clause = []
        values = []
        for i, (col, val) in enumerate(data.items(), start=1):
            set_clause.append(f"{col} = ${i}")
            values.append(val)

        offset = len(values)

        # 1) 先处理 '?' 占位符
        where_placeholders = where
        if "?" in where_placeholders:
            for j, arg in enumerate(where_args, start=offset + 1):
                where_placeholders = where_placeholders.replace("?", f"${j}", 1)
                values.append(arg)
        else:
            # 2) 处理 '$n' 占位符：整体加 offset
            def _shift(m):
                return f"${int(m.group(1)) + offset}"

            where_placeholders = re.sub(r"\$(\d+)", _shift, where_placeholders)
            values.extend(where_args)

        query = f"UPDATE {table} SET {', '.join(set_clause)} WHERE {where_placeholders}"

        logger.error("SQL=%s", (query[:MAX_LEN] + "…(truncated)") if len(query) > MAX_LEN else query)
        args_str = repr(values)
        logger.error("ARGS=%s", (args_str[:MAX_LEN] + "…(truncated)") if len(args_str) > MAX_LEN else args_str)


        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(query, *values)
                return result
        except Exception as e:
            logger.error(f"更新 {table} 表失败: {e}")
            raise
    
    async def _execute_delete(self, table: str, where: str, *where_args) -> str:
        """
        执行删除操作
        
        Args:
            table: 表名
            where: WHERE 条件（使用 $1, $2, ... 作为占位符）
            *where_args: WHERE 条件的参数
            
        Returns:
            执行结果状态字符串
        """
        self._ensure_initialized()
        
        query = f"DELETE FROM {table} WHERE {where}"
        
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(query, *where_args)
                return result
        except Exception as e:
            logger.error(f"删除 {table} 表失败: {e}")
            raise

    async def _execute_select(
            self,
            table: str,
            columns: str = "*",
            where: Optional[str] = None,
            *where_args,
            order_by: Optional[str] = None,
            limit: Optional[int] = None,
            offset: Optional[int] = None,
    ) -> List[asyncpg.Record]:
        """
        执行查询操作
        
        Args:
            table: 表名
            columns: 要查询的列（默认为 "*"）
            where: WHERE 条件（使用 $1, $2, ... 作为占位符）
            order_by: ORDER BY 子句
            limit: LIMIT 数量
            offset: OFFSET 数量
            *where_args: WHERE 条件的参数
            
        Returns:
            查询结果列表
        """
        self._ensure_initialized()

        query = f"SELECT {columns} FROM {table}"

        if where:
            query += f" WHERE {where}"

        if order_by:
            query += f" ORDER BY {order_by}"

        if limit is not None:
            query += f" LIMIT {limit}"

        if offset is not None:
            query += f" OFFSET {offset}"
        logger.error("SQL=%s", query)
        logger.error("ARGS=%s", where_args)

        try:
            async with self.pool.acquire() as conn:
                return await conn.fetch(query, *where_args)
        except Exception as e:
            logger.error(f"查询 {table} 表失败: {e}")
            raise
    
    # ==================== 各表的插入方法 ====================
    
    async def insert_camera(self, camera_code: str, name: str, location: Optional[str] = None,
                           vendor: Optional[str] = None, model: Optional[str] = None,
                           stream_uri: Optional[str] = None, timezone: Optional[str] = None,
                           calibration: Optional[Dict] = None, meta: Optional[Dict] = None,
                           **kwargs) -> str:
        """插入摄像头记录"""
        data = {
            'camera_code': camera_code,
            'name': name,
            'location': location,
            'vendor': vendor,
            'model': model,
            'stream_uri': stream_uri,
            'timezone': timezone,
            'calibration': calibration,
            'meta': meta,
            **kwargs
        }
        data = {k: v for k, v in data.items() if v is not None}
        return await self._execute_insert('camera', data)
    
    async def insert_camera_stream(self, camera_id: str, stream_name: str, task_type: str,
                                  shm_name: Optional[str] = None, zmq_addr: Optional[str] = None,
                                  is_active: bool = True, meta: Optional[Dict] = None,
                                  **kwargs) -> str:
        """插入流/任务实例记录"""
        data = {
            'camera_id': camera_id,
            'stream_name': stream_name,
            'task_type': task_type,
            'shm_name': shm_name,
            'zmq_addr': zmq_addr,
            'is_active': is_active,
            'meta': meta,
            **kwargs
        }
        data = {k: v for k, v in data.items() if v is not None}
        return await self._execute_insert('camera_stream', data)
    
    async def insert_media_asset(self, stream_id: str, asset_type: str, start_ts: datetime,
                                duration_ms: int, play_url: str, oss_bucket: Optional[str] = None,
                                oss_key: Optional[str] = None, content_type: Optional[str] = None,
                                meta: Optional[Dict] = None, **kwargs) -> str:
        """插入媒体索引记录"""
        data = {
            'stream_id': stream_id,
            'asset_type': asset_type,
            'start_ts': start_ts,
            'duration_ms': duration_ms,
            'play_url': play_url,
            'oss_bucket': oss_bucket,
            'oss_key': oss_key,
            'content_type': content_type,
            'meta': meta,
            **kwargs
        }
        data = {k: v for k, v in data.items() if v is not None}
        return await self._execute_insert('media_asset', data)
    
    async def insert_tracklet(self, stream_id: str, start_ts: datetime, cls_name: str = 'person',
                             end_ts: Optional[datetime] = None, color_rgb: Optional[int] = None,
                             query_asset_base64: Optional[str] = None, frame_asset_base64: Optional[str] = None,
                             gallery_target_id: Optional[str] = None,
                             gallery_similarity: Optional[float] = None, stranger_target_id: Optional[str] = None,
                             repr_embedding: Optional[List[float]] = None, embedding_model: Optional[str] = None,
                             trajectory_points: Optional[Dict] = None,
                             meta: Optional[Dict] = None, **kwargs) -> str:
        """插入轨迹记录"""
        data = {
            'stream_id': stream_id,
            'start_ts': start_ts,
            'cls_name': cls_name,
            'end_ts': end_ts,
            'color_rgb': color_rgb,
            'query_asset_base64': query_asset_base64,
            'frame_asset_base64': frame_asset_base64,
            'gallery_target_id': gallery_target_id,
            'gallery_similarity': gallery_similarity,
            'stranger_target_id': stranger_target_id,
            'repr_embedding': repr_embedding,
            'embedding_model': embedding_model,
            'trajectory_points': trajectory_points,
            'meta': meta,
            **kwargs
        }
        data = {k: v for k, v in data.items() if v is not None}
        return await self._execute_insert('tracklet', data)
    
    async def insert_reid_target(self, name: str, embedding: List[float], embedding_model: str,
                                employee_id: Optional[str] = None, source_asset_id: Optional[str] = None,
                                image_base64: Optional[str] = None, is_active: bool = True, **kwargs) -> str:
        """插入内部人员库记录"""
        data = {
            'name': name,
            'embedding': embedding,
            'embedding_model': embedding_model,
            'employee_id': employee_id,
            'source_asset_id': source_asset_id,
            'image_base64': image_base64,
            'is_active': is_active,
            **kwargs
        }
        data = {k: v for k, v in data.items() if v is not None}
        return await self._execute_insert('reid_target', data)
    
    async def insert_stranger_target(self, code: str, status: str, embedding: List[float],
                                    embedding_model: str, is_active: bool = True,
                                    promoted_target_id: Optional[str] = None, **kwargs) -> str:
        """插入陌生人库记录"""
        data = {
            'code': code,
            'status': status,
            'embedding': embedding,
            'embedding_model': embedding_model,
            'is_active': is_active,
            'promoted_target_id': promoted_target_id,
            **kwargs
        }
        data = {k: v for k, v in data.items() if v is not None}
        return await self._execute_insert('stranger_target', data)
    
    async def insert_reid_match(self, tracklet_id: str, ts: datetime, similarity: float,
                               threshold: float, matched: bool, target_id: Optional[str] = None,
                               stranger_target_id: Optional[str] = None, query_asset_base64: Optional[str] = None,
                               evidence_asset_base64: Optional[str] = None, meta: Optional[Dict] = None,
                               **kwargs) -> str:
        """插入ReID匹配结果记录"""
        data = {
            'tracklet_id': tracklet_id,
            'ts': ts,
            'similarity': similarity,
            'threshold': threshold,
            'matched': matched,
            'target_id': target_id,
            'stranger_target_id': stranger_target_id,
            'query_asset_base64': query_asset_base64,
            'evidence_asset_base64': evidence_asset_base64,
            'meta': meta,
            **kwargs
        }
        data = {k: v for k, v in data.items() if v is not None}
        return await self._execute_insert('reid_match', data)
    
    async def insert_episode(self, start_ts: datetime,
                            end_ts: Optional[datetime] = None, title: Optional[str] = None,
                            target_id: Optional[str] = None, stranger_target_id: Optional[str] = None,
                            meta: Optional[Dict] = None, **kwargs) -> str:
        """插入事件容器记录"""
        data = {
            'start_ts': start_ts,
            'end_ts': end_ts,
            'title': title,
            'target_id': target_id,
            'stranger_target_id': stranger_target_id,
            'meta': meta,
            **kwargs
        }
        data = {k: v for k, v in data.items() if v is not None}
        return await self._execute_insert('episode', data)
    
    async def insert_episode_tracklet_link(self, episode_id: str, tracklet_id: str,
                                          note: Optional[str] = None, **kwargs) -> str:
        """插入Episode-Tracklet关联记录"""
        data = {
            'episode_id': episode_id,
            'tracklet_id': tracklet_id,
            'note': note,
            **kwargs
        }
        data = {k: v for k, v in data.items() if v is not None}
        return await self._execute_insert('episode_tracklet_link', data)
    
    async def insert_episode_media_link(self, episode_id: str, media_asset_id: str,
                                       note: Optional[str] = None, **kwargs) -> str:
        """插入Episode-Media关联记录"""
        data = {
            'episode_id': episode_id,
            'media_asset_id': media_asset_id,
            'note': note,
            **kwargs
        }
        data = {k: v for k, v in data.items() if v is not None}
        return await self._execute_insert('episode_media_link', data)
    
    async def insert_llm_report(self, episode_id: str, report_json: Dict, prompt_version: Optional[str] = None,
                               report_text: Optional[str] = None, **kwargs) -> str:
        """插入LLM报告记录"""
        data = {
            'episode_id': episode_id,
            'report_json': report_json,
            'prompt_version': prompt_version,
            'report_text': report_text,
            **kwargs
        }
        data = {k: v for k, v in data.items() if v is not None}
        return await self._execute_insert('llm_report', data)
    
    async def insert_vad(self, media_asset_id: str, stream_id: str, frame_vad_base64: Optional[str] = None, 
                         anomaly_name: Optional[str] = None, anomaly_level: Optional[int] = None, **kwargs) -> str:
        """插入VAD记录
        
        Args:
            media_asset_id: 媒体资产ID
            stream_id: 流ID
            frame_vad_base64: 帧级VAD结果（base64字符串）
            anomaly_name: 异常名称（如 'fall' / 'fight' / 'intrusion'）
            anomaly_level: 异常等级（1~4，数值越大越严重）
                - 1: ROI区域停留
                - 2: 跌倒
                - 3: 打架
                - 4: 火灾/烟雾
            **kwargs: 其他字段
        """
        data = {
            'media_asset_id': media_asset_id,
            'stream_id': stream_id,
            'frame_vad_base64': frame_vad_base64,
            'anomaly_name': anomaly_name,
            'anomaly_level': anomaly_level,
            **kwargs
        }
        data = {k: v for k, v in data.items() if v is not None}
        return await self._execute_insert('vad', data)
    
    # ==================== 各表的查询方法 ====================

    async def select_reid_target(
            self,
            where: Optional[str] = None,
            is_active: bool = True,
            *where_args
    ) -> List[asyncpg.Record]:
        if where:
            where_clause = f"({where}) AND is_active = ${len(where_args) + 1}"
            return await self._execute_select("reid_target", "*", where_clause, *where_args, is_active)
        else:
            return await self._execute_select("reid_target", "*", "is_active = $1", is_active)

    async def select_stranger_target(
            self,
            where: Optional[str] = None,
            is_active: bool = True,
            *where_args
    ) -> List[asyncpg.Record]:
        if where:
            where_clause = f"({where}) AND is_active = ${len(where_args) + 1}"
            return await self._execute_select("stranger_target", "*", where_clause, *where_args, is_active)
        else:
            return await self._execute_select("stranger_target", "*", "is_active = $1", is_active)

    async def select_tracklet(
            self,
            where: Optional[str] = None,
            *where_args,
            order_by: Optional[str] = None,
            limit: Optional[int] = None,
            offset: Optional[int] = None
    ) -> List[asyncpg.Record]:
        """查询轨迹记录"""
        if where:
            return await self._execute_select("tracklet", "*", where, *where_args, order_by=order_by, limit=limit, offset=offset)
        else:
            return await self._execute_select("tracklet", "*", order_by=order_by, limit=limit, offset=offset)

    async def select_vad(
            self,
            where: Optional[str] = None,
            *where_args,
            order_by: Optional[str] = None,
            limit: Optional[int] = None,
            offset: Optional[int] = None
    ) -> List[asyncpg.Record]:
        """查询VAD记录"""
        if where:
            return await self._execute_select("vad", "*", where, *where_args, order_by=order_by, limit=limit, offset=offset)
        else:
            return await self._execute_select("vad", "*", order_by=order_by, limit=limit, offset=offset)

    async def select_episode(
            self,
            where: Optional[str] = None,
            *where_args,
            order_by: Optional[str] = None,
            limit: Optional[int] = None,
            offset: Optional[int] = None
    ) -> List[asyncpg.Record]:
        """查询Episode记录"""
        if where:
            return await self._execute_select("episode", "*", where, *where_args, order_by=order_by, limit=limit, offset=offset)
        else:
            return await self._execute_select("episode", "*", order_by=order_by, limit=limit, offset=offset)

    async def select_media_asset_by_timestamp(self, timestamp: datetime) -> Optional[asyncpg.Record]:
        """
        根据时间戳查询media_asset，返回最接近但小于给定时间的记录的id
        
        Args:
            timestamp: 查询时间戳
            
        Returns:
            最接近但小于给定时间的media_asset记录的id，如果没有找到则返回None
        """
        records = await self._execute_select(
            "media_asset",
            "id",
            "start_ts <= $1",
            timestamp,
            order_by="start_ts DESC",
            limit=1
        )
        if records and len(records) > 0:
            return records[0]
        return None

    async def select_media_asset_for_event(self, recording_stream_id: str,
                                           event_ts: datetime) -> Optional[asyncpg.Record]:
        """Return the recording segment from one stream that covers an event."""
        if not recording_stream_id or event_ts is None:
            return None
        records = await self._execute_select(
            "media_asset",
            "id, stream_id, start_ts, duration_ms, play_url",
            "stream_id = $1 AND start_ts <= $2 "
            "AND $2 < start_ts + (duration_ms * interval '1 millisecond')",
            recording_stream_id,
            event_ts,
            order_by="start_ts DESC",
            limit=1
        )
        if records and len(records) > 0:
            return records[0]
        return None

    async def get_max_stranger_code(self) -> int:
        """
        获取stranger_target表中最大的code编号
        
        Returns:
            最大的code编号（数字部分），如果没有记录则返回0
            例如：如果code为"STR-000123"，则返回123
        """
        try:
            # 查询所有code字段
            records = await self._execute_select("stranger_target", "code")
            
            if not records or len(records) == 0:
                return 0
            
            max_code_num = 0
            for record in records:
                code = record.get('code', '')
                if code and code.startswith('STR-'):
                    try:
                        # 提取"STR-"后面的数字部分
                        code_num_str = code[4:]  # 跳过"STR-"
                        code_num = int(code_num_str)
                        max_code_num = max(max_code_num, code_num)
                    except (ValueError, IndexError):
                        # 如果code格式不正确，跳过
                        continue
            
            return max_code_num
        except Exception as e:
            logger.error(f"获取最大stranger code失败: {e}")
            # 如果查询失败，返回0，让调用者从1开始
            return 0

    # ==================== 各表的更新方法 ====================

    async def update_stranger_target(self, stranger_id: str, **kwargs) -> str:
        """更新陌生人库记录"""
        return await self._execute_update('stranger_target', kwargs, "id = $1", stranger_id)

    async def update_reid_target(self, target_id: str, **kwargs) -> str:
        """更新内部人员库记录"""
        return await self._execute_update('reid_target', kwargs, "id = $1", target_id)

    async def update_tracklet(self, tracklet_id: str, **kwargs) -> str:
        """更新轨迹记录"""
        return await self._execute_update('tracklet', kwargs, "id = $1", tracklet_id)
    
    async def update_vad(self, vad_id: str, **kwargs) -> str:
        """更新VAD记录"""
        return await self._execute_update('vad', kwargs, "id = $1", vad_id)
    
    # ==================== 各表的删除方法 ====================
    
    async def delete_stranger_target(self, stranger_id: str) -> str:
        """删除陌生人库记录（软删除，设置is_active=False）"""
        return await self.update_stranger_target(stranger_id, is_active=False)
    
    async def delete_reid_target(self, target_id: str) -> str:
        """删除内部人员库记录（软删除，设置is_active=False）"""
        return await self.update_reid_target(target_id, is_active=False)

    async def delete_tracklet(self, tracklet_id: str) -> str:
        """删除轨迹记录（硬删除）"""
        return await self._execute_delete('tracklet', "id = $1", tracklet_id)
    
    async def delete_vad(self, vad_id: str) -> str:
        """删除VAD记录（硬删除）"""
        return await self._execute_delete('vad', "id = $1", vad_id)
