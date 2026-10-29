import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from video_analysis.business_client import BusinessRequestError, BusinessUnavailable
from video_analysis.business_runtime import BusinessRuntime
from video_analysis.recording_delivery import RecordingDelivery


SOURCE = '10000000-0000-4000-8000-000000000001'
STREAM = '20000000-0000-4000-8000-000000000001'
SESSION = '30000000-0000-4000-8000-000000000001'
ASSET = '40000000-0000-4000-8000-000000000001'
INSTANCE = '50000000-0000-4000-8000-000000000001'


def manifest():
    return {
        'request_id': 'asset:fixture-recording', 'asset_id': ASSET,
        'producer_key': 'recording:' + SOURCE + ':' + SESSION + ':1',
        'asset_type': 'recording', 'source_id': SOURCE, 'stream_session_id': SESSION,
        'storage_key': f'recordings/{SOURCE}/{SESSION}/{ASSET}.mp4',
        'state': 'available', 'start_at': '2026-10-27T00:00:00.080Z',
        'end_at': '2026-10-27T00:00:01.080Z', 'expires_at': '2026-11-03T00:00:01.080Z',
        'content_type': 'video/mp4', 'byte_size': 123, 'checksum_sha256': 'a' * 64,
        'recording_alignment': {'schema_version': '1', 'stream_start_pts_ms': 80,
                                'stream_end_pts_ms': 1080, 'media_start_pts_ms': 0},
        'stream_session': {'stream_session_id': SESSION, 'started_at': '2026-10-27T00:00:00.000Z',
                           'time_origin_at': '2026-10-27T00:00:00.000Z', 'time_basis': 'ingest_clock',
                           'source_timezone': 'UTC', 'source_width': 1920, 'source_height': 1080},
        'end_timing': 'next_packet',
    }


def wait_for(predicate):
    deadline = time.monotonic() + 2
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError('Recording delivery did not reach the expected state')
        time.sleep(0.005)


class RecordingDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3] / '.run')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.client = Mock()
        self.client.open_session.side_effect = lambda payload: {
            'source_id': payload['source_id'], 'stream_session_id': payload['stream_session_id']}
        self.client.register_asset.side_effect = lambda payload: {
            'asset_id': payload['asset_id'], 'producer_key': payload['producer_key'],
            'state': 'available', 'revision': 1, 'duplicate': False}
        self.runtime = BusinessRuntime(self.client, source_streams={SOURCE: STREAM},
                                       instances={(SOURCE, 'botsort'): {
                                           'instance_id': INSTANCE, 'capability_code': 'tracking'}})

    def delivery(self, **options):
        return RecordingDelivery(self.client, self.runtime, storage_root=self.root,
                                 source_ids={SOURCE}, retry_interval=0.01, **options)

    def write_manifest(self, value=None):
        value = manifest() if value is None else value
        path = self.root / (value['storage_key'] + '.manifest.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def test_construction_and_callback_do_not_touch_storage_or_network(self):
        with patch.object(Path, 'read_text', side_effect=AssertionError('no callback disk I/O')), \
                patch.object(Path, 'rglob', side_effect=AssertionError('no callback scan')):
            delivery = self.delivery()
            delivery(manifest())
        self.assertEqual(delivery.status()['state'], 'idle')
        self.client.open_session.assert_not_called()
        self.client.register_asset.assert_not_called()

    def test_records_without_detection_and_uses_shared_input_metadata(self):
        path = self.write_manifest()
        delivery = self.delivery()
        delivery.start()
        self.addCleanup(delivery.stop)
        wait_for(lambda: delivery.status()['confirmed_manifests'] == 1)
        self.assertTrue(delivery.stop())

        opened = self.client.open_session.call_args.args[0]
        self.assertEqual(opened['camera_stream_id'], STREAM)
        self.assertEqual(opened['started_at'], '2026-10-27T00:00:00+00:00')
        self.assertEqual(opened['time_origin_at'], '2026-10-27T00:00:00+00:00')
        self.assertEqual((opened['source_width'], opened['source_height']), (1920, 1080))
        self.runtime.open_input(SOURCE, manifest()['stream_session'])
        self.assertEqual(self.client.open_session.call_count, 1)
        self.client.create_task.assert_not_called()
        self.client.start_task.assert_not_called()
        request = self.client.register_asset.call_args.args[0]
        self.assertNotIn('stream_session', request)
        self.assertNotIn('end_timing', request)
        self.assertEqual(request['recording_alignment'], manifest()['recording_alignment'])
        self.assertTrue(path.with_suffix(path.suffix + '.ack').is_file())
        self.assertEqual(delivery.status()['pending_manifests'], 0)

    def test_registration_retry_reuses_the_exact_payload_and_keeps_manifest(self):
        path = self.write_manifest()
        expected = self.client.register_asset.side_effect
        self.client.register_asset.side_effect = [BusinessUnavailable(), expected(manifest())]
        delivery = self.delivery()
        with self.assertLogs('video_analysis.recording_delivery', level='ERROR'):
            delivery._scan()
        self.assertEqual(delivery.status()['pending_manifests'], 1)
        self.assertTrue(path.exists())
        self.assertFalse(path.with_suffix(path.suffix + '.ack').exists())
        delivery._scan()
        first, second = self.client.register_asset.call_args_list
        self.assertEqual(first.args[0], second.args[0])
        self.assertEqual(self.client.open_session.call_count, 1)
        self.assertEqual(delivery.status()['confirmed_manifests'], 1)

    def test_session_open_failure_retries_before_registering_the_asset(self):
        self.write_manifest()
        self.client.open_session.side_effect = [BusinessUnavailable(),
                                               {'source_id': SOURCE, 'stream_session_id': SESSION}]
        delivery = self.delivery()
        with self.assertLogs('video_analysis.recording_delivery', level='ERROR'):
            delivery._scan()
        self.client.register_asset.assert_not_called()
        delivery._scan()
        self.assertEqual(self.client.register_asset.call_count, 1)
        self.assertEqual(self.client.open_session.call_args_list[0],
                         self.client.open_session.call_args_list[1])

    def test_callback_stays_nonblocking_while_registration_is_waiting(self):
        self.write_manifest()
        entered, release = threading.Event(), threading.Event()
        original = self.client.register_asset.side_effect

        def wait_for_network(payload):
            entered.set()
            release.wait(2)
            return original(payload)

        self.client.register_asset.side_effect = wait_for_network
        delivery = self.delivery()
        delivery.start()
        try:
            self.assertTrue(entered.wait(1))
            callback_done = threading.Event()
            caller = threading.Thread(target=lambda: (delivery(manifest()), callback_done.set()))
            caller.start()
            self.assertTrue(callback_done.wait(0.2))
            caller.join(1)
        finally:
            release.set()
            self.assertTrue(delivery.stop())
        self.assertEqual(delivery.status()['confirmed_manifests'], 1)

    def test_shutdown_scan_includes_the_final_sealed_segment(self):
        delivery = self.delivery()
        delivery.start()
        self.write_manifest()
        self.assertTrue(delivery.stop())
        self.assertEqual(delivery.status()['confirmed_manifests'], 1)
        self.assertEqual(delivery.status()['pending_manifests'], 0)

    def test_matching_ack_skips_registration_after_restart_without_reading_mp4(self):
        self.write_manifest()
        self.delivery()._scan()
        self.client.reset_mock()
        restarted = self.delivery()
        self.assertFalse((self.root / manifest()['storage_key']).exists())
        restarted._scan()
        self.client.open_session.assert_not_called()
        self.client.register_asset.assert_not_called()
        self.assertEqual(restarted.status()['pending_manifests'], 0)

    def test_changed_manifest_is_not_hidden_by_an_old_ack(self):
        path = self.write_manifest()
        delivery = self.delivery()
        delivery._scan()
        changed = manifest()
        changed['checksum_sha256'] = 'b' * 64
        path.write_text(json.dumps(changed), encoding='utf-8')
        self.client.register_asset.side_effect = BusinessRequestError('CONFLICT', 409)
        with self.assertLogs('video_analysis.recording_delivery', level='ERROR'):
            delivery._scan()
        delivery._scan()
        self.assertEqual(self.client.register_asset.call_count, 2)
        self.assertEqual(delivery.status()['pending_manifests'], 1)
        self.assertEqual(delivery.status()['blocked_manifests'], 1)

    def test_mismatched_success_is_never_an_acknowledgement(self):
        path = self.write_manifest()
        self.client.register_asset.side_effect = None
        self.client.register_asset.return_value = {'asset_id': ASSET, 'producer_key': 'different',
                                                   'state': 'available'}
        delivery = self.delivery()
        with self.assertLogs('video_analysis.recording_delivery', level='ERROR'):
            delivery._scan()
        self.assertFalse(path.with_suffix(path.suffix + '.ack').exists())
        self.assertEqual(delivery.status()['pending_manifests'], 1)

    def test_invalid_source_session_or_path_never_opens_an_input(self):
        for field, value in (('source_id', STREAM), ('stream_session_id', ASSET),
                             ('storage_key', '../outside.mp4')):
            with self.subTest(field=field):
                bad = manifest()
                path = self.write_manifest()
                bad[field] = value
                path.write_text(json.dumps(bad), encoding='utf-8')
                delivery = self.delivery()
                with self.assertLogs('video_analysis.recording_delivery', level='ERROR'):
                    delivery._scan()
                self.assertEqual(delivery.status()['pending_manifests'], 1)
                self.client.open_session.assert_not_called()
                self.client.register_asset.assert_not_called()


if __name__ == '__main__':
    unittest.main()
