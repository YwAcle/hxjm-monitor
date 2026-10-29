import dataclasses
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch
from uuid import UUID

import numpy as np

from frame_hub.hub import FrameHub
from video_analysis.stream_grabber import CapturedFrame, LatestFrameGrabber


SOURCE_A = "10000000-0000-4000-8000-000000000001"
SOURCE_B = "10000000-0000-4000-8000-000000000002"
URL_A = "rtsp://fake/source-a"
URL_B = "rtsp://fake/source-b"


class FakeGrabber:
    instances = {}

    def __init__(self, on_status, rtsp_url, on_frame):
        self.on_status = on_status
        self.on_frame = on_frame
        self.started = False
        self.stop_requested = False
        self.stopped = False
        self.latest = None
        self.state = "idle"
        self.epoch = 0
        self.instances[rtsp_url] = self

    def start(self):
        self.started = True

    def request_stop(self):
        self.stop_requested = True

    def stop(self):
        self.request_stop()
        self.stopped = True

    def snapshot(self):
        return {
            "state": self.state,
            "error": None,
            "stream_epoch": self.epoch,
            "latest_frame_id": self.latest.frame_id if self.latest else None,
            "thread_alive": self.started and not self.stopped,
        }

    def status(self, state, epoch, error=None):
        self.state = state
        self.epoch = epoch
        self.on_status(state, error, epoch)

    def emit(self, frame_id, epoch=1, pixels=None, width=None, height=None):
        if pixels is None:
            pixels = np.full((2, 3, 3), frame_id, dtype=np.uint8)
        captured = CapturedFrame(
            frame=pixels,
            frame_ts_ms=1700000000000 + frame_id,
            source_width=pixels.shape[1] if width is None else width,
            source_height=pixels.shape[0] if height is None else height,
            frame_id=frame_id,
            stream_epoch=epoch,
            decode_ts_ms=1700000000010 + frame_id,
            media_pts_ms=frame_id * 40.0,
            timestamp_kind="pts_wall_estimate",
        )
        self.on_frame(captured)
        self.latest = captured
        self.status("streaming", epoch)
        return captured


class PacketGrabber(FakeGrabber):
    def __init__(self, on_status, rtsp_url, on_frame, on_packet=None):
        super().__init__(on_status, rtsp_url, on_frame)
        self.on_packet = on_packet

    def emit_packet(self, packet, stream, session):
        self.on_packet(packet, stream, session)


