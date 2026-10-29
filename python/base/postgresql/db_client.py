"""
PostgreSQL 异步数据库客户端（基础组件）

提供连接池管理和基础的增删改查操作
支持传入 SQL 语句进行异步处理
"""

import logging
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

import asyncpg
from asyncpg.pool import Pool

from .config import DBConfig


logger = logging.getLogger(__name__)


class PostgreSQLClient:
    """PostgreSQL 异步客户端（基础组件）
    
    提供：
    - 连接池管理
    - 基础 SQL 执行（execute、fetch、fetchrow、fetchval）
    - 基础 CRUD 操作（insert、update、delete、select）
    - 事务支持
    """
    
    def __init__(self, config: DBConfig):
        """初始化客户端
        
        Args:
            config: 数据库配置对象
        """
        self.config = config
        self.pool: Optional[Pool] = None
        self._initialized = False
    
    async def initialize(self):
        """初始化连接池"""
        if self._initialized:
            logger.warning("数据库连接池已经初始化")
            return
        
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
            )
            self._initialized = True
            logger.info(f"PostgreSQL 连接池初始化成功: {self.config.host}:{self.config.port}/{self.config.database}")
        except Exception as e:
            logger.error(f"初始化 PostgreSQL 连接池失败: {e}")
            raise
    
    async def close(self):
        """关闭连接池"""
        if self.pool:
            await self.pool.close()
            self._initialized = False
            logger.info("PostgreSQL 连接池已关闭")
    
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
        """获取数据库连接
        
        使用示例:
            async with client.acquire() as conn:
                result = await conn.fetch("SELECT * FROM users")
        """
        self._ensure_initialized()
        async with self.pool.acquire() as connection:
            yield connection
    
    # ==================== 核心 SQL 执行方法 ====================
    
    async def execute(self, query: str, *args, timeout: Optional[float] = None) -> str:
        """执行 SQL 语句（INSERT, UPDATE, DELETE, CREATE 等）
        
        Args:
            query: SQL 语句（支持参数化查询，使用 $1, $2, ... 作为占位符）
            *args: 查询参数
            timeout: 超时时间（秒）
            
        Returns:
            执行结果状态字符串（如 "INSERT 0 1"）
            
        Example:
            await client.execute("INSERT INTO users (name, age) VALUES ($1, $2)", "张三", 25)
        """
        self._ensure_initialized()
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(query, *args, timeout=timeout)
                return result
        except Exception as e:
            logger.error(f"执行 SQL 失败: {query[:100]}... 错误: {e}")
            raise
    
    async def fetch(self, query: str, *args, timeout: Optional[float] = None) -> List[asyncpg.Record]:
        """查询多行数据
        
        Args:
            query: SQL 查询语句（支持参数化查询）
            *args: 查询参数
            timeout: 超时时间（秒）
            
        Returns:
            查询结果列表（asyncpg.Record 对象列表）
            
        Example:
            rows = await client.fetch("SELECT * FROM users WHERE age > $1", 18)
            for row in rows:
                print(dict(row))
        """
        self._ensure_initialized()
        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetch(query, *args, timeout=timeout)
                return result
        except Exception as e:
            logger.error(f"查询失败: {query[:100]}... 错误: {e}")
            raise
    
    async def fetchrow(self, query: str, *args, timeout: Optional[float] = None) -> Optional[asyncpg.Record]:
        """查询单行数据
        
        Args:
            query: SQL 查询语句（支持参数化查询）
            *args: 查询参数
            timeout: 超时时间（秒）
            
        Returns:
            查询结果（单行，asyncpg.Record 对象）或 None
            
        Example:
            row = await client.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
            if row:
                print(dict(row))
        """
        self._ensure_initialized()
        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchrow(query, *args, timeout=timeout)
                return result
        except Exception as e:
            logger.error(f"查询单行失败: {query[:100]}... 错误: {e}")
            raise
    
    async def fetchval(self, query: str, *args, column: int = 0, timeout: Optional[float] = None) -> Any:
        """查询单个值
        
        Args:
            query: SQL 查询语句（支持参数化查询）
            *args: 查询参数
            column: 列索引（默认 0，即第一列）
            timeout: 超时时间（秒）
            
        Returns:
            查询结果（单个值）
            
        Example:
            count = await client.fetchval("SELECT COUNT(*) FROM users")
            user_id = await client.fetchval("SELECT id FROM users WHERE name = $1", "张三")
        """
        self._ensure_initialized()
        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchval(query, *args, column=column, timeout=timeout)
                return result
        except Exception as e:
            logger.error(f"查询单值失败: {query[:100]}... 错误: {e}")
            raise
    
    # ==================== 基础 CRUD 操作（便捷方法） ====================
    
    async def insert(self, table: str, data: Dict[str, Any], returning: Optional[str] = None) -> Optional[Any]:
        """插入单条数据
        
        Args:
            table: 表名
            data: 要插入的数据字典
            returning: 返回的字段（如 "id"），如果指定则返回该字段的值
            
        Returns:
            如果指定了 returning，返回相应的值；否则返回 None
            
        Example:
            user_id = await client.insert("users", {"name": "张三", "age": 25}, returning="id")
        """
        if not data:
            raise ValueError("data 不能为空")
        
        columns = list(data.keys())
        values = list(data.values())
        placeholders = [f"${i+1}" for i in range(len(values))]
        
        query = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
        
        if returning:
            query += f" RETURNING {returning}"
            return await self.fetchval(query, *values)
        else:
            await self.execute(query, *values)
            return None
    
    async def insert_many(self, table: str, data_list: List[Dict[str, Any]]) -> int:
        """批量插入数据（高性能，使用 COPY 协议）
        
        Args:
            table: 表名
            data_list: 要插入的数据列表（所有字典必须有相同的键）
            
        Returns:
            插入的行数
            
        Example:
            data_list = [
                {"name": "张三", "age": 25},
                {"name": "李四", "age": 30}
            ]
            count = await client.insert_many("users", data_list)
        """
        if not data_list:
            return 0
        
        # 获取列名（假设所有数据的列相同）
        columns = list(data_list[0].keys())
        
        # 准备数据
        values = [[row[col] for col in columns] for row in data_list]
        
        # 使用 COPY 进行批量插入（最快的方式）
        async with self.pool.acquire() as conn:
            try:
                result = await conn.copy_records_to_table(
                    table,
                    records=values,
                    columns=columns
                )
                # result 格式为 "COPY N"，提取插入的行数
                count = int(result.split()[-1]) if result else len(data_list)
                logger.debug(f"批量插入 {count} 条数据到表 {table}")
                return count
            except Exception as e:
                logger.error(f"批量插入失败: {e}")
                raise
    
    async def update(self, table: str, data: Dict[str, Any], where: str, *where_args) -> str:
        """更新数据
        
        Args:
            table: 表名
            data: 要更新的数据字典
            where: WHERE 条件（不包含 WHERE 关键字，使用 $1, $2, ... 作为占位符）
            *where_args: WHERE 条件的参数
            
        Returns:
            执行结果状态字符串
            
        Example:
            await client.update(
                "users", 
                {"age": 26}, 
                "id = $1", 
                user_id
            )
        """
        if not data:
            raise ValueError("data 不能为空")
        
        set_clause = []
        values = []
        for i, (col, val) in enumerate(data.items(), start=1):
            set_clause.append(f"{col} = ${i}")
            values.append(val)
        
        # WHERE 参数的占位符从 len(data) + 1 开始
        where_placeholders = where
        for i, arg in enumerate(where_args, start=len(data) + 1):
            where_placeholders = where_placeholders.replace('?', f'${i}', 1)
            values.append(arg)
        
        query = f"UPDATE {table} SET {', '.join(set_clause)} WHERE {where_placeholders}"
        return await self.execute(query, *values)
    
    async def delete(self, table: str, where: str, *where_args) -> str:
        """删除数据
        
        Args:
            table: 表名
            where: WHERE 条件（不包含 WHERE 关键字，使用 $1, $2, ... 作为占位符）
            *where_args: WHERE 条件的参数
            
        Returns:
            执行结果状态字符串
            
        Example:
            await client.delete("users", "id = $1", user_id)
        """
        query = f"DELETE FROM {table} WHERE {where}"
        return await self.execute(query, *where_args)
    
    async def select(
        self, 
        table: str, 
        columns: str = "*",
        where: Optional[str] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        *where_args
    ) -> List[asyncpg.Record]:
        """查询数据（便捷方法）
        
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
            
        Example:
            rows = await client.select(
                "users",
                where="age > $1",
                order_by="created_at DESC",
                limit=10,
                18
            )
        """
        query = f"SELECT {columns} FROM {table}"
        
        if where:
            query += f" WHERE {where}"
        
        if order_by:
            query += f" ORDER BY {order_by}"
        
        if limit:
            query += f" LIMIT {limit}"
        
        if offset:
            query += f" OFFSET {offset}"
        
        return await self.fetch(query, *where_args)
    
    # ==================== 事务操作 ====================
    
    @asynccontextmanager
    async def transaction(self):
        """创建事务上下文
        
        使用示例:
            async with client.transaction() as conn:
                await conn.execute("INSERT INTO users ...")
                await conn.execute("UPDATE accounts ...")
                # 自动提交，如果出错则回滚
        
        注意：事务内的 conn 是 asyncpg.Connection 对象，可以直接使用其方法
        """
        self._ensure_initialized()
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                yield conn
    
    # ==================== 连接池信息 ====================
    
    async def get_connection_stats(self) -> Dict[str, int]:
        """获取连接池统计信息
        
        Returns:
            连接池统计信息字典
        """
        self._ensure_initialized()
        return {
            'size': self.pool.get_size(),
            'free': self.pool.get_idle_size(),
            'min_size': self.pool.get_min_size(),
            'max_size': self.pool.get_max_size(),
        }
