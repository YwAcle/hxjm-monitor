# -*- coding: utf-8 -*-
# pip install -i https://pypi.doubanio.com/simple/ 包名
# pip install -i https://pypi.tuna.tsinghua.edu.cn/simple 包名
# @Time    : 2025/12/25 11:01
# @Author  : beidanci
# !/usr/bin/env python3
"""
向 reid_target 表添加目标人物特征

使用方法：
1. 单张图片：python add_reid_target.py --image /path/to/image.jpg --name "张三"
2. 批量处理：python add_reid_target.py --dir /path/to/images --name_prefix "人员"
"""

import os
import sys
import cv2
import torch
import numpy as np
import argparse
from pathlib import Path
import asyncio

# CLIP-ReID 模型路径
sys.path.insert(0, "/home/guest/Documents/hxjm-monitor/mtx/python/reid/CLIP-ReID")

from config import cfg_base as cfg
from model.make_model import make_model

# 添加模块路径 (上级目录)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from base.postgresql.db_session import DBSession
from base.postgresql.config import DBConfig


class ReIDTargetAdder:
    """ReID目标人物特征添加器"""

    def __init__(self):
        """初始化ReID模型和数据库连接（不在这里await）"""
        print("[INIT] 初始化 ReID 模型...")

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[INIT] 使用设备: {self.device}")

        # 加载配置
        cfg.merge_from_file(
            "/home/guest/Documents/hxjm-monitor/mtx/python/reid/config/vit_base.yml"
        )
        cfg.freeze()

        # 构建模型
        self.reid_model = make_model(
            cfg,
            num_class=1,
            camera_num=1,
            view_num=1
        )
        self.reid_model.to(self.device)
        self.reid_model.eval()

        # 加载权重
        weight_path = Path(
            "/home/guest/Documents/hxjm-monitor/mtx/python/reid/weights/MSMT17_clipreid_ViT-B-16_60.pth"
        )
        if not weight_path.exists():
            raise FileNotFoundError(f"权重文件不存在: {weight_path}")

        print(f"[INIT] 加载模型权重: {weight_path}")
        self.reid_model.load_param(str(weight_path))

        # 初始化transform
        import torchvision.transforms as T
        self.reid_transform = T.Compose([
            T.ToPILImage(),
            T.Resize((cfg.INPUT.SIZE_TRAIN[0], cfg.INPUT.SIZE_TRAIN[1])),
            T.ToTensor(),
            T.Normalize(mean=cfg.INPUT.PIXEL_MEAN, std=cfg.INPUT.PIXEL_STD)
        ])

        # 初始化数据库连接（只创建对象，不初始化连接池）
        print("[INIT] 初始化数据库连接配置...")
        db_config = DBConfig(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "postgres"),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", "123456")
        )
        self.db = DBSession(config=db_config)

    async def init(self):
        """异步初始化：在事件循环中初始化数据库连接池"""
        print("[INIT] 初始化数据库连接池...")
        await self.db.initialize()
        print("[INIT] 初始化完成\n")
        return self

    def extract_feature(self, image_path: str) -> np.ndarray:
        """
        从图片路径提取特征

        Args:
            image_path: 图片文件路径

        Returns:
            特征向量 (numpy array)
        """
        # 读取图片
        img_bgr = cv2.imread(image_path)
        if img_bgr is None:
            raise ValueError(f"无法读取图片: {image_path}")

        # 转换为RGB
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

        # 转换为tensor
        tensor = self.reid_transform(img_rgb).unsqueeze(0).to(self.device)

        # 提取特征
        with torch.no_grad():
            feat = self.reid_model(tensor)
            feat = feat / feat.norm(dim=1, keepdim=True)

        return feat.cpu().numpy()

    async def add_target(self, image_path: str, name: str,
                         employee_id: str = None, source_asset_id: str = None,
                         is_active: bool = True) -> str:
        """
        添加目标人物到数据库

        Args:
            image_path: 图片路径
            name: 姓名/别名（必填）
            employee_id: 员工ID（可选）
            source_asset_id: 来源图片ID（可选）
            is_active: 是否有效

        Returns:
            插入记录的ID
        """
        print(f"[处理] 正在处理: {image_path}")

        # 提取特征
        feature = self.extract_feature(image_path)
        embedding = feature.flatten().tolist()  # 转换为列表

        # 插入数据库
        db_id = await self.db.insert_reid_target(
            name=name,
            embedding=embedding,
            embedding_model="CLIP-ReID-ViT-B-16",
            employee_id=employee_id,
            source_asset_id=source_asset_id,
            is_active=is_active
        )

        print(f"[成功] 已添加目标人物: {name} (ID: {db_id})")
        return db_id

    async def add_targets_from_dir(self, dir_path: str, name_prefix: str = "人员"):
        """
        批量从目录添加目标人物

        Args:
            dir_path: 图片目录路径
            name_prefix: 名称前缀
        """
        dir_path = Path(dir_path)
        if not dir_path.exists() or not dir_path.is_dir():
            raise ValueError(f"目录不存在: {dir_path}")

        # 获取所有图片文件
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp'}
        image_files = [
            f for f in dir_path.iterdir()
            if f.suffix.lower() in image_extensions
        ]

        if len(image_files) == 0:
            print(f"[警告] 目录中没有找到图片文件: {dir_path}")
            return

        print(f"[批量处理] 找到 {len(image_files)} 张图片")

        # 批量处理
        for idx, image_file in enumerate(sorted(image_files), start=1):
            try:
                # 从文件名提取名称（去掉扩展名）
                name = name_prefix + str(idx) if name_prefix else image_file.stem

                await self.add_target(
                    image_path=str(image_file),
                    name=name
                )
            except Exception as e:
                print(f"[错误] 处理 {image_file} 失败: {e}")
                continue

        print(f"\n[完成] 批量处理完成，共处理 {len(image_files)} 张图片")

    async def close(self):
        """关闭数据库连接"""
        await self.db.close()


async def main_async(args):
    """异步主函数"""
    adder = await ReIDTargetAdder().init()

    try:
        if args.image:
            # 单张图片处理
            if not args.name:
                # 从文件名提取名称
                name = Path(args.image).stem
            else:
                name = args.name

            await adder.add_target(
                image_path=args.image,
                name=name,
                employee_id=args.employee_id,
                source_asset_id=args.source_asset_id
            )

        elif args.dir:
            # 批量处理目录
            await adder.add_targets_from_dir(
                dir_path=args.dir,
                name_prefix=args.name_prefix
            )

        else:
            print("[错误] 请指定 --image 或 --dir 参数")
            return

    finally:
        await adder.close()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="向 reid_target 表添加目标人物特征"
    )

    # 输入选项（互斥）
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        '--image',
        type=str,
        help='单张图片路径'
    )
    input_group.add_argument(
        '--dir',
        type=str,
        help='图片目录路径（批量处理）'
    )

    # 其他参数
    parser.add_argument(
        '--name',
        type=str,
        help='目标人物姓名（单张图片时使用，如果不指定则使用文件名）'
    )
    parser.add_argument(
        '--name-prefix',
        type=str,
        default='人员',
        help='批量处理时的名称前缀（默认：人员）'
    )
    parser.add_argument(
        '--employee-id',
        type=str,
        help='员工ID（可选）'
    )
    parser.add_argument(
        '--source-asset-id',
        type=str,
        help='来源图片ID（可选）'
    )

    args = parser.parse_args()

    # 运行异步主函数
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()

