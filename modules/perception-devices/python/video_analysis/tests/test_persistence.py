"""Offline tests: temporary files and fake HTTP only; no app, DB, GPU or cameras."""
import asyncio
from copy import deepcopy
import io
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from video_analysis.tracking_client import BusinessClient, BusinessError
from video_analysis.persistence_config import PersistenceConfig
from video_analysis.tracking_spool import ResultSpool, SpoolFull
from video_analysis.result_publisher import ResultPublisher
from video_analysis.tracking_state import new_id, frame_fact


def capture(sequence=1, age_ms=0, epoch=1):
    now = time.time_ns() // 1_000_000 - age_ms
    return SimpleNamespace(frame_id=sequence, stream_epoch=epoch, frame_ts_ms=now,
                           decode_ts_ms=now, source_width=1920, source_height=1080,
                           media_pts_ms=sequence * 40, timestamp_kind='decode_wall_clock')


def detection(local=7, predicted=False):
    return dict(label='person', track_id=local, bbox=[.1, .2, .4, .8],
                confidence=None if predicted else .9, is_prediction=predicted)


class FakeBusiness:
    def __init__(self):
        self.calls, self.requests, self.frames = [], {}, set()
        self.lost_response = False
        self.partial = False

    def call(self, path, body=None):
        self.calls.append((path, deepcopy(body)))
        key = (path, body.get('request_id')) if body else (path, None)
        if key in self.requests:
            previous, result = self.requests[key]
            if previous != body:
                raise BusinessError('CONFLICT')
            return deepcopy(result)
        if path.startswith('/instances?'):
            return dict(items=[dict(implementation_code='botsort', implementation_version='test-v1')])
        if path == '/tasks':
            result = dict(task_id=new_id(), revision=1)
        elif path == '/tasks/start':
            result = dict(task_id=body['task_id'], run_id=new_id(), revision=2)
        elif path == '/streams/open':
            result = dict(source_id=body['source_id'], stream_session_id=body['stream_session_id'], state='open')
        elif path == '/streams/close':
            result = dict(stream_session_id=body['stream_session_id'], state=body['state'])
        elif path == '/tracking/close':
            result = dict(tracking_context_id=body['tracking_context_id'], context_closed=body['close_context'])
        elif path == '/results/register':
            accepted, duplicate, rejected = [], [], []
            for index, fact in enumerate(body['results']):
                ident = fact['result_id']
                if self.partial and index == len(body['results']) - 1:
                    rejected.append(dict(result_id=ident, code='DEPENDENCY_UNAVAILABLE', retryable=True))
                elif ident in self.frames:
                    duplicate.append(ident)
                else:
                    self.frames.add(ident)
                    accepted.append(ident)
            self.partial = False
            result = dict(accepted_result_ids=accepted, duplicate_result_ids=duplicate,
                          rejected_results=rejected, tracklets=[], coverage={})
        else:
            result = dict(ok=True)
        self.requests[key] = (deepcopy(body), deepcopy(result))
        if path == '/results/register' and self.lost_response:
            self.lost_response = False
            raise BusinessError('TRANSPORT_UNAVAILABLE', True)
        return deepcopy(result)


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.api = FakeBusiness()
        self.config = SimpleNamespace(spool_dir=str(self.root / 'spool'), max_bytes=16 * 1024 ** 2,
            service_id='fixture', sources={'camera_1': dict(source_id=new_id(), camera_stream_id=new_id(), instance_id=new_id()),
                                          'camera_2': dict(source_id=new_id(), camera_stream_id=new_id(), instance_id=new_id())},
            implementation_code='botsort', implementation_version='test-v1', capability_code='tracking',
            batch_frames=10, batch_bytes=512 * 1024, flush_seconds=.001, retry_max=.01)
        self.publisher = ResultPublisher(self.config, client=self.api)
        self.addCleanup(lambda: self.publisher.spool.close())

    def frame(self, sequence=1, local=7, predicted=False, session='component-a', epoch=1, camera='camera_1'):
        frame = capture(sequence, epoch=epoch)
        context = self.publisher._begin_frame(camera, frame, 'service-a', session)
        self.publisher._record(context, frame, [detection(local, predicted)], frame.frame_ts_ms + 10, [])
        return context

    def drain(self, camera='camera_1'):
        while entries := self.publisher.spool.lane_entries(camera):
            self.publisher._process(entries)

    def test_batch_keeps_one_context_and_original_frame_numbers(self):
        context = self.frame(1)
        self.assertEqual(context, self.frame(20))
        self.drain()
        requests = [b for p, b in self.api.calls if p == '/results/register']
        self.assertEqual(len(requests), 1)
        self.assertEqual([f['frame_seq'] for f in requests[0]['results']], [1, 20])
        self.assertEqual(len(self.api.frames), 2)
        self.assertEqual(requests[0]['analysis_coverage']['analyzed_frame_count'], 2)

    def test_lost_ack_retries_exact_frozen_request(self):
        self.frame()
        self.publisher._process(self.publisher.spool.lane_entries('camera_1'))
        self.api.lost_response = True
        with self.assertRaises(BusinessError):
            self.publisher._process(self.publisher.spool.lane_entries('camera_1'))
        self.drain()
        requests = [b for p, b in self.api.calls if p == '/results/register']
        self.assertEqual(requests[0], requests[1])
        self.assertEqual(len(self.api.frames), 1)

    def test_partial_ack_only_resubmits_failed_subset(self):
        self.frame(1)
        self.frame(2)
        self.publisher._process(self.publisher.spool.lane_entries('camera_1'))
        self.api.partial = True
        with self.assertRaises(BusinessError):
            self.publisher._process(self.publisher.spool.lane_entries('camera_1'))
        self.drain()
        requests = [b for p, b in self.api.calls if p == '/results/register']
        self.assertNotEqual(requests[0]['request_id'], requests[1]['request_id'])
        self.assertEqual(requests[1]['results'], [requests[0]['results'][1]])
        self.assertEqual(requests[0]['analysis_coverage'], requests[1]['analysis_coverage'])
        self.assertEqual(len(self.api.frames), 2)

    def test_recovery_drains_old_context_before_closing_input(self):
        context = self.frame()
        self.publisher.spool.close()
        self.publisher = ResultPublisher(self.config, client=self.api)
        self.publisher._recover()
        self.drain()
        paths = [p for p, _ in self.api.calls]
        self.assertLess(paths.index('/results/register'), paths.index('/tracking/close'))
        self.assertLess(paths.index('/tracking/close'), paths.index('/streams/close'))
        self.assertEqual(self.publisher.spool.all_states(), [])
        self.assertEqual([b for p,b in self.api.calls if p == '/tracking/close'][0]['tracking_context_id'], context)

    def test_recovery_preserves_original_close_request(self):
        context = self.frame()
        self.publisher._interrupt('camera_1', 'manual-stop', True)
        original = self.publisher.spool.load_state(context)['close_payload']
        self.publisher.spool.close()
        self.publisher = ResultPublisher(self.config, client=self.api)
        self.publisher._recover()
        self.drain()
        result = [b for p,b in self.api.calls if p == '/tracking/close'][0]
        self.assertEqual(result['reason_code'], original['reason_code'])
        self.assertEqual(result['ended_at'], original['ended_at'])

    def test_tracker_restart_retains_public_input(self):
        first = self.frame(1)
        second = self.frame(2, session='component-b')
        a, b = [self.publisher.spool.load_state(c) for c in (first, second)]
        self.assertNotEqual(first, second)
        self.assertEqual(a['input_id'], b['input_id'])
        self.drain()
        self.assertEqual(len([p for p,b in self.api.calls if p == '/streams/open']), 1)

    def test_input_reconnect_creates_new_session(self):
        first = self.frame(1)
        second = self.frame(2, epoch=2)
        self.assertNotEqual(self.publisher.spool.load_state(first)['input_id'], self.publisher.spool.load_state(second)['input_id'])
        self.drain()
        self.assertEqual(len([p for p,b in self.api.calls if p == '/streams/open']), 2)

    def test_real_and_prediction_and_empty_frame_remain_distinct(self):
        context = self.frame(1)
        self.frame(2, predicted=True)
        frame = capture(3)
        self.publisher._record(context, frame, [], frame.frame_ts_ms, [])
        self.drain()
        frames = [b for p,b in self.api.calls if p == '/results/register'][0]['results']
        self.assertFalse(frames[0]['targets'][0]['is_prediction'])
        self.assertTrue(frames[1]['targets'][0]['is_prediction'])
        self.assertIsNone(frames[1]['targets'][0]['confidence'])
        self.assertEqual(frames[2]['targets'], [])

    def test_predictions_do_not_advance_local_true_observation(self):
        context = self.frame(1)
        old = self.publisher.spool.load_state(context)['tracks']['7']
        self.frame(2, predicted=True)
        self.assertEqual(self.publisher.spool.load_state(context)['tracks']['7'], old)

    def test_removed_track_event_follows_its_frame(self):
        context = self.frame()
        frame = capture(2)
        self.publisher._record(context, frame, [], frame.frame_ts_ms, [7])
        self.drain()
        paths = [p for p,b in self.api.calls]
        self.assertGreater(paths.index('/tracking/close'), paths.index('/results/register'))
        body = [b for p,b in self.api.calls if p == '/tracking/close'][0]
        self.assertFalse(body['close_context'])
        self.assertEqual(body['local_track_ids'], [7])

    def test_only_lane_with_unconfirmed_facts_is_blocked(self):
        self.frame(camera='camera_1')
        self.frame(camera='camera_2')
        self.drain('camera_2')
        self.assertEqual(len(self.api.frames), 1)
        self.assertTrue(self.publisher.spool.lane_entries('camera_1'))

    def test_saved_facts_can_outlive_display_expiry(self):
        frame = capture(age_ms=60000)
        context = self.publisher._begin_frame('camera_1', frame, 'service-a', 'component-a')
        self.publisher._record(context, frame, [detection()], frame.frame_ts_ms + 60000, [])
        self.drain()
        self.assertEqual(len(self.api.frames), 1)

    def test_restart_reuses_batch_after_partial_cleanup(self):
        self.frame(1)
        self.frame(2)
        self.publisher._process(self.publisher.spool.lane_entries('camera_1'))
        original_remove = self.publisher.spool.remove
        calls = []
        def crash(path):
            calls.append(path)
            if len(calls) == 2:
                raise OSError('simulated process death')
            original_remove(path)
        with patch.object(self.publisher.spool, 'remove', side_effect=crash):
            with self.assertRaises(OSError):
                self.publisher._process(self.publisher.spool.lane_entries('camera_1'))
        self.publisher.spool.close()
        self.publisher = ResultPublisher(self.config, client=self.api)
        self.publisher._recover()
        self.drain()
        self.assertEqual(len(self.api.frames), 2)

    def test_spool_exclusive_owner_and_bounded_capacity(self):
        with self.assertRaises(RuntimeError):
            ResultSpool(self.config.spool_dir)
        before = self.publisher.spool.size()
        self.publisher.spool.max_bytes = before + self.publisher.spool.reserve_bytes + 100
        with self.assertRaises(SpoolFull):
            self.publisher.spool.enqueue('camera_1', 'frame', {'large': 'x' * 1000})
        self.assertEqual(self.publisher.spool.size(), before)

    def test_invalid_boxes_and_unknown_confidence_are_rejected(self):
        for changes in ({'bbox': [0,0,0,1]}, {'bbox': [float('nan'),0,1,1]}, {'confidence': None},
                        {'track_id': True}, {'is_prediction': 'false'}):
            item = detection(); item.update(changes)
            with self.assertRaises(ValueError):
                frame_fact(capture(), [item])

    def test_pending_results_keep_original_implementation_version(self):
        self.frame()
        self.config.implementation_version = 'different-live-config'
        # Existing queue retains its captured producer version, not a new env value.
        self.drain()
        self.assertEqual(len(self.api.frames), 1)

    def test_registered_instance_version_mismatch_blocks_submission(self):
        self.config.implementation_version = 'unregistered-version'
        self.frame()
        with self.assertRaises(BusinessError) as caught:
            self.drain()
        self.assertEqual(caught.exception.code, 'IMPLEMENTATION_MISMATCH')
        self.assertFalse(any(p in ('/tasks', '/results/register') for p,b in self.api.calls))
        self.assertTrue(self.publisher.spool.lane_entries('camera_1'))

    def test_malformed_ack_preserves_frozen_request(self):
        self.frame()
        self.publisher._process(self.publisher.spool.lane_entries('camera_1'))
        for ack in ({}, {'accepted_result_ids': None},
                    {'accepted_result_ids': ['unknown'], 'duplicate_result_ids': [], 'rejected_results': []}):
            with patch.object(self.api, 'call', return_value=ack):
                with self.assertRaises(BusinessError) as caught:
                    self.publisher._process(self.publisher.spool.lane_entries('camera_1'))
            self.assertEqual(caught.exception.code, 'INVALID_RESULT_ACK')
        self.drain()
        self.assertEqual(len(self.api.frames), 1)

    def test_legacy_tracking_ack_does_not_discard_close(self):
        self.frame()
        self.drain()
        self.publisher._interrupt('camera_1', 'test-stop', False)
        with patch.object(self.api, 'call', return_value={}):
            with self.assertRaises(BusinessError):
                self.drain()
        self.assertTrue(self.publisher.spool.lane_entries('camera_1'))
        self.drain()

    def test_backpressure_records_gap_and_rotates_context(self):
        original = self.frame()
        self.publisher.paused_at = self.publisher.spool.load_state(original)['last_at']
        time.sleep(.002)
        replacement = self.frame(2)
        self.assertNotEqual(original, replacement)
        self.drain()
        close = next(b for p,b in self.api.calls if p == '/tracking/close')
        self.assertEqual(close['reason_code'], 'analysis_backpressure')
        self.assertLess(close['gap_start_at'], close['gap_end_at'])

    def test_expired_results_reclaimed_without_network(self):
        frame = capture(age_ms=8 * 86400000)
        context = self.publisher._begin_frame('camera_1', frame, 'service-a', 'component-a')
        self.publisher._record(context, frame, [detection()], frame.frame_ts_ms + 1, [])
        self.publisher._interrupt('camera_1', 'test-stop', True)
        self.drain()
        self.assertEqual(self.api.calls, [])
        self.assertEqual(self.publisher.confirmed, 0)
        self.assertEqual(self.publisher.spool.all_states()[0]['kind'], 'expiry_receipt')

    def test_health_survives_unreadable_journal(self):
        with patch.object(self.publisher.spool, 'snapshot', side_effect=OSError('unavailable')):
            self.assertEqual(self.publisher.health()['state'], 'degraded')

    def test_service_identity_change_makes_no_api_request(self):
        self.frame()
        self.config.service_id = 'other-owner'
        with self.assertRaises(BusinessError):
            self.drain()
        self.assertEqual(self.api.calls, [])


