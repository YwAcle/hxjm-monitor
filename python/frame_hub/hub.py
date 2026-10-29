"""One capture per source, with immutable frames and shared public identities."""
import logging
import math
import threading
import uuid
from dataclasses import dataclass

import numpy as np

from video_analysis.config import MAX_FRAME_BYTES
from video_analysis.stream_grabber import CapturedFrame, LatestFrameGrabber


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FrameReference:
    source_id: str
    stream_session_id: str
    frame_id: str
    frame_seq: int
    session_started_at_ms: int = None
    session_width: int = None
    session_height: int = None
    session_time_origin_at_ms: int = None


@dataclass(frozen=True)
class SharedFrame:
    reference: FrameReference
    pixels: bytes
    source_width: int
    source_height: int
    legacy_frame_id: int
    stream_epoch: int
    frame_ts_ms: int
    decode_ts_ms: int
    media_pts_ms: float
    timestamp_kind: str

    def as_captured(self):
        # A bytes-backed view cannot be made writable by a reader.
        image = np.frombuffer(self.pixels, dtype=np.uint8).reshape(
            self.source_height, self.source_width, 3)
        return CapturedFrame(
            frame=image, frame_ts_ms=self.frame_ts_ms,
            source_width=self.source_width, source_height=self.source_height,
            frame_id=self.legacy_frame_id, stream_epoch=self.stream_epoch,
            decode_ts_ms=self.decode_ts_ms, media_pts_ms=self.media_pts_ms,
            timestamp_kind=self.timestamp_kind, public_frame_ref=self.reference,
            stream_session_id=self.reference.stream_session_id,
            session_started_at_ms=self.reference.session_started_at_ms,
            session_time_origin_at_ms=self.reference.session_time_origin_at_ms)


class _Source:
    def __init__(self):
        self.grabber = None
        self.recorder = None
        self.readers = set()
        self.frame = None
        self.session_id = None
        self.session_started_at_ms = None
        self.session_time_origin_at_ms = None
        self.session_width = None
        self.session_height = None
        self.session_epoch = 0
        self.closed_epoch = 0
        self.epoch = 0
        self.sequence = 0
        self.last_frame_id = 0
        self.state = 'idle'
        self.error = None
        self.status_version = 0


