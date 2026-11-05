import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np

from video_analysis.analyzer import Analyzer, Subscription


class FakeGrabber:
    def __init__(self, callback, rtsp_url):
        self.callback = callback
        self.marker = int(rtsp_url.rsplit('/', 1)[-1])
        self.available = True
        self.epoch = 1
        self.counter = 0
        self.stale = False
        self.frame_age_ms = 0

    def start(self):
        self.callback('streaming', None, self.epoch)

    def latest_frame(self):
        if not self.available:
            return None
        self.counter += 1
        return SimpleNamespace(frame=np.full((2, 2, 3), self.marker, dtype=np.uint8),
                               frame_id=self.counter, stream_epoch=self.epoch,
                               frame_ts_ms=1 if self.stale else time.time_ns() // 1_000_000 - self.frame_age_ms,
                               source_width=2, source_height=2)

    def snapshot(self):
        return {'state': 'streaming' if self.available else 'reconnecting',
                'stream_epoch': self.epoch, 'latest_frame_id': self.counter if self.available else None}

    def request_stop(self):
        pass

    def stop(self):
        pass


class FakeWorker:
    def __init__(self, slot):
        self.slot = slot
        self.ready = False
        self.generation = 0
        self.initializations = 0
        self.calls = []
        self.busy = False
        self.last_error = None
        self.fail_next = False
        self.delay = 0.005
        self.hook = None

    async def start(self):
        self.ready = True
        self.generation += 1
        self.initializations += 1

    async def stop(self):
        self.ready = False

    async def infer(self, frame, metadata=None):
        assert not self.busy
        self.busy = True
        marker = int(frame[0, 0, 0])
        self.calls.append(marker)
        try:
            if self.hook:
                self.hook(marker)
            await asyncio.sleep(self.delay)
            if self.fail_next:
                self.fail_next = False
                self.ready = False
                raise TimeoutError('fake timeout')
            return [], 5
        finally:
            self.busy = False

    def snapshot(self):
        return {'slot': self.slot, 'ready': self.ready, 'busy': self.busy,
                'model_initializations': self.initializations}


async def until(predicate, timeout=2):
    async def wait():
        while not predicate():
            await asyncio.sleep(0.005)
    await asyncio.wait_for(wait(), timeout)


