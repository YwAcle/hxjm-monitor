"""Four cameras, one inference job, and a standalone same-origin dashboard."""
import base64
import errno
import io
import json
import os
import threading
import time
import uuid
import warnings
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from inference_worker import InferenceWorker as Detector
from detector import LABELS

ROOT = Path(__file__).resolve().parent
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_PIXELS = 20_000_000


def decode_upload(data):
    from PIL import Image, ImageOps, UnidentifiedImageError
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("请选择不超过 10 MB 的图片。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in ("JPEG", "PNG", "WEBP"):
                    raise ValueError("仅支持 JPG、PNG、WebP 图片。")
                if image.width * image.height > MAX_UPLOAD_PIXELS:
                    raise ValueError("图片不能超过 2000 万像素。")
                image.load()
                image = ImageOps.exif_transpose(image).convert("RGBA")
                background = Image.new("RGBA", image.size, "white")
                background.alpha_composite(image)
                output = io.BytesIO()
                background.convert("RGB").save(output, "PNG")
                return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError("无法读取图片，请选择有效的 JPG、PNG 或 WebP 文件。") from None


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class Camera:
    def __init__(self, url, camera_id="camera_3", name=None):
        self.url = url
        self.id = camera_id
        self.name = name or f"摄像头 {camera_id.rsplit('_', 1)[-1]}"
        self.lock = threading.Lock()
        self.frame = None
        self.jpeg = None
        self.captured_at = None
        self.arrived = 0
        self.error = f"正在连接{self.name}…" if url else f"{self.name}尚未配置视频地址。"
        self.stop = threading.Event()

    def snapshot(self):
        with self.lock:
            if self.frame is None or time.monotonic() - self.arrived > 10:
                raise RuntimeError(self.error or "摄像头画面已过期，正在等待新画面。")
            return self.frame.copy(), self.jpeg, self.captured_at

    def run(self):
        import cv2
        transport = os.getenv("GARBAGE_RTSP_TRANSPORT", "udp")
        # The camera network has multi-second stalls; bound probing and avoid 32 decoder threads per feed.
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            f"rtsp_transport;{transport}|analyzeduration;1000000|probesize;262144"
            "|buffer_size;2097152|reorder_queue_size;1024|max_delay;1000000")
        while not self.stop.is_set():
            capture = cv2.VideoCapture()
            try:
                opened = capture.open(self.url, cv2.CAP_FFMPEG, [
                    cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 15000,
                    cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10000,
                    cv2.CAP_PROP_N_THREADS, 1])
                if not opened:
                    raise RuntimeError(f"无法连接{self.name}，请检查网络、账号及 RTSP 地址。")
                encoded_at = 0
                while not self.stop.is_set():
                    ok, frame = capture.read()
                    if not ok:
                        raise RuntimeError(f"{self.name}读取中断，正在重连。")
                    # Drain the source continuously; only encode the newest preview twice a second.
                    if time.monotonic() - encoded_at < 0.5:
                        continue
                    ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    if not ok:
                        raise RuntimeError("画面编码失败。")
                    encoded_at = time.monotonic()
                    with self.lock:
                        self.frame, self.jpeg = frame, jpg.tobytes()
                        self.captured_at, self.arrived, self.error = timestamp(), encoded_at, None
            except Exception as exc:
                with self.lock:
                    self.frame = self.jpeg = None
                    self.error = str(exc) if isinstance(exc, RuntimeError) else "摄像头解码失败，正在重连。"
            finally:
                capture.release()
            self.stop.wait(3)


