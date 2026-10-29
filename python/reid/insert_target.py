# -*- coding: utf-8 -*-
# pip install -i https://pypi.doubanio.com/simple/ 包名
# pip install -i https://pypi.tuna.tsinghua.edu.cn/simple 包名
# @Time    : 2025/12/25 10:32
# @Author  : beidanci

import os
import cv2
import torch
import numpy as np
import time, json
from collections import deque
from datetime import datetime
from pathlib import Path
from sklearn.metrics.pairwise import cosine_similarity

# CLIP-ReID 模型路径
import sys

sys.path.insert(0, "/home/guest/Documents/hxjm-monitor/mtx/python/reid/CLIP-ReID")

from config import cfg_base as cfg
from model.make_model import make_model



device = "cuda" if torch.cuda.is_available() else "cpu"
cfg.merge_from_file(
            "/home/guest/Documents/hxjm-monitor/mtx/python/reid/config/vit_base.yml"
        )
cfg.freeze()
reid_model = make_model(
    cfg,
    num_class=1,
    camera_num=1,
    view_num=1,
    device=device
)
reid_model.to(device)
reid_model.eval()
import torchvision.transforms as T
reid_transform = T.Compose([
    T.ToPILImage(),
    T.Resize((cfg.INPUT.SIZE_TRAIN[0], cfg.INPUT.SIZE_TRAIN[1])),
    T.ToTensor(),
    T.Normalize(mean=cfg.INPUT.PIXEL_MEAN, std=cfg.INPUT.PIXEL_STD)
])

def extract_feature(img_bgr, match=False):
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    tensor = reid_transform(img_rgb).unsqueeze(0).to(device)

    with torch.no_grad():
        feat = reid_model(tensor)
        feat = feat / feat.norm(dim=1, keepdim=True)

    return feat.cpu().numpy()
