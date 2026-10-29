# -*- coding: utf-8 -*-
# @Time    : 2025/01/XX
# @Author  : beidanci
# !/usr/bin/env python3
"""
向 reid_target 表添加目标人物特征（使用平均特征）

从 ./data/student/姓名/图片1.jpg, 图片2.jpg, ... 提取每个图片的特征，
然后计算平均特征值，每个姓名只写入一条数据库记录。

使用方法：
python add__reid_target_mean.py
"""

import os
import sys
import cv2
import torch
import numpy as np
import asyncio
import base64
from pathlib import Path

# CLIP-ReID 模型路径
sys.path.insert(0, "/home/guest/Documents/hxjm-monitor/mtx/python/reid/CLIP-ReID")

from config import cfg_base as cfg
from model.make_model import make_model

# 添加模块路径 (上级目录)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from base.postgresql.db_session import DBSession
from base.postgresql.config import DBConfig


class ReIDTargetMeanAdder:
    """ReID目标人物特征添加器（使用平均特征）"""

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
            view_num=1,
            device=self.device
        )
        self.reid_model.to(self.device)
        self.reid_model.eval()

        # 加载权重
        weight_path = Path(
            "/home/guest/Documents/hxjm-monitor/mtx/python/reid/weights/ViT-B-16_60_trained.pth"
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

    def compute_mean_feature(self, feature_list: list) -> np.ndarray:
        """
        计算特征列表的平均值并归一化

        Args:
            feature_list: 特征向量列表，每个元素是一个 numpy array

        Returns:
            平均特征向量（归一化后）
        """
        if len(feature_list) == 0:
            raise ValueError("特征列表为空")

        # 将所有特征堆叠成矩阵
        features = np.vstack(feature_list)  # shape: (n, feature_dim)

        # 计算平均值
        mean_feature = np.mean(features, axis=0)  # shape: (feature_dim,)

        # 归一化（L2归一化）
        norm = np.linalg.norm(mean_feature)
        if norm > 0:
            mean_feature = mean_feature / norm

        return mean_feature

    async def add_target_with_mean_feature(self, image_paths: list, name: str,
                                           employee_id: str = None, source_asset_id: str = None,
                                           is_active: bool = True) -> str:
        """
        从多张图片提取特征，计算平均值，然后添加到数据库

        Args:
            image_paths: 图片路径列表
            name: 姓名/别名（必填）
            employee_id: 员工ID（可选）
            source_asset_id: 来源图片ID（可选）
            is_active: 是否有效

        Returns:
            插入记录的ID
        """
        if len(image_paths) == 0:
            raise ValueError("图片路径列表为空")

        print(f"[处理] 正在处理: {name} ({len(image_paths)} 张图片)")

        # 提取所有图片的特征
        feature_list = []
        valid_image_paths = []
        
        for image_path in image_paths:
            try:
                feature = self.extract_feature(image_path)
                feature_list.append(feature)
                valid_image_paths.append(image_path)
            except Exception as e:
                print(f"  [警告] 无法提取特征 {image_path}: {e}")
                continue

        if len(feature_list) == 0:
            raise ValueError(f"无法从任何图片提取特征: {name}")

        print(f"  [提取特征] 成功提取 {len(feature_list)}/{len(image_paths)} 张图片的特征")

        # 计算平均特征
        mean_feature = self.compute_mean_feature(feature_list)
        embedding = mean_feature.flatten().tolist()  # 转换为列表

        # 使用第一张有效图片作为 image_base64
        representative_image_path = valid_image_paths[0]
        img_bgr = cv2.imread(representative_image_path)
        if img_bgr is None:
            raise ValueError(f"无法读取代表性图片: {representative_image_path}")
        
        # 编码为base64
        success, buffer = cv2.imencode('.jpg', img_bgr)
        if not success:
            raise ValueError(f"无法编码图片: {representative_image_path}")
        image_base64 = base64.b64encode(buffer).decode('utf-8')

        # 插入数据库
        db_id = await self.db.insert_reid_target(
            name=name,
            embedding=embedding,
            embedding_model="CLIP-ReID-ViT-B-16",
            employee_id=employee_id,
            source_asset_id=source_asset_id,
            image_base64=image_base64,
            is_active=is_active
        )

        print(f"[成功] 已添加目标人物: {name} (ID: {db_id}, 使用 {len(feature_list)} 张图片的平均特征)")
        return db_id

    async def add_targets_from_student_dir(self, student_dir: str = "./data/students"):
        """
        从student目录结构批量添加目标人物（使用平均特征）
        目录结构：./data/student/姓名/图片1.jpg, 图片2.jpg, ...
        
        每个姓名只写入一条数据库记录，使用该姓名下所有图片的平均特征
        
        Args:
            student_dir: student目录路径（默认：./data/student）
        """
        student_dir_path = Path(student_dir)
        if not student_dir_path.exists() or not student_dir_path.is_dir():
            raise ValueError(f"目录不存在: {student_dir_path}")
        
        # 获取所有子目录（姓名列表）
        student_names = [
            d.name for d in student_dir_path.iterdir()
            if d.is_dir()
        ]
        
        if len(student_names) == 0:
            print(f"[警告] {student_dir_path} 目录下没有找到子目录")
            return
        
        print(f"[批量处理] 找到 {len(student_names)} 个人的目录: {student_names}\n")
        
        # 遍历每个姓名目录
        total_added = 0
        success_count = 0
        fail_count = 0
        
        for student_name in sorted(student_names):
            student_subdir = student_dir_path / student_name
            print(f"[处理] 正在处理: {student_name} (目录: {student_subdir})")
            
            # 获取该目录下的所有图片文件
            image_extensions = {'.jpg', '.jpeg', '.png', '.bmp'}
            image_files = [
                f for f in student_subdir.iterdir()
                if f.is_file() and f.suffix.lower() in image_extensions
            ]
            
            if len(image_files) == 0:
                print(f"[警告] {student_subdir} 目录下没有找到图片文件\n")
                fail_count += 1
                continue
            
            print(f"  找到 {len(image_files)} 张图片")
            
            # 将该目录下的所有图片路径传入，计算平均特征并插入一条记录
            try:
                image_paths = [str(f) for f in sorted(image_files)]
                await self.add_target_with_mean_feature(
                    image_paths=image_paths,
                    name=student_name  # 使用目录名作为name
                )
                success_count += 1
                total_added += 1
            except Exception as e:
                print(f"  [错误] 处理 {student_name} 失败: {e}")
                fail_count += 1
                continue
            
            print()  # 空行分隔
        
        print("=" * 60)
        print(f"[全部完成]")
        print(f"  成功添加: {success_count} 个人")
        print(f"  失败: {fail_count} 个人")
        print(f"  总计: {len(student_names)} 个人")
        print("=" * 60)

    async def close(self):
        """关闭数据库连接"""
        await self.db.close()


async def main():
    """
    主函数：从 ./data/student 目录批量添加目标人物（使用平均特征）
    """
    print("=" * 60)
    print("批量添加目标人物（从 ./data/students 目录，使用平均特征）")
    print("=" * 60)
    print()
    
    # 获取脚本所在目录，构建 data/student 的绝对路径
    script_dir = Path(__file__).parent
    student_dir = script_dir / "data" / "students"
    
    adder = await ReIDTargetMeanAdder().init()
    
    try:
        await adder.add_targets_from_student_dir(str(student_dir))
    finally:
        await adder.close()
    
    print("\n" + "=" * 60)
    print("处理完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