class Service:
    def __init__(self, camera, detector):
        self.cameras = camera if isinstance(camera, dict) else {camera.id: camera}
        self.camera = self.cameras.get("camera_3", next(iter(self.cameras.values())))
        self.detector = detector
        self.lock = threading.Lock()
        self.job = {"state": "idle", "id": None, "error": None}
        self.result = None

    def get_camera(self, camera_id=None):
        camera_id = camera_id or self.camera.id
        if camera_id not in self.cameras:
            raise ValueError("摄像头编号无效，请选择已配置的摄像头。")
        return self.cameras[camera_id]

    def status(self, camera_id=None):
        selected = self.get_camera(camera_id)
        cameras = []
        for item in self.cameras.values():
            with item.lock:
                online = item.frame is not None and time.monotonic() - item.arrived <= 10
                cameras.append({"id": item.id, "name": item.name, "online": online,
                                "captured_at": item.captured_at if online else None,
                                "error": None if online else (item.error or "画面已过期，正在等待新画面。")})
        camera = next(item for item in cameras if item["id"] == selected.id)
        with self.lock:
            job = dict(self.job)
        return {"camera": camera, "cameras": cameras, "categories": list(dict.fromkeys(LABELS.values())),
                "job": job, "device": self.detector.device, "pid": os.getpid()}

    def start(self, image_bytes=None, file_name=None, detailed=False, threshold=.25, camera_id=None):
        with self.lock:
            if self.job["state"] in ("loading", "running"):
                return None
            source = "upload" if image_bytes is not None else "camera"
            if source == "camera":
                camera = self.get_camera(camera_id)
                camera_id = camera.id
                _, jpg, captured_at = camera.snapshot()
            else:
                jpg, captured_at = image_bytes, timestamp()
                camera_id = None
            job_id = uuid.uuid4().hex
            self.job = {"id": job_id, "state": "loading", "error": None,
                        "started_at": timestamp(), "source": source, "file_name": file_name,
                        "detailed": detailed, "threshold": threshold, "camera_id": camera_id}
            threading.Thread(target=self.detect, args=(job_id, jpg, captured_at, source, file_name, detailed, threshold, camera_id), daemon=True).start()
            return job_id

    def detect(self, job_id, jpg, captured_at, source="camera", file_name=None, detailed=False, threshold=.25, camera_id=None):
        started = time.monotonic()
        try:
            from PIL import Image
            self.detector.load()
            with self.lock:
                self.job["state"] = "running"
            with Image.open(io.BytesIO(jpg)) as original:
                image = original.convert("RGB")
            if detailed or threshold != .25:
                result = self.detector.infer(image, detailed=detailed, threshold=threshold)
            else:
                result = self.detector.infer(image)
            width, height = image.size
            preview = jpg
            if source == "upload":
                # Keep full resolution for inference but bound the browser/result payload.
                image.thumbnail((2048, 2048))
                output = io.BytesIO()
                image.save(output, "JPEG", quality=90)
                preview = output.getvalue()
            result.update({"id": job_id, "camera_id": (camera_id or self.camera.id) if source == "camera" else None,
                           "source": source, "file_name": file_name, "captured_at": captured_at,
                           "completed_at": timestamp(), "elapsed_seconds": round(time.monotonic() - started, 1),
                           "image_width": width, "image_height": height,
                           "coordinate_space": "image_0_1000", "map_calibrated": False,
                           "image": "data:image/jpeg;base64," + base64.b64encode(preview).decode("ascii")})
            with self.lock:
                self.result = result
                self.job["state"] = "done"
        except Exception as exc:
            print(f"Detection failed: {type(exc).__name__}: {exc}", flush=True)
            message = str(exc) if isinstance(exc, (RuntimeError, ValueError)) else "检测执行失败，请查看服务日志。"
            with self.lock:
                self.job.update(state="error", error=message[:600])


