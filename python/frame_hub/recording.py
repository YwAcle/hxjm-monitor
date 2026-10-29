"""Non-blocking background remux recording for a shared input stream.

The input thread owns packet acquisition.  :class:`BackgroundRecorder` only
copies packet data into a bounded queue; a worker owns all container and file
operations.  A segment is published only after its MP4 has been closed,
fsynced, renamed, hashed, and described by a manifest.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import queue
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import av
except ImportError:  # pragma: no cover - exercised only in environments without PyAV
    av = None


logger = logging.getLogger(__name__)

_QUEUE_SENTINEL = object()
_DEFAULT_RETENTION_SECONDS = 7 * 24 * 60 * 60


def _positive_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{name} must be positive")
    return float(value)


def _fraction(value: Any, name: str) -> Fraction:
    if isinstance(value, Fraction):
        result = value
    elif isinstance(value, tuple) and len(value) == 2:
        result = Fraction(value[0], value[1])
    else:
        try:
            result = Fraction(value)
        except (TypeError, ValueError, ZeroDivisionError) as exc:
            raise ValueError(f"{name} must be a valid time base") from exc
    if result <= 0:
        raise ValueError(f"{name} must be positive")
    return result


def _round_fraction_ms(value: Fraction) -> int:
    """Round a non-negative seconds value to integer milliseconds exactly."""
    scaled = value * 1000
    if scaled < 0:
        raise ValueError("negative media time")
    return (scaled.numerator * 2 + scaled.denominator) // (2 * scaled.denominator)


def _iso_ms(epoch_ms: int) -> str:
    return datetime.fromtimestamp(epoch_ms / 1000, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


@dataclass(frozen=True)
class _PacketSnapshot:
    data: bytes
    pts: Optional[int]
    dts: Optional[int]
    duration: int
    time_base: Fraction
    is_keyframe: bool


@dataclass(frozen=True)
class _TemplateSnapshot:
    signature: tuple
    stream_type: str
    codec_name: str
    codec_tag: Optional[str]
    flags: int
    extradata: bytes
    profile: Any
    level: Any
    width: int
    height: int
    pixel_format: Optional[str]
    time_base: Fraction
    average_rate: Any
    base_rate: Any


@dataclass(frozen=True)
class _Offer:
    packet: _PacketSnapshot
    template: _TemplateSnapshot
    session: dict[str, Any]


class BackgroundRecorder:
    """Write encoded video packets to keyframe-aligned MP4 segments.

    ``offer`` is intended to run on the input/grabber thread.  It never does
    filesystem or container work and uses ``put_nowait`` on a bounded queue.
    The callback is invoked by the writer thread after a segment manifest has
    been atomically written.  This class accepts video packets only; audio is
    intentionally a separate future contract.
    """

    def __init__(
        self,
        source_id: str,
        storage_root: str | os.PathLike[str] = "/data/nfs_storage/hxjm_datas",
        segment_seconds: float = 3600,
        on_segment: Optional[Callable[[dict[str, Any]], Any]] = None,
        *,
        queue_size: int = 256,
        retention_seconds: int = _DEFAULT_RETENTION_SECONDS,
    ) -> None:
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("source_id must be a non-empty string")
        if type(queue_size) is not int or queue_size <= 0:
            raise ValueError("queue_size must be a positive integer")
        if type(retention_seconds) is not int or retention_seconds <= 0:
            raise ValueError("retention_seconds must be a positive integer")
        if on_segment is not None and not callable(on_segment):
            raise ValueError("on_segment must be callable")
        self.source_id = source_id
        self.storage_root = Path(storage_root)
        self.segment_seconds = _positive_number(segment_seconds, "segment_seconds")
        self.on_segment = on_segment
        self.retention_seconds = retention_seconds

        self._queue: queue.Queue[Any] = queue.Queue(maxsize=queue_size)
        self._lock = threading.RLock()
        self._stop_requested = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._state = "idle"
        self._last_error: Optional[str] = None
        self._accepted_packets = 0
        self._rejected_packets = 0
        self._written_packets = 0
        self._segments_completed = 0
        self._pending: dict[str, dict[str, Any]] = {}
        self._active: Optional[dict[str, Any]] = None
        self._session_key: Optional[str] = None
        self._template_signature: Optional[tuple] = None
        self._segment_index = 0

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
                if self._thread.is_alive():
                    return
                raise RuntimeError("Recorder cannot be restarted")
            if self._stop_requested.is_set():
                raise RuntimeError("Recorder cannot be restarted")
            self._state = "running"
            self._thread = threading.Thread(
                target=self._run, name=f"recording-{self.source_id}", daemon=False
            )
            self._thread.start()

    def stop(self, timeout: Optional[float] = None) -> bool:
        """Drain queued packets, close the current segment, and join the worker."""
        with self._lock:
            thread = self._thread
            if thread is None:
                self._state = "stopped"
                return True
            self._stop_requested.set()
        if thread.is_alive():
            thread.join(timeout)
        alive = thread.is_alive()
        if not alive:
            with self._lock:
                self._state = "stopped"
        return not alive

    def status(self) -> dict[str, Any]:
        with self._lock:
            thread = self._thread
            return {
                "state": self._state,
                "queued_packets": self._queue.qsize(),
                "accepted_packets": self._accepted_packets,
                "rejected_packets": self._rejected_packets,
                "written_packets": self._written_packets,
                "segments_completed": self._segments_completed,
                "last_error": self._last_error,
                "thread_alive": bool(thread and thread.is_alive()),
                "pending_manifests": len(self._pending),
            }

    def offer(self, packet: Any, template: Any, session: dict[str, Any]) -> bool:
        """Copy and enqueue one encoded video packet without waiting."""
        try:
            offer = _Offer(
                self._snapshot_packet(packet),
                self._snapshot_template(template),
                self._snapshot_session(session),
            )
        except (AttributeError, TypeError, ValueError, OverflowError) as exc:
            self._reject(str(exc))
            return False
        with self._lock:
            if self._thread is None or self._stop_requested.is_set():
                self._reject_locked("recorder is not running")
                return False
        try:
            self._queue.put_nowait(offer)
        except queue.Full:
            self._reject("recording queue is full")
            return False
        with self._lock:
            self._accepted_packets += 1
        return True

    def pending_manifests(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(value) for value in self._pending.values()]

    def acknowledge(self, manifest_or_asset_id: Any) -> bool:
        asset_id = manifest_or_asset_id.get("asset_id") if isinstance(manifest_or_asset_id, dict) else manifest_or_asset_id
        if not isinstance(asset_id, str):
            return False
        with self._lock:
            return self._pending.pop(asset_id, None) is not None

    @staticmethod
    def _snapshot_session(session: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(session, dict):
            raise ValueError("session must be an object")
        session_id = session.get("stream_session_id")
        started_at_ms = session.get("started_at_ms")
        width = session.get("width")
        height = session.get("height")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("stream_session_id is required")
        if isinstance(started_at_ms, bool) or not isinstance(started_at_ms, int) or started_at_ms < 0:
            raise ValueError("started_at_ms must be a non-negative integer")
        if type(width) is not int or width <= 0 or type(height) is not int or height <= 0:
            raise ValueError("session dimensions must be positive integers")
        result = {
            "stream_session_id": session_id,
            "started_at_ms": started_at_ms,
            "width": width,
            "height": height,
        }
        origin = session.get("time_origin_at_ms", started_at_ms)
        if type(origin) is not int or origin < 0:
            raise ValueError("time_origin_at_ms must be a non-negative integer")
        result["time_origin_at_ms"] = origin
        if "source_id" in session:
            result["source_id"] = session["source_id"]
        return result

    @staticmethod
    def _snapshot_packet(packet: Any) -> _PacketSnapshot:
        if packet is None:
            raise ValueError("packet is required")
        data = bytes(packet)
        if not data:
            raise ValueError("packet is empty")
        pts = getattr(packet, "pts", None)
        dts = getattr(packet, "dts", None)
        duration = getattr(packet, "duration", 0)
        time_base = _fraction(getattr(packet, "time_base", None), "packet.time_base")
        if pts is not None and (isinstance(pts, bool) or not isinstance(pts, int)):
            raise ValueError("packet.pts must be an integer or null")
        if dts is not None and (isinstance(dts, bool) or not isinstance(dts, int)):
            raise ValueError("packet.dts must be an integer or null")
        if type(duration) is not int or duration < 0:
            raise ValueError("packet.duration must be a non-negative integer")
        if pts is None:
            raise ValueError("packet.pts is required")
        return _PacketSnapshot(data, pts, dts, duration, time_base, bool(getattr(packet, "is_keyframe", False)))

    @staticmethod
    def _snapshot_template(template: Any) -> _TemplateSnapshot:
        if template is None or getattr(template, "type", None) != "video":
            raise ValueError("only video stream templates are accepted")
        codec_context = getattr(template, "codec_context", None)
        codec = getattr(codec_context, "codec", None)
        codec_name = getattr(codec, "name", None)
        if not isinstance(codec_name, str) or not codec_name:
            raise ValueError("video template codec is required")
        width = getattr(template, "width", None)
        height = getattr(template, "height", None)
        if type(width) is not int or width <= 0 or type(height) is not int or height <= 0:
            raise ValueError("video template dimensions are required")
        time_base = _fraction(getattr(template, "time_base", None), "template.time_base")
        codec_tag = getattr(codec_context, "codec_tag", None)
        if codec_tag is not None and not isinstance(codec_tag, str):
            codec_tag = None
        flags = getattr(codec_context, "flags", 0)
        if type(flags) is not int:
            raise ValueError("video template codec flags must be an integer")
        extradata = getattr(codec_context, "extradata", None)
        if extradata is None:
            extradata = b""
        try:
            extradata = bytes(extradata)
        except (TypeError, ValueError):
            raise ValueError("video template extradata is invalid") from None
        profile = getattr(codec_context, "profile", None)
        level = getattr(codec_context, "level", None)
        pixel_format = getattr(codec_context, "pix_fmt", None)
        if pixel_format is not None and not isinstance(pixel_format, str):
            pixel_format = None
        average_rate = getattr(template, "average_rate", None)
        if average_rate is not None:
            try:
                average_rate = _fraction(average_rate, "template.average_rate")
            except ValueError:
                average_rate = None
        base_rate = getattr(template, "base_rate", None)
        if base_rate is not None:
            try:
                base_rate = _fraction(base_rate, "template.base_rate")
            except ValueError:
                base_rate = None
        signature = (codec_name, codec_tag, flags, extradata, profile, level, width,
                     height, pixel_format, time_base, average_rate, base_rate)
        return _TemplateSnapshot(
            signature, "video", codec_name, codec_tag, flags, extradata, profile, level,
            width, height, pixel_format, time_base, average_rate, base_rate,
        )

    def _reject(self, error: str) -> None:
        with self._lock:
            self._reject_locked(error)

    def _reject_locked(self, error: str) -> None:
        self._rejected_packets += 1
        self._last_error = error

    def _run(self) -> None:
        try:
            while True:
                try:
                    item = self._queue.get(timeout=0.1)
                except queue.Empty:
                    if self._stop_requested.is_set():
                        break
                    continue
                try:
                    self._write_offer(item)
                except Exception as exc:  # keep input handoff alive after storage failures
                    logger.exception("background recording failed")
                    self._set_error(f"{type(exc).__name__}: {exc}")
                    self._discard_active()
                finally:
                    self._queue.task_done()
            self._finalize_active()
        except Exception as exc:
            logger.exception("recording worker stopped unexpectedly")
            self._set_error(f"{type(exc).__name__}: {exc}")
            self._discard_active()
        finally:
            with self._lock:
                self._state = "stopped" if self._stop_requested.is_set() else "degraded"

    def _write_offer(self, item: _Offer) -> None:
        session = item.session
        if session.get("source_id") not in (None, self.source_id):
            raise ValueError("session source_id does not match recorder source")
        session_key = session["stream_session_id"]
        if self._active is not None and (
            session_key != self._session_key or item.template.signature != self._template_signature
        ):
            self._finalize_active()
            self._session_key = None
            self._template_signature = None
        packet = item.packet
        if self._active is None:
            if not packet.is_keyframe:
                return
            if packet.pts is None or packet.pts < 0:
                raise ValueError("first keyframe has an invalid PTS")
            self._open_segment(item)
        active = self._active
        if active is None:
            return
        if packet.is_keyframe and packet.pts < active["base_pts"]:
            raise ValueError("packet PTS moved backwards")
        elapsed = (packet.pts - active["base_pts"]) * active["packet_time_base"]
        if (
            packet.is_keyframe
            and packet is not active.get("first_packet")
            and elapsed >= Fraction(str(self.segment_seconds))
        ):
            self._finalize_active(next_keyframe_pts=packet.pts)
            self._open_segment(item)
            active = self._active
        if active is None:
            return
        if packet.pts > active["max_pts"]:
            active["previous_max_pts"] = active["max_pts"]
            active["max_pts"] = packet.pts
            active["max_pts_duration"] = packet.duration
        elif packet.pts == active["max_pts"]:
            active["max_pts_duration"] = max(active["max_pts_duration"], packet.duration)
        elif active["previous_max_pts"] is None or packet.pts > active["previous_max_pts"]:
            active["previous_max_pts"] = packet.pts
        out_packet = self._make_output_packet(packet, active["stream"], active["base_pts"])
        if packet.duration == 0:
            duration, _ = self._infer_duration(active)
            if duration is not None:
                out_packet.duration = round(duration)
        active["container"].mux(out_packet)
        active["packet_count"] += 1
        active["end_pts"] = max(active["end_pts"], packet.pts + packet.duration)
        with self._lock:
            self._written_packets += 1

    def _open_segment(self, item: _Offer) -> None:
        if av is None:
            raise RuntimeError("PyAV is required for background recording")
        session = item.session
        self._segment_index += 1
        asset_id = str(uuid.uuid4())
        producer_key = f"recording:{self.source_id}:{session['stream_session_id']}:{self._segment_index}"
        relative = Path("recordings") / self.source_id / session["stream_session_id"] / f"{asset_id}.mp4"
        output_path = self.storage_root / relative
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        container = av.open(str(temp_path), mode="w", format="mp4")
        try:
            stream_kwargs = {}
            frame_rate = item.template.average_rate or item.template.base_rate
            if frame_rate is not None:
                stream_kwargs["rate"] = frame_rate
            stream = container.add_stream(item.template.codec_name, **stream_kwargs)
            stream.width = item.template.width
            stream.height = item.template.height
            if item.template.pixel_format is not None:
                stream.pix_fmt = item.template.pixel_format
            stream.time_base = item.template.time_base
            codec_context = stream.codec_context
            # Preserve the input framing flags so opening the output context
            # does not replace its codec headers and corrupt remuxed packets.
            codec_context.flags = item.template.flags
            # Container-specific input tags must be selected again by the MP4 muxer.
            if item.template.extradata:
                codec_context.extradata = item.template.extradata
            if item.template.profile is not None:
                codec_context.profile = item.template.profile
            if item.template.level is not None:
                codec_context.level = item.template.level
        except Exception:
            container.close()
            raise
        self._active = {
            "container": container,
            "stream": stream,
            "temp_path": temp_path,
            "output_path": output_path,
            "relative": relative.as_posix(),
            "asset_id": asset_id,
            "producer_key": producer_key,
            "request_id": f"asset:{producer_key}",
            "session": dict(session),
            "base_pts": item.packet.pts,
            "packet_time_base": item.packet.time_base,
            "first_packet": None,
            "first_pts": item.packet.pts,
            "end_pts": item.packet.pts + item.packet.duration,
            "max_pts": item.packet.pts,
            "max_pts_duration": item.packet.duration,
            "previous_max_pts": None,
            "average_rate": item.template.average_rate,
            "base_rate": item.template.base_rate,
            "packet_count": 0,
        }
        self._session_key = session["stream_session_id"]
        self._template_signature = item.template.signature
        self._active["first_packet"] = item.packet

    @staticmethod
    def _make_output_packet(packet: _PacketSnapshot, stream: Any, base_pts: int) -> Any:
        if av is None:
            raise RuntimeError("PyAV is required for background recording")
        output = av.Packet(packet.data)
        output.pts = packet.pts - base_pts if packet.pts is not None else None
        output.dts = packet.dts - base_pts if packet.dts is not None else None
        output.duration = packet.duration
        output.time_base = packet.time_base
        output.is_keyframe = packet.is_keyframe
        output.stream = stream
        return output

    @staticmethod
    def _infer_duration(active: dict[str, Any]) -> tuple[Optional[Fraction], Optional[str]]:
        for rate_name in ("average_rate", "base_rate"):
            if active[rate_name] is not None:
                return 1 / active[rate_name] / active["packet_time_base"], rate_name
        if active["previous_max_pts"] is not None:
            return active["max_pts"] - active["previous_max_pts"], "observed_pts_gap"
        return None, None

    def _finalize_active(self, *, next_keyframe_pts: Optional[int] = None) -> None:
        active = self._active
        if active is None:
            return
        self._active = None
        try:
            active["container"].close()
            time_base = active["packet_time_base"]
            # A known next segment boundary takes precedence over estimated tail duration.
            end_pts = active["end_pts"] if next_keyframe_pts is None else next_keyframe_pts
            end_timing = "packet_duration" if next_keyframe_pts is None else "next_keyframe"
            if next_keyframe_pts is None and active["max_pts_duration"] == 0:
                tail_duration, end_timing = self._infer_duration(active)
                if tail_duration is None:
                    raise ValueError("recording end time is unknown: packet duration, frame rate and PTS interval are missing")
                end_pts = max(end_pts, active["max_pts"] + tail_duration)
            _fsync_file(active["temp_path"])
            os.replace(active["temp_path"], active["output_path"])
            _fsync_file(active["output_path"])
            digest = hashlib.sha256()
            size = 0
            with active["output_path"].open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    size += len(chunk)
                    digest.update(chunk)
            session = active["session"]
            first_pts = active["first_pts"]
            start_offset_ms = _round_fraction_ms(Fraction(first_pts) * time_base)
            end_offset_ms = _round_fraction_ms(Fraction(end_pts) * time_base)
            start_ms = session["time_origin_at_ms"] + start_offset_ms
            end_ms = session["time_origin_at_ms"] + max(start_offset_ms, end_offset_ms)
            expires_ms = end_ms + self.retention_seconds * 1000
            manifest = {
                "request_id": active["request_id"],
                "asset_id": active["asset_id"],
                "producer_key": active["producer_key"],
                "asset_type": "recording",
                "source_id": self.source_id,
                "stream_session_id": session["stream_session_id"],
                "stream_session": {
                    "stream_session_id": session["stream_session_id"],
                    "started_at": _iso_ms(session["started_at_ms"]),
                    "time_origin_at": _iso_ms(session["time_origin_at_ms"]),
                    "time_basis": "ingest_clock",
                    "source_timezone": "UTC",
                    "source_width": session["width"],
                    "source_height": session["height"],
                },
                "storage_key": active["relative"],
                "state": "available",
                "start_at": _iso_ms(start_ms),
                "end_at": _iso_ms(end_ms),
                "content_type": "video/mp4",
                "byte_size": size,
                "checksum_sha256": digest.hexdigest(),
                "expires_at": _iso_ms(expires_ms),
                "end_timing": end_timing,
                "recording_alignment": {
                    "schema_version": "1",
                    "stream_start_pts_ms": start_offset_ms,
                    "stream_end_pts_ms": end_offset_ms,
                    "media_start_pts_ms": 0,
                },
            }
            manifest_path = active["output_path"].with_suffix(active["output_path"].suffix + ".manifest.json")
            manifest_temp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
            with manifest_temp.open("w", encoding="utf-8") as handle:
                json.dump(manifest, handle, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(manifest_temp, manifest_path)
            with self._lock:
                self._segments_completed += 1
            if self.on_segment is not None:
                try:
                    self.on_segment(dict(manifest))
                except Exception as exc:
                    logger.exception("recording manifest callback failed")
                    with self._lock:
                        self._pending[manifest["asset_id"]] = manifest
                        self._last_error = f"{type(exc).__name__}: {exc}"
        except Exception:
            self._discard_path(active)
            raise

    @staticmethod
    def _discard_path(active: dict[str, Any]) -> None:
        for key in ("temp_path",):
            path = active.get(key)
            if path is not None:
                try:
                    Path(path).unlink()
                except FileNotFoundError:
                    pass

    def _discard_active(self) -> None:
        active = self._active
        self._active = None
        if active is None:
            return
        try:
            active["container"].close()
        except Exception:
            pass
        self._discard_path(active)

    def _set_error(self, error: str) -> None:
        with self._lock:
            self._last_error = error
            self._state = "degraded"

