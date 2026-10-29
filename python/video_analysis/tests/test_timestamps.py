import unittest
from fractions import Fraction
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import numpy as np

from video_analysis.stream_grabber import (
    DECODE_THREADS,
    LatestFrameGrabber,
    MediaClockMapper,
    _open_capture,
)

class TimestampTests(unittest.TestCase):
    def test_pyav_packet_and_frame_share_session_and_packet_failure_isolated(self):
        class FakeFrame:
            pts = 0
            time_base = Fraction(1, 25)

            @staticmethod
            def to_ndarray(format):
                self.assertEqual(format, 'bgr24')
                return np.zeros((2, 3, 3), dtype=np.uint8)

        class FakePacket:
            pts = 0
            dts = 0
            duration = 1
            time_base = Fraction(1, 25)
            is_keyframe = True

            @staticmethod
            def decode():
                return [FakeFrame()]

        stream = SimpleNamespace(
            type='video', width=3, height=2,
            codec_context=SimpleNamespace(width=3, height=2),
        )
        container = SimpleNamespace(
            streams=SimpleNamespace(video=[stream]),
            demux=lambda selected: iter([FakePacket()]),
        )
        delivered = []
        packets = []

        def on_packet(*args):
            packets.append(args)
            raise RuntimeError('simulated full recorder queue')

        grabber = LatestFrameGrabber(
            lambda *args: None,
            rtsp_url='rtsp://fake/source',
            on_frame=delivered.append,
            on_packet=on_packet,
        )
        grabber._run_pyav_session(container)

        self.assertEqual(len(packets), 1)
        self.assertEqual(len(delivered), 1)
        self.assertEqual(
            packets[0][2]['stream_session_id'],
            delivered[0].stream_session_id,
        )
        self.assertEqual(delivered[0].frame_id, 1)

    def test_decoder_thread_budget_and_failed_capture_cleanup(self):
        capture = Mock()
        with patch('video_analysis.stream_grabber.cv2.VideoCapture', return_value=capture):
            self.assertIs(_open_capture('rtsp://127.0.0.1:18554/live/camera_1'), capture)
            options = capture.open.call_args.args[2]
            if hasattr(cv2, 'CAP_PROP_N_THREADS'):
                self.assertEqual(dict(zip(options[::2], options[1::2]))[cv2.CAP_PROP_N_THREADS], DECODE_THREADS)
            capture.open.return_value = False
            with self.assertRaises(RuntimeError):
                _open_capture('rtsp://127.0.0.1:18554/live/camera_1')
            capture.release.assert_called_once()

    def test_pts_absorbs_burst_decode_jitter_but_remains_approximate(self):
        clock = MediaClockMapper()
        self.assertEqual(clock.map(None, 10000), (10000, 'decode_wall_clock'))
        self.assertEqual(clock.map(0, 10000)[1], 'decode_wall_clock')
        self.assertEqual(clock.map(100, 10400), (10100, 'pts_wall_estimate'))
        self.assertEqual(clock.map(200, 10250), (10200, 'pts_wall_estimate'))
        self.assertEqual(clock.map(200, 10300)[1], 'decode_wall_clock')
        self.assertEqual(clock.map(0, 11000), (11000, 'decode_wall_clock'))
        self.assertEqual(clock.map(100, 11100), (11100, 'pts_wall_estimate'))

    def test_missing_constant_and_discontinuous_pts_reanchor(self):
        for bad in (None, float('nan'), float('inf'), -184467440737095500000):
            clock = MediaClockMapper()
            clock.map(0, 10000)
            self.assertEqual(clock.map(bad, 20000), (20000, 'decode_wall_clock'))
            self.assertEqual(clock.map(100, 20100), (20100, 'decode_wall_clock'))
            self.assertEqual(clock.map(200, 20200), (20200, 'pts_wall_estimate'))
        clock = MediaClockMapper()
        clock.map(100, 10000)
        self.assertEqual(clock.map(100, 13000), (13000, 'decode_wall_clock'))
        self.assertEqual(clock.map(200, 13100), (13100, 'pts_wall_estimate'))
        self.assertEqual(clock.map(20000, 14000), (14000, 'decode_wall_clock'))

    def test_slow_pts_cannot_consume_fresh_frames_entire_lifetime(self):
        clock = MediaClockMapper()
        fallbacks = 0
        for i in range(100):
            arrival = 10000 + i * 200
            mapped, kind = clock.map(i * 100, arrival)
            self.assertLessEqual(arrival - mapped, 500)
            self.assertLessEqual(mapped, arrival)
            fallbacks += kind == 'decode_wall_clock'
        self.assertGreater(fallbacks, 1)
