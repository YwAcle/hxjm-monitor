#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统计 /home/guest/Documents/lkh/mtx/python/reid/save 目录下的图片数量
"""

import os
from pathlib import Path
from collections import defaultdict
import json
from datetime import datetime


# 数据源路径
DATA_SOURCE = "/home/guest/Documents/lkh/mtx/python/reid/save"

# 支持的图片格式
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif'}


def is_image_file(filepath):
    """判断文件是否为图片"""
    return Path(filepath).suffix.lower() in IMAGE_EXTENSIONS


def count_images_in_directory(root_dir):
    """
    统计目录下的所有图片
    
    Returns:
        dict: 统计结果，包含：
            - total_images: 总图片数
            - by_date: 按日期统计
            - by_camera: 按摄像头统计
            - by_date_camera: 按日期和摄像头统计
            - track_folders: track 文件夹统计
    """
    root_path = Path(root_dir)
    if not root_path.exists():
        print(f"错误：目录不存在: {root_dir}")
        return None
    
    stats = {
        'total_images': 0,
        'total_tracks': 0,
        'by_date': defaultdict(int),
        'by_camera': defaultdict(int),
        'by_date_camera': defaultdict(lambda: defaultdict(int)),
        'track_folders': defaultdict(int),  # track 文件夹名 -> 图片数
        'date_list': [],
        'camera_list': []
    }
    
    print(f"开始扫描目录: {root_dir}")
    print("-" * 60)
    
    # 遍历所有日期文件夹
    for date_dir in sorted(root_path.iterdir()):
        if not date_dir.is_dir():
            continue
        
        date_str = date_dir.name
        # 检查是否是日期格式 (YYYY-MM-DD)
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            continue
        
        stats['date_list'].append(date_str)
        date_image_count = 0
        
        # 遍历该日期下的所有 track 文件夹
        for track_dir in sorted(date_dir.iterdir()):
            if not track_dir.is_dir():
                continue
            
            track_name = track_dir.name
            track_image_count = 0
            
            # 统计该 track 文件夹下的图片
            for file_path in track_dir.iterdir():
                if file_path.is_file() and is_image_file(file_path):
                    track_image_count += 1
                    stats['total_images'] += 1
                    date_image_count += 1
            
            if track_image_count > 0:
                stats['total_tracks'] += 1
                stats['track_folders'][track_name] = track_image_count
                
                # 从 track 名称中提取摄像头信息
                # 格式：live_camera_{camera_id}_savereid_track_{track_id}
                parts = track_name.split('_')
                camera_id = None
                if len(parts) >= 2 and parts[0] == 'live' and parts[1] == 'camera':
                    try:
                        camera_id = parts[2]
                        camera_name = f"camera_{camera_id}"
                        stats['by_camera'][camera_name] += track_image_count
                        stats['by_date_camera'][date_str][camera_name] += track_image_count
                        if camera_name not in stats['camera_list']:
                            stats['camera_list'].append(camera_name)
                    except (IndexError, ValueError):
                        pass
            
            stats['by_date'][date_str] = date_image_count
        
        if date_image_count > 0:
            print(f"日期 {date_str}: {date_image_count} 张图片, {len([d for d in date_dir.iterdir() if d.is_dir()])} 个 track 文件夹")
    
    # 转换 defaultdict 为普通 dict（用于 JSON 序列化）
    stats['by_date'] = dict(stats['by_date'])
    stats['by_camera'] = dict(stats['by_camera'])
    stats['by_date_camera'] = {
        date: dict(cameras) 
        for date, cameras in stats['by_date_camera'].items()
    }
    stats['track_folders'] = dict(stats['track_folders'])
    
    return stats


def print_statistics(stats):
    """打印统计结果"""
    if not stats:
        return
    
    print("\n" + "=" * 60)
    print("统计结果")
    print("=" * 60)
    
    print(f"\n【总体统计】")
    print(f"  总图片数: {stats['total_images']:,}")
    print(f"  总 track 数: {stats['total_tracks']:,}")
    print(f"  日期数: {len(stats['date_list'])}")
    print(f"  摄像头数: {len(stats['camera_list'])}")
    
    print(f"\n【按日期统计】")
    for date in sorted(stats['by_date'].keys()):
        count = stats['by_date'][date]
        print(f"  {date}: {count:,} 张")
    
    print(f"\n【按摄像头统计】")
    for camera in sorted(stats['by_camera'].keys()):
        count = stats['by_camera'][camera]
        print(f"  {camera}: {count:,} 张")
    
    print(f"\n【按日期和摄像头统计】")
    for date in sorted(stats['by_date_camera'].keys()):
        print(f"  {date}:")
        for camera in sorted(stats['by_date_camera'][date].keys()):
            count = stats['by_date_camera'][date][camera]
            print(f"    {camera}: {count:,} 张")
    
    # 统计 track 文件夹的图片数量分布
    print(f"\n【Track 文件夹图片数量分布】")
    track_counts = list(stats['track_folders'].values())
    if track_counts:
        print(f"  最少图片数: {min(track_counts)}")
        print(f"  最多图片数: {max(track_counts)}")
        print(f"  平均图片数: {sum(track_counts) / len(track_counts):.1f}")
        
        # 统计不同图片数量范围的 track 数量
        ranges = [
            (1, 5, "1-5张"),
            (6, 10, "6-10张"),
            (11, 20, "11-20张"),
            (21, 50, "21-50张"),
            (51, 100, "51-100张"),
            (101, float('inf'), "100+张")
        ]
        for min_count, max_count, label in ranges:
            count = sum(1 for c in track_counts if min_count <= c <= max_count)
            if count > 0:
                print(f"  {label}: {count} 个 track")


def save_statistics_to_json(stats, output_file):
    """保存统计结果到 JSON 文件"""
    if not stats:
        return
    
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        print(f"\n统计结果已保存到: {output_file}")
    except Exception as e:
        print(f"\n保存统计结果失败: {e}")


def main():
    """主函数"""
    print("=" * 60)
    print("ReID 图片统计工具")
    print("=" * 60)
    
    # 统计图片
    stats = count_images_in_directory(DATA_SOURCE)
    
    if stats:
        # 打印统计结果
        print_statistics(stats)
        
        # 保存到 JSON 文件
        output_file = Path(__file__).parent / "image_statistics.json"
        save_statistics_to_json(stats, output_file)
        
        print("\n" + "=" * 60)
        print("统计完成！")
        print("=" * 60)
    else:
        print("统计失败！")


if __name__ == '__main__':
    main()


