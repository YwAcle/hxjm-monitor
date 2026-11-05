import unittest
from fractions import Fraction
from unittest.mock import patch

import numpy as np

from video_analysis.stream_grabber import LatestFrameGrabber


class _Frame:
    def __init__(self, value, pts):
        self.pts = pts
        self.time_base = Fraction(1, 25)
        self._image = np.full((2, 3, 3), value, dtype=np.uint8)

    def to_ndarray(self, format):
        self.assert_format = format
        return self._image


class _Packet:
    def __init__(self, value, pts):
        self.pts = pts
        self.time_base = Fraction(1, 25)
        self._frame = _Frame(value, pts)

    def decode(self):
        return [self._frame]


class _Stream:
    width = 3
    height = 2


class _Streams:
    video = [_Stream()]


class _Container:
    streams = _Streams()

    def __init__(self, packets):
        self._packets = packets

    def demux(self, stream):
        return iter(self._packets)


class UnifiedCaptureTests(unittest.TestCase):
    def _grabber(self, on_frame, on_packet):
        return LatestFrameGrabber(
            lambda *args: None,
            rtsp_url="rtsp://fixture/source",
            reconnect_delay=0.01,
            on_frame=on_frame,
            on_packet=on_packet,
        )

    def test_packet_and_decoded_frame_share_session_identity(self):
        packets = []
        frames = []
        grabber = self._grabber(frames.append, lambda packet, stream, session: packets.append(session))

        grabber._run_pyav_session(_Container([_Packet(1, 0)]))

        self.assertEqual(len(packets), 1)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].stream_session_id, packets[0]["stream_session_id"])
        self.assertEqual(packets[0]["width"], 3)
        self.assertEqual(packets[0]["height"], 2)
        self.assertEqual(frames[0].stream_epoch, 1)

    def test_packet_callback_failure_does_not_drop_decoded_frame(self):
        frames = []

        def failing_packet(*args):
            raise RuntimeError("recorder queue is full")

        grabber = self._grabber(frames.append, failing_packet)
        grabber._run_pyav_session(_Container([_Packet(1, 0)]))

        self.assertEqual(len(frames), 1)
        np.testing.assert_array_equal(frames[0].frame, np.full((2, 3, 3), 1, dtype=np.uint8))

    def test_nonzero_pts_and_decode_jitter_keep_the_recording_time_origin(self):
        packets, frames = [], []
        grabber = self._grabber(frames.append, lambda packet, stream, session: packets.append(session))
        with patch('video_analysis.stream_grabber.time.time_ns', side_effect=[
                10_000_000_000, 10_300_000_000, 10_400_000_000, 10_500_000_000]):
            grabber._run_pyav_session(_Container([_Packet(1, 25), _Packet(2, 26)]))
        self.assertEqual([session['started_at_ms'] for session in packets], [10000, 10000])
        self.assertEqual([frame.session_started_at_ms for frame in frames], [10000, 10000])
        self.assertEqual([frame.session_time_origin_at_ms for frame in frames], [9000, 9000])
        self.assertEqual([frame.frame_ts_ms for frame in frames], [10000, 10040])
        self.assertEqual([frame.decode_ts_ms for frame in frames], [10300, 10500])

    def test_reconnect_starts_new_session_identity(self):
        sessions = []
        frames = []
        grabber = self._grabber(frames.append, lambda packet, stream, session: sessions.append(session))

        grabber._run_pyav_session(_Container([_Packet(1, 0)]))
        grabber._run_pyav_session(_Container([_Packet(2, 0)]))

        self.assertEqual(len(sessions), 2)
        self.assertNotEqual(sessions[0]["stream_session_id"], sessions[1]["stream_session_id"])
        self.assertEqual(frames[0].stream_session_id, sessions[0]["stream_session_id"])
        self.assertEqual(frames[1].stream_session_id, sessions[1]["stream_session_id"])
        self.assertEqual([frame.stream_epoch for frame in frames], [1, 2])


if __name__ == "__main__":
    unittest.main()
