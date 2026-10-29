#!/usr/bin/env python3
"""
VAD Demo - 从数据库读取frame_vad_base64字段并保存为图片
"""

import os
import sys
import cv2
import base64
import asyncio
import numpy as np

# 添加模块路径（python 目录）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from base.postgresql.db_session import DBSession
from base.postgresql.config import DBConfig


async def main():
    """主函数：读取vad表中的base64图片并保存"""
    # 初始化数据库连接
    db_config = DBConfig(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "123456")
    )
    db = DBSession(config=db_config)
    
    try:
        # 初始化数据库连接池
        await db.initialize()
        print("[INFO] 数据库连接池初始化完成")
        
        # 查询vad表中所有记录
        print("[INFO] 开始查询vad表...")
        records = await db.select_tracklet("id = $1", "a4d36be5-85e9-4a53-9881-032f312041f3")
        print(f"[INFO] 查询到 {len(records)} 条记录")
        
        # 创建输出目录
        output_dir = "./output"
        os.makedirs(output_dir, exist_ok=True)
        print(f"[INFO] 输出目录: {output_dir}")
        
        # 处理每条记录
        success_count = 0
        fail_count = 0
        
        for i, record in enumerate(records, 1):
            try:
                record_id = record.get('id')
                frame_vad_base64 = record.get('frame_asset_base64')
                
                if not record_id:
                    print(f"[WARN] 记录 {i} 没有id字段，跳过")
                    fail_count += 1
                    continue
                
                if not frame_vad_base64:
                    print(f"[WARN] 记录 {i} (id={record_id}) 的frame_vad_base64字段为空，跳过")
                    fail_count += 1
                    continue
                
                # 解码base64为图片
                try:
                    # base64解码
                    image_data = base64.b64decode(frame_vad_base64)
                    
                    # 使用cv2解码图片
                    nparr = np.frombuffer(image_data, dtype=np.uint8)
                    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    img = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)   # 交换红蓝通道就变正常了

                    
                    # 保存图片，文件名使用id
                    output_path = os.path.join(output_dir, f"{record_id}.jpg")
                    cv2.imwrite(output_path, img)
                    
                    success_count += 1
                    if success_count % 10 == 0:
                        print(f"[INFO] 已处理 {success_count} 张图片...")
                    
                except Exception as e:
                    print(f"[ERROR] 处理记录 {i} (id={record_id}) 时出错: {e}")
                    fail_count += 1
                    continue
                    
            except Exception as e:
                print(f"[ERROR] 处理记录 {i} 时出错: {e}")
                fail_count += 1
                continue
        
        print(f"\n[INFO] 处理完成！成功: {success_count}, 失败: {fail_count}, 总计: {len(records)}")
        
    except Exception as e:
        print(f"[ERROR] 程序执行失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 关闭数据库连接
        await db.close()
        print("[INFO] 数据库连接已关闭")


if __name__ == "__main__":
    asyncio.run(main())

