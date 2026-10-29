# -*- coding: utf-8 -*-
"""
向 tracklet 表添加轨迹数据

使用方法：
python add_trajectory.py
"""

import os
import sys
import cv2
import base64
import random
import asyncio
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

# 添加模块路径 (上级目录)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from base.postgresql.db_session import DBSession
from base.postgresql.config import DBConfig
# ------------------------------------------------------------------
# 朦姐命令： python add_trajectory.py --image_path ./frame/zym/image.png --cream 2 --flag 1 

# 我的命令： python add_trajectory.py --image_path ./frame/zjh/image.png --cream 2 --flag 1 
# 如果重新新增了特征，就需要更新下这个
TRAGERT_DICT = {   
    "df794f6e-b10a-47f2-828b-b8f2397aaf2d":"冷佳旭",
    "293ababf-1e58-433d-9f97-6a336c3197e0":"李昆鸿",
    "38c10d0d-5638-4222-abe3-824e6fe61688":"李爽"
}

def get_target_info_by_flag(flag: int) -> tuple: 
    """
    根据FLAGE获取目标人物信息
    
    Args:
        flag: 目标人物标识 (1=冷佳旭, 2=李昆鸿, 其他=李爽)
        
    Returns:
        (target_id, target_name) 元组
    """
    if flag == 1:
        target_id = "df794f6e-b10a-47f2-828b-b8f2397aaf2d"
        target_name = "冷佳旭"
    elif flag == 2:
        target_id = "293ababf-1e58-433d-9f97-6a336c3197e0"
        target_name = "李昆鸿"
    else:
        target_id = "38c10d0d-5638-4222-abe3-824e6fe61688"
        target_name = "李爽"
    return target_id, target_name

def print_parameter_info(flag: int, cream: int, image_path: str):
    """
    打印参数含义，让用户理解每个参数对应的值
    
    Args:
        flag: 目标人物标识
        cream: 摄像头编号
        image_path: 图片路径
    """
    target_id, target_name = get_target_info_by_flag(flag)
    stream_id = f"live/camera_{cream}_boxmot"
    
    print("\n" + "=" * 60)
    print("参数说明")
    print("=" * 60)
    print(f"FLAGE = {flag}")
    print(f"  └─> 对应目标人物: {target_name}")
    print(f"  └─> UUID: {target_id}")
    print()
    print(f"CREAM = {cream}")
    print(f"  └─> 摄像头编号: {cream}")
    print(f"  └─> 生成的 stream_id: {stream_id}")
    print()
    print(f"IMAGE_PATH = {image_path}")
    print(f"  └─> 图片文件路径（用于 frame_asset_base64）")
    print("=" * 60 + "\n")
# ------------------------------------------------------------------
def random_bright_color_rgb(min_v: int = 80) -> list[int]:
    """生成随机明亮的RGB颜色"""
    return [random.randint(min_v, 255), random.randint(min_v, 255), random.randint(min_v, 255)]


def add_random_offset_to_points(points: list) -> list:
    """
    对轨迹点中的x和y值进行随机加减70~150以内的随机小数
    
    Args:
        points: 轨迹点列表，每个点包含 "x", "y", "ts" 字段
        
    Returns:
        修改后的轨迹点列表
    """
    modified_points = []
    for point in points:
        # 生成70~150之间的随机小数
        offset_x = random.uniform(70, 150)
        offset_y = random.uniform(70, 150)
        
        # 随机决定是加还是减（50%概率）
        sign_x = random.choice([-1, 1])
        sign_y = random.choice([-1, 1])
        
        # 应用随机偏移
        new_point = {
            "x": point["x"] + sign_x * offset_x,
            "y": point["y"] + sign_y * offset_y,
            "ts": point["ts"]  # 时间戳保持不变
        }
        modified_points.append(new_point)
    
    return modified_points


def image_to_base64(image_path: str) -> str:
    """
    将图片转换为base64字符串
    
    Args:
        image_path: 图片文件路径
        
    Returns:
        base64编码的字符串
    """
    img_bgr = cv2.imread(image_path)
    if img_bgr is None:
        raise ValueError(f"无法读取图片: {image_path}")
    
    # 编码为base64
    success, buffer = cv2.imencode('.jpg', img_bgr)
    if not success:
        raise ValueError(f"无法编码图片: {image_path}")
    image_base64 = base64.b64encode(buffer).decode('utf-8')
    return image_base64


