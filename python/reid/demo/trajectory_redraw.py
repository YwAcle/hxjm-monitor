# -*- coding: utf-8 -*-
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
根据数据库记录重新绘制轨迹并保存图片。

从数据库读取 tracklet 记录，获取 frame_asset_base64、trajectory_points、color_rgb，
然后在图像上绘制轨迹并保存。

使用 db_session.py 框架进行数据库操作。

用法：
  1) 默认全表：
     python trajectory_redraw.py

  2) 指定 tracklet_id：
     python trajectory_redraw.py --tracklet-id <uuid>

  3) 最新 N 条：
     python trajectory_redraw.py --latest 10

  4) 自定义数据库配置：
     python trajectory_redraw.py --host <host> --port <port> --database <db> --user <user> --password <pwd>

输出：
  默认保存到 ./tracklet_vis_redraw/<tracklet_id>.jpg
"""

import os
import sys
import re
import json
import base64
import argparse
import asyncio
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import cv2

# 添加模块路径（python 目录）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from base.postgresql.db_session import DBSession
from base.postgresql.config import DBConfig


def _strip_data_url_prefix(b64: str) -> str:
    """兼容 data:image/jpeg;base64,xxxx 格式"""
    if not b64:
        return b64
    m = re.match(r"^data:.*?;base64,(.*)$", b64, flags=re.IGNORECASE | re.DOTALL)
    return m.group(1) if m else b64


def decode_base64_image_to_bgr(b64: str) -> np.ndarray:
    """解码base64图片为BGR格式的numpy数组"""
    b64 = _strip_data_url_prefix(b64)
    raw = base64.b64decode(b64)
    nparr = np.frombuffer(raw, dtype=np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise ValueError("cv2.imdecode failed (base64 image invalid)")
    return img_bgr


def parse_jsonb(val: Any) -> Optional[Dict[str, Any]]:
    """解析JSONB字段值"""
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


def stable_color_bgr(seed: int) -> Tuple[int, int, int]:
    """生成稳定的BGR颜色"""
    seed = int(seed) & 0xFFFFFFFF
    rng = np.random.default_rng(seed)
    b = int(rng.integers(60, 256))
    g = int(rng.integers(60, 256))
    r = int(rng.integers(60, 256))
    return (b, g, r)


def color_from_color_rgb_any(color_rgb: Any, fallback_seed: int = 0) -> Tuple[int, int, int]:
    """
    将color_rgb转换为OpenCV BGR格式
    支持：
      - PostgreSQL int2[]/smallint[]：如 {200,242,189} / [200,242,189] / (200,242,189)  -> 按 RGB 解析
      - '#RRGGBB' / '0xRRGGBB'
      - int (0..0xFFFFFF) 认为是 0xRRGGBB
      - 其它情况 fallback 稳定色
    """
    if color_rgb is None:
        return stable_color_bgr(fallback_seed)

    # 1) 数组：{200,242,189} 通常被 asyncpg 解出来是 list/tuple
    if isinstance(color_rgb, (list, tuple)) and len(color_rgb) == 3:
        try:
            r = int(color_rgb[0])
            g = int(color_rgb[1])
            b = int(color_rgb[2])
            r = max(0, min(255, r))
            g = max(0, min(255, g))
            b = max(0, min(255, b))
            return (b, g, r)  # OpenCV BGR
        except Exception:
            return stable_color_bgr(fallback_seed)

    # 2) 字符串 '#RRGGBB' 或 '0xRRGGBB'
    if isinstance(color_rgb, str):
        s = color_rgb.strip()
        try:
            if s.startswith("#") and len(s) == 7:
                c = int(s[1:], 16)
                r = (c >> 16) & 0xFF
                g = (c >> 8) & 0xFF
                b = c & 0xFF
                return (b, g, r)
            if s.lower().startswith("0x"):
                c = int(s, 16)
                r = (c >> 16) & 0xFF
                g = (c >> 8) & 0xFF
                b = c & 0xFF
                return (b, g, r)
        except Exception:
            return stable_color_bgr(fallback_seed)

    # 3) int：认为是 0xRRGGBB
    try:
        c = int(color_rgb)
        if 0 <= c <= 0xFFFFFF:
            r = (c >> 16) & 0xFF
            g = (c >> 8) & 0xFF
            b = c & 0xFF
            return (b, g, r)
        # 否则当作 seed
        return stable_color_bgr(c if c != 0 else fallback_seed)
    except Exception:
        return stable_color_bgr(fallback_seed)


def draw_trajectory(
    img_bgr: np.ndarray,
    points: List[Dict[str, Any]],
    color_bgr: Tuple[int, int, int],
    thickness: int = 5,             # 线条粗细
    point_radius: int = 4,          # 起点/终点圆点大小
    arrow_step: int = 1,            # 每隔N段画一个箭头（>=1）
    arrow_tip_length: float = 0.1, # 箭头大小比例
) -> np.ndarray:
    """
    在BGR图像上绘制轨迹
    
    Args:
        img_bgr: BGR格式的图像
        points: [{"x":..., "y":..., "ts":"2025-12-28T14:27:22.450718"}, ...]
        color_bgr: BGR格式的颜色 (B, G, R)
        thickness: 线条粗细
        point_radius: 起点/终点圆点大小
        arrow_step: 每隔N段画一个箭头
        arrow_tip_length: 箭头大小比例
    
    Returns:
        绘制轨迹后的图像
    """
    h, w = img_bgr.shape[:2]

    # 过滤+解析点
    cleaned: List[Tuple[float, float, Optional[str]]] = []
    for p in points:
        if not isinstance(p, dict):
            continue
        x, y = p.get("x"), p.get("y")
        if x is None or y is None:
            continue
        try:
            xf = float(x)
            yf = float(y)
        except Exception:
            continue
        ts = p.get("ts")
        cleaned.append((xf, yf, ts))

    if not cleaned:
        return img_bgr

    # 按时间戳排序（ISO8601 字符串直接字典序即可）
    # 如果 ts 可能为空：放到最后
    cleaned.sort(key=lambda t: (t[2] is None, t[2] or ""))

    # 转成像素坐标并裁剪
    pts: List[Tuple[int, int]] = []
    for xf, yf, _ in cleaned:
        xi = int(round(xf))
        yi = int(round(yf))
        xi = max(0, min(w - 1, xi))
        yi = max(0, min(h - 1, yi))
        pts.append((xi, yi))

    if len(pts) == 1:
        out = img_bgr.copy()
        cv2.circle(out, pts[0], point_radius, color_bgr, -1)
        return out

    out = img_bgr.copy()

    # 画轨迹线
    cv2.polylines(out, [np.array(pts, dtype=np.int32)], False, color_bgr, thickness)

    # 按时间方向画箭头（早->晚）
    # 每 arrow_step 段画一个箭头，避免太密
    step = max(1, int(arrow_step))
    for i in range(0, len(pts) - 1, step):
        p1 = pts[i]
        p2 = pts[i + 1]
        # 如果两点重合就跳过
        if p1 == p2:
            continue
        cv2.arrowedLine(
            out,
            p1,
            p2,
            color_bgr,
            thickness=thickness,
            tipLength=arrow_tip_length,
            line_type=cv2.LINE_AA,
        )

    # 起点/终点
    cv2.circle(out, pts[0], point_radius, color_bgr, -1)
    cv2.circle(out, pts[-1], point_radius, color_bgr, -1)

    return out


async def fetch_tracklets(db: DBSession, tracklet_id: Optional[str], latest: Optional[int]) -> List:
    """
    查询 tracklet 记录（只查询 end_ts 不为空的已结束轨迹）
    
    Args:
        db: DBSession 实例
        tracklet_id: 可选的 tracklet ID（UUID字符串）
        latest: 可选的最新 N 条记录
    
    Returns:
        tracklet 记录列表（只包含 end_ts 不为空的记录）
    """
    # 只查询 end_ts 不为空的轨迹（已结束的轨迹）
    end_ts_condition = "end_ts IS NOT NULL"
    
    if tracklet_id:
        # 按 tracklet_id 查询，同时要求 end_ts 不为空
        records = await db.select_tracklet(f"id = $1 AND {end_ts_condition}", tracklet_id)
        return list(records)

    if latest is not None:
        # 查询最新 N 条已结束的轨迹
        records = await db.select_tracklet(
            where=end_ts_condition,
            order_by="created_at DESC",
            limit=int(latest)
        )
        return list(records)

    # 默认：全表查询已结束的轨迹（按创建时间降序）
    records = await db.select_tracklet(
        where=end_ts_condition,
        order_by="created_at DESC"
    )
    return list(records)


async def process_tracklet(row: Dict[str, Any], outdir: str) -> bool:
    """
    处理单个 tracklet 记录：绘制轨迹并保存
    
    Args:
        row: tracklet 记录字典
        outdir: 输出目录
    
    Returns:
        是否处理成功
    """
    tid = str(row["id"])
    
    # 检查 end_ts 是否存在（只处理已结束的轨迹）
    end_ts = row.get("end_ts")
    if end_ts is None:
        print(f"[WARN] tracklet={tid} end_ts 为空，跳过（只处理已结束的轨迹）")
        return False
    
    # 获取必要字段
    frame_asset_base64 = row.get("frame_asset_base64")
    trajectory_points = row.get("trajectory_points")
    color_rgb = row.get("color_rgb")
    
    if not frame_asset_base64:
        print(f"[WARN] tracklet={tid} 没有 frame_asset_base64，跳过")
        return False
    
    if not trajectory_points:
        print(f"[WARN] tracklet={tid} 没有 trajectory_points，跳过")
        return False
    
    try:
        # 解码 base64 图像
        img_bgr = decode_base64_image_to_bgr(frame_asset_base64)
        
        # 解析 trajectory_points
        traj = parse_jsonb(trajectory_points) or {}
        points = traj.get("points") or []
        if not isinstance(points, list):
            points = []
        
        if not points:
            print(f"[WARN] tracklet={tid} trajectory_points 中没有有效的点，跳过绘制")
            # 即使没有轨迹点，也保存原始图像
            out_path = os.path.join(outdir, f"{tid}.jpg")
            ok = cv2.imwrite(out_path, img_bgr)
            if ok:
                print(f"[OK] saved (no trajectory): {out_path}")
            else:
                print(f"[ERR] save failed: {out_path}")
            return ok
        
        # 获取颜色（使用 tracklet_id 的 hash 作为 fallback seed）
        fallback_seed = hash(tid) & 0xFFFFFFFF
        color_bgr = color_from_color_rgb_any(color_rgb, fallback_seed=fallback_seed)
        
        # 绘制轨迹
        img_with_trajectory = draw_trajectory(
            img_bgr,
            points,
            color_bgr,
            thickness=5,
            point_radius=4,
            arrow_step=1,
            arrow_tip_length=0.1
        )
        
        # 保存结果
        out_path = os.path.join(outdir, f"{tid}.jpg")
        ok = cv2.imwrite(out_path, img_with_trajectory)
        
        if ok:
            print(f"[OK] saved: {out_path} (trajectory points: {len(points)})")
            return True
        else:
            print(f"[ERR] save failed: {out_path}")
            return False
            
    except Exception as e:
        print(f"[ERR] tracklet={tid} 处理失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    ap = argparse.ArgumentParser(
        description="从数据库读取 tracklet 记录，绘制轨迹并保存图片"
    )
    ap.add_argument("--tracklet-id", type=str, default=None, help="指定 tracklet.id (uuid)")
    ap.add_argument("--latest", type=int, default=5, help="取最新 N 条（不指定 tracklet-id 时生效）")
    ap.add_argument("--outdir", type=str, default="./tracklet_vis_redraw", help="输出目录")
    ap.add_argument("--host", type=str, default=None, help="数据库主机地址")
    ap.add_argument("--port", type=int, default=None, help="数据库端口")
    ap.add_argument("--database", type=str, default=None, help="数据库名称")
    ap.add_argument("--user", type=str, default=None, help="数据库用户名")
    ap.add_argument("--password", type=str, default=None, help="数据库密码")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

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
        rows = await fetch_tracklets(db, args.tracklet_id, args.latest)
        if not rows:
            print("[ERR] 没找到 tracklet 记录")
            return

        print(f"[INFO] fetched {len(rows)} tracklets")

        # 处理每个 tracklet
        success_count = 0
        for row in rows:
            if await process_tracklet(row, args.outdir):
                success_count += 1

        print(f"\n[SUMMARY] 成功处理 {success_count}/{len(rows)} 个 tracklet")

    except Exception as e:
        print(f"[ERR] 处理过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 关闭数据库连接池
        await db.close()
        print("[INFO] 数据库连接池已关闭")


if __name__ == "__main__":
    asyncio.run(main())

