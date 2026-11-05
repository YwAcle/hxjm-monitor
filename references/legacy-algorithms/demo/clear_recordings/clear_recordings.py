#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理 mediamtx/recordings/live 目录下指定日期开头的 mp4 文件

用法:
    python3 clear_recordings.py 2026-01-04              # 交互式删除
    python3 clear_recordings.py 2026-01-04 --dry-run    # 只显示不删除
    python3 clear_recordings.py 2026-01-04 --force      # 跳过确认直接删除
"""

import os
import sys
import argparse
from pathlib import Path
from collections import defaultdict
from datetime import datetime


# 目标目录（相对于脚本所在目录）
LIVE_DIR = "/home/guest/Documents/lkh/mtx/mediamtx/recordings/live"


def validate_date(date_str):
    """验证日期格式"""
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except ValueError:
        return False


def find_files_by_date(date_str, root_dir):
    """
    查找所有以指定日期开头的 mp4 文件
    
    Args:
        date_str: 日期字符串，格式 YYYY-MM-DD
        root_dir: 根目录路径
        
    Returns:
        list: 文件路径列表
    """
    files = []
    root_path = Path(root_dir)
    
    if not root_path.exists():
        print(f"错误：目录不存在: {root_dir}")
        return files
    
    # 查找所有以 date_str 开头的 mp4 文件
    pattern = f"{date_str}*.mp4"
    for file_path in root_path.rglob(pattern):
        if file_path.is_file():
            files.append(file_path)
    
    return sorted(files)


def get_file_size_mb(file_path):
    """获取文件大小（MB）"""
    try:
        size_bytes = file_path.stat().st_size
        return size_bytes / (1024 * 1024)
    except Exception:
        return 0


def group_files_by_directory(files):
    """按目录分组文件"""
    groups = defaultdict(list)
    for file_path in files:
        parent_dir = file_path.parent.name
        groups[parent_dir].append(file_path)
    return groups


def print_statistics(files, date_str):
    """打印统计信息"""
    if not files:
        print(f"\n未找到以 '{date_str}' 开头的 mp4 文件")
        return
    
    print(f"\n{'='*60}")
    print(f"找到 {len(files)} 个以 '{date_str}' 开头的 mp4 文件")
    print(f"{'='*60}")
    
    # 计算总大小
    total_size_mb = sum(get_file_size_mb(f) for f in files)
    
    # 按目录分组
    groups = group_files_by_directory(files)
    
    print(f"\n【总体统计】")
    print(f"  文件总数: {len(files):,}")
    print(f"  总大小: {total_size_mb:.2f} MB ({total_size_mb/1024:.2f} GB)")
    print(f"  涉及目录数: {len(groups)}")
    
    print(f"\n【按目录统计】")
    for dir_name in sorted(groups.keys()):
        dir_files = groups[dir_name]
        dir_size_mb = sum(get_file_size_mb(f) for f in dir_files)
        print(f"  {dir_name}: {len(dir_files)} 个文件, {dir_size_mb:.2f} MB")
    
    # 显示前10个文件示例
    print(f"\n【文件示例（前10个）】")
    for i, file_path in enumerate(files[:10], 1):
        size_mb = get_file_size_mb(file_path)
        rel_path = file_path.relative_to(LIVE_DIR)
        print(f"  {i}. {rel_path} ({size_mb:.2f} MB)")
    
    if len(files) > 10:
        print(f"  ... 还有 {len(files) - 10} 个文件")


def delete_files(files, dry_run=False):
    """
    删除文件列表
    
    Args:
        files: 文件路径列表
        dry_run: 如果为 True，只显示不删除
        
    Returns:
        tuple: (成功数, 失败数, 错误列表)
    """
    success_count = 0
    fail_count = 0
    errors = []
    
    if dry_run:
        print(f"\n【DRY-RUN 模式】只显示，不删除")
        return len(files), 0, []
    
    print(f"\n开始删除文件...")
    
    for i, file_path in enumerate(files, 1):
        try:
            file_path.unlink()
            success_count += 1
            if i % 50 == 0:
                print(f"  已删除 {i}/{len(files)} 个文件...", end='\r')
        except Exception as e:
            fail_count += 1
            errors.append((str(file_path), str(e)))
            print(f"\n  删除失败: {file_path} - {e}")
    
    print(f"\n删除完成: 成功 {success_count}, 失败 {fail_count}")
    
    if errors:
        print(f"\n【删除失败的文件】")
        for file_path, error in errors[:10]:
            print(f"  {file_path}: {error}")
        if len(errors) > 10:
            print(f"  ... 还有 {len(errors) - 10} 个失败")
    
    return success_count, fail_count, errors


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='清理 mediamtx/recordings/live 目录下指定日期开头的 mp4 文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s 2026-01-04              # 交互式删除
  %(prog)s 2026-01-04 --dry-run    # 只显示不删除
  %(prog)s 2026-01-04 --force      # 跳过确认直接删除
        """
    )
    
    parser.add_argument(
        'date',
        type=str,
        help='日期，格式: YYYY-MM-DD (例如: 2026-01-04)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='只显示要删除的文件，不实际删除'
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='跳过确认，直接删除'
    )
    
    parser.add_argument(
        '--dir',
        type=str,
        default=str(LIVE_DIR),
        help=f'目标目录 (默认: {LIVE_DIR})'
    )
    
    args = parser.parse_args()
    
    # 验证日期格式
    if not validate_date(args.date):
        print(f"错误：日期格式不正确，应为 YYYY-MM-DD (例如: 2026-01-04)")
        sys.exit(1)
    
    # 验证目录
    target_dir = Path(args.dir)
    if not target_dir.exists():
        print(f"错误：目录不存在: {target_dir}")
        sys.exit(1)
    
    print("="*60)
    print("MediaMTX 录制文件清理工具")
    print("="*60)
    print(f"目标目录: {target_dir}")
    print(f"日期: {args.date}")
    print(f"模式: {'DRY-RUN (只显示)' if args.dry_run else ('FORCE (直接删除)' if args.force else '交互式')}")
    
    # 查找文件
    print(f"\n正在扫描文件...")
    files = find_files_by_date(args.date, target_dir)
    
    # 打印统计信息
    print_statistics(files, args.date)
    
    if not files:
        print("\n没有找到需要删除的文件")
        sys.exit(0)
    
    # 确认删除
    if args.dry_run:
        print(f"\n【DRY-RUN 模式】不会实际删除文件")
        sys.exit(0)
    
    if not args.force:
        print(f"\n{'='*60}")
        print(f"警告：将删除 {len(files)} 个文件！")
        print(f"{'='*60}")
        confirm = input("确认删除？(输入 'yes' 确认): ")
        
        if confirm.lower() != 'yes':
            print("已取消删除操作")
            sys.exit(0)
    
    # 执行删除
    success_count, fail_count, errors = delete_files(files, dry_run=False)
    
    # 最终统计
    print(f"\n{'='*60}")
    print("清理完成")
    print(f"{'='*60}")
    print(f"成功删除: {success_count} 个文件")
    if fail_count > 0:
        print(f"删除失败: {fail_count} 个文件")
    
    sys.exit(0 if fail_count == 0 else 1)


if __name__ == '__main__':
    main()