async def add_trajectory(flag: int, cream: int, image_path: str):
    """
    添加轨迹数据到数据库
    
    Args:
        flag: 目标人物标识 (1=冷佳旭, 2=李昆鸿, 其他=李爽)
        cream: 摄像头编号
        image_path: 图片文件路径
    """
    # 获取目标人物信息
    target_id, target_name = get_target_info_by_flag(flag)
    stream_id = f"live/camera_{cream}_boxmot"
    
    # 初始化数据库连接配置
    print("[INIT] 初始化数据库连接配置...")
    db_config = DBConfig(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "123456")
    )
    db = DBSession(config=db_config)
    
    # 初始化数据库连接池
    print("[INIT] 初始化数据库连接池...")
    await db.initialize()
    print("[INIT] 初始化完成\n")
    
    try:
        # 准备数据
        # 注意：id字段由数据库自动生成，不需要手动指定
        end_ts = datetime.now()  # 当前时间
        start_ts = end_ts - timedelta(seconds=8)  # end_ts - 10秒
        cls_name = "person"
        color_rgb = random_bright_color_rgb()  # 例如 [185, 124, 226]
        gallery_target_id = target_id
        gallery_similarity = 0.85
        embedding_model = "ResNet50"
        stream_2_points_original = [
                {
                    "x": 915.1,
                    "y": 1452.5,
                    "ts": start_ts.isoformat()
                },
                {
                    "x": 1485.6,
                    "y": 1395.7,
                    "ts": end_ts.isoformat()
                }
            ]
        stream_4_points_original = [
                {
                    "x": 351.1,
                    "y": 1935.5,
                    "ts": start_ts.isoformat()
                },
                {
                    "x": 978.6,
                    "y": 542.6,
                    "ts": (start_ts + timedelta(seconds=1)).isoformat()
                },
                {
                    "x": 1476.2,
                    "y": 905.1,
                    "ts": (start_ts + timedelta(seconds=2)).isoformat()
                },
                {
                    "x": 1785.6,
                    "y": 1395.7,
                    "ts": end_ts.isoformat()
                }
            ]
        
        # 对轨迹点应用随机偏移
        stream_2_points = add_random_offset_to_points(stream_2_points_original)
        stream_4_points = add_random_offset_to_points(stream_4_points_original)
        
        # 读取frame_start图片并转换为base64
        frame_start_path = Path(image_path)
        if not frame_start_path.exists():
            raise FileNotFoundError(f"找不到frame_start图片文件: {frame_start_path}")
        
        frame_asset_base64 = image_to_base64(str(frame_start_path))
        print(f"[处理] 已读取frame_start图片: {frame_start_path}")
        
        # 构建trajectory_points
        trajectory_points = {
            "points": stream_2_points if cream == 2 else stream_4_points
        }
        
        # 构建meta数据（参考server.py:1688-1699）
        # 从stream_id中提取camera编号
        camera = stream_id.split('/')[-1].replace('_boxmot', '').replace('camera_', '') if '/' in stream_id else "1"
        
        meta = {
            'camera': camera,  # 从stream_id中提取的真实camera编号
            'stream_id': stream_id,
            'media_asset_id': None,  # media_asset_id列表，这里设为None
            'stream_task': os.getenv("REID_ZMQ_ADDR", "ipc:///tmp/py_ai_boxmot.ipc"),  # 流任务
            'start_ts': start_ts.isoformat() if isinstance(start_ts, datetime) else str(start_ts),
            'end_ts': end_ts.isoformat() if isinstance(end_ts, datetime) else str(end_ts),
            'person_name': target_name,  
            'person_image': None,  # query_asset_base64为None
            'trajectory_points': trajectory_points,  # 轨迹序列
            'trajectory_color': color_rgb  # 轨迹线条颜色
        }
        
        # 插入轨迹记录
        print(f"[处理] 正在插入轨迹记录...")
        print(f"  - stream_id: {stream_id}")
        print(f"  - start_ts: {start_ts}")
        print(f"  - end_ts: {end_ts}")
        print(f"  - color_rgb: {color_rgb}")
        print(f"  - gallery_target_id: {gallery_target_id}")
        print(f"  - gallery_similarity: {gallery_similarity}")
        print(f"  - embedding_model: {embedding_model}")
        
        inserted_tracklet_id = await db.insert_tracklet(
            stream_id=stream_id,
            start_ts=start_ts,
            end_ts=end_ts,
            cls_name=cls_name,
            color_rgb=color_rgb,
            query_asset_base64=None,
            frame_asset_base64=frame_asset_base64,
            frame_end_base64=None,  # 通过kwargs传递
            gallery_target_id=gallery_target_id,
            gallery_similarity=gallery_similarity,
            stranger_target_id=None,
            repr_embedding=None,
            embedding_model=embedding_model,
            trajectory_points=trajectory_points,
            meta=meta
        )
        
        print(f"\n[成功] 已插入轨迹记录，ID: {inserted_tracklet_id}")
        
        # 插入 episode 表
        print(f"\n[处理] 正在插入 episode 记录...")
        episode_id = str(uuid4())  # 随机生成uuid
        
        inserted_episode_id = await db.insert_episode(
            id=episode_id,  # 手动指定id
            start_ts=start_ts,  # 复用tracklet的start_ts
            end_ts=end_ts,  # 复用tracklet的end_ts
            title=None,
            target_id=gallery_target_id,  # 复用tracklet的gallery_target_id
            stranger_target_id=None,
            meta=meta
        )
        
        print(f"[成功] 已插入 episode 记录，ID: {inserted_episode_id}")
        print(f"       (使用随机生成的UUID: {episode_id})")
        
        # 创建 episode_tracklet_link 关联记录（可选，但建议创建以建立关联）
        print(f"\n[处理] 正在创建 episode_tracklet_link 关联记录...")
        link_id = await db.insert_episode_tracklet_link(
            episode_id=inserted_episode_id,
            tracklet_id=inserted_tracklet_id,
            note=None
        )
        print(f"[成功] 已创建关联记录，link_id: {link_id}")
        print(f"  - stream_id: {stream_id}")
        print(f"  - start_ts: {start_ts}")
        print(f"  - end_ts: {end_ts}")
        print(f"  - gallery_target_id: {gallery_target_id}")
        print(f"  - name: {target_name}")
        
    except Exception as e:
        print(f"[错误] 插入轨迹记录失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 关闭数据库连接
        await db.close()
        print("\n[完成] 数据库连接已关闭")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="向 tracklet 表添加轨迹数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python add_trajectory.py --flag 1 --cream 2 --image_path ./frame/image.jpg
  python add_trajectory.py --flag 2 --cream 1 --image_path ./frame/image.png

参数说明:
  FLAGE: 目标人物标识
    - 1: 冷佳旭 (UUID: df794f6e-b10a-47f2-828b-b8f2397aaf2d)
    - 2: 李昆鸿 (UUID: 293ababf-1e58-433d-9f97-6a336c3197e0)
    - 其他: 李爽 (UUID: 38c10d0d-5638-4222-abe3-824e6fe61688)
  
  CREAM: 摄像头编号，将生成 stream_id = live/camera_{CREAM}_boxmot
  
  IMAGE_PATH: 图片文件路径（支持 .jpg 或 .png 格式）
        """
    )
    
    parser.add_argument(
        "--flag",
        type=int,
        required=True,
        help="目标人物标识 (1=冷佳旭, 2=李昆鸿, 其他=李爽)"
    )
    
    parser.add_argument(
        "--cream",
        type=int,
        required=True,
        help="摄像头编号 (将生成 stream_id = live/camera_{CREAM}_boxmot)"
    )
    
    parser.add_argument(
        "--image_path",
        type=str,
        required=True,
        help="图片文件路径（用于 frame_asset_base64，支持 .jpg 或 .png 格式）"
    )
    
    args = parser.parse_args()
    
    # 打印参数含义
    print_parameter_info(args.flag, args.cream, args.image_path)
    
    print("=" * 60)
    print("添加轨迹数据到 tracklet 表")
    print("=" * 60)
    asyncio.run(add_trajectory(args.flag, args.cream, args.image_path))


if __name__ == "__main__":
    main()

