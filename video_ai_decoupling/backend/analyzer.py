import asyncio
import logging
import math
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from .config import CAMERA_ID, INFERENCE_INTERVAL_SECONDS
from .detector_adapter import detect_people, initialize_detector
from .stream_grabber import LatestFrameGrabber


logger = logging.getLogger(__name__)


class Subscription:
    def __init__(self):
        self.detections = asyncio.Queue(maxsize=1)
        self.statuses = asyncio.Queue(maxsize=1)
        self._ready = asyncio.Event()

    def put(self, message):
        queue = self.statuses if message["type"] == "status" else self.detections
        if queue.full():
            queue.get_nowait()
        queue.put_nowait(message)
        self._ready.set()

    async def next_message(self):
        await self._ready.wait()
        queue = self.statuses if not self.statuses.empty() else self.detections
        message = queue.get_nowait()
        if self.statuses.empty() and self.detections.empty():
            self._ready.clear()
        return message


class Analyzer:
    def __init__(self, inference_interval=INFERENCE_INTERVAL_SECONDS):
        if not math.isfinite(inference_interval) or inference_interval <= 0:
            raise ValueError("DEMO_INFERENCE_INTERVAL_SECONDS must be finite and positive")
        self._inference_interval = inference_interval
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="demo-inference")
        self._stop_event = asyncio.Event()
        self._subscriptions = set()
        self._loop = None
        self._task = None
        self._grabber = LatestFrameGrabber(self._on_capture_status)
        self._states = {
            "capture": {"state": "idle", "error": None},
            "analyzer": {"state": "starting", "error": None},
        }
        self._model_initializations = 0
        self._last_attempted_frame_id = 0
        self._last_result = None
        self._inference_count = 0
        self._published_count = 0
        self._discarded_results = 0
        self._recent_inferences = deque(maxlen=10)

    async def start(self):
        if self._task is not None:
            raise RuntimeError("Analyzer has already been started")
        self._loop = asyncio.get_running_loop()
        self._grabber.start()
        self._task = asyncio.create_task(self._run(), name="demo-analysis")

    async def stop(self):
        self._stop_event.set()
        self._grabber.request_stop()
        try:
            if self._task is not None:
                await self._task
        finally:
            try:
                await asyncio.to_thread(self._grabber.stop)
            finally:
                await asyncio.to_thread(self._executor.shutdown, wait=True, cancel_futures=True)
                self._subscriptions.clear()

    def subscribe(self):
        subscription = Subscription()
        self._subscriptions.add(subscription)
        subscription.put(self._status_message("service", self.health()["status"]))
        return subscription

    def unsubscribe(self, subscription):
        self._subscriptions.discard(subscription)

    def health(self):
        capture = self._grabber.snapshot()
        task_alive = self._task is not None and not self._task.done()
        ready = (
            self._model_initializations == 1
            and capture["state"] == "streaming"
            and capture["latest_frame_id"] is not None
            and self._states["analyzer"]["state"] == "ready"
            and task_alive
        )
        status = "ok" if ready else "degraded"
        if self._states["analyzer"]["state"] in ("starting", "loading_model"):
            status = "starting"
        if self._stop_event.is_set():
            status = "stopping"
        return {
            "status": status,
            "camera_id": CAMERA_ID,
            "capture": capture,
            "components": dict(self._states),
            "model_initializations": self._model_initializations,
            "analysis_task_alive": task_alive,
            "inference_interval_seconds": self._inference_interval,
            "inference_count": self._inference_count,
            "published_count": self._published_count,
            "discarded_stale_results": self._discarded_results,
            "last_analyzed_frame_id": self._last_attempted_frame_id,
            "last_published_frame_id": self._last_result["frame_id"] if self._last_result else None,
            "recent_inferences": list(self._recent_inferences),
            "clients": len(self._subscriptions),
        }

    def _on_capture_status(self, state, error, stream_epoch):
        self._loop.call_soon_threadsafe(self._set_status, "capture", state, error, stream_epoch)

    def _status_message(self, component, state, error=None, stream_epoch=None):
        if stream_epoch is None:
            stream_epoch = self._grabber.snapshot()["stream_epoch"]
        return {
            "type": "status",
            "camera_id": CAMERA_ID,
            "component": component,
            "state": state,
            "error": error,
            "components": dict(self._states),
            "stream_epoch": stream_epoch,
            "sent_at_ms": time.time_ns() // 1_000_000,
        }

    def _set_status(self, component, state, error=None, stream_epoch=None):
        updated = {"state": state, "error": error}
        if self._states.get(component) == updated:
            return
        self._states[component] = updated
        logger.info("%s state=%s error=%s epoch=%s", component, state, error, stream_epoch)
        self._publish(self._status_message(component, state, error, stream_epoch))

    def _publish(self, message):
        for subscription in self._subscriptions:
            subscription.put(message)

    async def _wait(self, seconds):
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def _run(self):
        self._set_status("analyzer", "loading_model")
        try:
            await self._loop.run_in_executor(self._executor, initialize_detector)
        except Exception as exc:
            logger.exception("Model initialization failed")
            self._set_status("analyzer", "model_error", f"{type(exc).__name__}: {exc}")
            self._grabber.request_stop()
            return

        self._model_initializations = 1
        self._set_status("analyzer", "ready")
        next_inference_at = 0.0
        try:
            while not self._stop_event.is_set():
                delay = next_inference_at - self._loop.time()
                if delay > 0:
                    await self._wait(delay)
                if self._stop_event.is_set():
                    break
                captured = self._grabber.latest_frame()
                if captured is None or captured.frame_id <= self._last_attempted_frame_id:
                    await self._wait(0.05)
                    continue

                self._last_attempted_frame_id = captured.frame_id
                next_inference_at = self._loop.time() + self._inference_interval
                try:
                    detections, inference_ms = await self._loop.run_in_executor(
                        self._executor, detect_people, captured.frame,
                    )
                except Exception as exc:
                    logger.exception("Frame inference failed")
                    self._set_status("analyzer", "inference_error", f"{type(exc).__name__}: {exc}")
                    continue

                if self._stop_event.is_set():
                    break
                self._set_status("analyzer", "ready")
                self._inference_count += 1
                self._recent_inferences.append({
                    "frame_id": captured.frame_id,
                    "stream_epoch": captured.stream_epoch,
                    "inference_ms": inference_ms,
                })
                latest = self._grabber.latest_frame()
                if latest is None or latest.stream_epoch != captured.stream_epoch:
                    self._discarded_results += 1
                    continue

                result = {
                    "type": "detections",
                    "camera_id": CAMERA_ID,
                    "frame_ts_ms": captured.frame_ts_ms,
                    "source_width": captured.source_width,
                    "source_height": captured.source_height,
                    "inference_ms": inference_ms,
                    "detections": detections,
                    "frame_id": captured.frame_id,
                    "stream_epoch": captured.stream_epoch,
                    "sent_at_ms": time.time_ns() // 1_000_000,
                }
                self._last_result = result
                self._published_count += 1
                self._publish(result)
        finally:
            if self._stop_event.is_set():
                self._set_status("analyzer", "stopped")
