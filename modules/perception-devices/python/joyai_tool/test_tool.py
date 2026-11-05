import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from .contracts import agreed
from .ledger import Ledger
from .publisher import Publisher
from .observer import parse_action
from .monitor import Monitor
from .review_runtime import OnDemandReviewer
from .evidence import review_frames


class ManualReviewTest(unittest.TestCase):
    def test_restart_endpoint_requires_authentication_and_rejects_invalid_or_missing_events(self):
        from fastapi.testclient import TestClient
        from .app import app
        previous = dict(app.state._state)
        try:
            app.state.config = {'token': 'private-token'}
            app.state.monitor = Mock()
            app.state.monitor.restart_review.return_value = {'pending_reviews': 1}
            client = TestClient(app)
            report = '12345678-1234-4123-8123-123456789abc'
            self.assertEqual(401, client.post('/reviews/restart', json={'report_id': report}).status_code)
            self.assertEqual(422, client.post('/reviews/restart', json={'report_id': '../video'}).status_code)
            response = client.post('/reviews/restart', json={'report_id': report},
                                   headers={'X-JoyAI-Token': 'private-token'})
            self.assertEqual(200, response.status_code)
            app.state.monitor.restart_review.assert_called_once_with(report)
            app.state.monitor.restart_review.side_effect = ValueError('原视频片段不存在或已过期')
            self.assertEqual(409, client.post('/reviews/restart', json={'report_id': report},
                            headers={'X-JoyAI-Token': 'private-token'}).status_code)
        finally:
            app.state._state.clear()
            app.state._state.update(previous)

    def test_review_publishes_new_assessments_on_the_original_event_without_overwriting_history(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = Ledger(Path(folder) / 'delivery.db')
            ledger.save('session', 'unit', {'id': 'session', 'task_id': 'old-task', 'run_id': 'old-run'})
            client = Mock()
            client.get.side_effect = lambda path, *args: ({'event_key': 'joyai:original', 'revision': 2,
                'evidence': [{'evidence_id': 'evidence'}]} if path.startswith('/events/') else {'revision': 2})
            client.post.return_value = {}
            publisher = Publisher({'business_url': 'http://localhost/api/v1/business', 'token': 'test',
                'review_model': 'test', 'cameras': {'camera_1': {'name': '1号摄像头'}}}, ledger, client)
            publisher.asset = Mock()
            publisher.assessment = Mock(side_effect=['new-joy-result', 'new-review-result'])
            verdict = {'decision': 'confirmed', 'kind': 'fall', 'reason': '测试结果',
                       'report': {'observations': ['测试观察']}}
            job = dict(id='attempt', kind='job', manual_review=True, root_candidate_id='original',
                previous_report_id='old-report', event_id='original-event', unit_id='session',
                review_task_id='new-task', review_run_id='new-run', event_type='fall',
                source_id='source', camera_id='camera_1', start=100, end=110, trigger_at=105,
                asset_id='original-video', thumbnail_asset_id='original-image', evidence={'duration': 10},
                observation='初筛', joy_verdict=verdict, review_verdict=verdict)
            publisher.publish(job)
            publisher.asset.assert_not_called()
            event = next(c.args[1] for c in client.post.call_args_list if c.args[0] == '/events/register')
            report = next(c.args[1] for c in client.post.call_args_list if c.args[0] == '/reports/register')
            self.assertEqual('original-event', event['event_id'])
            self.assertEqual('joyai:original', event['event_key'])
            self.assertEqual(2, event['expected_revision'])
            self.assertEqual('new-run', event['run_id'])
            self.assertEqual('original-event', report['subject_id'])
            self.assertEqual('joyai_anomaly_review:attempt', report['report_type'])
            self.assertEqual('new-task', report['task_id'])
            self.assertEqual('original', report['report_json']['candidate_id'])
            self.assertEqual('old-report', report['report_json']['previous_report_id'])
            self.assertEqual('published', ledger.get('attempt')['state'])

    def test_restart_uses_original_clip_keeps_history_and_deduplicates_pending_clicks(self):
        with tempfile.TemporaryDirectory() as folder:
            monitor = object.__new__(Monitor)
            monitor.lock = threading.RLock()
            monitor.stop_event = threading.Event()
            monitor.threads = [Mock(is_alive=Mock(return_value=True))]
            monitor.config = {'storage_root': folder}
            monitor.publisher = Mock()
            monitor.ledger = Ledger(Path(folder) / 'delivery.db')
            monitor.status = Mock(return_value={'pending_reviews': 1})
            (Path(folder) / 'original.mp4').write_bytes(b'video')
            original = dict(id='original', kind='job', state='published', report_id='report',
                camera_id='camera_1', source_id='source', unit_id='old-session', trigger_at=100,
                event_type='fall', observation='疑似跌倒', joy_verdict={'decision': 'confirmed', 'kind': 'fall'},
                start=95, end=105, storage_key='original.mp4', asset_id='video', thumbnail_asset_id='image',
                evidence={'duration': 10}, event_id='event', review_verdict={'decision': 'rejected'},
                calls={'report': {'response': {'report_id': 'report'}}})
            monitor.ledger.save('original', 'job', original)
            with patch('joyai_tool.monitor.review_frames', return_value=[{'jpeg': 'new-sample'}]) as sample:
                monitor.restart_review('report')
                monitor.restart_review('report')
                sample.assert_called_once_with(Path(folder) / 'original.mp4')
            self.assertEqual(original, monitor.ledger.get('original'))
            pending = monitor.pending()
            self.assertEqual(1, len(pending))
            job = pending[0]
            self.assertNotEqual(original['id'], job['id'])
            self.assertEqual('original', job['root_candidate_id'])
            self.assertEqual('event', job['event_id'])
            self.assertEqual('old-session', job['unit_id'])
            self.assertEqual([{'jpeg': 'new-sample'}], job['frames'])
            self.assertNotIn('review_verdict', job)
            self.assertNotIn('calls', job)
            job['state'] = 'published'
            monitor.ledger.save(job['id'], 'job', job)
            (Path(folder) / 'original.mp4').unlink()
            with self.assertRaisesRegex(ValueError, '不存在或已过期'):
                monitor.restart_review('report')
            self.assertEqual([], monitor.pending())
            with self.assertRaisesRegex(ValueError, '找不到'):
                monitor.restart_review('unknown')

    def test_video_resampling_uses_eight_ordered_frames_from_saved_clip(self):
        import cv2
        import numpy as np
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'clip.avi'
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 4, (64, 48))
            for i in range(40):
                writer.write(np.full((48, 64, 3), i * 5, np.uint8))
            writer.release()
            frames = review_frames(path)
            self.assertEqual(8, len(frames))
            self.assertEqual(0, frames[0]['offset'])
            self.assertEqual(9.75, frames[-1]['offset'])
            self.assertEqual(sorted(f['offset'] for f in frames), [f['offset'] for f in frames])

    def test_review_creates_a_recording_task_and_never_reopens_the_old_live_session(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = Ledger(Path(folder) / 'delivery.db')
            client = Mock()
            client.get.return_value = {'items': []}
            client.post.side_effect = lambda path, body: (
                {'task_id': 'task', 'revision': 1} if path == '/tasks' else
                {'task_id': 'task', 'run_id': 'run'} if path == '/tasks/start' else {})
            publisher = Publisher({'business_url': 'http://localhost/api/v1/business', 'token': 'test',
                'tool_url': 'http://localhost', 'cameras': {'camera_1': {'source_id': 'source'}}}, ledger, client)
            job = {'id': 'manual', 'kind': 'job', 'manual_review': True, 'asset_id': 'video', 'start': 100, 'end': 110}
            publisher.prepare_review(job)
            task = next(c.args[1] for c in client.post.call_args_list if c.args[0] == '/tasks')
            self.assertEqual('recording', task['input']['kind'])
            self.assertEqual(['video'], task['input']['asset_ids'])
            self.assertEqual('once', task['task_mode'])
            self.assertEqual('run', ledger.get('manual')['review_run_id'])
            self.assertNotIn('/streams/open', [c.args[0] for c in client.post.call_args_list])


class AgreementTest(unittest.TestCase):
    def test_status_exposes_pending_event_metadata_without_frames_or_private_requests(self):
        with tempfile.TemporaryDirectory() as folder:
            config = {'state_dir': folder, 'business_url': 'http://localhost/api/v1/business',
                      'token': 'private', 'observer_url': 'http://localhost',
                      'review_url': 'http://127.0.0.1:34203/v1', 'review_model': 'test',
                      'model_url': 'http://localhost/v1', 'clip_seconds': 10,
                      'cameras': {'camera_1': {'name': '1号摄像头', 'location': '大厅'}}}
            monitor = Monitor(config)
            job = {'id': 'candidate', 'camera_id': 'camera_1', 'event_type': 'fight',
                   'state': 'collecting', 'trigger_at': time.time(), 'observation': '疑似冲突',
                   'frames': ['private-image'], 'calls': {'private': 'service-token'},
                   'storage_key': 'private/path'}
            monitor.ledger.save(job['id'], 'job', job)
            event = monitor.status()['pending_events'][0]
            self.assertEqual('candidate', event['id'])
            self.assertEqual('collecting', event['state'])
            self.assertEqual('大厅', event['location'])
            self.assertEqual('1号摄像头', event['camera_name'])
            self.assertIsNone(event['video_asset_id'])
            for private in ('frames', 'calls', 'storage_key', 'token'):
                self.assertNotIn(private, event)
            job.update(state='reviewing', asset_id='video', thumbnail_asset_id='image')
            monitor.ledger.save(job['id'], 'job', job)
            event = monitor.status()['pending_events'][0]
            self.assertEqual('reviewing', event['state'])
            self.assertEqual('video', event['video_asset_id'])
            job.update(state='published')
            monitor.ledger.save(job['id'], 'job', job)
            self.assertEqual([], monitor.status()['pending_events'])
            failed = {**job, 'id': 'failed-review', 'state': 'blocked', 'manual_review': True,
                      'root_candidate_id': job['id'], 'previous_report_id': 'original-report',
                      'end': time.time(), 'error': '复核失败'}
            monitor.ledger.save(failed['id'], 'job', failed)
            status = monitor.status()
            self.assertEqual(0, status['pending_reviews'])
            self.assertEqual('blocked', status['pending_events'][0]['state'])
            monitor.ledger.save('new-review', 'job', {**failed, 'id': 'new-review', 'state': 'published'})
            self.assertEqual([], monitor.status()['pending_events'])

    def test_both_must_confirm_the_same_event(self):
        yes = {'decision': 'confirmed', 'kind': 'fight'}
        self.assertTrue(agreed('fight', yes, yes))
        for other in [None, {}, {'decision': 'uncertain', 'kind': 'fight'},
                      {'decision': 'rejected', 'kind': 'none'}, {'decision': 'confirmed', 'kind': 'fall'}]:
            with self.subTest(other=other):
                self.assertFalse(agreed('fight', yes, other))
                self.assertFalse(agreed('fight', other, yes))

    def test_delivery_reuses_the_exact_request_after_connection_loss(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'delivery.db'
            ledger = Ledger(path)
            job = {'id': 'job', 'kind': 'job'}
            client = Mock()
            client.post.side_effect = [RuntimeError('lost response'), {'event_id': 'saved'}]
            with self.assertRaises(RuntimeError):
                ledger.call(job, 'event', '/events/register', {'request_id': 'original', 'at': 123}, client)
            recovered = Ledger(path)
            job = recovered.get('job')
            response = recovered.call(job, 'event', '/events/register', {'request_id': 'changed', 'at': 999}, client)
            self.assertEqual({'event_id': 'saved'}, response)
            self.assertEqual(client.post.call_args_list[0], client.post.call_args_list[1])
            recovered.call(job, 'event', '/events/register', {}, client)
            self.assertEqual(2, client.post.call_count)

    def test_runtime_finish_retries_after_lost_ack_and_never_cancels_success(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = Ledger(Path(folder) / 'delivery.db')
            client = Mock()
            client.get.return_value = {'revision': 2}
            client.post.side_effect = [RuntimeError('ack lost'), {'state': 'succeeded'}]
            publisher = Publisher({}, ledger, client)
            job = dict(id='review', kind='job', manual_review=True,
                       review_task_id='task', review_run_id='run', state='registering')
            with self.assertRaises(RuntimeError):
                publisher.finish_review(job)
            restored = ledger.get('review')
            self.assertEqual('registering', restored['state'])
            publisher.finish_review(restored)
            self.assertTrue(restored['task_ended'])
            self.assertEqual(client.post.call_args_list[0], client.post.call_args_list[1])
            self.assertEqual('/tasks/end', client.post.call_args.args[0])
            self.assertEqual('succeeded', client.post.call_args.args[1]['state'])

    def test_event_and_report_require_both_results_acknowledged(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = Ledger(Path(folder) / 'delivery.db')
            publisher = Publisher({'business_url': 'http://localhost/api/v1/business', 'token': 'test'}, ledger, Mock())
            publisher.asset = Mock()
            publisher.assessment = Mock(side_effect=['joy-result', RuntimeError('review result not acknowledged')])
            job = {'id': 'job', 'joy_verdict': {}, 'review_verdict': {}}
            with self.assertRaises(RuntimeError):
                publisher.publish(job)
            publisher.client.post.assert_not_called()

    def test_native_delegation_never_becomes_confirmation(self):
        self.assertEqual([], parse_action('</silence>')['candidates'])
        result = parse_action('</response>两人靠近，尚未看见攻击。</delegation>{"kind":"fight","question":"请复核是否打架"}')
        self.assertEqual('delegate', result['action'])
        self.assertNotIn('verdict', result['candidates'][0])
        normal = {'decision': 'rejected', 'kind': 'none', 'confidence': .95, 'reason': '仅正常办公'}
        self.assertEqual([], parse_action('</response>' + json.dumps(normal))['candidates'])

    def test_retiring_an_input_completes_task_then_closes_session_with_stable_requests(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = Ledger(Path(folder) / 'delivery.db')
            client = Mock()
            client.get.return_value = {'revision': 2}
            client.post.return_value = {'state': 'succeeded'}
            publisher = Publisher({}, ledger, client)
            unit = {'id': 'session', 'kind': 'unit', 'task_id': 'task', 'run_id': 'run', 'calls': {'start': {'response': {}}}}
            publisher.retire(unit)
            self.assertEqual(['/tasks/end', '/streams/close'], [call.args[0] for call in client.post.call_args_list])
            self.assertTrue(ledger.get('session')['retired'])
            publisher.retire(ledger.get('session'))
            self.assertEqual(2, client.post.call_count)

    def test_distinct_candidates_do_not_replace_each_others_result_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = Ledger(Path(folder) / 'delivery.db')
            ledger.save('unit', 'unit', {'id': 'unit', 'task_id': 'task', 'run_id': 'run', 'source_id': 'source'})
            publisher = Publisher({}, ledger, Mock())
            publisher.prepare = Mock()
            def register(path, body):
                return {'accepted_result_ids': [body['results'][0]['result_id']]}
            publisher.client.post.side_effect = register
            for key in ['candidate-fight', 'candidate-fall']:
                publisher.assessment({'id': key, 'kind': 'job', 'unit_id': 'unit', 'start': 100, 'end': 110,
                    'processed_at': 120, 'event_type': 'fight'}, 'joyai', {'decision': 'uncertain', 'reason': '待复核'})
            requests = [call.args[1] for call in publisher.client.post.call_args_list]
            self.assertNotEqual(requests[0]['result_set_id'], requests[1]['result_set_id'])
            self.assertNotEqual(requests[0]['set_key'], requests[1]['set_key'])


class OnDemandReviewTest(unittest.TestCase):
    def make_reviewer(self):
        reviewer = OnDemandReviewer({'review_url': 'http://127.0.0.1:34203/v1', 'review_model': 'test', 'state_dir': '/tmp/joyai-fixture'}, threading.Event())
        reviewer.command = Mock()
        reviewer.healthy = Mock(return_value=True)
        reviewer.alive = Mock(return_value=True)
        reviewer.reviewer = Mock()
        return reviewer

    def test_idle_does_not_start_model_and_two_clips_share_one_load(self):
        reviewer = self.make_reviewer()
        reviewer.release()
        reviewer.command.assert_not_called()
        self.assertEqual('stopped', reviewer.status()['state'])
        reviewer.review('fight', [], {})
        reviewer.review('fall', [], {})
        self.assertEqual(['review-start'], [c.args[0] for c in reviewer.command.call_args_list])
        self.assertEqual(2, reviewer.reviewer.review.call_count)
        reviewer.release()
        self.assertEqual(['review-start', 'review-stop'], [c.args[0] for c in reviewer.command.call_args_list])
        self.assertEqual('stopped', reviewer.status()['state'])

    def test_failed_launch_releases_model_without_confirming(self):
        reviewer = self.make_reviewer()
        reviewer.command.side_effect = [RuntimeError('launch failed'), None]
        with self.assertRaises(RuntimeError):
            reviewer.review('fight', [], {})
        reviewer.reviewer.review.assert_not_called()
        self.assertEqual('error', reviewer.status()['state'])
        self.assertEqual(['review-start', 'review-stop'], [c.args[0] for c in reviewer.command.call_args_list])

    def test_stop_during_loading_releases_model(self):
        reviewer = self.make_reviewer()
        reviewer.command.side_effect = lambda action: reviewer.stop_event.set() if action == 'review-start' else None
        with self.assertRaises(RuntimeError):
            reviewer.review('fight', [], {})
        reviewer.reviewer.review.assert_not_called()
        self.assertFalse(reviewer.owned)
        self.assertEqual(['review-start', 'review-stop'], [c.args[0] for c in reviewer.command.call_args_list])

    def test_release_failure_is_visible_and_can_be_retried(self):
        reviewer = self.make_reviewer()
        reviewer.ensure_ready()
        reviewer.command.side_effect = [RuntimeError('stop failed'), None]
        with self.assertRaises(RuntimeError):
            reviewer.release()
        self.assertTrue(reviewer.owned)
        self.assertEqual('error', reviewer.status()['state'])
        reviewer.release()
        self.assertFalse(reviewer.owned)
        self.assertEqual('stopped', reviewer.status()['state'])

    def test_dead_engine_does_not_wait_for_full_startup_timeout(self):
        reviewer = self.make_reviewer()
        reviewer.healthy.return_value = False
        reviewer.alive.return_value = False
        with self.assertRaisesRegex(RuntimeError, '进程启动失败'):
            reviewer.ensure_ready()
        self.assertFalse(reviewer.owned)

    def test_startup_timeout_releases_live_but_unready_model(self):
        reviewer = self.make_reviewer()
        reviewer.healthy.return_value = False
        with patch('joyai_tool.review_runtime.time.monotonic', side_effect=[0, reviewer.timeout + 1]):
            with self.assertRaisesRegex(RuntimeError, '加载超时'):
                reviewer.ensure_ready()
        reviewer.reviewer.review.assert_not_called()
        self.assertFalse(reviewer.owned)
        self.assertEqual(['review-start', 'review-stop'], [c.args[0] for c in reviewer.command.call_args_list])

    def test_collecting_and_future_retry_jobs_do_not_keep_qwen_resident(self):
        for job in [{'state': 'collecting'}, {'state': 'awaiting_review', 'retry_at': float('inf')}]:
            with self.subTest(job=job):
                monitor = object.__new__(Monitor)
                monitor.stop_event = threading.Event()
                monitor.pending = Mock(return_value=[job])
                monitor.publisher = Mock()
                monitor.retire_idle = Mock()
                monitor.release_reviewer = Mock()
                with patch.object(monitor.stop_event, 'wait', side_effect=lambda _: monitor.stop_event.set()):
                    monitor.deliver_pending()
                monitor.publisher.asset.assert_not_called()
                monitor.release_reviewer.assert_called_once()


if __name__ == '__main__':
    unittest.main()
