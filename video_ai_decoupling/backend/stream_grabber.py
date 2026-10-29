import math
import os
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np

from .config import (
    OPEN_TIMEOUT_MS,
    READ_TIMEOUT_MS,
    RECONNECT_DELAY_SECONDS,
    RTSP_TRANSPORT,
    RTSP_URL,
)


@dataclass
class CapturedFrame:
    frame: np.ndarray
    frame_ts_ms: int
    source_width: int
    source_height: int
    frame_id: int = 0
    stream_epoch: int = 0


def _open_capture(rtsp_url):
    if not rtsp_url.strip():
        raise ValueError("DEMO_RTSP_URL must not be empty")
    if RTSP_TRANSPORT not in ("udp", "tcp"):
        raise ValueError("DEMO_RTSP_TRANSPORT must be udp or tcp")

    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", f"rtsp_transport;{RTSP_TRANSPORT}")
    capture = cv2.VideoCapture()
    try:
        opened = capture.open(
            rtsp_url,
            cv2.CAP_FFMPEG,
            [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, OPEN_TIMEOUT_MS,
                cv2.CAP_PROP_READ_TIMEOUT_MSEC, READ_TIMEOUT_MS,
            ],
        )
        if not opened:
            raise RuntimeError("RTSP connection failed or exceeded the 5-second open timeout")

        return capture
    except BaseException:
        capture.release()
        raise


def _read_frame(capture):
    success, frame = capture.read()
    frame_ts_ms = time.time_ns() // 1_000_000
    if not success or frame is None or frame.size == 0:
        raise RuntimeError("RTSP frame read failed or exceeded the 5-second read timeout")
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise RuntimeError("Expected a three-channel BGR frame")

    height, width = frame.shape[:2]
    return CapturedFrame(frame, frame_ts_ms, width, height)


def grab_frame(rtsp_url=RTSP_URL):
    capture = _open_capture(rtsp_url)
    try:
        return _read_frame(capture)
    finally:
        capture.release()


class LatestFrameGrabber:
    def __init__(self, on_status, rtsp_url=RTSP_URL, reconnect_delay=RECONNECT_DELAY_SECONDS):
        if not math.isfinite(reconnect_delay) or reconnect_delay <= 0:
            raise ValueError("DEMO_RECONNECT_DELAY_SECONDS must be finite and positive")
        self._on_status = on_status
        self._rtsp_url = rtsp_url
        self._reconnect_delay = reconnect_delay
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._latest = None
        self._frame_id = 0
        self._stream_epoch = 0
        self._state = "idle"
        self._error = None

    def start(self):
        if self._thread is not None:
            raise RuntimeError("Capture thread has already been started")
        self._thread = threading.Thread(target=self._run, name="demo-rtsp", daemon=False)
        self._thread.start()

    def latest_frame(self):
        with self._lock:
            return self._latest

    def snapshot(self):
        with self._lock:
            return {
                "state": self._state,
                "error": self._error,
                "stream_epoch": self._stream_epoch,
                "latest_frame_id": self._latest.frame_id if self._latest else None,
                "latest_frame_ts_ms": self._latest.frame_ts_ms if self._latest else None,
                "thread_alive": self._thread is not None and self._thread.is_alive(),
            }

    def request_stop(self):
        self._stop_event.set()

    def stop(self):
        self.request_stop()
        if self._thread is not None:
            self._thread.join()

    def _set_status(self, state, error=None):
        with self._lock:
            self._state = state
            self._error = error
            stream_epoch = self._stream_epoch
        self._on_status(state, error, stream_epoch)

    def _run(self):
        try:
            while not self._stop_event.is_set():
                capture = None
                self._set_status("connecting")
                try:
                    capture = _open_capture(self._rtsp_url)
                    with self._lock:
                        self._stream_epoch += 1
                    self._set_status("streaming")
                    while not self._stop_event.is_set():
                        captured = _read_frame(capture)
                        if self._stop_event.is_set():
                            break
                        with self._lock:
                            self._frame_id += 1
                            captured.frame_id = self._frame_id
                            captured.stream_epoch = self._stream_epoch
                            self._latest = captured
                except Exception as exc:
                    with self._lock:
                        self._latest = None
                    if not self._stop_event.is_set():
                        self._set_status("reconnecting", f"{type(exc).__name__}: {exc}")
                finally:
                    if capture is not None:
                        capture.release()
                self._stop_event.wait(self._reconnect_delay)
        finally:
            with self._lock:
                self._latest = None
            self._set_status("stopped")
