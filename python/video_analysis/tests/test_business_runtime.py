from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest
import uuid
from unittest.mock import Mock, patch

from video_analysis.business_client import BusinessRequestError, BusinessUnavailable
from video_analysis.business_runtime import BusinessRuntime, create_delivery


SOURCE = '10000000-0000-4000-8000-000000000001'
STREAM = '20000000-0000-4000-8000-000000000001'
SESSION = '30000000-0000-4000-8000-000000000001'
INSTANCE = '40000000-0000-4000-8000-000000000001'
START = datetime(2026, 10, 26, 2, tzinfo=timezone.utc)


def frame(sequence=1, session=SESSION, algorithm='botsort'):
    return {
        'source_id': SOURCE, 'stream_session_id': session, 'algorithm': algorithm,
        'tracking_context_id': str(uuid.uuid4()),
        'stream_session': {'stream_session_id': session, 'started_at': START.isoformat(),
                           'time_origin_at': START.isoformat(), 'time_basis': 'ingest_clock',
                           'source_timezone': 'UTC', 'source_width': 1920, 'source_height': 1080},
        'result': {'result_id': str(uuid.uuid4()), 'frame_id': str(uuid.uuid4()),
                   'frame_seq': sequence, 'targets': [],
                   'occurred_at': (START + timedelta(milliseconds=sequence * 40)).isoformat()},
    }


