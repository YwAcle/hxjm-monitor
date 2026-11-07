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
    MAX_FRAME_BYTES,
    DECODE_THREADS,
)


@dataclass
class CapturedFrame:
    frame: np.ndarray
    frame_ts_ms: int
    source_width: int
    source_height: int
    frame_id: int = 0
    stream_epoch: int = 0
    decode_ts_ms: int = 0
    media_pts_ms: float = None
    timestamp_kind: str = 'decode_wall_clock'
    # Public IDs assigned by ResultPublisher once the frame is durably enqueued.
    public_frame_ref: object = None


class MediaClockMapper:
    """Session-local PTS anchored to minimum decode arrival; NOT camera capture time."""
    MAX_ARRIVAL_LAG_MS = 500

    def __init__(self):
        self.last_pts = None
        self.anchor = None

    def map(self, pts, arrival):
        # FFmpeg may expose AV_NOPTS_VALUE as a huge negative timestamp. PTS can
        # also stall or advance at a different rate after lost/corrupt packets.
        # An old minimum-arrival anchor must not age every freshly decoded frame.
        if pts is None or not math.isfinite(pts) or pts < 0:
            self.last_pts = self.anchor = None
            return arrival, 'decode_wall_clock'
        advancing = self.last_pts is not None and 0 < pts - self.last_pts < 10000
        if not advancing:
            self.anchor = None
        candidate = arrival - pts
        self.anchor = candidate if self.anchor is None else min(self.anchor, candidate)
        self.last_pts = pts
        estimated = int(self.anchor + pts)
        if arrival - estimated > self.MAX_ARRIVAL_LAG_MS:
            self.anchor = candidate
            return arrival, 'decode_wall_clock'
        return (estimated, 'pts_wall_estimate') if advancing else (arrival, 'decode_wall_clock')


def _open_capture(rtsp_url):
    if not rtsp_url.strip():
        raise ValueError("VIDEO_ANALYSIS_RTSP_URL must not be empty")
    if RTSP_TRANSPORT not in ("udp", "tcp"):
        raise ValueError("VIDEO_ANALYSIS_RTSP_TRANSPORT must be udp or tcp")

    # Do not accumulate FFmpeg's default probing/reorder buffer on the independent
    # analysis receiver. RTP/codec errors still trigger capture recovery, not model recovery.
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
        f"rtsp_transport;{RTSP_TRANSPORT}|fflags;nobuffer|flags;low_delay"
        "|analyzeduration;0|probesize;32768|max_delay;100000"
    )
    capture = cv2.VideoCapture()
    try:
        options = [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, OPEN_TIMEOUT_MS,
                   cv2.CAP_PROP_READ_TIMEOUT_MSEC, READ_TIMEOUT_MS]
        # Four full-rate decoders must not each spawn a host-sized thread pool.
        if hasattr(cv2, 'CAP_PROP_N_THREADS'):
            options.extend([cv2.CAP_PROP_N_THREADS, DECODE_THREADS])
        opened = capture.open(
            rtsp_url,
            cv2.CAP_FFMPEG,
            options,
        )
        if not opened:
            raise RuntimeError("RTSP connection failed or exceeded the 5-second open timeout")

        return capture
    except BaseException:
        capture.release()
        raise


def _read_frame(capture, clock=None):
    success, frame = capture.read()
    frame_ts_ms = time.time_ns() // 1_000_000
    if not success or frame is None or frame.size == 0:
        raise RuntimeError("RTSP frame read failed or exceeded the 5-second read timeout")
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise RuntimeError("Expected a three-channel BGR frame")
    if frame.nbytes > MAX_FRAME_BYTES:
        raise RuntimeError("Decoded frame exceeds VIDEO_ANALYSIS_MAX_FRAME_BYTES")

    height, width = frame.shape[:2]
    captured = CapturedFrame(frame, frame_ts_ms, width, height, decode_ts_ms=frame_ts_ms)
    if clock is not None and hasattr(cv2, 'CAP_PROP_PTS'):
        fps = capture.get(cv2.CAP_PROP_FPS)
        pts = capture.get(cv2.CAP_PROP_PTS)
        if math.isfinite(fps) and fps > 0 and math.isfinite(pts):
            captured.media_pts_ms = pts * 1000 / fps
            captured.frame_ts_ms, captured.timestamp_kind = clock.map(captured.media_pts_ms, frame_ts_ms)
    return captured


def grab_frame(rtsp_url=RTSP_URL):
    capture = _open_capture(rtsp_url)
    try:
        return _read_frame(capture)
    finally:
        capture.release()


class LatestFrameGrabber:
    def __init__(self, on_status, rtsp_url=RTSP_URL, reconnect_delay=RECONNECT_DELAY_SECONDS):
        if not math.isfinite(reconnect_delay) or reconnect_delay <= 0:
            raise ValueError("VIDEO_ANALYSIS_RECONNECT_DELAY_SECONDS must be finite and positive")
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
        self._thread = threading.Thread(target=self._run, name="video-analysis-rtsp", daemon=False)
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
                "latest_decode_ts_ms": self._latest.decode_ts_ms if self._latest else None,
                "media_pts_ms": self._latest.media_pts_ms if self._latest else None,
                "timestamp_kind": self._latest.timestamp_kind if self._latest else None,
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
                    clock = MediaClockMapper()
                    self._set_status("waiting_frame")
                    while not self._stop_event.is_set():
                        captured = _read_frame(capture, clock)
                        if self._stop_event.is_set():
                            break
                        with self._lock:
                            self._frame_id += 1
                            captured.frame_id = self._frame_id
                            captured.stream_epoch = self._stream_epoch
                            self._latest = captured
                        if self._state != 'streaming':
                            self._set_status('streaming')
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
