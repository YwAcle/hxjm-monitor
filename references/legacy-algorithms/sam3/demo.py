import cv2
import numpy as np
from PIL import Image
import torch
import os

from sam3.model_builder import build_sam3_image_model
from sam3.model.sam3_image_processor import Sam3Processor


# ---------------------
# 1. 加载 SAM3 图像模型
# ---------------------
model = build_sam3_image_model(
    checkpoint_path="./models/sam3/sam3.pt",
    load_from_HF=False,
    device="cuda",
    eval_mode=True
)

# 降低置信度阈值以检测更多物体（"segment everything" 模式）
processor = Sam3Processor(model, device="cuda", confidence_threshold=0.1)


# ---------------------
# "分割一切"模式：处理单帧图像
# ---------------------
def process_frame(frame_rgb, prompt="object"):
    """
    处理单帧图像，使用"分割一切"模式
    
    Args:
        frame_rgb: RGB格式的numpy数组 (H, W, 3)
        prompt: 文本提示，默认"object"检测所有物体
    
    Returns:
        dict: 包含 masks, boxes, scores, ids
    """
    # 转换为 PIL Image
    if isinstance(frame_rgb, np.ndarray):
        image = Image.fromarray(frame_rgb)
    else:
        image = frame_rgb
    
    # 设置图像
    state = processor.set_image(image)
    
    # 尝试多个提示词以获得更好效果
    prompts = [prompt, "object", "thing", "item"]
    best_result = {"masks": np.array([]), "boxes": np.array([]), "scores": np.array([])}
    
    for p in prompts:
        temp_state = processor.set_text_prompt(p, state)
        masks = temp_state.get("masks", torch.tensor([]))
        
        # 如果当前提示词检测到了更多物体，则使用它
        if masks.numel() > 0 and (best_result["masks"].size == 0 or 
                                  masks.shape[0] > best_result["masks"].shape[0]):
            best_result = temp_state
    
    # 使用最佳结果
    masks = best_result.get("masks", torch.tensor([]))
    boxes = best_result.get("boxes", torch.tensor([]))
    scores = best_result.get("scores", torch.tensor([]))
    
    # 转换为 numpy
    if isinstance(masks, torch.Tensor) and masks.numel() > 0:
        masks = masks.squeeze(1).cpu().numpy()  # (N, 1, H, W) -> (N, H, W)
    else:
        masks = np.array([])
    if isinstance(boxes, torch.Tensor) and boxes.numel() > 0:
        boxes = boxes.cpu().numpy()
    else:
        boxes = np.array([])
    if isinstance(scores, torch.Tensor) and scores.numel() > 0:
        scores = scores.cpu().numpy()
    else:
        scores = np.array([])
    
    # 生成 IDs
    ids = list(range(len(masks))) if len(masks) > 0 else []
    
    return {
        "masks": masks,
        "boxes": boxes,
        "scores": scores,
        "ids": ids
    }


# ---------------------
# 测试 Demo（读取图片模拟流输入）
# ---------------------
def load_test_frames():
    """
    你可以将自己的图片放进 demo_frames/ 目录
    命名为 1.png, 2.png, ... 或 1.jpg, 2.jpg, ...
    """
    frames = []
    for i in range(1, 20):  # 支持更多帧
        # 尝试 png 和 jpg 格式
        for ext in ['.png', '.jpg', '.jpeg']:
            path = f"./demo_frames/{i}{ext}"
            img = cv2.imread(path)
            if img is not None:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                frames.append(img)
                break
    return frames


def visualize_result(frame_rgb, masks, boxes, ids, save_path):
    img = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

    for i, mask in enumerate(masks):
        color = np.random.randint(0, 255, (3,), dtype=np.uint8)
        img[mask > 0] = img[mask > 0] * 0.3 + color * 0.7
        # 移除了绘制边框的部分

    cv2.imwrite(save_path, img)
    print("Result saved:", save_path)


def main():
    frames = load_test_frames()

    if not frames:
        print("⚠️ No frames found! 请往 demo_frames/ 加入图片：1.png 或 1.jpg")
        return

    for idx, frame in enumerate(frames):
        print(f"\n=== Processing frame {idx} ===")
        output = process_frame(frame)

        masks = output["masks"]
        boxes = output["boxes"]
        ids = output["ids"]

        print("Masks:", len(masks), " Boxes:", len(boxes), " IDs:", ids)

        visualize_result(
            frame_rgb=frame,
            masks=masks,
            boxes=boxes,
            ids=ids,
            save_path=f"./result_{idx:03d}.jpg"
        )


if __name__ == "__main__":
    main()