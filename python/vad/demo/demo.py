#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shutil
from ultralytics import YOLO

def main():
    # ====== 直接写死参数（对应你之前命令行） ======
    input_video = "./fall_video.mp4"
    output_video = "./out.mp4"
    weights = "./best.pt"
    device = 0  # 等同于 --device 0
    conf = 0.25
    imgsz = 640

    # Ultralytics 输出目录（会自动创建 runs/detect/predict、predict2...）
    project = "runs/detect"
    name = "predict"

    if not os.path.exists(input_video):
        raise FileNotFoundError(f"input not found: {input_video}")
    if not os.path.exists(weights):
        raise FileNotFoundError(f"weights not found: {weights}")

    # ====== 推理并保存 ======
    model = YOLO(weights)

    results = model.predict(
        source=input_video,
        device=device,
        conf=conf,
        imgsz=imgsz,
        save=True,
        project=project,
        name=name,
        verbose=True,
    )

    # ====== 把 Ultralytics 输出的视频复制/重命名为 ./out.mp4 ======
    # results[0].save_dir 是本次输出目录（例如 runs/detect/predict 或 predict2）
    save_dir = str(results[0].save_dir)

    # 在目录里找输出视频（通常是同名视频文件，可能是 .mp4 或 .avi，依赖环境）
    candidates = []
    for fn in os.listdir(save_dir):
        lower = fn.lower()
        if lower.endswith((".mp4", ".avi", ".mov", ".mkv")):
            candidates.append(os.path.join(save_dir, fn))

    if not candidates:
        raise RuntimeError(f"no output video found in {save_dir}")

    # 如果有多个，优先选择与输入同名的；否则取第一个
    base = os.path.splitext(os.path.basename(input_video))[0].lower()
    picked = None
    for p in candidates:
        if os.path.splitext(os.path.basename(p))[0].lower() == base:
            picked = p
            break
    if picked is None:
        picked = candidates[0]

    # 复制到你想要的输出路径（覆盖）
    shutil.copyfile(picked, output_video)
    print(f"[DONE] Ultralytics saved: {picked}")
    print(f"[DONE] Copied to: {output_video}")

if __name__ == "__main__":
    main()
