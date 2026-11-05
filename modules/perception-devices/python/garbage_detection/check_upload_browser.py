"""Exercise the real upload HTTP flow with a labelled test image and a test detector."""
import io
import os
import subprocess
import threading
import time
from http.server import ThreadingHTTPServer

from PIL import Image, ImageDraw
from server import Camera, ROOT, Service, make_handler


class TestDetector:
    device = "test"

    def load(self):
        pass

    def infer(self, image, detailed=False, threshold=.25):
        time.sleep(1)
        return {"has_garbage": True, "targets": [{"label": "测试目标", "confidence": 0.8,
                "bbox": [100, 700, 250, 900], "region_id": "r3c1", "region_name": "左下"}],
                "scene_description": "浏览器流程测试", "reason": "替代推理器输出，用于验证界面", "unlocalized": False,
                "threshold": threshold, "passes": 6 if detailed else 2}


def main():
    runtime = ROOT / ".runtime"
    runtime.mkdir(exist_ok=True)
    image = Image.new("RGB", (800, 450), "#dfe9e6")
    ImageDraw.Draw(image).rectangle((80, 315, 200, 405), fill="#568277")
    path = runtime / "upload-test.png"
    image.save(path)
    cameras = {}
    for index in range(1, 5):
        camera = Camera("rtsp://offline.invalid", f"camera_{index}")
        camera.error = f"测试摄像头 {index} 离线"
        if index in (1, 4):
            import numpy as np
            preview = Image.new("RGB", (800, 450), "#568277" if index == 1 else "#967252")
            output = io.BytesIO()
            preview.save(output, "JPEG")
            camera.frame, camera.jpeg = np.array(preview), output.getvalue()
            # Keep the fixed browser fixtures fresh for the complete test run.
            camera.arrived, camera.captured_at, camera.error = time.monotonic() + 120, "2026-10-20T00:00:00+00:00", None
        cameras[camera.id] = camera
    service = Service(cameras, TestDetector())
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        env = dict(os.environ, UPLOAD_TEST_URL=f"http://127.0.0.1:{server.server_port}")
        subprocess.run(["node", "test_upload_browser.cjs"], cwd=ROOT, env=env, check=True)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