class ClientAndConfigTests(unittest.TestCase):
    def test_opt_in_is_disabled_without_config_or_files(self):
        self.assertFalse(PersistenceConfig({}).enabled)

    def test_redirect_and_legacy_success_are_not_acknowledgements(self):
        for data in (b'{"code":200}', b'[]', b'<html>login</html>'):
            response = io.BytesIO(data)
            opener = SimpleNamespace(open=lambda *a, **k: response)
            client = BusinessClient('http://127.0.0.1/api/v1/business', 'test', 'private', opener=opener)
            with self.assertRaises(BusinessError) as caught:
                client.call('/results/register', {})
            self.assertNotIn('private', str(caught.exception))

    def test_url_cannot_embed_credentials(self):
        with self.assertRaises(ValueError):
            BusinessClient('https://user:secret@host/api', 'test', 'token')

    def test_duplicate_camera_stream_mapping_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            mapping = dict(source_id=new_id(), camera_stream_id=new_id(), instance_id=new_id())
            path = Path(directory) / 'sources.json'
            path.write_text(json.dumps({'camera_1': mapping, 'camera_2': mapping}))
            env = {'VIDEO_RESULTS_' + key: value for key,value in dict(PERSIST_ENABLED='true',
                BUSINESS_BASE_URL='http://127.0.0.1/api/v1/business', SERVICE_ID='test', SERVICE_TOKEN='offline',
                SPOOL_DIR=directory, SOURCE_MAP_FILE=str(path), IMPLEMENTATION_CODE='botsort',
                IMPLEMENTATION_VERSION='test-v1').items()}
            with self.assertRaisesRegex(ValueError, 'distinct camera stream'):
                PersistenceConfig(env)

    def test_compose_passes_producer_config_but_media_gets_no_token(self):
        import yaml
        compose=yaml.safe_load((Path(__file__).resolve().parents[5]/'deploy/compose.yml').read_text())
        analysis=compose['services']['analysis']['environment']
        media=compose['services']['mediamtx'].get('environment',{})
        self.assertEqual(analysis['VIDEO_RESULTS_PERSIST_ENABLED'],'true')
        self.assertIn('PIPELINE_TOKEN',analysis['VIDEO_RESULTS_SERVICE_TOKEN'])
        self.assertFalse(any(key.startswith('VIDEO_RESULTS_') for key in media))


class SenderBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_corrupt_blocked_lane_is_retained_and_shutdown_wakes_retry(self):
        fixture = PersistenceTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        publisher = fixture.publisher
        fixture.frame()
        publisher.blocked['camera_1'] = 'FORBIDDEN'
        with patch.object(publisher.spool, 'load_state', side_effect=ValueError('corrupt state')):
            publisher.tasks = [asyncio.create_task(publisher._lane('camera_1'))]
            await asyncio.sleep(.05)
            self.assertFalse(publisher.tasks[0].done())
            self.assertEqual(publisher.health()['state'], 'degraded')
        publisher.inputs.clear()
        await asyncio.wait_for(publisher.stop(), timeout=.5)
        self.assertTrue(publisher.spool.lane_entries('camera_1'))
        self.assertEqual(fixture.api.calls, [])


if __name__ == '__main__':
    unittest.main()
