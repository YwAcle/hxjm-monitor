import time
import torch
import numpy as np
import cv2
from PIL import Image
import torchreid

# -----------------------------------------
# 1. 加载 ReID 模型
# -----------------------------------------
def load_reid_model(device="cuda"):
    start = time.perf_counter()

    model = torchreid.models.build_model(
        name='osnet_x0_25',
        num_classes=1000,
        pretrained=True
    )
    model.to(device)
    model.eval()

    # ----------------------------------------
    # 🚀 Warm-up：预热模型，加速后续推理
    # ----------------------------------------
    with torch.no_grad():
        dummy = torch.randn(1, 3, 256, 128).to(device)
        model(dummy)

    load_time = (time.perf_counter() - start) * 1000
    print(f"[TIME] 模型加载耗时: {load_time:.2f} ms")

    return model



# -----------------------------------------
# 2. 特征提取函数（带耗时）
# -----------------------------------------
def extract_feature(model, img_path, device="cuda"):
    start = time.perf_counter()

    # 读取并转 RGB
    img = cv2.imread(img_path)
    if img is None:
        raise ValueError(f"无法读取图片: {img_path}")

    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img_pil = Image.fromarray(img)

    # torchreid transform
    _, transform = torchreid.data.transforms.build_transforms(
        height=256, width=128, is_train=False
    )

    img_tensor = transform(img_pil).unsqueeze(0).to(device)

    # 提取特征
    with torch.no_grad():
        feat = model(img_tensor)

    feat = feat.detach().cpu().numpy()
    feat = feat / np.linalg.norm(feat)

    extract_time = (time.perf_counter() - start) * 1000
    print(f"[TIME] 特征提取耗时({img_path}): {extract_time:.2f} ms")

    return feat


# -----------------------------------------
# 3. 相似度计算
# -----------------------------------------
def cosine_similarity(f1, f2):
    return float(np.dot(f1, f2.T))

def euclidean_distance(f1, f2):
    return float(np.linalg.norm(f1 - f2))


# -----------------------------------------
# 4. 测试入口
# -----------------------------------------
if __name__ == "__main__":
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = load_reid_model(device)

    imgA = "/home/guest/Documents/hxjm-monitor/mtx/python/reid/data/zjh1.png"
    imgB = "/home/guest/Documents/hxjm-monitor/mtx/python/reid/data/person1.png"
    imgC = "/home/guest/Documents/hxjm-monitor/mtx/python/reid/data/person3.png"

    # 特征提取
    featA = extract_feature(model, imgA, device)
    featB = extract_feature(model, imgB, device)
    featC = extract_feature(model, imgC, device)

    # ==========================
    # A vs B
    # ==========================
    cos_AB = cosine_similarity(featA, featB)
    dist_AB = euclidean_distance(featA, featB)
    print("\n=== A vs B ===")
    print(f"余弦相似度 Cosine = {cos_AB:.4f}")
    print(f"欧式距离 Euclidean = {dist_AB:.4f}")

    # ==========================
    # A vs C
    # ==========================
    cos_AC = cosine_similarity(featA, featC)
    dist_AC = euclidean_distance(featA, featC)
    print("\n=== A vs C ===")
    print(f"余弦相似度 Cosine = {cos_AC:.4f}")
    print(f"欧式距离 Euclidean = {dist_AC:.4f}")

    # ==========================
    # B vs C
    # ==========================
    cos_BC = cosine_similarity(featB, featC)
    dist_BC = euclidean_distance(featB, featC)
    print("\n=== B vs C ===")
    print(f"余弦相似度 Cosine = {cos_BC:.4f}")
    print(f"欧式距离 Euclidean = {dist_BC:.4f}")
