import asyncio
import time
import unittest
from unittest.mock import patch

import numpy as np

from frame_hub.hub import FrameHub
from video_analysis.analyzer import Analyzer
from video_analysis.stream_grabber import CapturedFrame


SOURCE = '10000000-0000-4000-8000-000000000001'


class ManualGrabber:
    def __init__(self, on_status, rtsp_url, on_frame):
        self.on_status, self.on_frame = on_status, on_frame
        self.running = False

    def start(self):
        self.running = True

    def request_stop(self):
        self.running = False

    def stop(self):
        self.request_stop()

    def snapshot(self):
        return {'thread_alive': self.running}

    def emit(self, sequence):
        now = time.time_ns() // 1_000_000
        self.on_frame(CapturedFrame(
            np.zeros((2, 3, 3), dtype=np.uint8), now, 3, 2,
            frame_id=sequence, stream_epoch=1, decode_ts_ms=now))


class StubWorker:
    def __init__(self, slot):
        self.slot, self.generation = slot, 0
        self.ready, self.busy = False, False
        self.last_error = None
        self.calls = []

    async def start(self):
        self.ready = True
        self.generation += 1

    async def stop(self):
        self.ready = False

    async def infer(self, frame, metadata=None):
        self.calls.append(metadata)
        return [], 1


async def until(predicate):
    async def wait():
        while not predicate():
            await asyncio.sleep(0.005)
    await asyncio.wait_for(wait(), 2)


async def run_inline(function, *args, **kwargs):
    # Fake reader stops never block; isolate test-runtime executor shutdown.
    return function(*args, **kwargs)


class AnalyzerAdapterTests(unittest.IsolatedAsyncioTestCase):
    @patch('video_analysis.analyzer.asyncio.to_thread', new=run_inline)
    async def test_two_analyzers_share_input_without_sharing_tracker_lifecycle(self):
        hub = FrameHub({SOURCE: 'rtsp://fake/shared'}, grabber_factory=ManualGrabber)
        hub.start()
        grabber = hub._sources[SOURCE].grabber
        grabber.emit(1)

        def make_analyzer():
            return Analyzer(
                cameras={'camera_1': 'rtsp://fake/shared'}, worker_count=1,
                worker_factory=StubWorker, algorithm='botsort', inference_interval=0.001,
                frame_hub=hub, source_ids={'camera_1': SOURCE})

        first, second = make_analyzer(), make_analyzer()
        try:
            await first.start()
            await second.start()
            await until(lambda: first._order[0].published and second._order[0].published)
            reference = hub.latest(SOURCE).reference
            self.assertEqual(first._order[0].grabber.latest_frame().public_frame_ref, reference)
            self.assertEqual(second._order[0].grabber.latest_frame().public_frame_ref, reference)

            camera = first._order[0]
            old_tracker_session = camera.session_id
            camera.invalidate()
            self.assertNotEqual(camera.session_id, old_tracker_session)
            self.assertEqual(hub.latest(SOURCE).reference, reference)

            await first.stop()
            self.assertTrue(grabber.running)
            grabber.emit(2)
            await until(lambda: second._order[0].published == 2)
            result = second._order[0].last_result
            self.assertEqual(result['frame_id'], 2)
            self.assertEqual(result['stream_session_id'], second._order[0].session_id)
            self.assertEqual(result['input_stream_session_id'], reference.stream_session_id)
            self.assertEqual(result['tracking_context_id'], second._order[0].tracking_context_id)
            self.assertEqual(second._workers[0].calls[-1]['stream_session_id'],
                             reference.stream_session_id)
            self.assertEqual(second._workers[0].calls[-1]['tracking_context_id'],
                             second._order[0].tracking_context_id)
            self.assertNotEqual(result['stream_session_id'], reference.stream_session_id)
            self.assertNotIn('public_frame_ref', result)
            self.assertEqual(hub.latest(SOURCE).reference.stream_session_id,
                             reference.stream_session_id)
        finally:
            await first.stop()
            await second.stop()
            hub.stop()


if __name__ == '__main__':
    unittest.main()
