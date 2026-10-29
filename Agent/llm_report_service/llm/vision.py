from __future__ import annotations

import base64
from io import BytesIO

import numpy as np
from decord import VideoReader, cpu
from PIL import Image

# 把前端或数据库传来的 Base64 图片转换成 PIL 图片
def decode_base64_image(b64: str) -> Image.Image | None:
    if b64 is None:
        return None

    b64 = b64.strip()
    if b64.startswith("data:image") and "," in b64:
        b64 = b64.split(",", 1)[1]

    try:
        raw = base64.b64decode(b64, validate=False)
        return Image.open(BytesIO(raw)).convert("RGB")
    except Exception:
        return None

def get_index(bound, fps, max_frame, first_idx=0, num_segments=8):
    if bound:
        start, end = bound[0], bound[1]
    else:
        start, end = -100000, 100000
    start_idx = max(first_idx, round(start * fps))
    end_idx = min(round(end * fps), max_frame)
    seg_size = float(end_idx - start_idx) / num_segments
    frame_indices = np.array(
        [int(start_idx + (seg_size / 2) + np.round(seg_size * idx)) for idx in range(num_segments)]
    )
    return frame_indices


# 视频文件 → PIL 图片列表，默认在整个视频中均匀采样8帧
def load_video_frame_images(
    video_path: str,
    bound=None,
    num_segments: int = 8,
) -> list[Image.Image]:
    """采样视频帧，并转换为 RGB PIL 图像。"""

    vr = VideoReader(video_path, ctx=cpu(0), num_threads=1)
    max_frame = len(vr) - 1
    if max_frame < 0:
        return []
    fps = float(vr.get_avg_fps())
    frame_indices = get_index(
        bound,
        fps,
        max_frame,
        first_idx=0,
        num_segments=num_segments,
    )
    return [
        Image.fromarray(vr[int(frame_index)].asnumpy()).convert("RGB")
        for frame_index in frame_indices
    ]

# 用于远程 SGLang/OpenAI 兼容接口
def image_to_data_url(
    image: Image.Image,
    *,
    max_side: int = 1280,
    jpeg_quality: int = 88,
) -> str:
    """将图像编码为大小受限的 JPEG data URL，供远程模型接口使用。"""

    image = image.convert("RGB")
    width, height = image.size
    longest_side = max(width, height)
    if longest_side > max_side:
        scale = max_side / longest_side
        image = image.resize(
            (max(1, round(width * scale)), max(1, round(height * scale))),
            Image.Resampling.LANCZOS,
        )

    output = BytesIO()
    image.save(output, format="JPEG", quality=jpeg_quality, optimize=True)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"
