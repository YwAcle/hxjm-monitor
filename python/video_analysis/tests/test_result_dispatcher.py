from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest
import uuid
import weakref
from unittest.mock import patch

from video_analysis.frame_result import registration_request
from video_analysis.result_delivery import OPERATION, ResultDispatcher
from video_analysis.result_spool import ResultSpool


PROJECT = Path(__file__).resolve().parents[3]
SOURCE = '10000000-0000-4000-8000-000000000001'
INPUT = '20000000-0000-4000-8000-000000000001'
CONTEXT = '30000000-0000-4000-8000-000000000001'
START = datetime(2026, 10, 26, 2, 0, tzinfo=timezone.utc)


def unit():
    return {'task_id': str(uuid.uuid4()), 'run_id': str(uuid.uuid4()),
            'result_set_id': str(uuid.uuid4()), 'set_key': 'tracking:test',
            'capability_code': 'tracking'}


def frame(sequence=1, source=SOURCE, context=CONTEXT):
    occurred = START + timedelta(milliseconds=40 * sequence)
    return {
        'source_id': source, 'stream_session_id': INPUT, 'tracking_context_id': context,
        'algorithm': 'botsort', 'processed_at': (occurred + timedelta(milliseconds=10)).isoformat(),
        'tracking_context': {'context_key': 'tracker:' + context,
                             'started_at': START.isoformat(), 'reset_reason': None},
        'result': {'result_id': str(uuid.uuid4()), 'frame_id': str(uuid.uuid4()),
                   'producer_result_key': 'frame:' + str(uuid.uuid4()), 'frame_seq': sequence,
                   'occurred_at': occurred.isoformat(), 'targets': []},
    }


def window(frames):
    return {'start_at': START.isoformat(),
            'end_at': (START + timedelta(minutes=1)).isoformat()}


def accepted(payload):
    return {'accepted_result_ids': [result['result_id'] for result in payload['results']],
            'duplicate_result_ids': [], 'rejected_results': []}


