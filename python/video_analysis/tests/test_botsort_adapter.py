import unittest
from types import SimpleNamespace

import numpy as np

from video_analysis.botsort_adapter import BoTSortPipeline, CudaGraphDetector


class Tracker:
    def __init__(self, args, frame_rate, encoder, reset_id):
        assert reset_id is False
        self.encoder = encoder
        self.timestamps = []

    def update(self, detections, frame, timestamp_ms):
        self.timestamps.append(timestamp_ms)
        return []


class AdapterTests(unittest.TestCase):
    def pipeline(self):
        pipeline = BoTSortPipeline.__new__(BoTSortPipeline)
        pipeline.args = SimpleNamespace(fps=20)
        pipeline.encoder = object()
        pipeline._tracker_class = Tracker
        pipeline.cameras = {}
        pipeline.timer = None
        pipeline.predictor = SimpleNamespace(inference=lambda *args: ([None], {}))
        return pipeline

    def test_tracker_reset_does_not_change_input_session(self):
        pipeline = self.pipeline()
        frame = np.zeros((8, 8, 3), dtype=np.uint8)
        metadata = dict(camera_id='camera_1', frame_id=1, stream_session_id='input-a',
                        tracking_context_id='tracker-a', stream_epoch=1, decode_ts_ms=1000)
        pipeline.infer(frame, metadata)
        first = pipeline.cameras['camera_1'].tracker
        pipeline.infer(frame, dict(metadata, frame_id=2, decode_ts_ms=1050))
        self.assertIs(pipeline.cameras['camera_1'].tracker, first)
        pipeline.infer(frame, dict(metadata, frame_id=3, decode_ts_ms=1100,
                                  tracking_context_id='tracker-b'))
        self.assertIsNot(pipeline.cameras['camera_1'].tracker, first)

    def test_cuda_graph_replays_new_inputs_and_keeps_postprocessing_private(self):
        import torch
        if not torch.cuda.is_available():
            self.skipTest('CUDA is required for graph replay')
        model = torch.nn.Sequential(torch.nn.Conv2d(3, 2, 1), torch.nn.SiLU()).eval().half().cuda()
        with torch.inference_mode():
            graph = CudaGraphDetector(model, (1, 3, 4, 6))
            first = torch.arange(72, device='cuda', dtype=torch.float16).reshape(1, 3, 4, 6) / 72
            actual = graph(first)
            self.assertTrue(torch.equal(actual, model(first)))
            actual.fill_(123)  # Like YOLOX's in-place coordinate postprocessing.
            second = first.flip(-1)
            self.assertTrue(torch.equal(graph(second), model(second)))
            self.assertTrue(torch.all(actual == 123))
            with self.assertRaises(ValueError):
                graph(first[:, :, :2])

    def test_camera_clocks_sessions_and_order_are_independent_with_shared_encoder(self):
        pipeline = self.pipeline()
        frame = np.zeros((8, 8, 3), dtype=np.uint8)

        def infer(camera, frame_id, decode, session='a'):
            return pipeline.infer(frame, dict(camera_id=camera, frame_id=frame_id,
                                  stream_session_id=session, stream_epoch=1, decode_ts_ms=decode))

        infer('camera_1', 1, 1000)
        first = pipeline.cameras['camera_1'].tracker
        infer('camera_2', 1, 2000)
        second = pipeline.cameras['camera_2'].tracker
        infer('camera_1', 2, 1100)
        infer('camera_2', 2, 2050)
        self.assertIsNot(first, second)
        self.assertIs(first.encoder, second.encoder)
        self.assertEqual(first.timestamps, [50., 150.])
        self.assertEqual(second.timestamps, [50., 100.])
        with self.assertRaises(ValueError):
            infer('camera_1', 2, 1150)
        infer('camera_2', 1, 2100, session='b')
        self.assertIsNot(pipeline.cameras['camera_2'].tracker, second)
        self.assertIs(pipeline.cameras['camera_1'].tracker, first)
        infer('camera_1', 3, 1200)
        self.assertEqual(first.timestamps, [50., 150., 250.])
        second = pipeline.cameras['camera_2'].tracker
        def fail(*args, **kwargs):
            raise np.linalg.LinAlgError('not positive definite')
        first.update = fail
        with self.assertRaises(np.linalg.LinAlgError):
            infer('camera_1', 4, 1300)
        self.assertNotIn('camera_1', pipeline.cameras)
        self.assertIs(pipeline.cameras['camera_2'].tracker, second)
        infer('camera_1', 5, 1400)
        self.assertIsNot(pipeline.cameras['camera_1'].tracker, first)
        self.assertIs(pipeline.cameras['camera_1'].tracker.encoder, second.encoder)
