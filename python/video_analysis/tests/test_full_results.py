import asyncio
import sys
import unittest
from multiprocessing import shared_memory
from types import ModuleType
from unittest.mock import AsyncMock, patch

import numpy as np

from video_analysis.worker import ModelWorker, model_process


class FakeConnection:
    def __init__(self, jobs=()):
        self.jobs = iter(jobs)
        self.messages = []
        self.closed = False

    def recv(self):
        try:
            return next(self.jobs)
        except StopIteration:
            raise EOFError from None

    def send(self, message):
        self.messages.append(message)

    def close(self):
        self.closed = True


class FullResultsTests(unittest.TestCase):
    def run_model(self, algorithm, detections, full_results=None):
        memory = shared_memory.SharedMemory(create=True, size=12)
        try:
            np.ndarray((2, 2, 3), dtype=np.uint8, buffer=memory.buf)[:] = 7
            job = {'job_id': 'job-1', 'memory': memory.name,
                   'shape': (2, 2, 3), 'metadata': {'camera_id': 'camera_1'}}
            if full_results is not None:
                job['full_results'] = full_results
            connection = FakeConnection([job])

            def infer(frame, metadata=None):
                self.assertEqual(frame.shape, (2, 2, 3))
                self.assertTrue(np.all(frame == 7))
                return detections, 1.5

            detector = ModuleType('video_analysis.detector_adapter')
            detector.initialize_detector = lambda: None
            detector.detect_people = infer
            tracker = ModuleType('video_analysis.botsort_adapter')
            tracker.BoTSortPipeline = lambda: type('Pipeline', (), {'infer': staticmethod(infer)})()
            with patch.dict(sys.modules, {detector.__name__: detector, tracker.__name__: tracker}), \
                    patch('video_analysis.config.ALGORITHM', algorithm):
                model_process(connection)
            self.assertTrue(connection.closed)
            self.assertEqual(connection.messages[0], {'type': 'ready'})
            self.assertEqual(connection.messages[1]['type'], 'result')
            self.assertEqual(connection.messages[1]['job_id'], 'job-1')
            self.assertEqual(connection.messages[1]['inference_ms'], 1.5)
            return connection.messages[1]['detections']
        finally:
            memory.close()
            memory.unlink()

    def test_model_keeps_default_limit_and_only_explicit_true_returns_all(self):
        detections = [{'target': index} for index in range(503)]
        for algorithm in ('deepsort', 'botsort'):
            for flag in (None, False, 1, 'true', True):
                with self.subTest(algorithm=algorithm, full_results=flag):
                    expected = detections if flag is True else detections[:500]
                    self.assertEqual(self.run_model(algorithm, detections, flag), expected)

    def test_model_preserves_empty_frame_results(self):
        for algorithm in ('deepsort', 'botsort'):
            for flag in (None, True):
                with self.subTest(algorithm=algorithm, full_results=flag):
                    self.assertEqual(self.run_model(algorithm, [], flag), [])

    def test_infer_preserves_legacy_job_and_explicit_full_results_flag(self):
        async def check():
            for flag in (False, True):
                connection = FakeConnection()
                worker = ModelWorker(0)
                worker.ready = True
                worker.connection = connection
                metadata = {'camera_id': 'camera_1'}

                async def receive(timeout):
                    return {'type': 'result', 'job_id': connection.messages[-1]['job_id'],
                            'detections': [], 'inference_ms': 1}

                worker._receive = AsyncMock(side_effect=receive)
                if flag:
                    result = await worker.infer(np.zeros((2, 2, 3), dtype=np.uint8), metadata,
                                                full_results=True)
                else:
                    result = await worker.infer(np.zeros((2, 2, 3), dtype=np.uint8), metadata)
                self.assertEqual(result, ([], 1))
                self.assertFalse(worker.busy)
                job = connection.messages[0]
                self.assertIs(job['metadata'], metadata)
                self.assertEqual(set(job), {'job_id', 'memory', 'shape', 'metadata'} |
                                 ({'full_results'} if flag else set()))
                if flag:
                    self.assertIs(job['full_results'], True)
                with self.assertRaises(FileNotFoundError):
                    shared_memory.SharedMemory(name=job['memory'])

        asyncio.run(check())


if __name__ == '__main__':
    unittest.main()