def make_handler(service):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, data, content_type="application/json; charset=utf-8"):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/api/ping.svg":
                return self.send(200, b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"><rect width="1" height="1" fill="white"/></svg>', "image/svg+xml")
            if path == "/open.html":
                html = (ROOT / "open.html").read_text().replace("__GARBAGE_PORT__", str(self.server.server_port))
                return self.send(200, html.encode(), "text/html; charset=utf-8")
            if path == "/api/state":
                try:
                    camera_id = parse_qs(urlsplit(self.path).query).get("camera_id", [None])[0]
                    return self.send(200, service.status(camera_id))
                except ValueError as exc:
                    return self.send(400, {"error": str(exc)})
            if path == "/api/result":
                with service.lock:
                    result = service.result
                return self.send(200, {"result": result})
            if path == "/api/frame.jpg":
                try:
                    camera_id = parse_qs(urlsplit(self.path).query).get("camera_id", [None])[0]
                    _, jpg, _ = service.get_camera(camera_id).snapshot()
                    return self.send(200, jpg, "image/jpeg")
                except RuntimeError as exc:
                    return self.send(503, {"error": str(exc)})
                except ValueError as exc:
                    return self.send(400, {"error": str(exc)})
            files = {"/": ("index.html", "text/html; charset=utf-8"),
                     "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                     "/style.css": ("style.css", "text/css; charset=utf-8")}
            if path in files:
                name, mime = files[path]
                return self.send(200, (ROOT / "static" / name).read_bytes(), mime)
            self.send(404, {"error": "Not found"})

        def do_POST(self):
            # Only the dashboard's own origin may start compute jobs.
            origin = self.headers.get("Origin")
            if origin and urlsplit(origin).netloc != self.headers.get("Host"):
                return self.send(403, {"error": "不允许跨站发起检测。"})
            if self.path not in ("/api/detect", "/api/detect-image"):
                return self.send(404, {"error": "Not found"})
            try:
                if self.path == "/api/detect-image":
                    try:
                        size = int(self.headers.get("Content-Length", "0"))
                    except ValueError:
                        return self.send(400, {"error": "图片大小无效。"})
                    if not 0 < size <= MAX_UPLOAD_BYTES:
                        return self.send(413, {"error": "请选择不超过 10 MB 的图片。"})
                    self.connection.settimeout(15)
                    data = self.rfile.read(size)
                    if len(data) != size:
                        return self.send(400, {"error": "图片上传不完整，请重试。"})
                    image = decode_upload(data)
                    file_name = unquote(self.headers.get("X-File-Name", "上传图片"))[:200]
                    detailed = self.headers.get("X-Detection-Detail", "0") == "1"
                    try:
                        threshold = float(self.headers.get("X-Detection-Threshold", ".25"))
                    except ValueError:
                        return self.send(400, {"error": "检测阈值无效。"})
                    if not .15 <= threshold <= .6:
                        return self.send(400, {"error": "检测阈值必须在 0.15 到 0.60 之间。"})
                    job_id = service.start(image, file_name, detailed, threshold)
                else:
                    job_id = service.start(camera_id=self.headers.get("X-Camera-Id"))
                if job_id is None:
                    return self.send(409, {"error": "已有检测正在进行，请等待完成。"})
                self.send(202, {"id": job_id})
            except RuntimeError as exc:
                self.send(503, {"error": str(exc)})
            except ValueError as exc:
                self.send(400, {"error": str(exc)})
            except TimeoutError:
                self.send(408, {"error": "上传超时，请重试。"})

        def log_message(self, format, *args):
            if args and str(args[1]) not in ("200", "304"):
                super().log_message(format, *args)
    return Handler


def main():
    cameras = {}
    for index in range(1, 5):
        url = os.getenv(f"GARBAGE_RTSP_URL_{index}", os.getenv("GARBAGE_RTSP_URL", "") if index == 3 else "")
        if url and not url.startswith("rtsp://"):
            raise SystemExit(f"摄像头 {index} 的 RTSP 地址无效，请检查 .env。")
        cameras[f"camera_{index}"] = Camera(url, f"camera_{index}")
    if not any(camera.url for camera in cameras.values()):
        raise SystemExit("请在 .env 配置 GARBAGE_RTSP_URL_1～4，参见 README。")
    if os.getenv("GARBAGE_RTSP_TRANSPORT", "udp") not in ("udp", "tcp"):
        raise SystemExit("GARBAGE_RTSP_TRANSPORT 必须是 udp 或 tcp。")
    detector = Detector(os.getenv("GARBAGE_MODEL_PATH", str(ROOT / ".runtime/grounding-dino-tiny")),
                        os.getenv("GARBAGE_DEVICE", "cpu"))
    port = int(os.getenv("GARBAGE_PORT", "23071"))
    try:
        server = ThreadingHTTPServer((os.getenv("GARBAGE_HOST", "0.0.0.0"), port),
                                     make_handler(Service(cameras, detector)))
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        raise SystemExit(
            f"端口 {port} 已被占用。如果垃圾检测页面已启动，打开本目录 open.html 自动选择访问地址即可，无需重复启动。\n"
            f"如需重启，请先执行 bash {ROOT / 'stop.sh'}；如需使用其他端口，请修改本目录 .env 中的 GARBAGE_PORT。"
        ) from None
    for camera in cameras.values():
        if camera.url:
            threading.Thread(target=camera.run, daemon=True).start()
    print(f"垃圾检测页面：局域网 http://192.168.109.191:{server.server_port}/；Tailscale http://100.127.237.7:{server.server_port}/；自动入口 /open.html（后台服务请使用 stop.sh 停止）", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for camera in cameras.values():
            camera.stop.set()
        server.server_close()


if __name__ == "__main__":
    main()
