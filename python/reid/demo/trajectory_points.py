# -*- coding: utf-8 -*-
# @Time    : 2025/01/XX
# @Author  : beidanci
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
统计 tracklet 表中每条记录的 trajectory_points 长度，并按区间分组统计。

tracklet 表的 trajectory_points 字段格式为：{'points': []}

使用 db_session.py 框架进行数据库操作。

用法：
  1) 默认全表统计：
     python trajectory_points.py

  2) 最新 N 条：
     python trajectory_points.py --latest 100

  3) 自定义数据库配置：
     python trajectory_points.py --host <host> --port <port> --database <db> --user <user> --password <pwd>

输出：
  统计结果会输出到控制台，显示每个长度区间内的记录数量。
"""

import os
import sys
import json
import argparse
import asyncio
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

# 添加模块路径（python 目录）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from base.postgresql.db_session import DBSession
from base.postgresql.config import DBConfig


def parse_jsonb(val: Any) -> Optional[Dict[str, Any]]:
    """
    解析 JSONB 字段值
    
    Args:
        val: JSONB 字段的值（可能是 dict、str 或其他类型）
    
    Returns:
        解析后的字典，如果解析失败返回 None
    """
    if val is None:
        return None
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except Exception:
            return None
    try:
        return dict(val)
    except Exception:
        return None


def get_trajectory_points_length(trajectory_points_val: Any) -> int:
    """
    从 trajectory_points 字段中提取 points 列表并返回其长度
    
    Args:
        trajectory_points_val: trajectory_points 字段的值（JSONB），格式为 {'points': []}
    
    Returns:
        points 列表的长度，如果不存在或解析失败返回 0
    """
    # 解析 JSONB 字段
    traj_data = parse_jsonb(trajectory_points_val)
    
    print(f"[INFO] traj_data: {traj_data}")
    if not traj_data or not isinstance(traj_data, dict):
        return 0
    
    # 从字典中获取 points 字段
    points = traj_data.get("points")
    if points is None:
        return 0
    
    # points 应该是一个列表
    if isinstance(points, list):
        return len(points)
    
    return 0


def get_length_range(length: int) -> str:
    """
    根据轨迹点长度返回所属区间标签
    
    Args:
        length: 轨迹点长度
    
    Returns:
        区间标签字符串
    """
    if length == 0:
        return "0 (无轨迹点)"
    elif length == 1:
        return "1"
    elif length == 2:
        return "2"
    elif length == 3:
        return "3"
    elif length == 4:
        return "4"
    elif length == 5:
        return "5"
    elif length == 6:
        return "6"
    elif length == 7:
        return "7"
    elif length == 8:
        return "8"
    elif length == 9:
        return "9"
    elif length == 10:
        return "10"
    elif 11 <= length <= 50:
        return "11-50"
    elif 51 <= length <= 100:
        return "51-100"
    elif 101 <= length <= 500:
        return "101-500"
    elif 501 <= length <= 1000:
        return "501-1000"
    else:
        return "1001+"


async def fetch_tracklets(db: DBSession, latest: Optional[int] = None) -> List:
    """
    查询 tracklet 记录
    
    Args:
        db: DBSession 实例
        latest: 可选的最新 N 条记录（None 表示查询全部）
    
    Returns:
        tracklet 记录列表
    """
    if latest is not None:
        # 查询最新 N 条
        records = await db.select_tracklet(
            order_by="created_at DESC",
            limit=int(latest)
        )
        return list(records)
    
    # 默认：全表查询（按创建时间降序）
    records = await db.select_tracklet(
        order_by="created_at DESC"
    )
    return list(records)


async def main():
    ap = argparse.ArgumentParser(
        description="统计 tracklet 表中 trajectory_points 的长度分布"
    )
    ap.add_argument("--latest", type=int, default=None, help="取最新 N 条记录（不指定时查询全部）")
    ap.add_argument("--host", type=str, default=None, help="数据库主机地址")
    ap.add_argument("--port", type=int, default=None, help="数据库端口")
    ap.add_argument("--database", type=str, default=None, help="数据库名称")
    ap.add_argument("--user", type=str, default=None, help="数据库用户名")
    ap.add_argument("--password", type=str, default=None, help="数据库密码")
    args = ap.parse_args()

    # 创建数据库配置
    db_config = DBConfig(
        host=args.host or os.getenv("DB_HOST", "192.168.108.238"),
        port=args.port or int(os.getenv("DB_PORT", "5432")),
        database=args.database or os.getenv("DB_NAME", "postgres"),
        user=args.user or os.getenv("DB_USER", "root"),
        password=args.password or os.getenv("DB_PASSWORD", "123456")
    )

    # 创建 DBSession 实例
    db = DBSession(config=db_config)

    try:
        # 初始化数据库连接池
        await db.initialize()
        print("[INFO] 数据库连接池初始化成功")

        # 查询 tracklet 记录
        print(f"[INFO] 开始查询 tracklet 记录...")
        rows = await fetch_tracklets(db, args.latest)
        if not rows:
            print("[WARN] 没找到 tracklet 记录")
            return

        total_count = len(rows)
        print(f"[INFO] 查询到 {total_count} 条 tracklet 记录")

        # 统计每个区间的数量
        range_counts = defaultdict(int)
        length_list = []
        
        print(f"\n[INFO] 开始统计 trajectory_points 长度...")
        for i, row in enumerate(rows, 1):
            tid = str(row.get("id", ""))
            trajectory_points_val = row.get("trajectory_points")
            
            # 获取轨迹点长度
            length = get_trajectory_points_length(trajectory_points_val)
            length_list.append(length)
            
            # 获取区间标签
            range_label = get_length_range(length)
            range_counts[range_label] += 1
            
            # 每处理 100 条记录输出一次进度
            if i % 100 == 0:
                print(f"[INFO] 已处理 {i}/{total_count} 条记录...", end='\r')

        print(f"\n[INFO] 统计完成！\n")

        # 计算统计信息
        if length_list:
            min_length = min(length_list)
            max_length = max(length_list)
            avg_length = sum(length_list) / len(length_list)
            
            # 计算中位数
            sorted_lengths = sorted(length_list)
            n = len(sorted_lengths)
            if n % 2 == 0:
                median_length = (sorted_lengths[n // 2 - 1] + sorted_lengths[n // 2]) / 2
            else:
                median_length = sorted_lengths[n // 2]
        else:
            min_length = max_length = avg_length = median_length = 0

        # 输出统计结果
        print("=" * 60)
        print("轨迹点长度统计结果")
        print("=" * 60)
        print(f"\n总记录数: {total_count}")
        print(f"\n长度统计信息:")
        print(f"  最小值: {min_length}")
        print(f"  最大值: {max_length}")
        print(f"  平均值: {avg_length:.2f}")
        print(f"  中位数: {median_length:.2f}")

        print(f"\n长度区间分布:")
        print("-" * 60)
        print(f"{'区间':<20} {'记录数':<15} {'占比':<15}")
        print("-" * 60)
        
        # 按区间顺序输出
        range_order = [
            "0 (无轨迹点)",
            "1",
            "2-10",
            "11-50",
            "51-100",
            "101-500",
            "501-1000",
            "1001+"
        ]
        
        for range_label in range_order:
            count = range_counts.get(range_label, 0)
            if count > 0:
                percentage = (count / total_count) * 100
                print(f"{range_label:<20} {count:<15} {percentage:>6.2f}%")
        
        # 输出其他可能的区间（如果有）
        other_ranges = set(range_counts.keys()) - set(range_order)
        if other_ranges:
            print("-" * 60)
            for range_label in sorted(other_ranges):
                count = range_counts.get(range_label, 0)
                percentage = (count / total_count) * 100
                print(f"{range_label:<20} {count:<15} {percentage:>6.2f}%")
        
        print("-" * 60)
        print("=" * 60)

    except Exception as e:
        print(f"[ERR] 处理过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 关闭数据库连接池
        await db.close()
        print("\n[INFO] 数据库连接池已关闭")


if __name__ == "__main__":
    asyncio.run(main())