class BusinessRuntimeTests(unittest.TestCase):
    def test_delivery_creation_validates_configuration_without_storage_io(self):
        configuration = {
            'api_url': 'http://fixture.invalid/api/v1/business', 'service_id': 'fixture',
            'token_env': 'HXJM_FIXTURE_TOKEN', 'timeout_seconds': 1,
            'source_streams': {SOURCE: STREAM}, 'instances': {(SOURCE, 'botsort'): {
                'instance_id': INSTANCE, 'capability_code': 'tracking'}},
            'spool_dir': '/data/nfs_storage/fixture-result-spool',
            'batch_size': 1, 'queue_size': 2, 'flush_interval_seconds': 0.01,
        }
        with patch('video_analysis.result_spool.ResultSpool._prepare',
                   side_effect=AssertionError('startup must not access runtime storage')) as prepare:
            delivery = create_delivery(configuration)
            self.assertEqual(delivery.status()['state'], 'idle')
            prepare.assert_not_called()
            configuration['queue_size'] = 0
            with self.assertRaises(ValueError):
                create_delivery(configuration)

    def runtime(self, **options):
        client = Mock()
        client.open_session.side_effect = lambda request: {
            'source_id': request['source_id'], 'stream_session_id': request['stream_session_id']}
        client.create_task.side_effect = lambda request: {
            'task_id': str(uuid.uuid4()), 'run_id': None, 'state': 'pending', 'revision': 1}
        client.start_task.side_effect = lambda request: {
            'task_id': request['task_id'], 'run_id': str(uuid.uuid4()), 'state': 'running', 'revision': 2}
        runtime = BusinessRuntime(client, source_streams=options.pop('source_streams', {SOURCE: STREAM}),
                                  instances=options.pop('instances', {(SOURCE, 'botsort'): {
                                      'instance_id': INSTANCE, 'capability_code': 'tracking'}}), **options)
        return runtime, client

    def test_opens_real_input_and_starts_configured_instance_once(self):
        runtime, client = self.runtime()
        first = frame()
        original = deepcopy(first)
        unit = runtime.execution_for([first])
        second = frame(5)
        again = runtime.execution_for([second])
        self.assertEqual(again, unit)
        self.assertEqual(first, original)
        self.assertEqual(client.open_session.call_count, 1)
        self.assertEqual(client.create_task.call_count, 1)
        self.assertEqual(client.start_task.call_count, 1)
        opened = client.open_session.call_args.args[0]
        self.assertEqual(opened['stream_session_id'], SESSION)
        self.assertEqual(opened['camera_stream_id'], STREAM)
        self.assertEqual(opened['started_at'], START.isoformat())
        self.assertEqual(opened['source_timezone'], 'UTC')
        task = client.create_task.call_args.args[0]
        self.assertEqual(task['input'], {'kind': 'live_video', 'source_id': SOURCE,
                                        'stream_session_id': SESSION})
        self.assertEqual(task['instance_id'], INSTANCE)
        self.assertEqual(task['requested_outputs'], ['detection.frame'])
        claimed = client.start_task.call_args.args[0]
        self.assertEqual(claimed['instance_id'], INSTANCE)
        self.assertEqual(claimed['expected_revision'], 1)
        self.assertEqual(unit['task_id'], claimed['task_id'])
        self.assertNotEqual(unit['run_id'], unit['result_set_id'])
        self.assertEqual(uuid.UUID(unit['result_set_id']).version, 4)
        unit['task_id'] = 'mutated'
        self.assertEqual(runtime.execution_for([second]), again)

    def test_input_reconnect_creates_a_new_unit_while_tracker_reset_does_not(self):
        runtime, client = self.runtime()
        original = runtime.execution_for([frame()])
        self.assertEqual(runtime.execution_for([frame(2)]), original)
        reconnect = runtime.execution_for([frame(1, session=str(uuid.uuid4()))])
        for name in ('task_id', 'run_id', 'result_set_id', 'set_key'):
            self.assertNotEqual(reconnect[name], original[name])
        self.assertEqual(client.open_session.call_count, 2)

    def test_recording_opens_input_without_an_inference_and_analysis_reuses_it(self):
        runtime, client = self.runtime()
        first = frame()
        self.assertEqual(runtime.open_input(SOURCE, first['stream_session']), SESSION)
        client.create_task.assert_not_called()
        client.start_task.assert_not_called()
        runtime.execution_for([first])
        self.assertEqual(client.open_session.call_count, 1)
        with self.assertRaises(ValueError):
            runtime.open_input(str(uuid.uuid4()), first['stream_session'])

    def test_session_open_is_stable_across_restart_and_utc_spellings(self):
        runtime, client = self.runtime()
        first = frame()
        recorder_metadata = deepcopy(first['stream_session'])
        for name in ('started_at', 'time_origin_at'):
            recorder_metadata[name] = recorder_metadata[name].replace('+00:00', '.000Z')
        runtime.open_input(SOURCE, recorder_metadata)
        runtime.execution_for([first])
        original = client.open_session.call_args.args[0]
        restarted, reopened = self.runtime()
        restarted.open_input(SOURCE, first['stream_session'])
        self.assertEqual(reopened.open_session.call_args.args[0], original)
        self.assertEqual(client.open_session.call_count, 1)

    def test_algorithms_share_the_input_session_and_keep_separate_tasks(self):
        runtime, client = self.runtime(instances={
            (SOURCE, 'botsort'): {'instance_id': INSTANCE, 'capability_code': 'tracking'},
            (SOURCE, 'deepsort'): {'instance_id': str(uuid.uuid4()), 'capability_code': 'detection'},
        })
        tracked = runtime.execution_for([frame()])
        detected = runtime.execution_for([frame(algorithm='deepsort')])
        self.assertNotEqual(tracked['task_id'], detected['task_id'])
        self.assertEqual(client.open_session.call_count, 1)

    def test_transient_request_failures_keep_original_request_ids_and_bodies(self):
        for method in ('open_session', 'create_task', 'start_task'):
            with self.subTest(method=method):
                runtime, client = self.runtime()
                target = getattr(client, method)
                normal = target.side_effect
                calls = []
                def send(request):
                    calls.append(deepcopy(request))
                    if len(calls) == 1:
                        raise BusinessUnavailable()
                    return normal(request)
                target.side_effect = send
                sample = frame()
                with self.assertRaises(BusinessUnavailable):
                    runtime.execution_for([sample])
                self.assertTrue(runtime.execution_for([sample])['run_id'])
                self.assertEqual(calls[0], calls[1])

    def test_missing_or_changed_session_is_rejected_without_guessing(self):
        for mutation in ('missing', 'wrong_id', 'late_start', 'bad_time', 'bad_dimensions'):
            runtime, client = self.runtime()
            sample = frame()
            if mutation == 'missing':
                sample.pop('stream_session')
            elif mutation == 'wrong_id':
                sample['stream_session']['stream_session_id'] = str(uuid.uuid4())
            elif mutation == 'late_start':
                sample['stream_session']['started_at'] = (START + timedelta(hours=1)).isoformat()
            elif mutation == 'bad_time':
                sample['stream_session']['started_at'] = '2026-10-26T02:00:00'
            else:
                sample['stream_session']['source_width'] = 0
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                runtime.execution_for([sample])
            client.open_session.assert_not_called()
        runtime, client = self.runtime()
        runtime.execution_for([frame()])
        changed = frame(2)
        changed['stream_session']['source_width'] = 1280
        with self.assertRaises(ValueError):
            runtime.execution_for([changed])
        self.assertEqual(client.open_session.call_count, 1)

    def test_no_instance_or_mismatched_server_identity_is_accepted(self):
        runtime, client = self.runtime()
        with self.assertRaises(ValueError):
            runtime.execution_for([frame(algorithm='unconfigured')])
        client.open_session.return_value = {'source_id': SOURCE, 'stream_session_id': str(uuid.uuid4())}
        client.open_session.side_effect = None
        with self.assertRaises(BusinessRequestError):
            runtime.execution_for([frame()])
        client.create_task.assert_not_called()

    def test_window_describes_only_the_processed_batch_including_last_instant(self):
        first, last = frame(1), frame(5)
        window = BusinessRuntime.window_for([last, first])
        self.assertFalse(window['closed'])
        self.assertEqual(window['gaps'], [])
        self.assertEqual(datetime.fromisoformat(window['start_at']),
                         datetime.fromisoformat(first['result']['occurred_at']))
        self.assertEqual(datetime.fromisoformat(window['end_at']),
                         datetime.fromisoformat(last['result']['occurred_at']) + timedelta(microseconds=1))

    def test_explicit_close_preserves_original_results_and_manifest_with_stable_new_request(self):
        first, last = frame(1), frame(4)
        payload = {'request_id': str(uuid.uuid4()), 'results': [first['result'], last['result']],
                   'analysis_coverage': dict(BusinessRuntime.window_for([first, last]),
                                            frame_ids=[first['result']['frame_id'], last['result']['frame_id']],
                                            analyzed_frame_count=2)}
        original = deepcopy(payload)
        closed = BusinessRuntime.close_request(payload)
        self.assertEqual(payload, original)
        self.assertTrue(closed['analysis_coverage']['closed'])
        self.assertNotEqual(closed['request_id'], payload['request_id'])
        self.assertEqual(closed['results'], payload['results'])
        self.assertEqual(BusinessRuntime.close_request(payload), closed)
        subset = deepcopy(payload)
        subset['results'] = subset['results'][1:]
        self.assertEqual(BusinessRuntime.close_request(subset)['analysis_coverage']['frame_ids'],
                         payload['analysis_coverage']['frame_ids'])
        subset['analysis_coverage']['gaps'] = [{'reason_code': 'UNSAVED'}]
        with self.assertRaises(ValueError):
            BusinessRuntime.close_request(subset)


if __name__ == '__main__':
    unittest.main()