class FrameHubTests(unittest.TestCase):
    def setUp(self):
        FakeGrabber.instances = {}
        self.hub = FrameHub(
            sources={SOURCE_A: URL_A, SOURCE_B: URL_B},
            grabber_factory=FakeGrabber,
        )
        self.hub.start()
        self.addCleanup(self.hub.stop)
        self.grabber_a = FakeGrabber.instances[URL_A]
        self.grabber_b = FakeGrabber.instances[URL_B]

    def assert_uuid4(self, value):
        parsed = UUID(value)
        self.assertEqual(parsed.version, 4)
        self.assertEqual(str(parsed), value)

    def test_two_readers_share_one_input_and_public_frame_reference(self):
        first = self.hub.reader(SOURCE_A, lambda *args: None)
        second = self.hub.reader(SOURCE_A, lambda *args: None)
        first.start()
        second.start()
        self.addCleanup(first.stop)
        self.addCleanup(second.stop)

        self.assertIsNone(self.hub.latest(SOURCE_A))
        self.assertIsNone(first.latest_frame())
        self.grabber_a.emit(1)
        shared = self.hub.latest(SOURCE_A)
        first_frame = first.latest_frame()
        second_frame = second.latest_frame()

        self.assertIs(self.hub.latest(SOURCE_A), shared)
        self.assertEqual(first_frame.public_frame_ref, shared.reference)
        self.assertEqual(second_frame.public_frame_ref, shared.reference)
        self.assertEqual(shared.reference.source_id, SOURCE_A)
        self.assertEqual(shared.reference.frame_seq, 1)
        self.assert_uuid4(shared.reference.stream_session_id)
        self.assert_uuid4(shared.reference.frame_id)
        self.assertEqual((shared.source_width, shared.source_height), (3, 2))
        np.testing.assert_array_equal(first_frame.frame, second_frame.frame)
        self.assertEqual(len(FakeGrabber.instances), 2)

    def test_public_reference_preserves_capture_session_identity(self):
        reader = self.hub.reader(SOURCE_A, lambda *args: None)
        reader.start()
        self.addCleanup(reader.stop)

        capture_session_id = "50000000-0000-4000-8000-000000000001"
        captured = CapturedFrame(
            np.ones((2, 3, 3), dtype=np.uint8), 1700000000001, 3, 2,
            frame_id=1, stream_epoch=1, decode_ts_ms=1700000000011,
            media_pts_ms=0, timestamp_kind="pts_wall_estimate",
            stream_session_id=capture_session_id,
        )
        self.hub._publish(SOURCE_A, captured)

        self.assertEqual(
            self.hub.latest(SOURCE_A).reference.stream_session_id,
            capture_session_id,
        )
        self.assertEqual(reader.latest_frame().stream_session_id, capture_session_id)
        self.assertEqual(self.hub.snapshot(SOURCE_A)['stream_session_id'], capture_session_id)

    def test_public_reference_and_recording_share_the_session_time_origin(self):
        captured = CapturedFrame(
            np.ones((2, 3, 3), dtype=np.uint8), 1700000000080, 3, 2,
            frame_id=1, stream_epoch=1, decode_ts_ms=1700000000100,
            media_pts_ms=80, timestamp_kind="pts_wall_estimate",
            stream_session_id="50000000-0000-4000-8000-000000000001",
        )
        captured.session_started_at_ms = 1700000000000
        self.hub._publish(SOURCE_A, captured)

        shared = self.hub.latest(SOURCE_A)
        self.assertEqual(shared.reference.session_started_at_ms, 1700000000000)
        self.assertEqual(shared.frame_ts_ms,
                         shared.reference.session_started_at_ms + shared.media_pts_ms)
        self.assertEqual(shared.as_captured().session_started_at_ms, 1700000000000)
        self.assertEqual(self.hub.snapshot(SOURCE_A)['session_started_at_ms'], 1700000000000)

        captured.frame_id = 2
        captured.session_started_at_ms += 1
        with self.assertRaisesRegex(ValueError, 'time origin changed'):
            self.hub._publish(SOURCE_A, captured)
        self.assertIs(self.hub.latest(SOURCE_A), shared)

    def test_invalid_session_time_origin_does_not_replace_a_frame(self):
        self.grabber_a.emit(1)
        original = self.hub.latest(SOURCE_A)
        for origin in (-1, True, 1700000000003):
            captured = CapturedFrame(
                np.ones((2, 3, 3), dtype=np.uint8), 1700000000002, 3, 2,
                frame_id=2, stream_epoch=1, decode_ts_ms=1700000000012,
            )
            captured.session_started_at_ms = origin
            with self.subTest(origin=origin), self.assertRaisesRegex(ValueError, 'time origin'):
                self.hub._publish(SOURCE_A, captured)
            self.assertIs(self.hub.latest(SOURCE_A), original)

    def test_input_is_copied_and_public_views_cannot_modify_shared_pixels(self):
        reader = self.hub.reader(SOURCE_A, lambda *args: None)
        reader.start()
        self.addCleanup(reader.stop)
        pixels = np.arange(18, dtype=np.uint8).reshape(2, 3, 3)
        expected = pixels.tobytes()
        self.grabber_a.emit(1, pixels=pixels)
        shared = self.hub.latest(SOURCE_A)
        pixels[:] = 0

        self.assertIsInstance(shared.pixels, bytes)
        self.assertEqual(shared.pixels, expected)
        view = reader.latest_frame().frame
        self.assertFalse(view.flags.writeable)
        with self.assertRaises(ValueError):
            view[0, 0, 0] = 99
        with self.assertRaises(ValueError):
            view.setflags(write=True)
        with self.assertRaises((AttributeError, dataclasses.FrozenInstanceError)):
            shared.reference.frame_seq = 5
        with self.assertRaises((AttributeError, dataclasses.FrozenInstanceError)):
            shared.pixels = b"changed"

    def test_reconnect_clears_latest_and_starts_new_session_and_sequence(self):
        self.grabber_a.emit(1)
        before = self.hub.latest(SOURCE_A)
        self.grabber_a.status("reconnecting", 1, "input disconnected")
        self.assertIsNone(self.hub.latest(SOURCE_A))
        self.grabber_a.status("waiting_frame", 2)
        self.assertIsNone(self.hub.latest(SOURCE_A))
        self.grabber_a.emit(2, epoch=2)
        after = self.hub.latest(SOURCE_A)

        self.assertNotEqual(before.reference.stream_session_id,
                            after.reference.stream_session_id)
        self.assertNotEqual(before.reference.frame_id, after.reference.frame_id)
        self.assertEqual(after.reference.frame_seq, 1)
        self.assertEqual(before.reference.frame_seq, 1)
        with self.assertRaises(ValueError):
            self.grabber_a.emit(3, epoch=1)
        self.assertIs(self.hub.latest(SOURCE_A), after)

    def test_slow_reader_observes_sequence_gap_without_relabeling_frames(self):
        reader = self.hub.reader(SOURCE_A, lambda *args: None)
        reader.start()
        self.addCleanup(reader.stop)
        self.grabber_a.emit(1)
        first_ref = reader.latest_frame().public_frame_ref
        self.grabber_a.emit(2)
        self.grabber_a.emit(3)
        latest_ref = reader.latest_frame().public_frame_ref

        self.assertEqual(first_ref.frame_seq, 1)
        self.assertEqual(latest_ref.frame_seq, 3)
        self.assertEqual(first_ref.stream_session_id, latest_ref.stream_session_id)
        self.assertNotEqual(first_ref.frame_id, latest_ref.frame_id)

    def test_sources_have_separate_sessions_and_sequences(self):
        self.grabber_a.emit(1)
        first_a = self.hub.latest(SOURCE_A)
        self.grabber_b.emit(1)
        first_b = self.hub.latest(SOURCE_B)
        self.grabber_a.emit(2)

        self.assertEqual(first_a.reference.source_id, SOURCE_A)
        self.assertEqual(first_b.reference.source_id, SOURCE_B)
        self.assertNotEqual(first_a.reference.stream_session_id,
                            first_b.reference.stream_session_id)
        self.assertNotEqual(first_a.reference.frame_id, first_b.reference.frame_id)
        self.assertEqual(self.hub.latest(SOURCE_A).reference.frame_seq, 2)
        self.assertIs(self.hub.latest(SOURCE_B), first_b)

    def test_concurrent_reads_never_allocate_new_identifiers(self):
        self.grabber_a.emit(1)
        expected = self.hub.latest(SOURCE_A)
        with ThreadPoolExecutor(max_workers=8) as pool:
            frames = list(pool.map(lambda _: self.hub.latest(SOURCE_A), range(64)))
        self.assertTrue(all(frame is expected for frame in frames))
        self.assertTrue(all(frame.reference == expected.reference for frame in frames))

    def test_stopping_reader_does_not_stop_input_or_other_readers(self):
        stopped_reader = self.hub.reader(SOURCE_A, lambda *args: None)
        active_reader = self.hub.reader(SOURCE_A, lambda *args: None)
        stopped_reader.start()
        active_reader.start()
        self.addCleanup(active_reader.stop)
        stopped_reader.request_stop()
        stopped_reader.stop()
        self.grabber_a.emit(1)

        self.assertFalse(self.grabber_a.stop_requested)
        self.assertFalse(self.grabber_a.stopped)
        self.assertIsNotNone(active_reader.latest_frame())
        self.assertIsNone(stopped_reader.latest_frame())

    def test_new_reader_never_receives_initial_status_after_a_newer_status(self):
        statuses = []
        reader = self.hub.reader(SOURCE_A, lambda *status: statuses.append(status))
        deliver = reader._deliver

        def interleaved_delivery(version, *status):
            if version == 0:
                self.grabber_a.emit(1)
            deliver(version, *status)

        reader._deliver = interleaved_delivery
        reader.start()
        self.addCleanup(reader.stop)

        self.assertEqual(statuses, [('streaming', None, 1)])
        self.assertEqual(reader.latest_frame().public_frame_ref.frame_seq, 1)

    def test_reentrant_status_is_delivered_after_the_current_callback(self):
        statuses = []
        in_callback = False

        def on_status(state, error, epoch):
            nonlocal in_callback
            self.assertFalse(in_callback)
            in_callback = True
            statuses.append((state, error, epoch))
            if state == 'idle':
                self.grabber_a.emit(1)
            in_callback = False

        reader = self.hub.reader(SOURCE_A, on_status)
        reader.start()
        self.addCleanup(reader.stop)

        self.assertEqual(statuses, [('idle', None, 0), ('streaming', None, 1)])

    def test_invalid_frame_does_not_consume_sequence_or_replace_latest(self):
        self.grabber_a.emit(1)
        original = self.hub.latest(SOURCE_A)
        invalid_frames = [
            {"pixels": np.zeros((2, 3), dtype=np.uint8)},
            {"pixels": np.zeros((2, 3, 4), dtype=np.uint8)},
            {"pixels": np.zeros((2, 3, 3), dtype=np.float32)},
            {"pixels": np.zeros((0, 3, 3), dtype=np.uint8)},
            {"pixels": np.zeros((2, 3, 3), dtype=np.uint8), "width": 4},
            {"pixels": np.zeros((2, 3, 3), dtype=np.uint8), "height": 3},
        ]
        for values in invalid_frames:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    self.grabber_a.emit(2, **values)
                self.assertIs(self.hub.latest(SOURCE_A), original)
        self.grabber_a.emit(2)
        self.assertEqual(self.hub.latest(SOURCE_A).reference.frame_seq, 2)

    def test_duplicate_or_stale_input_identifier_is_rejected(self):
        self.grabber_a.emit(2)
        original = self.hub.latest(SOURCE_A)
        for frame_id in (2, 1):
            with self.subTest(frame_id=frame_id):
                with self.assertRaises(ValueError):
                    self.grabber_a.emit(frame_id)
                self.assertIs(self.hub.latest(SOURCE_A), original)
        self.grabber_a.emit(3)
        self.assertEqual(self.hub.latest(SOURCE_A).reference.frame_seq, 2)

    def test_stopped_hub_cannot_be_restarted(self):
        self.hub.stop()
        self.assertTrue(self.grabber_a.stopped)
        self.assertTrue(self.grabber_b.stopped)
        with self.assertRaises(RuntimeError):
            self.hub.start()

    def test_original_captured_frame_constructor_remains_valid(self):
        pixels = np.zeros((2, 3, 3), dtype=np.uint8)
        captured = CapturedFrame(pixels, 1700000000000, 3, 2)
        self.assertEqual(captured.frame_id, 0)
        self.assertEqual(captured.stream_epoch, 0)
        self.assertIsNone(captured.public_frame_ref)

    def test_recorder_lifecycle_and_packet_handoff(self):
        recorder = Mock()
        recorder.offer.return_value = True
        hub = FrameHub(
            sources={SOURCE_A: URL_A},
            grabber_factory=PacketGrabber,
            recorder_factory=lambda source_id: recorder,
        )
        grabber = PacketGrabber.instances[URL_A]
        try:
            hub.start()
            recorder.start.assert_called_once_with()
            session = {"stream_session_id": "session", "started_at_ms": 1}
            grabber.emit_packet("packet", "stream", session)
            recorder.offer.assert_called_once_with(
                "packet", "stream", {"stream_session_id": "session", "started_at_ms": 1,
                                      "source_id": SOURCE_A}
            )
        finally:
            hub.stop()
        recorder.stop.assert_called_once_with()

    def test_recorder_drains_after_capture_has_stopped(self):
        events = []
        recorder = Mock()
        recorder.start.side_effect = lambda: events.append('recorder-start')
        recorder.stop.side_effect = lambda: events.append('recorder-drain')
        hub = FrameHub(
            sources={SOURCE_A: URL_A},
            grabber_factory=PacketGrabber,
            recorder_factory=lambda source_id: recorder,
        )
        grabber = PacketGrabber.instances[URL_A]
        grabber.start = lambda: events.append('capture-start')
        grabber.request_stop = lambda: events.append('capture-stop-request')
        grabber.stop = lambda: events.append('capture-joined')
        hub.start()
        hub.stop()
        self.assertEqual(events, ['recorder-start', 'capture-start',
                                  'capture-stop-request', 'capture-joined', 'recorder-drain'])

    def test_recording_handoff_failure_does_not_prevent_frame_publication(self):
        recorder = Mock()
        recorder.offer.side_effect = OSError('storage unavailable')
        hub = FrameHub(
            sources={SOURCE_A: URL_A},
            grabber_factory=PacketGrabber,
            recorder_factory=lambda source_id: recorder,
        )
        hub.start()
        self.addCleanup(hub.stop)
        grabber = PacketGrabber.instances[URL_A]
        with self.assertLogs('frame_hub.hub', level='ERROR'):
            grabber.emit_packet('packet', 'stream', {})
        grabber.emit(1)
        self.assertIsNotNone(hub.latest(SOURCE_A))

    def test_capture_callback_assigns_reference_before_latest_is_visible(self):
        captured = CapturedFrame(np.zeros((2, 3, 3), dtype=np.uint8), 1, 3, 2)
        reference = object()
        published = []

        def on_frame(frame):
            self.assertIsNone(grabber.latest_frame())
            self.assertEqual((frame.frame_id, frame.stream_epoch), (1, 1))
            frame.public_frame_ref = reference

        def on_status(state, error, epoch):
            if state == 'streaming':
                published.append(grabber.latest_frame())
                grabber.request_stop()

        grabber = LatestFrameGrabber(on_status, rtsp_url=URL_A, on_frame=on_frame)
        capture = Mock()
        with patch('video_analysis.stream_grabber._open_capture', return_value=capture), \
                patch('video_analysis.stream_grabber._read_frame', return_value=captured):
            grabber._run()

        self.assertEqual(len(published), 1)
        self.assertIs(published[0], captured)
        self.assertIs(published[0].public_frame_ref, reference)
        capture.release.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
