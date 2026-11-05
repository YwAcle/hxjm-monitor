# -*- coding: utf-8 -*-
# Final Demo: YOLO + CLIP static fight detection
# Author: beidanci (refined)

import cv2
import torch
import clip
import math
from PIL import Image
from ultralytics import YOLO

# ------------------------------------------------
# 1. 模型加载
# ------------------------------------------------
device = "cuda" if torch.cuda.is_available() else "cpu"

# YOLOv8 行人检测
yolo = YOLO("./yolov8n.pt")

# CLIP
clip_model, preprocess = clip.load("ViT-B/32", device=device)
clip_model.eval()

# ------------------------------------------------
# 2. CLIP prompts（正 / 负类，非常关键）
# ------------------------------------------------
fight_prompts = [
    "a violent fight between two people",      # 原始
    "two people hitting each other",            # 原始

    "two people fighting violently",
    "two people physically attacking each other",
    "two people punching and hitting each other",
    "two people engaged in violent physical combat"
]




normal_prompts = [
    "people walking side by side",              # 原始
    "people walking alongside each other",
    "people walking together peacefully"
]





with torch.no_grad():
    fight_text_features = clip_model.encode_text(
        clip.tokenize(fight_prompts).to(device)
    )
    fight_text_features /= fight_text_features.norm(dim=-1, keepdim=True)

    normal_text_features = clip_model.encode_text(
        clip.tokenize(normal_prompts).to(device)
    )
    normal_text_features /= normal_text_features.norm(dim=-1, keepdim=True)

# ------------------------------------------------
# 3. 工具函数
# ------------------------------------------------
def center(box):
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2, (y1 + y2) / 2)

def distance(b1, b2):
    c1, c2 = center(b1), center(b2)
    return math.hypot(c1[0] - c2[0], c1[1] - c2[1])

def merge_boxes(b1, b2):
    return [
        min(b1[0], b2[0]),
        min(b1[1], b2[1]),
        max(b1[2], b2[2]),
        max(b1[3], b2[3]),
    ]

# ------------------------------------------------
# 4. 主检测逻辑
# ------------------------------------------------
def fight_detection(image_path):
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError("Image not found")

    # YOLO 推理（只检测 person）
    results = yolo(img, conf=0.5, classes=[0])[0]

    persons = []
    for box in results.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        persons.append([x1, y1, x2, y2])

    if len(persons) < 2:
        print("❌ 少于两个人，无法判断")
        return img

    # 找交互对
    candidate_boxes = []
    for i in range(len(persons)):
        for j in range(i + 1, len(persons)):
            print("距离：",distance(persons[i], persons[j]))
            if distance(persons[i], persons[j]) < 250:  # 距离阈值（经验）
                candidate_boxes.append(merge_boxes(persons[i], persons[j]))

    if not candidate_boxes:
        print("✅ 未发现近距离交互")
        return img

    # ------------------------------------------------
    # CLIP 判断
    # ------------------------------------------------
    for box in candidate_boxes:
        x1, y1, x2, y2 = map(int, box)
        roi = img[y1:y2, x1:x2]
        if roi.size == 0:
            continue

        roi_pil = Image.fromarray(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB))
        roi_tensor = preprocess(roi_pil).unsqueeze(0).to(device)

        with torch.no_grad():
            image_features = clip_model.encode_image(roi_tensor)
            image_features /= image_features.norm(dim=-1, keepdim=True)

            fight_sim = (image_features @ fight_text_features.T)[0]
            normal_sim = (image_features @ normal_text_features.T)[0]

            fight_score = fight_sim.mean().item()
            normal_score = normal_sim.mean().item()
            diff_score = fight_score - normal_score
            print("---- Fight prompts similarity ----")
            for p, s in zip(fight_prompts, fight_sim):
                print(f"{p:40s} : {s.item():.3f}")

            print("---- Normal prompts similarity ----")
            for p, s in zip(normal_prompts, normal_sim):
                print(f"{p:40s} : {s.item():.3f}")

        print(
            f"[CLIP] fight={fight_score:.3f}, "
            f"normal={normal_score:.3f}, "
            f"diff={diff_score:.3f}"
        )

        # 判定阈值（Demo 推荐 0.05 左右）
        if diff_score > 0.05:
            label = f"FIGHT {diff_score:.2f}"
            color = (0, 0, 255)
            thickness = 3
        else:
            label = f"NORMAL {diff_score:.2f}"
            color = (0, 255, 0)
            thickness = 2

        cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)
        cv2.putText(
            img,
            label,
            (x1, y1 - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            color,
            2,
        )

    return img

# ------------------------------------------------
# 5. Demo 入口
# ------------------------------------------------
if __name__ == "__main__":
    image_path = "data/1.jpg"  # 替换为你的测试图
    result = fight_detection(image_path)

    cv2.imshow("YOLO + CLIP Fight Detection (Final Demo)", result)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
