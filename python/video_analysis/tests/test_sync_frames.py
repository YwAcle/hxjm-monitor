import asyncio
import base64
import time
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

from video_analysis.analyzer import Analyzer
from video_analysis.app import _send_messages
from video_analysis.sync_frame import encode_frame
from video_analysis.stream_grabber import CapturedFrame


def decoded(frame):
    return cv2.imdecode(np.frombuffer(base64.b64decode(frame['data']), dtype=np.uint8), cv2.IMREAD_COLOR)


class SyncFrameTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_frame_encoding_overlaps_inference_once_for_all_viewers(self):
        analyzer = Analyzer(cameras={'camera_1': 'rtsp://fake/1'}, worker_count=1)
        analyzer._loop = asyncio.get_running_loop()
        viewers = [analyzer.subscribe(include_frames=True) for _ in range(3)]
        camera = analyzer._order[0]
        captured = CapturedFrame(frame=np.zeros((8, 8, 3), dtype=np.uint8), frame_id=9,
                                 stream_epoch=1, frame_ts_ms=time.time_ns() // 1_000_000,
                                 source_width=8, source_height=8)
        camera.grabber._latest = captured
        encoded = threading.Event()

        def encode(image, frame_id):
            encoded.set()
            return encode_frame(image, frame_id)

        class Worker:
            slot = 0
            generation = 1

            async def infer(self, frame, metadata=None):
                if not await asyncio.to_thread(encoded.wait, 1):
                    raise AssertionError('JPEG was deferred until after inference')
                return [], 1

        with patch('video_analysis.analyzer.encode_frame', side_effect=encode) as called:
            await analyzer._analyze(Worker(), camera, captured)
            await asyncio.gather(*analyzer._image_tasks.values())
        called.assert_called_once()
        self.assertEqual(camera.failures, 0)
        for viewer in viewers:
            result = viewer.pending[('camera_1', 'deepsort', 'detections')]
            self.assertNotIn('frame', camera.last_result)
            self.assertEqual(result['frame_id'], camera.last_result['frame_id'])
            self.assertEqual(result['frame_id'], result['frame']['frame_id'])

    async def test_live_viewers_share_inference_without_encoding_images(self):
        analyzer = Analyzer(cameras={'camera_1': 'rtsp://fake/1'}, worker_count=1)
        analyzer._loop = asyncio.get_running_loop()
        viewers = [analyzer.subscribe(include_frames=False) for _ in range(4)]
        camera = analyzer._order[0]
        captured = CapturedFrame(frame=np.zeros((8, 8, 3), dtype=np.uint8), frame_id=1,
                                 stream_epoch=1, frame_ts_ms=time.time_ns() // 1_000_000,
                                 source_width=8, source_height=8)
        camera.grabber._latest = captured

        class Worker:
            slot = 0
            generation = 1
            calls = 0

            async def infer(self, frame, metadata=None):
                self.calls += 1
                return [], 1

        worker = Worker()
        with patch('video_analysis.analyzer.encode_frame', side_effect=AssertionError('Live mode encoded JPEG')):
            await analyzer._analyze(worker, camera, captured)
        self.assertEqual(worker.calls, 1)
        for viewer in viewers:
            result = viewer.pending[('camera_1', 'deepsort', 'detections')]
            self.assertNotIn('frame', result)
            self.assertIs(result, camera.last_result)

    def test_encoding_preserves_clean_input_and_bounds_image_size(self):
        image = np.full((1080, 1920, 3), [20, 80, 200], dtype=np.uint8)
        original = image.copy()
        encoded = encode_frame(image, 7)
        self.assertEqual(encoded['frame_id'], 7)
        self.assertEqual((encoded['width'], encoded['height']), (1280, 720))
        np.testing.assert_array_equal(image, original)
        np.testing.assert_allclose(decoded(encoded)[360, 640], [20, 80, 200], atol=3)

    async def test_frame_is_inference_input_even_when_capture_advances(self):
        analyzer = Analyzer(cameras={'camera_1': 'rtsp://fake/1'}, worker_count=1)
        analyzer._loop = asyncio.get_running_loop()
        analyzer.subscribe(include_frames=True)
        camera = analyzer._order[0]
        image = np.full((16, 16, 3), 30, dtype=np.uint8)
        captured = CapturedFrame(frame=image, frame_id=11, stream_epoch=1,
                                 frame_ts_ms=time.time_ns() // 1_000_000,
                                 source_width=16, source_height=16)
        # The latest slot already points at a different image when inference returns.
        camera.grabber._latest = SimpleNamespace(**{**captured.__dict__, 'frame': np.full_like(image, 220)})

        class Worker:
            slot = 0
            generation = 1

            async def infer(self, frame, metadata=None):
                self.input = frame.copy()
                return [{'label': 'person', 'confidence': 0.9, 'bbox': [0.1, 0.2, 0.5, 0.8]}], 5

        worker = Worker()
        await analyzer._analyze(worker, camera, captured)
        await asyncio.gather(*analyzer._image_tasks.values())
        result = next(sub for sub in analyzer._subscriptions).pending[('camera_1', 'deepsort', 'detections')]
        self.assertEqual(result['frame_id'], result['frame']['frame_id'])
        np.testing.assert_allclose(decoded(result['frame']), worker.input, atol=2)
        self.assertEqual(int(decoded(result['frame'])[0, 0, 0]), 30)

    async def test_slow_diagnostic_encoding_does_not_wait_or_queue_more_images(self):
        analyzer = Analyzer(cameras={'camera_1': 'rtsp://fake/1'}, worker_count=1)
        live = analyzer.subscribe()
        diagnostic = analyzer.subscribe(include_frames=True)
        camera = analyzer._order[0]
        release = asyncio.Event()
        started = asyncio.Event()
        calls = []

        async def blocked_encode(function, *args):
            calls.append(args[1])
            started.set()
            await release.wait()
            return function(*args)

        class Worker:
            slot = 0
            generation = 1
            calls = 0

            async def infer(self, frame, metadata=None):
                self.calls += 1
                await asyncio.sleep(0)
                return [], 1

        worker = Worker()
        with patch('video_analysis.analyzer.asyncio.to_thread', new=blocked_encode):
            try:
                for sequence in (1, 2):
                    captured = CapturedFrame(np.zeros((8, 8, 3), dtype=np.uint8),
                                             time.time_ns() // 1_000_000, 8, 8,
                                             frame_id=sequence, stream_epoch=1)
                    camera.grabber._latest = captured
                    await asyncio.wait_for(analyzer._analyze(worker, camera, captured), 1)
                await asyncio.wait_for(started.wait(), 1)
                self.assertEqual(worker.calls, 2)
                self.assertEqual(calls, [1])
                self.assertEqual(len(analyzer._image_tasks), 1)
                self.assertEqual(live.pending[('camera_1', 'deepsort', 'detections')]['frame_id'], 2)
                self.assertNotIn(('camera_1', 'deepsort', 'detections'), diagnostic.pending)
            finally:
                release.set()
                await asyncio.gather(*analyzer._image_tasks.values())
        pair = diagnostic.pending[('camera_1', 'deepsort', 'detections')]
        self.assertEqual(pair['frame_id'], pair['frame']['frame_id'])
        self.assertEqual(pair['frame_id'], 1)
        self.assertEqual(camera.last_result['frame_id'], 2)

    async def test_diagnostic_image_is_discarded_after_session_change_or_expiry(self):
        for invalidation in ('session', 'expiry'):
            with self.subTest(invalidation=invalidation):
                analyzer = Analyzer(cameras={'camera_1': 'rtsp://fake/1'}, worker_count=1)
                diagnostic = analyzer.subscribe(include_frames=True)
                camera = analyzer._order[0]
                release = asyncio.Event()
                captured = CapturedFrame(np.zeros((8, 8, 3), dtype=np.uint8),
                                         time.time_ns() // 1_000_000, 8, 8,
                                         frame_id=1, stream_epoch=1)
                camera.grabber._latest = captured

                async def blocked_encode(function, *args):
                    await release.wait()
                    return function(*args)

                class Worker:
                    slot = 0
                    generation = 1

                    async def infer(self, frame, metadata=None):
                        return [], 1

                with patch('video_analysis.analyzer.asyncio.to_thread', new=blocked_encode):
                    await analyzer._analyze(Worker(), camera, captured)
                    if invalidation == 'session':
                        camera.invalidate()
                    else:
                        camera.last_result['valid_until_ms'] = 0
                    release.set()
                    await asyncio.gather(*analyzer._image_tasks.values())
                self.assertNotIn(('camera_1', 'deepsort', 'detections'), diagnostic.pending)

    async def test_json_only_subscriber_does_not_receive_images(self):
        class Sent(Exception):
            pass

        class Socket:
            async def send_json(self, message):
                self.message = message
                raise Sent()

        for include_frames in (False, True):
            analyzer = Analyzer(cameras={'camera_1': 'rtsp://fake/1'}, worker_count=1)
            sub = analyzer.subscribe(include_frames=include_frames)
            sub.pending.clear()
            sub.put({'type': 'detections', 'camera_id': 'camera_1', 'task': 'deepsort',
                     'frame': {'frame_id': 10}, 'valid_until_ms': time.time_ns() // 1_000_000 + 3000})
            socket = Socket()
            with self.assertRaises(Sent):
                await _send_messages(socket, sub, asyncio.Lock())
            self.assertEqual('frame' in socket.message, include_frames)