class FrameHub:
    def __init__(self, sources, grabber_factory=LatestFrameGrabber,
                 max_frame_bytes=MAX_FRAME_BYTES, recorder_factory=None):
        if not sources:
            raise ValueError('At least one source is required')
        if type(max_frame_bytes) is not int or max_frame_bytes <= 0:
            raise ValueError('max_frame_bytes must be a positive integer')
        self._lock = threading.RLock()
        self._sources = {}
        self._started = False
        self._stopped = False
        self._max_frame_bytes = max_frame_bytes
        if recorder_factory is not None and not callable(recorder_factory):
            raise ValueError('recorder_factory must be callable')
        for source_id, url in sources.items():
            if not isinstance(source_id, str) or str(uuid.UUID(source_id)) != source_id:
                raise ValueError('Source ID must be a canonical UUID')
            if not isinstance(url, str) or not url.startswith('rtsp://'):
                raise ValueError('A source must have an RTSP URL')
            source = _Source()
            if recorder_factory is not None:
                source.recorder = recorder_factory(source_id)
                if source.recorder is None:
                    raise ValueError('recorder_factory must return a recorder')
            grabber_options = {
                'rtsp_url': url,
                'on_frame': lambda frame, sid=source_id: self._publish(sid, frame),
            }
            if source.recorder is not None:
                grabber_options['on_packet'] = (
                    lambda packet, stream, session, sid=source_id:
                    self._offer_packet(sid, packet, stream, session)
                )
            source.grabber = grabber_factory(
                lambda state, error, epoch, sid=source_id: self._status(sid, state, error, epoch),
                **grabber_options)
            self._sources[source_id] = source

    def start(self):
        with self._lock:
            if self._started or self._stopped:
                raise RuntimeError('Create a new FrameHub to start another input lifecycle')
            self._started = True
        try:
            # Start the consumer before the producer so the first packet can be
            # handed off without a race or a special-case drop.
            for source in self._sources.values():
                if source.recorder is not None:
                    source.recorder.start()
            for source in self._sources.values():
                source.grabber.start()
        except BaseException:
            self.stop()
            raise

    def stop(self):
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
            started = self._started
        if started:
            for source in self._sources.values():
                source.grabber.request_stop()
            # Finish packet handoff before draining the recording queue.
            for source in self._sources.values():
                source.grabber.stop()
            for source in self._sources.values():
                if source.recorder is not None:
                    source.recorder.stop()
        for source_id, source in self._sources.items():
            self._status(source_id, 'stopped', None, source.epoch)

    def _offer_packet(self, source_id, packet, stream, session):
        source = self._source(source_id)
        recorder = source.recorder
        if recorder is None:
            return
        handoff = dict(session) if isinstance(session, dict) else session
        if isinstance(handoff, dict):
            handoff.setdefault('source_id', source_id)
        try:
            accepted = recorder.offer(packet, stream, handoff)
            if accepted is False:
                logger.warning('Recording packet was not accepted for source %s', source_id)
        except Exception:
            # Recording is deliberately independent from decoding and analysis.
            logger.exception('Recording packet handoff failed for source %s', source_id)

    def reader(self, source_id, on_status):
        """Status callbacks run on input threads; dispatch owner shutdown to its loop."""
        self._source(source_id)
        return HubGrabber(self, source_id, on_status)

    def _source(self, source_id):
        try:
            return self._sources[source_id]
        except KeyError:
            raise ValueError('Unknown source') from None

    def latest(self, source_id):
        with self._lock:
            return self._source(source_id).frame

    def snapshot(self, source_id):
        with self._lock:
            source = self._source(source_id)
            frame = source.frame
            grabber_snapshot = source.grabber.snapshot()
            return {
                'state': source.state, 'error': source.error,
                'stream_epoch': source.epoch,
                'stream_session_id': (frame.reference.stream_session_id if frame else
                                      grabber_snapshot.get('stream_session_id')),
                'session_started_at_ms': (frame.reference.session_started_at_ms if frame else None),
                'session_time_origin_at_ms': source.session_time_origin_at_ms,
                'latest_frame_id': frame.legacy_frame_id if frame else None,
                'latest_frame_ts_ms': frame.frame_ts_ms if frame else None,
                'latest_decode_ts_ms': frame.decode_ts_ms if frame else None,
                'media_pts_ms': frame.media_pts_ms if frame else None,
                'timestamp_kind': frame.timestamp_kind if frame else None,
                'thread_alive': grabber_snapshot.get('thread_alive', False),
            }

    def _notify(self, source_id, version, state, error, epoch):
        with self._lock:
            readers = tuple(self._source(source_id).readers)
        for reader in readers:
            try:
                reader._deliver(version, state, error, epoch)
            except Exception:
                logger.exception('Frame reader status callback failed')

    def _status(self, source_id, state, error, epoch):
        with self._lock:
            source = self._source(source_id)
            if self._stopped and state != 'stopped':
                return
            if epoch < source.epoch:
                return
            if (source.state, source.error, source.epoch) == (state, error, epoch):
                return
            source.state, source.error = state, error
            if state != 'streaming' or epoch != source.epoch:
                source.frame = None
            if state in ('reconnecting', 'stopped', 'connecting'):
                source.closed_epoch = max(source.closed_epoch, epoch)
            source.epoch = epoch
            source.status_version += 1
            version = source.status_version
        self._notify(source_id, version, state, error, epoch)

    def _publish(self, source_id, captured):
        image = captured.frame
        if (not isinstance(image, np.ndarray) or image.dtype != np.uint8
                or image.ndim != 3 or image.shape[2] != 3
                or image.shape[:2] != (captured.source_height, captured.source_width)
                or image.size == 0 or image.nbytes > self._max_frame_bytes):
            raise ValueError('Expected a bounded BGR uint8 frame with matching dimensions')
        if (type(captured.source_width) is not int or captured.source_width <= 0
                or type(captured.source_height) is not int or captured.source_height <= 0
                or type(captured.frame_id) is not int or captured.frame_id <= 0
                or type(captured.stream_epoch) is not int or captured.stream_epoch <= 0
                or type(captured.frame_ts_ms) is not int or captured.frame_ts_ms < 0
                or type(captured.decode_ts_ms) is not int or captured.decode_ts_ms < 0):
            raise ValueError('Invalid input frame number, epoch or time')
        pts = captured.media_pts_ms
        if pts is not None and (isinstance(pts, bool) or not isinstance(pts, (int, float))
                                or not math.isfinite(pts) or pts < 0):
            pts = None
        if captured.timestamp_kind not in ('decode_wall_clock', 'pts_wall_estimate'):
            raise ValueError('Unsupported input clock interpretation')
        session_started_at_ms = getattr(captured, 'session_started_at_ms', None)
        time_origin_at_ms = getattr(captured, 'session_time_origin_at_ms', None)
        if session_started_at_ms is not None and (
                type(session_started_at_ms) is not int
                or session_started_at_ms < 0
                or session_started_at_ms > captured.frame_ts_ms):
            raise ValueError('Invalid input session time origin')
        if time_origin_at_ms is not None and (type(time_origin_at_ms) is not int or time_origin_at_ms < 0):
            raise ValueError('Invalid input session time origin')
        pixels = image.tobytes(order='C')
        with self._lock:
            source = self._source(source_id)
            if not self._started or self._stopped:
                raise ValueError('Input is not running')
            if (captured.stream_epoch < source.epoch
                    or captured.stream_epoch <= source.closed_epoch
                    or captured.frame_id <= source.last_frame_id):
                raise ValueError('Stale or repeated capture')
            if source.session_id is None or source.session_epoch != captured.stream_epoch:
                session_id = captured.stream_session_id
                if not isinstance(session_id, str) or not session_id.strip():
                    session_id = str(uuid.uuid4())
                source.session_id = session_id
                source.session_epoch = captured.stream_epoch
                source.sequence = 0
                source.session_started_at_ms = (captured.frame_ts_ms if session_started_at_ms is None
                                                else session_started_at_ms)
                source.session_time_origin_at_ms = (source.session_started_at_ms if time_origin_at_ms is None
                                                    else time_origin_at_ms)
                source.session_width = captured.source_width
                source.session_height = captured.source_height
            elif (isinstance(captured.stream_session_id, str)
                  and captured.stream_session_id != source.session_id):
                raise ValueError('Capture session changed within a stream epoch')
            elif (session_started_at_ms is not None
                  and session_started_at_ms != source.session_started_at_ms):
                raise ValueError('Capture time origin changed within a stream epoch')
            elif time_origin_at_ms is not None and time_origin_at_ms != source.session_time_origin_at_ms:
                raise ValueError('Capture time origin changed within a stream epoch')
            source.sequence += 1
            reference = FrameReference(source_id, source.session_id,
                                       str(uuid.uuid4()), source.sequence,
                                       source.session_started_at_ms,
                                       source.session_width, source.session_height,
                                       source.session_time_origin_at_ms)
            source.frame = SharedFrame(
                reference, pixels, captured.source_width, captured.source_height,
                captured.frame_id, captured.stream_epoch, captured.frame_ts_ms,
                captured.decode_ts_ms or captured.frame_ts_ms, pts, captured.timestamp_kind)
            source.last_frame_id = captured.frame_id
            notify = source.state != 'streaming' or source.epoch != captured.stream_epoch
            source.epoch = captured.stream_epoch
            source.state, source.error = 'streaming', None
            if notify:
                source.status_version += 1
            version = source.status_version
            captured.public_frame_ref = reference
        if notify:
            self._notify(source_id, version, 'streaming', None, captured.stream_epoch)


