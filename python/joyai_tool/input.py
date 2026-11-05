"""Use the existing video input decoder, with explicitly registered JoyAI sessions.

The branch's FrameHub expects a newer grabber callback API than it contains.
Keep this adapter local instead of changing shared tracking capture behavior.
"""
import threading
import time
from types import SimpleNamespace
import uuid
from video_analysis.stream_grabber import _open_capture, _read_frame, MediaClockMapper


class InputHub:
    def __init__(self, sources):
        self.sources = sources
        self.frames = {}
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.threads = []

    def start(self):
        self.threads = [threading.Thread(target=self.capture, args=(source, url), daemon=True,
                                        name='joyai-input-' + source[:8]) for source, url in self.sources.items()]
        for thread in self.threads:
            thread.start()

    def stop(self):
        self.stop_event.set()
        for thread in self.threads:
            thread.join(timeout=6)

    def latest(self, source):
        with self.lock:
            return self.frames.get(source)

    def capture(self, source, url):
        while not self.stop_event.is_set():
            capture = None
            try:
                capture = _open_capture(url)
                clock = MediaClockMapper()
                session = str(uuid.uuid4())
                started = None
                sequence = 0
                while not self.stop_event.is_set():
                    captured = _read_frame(capture, clock)
                    if started is None:
                        started = captured.frame_ts_ms
                    sequence += 1
                    captured.frame.setflags(write=False)
                    reference = SimpleNamespace(source_id=source, stream_session_id=session,
                        frame_id=str(uuid.uuid5(uuid.UUID(session), str(sequence))), frame_seq=sequence,
                        session_started_at_ms=started, session_time_origin_at_ms=started,
                        session_width=captured.source_width, session_height=captured.source_height)
                    frame = SimpleNamespace(reference=reference, frame=captured.frame,
                                            frame_ts_ms=captured.frame_ts_ms)
                    with self.lock:
                        self.frames[source] = frame
            except (RuntimeError, ValueError, OSError):
                with self.lock:
                    self.frames.pop(source, None)
            finally:
                if capture is not None:
                    capture.release()
            self.stop_event.wait(2)
