"""Bounded JPEG history and short, timestamped candidate evidence."""
from collections import deque
import base64
from pathlib import Path
import shutil
import subprocess
import tempfile


class FrameBuffer:
    def __init__(self, seconds=8, fps=4, width=640):
        self.seconds, self.fps, self.width = seconds, fps, width
        self.frames = deque(maxlen=round(seconds * fps) + 4)
        self.last_stamp = None

    def clear(self):
        self.frames.clear()
        self.last_stamp = None

    def add(self, frame, stamp):
        if self.last_stamp is not None and stamp - self.last_stamp < 1 / self.fps - 1e-6:
            return
        import cv2
        if frame.shape[1] > self.width:
            frame = cv2.resize(frame, (self.width, round(frame.shape[0] * self.width / frame.shape[1])))
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if ok:
            self.frames.append((stamp, encoded.tobytes()))
            self.last_stamp = stamp
            while self.frames and stamp - self.frames[0][0] > self.seconds:
                self.frames.popleft()

    def between(self, start, end):
        return [(stamp, jpeg) for stamp, jpeg in self.frames if start <= stamp <= end]


def review_frames(path):
    """Resample the saved clip, never substitute the current camera picture."""
    import cv2
    capture = cv2.VideoCapture(str(path))
    try:
        count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = capture.get(cv2.CAP_PROP_FPS)
        if count < 8 or fps <= 0 or count / fps > 30:
            raise ValueError('原视频片段无法解码或时长无效')
        frames = []
        for i in range(8):
            index = round(i * (count - 1) / 7)
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, image = capture.read()
            if not ok:
                raise ValueError('原视频片段采样失败')
            ok, jpeg = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ok:
                raise ValueError('原视频片段采样编码失败')
            frames.append({'offset': round(index / fps, 3), 'jpeg': base64.b64encode(jpeg.tobytes()).decode('ascii')})
        return frames
    finally:
        capture.release()


def build_evidence(samples, box, source_shape, max_frames=8, duration=None):
    """Save raw context video; send an ordered sequence cropped with a fixed context ROI."""
    import cv2
    import numpy as np
    if len(samples) < 6 or samples[-1][0] - samples[0][0] < 2:
        raise ValueError("有效视频片段不足 2 秒，无法复核")
    if max(b[0] - a[0] for a, b in zip(samples, samples[1:])) > 1:
        raise ValueError("视频片段存在超过 1 秒的断帧，无法复核")
    captured_seconds = samples[-1][0] - samples[0][0]
    if duration is not None and not duration - 0.5 <= captured_seconds <= duration + 0.01:
        raise ValueError(f"有效视频片段不足 {duration:g} 秒，无法复核")
    images = [cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR) for _, jpeg in samples]
    if any(image is None for image in images):
        raise ValueError("视频证据解码失败")
    height, width = images[0].shape[:2]
    if any(image.shape[:2] != (height, width) for image in images):
        raise ValueError("视频证据分辨率不一致")
    # A sampled window excludes part of the final frame interval; keep its intended playback duration.
    fps = len(samples) / duration if duration is not None else (len(samples) - 1) / captured_seconds
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "clip.mp4"
        if not shutil.which("ffmpeg"):
            raise RuntimeError("缺少 ffmpeg，无法保存可播放片段")
        for index, (_, jpeg) in enumerate(samples):
            (Path(folder) / f"frame-{index:04d}.jpg").write_bytes(jpeg)
        try:
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(fps),
                            "-i", str(Path(folder) / "frame-%04d.jpg"), "-an", "-c:v", "libx264", "-threads", "2",
                            "-preset", "ultrafast", "-crf", "26", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)],
                           check=True, capture_output=True, timeout=30)
        except (subprocess.SubprocessError, OSError):
            raise RuntimeError("片段 H.264 编码失败") from None
        video = path.read_bytes()
    source_height, source_width = source_shape[:2]
    scale_x, scale_y = width / source_width, height / source_height
    padding = max(box[2] - box[0], box[3] - box[1]) * 0.4
    x1, y1 = max(0, int((box[0] - padding) * scale_x)), max(0, int((box[1] - padding) * scale_y))
    x2, y2 = min(width, int((box[2] + padding) * scale_x)), min(height, int((box[3] + padding) * scale_y))
    if x2 <= x1 or y2 <= y1:
        raise ValueError("可疑区域无效")
    indexes = sorted({round(i * (len(samples) - 1) / (max_frames - 1)) for i in range(max_frames)})
    frames = []
    for index in indexes:
        roi = images[index][y1:y2, x1:x2]
        ok, jpeg = cv2.imencode(".jpg", roi, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            raise ValueError("片段采样编码失败")
        frames.append({"offset": round(samples[index][0] - samples[0][0], 3),
                       "jpeg": base64.b64encode(jpeg.tobytes()).decode("ascii")})
    return video, frames, {"start": samples[0][0], "end": samples[-1][0], "frameCount": len(samples),
                           "duration": duration if duration is not None else round(captured_seconds, 2),
                           "capturedSeconds": round(captured_seconds, 3), "fps": round(fps, 2),
                           "roi": [x1, y1, x2, y2]}
