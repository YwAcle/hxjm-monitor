import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import gc
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid
import weakref
from unittest.mock import patch

import numpy as np

from frame_hub.hub import FrameReference
from video_analysis.analyzer import Analyzer, TASK
from video_analysis.config import camera_source_ids
from video_analysis.business_runtime import BusinessRuntime
from video_analysis.frame_result import frame_result, registration_request
from video_analysis.result_delivery import ResultDispatcher
from video_analysis.result_spool import ResultSpool
from video_analysis.sample_pipeline import LocalSamplePipeline
from video_analysis.stream_grabber import CapturedFrame


SOURCE = '10000000-0000-4000-8000-000000000001'
INPUT_SESSION = '20000000-0000-4000-8000-000000000001'
TRACKER = '30000000000040008000000000000001'


def capture(sequence=1, milliseconds=None):
    return CapturedFrame(
        np.zeros((4, 6, 3), dtype=np.uint8),
        time.time_ns() // 1_000_000 if milliseconds is None else milliseconds, 6, 4,
        frame_id=sequence, stream_epoch=1, decode_ts_ms=milliseconds or 1,
        media_pts_ms=sequence * 40.25, timestamp_kind='pts_wall_estimate',
        public_frame_ref=FrameReference(SOURCE, INPUT_SESSION, str(uuid.uuid4()), sequence))


def detection(index=1):
    return {'label': 'person', 'track_id': index, 'bbox': [0.1, 0.2, 0.5, 0.9],
            'confidence': 0.9, 'is_prediction': False}


def completed(captured, targets, tracker=TRACKER):
    return frame_result(captured, targets, camera_id='camera_1', algorithm='botsort',
                        tracking_session=tracker, session_generation=2,
                        worker_slot=0, worker_generation=1,
                        processed_at_ms=captured.frame_ts_ms + 20)


class Worker:
    slot = 0
    generation = 7
    ready = True

    def __init__(self, targets, hook=None):
        self.targets, self.hook = targets, hook
        self.full_results = None

    async def infer(self, image, metadata=None, full_results=False):
        self.full_results = full_results
        if self.hook:
            self.hook()
        return self.targets, 1