class HubGrabber:
    """Analyzer-compatible reader; stopping it never stops the shared input."""
    def __init__(self, hub, source_id, on_status):
        self._hub = hub
        self._source_id = source_id
        self._on_status = on_status
        self._started = False
        self._stopped = False
        self._delivery_lock = threading.Lock()
        self._last_status_version = -1
        self._pending_status = None
        self._delivering = False

    def start(self):
        with self._hub._lock:
            if self._started or self._stopped:
                raise RuntimeError('Frame reader has already been started or stopped')
            self._started = True
            source = self._hub._source(self._source_id)
            source.readers.add(self)
            initial = (source.status_version, source.state, source.error, source.epoch)
        self._deliver(*initial)

    def _deliver(self, version, state, error, epoch):
        with self._delivery_lock:
            if self._stopped or version <= self._last_status_version:
                return
            self._last_status_version = version
            self._pending_status = (state, error, epoch)
            if self._delivering:
                return
            self._delivering = True
        while True:
            with self._delivery_lock:
                status = self._pending_status
                self._pending_status = None
                if status is None or self._stopped:
                    self._delivering = False
                    return
            try:
                self._on_status(*status)
            except Exception:
                logger.exception('Frame reader status callback failed')

    def latest_frame(self):
        if not self._started or self._stopped:
            return None
        frame = self._hub.latest(self._source_id)
        return frame.as_captured() if frame else None

    def snapshot(self):
        return self._hub.snapshot(self._source_id)

    def request_stop(self):
        self.stop()

    def stop(self):
        with self._hub._lock:
            self._stopped = True
            self._hub._source(self._source_id).readers.discard(self)
