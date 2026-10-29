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
2. 批量处理：python add_reid_target.py --dir /path/to/images --name_prefix "张三"  // 批量写入的 name 也都是张三
"""

import os
import sys
import cv2
import torch
import numpy as np
import argparse
from pathlib import Path
import asyncio
import base64

# Resolve bundled model resources relative to this script so the utility works
# from both a local checkout and the Docker image.
BASE_DIR = Path(__file__).resolve().parent
CLIP_REID_DIR = BASE_DIR / "CLIP-ReID"
CONFIG_DIR = BASE_DIR / "config"
WEIGHTS_DIR = BASE_DIR / "weights"

sys.path.insert(0, str(CLIP_REID_DIR))

from config import cfg_base as cfg
from model.make_model import make_model

# 添加模块路径 (上级目录)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from base.postgresql.db_session import DBSession
from base.postgresql.config import DBConfig

# ========== ReID 模型配置常量 ==========
# 可选值: "vit" (ViT-B-16) 或 "rs50" (ResNet50)
REID_MODEL = "rs50"  # 默认使用rs50模型
# REID_MODEL = "vit"  # 默认使用ViT模型

# ========== 名字到固定UUID的映射（第一条记录使用） ==========
# 如果重新新增了特征，就需要更新下这个
NAME_TO_FIXED_UUID = {
    "冷佳旭": "df794f6e-b10a-47f2-828b-b8f2397aaf2d",
    "李昆鸿": "293ababf-1e58-433d-9f97-6a336c3197e0",
    "李爽": "38c10d0d-5638-4222-abe3-824e6fe61688"
}

class ReIDTargetAdder:
    """ReID目标人物特征添加器"""

    def __init__(self):
        """初始化ReID模型和数据库连接（不在这里await）"""
        print("[INIT] 初始化 ReID 模型...")

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[INIT] 使用设备: {self.device}")

        # 根据REID_MODEL常量选择配置文件和权重
        if REID_MODEL.lower() == "vit":
            # ViT-B-16 模型配置
            cfg.merge_from_file(str(CONFIG_DIR / "vit_base.yml"))
            weight_path = WEIGHTS_DIR / "MSMT17_clipreid_ViT-B-16_60.pth"
            self.embedding_model_name = "CLIP-ReID-ViT-B-16"
            model_name = "ViT-B-16"
        elif REID_MODEL.lower() == "rs50":
            # ResNet50 模型配置
            cfg.merge_from_file(str(CONFIG_DIR / "cnn_base.yml"))
            weight_path = WEIGHTS_DIR / "MSMT17_clipreid_RN50_120.pth"
            self.embedding_model_name = "CLIP-ReID-ResNet50"
            model_name = "ResNet50"
        else:
            raise ValueError(f"不支持的REID_MODEL值: {REID_MODEL}，仅支持 'vit' 或 'rs50'")
        
        cfg.freeze()
        print(f"[CLIP-ReID] 使用模型: {model_name} (REID_MODEL={REID_MODEL})")

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
        
        # 清空对应数据库表的所有记录
        await self.clear_table()
        
        return self
    
    async def clear_table(self):
        """清空对应数据库表的所有记录"""
        # 根据REID_MODEL选择表名
        table_name = "reid_target" if REID_MODEL.lower() == "rs50" else "reid_target_vit"
        
        try:
            print(f"[清空表] 正在清空 {table_name} 表的所有记录...")
            # 使用 "1=1" 作为 where 条件，匹配所有记录
            result = await self.db._execute_delete(table_name, "1=1")
            print(f"[清空表] 已清空 {table_name} 表的所有记录")
        except Exception as e:
            print(f"[警告] 清空表 {table_name} 失败: {e}")
            # 不抛出异常，允许继续执行

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
        print(f"特征维度: {feat.shape}")
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

        # 读取图片并转换为base64
        img_bgr = cv2.imread(image_path)
        if img_bgr is None:
            raise ValueError(f"无法读取图片: {image_path}")
        
        # 编码为base64
        success, buffer = cv2.imencode('.jpg', img_bgr)
        if not success:
            raise ValueError(f"无法编码图片: {image_path}")
        image_base64 = base64.b64encode(buffer).decode('utf-8')

        # 提取特征
        feature = self.extract_feature(image_path)
        embedding = feature.flatten().tolist()  # 转换为列表

        # 如果没有传入employee_id，则使用图片名称（不含扩展名）作为employee_id
        if employee_id is None:
            image_name = Path(image_path).stem  # 获取文件名（不含扩展名）
            employee_id = image_name
            print(f"[信息] 未指定employee_id，使用图片名称: {employee_id}")

        # 根据REID_MODEL选择表名
        table_name = "reid_target" if REID_MODEL.lower() == "rs50" else "reid_target_vit"
        
        # 检查该名字是否已有记录（按创建时间排序，取第一条）
        # 注意：查询所有记录（包括非活跃的），以检查是否存在
        existing_records = await self.db._execute_select(
            table_name,
            "id",
            "name = $1",
            name,
            order_by="created_at ASC",
            limit=1
        )
        
        # 如果该名字还没有记录，且名字在固定UUID映射中，使用固定UUID
        fixed_uuid = None
        if len(existing_records) == 0 and name in NAME_TO_FIXED_UUID:
            fixed_uuid = NAME_TO_FIXED_UUID[name]
            print(f"[固定UUID] 使用固定UUID: {fixed_uuid} (名字: {name})")
        elif len(existing_records) > 0:
            existing_id = str(existing_records[0]['id'])
            if name in NAME_TO_FIXED_UUID and existing_id != NAME_TO_FIXED_UUID[name]:
                print(f"[警告] 名字 {name} 已存在记录，但UUID不匹配。现有UUID: {existing_id}, 期望UUID: {NAME_TO_FIXED_UUID[name]}")
        
        # 插入数据库（直接使用_execute_insert以支持动态表名）
        data = {
            'name': name,
            'embedding': embedding,
            'embedding_model': self.embedding_model_name,  # 使用根据REID_MODEL设置的模型名称
            'employee_id': employee_id,  # 使用图片名称作为employee_id
            'source_asset_id': source_asset_id,
            'image_base64': image_base64,
            'is_active': is_active
        }
        
        # 如果是第一条记录且名字在映射中，使用固定UUID
        if fixed_uuid:
            data['id'] = fixed_uuid
        
        data = {k: v for k, v in data.items() if v is not None}
        db_id = await self.db._execute_insert(table_name, data)

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
                # name = name_prefix + str(idx) if name_prefix else image_file.stem
                name = name_prefix
                await self.add_target(
                    image_path=str(image_file),
                    name=name
                )
            except Exception as e:
                print(f"[错误] 处理 {image_file} 失败: {e}")
                continue

        print(f"\n[完成] 批量处理完成，共处理 {len(image_files)} 张图片")

    async def add_targets_from_person_dir(self, person_dir: str = "./data/new_person"):
        """
        从person目录结构批量添加目标人物
        目录结构：./data/person/姓名/图片1.jpg, 图片2.jpg, ...
        
        Args:
            person_dir: person目录路径（默认：./data/person）
        """
        person_dir_path = Path(person_dir)
        if not person_dir_path.exists() or not person_dir_path.is_dir():
            raise ValueError(f"目录不存在: {person_dir_path}")
        
        # 获取所有子目录（姓名列表）
        person_names = [
            d.name for d in person_dir_path.iterdir()
            if d.is_dir()
        ]
        
        if len(person_names) == 0:
            print(f"[警告] {person_dir_path} 目录下没有找到子目录")
            return
        
        print(f"[批量处理] 找到 {len(person_names)} 个人的目录: {person_names}\n")
        
        # 遍历每个姓名目录
        total_images = 0
        for person_name in sorted(person_names):
            person_subdir = person_dir_path / person_name
            print(f"[处理] 正在处理: {person_name} (目录: {person_subdir})")
            
            # 获取该目录下的所有图片文件
            image_extensions = {'.jpg', '.jpeg', '.png', '.bmp'}
            image_files = [
                f for f in person_subdir.iterdir()
                if f.is_file() and f.suffix.lower() in image_extensions
            ]
            
            if len(image_files) == 0:
                print(f"[警告] {person_subdir} 目录下没有找到图片文件\n")
                continue
            
            print(f"  找到 {len(image_files)} 张图片")
            
            # 批量处理该目录下的所有图片，name字段使用目录名（person_name）
            success_count = 0
            for image_file in sorted(image_files):
                try:
                    await self.add_target(
                        image_path=str(image_file),
                        name=person_name  # 使用目录名作为name
                    )
                    success_count += 1
                    total_images += 1
                except Exception as e:
                    print(f"  [错误] 处理 {image_file.name} 失败: {e}")
                    continue
            
            print(f"  [完成] {person_name}: 成功处理 {success_count}/{len(image_files)} 张图片\n")
        
        print(f"\n[全部完成] 共处理 {total_images} 张图片，涉及 {len(person_names)} 个人")

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


async def batch_add_from_person_dir():
    """
    批量从 ./data/person 目录添加目标人物（直接执行）
    目录结构：./data/person/姓名/图片1.jpg, 图片2.jpg, ...
    """
    person_dir = "/data/nfs_storage/hxjm/python/reid/data/2026hanjia/2"
    print("=" * 60)
    print(f"批量添加目标人物（从 {person_dir} 目录）")
    print("=" * 60)
    
    adder = await ReIDTargetAdder().init()
    
    try:
        await adder.add_targets_from_person_dir(str(person_dir))
    finally:
        await adder.close()
    
    print("\n" + "=" * 60)
    print("处理完成")
    print("=" * 60)


if __name__ == "__main__":
    # 如果直接运行脚本，执行批量添加功能
    # 如果需要使用命令行参数，可以注释掉下面这行，取消注释 main() 调用
    asyncio.run(batch_add_from_person_dir())
    
    # 如果需要使用命令行参数，取消下面的注释，并注释掉上面的 asyncio.run
    # main()

