#!/usr/bin/env python3
"""
向 camera 表插入一条记录

使用方法：
1. 修改下面的字段值
2. 运行脚本：python insert_camera.py
3. 需要插入多条记录时，修改字段值后再次运行
"""

import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from base.postgresql.db_session import DBSession
from base.postgresql.config import DBConfig

# ==================== 在这里修改字段值 ====================

# 必填字段
CAMERA_CODE = "CAM04"  # 设备编号/通道号（必须唯一）
NAME = "摄像头4"  # 显示名称

# 可选字段（如果不需要，设置为 None）
LOCATION = "大厅门口"  # 位置描述
VENDOR = "海康威视"  # 设备厂商
MODEL = ""  # 型号
STREAM_URI = "rtsp://admin:hxjm2025@192.168.118.148:554/Streaming/Channels/101"  # RTSP/WEBRTC 源地址
TIMEZONE = "Asia/Singapore"  # 时区

# JSONB 字段（如果不需要，设置为 None）
CALIBRATION = {
    "world_x": 0.0,
    "world_y": 0.0
}  # 标定/映射参数

META = {
    "resolution": "1270x720",
}  # 其他扩展信息

# =========================================================


async def main():
    """主函数"""
    # 创建数据库配置（使用默认配置，如需修改请参考 config.py）
    config = DBConfig()
    
    # 创建数据库会话
    db = DBSession(config)
    
    try:
        # 初始化数据库连接
        await db.initialize()
        print(f"✓ 数据库连接成功: {config.host}:{config.port}/{config.database}")
        
        # 插入摄像头记录
        print(f"\n正在插入摄像头记录...")
        print(f"  camera_code: {CAMERA_CODE}")
        print(f"  name: {NAME}")
        if LOCATION:
            print(f"  location: {LOCATION}")
        if VENDOR:
            print(f"  vendor: {VENDOR}")
        if MODEL:
            print(f"  model: {MODEL}")
        if STREAM_URI:
            print(f"  stream_uri: {STREAM_URI}")
        if TIMEZONE:
            print(f"  timezone: {TIMEZONE}")
        if CALIBRATION:
            print(f"  calibration: {CALIBRATION}")
        if META:
            print(f"  meta: {META}")
        
        camera_id = await db.insert_camera(
            camera_code=CAMERA_CODE,
            name=NAME,
            location=LOCATION,
            vendor=VENDOR,
            model=MODEL,
            stream_uri=STREAM_URI,
            timezone=TIMEZONE,
            calibration=CALIBRATION,
            meta=META
        )
        
        print(f"\n✓ 插入成功！摄像头ID: {camera_id}")
        print(f"  如需插入更多记录，请修改字段值后再次运行此脚本。")
        
    except Exception as e:
        print(f"\n✗ 插入失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        # 关闭数据库连接
        await db.close()
        print(f"\n✓ 数据库连接已关闭")


if __name__ == "__main__":
    asyncio.run(main())


