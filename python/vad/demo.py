#!/usr/bin/env python3
"""
VAD Demo - 从数据库读取frame_vad_base64字段并保存为图片

用法：
  1) 查询所有记录：
     python demo.py

  2) 查询最新N条记录：
     python demo.py --latest 50

  3) 按anomaly_name查询（例如：fight, fire, fall）：
     python demo.py --anomaly-name fight
     注意：使用anomaly-name时，图片会保存到 output/{anomaly_name}/ 目录

  4) 按anomaly_name查询最新N条：
     python demo.py --anomaly-name fight --latest 10

  5) 清空输出目录后再保存：
     python demo.py --anomaly-name fight --latest 10 --clean-output

  6) 自定义数据库配置：
     python demo.py --anomaly-name fire --latest 20 --host <host> --port <port> --database <db> --user <user> --password <pwd>
"""

import os
import sys
import cv2
import base64
import asyncio
import argparse
import numpy as np
import shutil

# 添加模块路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from base.postgresql.db_session import DBSession
from base.postgresql.config import DBConfig


async def main():
    """主函数：读取vad表中的base64图片并保存"""
    # 解析命令行参数
    ap = argparse.ArgumentParser(
        description="从数据库读取vad表中的base64图片并保存"
    )
    ap.add_argument("--anomaly-name", type=str, default=None, 
                    help="按anomaly_name字段查询（例如：fight, fire, fall）")
    ap.add_argument("--latest", type=int, default=None, 
                    help="取最新的N条记录（不指定时查询所有记录）")
    ap.add_argument("--clean-output", action="store_true", 
                    help="每次执行时清空目标输出文件夹（默认：False，不清空）")
    ap.add_argument("--host", type=str, default=None, help="数据库主机地址")
    ap.add_argument("--port", type=int, default=None, help="数据库端口")
    ap.add_argument("--database", type=str, default=None, help="数据库名称")
    ap.add_argument("--user", type=str, default=None, help="数据库用户名")
    ap.add_argument("--password", type=str, default=None, help="数据库密码")
    args = ap.parse_args()
    
    # 初始化数据库连接
    db_config = DBConfig(
        host=args.host or os.getenv("DB_HOST", "localhost"),
        port=args.port or int(os.getenv("DB_PORT", "5432")),
        database=args.database or os.getenv("DB_NAME", "postgres"),
        user=args.user or os.getenv("DB_USER", "root"),
        password=args.password or os.getenv("DB_PASSWORD", "123456")
    )
    db = DBSession(config=db_config)
    
    try:
        # 初始化数据库连接池
        await db.initialize()
        print("[INFO] 数据库连接池初始化完成")
        
        # 查询vad表记录
        if args.anomaly_name:
            # 按anomaly_name条件查询
            query_desc = f"anomaly_name = '{args.anomaly_name}'"
            if args.latest:
                query_desc += f", 最新 {args.latest} 条"
            print(f"[INFO] 开始查询vad表（{query_desc}）...")
            records = await db.select_vad(
                "anomaly_name = $1", args.anomaly_name, 
                order_by="created_at DESC",
                limit=args.latest
            )
            print(f"[INFO] 查询到 {len(records)} 条记录（{query_desc}）")
        else:
            # 查询所有记录或最新N条
            if args.latest:
                print(f"[INFO] 开始查询vad表（最新 {args.latest} 条记录）...")
                records = await db.select_vad(order_by="created_at DESC", limit=args.latest)
                print(f"[INFO] 查询到 {len(records)} 条记录（最新 {args.latest} 条）")
            else:
                print("[INFO] 开始查询vad表（所有记录）...")
                records = await db.select_vad(order_by="created_at DESC")
                print(f"[INFO] 查询到 {len(records)} 条记录")
        
        # 确定输出目录
        if args.anomaly_name:
            # 如果指定了anomaly_name，创建对应的子目录
            output_dir = os.path.join("./output", args.anomaly_name)
        else:
            # 如果没有指定，使用默认输出目录
            output_dir = "./output"
        
        # 如果启用清空选项且目录存在，先清空目录
        if args.clean_output and os.path.exists(output_dir):
            try:
                shutil.rmtree(output_dir)
                print(f"[INFO] 已清空输出目录: {output_dir}")
            except Exception as e:
                print(f"[WARN] 清空输出目录失败: {e}，继续执行...")
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        print(f"[INFO] 输出目录: {output_dir}")
        
        # 处理每条记录
        success_count = 0
        fail_count = 0
        
        for i, record in enumerate(records, 1):
            try:
                record_id = record.get('id')
                frame_vad_base64 = record.get('frame_vad_base64')
                
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
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    
                    if img is None:
                        print(f"[ERROR] 记录 {i} (id={record_id}) 图片解码失败，跳过")
                        fail_count += 1
                        continue
                    
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
"""
# 查询所有记录
python demo.py

# 查询最新50条记录
python demo.py --latest 50

# 查询 fight 类型的最新10条记录
python demo.py --anomaly-name fight --latest 10

# 查询 fire 类型的最新20条记录
python demo.py --anomaly-name fire --latest 20

# 组合使用：查询 fall 类型的最新5条，并指定数据库配置
python demo.py --anomaly-name fall --latest 5 --host localhost --port 5432
"""
