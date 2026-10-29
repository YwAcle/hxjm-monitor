import math
import logging
import os
import threading
import time
from dataclasses import dataclass
import uuid

import cv2
import numpy as np

try:
    import av
except ImportError:  # pragma: no cover - PyAV is supplied by the media runtime
    av = None

from .config import (
    OPEN_TIMEOUT_MS,
    READ_TIMEOUT_MS,
    RECONNECT_DELAY_SECONDS,
    RTSP_TRANSPORT,
    RTSP_URL,
    MAX_FRAME_BYTES,
    DECODE_THREADS,
)


logger = logging.getLogger(__name__)


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
    public_frame_ref: object = None
    stream_session_id: str = None
    session_started_at_ms: int = None
    session_time_origin_at_ms: int = None


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


def _open_pyav(rtsp_url):
    """Open one low-latency PyAV input used for both recording and decoding."""
    if av is None:
        raise RuntimeError("PyAV is required when packet delivery is enabled")
    if not rtsp_url.strip():
        raise ValueError("VIDEO_ANALYSIS_RTSP_URL must not be empty")
    options = {
        "rtsp_transport": RTSP_TRANSPORT,
        "fflags": "nobuffer",
        "flags": "low_delay",
        "analyzeduration": "0",
        "probesize": "32768",
        "max_delay": "100000",
    }
    try:
        return av.open(
            rtsp_url,
            mode="r",
            options=options,
            timeout=(OPEN_TIMEOUT_MS / 1000, READ_TIMEOUT_MS / 1000),
        )
    except TypeError:
        # Older PyAV releases accept a scalar timeout only.
        return av.open(
            rtsp_url,
            mode="r",
            options=options,
            timeout=OPEN_TIMEOUT_MS / 1000,
        )


def _close_pyav(container):
    if container is not None:
        container.close()


def _stream_dimensions(stream):
    width = getattr(stream, "width", None)
    height = getattr(stream, "height", None)
    codec_context = getattr(stream, "codec_context", None)
    if not isinstance(width, int) or width <= 0:
        width = getattr(codec_context, "width", None)
    if not isinstance(height, int) or height <= 0:
        height = getattr(codec_context, "height", None)
    if type(width) is not int or width <= 0 or type(height) is not int or height <= 0:
        return None, None
    return width, height


def _time_base_seconds(value):
    if value is None:
        return None
    try:
        numerator = value.numerator
        denominator = value.denominator
    except AttributeError:
        try:
            numerator, denominator = value
        except (TypeError, ValueError):
            return None
    if denominator == 0:
        return None
    result = float(numerator) / float(denominator)
    return result if math.isfinite(result) and result > 0 else None


def _media_pts_ms(value, time_base):
    if value is None:
        return None
    try:
        pts = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    scale = _time_base_seconds(time_base)
    if scale is None or not math.isfinite(pts) or pts < 0:
        return None
    result = pts * scale * 1000
    return result if math.isfinite(result) and result >= 0 else None