def until(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError('Timed out waiting for dispatcher')
        time.sleep(0.005)


class ResultDispatcherTests(unittest.TestCase):
    def setUp(self):
        self.parent = PROJECT / '.run' / 'test-result-dispatcher'
        self.parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=self.parent)
        self.spool = ResultSpool(Path(self.temporary.name) / 'spool')
        self.execution = unit()
        self.dispatchers = []

    def tearDown(self):
        for dispatcher in self.dispatchers:
            self.assertTrue(dispatcher.stop(timeout=2))
        self.temporary.cleanup()
        for directory in (self.parent, self.parent.parent):
            try:
                directory.rmdir()
            except OSError:
                pass

    def dispatcher(self, submit, **options):
        dispatcher = ResultDispatcher(
            self.spool, actor_key='service:test',
            units=options.pop('units', {(SOURCE, 'botsort'): self.execution}),
            window_for=options.pop('window_for', window), submit=submit,
            flush_interval=options.pop('flush_interval', 0.02), **options)
        self.dispatchers.append(dispatcher)
        return dispatcher

    def test_multiple_frames_are_written_and_submitted_outside_caller_thread(self):
        calls = []
        sender_thread = []
        def submit(actor, operation, payload):
            calls.append((actor, operation, deepcopy(payload)))
            sender_thread.append(threading.get_ident())
            return accepted(payload)
        dispatcher = self.dispatcher(submit, batch_size=2)
        dispatcher.start()
        first, last = frame(1), frame(4)
        dispatcher(first)
        dispatcher(last)
        first['result']['targets'].append({'mutated': True})
        until(lambda: dispatcher.status()['confirmed_batches'] == 1)
        payload = calls[0][2]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:2], ('service:test', OPERATION))
        self.assertNotEqual(sender_thread[0], threading.get_ident())
        self.assertEqual([result['frame_seq'] for result in payload['results']], [1, 4])
        self.assertEqual(payload['results'][0]['targets'], [])
        self.assertEqual(payload['analysis_coverage']['analyzed_frame_count'], 2)
        self.assertFalse(payload['analysis_coverage']['closed'])
        self.assertEqual(payload['tracking_context'], last['tracking_context'])
        self.assertEqual(self.spool.pending(), [])

    def test_blocked_sender_does_not_block_handoff_and_queue_full_is_explicit(self):
        sending = threading.Event()
        release = threading.Event()
        def submit(actor, operation, payload):
            sending.set()
            if not release.wait(2):
                raise OSError('test sender timeout')
            return accepted(payload)
        dispatcher = self.dispatcher(submit, batch_size=1, queue_size=1)
        dispatcher.start()
        try:
            dispatcher(frame(1))
            self.assertTrue(sending.wait(1))
            dispatcher(frame(2))
            with self.assertRaises(queue.Full):
                dispatcher(frame(3))
            self.assertEqual(dispatcher.status()['rejected_handoffs'], 1)
            self.assertEqual(dispatcher.status()['enqueued_frames'], 2)
        finally:
            release.set()
        until(lambda: dispatcher.status()['confirmed_batches'] == 2)

    def test_restart_replays_original_payload_before_accepting_new_batches(self):
        old = frame()
        execution = dict(self.execution, tracking_context=old['tracking_context'])
        coverage = dict(window([old]), frame_ids=[old['result']['frame_id']],
                        analyzed_frame_count=1, closed=False, gaps=[])
        payload = registration_request([old], execution, coverage, request_id='original-request')
        key = self.spool.put('service:test', OPERATION, payload)
        calls = []
        def submit(actor, operation, request):
            calls.append(deepcopy(request))
            return accepted(request)
        dispatcher = self.dispatcher(submit, batch_size=1)
        dispatcher.start()
        dispatcher(frame(2))
        until(lambda: dispatcher.status()['confirmed_batches'] == 2)
        self.assertEqual(calls[0], payload)
        self.assertNotIn(key, self.spool.pending())

    def test_partial_confirmation_uses_new_request_but_original_results_and_manifest(self):
        calls = []
        def submit(actor, operation, payload):
            calls.append(deepcopy(payload))
            if len(calls) == 1:
                return {'accepted_result_ids': [payload['results'][0]['result_id']],
                        'duplicate_result_ids': [], 'rejected_results': [
                            {'result_id': payload['results'][1]['result_id'], 'retryable': True}]}
            return accepted(payload)
        dispatcher = self.dispatcher(submit, batch_size=2)
        dispatcher.start()
        dispatcher(frame(1))
        dispatcher(frame(2))
        until(lambda: dispatcher.status()['confirmed_batches'] == 1)
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(calls[0]['request_id'], calls[1]['request_id'])
        self.assertEqual(calls[1]['results'], calls[0]['results'][1:])
        self.assertEqual(calls[0]['analysis_coverage'], calls[1]['analysis_coverage'])
        self.assertEqual(dispatcher.status()['partial_batches'], 1)
        self.assertEqual(self.spool.pending(), [])

    def test_async_submit_reads_credentials_when_sending_without_spooling_them(self):
        token = {'value': 'current-secret'}
        used = []
        async def submit(actor, operation, payload):
            used.append(token['value'])
            record = self.spool.read(self.spool.pending()[0])
            self.assertNotIn('current-secret', json.dumps(record))
            return accepted(payload)
        dispatcher = self.dispatcher(submit, batch_size=1)
        dispatcher.start()
        dispatcher(frame())
        until(lambda: dispatcher.status()['confirmed_batches'] == 1)
        self.assertEqual(used, ['current-secret'])

    def test_network_retry_preserves_request_and_recovers_status(self):
        requests = []
        def submit(actor, operation, payload):
            requests.append(deepcopy(payload))
            if len(requests) == 1:
                raise OSError('test temporary disconnect')
            return accepted(payload)
        dispatcher = self.dispatcher(submit, batch_size=1)
        with self.assertLogs('video_analysis.result_delivery', level='ERROR'):
            dispatcher.start()
            dispatcher(frame())
            until(lambda: dispatcher.status()['confirmed_batches'] == 1)
        self.assertEqual(requests[0], requests[1])
        self.assertEqual(dispatcher.status()['state'], 'running')
        self.assertIsNone(dispatcher.status()['last_error'])

    def test_nonretryable_result_stays_on_disk_without_busy_resubmission(self):
        calls = []
        def submit(actor, operation, payload):
            calls.append(payload)
            return {'accepted_result_ids': [], 'duplicate_result_ids': [],
                    'rejected_results': [{'result_id': payload['results'][0]['result_id'],
                                          'retryable': False}]}
        dispatcher = self.dispatcher(submit, batch_size=1)
        with self.assertLogs('video_analysis.result_delivery', level='ERROR'):
            dispatcher.start()
            dispatcher(frame())
            until(lambda: dispatcher.status()['blocked_batches'] == 1)
        time.sleep(0.05)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(self.spool.pending()), 1)
        self.assertEqual(dispatcher.status()['state'], 'retrying')

    def test_missing_execution_and_context_are_rejected_without_fake_references(self):
        dispatcher = self.dispatcher(lambda *args: None)
        dispatcher.start()
        with self.assertRaises(ValueError):
            dispatcher(frame(source=str(uuid.uuid4())))
        missing = frame()
        del missing['tracking_context']
        with self.assertLogs('video_analysis.result_delivery', level='ERROR'):
            dispatcher(missing)
            until(lambda: dispatcher.status()['state'] == 'failed')
        self.assertEqual(dispatcher.status()['inflight_frames'], 1)
        self.assertEqual(self.spool.pending(), [])
        with self.assertRaises(RuntimeError):
            dispatcher(frame(2))

    def test_disk_failure_is_visible_and_does_not_count_a_persisted_frame(self):
        dispatcher = self.dispatcher(lambda *args: None, batch_size=1)
        with patch.object(self.spool, 'put', side_effect=OSError('test write failure')), \
                self.assertLogs('video_analysis.result_delivery', level='ERROR'):
            dispatcher.start()
            dispatcher(frame())
            until(lambda: dispatcher.status()['state'] == 'retrying')
            self.assertFalse(dispatcher.stop(timeout=0.03))
            self.assertEqual(dispatcher.status()['state'], 'retrying')
            self.assertEqual(dispatcher.status()['persisted_frames'], 0)
            self.assertEqual(dispatcher.status()['inflight_frames'], 1)
        until(lambda: dispatcher.status()['persisted_frames'] == 1)
        self.assertTrue(dispatcher.stop(timeout=2))
        self.assertEqual(dispatcher.status()['state'], 'stopped')
        self.assertEqual(dispatcher.status()['inflight_frames'], 0)
        self.assertEqual(len(self.spool.pending()), 1)

    def test_slow_storage_never_blocks_start_handoff_or_status(self):
        entered = threading.Event()
        release = threading.Event()
        original = self.spool.pending
        def pending():
            entered.set()
            if not release.wait(2):
                raise OSError('test storage timeout')
            return original()
        dispatcher = self.dispatcher(lambda actor, operation, payload: accepted(payload), batch_size=1)
        factory_calls = []
        sample = frame()
        def factory():
            factory_calls.append(threading.get_ident())
            return sample
        with patch.object(self.spool, 'pending', side_effect=pending):
            before = time.monotonic()
            dispatcher.start()
            self.assertLess(time.monotonic() - before, 0.1)
            try:
                self.assertTrue(entered.wait(1))
                before = time.monotonic()
                dispatcher.defer(factory)
                self.assertEqual(dispatcher.status()['queued_frames'], 1)
                self.assertLess(time.monotonic() - before, 0.1)
                self.assertEqual(factory_calls, [])
            finally:
                release.set()
            until(lambda: dispatcher.status()['confirmed_batches'] == 1)
        self.assertEqual(len(factory_calls), 1)
        self.assertNotEqual(factory_calls[0], threading.get_ident())

    def test_unavailable_initial_storage_is_retryable_and_recovers(self):
        ready = threading.Event()
        original = self.spool.pending
        def pending():
            if not ready.is_set():
                raise PermissionError('test NFS not ready')
            return original()
        dispatcher = self.dispatcher(lambda actor, operation, payload: accepted(payload), batch_size=1)
        with patch.object(self.spool, 'pending', side_effect=pending), \
                self.assertLogs('video_analysis.result_delivery', level='ERROR'):
            dispatcher.start()
            until(lambda: dispatcher.status()['state'] == 'retrying')
            dispatcher(frame())
            self.assertEqual(dispatcher.status()['queued_frames'], 1)
            self.assertTrue(dispatcher.status()['thread_alive'])
            self.assertEqual(dispatcher.status()['persisted_frames'], 0)
            ready.set()
            until(lambda: dispatcher.status()['confirmed_batches'] == 1)
        self.assertEqual(dispatcher.status()['state'], 'running')
        self.assertIsNone(dispatcher.status()['last_error'])
        self.assertEqual(self.spool.pending(), [])

    def test_write_retry_keeps_one_factory_result_and_one_logical_request(self):
        original = self.spool.put
        attempts = []
        factory_calls = []
        sample = frame()
        def factory():
            factory_calls.append(True)
            return deepcopy(sample)
        def put(actor, operation, payload):
            attempts.append(deepcopy(payload))
            result = original(actor, operation, payload)
            if len(attempts) == 1:
                raise OSError('test write completed but directory sync unconfirmed')
            return result
        dispatcher = self.dispatcher(lambda actor, operation, payload: accepted(payload), batch_size=1)
        with patch.object(self.spool, 'put', side_effect=put), \
                self.assertLogs('video_analysis.result_delivery', level='ERROR'):
            dispatcher.start()
            dispatcher.defer(factory)
            until(lambda: dispatcher.status()['confirmed_batches'] == 1)
        self.assertEqual(factory_calls, [True])
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0], attempts[1])
        self.assertEqual(dispatcher.status()['persisted_frames'], 1)
        self.assertEqual(self.spool.pending(), [])

    def test_invalid_factory_is_not_saved_and_does_not_block_valid_frames(self):
        calls = []
        def submit(actor, operation, payload):
            calls.append(deepcopy(payload))
            return accepted(payload)
        dispatcher = self.dispatcher(submit, batch_size=4)
        failures = []
        references = []
        with self.assertLogs('video_analysis.result_delivery', level='ERROR'):
            dispatcher.start()
            for kind in (ValueError, KeyError, TypeError):
                def invalid(kind=kind):
                    failures.append(kind)
                    raise kind('test invalid frame')
                references.append(weakref.ref(invalid))
                dispatcher.defer(invalid)
            del invalid
            good = frame()
            dispatcher.defer(lambda: good)
            until(lambda: dispatcher.status()['confirmed_batches'] == 1)
        state = dispatcher.status()
        self.assertEqual(state['invalid_frames'], 3)
        self.assertIn('TypeError', state['last_invalid_error'])
        self.assertEqual(state['persisted_frames'], 1)
        self.assertEqual(state['inflight_frames'], 0)
        self.assertEqual(state['state'], 'running')
        self.assertTrue(state['thread_alive'])
        self.assertEqual(failures, [ValueError, KeyError, TypeError])
        self.assertTrue(all(reference() is None for reference in references))
        self.assertEqual(calls[0]['results'], [good['result']])
        dispatcher(frame(2))
        until(lambda: dispatcher.status()['confirmed_batches'] == 2)
        self.assertEqual(dispatcher.status()['persisted_frames'], 2)
        self.assertEqual(self.spool.pending(), [])

    def test_execution_resolver_retries_the_same_input_batch(self):
        calls = []
        def resolve(group):
            calls.append(deepcopy(group))
            if len(calls) == 1:
                raise OSError('test temporary task service failure')
            return self.execution
        dispatcher = self.dispatcher(lambda actor, op, payload: accepted(payload),
                                     units=resolve, batch_size=1)
        with self.assertLogs('video_analysis.result_delivery', level='ERROR'):
            dispatcher.start()
            dispatcher(frame())
            until(lambda: dispatcher.status()['confirmed_batches'] == 1)
        self.assertEqual(calls[0], calls[1])
        self.assertEqual(dispatcher.status()['persisted_frames'], 1)
        self.assertEqual(dispatcher.status()['inflight_frames'], 0)

    def test_confirmed_batch_is_durably_closed_and_close_is_not_recursive(self):
        from video_analysis.business_runtime import BusinessRuntime
        calls = []
        def submit(actor, operation, payload):
            calls.append(deepcopy(payload))
            return accepted(payload)
        dispatcher = self.dispatcher(submit, batch_size=1,
                                     close_for=BusinessRuntime.close_request)
        dispatcher.start()
        dispatcher(frame())
        until(lambda: dispatcher.status()['confirmed_batches'] == 2)
        self.assertEqual(len(calls), 2)
        self.assertFalse(calls[0]['analysis_coverage']['closed'])
        self.assertTrue(calls[1]['analysis_coverage']['closed'])
        self.assertEqual(calls[0]['results'], calls[1]['results'])
        self.assertNotEqual(calls[0]['request_id'], calls[1]['request_id'])
        self.assertEqual(self.spool.pending(), [])

    def test_sources_and_context_resets_are_separate_batches(self):
        other_source, other_context = str(uuid.uuid4()), str(uuid.uuid4())
        calls = []
        def submit(actor, operation, payload):
            calls.append(deepcopy(payload))
            return accepted(payload)
        dispatcher = self.dispatcher(submit, batch_size=3, units={
            (SOURCE, 'botsort'): self.execution, (other_source, 'botsort'): unit()})
        dispatcher.start()
        dispatcher(frame())
        dispatcher(frame(2, context=other_context))
        dispatcher(frame(3, source=other_source))
        until(lambda: dispatcher.status()['confirmed_batches'] == 3)
        self.assertEqual(len(calls), 3)
        self.assertEqual({payload['source_id'] for payload in calls}, {SOURCE, other_source})
        self.assertEqual({payload['tracking_context_id'] for payload in calls}, {CONTEXT, other_context})
        self.assertTrue(all(len(payload['results']) == 1 for payload in calls))

    def test_stop_flushes_queued_frames_and_refuses_further_handoffs(self):
        dispatcher = self.dispatcher(lambda actor, operation, payload: accepted(payload),
                                     batch_size=8, flush_interval=0.1)
        with self.assertRaises(RuntimeError):
            dispatcher(frame())
        dispatcher.start()
        dispatcher(frame(1))
        dispatcher(frame(2))
        self.assertTrue(dispatcher.stop(timeout=2))
        self.assertEqual(dispatcher.status()['persisted_frames'], 2)
        self.assertEqual(dispatcher.status()['queued_frames'], 0)
        self.assertEqual(dispatcher.status()['inflight_frames'], 0)
        self.assertEqual(dispatcher.status()['state'], 'stopped')
        with self.assertRaises(RuntimeError):
            dispatcher(frame(3))
        with self.assertRaises(RuntimeError):
            dispatcher.start()


if __name__ == '__main__':
    unittest.main()
