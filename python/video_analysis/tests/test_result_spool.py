import copy
import json
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from video_analysis.result_spool import ResultSpool, SpoolConflict


PROJECT = Path(__file__).resolve().parents[3]


def batch():
    return {
        'request_id': 'request-001',
        'run_id': 'run-001',
        'expires_at': '2026-11-02T10:00:00+08:00',
        'results': [
            {'result_id': 'result-001', 'targets': [{'confidence': 0.8}]},
            {'result_id': 'result-002', 'targets': []},
        ],
    }


def confirmation(accepted=None, duplicate=None, rejected=None):
    return {'accepted_result_ids': accepted or [],
            'duplicate_result_ids': duplicate or [],
            'rejected_results': rejected or []}


class ResultSpoolTests(unittest.TestCase):
    def setUp(self):
        self.test_parent = PROJECT / '.run' / 'test-result-spool'
        self.test_parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=self.test_parent)
        self.spool = ResultSpool(Path(self.temporary.name) / 'pending')
        self.spool.pending()

    def tearDown(self):
        self.temporary.cleanup()
        for directory in (self.test_parent, self.test_parent.parent):
            try:
                directory.rmdir()
            except OSError:
                pass

    def put(self, payload=None):
        return self.spool.put('service:detector', 'results.register',
                              batch() if payload is None else payload)

    def test_construction_does_not_probe_or_create_storage(self):
        path = Path(self.temporary.name) / 'not-created'
        with patch('video_analysis.result_spool.Path.resolve', side_effect=AssertionError('resolve did I/O')), \
                patch('video_analysis.result_spool.Path.exists', side_effect=AssertionError('exists did I/O')), \
                patch('video_analysis.result_spool.Path.is_dir', side_effect=AssertionError('is_dir did I/O')), \
                patch('video_analysis.result_spool.Path.mkdir', side_effect=AssertionError('mkdir did I/O')):
            lazy = ResultSpool(path)
        self.assertFalse(path.exists())
        self.assertEqual(lazy.pending(), [])
        self.assertTrue(path.is_dir())
        for invalid in ('', ' ', '\x00', None):
            with self.subTest(invalid=repr(invalid)), self.assertRaises(ValueError):
                ResultSpool(invalid)

    def test_unavailable_listing_cannot_be_reported_as_an_empty_queue(self):
        with patch('video_analysis.result_spool.os.listdir', side_effect=PermissionError('test unavailable NFS')):
            with self.assertRaises(PermissionError):
                self.spool.pending()

    def test_multi_frame_batch_is_persistent_and_copied(self):
        payload = batch()
        expected = copy.deepcopy(payload)
        key = self.put(payload)
        payload['results'][0]['targets'].clear()
        restarted = ResultSpool(self.spool.directory)
        self.assertEqual(restarted.pending(), [key])
        stored = restarted.read(key)
        self.assertEqual(stored['actor_key'], 'service:detector')
        self.assertEqual(stored['operation'], 'results.register')
        self.assertEqual(stored['payload'], expected)
        stored['payload']['results'].clear()
        self.assertEqual(restarted.read(key)['payload'], expected)

    def test_same_request_reuses_record_but_changed_content_conflicts(self):
        key = self.put()
        reordered = dict(reversed(list(batch().items())))
        self.assertEqual(self.put(reordered), key)
        changed = batch()
        changed['results'][0]['targets'][0]['confidence'] = 0.9
        with self.assertRaises(SpoolConflict):
            self.put(changed)
        self.assertEqual(self.spool.pending(), [key])
        self.assertEqual(self.spool.read(key)['payload'], batch())

    def test_actor_and_operation_are_part_of_request_scope(self):
        first = self.put()
        second = self.spool.put('service:other', 'results.register', batch())
        third = self.spool.put('service:detector', 'results.other', batch())
        self.assertEqual(len({first, second, third}), 3)
        self.assertEqual(len(self.spool.pending()), 3)

    def test_full_accepted_and_duplicate_confirmation_removes_batch(self):
        key = self.put()
        response = confirmation(['result-001'], ['result-002'])
        self.assertTrue(self.spool.acknowledge(key, response))
        self.assertEqual(self.spool.pending(), [])
        self.assertEqual(ResultSpool(self.spool.directory).pending(), [])

    def test_partial_confirmation_preserves_original_request(self):
        key = self.put()
        for response in (confirmation(['result-001']),
                         confirmation(['result-001'], rejected=[
                             {'result_id': 'result-002', 'retryable': True}]),
                         confirmation()):
            with self.subTest(response=response):
                self.assertFalse(self.spool.acknowledge(key, response))
                self.assertEqual(self.spool.read(key)['payload'], batch())

    def test_partial_replacement_preserves_ids_and_coverage_under_new_request(self):
        payload = batch()
        payload['analysis_coverage'] = {'frame_ids': ['frame-1', 'frame-2'],
                                        'analyzed_frame_count': 2, 'closed': False}
        key = self.put(payload)
        new_key = self.spool.replace_unconfirmed(key, confirmation(['result-001']))
        replacement = self.spool.read(new_key)['payload']
        self.assertNotEqual(replacement['request_id'], payload['request_id'])
        self.assertEqual(replacement['results'], [payload['results'][1]])
        self.assertEqual(replacement['analysis_coverage'], payload['analysis_coverage'])
        self.assertEqual(self.spool.pending(), [new_key])

    def test_partial_replacement_must_be_durable_before_old_batch_is_removed(self):
        key = self.put()
        response = confirmation(['result-001'])
        original_unlink = Path.unlink
        def fail_original(path, *args, **kwargs):
            if path == self.spool.directory / (key + '.json'):
                raise OSError('test interruption after new request saved')
            return original_unlink(path, *args, **kwargs)
        with patch('video_analysis.result_spool.Path.unlink', new=fail_original):
            with self.assertRaises(OSError):
                self.spool.replace_unconfirmed(key, response)
        self.assertEqual(len(self.spool.pending()), 2)
        replacement = self.spool.replace_unconfirmed(key, response)
        self.assertEqual(self.spool.pending(), [replacement])
        self.assertEqual(self.spool.read(replacement)['payload']['results'], [batch()['results'][1]])
        nonretryable = self.put()
        with self.assertRaises(ValueError):
            self.spool.replace_unconfirmed(nonretryable, confirmation(
                rejected=[{'result_id': 'result-001', 'retryable': False}]))
        self.assertIn(nonretryable, self.spool.pending())

    def test_unknown_duplicate_or_malformed_confirmations_cannot_delete(self):
        key = self.put()
        responses = [
            {}, None,
            {'accepted_result_ids': ['result-001', 'result-002']},
            confirmation(['result-001', 'result-002', 'unknown']),
            confirmation(['result-001'], ['result-001', 'result-002']),
            confirmation(['result-001', 'result-002'], rejected=[{}]),
            confirmation(['result-001', 'result-002'], rejected=[{'result_id': 'unknown'}]),
        ]
        for response in responses:
            with self.subTest(response=response):
                with self.assertRaises(ValueError):
                    self.spool.acknowledge(key, response)
                self.assertEqual(self.spool.pending(), [key])

    def test_response_loss_can_replay_exact_batch_after_restart(self):
        key = self.put()
        restarted = ResultSpool(self.spool.directory)
        self.assertEqual(restarted.put('service:detector', 'results.register', batch()), key)
        self.assertEqual(restarted.read(key)['payload']['expires_at'], batch()['expires_at'])
        self.assertTrue(restarted.acknowledge(
            key, confirmation(duplicate=['result-001', 'result-002'])))

    def test_concurrent_puts_from_two_instances_reuse_one_record(self):
        other = ResultSpool(self.spool.directory)
        def put(index):
            instance = self.spool if index % 2 else other
            return instance.put('service:detector', 'results.register', batch())
        with ThreadPoolExecutor(max_workers=4) as executor:
            keys = list(executor.map(put, range(16)))
        self.assertEqual(len(set(keys)), 1)
        self.assertEqual(self.spool.pending(), [keys[0]])

    def test_file_sync_failure_cannot_publish_half_batch(self):
        with patch('video_analysis.result_spool.os.fsync', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.put()
        self.assertEqual(self.spool.pending(), [])
        self.assertEqual(list(self.spool.directory.iterdir()), [])

    def test_rename_failure_leaves_no_registered_batch(self):
        with patch('video_analysis.result_spool.os.replace', side_effect=OSError('rename failed')):
            with self.assertRaises(OSError):
                self.put()
        self.assertEqual(self.spool.pending(), [])
        self.assertEqual(list(self.spool.directory.iterdir()), [])

    def test_directory_sync_failure_raises_and_original_key_remains_retryable(self):
        with patch('video_analysis.result_spool._sync_directory',
                   side_effect=OSError('directory sync failed')):
            with self.assertRaises(OSError):
                self.put()
        keys = self.spool.pending()
        self.assertEqual(len(keys), 1)
        self.assertEqual(self.put(), keys[0])
        self.assertEqual(self.spool.read(keys[0])['payload'], batch())

    def test_delete_failure_preserves_confirmed_batch_for_safe_replay(self):
        key = self.put()
        with patch('video_analysis.result_spool.Path.unlink', side_effect=OSError('delete failed')):
            with self.assertRaises(OSError):
                self.spool.acknowledge(key, confirmation(['result-001', 'result-002']))
        self.assertEqual(self.spool.pending(), [key])

    def test_damaged_record_is_not_read_or_acknowledged(self):
        key = self.put()
        path = self.spool.directory / (key + '.json')
        record = json.loads(path.read_bytes())
        record['payload']['results'].pop()
        path.write_text(json.dumps(record))
        with self.assertRaises(ValueError):
            self.spool.read(key)
        with self.assertRaises(ValueError):
            self.spool.acknowledge(key, confirmation(['result-001', 'result-002']))
        self.assertTrue(path.exists())

    def test_temporary_files_are_not_pending_and_keys_cannot_escape_directory(self):
        (self.spool.directory / '.pending-crashed.tmp').write_text('{')
        self.assertEqual(self.spool.pending(), [])
        with self.assertRaises(ValueError):
            self.spool.read('../elsewhere')

    def test_invalid_batch_never_creates_record(self):
        invalid = [None, {}, {'request_id': 'request-001', 'results': []},
                   {'request_id': 'request-001', 'results': [{}]},
                   {'request_id': 'request-001', 'results': [
                       {'result_id': 'same'}, {'result_id': 'same'}]},
                   {'request_id': 'request-001', 'results': [
                       {'result_id': 'result-001', 'confidence': float('nan')}]}]
        for payload in invalid:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    self.spool.put('service:detector', 'results.register', payload)
        self.assertEqual(self.spool.pending(), [])


if __name__ == '__main__':
    unittest.main()
