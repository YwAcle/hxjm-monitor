import asyncio
import os
import struct
import time
import unittest
import sys
from types import ModuleType
from multiprocessing import shared_memory
from unittest.mock import patch

import numpy as np

from video_analysis.worker import ModelWorker, RecoverableInferenceError, model_process


def test_model(connection):
    connection.send({'type': 'ready'})
    while True:
        job = connection.recv()
        memory = shared_memory.SharedMemory(name=job['memory'])
        frame = np.ndarray(job['shape'], dtype=np.uint8, buffer=memory.buf)
        marker = int(frame[0, 0, 0])
        del frame
        memory.close()
        if marker == 99:
            time.sleep(100)  # Real stuck child; supervisor must terminate it.
        if marker == 88:
            raise SystemExit(17)
        connection.send({'type': 'result', 'job_id': job['job_id'], 'detections': [], 'inference_ms': 1})


def stuck_initialization(connection):
    time.sleep(100)


def partial_response(connection):
    connection.send({'type': 'ready'})
    connection.recv()
    # Simulate a child frozen halfway through an IPC result. poll() reports ready,
    # but a synchronous recv() would block health, heartbeats and the supervisor.
    os.write(connection.fileno(), struct.pack('!i', 10000) + b'partial')
    time.sleep(100)


class BrokenTrackerPipeline:
    def infer(self, frame, metadata):
        if frame[0, 0, 0] == 77:
            raise np.linalg.LinAlgError('not positive definite')
        return [], 1



def recoverable_model(connection):
    adapter = ModuleType('video_analysis.botsort_adapter')
    adapter.BoTSortPipeline = BrokenTrackerPipeline
    with patch.dict(sys.modules, {'video_analysis.botsort_adapter': adapter}), \
            patch('video_analysis.config.ALGORITHM', 'botsort'):
        model_process(connection)


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_tracking_error_keeps_same_model_process_and_next_job_succeeds(self):
        worker = ModelWorker(0, target=recoverable_model, model_timeout=10)
        try:
            await worker.start()
            pid = worker.process.pid
            with self.assertRaises(RecoverableInferenceError):
                await worker.infer(np.full((4, 4, 3), 77, dtype=np.uint8))
            self.assertTrue(worker.ready)
            self.assertEqual(worker.process.pid, pid)
            self.assertEqual(worker.restarts, 0)
            self.assertEqual(await worker.infer(np.zeros((4, 4, 3), dtype=np.uint8)), ([], 1))
            self.assertEqual(worker.initializations, 1)
        finally:
            await worker.stop()

    async def test_model_runs_without_reading_host_memory_thresholds(self):
        worker = ModelWorker(0, target=test_model, model_timeout=10)
        try:
            with patch('pathlib.Path.read_text', side_effect=AssertionError('No host memory preflight')):
                await worker.start()
                self.assertEqual(await worker.infer(np.zeros((4, 4, 3), dtype=np.uint8)), ([], 1))
            self.assertTrue(worker.ready)
            self.assertEqual(worker.restarts, 0)
        finally:
            await worker.stop()

    async def test_partial_ipc_response_cannot_block_supervisor(self):
        worker = ModelWorker(0, target=partial_response, model_timeout=10, inference_timeout=0.15)
        try:
            await worker.start()
            with self.assertRaises(TimeoutError):
                await asyncio.wait_for(worker.infer(np.zeros((4, 4, 3), dtype=np.uint8)), 2)
            self.assertIsNone(worker.process)
        finally:
            await worker.stop()

    async def test_actual_child_timeout_and_crash_recover_without_orphans(self):
        worker = ModelWorker(0, target=test_model, model_timeout=10, inference_timeout=0.15)
        try:
            await worker.start()
            old_pid = worker.process.pid
            with self.assertRaises(TimeoutError):
                await worker.infer(np.full((4, 4, 3), 99, dtype=np.uint8))
            self.assertIsNone(worker.process)
            self.assertFalse(worker.ready)
            await worker.start()
            self.assertNotEqual(worker.process.pid, old_pid)
            self.assertEqual(await worker.infer(np.zeros((4, 4, 3), dtype=np.uint8)), ([], 1))
            with self.assertRaises((EOFError, RuntimeError)):
                await worker.infer(np.full((4, 4, 3), 88, dtype=np.uint8))
            await worker.start()
            self.assertEqual(await worker.infer(np.zeros((4, 4, 3), dtype=np.uint8)), ([], 1))
            self.assertEqual(worker.restarts, 2)
        finally:
            await worker.stop()
        self.assertIsNone(worker.process)

    async def test_loading_timeout_and_cancel_are_bounded(self):
        worker = ModelWorker(0, target=stuck_initialization, model_timeout=0.15)
        with self.assertRaises(TimeoutError):
            await worker.start()
        self.assertIsNone(worker.process)
        worker.model_timeout = 100
        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        self.assertIsNone(worker.process)