class LatestFrameGrabber:
    def __init__(self, on_status, rtsp_url=RTSP_URL, reconnect_delay=RECONNECT_DELAY_SECONDS,
                 on_frame=None, on_packet=None):
        if not math.isfinite(reconnect_delay) or reconnect_delay <= 0:
            raise ValueError("VIDEO_ANALYSIS_RECONNECT_DELAY_SECONDS must be finite and positive")
        self._on_status = on_status
        self._on_frame = on_frame
        self._on_packet = on_packet
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
        self._stream_session_id = None

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
                "stream_session_id": self._latest.stream_session_id if self._latest else self._stream_session_id,
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
                    if self._on_packet is not None:
                        capture = _open_pyav(self._rtsp_url)
                        self._run_pyav_session(capture)
                    else:
                        capture = _open_capture(self._rtsp_url)
                        self._run_opencv_session(capture)
                except Exception as exc:
                    with self._lock:
                        self._latest = None
                    if not self._stop_event.is_set():
                        self._set_status("reconnecting", f"{type(exc).__name__}: {exc}")
                finally:
                    if capture is not None:
                        if self._on_packet is not None:
                            _close_pyav(capture)
                        else:
                            capture.release()
                self._stop_event.wait(self._reconnect_delay)
        finally:
            with self._lock:
                self._latest = None
            self._set_status("stopped")

    def _next_stream(self):
        with self._lock:
            self._stream_epoch += 1
            self._stream_session_id = str(uuid.uuid4())
            return self._stream_epoch, self._stream_session_id

    def _publish_captured(self, captured):
        if self._stop_event.is_set():
            return
        with self._lock:
            self._frame_id += 1
            captured.frame_id = self._frame_id
            captured.stream_epoch = self._stream_epoch
            captured.stream_session_id = self._stream_session_id
        if self._on_frame is not None:
            self._on_frame(captured)
        with self._lock:
            self._latest = captured
        if self._state != 'streaming':
            self._set_status('streaming')

    def _run_opencv_session(self, capture):
        self._next_stream()
        clock = MediaClockMapper()
        self._set_status("waiting_frame")
        while not self._stop_event.is_set():
            captured = _read_frame(capture, clock)
            self._publish_captured(captured)

    def _run_pyav_session(self, container):
        streams = getattr(container, "streams", None)
        video_streams = getattr(streams, "video", None) if streams is not None else None
        if not video_streams:
            raise RuntimeError("RTSP input has no video stream")
        video_stream = video_streams[0]
        codec_context = getattr(video_stream, "codec_context", None)
        if codec_context is not None:
            codec_context.thread_count = DECODE_THREADS
        _, session_id = self._next_stream()
        width, height = _stream_dimensions(video_stream)
        self._set_status("waiting_frame")
        session_started_at_ms = None
        time_origin_at_ms = None
        for packet in container.demux(video_stream):
            if self._stop_event.is_set():
                break
            packet_pts_ms = _media_pts_ms(getattr(packet, "pts", None), getattr(packet, "time_base", None))
            arrival_ms = time.time_ns() // 1_000_000
            if session_started_at_ms is None:
                session_started_at_ms = arrival_ms
                time_origin_at_ms = arrival_ms - (math.floor(packet_pts_ms + 0.5) if packet_pts_ms is not None else 0)
            packet_width, packet_height = width, height
            if packet_width is None or packet_height is None:
                packet_width, packet_height = _stream_dimensions(video_stream)
            session = {
                "stream_session_id": session_id,
                "started_at_ms": max(0, int(session_started_at_ms)),
                "time_origin_at_ms": max(0, int(time_origin_at_ms)),
                "width": packet_width,
                "height": packet_height,
            }
            if self._on_packet is not None and getattr(packet, 'size', None) != 0:
                try:
                    # The callback must perform only a bounded, non-blocking handoff.
                    self._on_packet(packet, video_stream, session)
                except Exception:
                    logger.exception("encoded packet handoff failed")
            try:
                decoded_frames = packet.decode()
            except Exception:
                raise
            for frame in decoded_frames:
                if self._stop_event.is_set():
                    break
                image = frame.to_ndarray(format="bgr24")
                if (not isinstance(image, np.ndarray) or image.dtype != np.uint8
                        or image.ndim != 3 or image.shape[2] != 3 or image.size == 0
                        or image.nbytes > MAX_FRAME_BYTES):
                    raise RuntimeError("Decoded frame is not a bounded BGR uint8 image")
                frame_height, frame_width = image.shape[:2]
                arrival = time.time_ns() // 1_000_000
                frame_pts = _media_pts_ms(getattr(frame, "pts", None), getattr(frame, "time_base", None))
                if frame_pts is None:
                    frame_pts = packet_pts_ms
                captured = CapturedFrame(
                    frame=image,
                    frame_ts_ms=arrival,
                    source_width=frame_width,
                    source_height=frame_height,
                    decode_ts_ms=arrival,
                    media_pts_ms=frame_pts,
                    timestamp_kind="decode_wall_clock",
                    session_started_at_ms=session["started_at_ms"],
                    session_time_origin_at_ms=session["time_origin_at_ms"],
                )
                if frame_pts is not None:
                    # Recording and public frames share the same fixed PTS origin.
                    captured.frame_ts_ms = session["time_origin_at_ms"] + math.floor(frame_pts + 0.5)
                    captured.timestamp_kind = "pts_wall_estimate"
                self._publish_captured(captured)
