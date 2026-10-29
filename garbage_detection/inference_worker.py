"""Run each bounded CPU inference in a child process so a timeout releases the job."""
import io
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class InferenceWorker:
    def __init__(self, model_path, device="cpu"):
        self.model_path = Path(model_path)
        self.device = device

    def load(self):
        if not (self.model_path / "model.safetensors").is_file():
            raise RuntimeError("未找到 Grounding DINO 模型，请按 README 配置模型目录。")

    def infer(self, image, detailed=False, threshold=.25):
        self.load()
        payload = io.BytesIO()
        image.save(payload, "PNG")
        command = [sys.executable, "-B", str(Path(__file__).resolve()), str(self.model_path),
                   self.device, "1" if detailed else "0", str(threshold), str(os.getpid())]
        try:
            completed = subprocess.run(command, input=payload.getvalue(), capture_output=True,
                                       timeout=120, cwd=ROOT)
        except subprocess.TimeoutExpired:
            raise RuntimeError("图片检测超过 120 秒，已终止推理并释放任务；请使用普通模式或裁剪图片后重试。") from None
        if completed.returncode:
            print(completed.stderr.decode("utf-8", errors="replace")[-4000:], flush=True)
            raise RuntimeError("目标检测执行失败，请查看日志；可以重新提交图片。")
        result = json.loads(completed.stdout)
        if "error" in result:
            raise ValueError(result["error"])
        self.device = result.get("device", self.device)
        return result


def main():
    # Linux parent-death signal prevents model workers surviving stop.sh or a server crash.
    import ctypes
    expected_parent = int(sys.argv[5])
    if ctypes.CDLL(None).prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
        raise RuntimeError("无法设置推理进程退出保护。")
    if os.getppid() != expected_parent:
        return
    from PIL import Image
    from detector import Detector
    data = sys.stdin.buffer.read()
    image = Image.open(io.BytesIO(data)).convert("RGB")
    detector = Detector(sys.argv[1], sys.argv[2])
    try:
        result = detector.infer(image, detailed=sys.argv[3] == "1", threshold=float(sys.argv[4]))
    except ValueError as exc:
        result = {"error": str(exc)}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