class ResultDeliveryTests(unittest.TestCase):
    def replay_dispatcher(self, spool, response, callback):
        execution = {'task_id': str(uuid.uuid4()), 'run_id': str(uuid.uuid4()),
                     'result_set_id': str(uuid.uuid4()), 'set_key': 'tracking:fixture',
                     'capability_code': 'tracking'}
        return ResultDispatcher(spool, actor_key='service:test',
                                units={(SOURCE, 'botsort'): execution},
                                window_for=BusinessRuntime.window_for,
                                submit=lambda *_: response, on_confirmed=callback)

    def analyze(self, targets, sink, captured=None, hook=None, sample_pipeline=None):
        async def run():
            analyzer = Analyzer(cameras={'camera_1': 'rtsp://fake/1'}, worker_count=1,
                                algorithm='botsort', result_sink=sink, sample_pipeline=sample_pipeline)
            analyzer._loop = asyncio.get_running_loop()
            camera = analyzer._order[0]
            current = captured if captured is not None else capture()
            camera.grabber._latest = current
            worker = Worker(targets, hook=lambda: hook(camera) if hook else None)
            old_session = camera.session_id
            old_generation = camera.session_generation
            await analyzer._analyze(worker, camera, current)
            return analyzer, camera, worker, old_session, old_generation
        return asyncio.run(run())

    def test_all_targets_are_handed_off_but_legacy_display_stays_capped(self):
        received = []
        analyzer, camera, worker, _, _ = self.analyze(
            [detection(index) for index in range(503)], received.append)
        self.assertTrue(worker.full_results)
        self.assertEqual(len(received[0]['result']['targets']), 503)
        self.assertEqual(len(camera.last_result['detections']), 500)
        self.assertEqual(camera.last_result['task'], TASK)
        self.assertEqual(camera.last_result['frame_id'], 1)
        self.assertNotIn('public_frame_ref', camera.last_result)
        self.assertEqual(analyzer._result_handoffs, 1)

    def test_zero_target_frame_is_handed_off(self):
        received = []
        _, camera, _, _, _ = self.analyze([], received.append)
        self.assertEqual(received[0]['result']['targets'], [])
        self.assertEqual(camera.published, 1)
        self.assertNotEqual(received[0]['result']['result_id'], received[0]['result']['frame_id'])

    def test_display_expiry_does_not_remove_the_historical_result(self):
        received = []
        current = capture(milliseconds=time.time_ns() // 1_000_000 - 10000)
        _, camera, _, _, _ = self.analyze([], received.append, current)
        self.assertEqual(len(received), 1)
        self.assertEqual(camera.discarded, 1)
        self.assertIsNone(camera.last_result)

    def test_context_is_captured_before_inference_and_not_read_after_reset(self):
        received = []
        _, camera, _, session, generation = self.analyze(
            [detection()], received.append, hook=lambda camera: camera.invalidate())
        result = received[0]
        self.assertEqual(result['tracking_context_id'], str(uuid.UUID(session)))
        self.assertEqual(result['session_generation'], generation)
        self.assertEqual(result['worker_generation'], 7)
        self.assertEqual(result['stream_session_id'], INPUT_SESSION)
        self.assertEqual(result['tracking_context']['context_key'], 'tracker:' + str(uuid.UUID(session)))
        self.assertIsNone(camera.tracking_started_at_ms)
        self.assertNotEqual(camera.session_id, session)
        self.assertIsNone(camera.last_result)

    def test_sink_failure_does_not_restart_successful_tracking(self):
        def unavailable(result):
            raise OSError('test storage unavailable')
        with self.assertLogs('video_analysis.analyzer', level='ERROR'):
            analyzer, camera, _, session, _ = self.analyze([], unavailable)
        self.assertEqual(camera.session_id, session)
        self.assertEqual(camera.failures, 0)
        self.assertEqual(camera.published, 1)
        self.assertEqual(analyzer._result_failures, 1)
        self.assertEqual(analyzer._result_handoffs, 0)

    def test_sample_handoff_failure_preserves_live_and_historical_results(self):
        class FailedSampler:
            def offer(self, *args, **kwargs):
                raise RuntimeError('sample queue unavailable')
        received = []
        with self.assertLogs('video_analysis.analyzer', level='ERROR'):
            analyzer, camera, _, session, _ = self.analyze([detection()], received.append,
                                                          sample_pipeline=FailedSampler())
        self.assertEqual(camera.session_id, session)
        self.assertEqual(camera.failures, 0)
        self.assertEqual(camera.published, 1)
        self.assertEqual(len(received), 1)
        self.assertEqual(analyzer._result_handoffs, 1)

    def test_no_sink_keeps_legacy_worker_call_and_health(self):
        _, camera, worker, _, _ = self.analyze([], None)
        self.assertFalse(worker.full_results)
        self.assertEqual(camera.published, 1)

    def test_async_sink_is_not_mistaken_for_successful_handoff(self):
        async def sink(result):
            raise AssertionError('Async sink must not be accepted')
        async def reject_async_sink():
            with self.assertRaises(ValueError):
                Analyzer(cameras={'camera_1': 'rtsp://fake/1'}, result_sink=sink)
        asyncio.run(reject_async_sink())
        with self.assertLogs('video_analysis.analyzer', level='ERROR'):
            analyzer, camera, _, _, _ = self.analyze([], lambda result: sink(result))
        self.assertEqual(analyzer._result_handoffs, 0)
        self.assertEqual(analyzer._result_failures, 1)
        self.assertEqual(camera.published, 1)

    def test_jpeg_failure_happens_after_result_handoff(self):
        async def inline(function, *args):
            return function(*args)

        async def run():
            received = []
            analyzer = Analyzer(cameras={'camera_1': 'rtsp://fake/1'}, worker_count=1,
                                algorithm='botsort', result_sink=received.append)
            analyzer._loop = asyncio.get_running_loop()
            ordinary = analyzer.subscribe()
            analyzer.subscribe(include_frames=True)
            camera = analyzer._order[0]
            session = camera.session_id
            current = capture()
            camera.grabber._latest = current
            with patch('video_analysis.analyzer.asyncio.to_thread', new=inline), \
                    patch('video_analysis.analyzer.encode_frame', side_effect=ValueError('test jpeg')), \
                    patch.object(analyzer, '_backoff', return_value=None), \
                    self.assertLogs('video_analysis.analyzer', level='WARNING'):
                await analyzer._analyze(Worker([]), camera, current)
                await asyncio.gather(*list(analyzer._image_tasks.values()))
            self.assertEqual(len(received), 1)
            self.assertEqual(camera.session_id, session)
            self.assertEqual(camera.failures, 0)
            self.assertEqual(camera.inferences, 1)
            self.assertEqual(camera.published, 1)
            self.assertEqual(analyzer._result_failures, 0)
            self.assertEqual(camera.states['analyzer']['state'], 'ready')
            self.assertTrue(any(message['type'] == 'detections'
                                for message in ordinary.pending.values()))
        asyncio.run(run())

    def test_blocked_dispatcher_preserves_live_results_and_later_saves_all_targets(self):
        project = Path(__file__).resolve().parents[3]
        entered, release = threading.Event(), threading.Event()
        built, requests = [], []
        caller_thread = threading.get_ident()
        execution = {'task_id': str(uuid.uuid4()), 'run_id': str(uuid.uuid4()),
                     'result_set_id': str(uuid.uuid4()), 'set_key': 'tracking:fixture',
                     'capability_code': 'tracking'}
        with tempfile.TemporaryDirectory(prefix='.test-deferred-delivery-', dir=project) as directory:
            spool = ResultSpool(directory)
            pending = spool.pending
            def slow_pending():
                entered.set()
                if not release.wait(2):
                    raise OSError('test blocked storage timeout')
                return pending()
            def build(metadata, targets, **options):
                result = frame_result(metadata, targets, **options)
                built.append((threading.get_ident(), result))
                return result
            def submit(actor, operation, payload):
                durable = spool.read(pending()[0])['payload']
                self.assertEqual(durable, payload)
                requests.append(deepcopy(payload))
                return {'accepted_result_ids': [result['result_id'] for result in payload['results']],
                        'duplicate_result_ids': [], 'rejected_results': []}
            dispatcher = ResultDispatcher(
                spool, actor_key='service:test', units={(SOURCE, 'botsort'): execution},
                window_for=BusinessRuntime.window_for, submit=submit,
                batch_size=1, flush_interval=0.01)
            with patch.object(spool, 'pending', side_effect=slow_pending), \
                    patch('video_analysis.analyzer.frame_result', new=build):
                dispatcher.start()
                try:
                    self.assertTrue(entered.wait(1))
                    current = capture()
                    pixels = weakref.ref(current.frame)
                    before = time.monotonic()
                    analyzer, camera, worker, session, generation = self.analyze(
                        [detection(index) for index in range(503)], dispatcher, current)
                    self.assertLess(time.monotonic() - before, 0.25)
                    self.assertEqual(camera.published, 1)
                    self.assertEqual(len(camera.last_result['detections']), 500)
                    self.assertEqual(analyzer._result_handoffs, 1)
                    self.assertEqual(dispatcher.status()['queued_frames'], 1)
                    self.assertEqual(built, [])
                    camera.grabber._latest = None
                    del current
                    gc.collect()
                    self.assertIsNone(pixels(), 'queued historical work must not retain frame pixels')
                    camera.invalidate()
                    worker.generation = 99
                    release.set()
                    deadline = time.monotonic() + 2
                    while dispatcher.status()['confirmed_batches'] != 1 and time.monotonic() < deadline:
                        time.sleep(0.005)
                    self.assertEqual(dispatcher.status()['confirmed_batches'], 1)
                    self.assertEqual(len(built), 1)
                    self.assertNotEqual(built[0][0], caller_thread)
                    self.assertEqual(built[0][1]['worker_generation'], 7)
                    self.assertEqual(built[0][1]['session_generation'], generation)
                    self.assertEqual(built[0][1]['tracking_context_id'], str(uuid.UUID(session)))
                    self.assertEqual(len(requests[0]['results'][0]['targets']), 503)
                    self.assertEqual(dispatcher.status()['persisted_frames'], 1)
                    self.assertEqual(pending(), [])
                finally:
                    release.set()
                    self.assertTrue(dispatcher.stop(timeout=2))

    def test_time_and_prediction_mapping_do_not_invent_video_offsets(self):
        predicted = dict(detection(), confidence=None, is_prediction=True)
        current = capture()
        output = completed(current, [predicted])
        result = output['result']
        self.assertEqual(result['time_quality'], 'ingest_estimated')
        self.assertEqual(result['stream_pts_ms'], 40)
        self.assertIsNone(result['media_pts_ms'])
        self.assertIsNone(result['media_asset_id'])
        self.assertIsNone(result['targets'][0]['confidence'])
        predicted['bbox'][0] = 0.3
        self.assertEqual(result['targets'][0]['bbox'][0], 0.1)
        with self.assertRaises(ValueError):
            completed(current, [dict(detection(), confidence=None)])

    def test_batch_registration_restart_and_confirmation(self):
        start = datetime(2026, 10, 26, 2, 0, tzinfo=timezone.utc)
        frames = [completed(capture(seq, int(start.timestamp() * 1000) + seq * 40),
                            [detection()] if seq == 4 else []) for seq in (1, 4)]
        execution = {
            'task_id': str(uuid.uuid4()), 'run_id': str(uuid.uuid4()),
            'result_set_id': str(uuid.uuid4()), 'set_key': 'tracking:camera_1',
            'capability_code': 'tracking',
            'tracking_context': {'context_key': 'tracker:' + TRACKER,
                                 'started_at': start.isoformat(), 'reset_reason': None},
        }
        coverage = {'start_at': start.isoformat(), 'end_at': (start + timedelta(seconds=1)).isoformat(),
                    'closed': True, 'analyzed_frame_count': 2,
                    'frame_ids': [frame['result']['frame_id'] for frame in frames], 'gaps': []}
        payload = registration_request(frames, execution, coverage, request_id='req-normal-1')
        self.assertEqual([result['frame_seq'] for result in payload['results']], [1, 4])
        project = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory(prefix='.test-result-delivery-', dir=project) as directory:
            spool = ResultSpool(directory)
            key = spool.put('service:test', 'results.register', payload)
            restarted = ResultSpool(directory)
            self.assertEqual(restarted.pending(), [key])
            self.assertEqual(restarted.read(key)['payload'], payload)
            response = {'accepted_result_ids': [result['result_id'] for result in payload['results']],
                        'duplicate_result_ids': [], 'rejected_results': []}
            self.assertTrue(restarted.acknowledge(key, response))
            self.assertEqual(restarted.pending(), [])
        frames[0]['result']['targets'].append(detection())
        self.assertEqual(payload['results'][0]['targets'], [])

    def test_saved_and_duplicate_frames_notify_consumer_and_clear_spool(self):
        for status in ('accepted_result_ids', 'duplicate_result_ids'):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                spool = ResultSpool(directory)
                payload = {'request_id': 'confirmed', 'results': [{'result_id': 'result-1'}]}
                spool.put('service:test', 'results.register', payload)
                response = {'accepted_result_ids': [], 'duplicate_result_ids': [], 'rejected_results': []}
                response[status] = ['result-1']
                notifications = []
                dispatcher = self.replay_dispatcher(spool, response,
                                                    lambda request, reply: notifications.append((request, reply)))
                dispatcher._replay()
                self.assertEqual(notifications, [(payload, response)])
                self.assertEqual(spool.pending(), [])
                self.assertEqual(dispatcher.status()['confirmed_batches'], 1)

    def test_partial_confirmation_only_releases_samples_for_saved_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            spool = ResultSpool(directory)
            context = str(uuid.uuid4())
            frames = [capture(number) for number in (1, 2, 3)]
            pipeline = LocalSamplePipeline(object(), threshold=0.88, instance_id=str(uuid.uuid4()),
                                           extractor=object(), queue_size=3)
            for number, frame in enumerate(frames, start=1):
                self.assertEqual(pipeline.offer(frame, [detection(number)], tracking_context_id=context), 1)
            payload = {'request_id': 'partial', 'source_id': SOURCE,
                       'results': [{'result_id': 'result-' + str(number),
                                    'frame_id': frame.public_frame_ref.frame_id}
                                   for number, frame in enumerate(frames, start=1)]}
            spool.put('service:test', 'results.register', payload)
            response = {'accepted_result_ids': ['result-1'], 'duplicate_result_ids': ['result-2'],
                        'rejected_results': [{'result_id': 'result-3', 'retryable': True}],
                        'tracklets': [{'tracking_context_id': context, 'local_track_id': number,
                                      'tracklet_id': str(uuid.uuid4())} for number in (1, 2, 3)]}
            dispatcher = self.replay_dispatcher(spool, response, pipeline.confirmed)
            dispatcher._replay()
            jobs = {key[2]: job for key, job in pipeline._jobs.items()}
            self.assertIsNotNone(jobs[1].tracklet_id)
            self.assertIsNotNone(jobs[2].tracklet_id)
            self.assertIsNone(jobs[3].tracklet_id)
            pending = spool.pending()
            self.assertEqual(len(pending), 1)
            self.assertEqual(spool.read(pending[0])['payload']['results'], [payload['results'][2]])
            self.assertEqual(dispatcher.status()['partial_batches'], 1)

    def test_sample_consumer_failure_does_not_revoke_saved_frame_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            spool = ResultSpool(directory)
            payload = {'request_id': 'consumer-fails', 'results': [{'result_id': 'result-1'}]}
            spool.put('service:test', 'results.register', payload)
            response = {'accepted_result_ids': ['result-1'], 'duplicate_result_ids': [], 'rejected_results': []}
            def failed_consumer(*_):
                raise RuntimeError('sample processing failed')
            dispatcher = self.replay_dispatcher(spool, response, failed_consumer)
            with self.assertLogs('video_analysis.result_delivery', level='ERROR'):
                dispatcher._replay()
            self.assertEqual(spool.pending(), [])
            self.assertEqual(dispatcher.status()['confirmed_batches'], 1)

    def test_registration_requires_real_execution_and_explicit_window(self):
        current = capture()
        output = completed(current, [])
        execution = {'task_id': str(uuid.uuid4()), 'run_id': str(uuid.uuid4()),
                     'result_set_id': str(uuid.uuid4()), 'set_key': 'tracking:camera_1',
                     'capability_code': 'tracking',
                     'tracking_context': {'context_key': 'tracker:' + TRACKER,
                                          'started_at': output['result']['occurred_at']}}
        instant = datetime.fromisoformat(output['result']['occurred_at'])
        coverage = {'start_at': instant.isoformat(), 'end_at': (instant + timedelta(seconds=1)).isoformat(),
                    'closed': False, 'analyzed_frame_count': 1,
                    'frame_ids': [output['result']['frame_id']], 'gaps': []}
        with self.assertRaises(KeyError):
            registration_request([output], {}, coverage, request_id='req-1')
        bad = deepcopy(coverage)
        bad['end_at'] = bad['start_at']
        with self.assertRaises(ValueError):
            registration_request([output], execution, bad, request_id='req-1')
        bad = deepcopy(coverage)
        bad['frame_ids'] = []
        with self.assertRaises(ValueError):
            registration_request([output], execution, bad, request_id='req-1')
        other = completed(capture(2), [], tracker=str(uuid.uuid4()))
        with self.assertRaises(ValueError):
            registration_request([output, other], execution, coverage, request_id='req-1')

    def test_camera_source_mapping_is_explicit_and_complete(self):
        cameras = {'camera_1': 'rtsp://fake/1'}
        self.assertEqual(camera_source_ids(cameras, json.dumps({'camera_1': SOURCE})), {'camera_1': SOURCE})
        for raw in ({}, {'camera_1': 'camera_1'}, {'camera_1': str(uuid.UUID(int=0))},
                    {'camera_1': SOURCE, 'camera_2': INPUT_SESSION}):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                camera_source_ids(cameras, json.dumps(raw))


if __name__ == '__main__':
    unittest.main()
