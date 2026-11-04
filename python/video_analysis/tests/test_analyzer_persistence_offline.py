"""Exercise the real producer method with dependency doubles; never start an app."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch


def load_analyzer():
    # The scheduler method itself needs no OpenCV, NumPy, CUDA or model subprocess.
    capture = ModuleType('video_analysis.stream_grabber')
    capture.LatestFrameGrabber = lambda *a, **k: None
    worker = ModuleType('video_analysis.worker')
    worker.ModelWorker = lambda slot: SimpleNamespace(slot=slot)
    image = ModuleType('video_analysis.sync_frame')
    image.encode_frame = lambda *a: None
    modules = {m.__name__: m for m in (capture, worker, image)}
    spec = importlib.util.spec_from_file_location('video_analysis.offline_analyzer', Path(__file__).parents[1] / 'analyzer.py')
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


class ProducerBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setup_case(self):
        module = load_analyzer()
        publisher = SimpleNamespace(begin_frame=AsyncMock(return_value='stable-context'),
                                    record=AsyncMock(), failure=AsyncMock())
        analyzer = module.Analyzer(cameras={'camera_1': 'rtsp://unused'}, worker_count=1,
                                   result_publisher=publisher)
        frame = SimpleNamespace(frame=object(), frame_id=9, stream_epoch=1,
                                frame_ts_ms=time.time_ns() // 1_000_000,
                                source_width=1920, source_height=1080)
        camera = analyzer._order[0]
        camera.grabber = SimpleNamespace(latest_frame=lambda: frame,
                                         snapshot=lambda: {'stream_epoch': frame.stream_epoch})
        worker = SimpleNamespace(slot=0, generation=1, ready=True, last_removed_tracks=[7],
                                 infer=AsyncMock(return_value=([], 1)))
        return module, analyzer, publisher, camera, worker, frame

    def test_sample_pipeline_requires_result_publisher(self):
        module = load_analyzer()
        with self.assertRaises(ValueError):
            module.Analyzer(cameras={'camera_1': 'rtsp://unused'}, worker_count=1,
                            sample_pipeline=Mock())

    async def test_sample_pipeline_receives_confirmed_public_reference(self):
        _, analyzer, publisher, camera, worker, frame = self.setup_case()
        reference = SimpleNamespace(source_id='source-id', stream_session_id='input-id',
                                    frame_id='frame-id')
        publisher.record.return_value = reference
        pipeline = Mock()
        pipeline.offer.return_value = 1
        analyzer._sample_pipeline = pipeline
        await analyzer._analyze(worker, camera, frame)
        self.assertIs(frame.public_frame_ref, reference)
        pipeline.offer.assert_called_once_with(
            frame, [], tracking_context_id='stable-context', algorithm=analyzer.algorithm)

    async def test_expired_display_result_is_still_enqueued(self):
        _, analyzer, publisher, camera, worker, frame = self.setup_case()
        frame.frame_ts_ms -= 60000
        await analyzer._analyze(worker, camera, frame)
        publisher.record.assert_awaited_once()
        self.assertEqual(camera.discarded, 1)
        self.assertIsNone(camera.last_result)

    async def test_changed_display_session_does_not_relabel_inflight_facts(self):
        _, analyzer, publisher, camera, worker, frame = self.setup_case()
        original = camera.session_id
        async def infer(*args):
            camera.invalidate()
            return [], 1
        worker.infer.side_effect = infer
        await analyzer._analyze(worker, camera, frame)
        self.assertEqual(publisher.begin_frame.call_args.args[-1], original)
        self.assertEqual(publisher.record.call_args.args[0], 'stable-context')
        self.assertIsNone(camera.last_result)

    async def test_jpeg_failure_occurs_after_reliable_enqueue(self):
        module, analyzer, publisher, camera, worker, frame = self.setup_case()
        analyzer.subscribe(include_frames=True)
        def fail(*args):
            raise ValueError('synthetic image failure')
        analyzer._backoff = AsyncMock()
        with patch.object(module, 'encode_frame', fail):
            await analyzer._analyze(worker, camera, frame)
        publisher.record.assert_awaited_once()
        publisher.failure.assert_not_awaited()
        self.assertIsNotNone(camera.last_result)

    async def test_persistence_failure_does_not_reset_tracker(self):
        module, analyzer, publisher, camera, worker, frame = self.setup_case()
        original = camera.session_id
        publisher.record.side_effect = module.PersistenceError('disk unavailable')
        await analyzer._analyze(worker, camera, frame)
        self.assertEqual(camera.session_id, original)
        publisher.failure.assert_not_awaited()

    async def test_inference_failure_records_gap_without_successful_frame(self):
        _, analyzer, publisher, camera, worker, frame = self.setup_case()
        worker.infer.side_effect = ValueError('synthetic inference failure')
        analyzer._backoff = AsyncMock()
        await analyzer._analyze(worker, camera, frame)
        publisher.record.assert_not_awaited()
        publisher.failure.assert_awaited_once_with('camera_1', frame)

    async def test_display_cap_does_not_truncate_saved_targets(self):
        _, analyzer, publisher, camera, worker, frame = self.setup_case()
        worker.infer.return_value = ([{'target': i} for i in range(501)], 1)
        await analyzer._analyze(worker, camera, frame)
        self.assertEqual(len(publisher.record.call_args.args[2]), 501)
        self.assertEqual(len(camera.last_result['detections']), 500)


if __name__ == '__main__':
    unittest.main()