class AnalyzerTests(unittest.IsolatedAsyncioTestCase):
    def make(self, **options):
        return Analyzer(cameras={f'camera_{i}': f'rtsp://fake/{i}' for i in range(1, 5)},
                        grabber_factory=FakeGrabber, worker_factory=FakeWorker,
                        inference_interval=0.001, worker_retry=0.001,
                        worker_count=options.pop('worker_count', 1), algorithm=options.pop('algorithm', 'deepsort'), **options)

    async def test_botsort_pins_each_camera_and_viewers_do_not_change_cadence(self):
        analyzer = self.make(worker_count=4, algorithm='botsort')
        await analyzer.start()
        try:
            await until(lambda: all(c.published >= 2 for c in analyzer._order))
            for index, worker in enumerate(analyzer._workers):
                self.assertEqual(set(worker.calls), {index + 1})
            self.assertTrue(analyzer.health()['tracking'])
            camera = analyzer._order[0]
            session = camera.session_id
            camera.grabber.epoch += 1
            analyzer._capture_status(camera.camera_id, 'streaming', None, camera.grabber.epoch)
            self.assertNotEqual(camera.session_id, session)
            await until(lambda: camera.last_result is not None and camera.last_result['stream_epoch'] == 2)
        finally:
            await analyzer.stop()

    async def test_botsort_shares_models_and_invalidates_all_owned_sessions_on_restart(self):
        analyzer = self.make(worker_count=1, algorithm='botsort')
        await analyzer.start()
        try:
            await until(lambda: all(c.published >= 2 for c in analyzer._order))
            worker = analyzer._workers[0]
            self.assertEqual(worker.calls[:8], [1, 2, 3, 4] * 2)
            self.assertEqual(worker.initializations, 1)
            sessions = [c.session_id for c in analyzer._order]
            worker.fail_next = True
            await until(lambda: worker.initializations == 2)
            self.assertTrue(all(c.session_id != old for c, old in zip(analyzer._order, sessions)))
            await until(lambda: all(c.last_result is not None for c in analyzer._order))
        finally:
            await analyzer.stop()

    async def test_repeated_load_failures_back_off_across_cameras_and_reset_after_inference(self):
        analyzer = self.make(algorithm='botsort', worker_retry_max=0.004)
        worker = analyzer._workers[0]
        original = worker.start
        worker.start = AsyncMock(side_effect=RuntimeError('out of memory'))
        waits = []
        backoff = analyzer._backoff

        async def record(worker):
            waits.append(analyzer._retry_delays.get(worker.slot, analyzer._worker_retry))
            await backoff(worker)
            if len(waits) == 4:
                worker.start = original

        analyzer._backoff = record
        await analyzer.start()
        try:
            await until(lambda: all(c.published for c in analyzer._order))
            self.assertEqual(waits, [0.001, 0.002, 0.004, 0.004])
            self.assertEqual(analyzer._retry_delays, {})
            self.assertEqual(worker.initializations, 1)
        finally:
            await analyzer.stop()

    async def test_model_initializations_are_serialized(self):
        analyzer = self.make(worker_count=4, algorithm='botsort')
        loading = 0
        peak = 0
        for worker in analyzer._workers:
            original = worker.start
            async def start(original=original):
                nonlocal loading, peak
                loading += 1
                peak = max(peak, loading)
                await asyncio.sleep(0.01)
                await original()
                loading -= 1
            worker.start = start
        await analyzer.start()
        try:
            await until(lambda: all(c.published for c in analyzer._order))
            self.assertEqual(peak, 1)
        finally:
            await analyzer.stop()

    async def test_round_robin_zero_targets_and_shared_service_tasks(self):
        analyzer = self.make()
        await analyzer.start()
        try:
            tasks = list(analyzer._tasks)
            clients = [analyzer.subscribe() for _ in range(3)]
            await until(lambda: all(c.published >= 2 for c in analyzer._order))
            self.assertEqual(analyzer._workers[0].calls[:8], [1, 2, 3, 4] * 2)
            self.assertEqual(analyzer._tasks, tasks)
            self.assertEqual(analyzer.health()['model_initializations'], 1)
            for camera in analyzer._order:
                self.assertEqual(camera.last_result['camera_id'], camera.camera_id)
                self.assertEqual(camera.last_result['detections'], [])
            for client in clients:
                analyzer.unsubscribe(client)
            self.assertEqual(analyzer.health()['clients'], 0)
        finally:
            await analyzer.stop()

    async def test_one_camera_offline_leaves_other_three_running(self):
        analyzer = self.make()
        camera = analyzer._order[0]
        camera.grabber.available = False
        await analyzer.start()
        try:
            await until(lambda: all(c.published >= 2 for c in analyzer._order[1:]))
            self.assertEqual(camera.attempts, 0)
            camera.grabber.available = True
            camera.grabber.epoch += 1
            await until(lambda: camera.published > 0)
            self.assertEqual(camera.last_result['stream_epoch'], 2)
        finally:
            await analyzer.stop()

    async def test_timeout_rotates_session_and_recovers_fairly(self):
        analyzer = self.make()
        camera = analyzer._order[0]
        old_session = camera.session_id
        analyzer._workers[0].fail_next = True
        await analyzer.start()
        try:
            await until(lambda: all(c.published > 0 for c in analyzer._order))
            self.assertNotEqual(camera.session_id, old_session)
            self.assertEqual(camera.session_generation, 1)
            self.assertEqual(camera.failures, 1)
            self.assertEqual(analyzer._workers[0].calls[:5], [1, 2, 3, 4, 1])
            self.assertEqual(analyzer.health()['model_initializations'], 2)
        finally:
            await analyzer.stop()

    async def test_reconnect_during_inference_discards_old_epoch(self):
        analyzer = self.make()
        camera = analyzer._order[0]
        analyzer._workers[0].hook = lambda marker: setattr(camera.grabber, 'epoch', camera.grabber.epoch + 1) if marker == 1 else None
        await analyzer.start()
        try:
            await until(lambda: camera.discarded > 0)
            self.assertEqual(camera.published, 0)
        finally:
            await analyzer.stop()

    async def test_stale_frames_not_claimed(self):
        analyzer = self.make()
        analyzer._order[0].grabber.stale = True
        await analyzer.start()
        try:
            await until(lambda: analyzer._order[3].published >= 2)
            self.assertEqual(analyzer._order[0].attempts, 0)
        finally:
            await analyzer.stop()

    async def test_takes_latest_frame_after_slot_becomes_available(self):
        analyzer = self.make()
        analyzer._workers[0].delay = 0.1
        await analyzer.start()
        try:
            await until(lambda: analyzer._order[0].inflight)
            self.assertEqual(analyzer._order[1].grabber.counter, 0)
            analyzer._order[1].grabber.counter = 1000
            await until(lambda: analyzer._order[1].published > 0)
            self.assertEqual(analyzer._order[1].last_result['frame_id'], 1002)
        finally:
            await analyzer.stop()

    async def test_result_expiring_during_inference_is_discarded(self):
        analyzer = self.make()
        analyzer._workers[0].delay = 1.25
        analyzer._order[0].grabber.frame_age_ms = 1800
        await analyzer.start()
        try:
            await until(lambda: analyzer._order[0].discarded > 0)
            self.assertEqual(analyzer._order[0].published, 0)
        finally:
            await analyzer.stop()

    async def test_four_slots_can_analyze_four_available_cameras(self):
        analyzer = self.make(worker_count=4)
        for worker in analyzer._workers:
            worker.delay = 0.1
        await analyzer.start()
        try:
            await until(lambda: analyzer.health()['active_inferences'] == 4)
            await until(lambda: all(c.published > 0 for c in analyzer._order))
            self.assertEqual(analyzer.health()['model_initializations'], 4)
        finally:
            await analyzer.stop()

    async def test_concurrency_limit_and_one_inflight_per_camera(self):
        analyzer = self.make(worker_count=2)
        active = set()
        for worker in analyzer._workers:
            async def infer(frame, worker=worker):
                marker = int(frame[0, 0, 0])
                self.assertNotIn(marker, active)
                active.add(marker)
                self.assertLessEqual(len(active), 2)
                await asyncio.sleep(0.02)
                active.remove(marker)
                return [], 20
            worker.infer = infer
        await analyzer.start()
        try:
            await until(lambda: all(c.published >= 3 for c in analyzer._order))
        finally:
            await analyzer.stop()

    async def test_status_heartbeat_responsive_during_slow_analysis(self):
        analyzer = self.make()
        analyzer._workers[0].delay = 1.2
        await analyzer.start()
        try:
            subscription = analyzer.subscribe()
            await until(lambda: analyzer._order[0].inflight)
            self.assertTrue(analyzer.health()['analysis_task_alive'])
            message = await asyncio.wait_for(subscription.next_message(), 0.1)
            self.assertEqual(message['type'], 'status')
            self.assertEqual(analyzer._order[0].published, 0)
        finally:
            await asyncio.wait_for(analyzer.stop(), 1)

    async def test_all_sources_absent_never_load_models_even_with_clients(self):
        analyzer = self.make(worker_count=4)
        for camera in analyzer._order:
            camera.grabber.available = False
        await analyzer.start()
        try:
            for _ in range(3):
                analyzer.subscribe()
            await asyncio.sleep(0.15)
            self.assertEqual(analyzer.health()['model_initializations'], 0)
            self.assertTrue(all(c.attempts == 0 for c in analyzer._order))
            analyzer._order[0].grabber.available = True
            await until(lambda: analyzer._order[0].published >= 3)
            await asyncio.sleep(0.1)
            self.assertEqual(analyzer.health()['model_initializations'], 1)
            self.assertTrue(all(c.attempts == 0 for c in analyzer._order[1:]))
        finally:
            await analyzer.stop()

    async def test_no_new_frame_does_not_repeat_inference_or_expand_pool(self):
        analyzer = self.make(worker_count=4)
        for camera in analyzer._order[1:]:
            camera.grabber.available = False
        camera = analyzer._order[0]
        frozen = camera.grabber.latest_frame()
        camera.grabber.latest_frame = lambda: frozen
        await analyzer.start()
        try:
            await until(lambda: camera.published == 1)
            await asyncio.sleep(0.15)
            self.assertEqual(camera.attempts, 1)
            self.assertEqual(analyzer.health()['model_initializations'], 1)
        finally:
            await analyzer.stop()

    async def test_idle_reaper_delays_and_recovers_on_demand(self):
        analyzer = self.make(worker_count=4, worker_idle=0.2)
        for camera in analyzer._order[1:]:
            camera.grabber.available = False
        await analyzer.start()
        try:
            await until(lambda: analyzer._order[0].published >= 2)
            camera = analyzer._order[0]
            camera.grabber.available = False
            await asyncio.sleep(0.05)
            self.assertEqual(sum(w.ready for w in analyzer._workers), 1)
            camera.grabber.available = True
            await until(lambda: camera.published >= 4)
            self.assertEqual(analyzer.health()['model_initializations'], 1)
            camera.grabber.available = False
            await until(lambda: not any(w.ready for w in analyzer._workers))
            camera.grabber.available = True
            await until(lambda: camera.published >= 6)
            self.assertEqual(analyzer.health()['model_initializations'], 2)
        finally:
            await analyzer.stop()

    async def test_source_lost_during_model_loading_submits_no_job(self):
        analyzer = self.make()
        for camera in analyzer._order[1:]:
            camera.grabber.available = False
        worker = analyzer._workers[0]
        async def start():
            await asyncio.sleep(0.05)
            analyzer._order[0].grabber.available = False
            worker.ready = True
        worker.start = start
        await analyzer.start()
        try:
            await asyncio.sleep(0.15)
            self.assertEqual(analyzer._order[0].attempts, 0)
            self.assertEqual(worker.calls, [])
        finally:
            await analyzer.stop()

    async def test_slow_subscriber_retains_each_channel_with_bounded_fair_delivery(self):
        sub = Subscription((f'camera_{i}', 'deepsort') for i in range(1, 5))
        for frame_id in range(100):
            for i in range(1, 5):
                for kind in ('status', 'detections'):
                    sub.put({'type': kind, 'camera_id': f'camera_{i}', 'task': 'deepsort', 'frame_id': frame_id})
        sub.put({'type': 'detections', 'camera_id': 'unknown', 'task': 'deepsort'})
        self.assertEqual(len(sub.pending), 8)
        received = [await sub.next_message() for _ in range(8)]
        self.assertTrue(all(m['frame_id'] == 99 for m in received))
        self.assertEqual({m['camera_id'] for m in received}, {f'camera_{i}' for i in range(1, 5)})
