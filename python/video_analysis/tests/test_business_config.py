from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from video_analysis.business_runtime import create_delivery
from video_analysis.config import load_business_config


PROJECT = Path(__file__).resolve().parents[3]
SOURCES = {'camera_1': '10000000-0000-4000-8000-000000000001',
           'camera_2': '10000000-0000-4000-8000-000000000002'}
STREAMS = {'10000000-0000-4000-8000-000000000001': '20000000-0000-4000-8000-000000000001',
           '10000000-0000-4000-8000-000000000002': '20000000-0000-4000-8000-000000000002'}
CAMERAS = {camera: 'rtsp://fixture.invalid/' + camera for camera in SOURCES}


def fixture():
    return {'api_url': 'http://127.0.0.1:18080/api/v1/business', 'service_id': 'fixture-tracker',
            'token_env': 'FIXTURE_BUSINESS_TOKEN', 'source_streams': dict(STREAMS),
            'instances': [{'source_id': source, 'algorithm': 'botsort',
                           'instance_id': '30000000-0000-4000-8000-000000000001',
                           'capability_code': 'tracking'} for source in SOURCES.values()]}


class BusinessConfigTests(unittest.TestCase):
    def setUp(self):
        self.parent = PROJECT / '.run' / 'test-business-config'
        self.parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=self.parent)
        self.path = Path(self.temporary.name) / 'business.json'
        self.environment = patch.dict(os.environ, {'FIXTURE_BUSINESS_TOKEN': 'fixture-token'}, clear=True)
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temporary.cleanup()
        for directory in (self.parent, self.parent.parent):
            try:
                directory.rmdir()
            except OSError:
                pass

    def load(self, value=None, **options):
        self.path.write_text(json.dumps(fixture() if value is None else value), encoding='utf-8')
        return load_business_config(self.path, cameras=CAMERAS,
                                    source_ids=options.pop('source_ids', SOURCES), algorithm='botsort', **options)

    def test_not_enabled_does_not_read_a_config_or_touch_storage(self):
        with patch.object(Path, 'read_text', side_effect=AssertionError('unexpected file read')):
            self.assertIsNone(load_business_config())

    def test_complete_explicit_bindings_and_nfs_default_without_storing_token(self):
        configuration = self.load()
        self.assertEqual(configuration['spool_dir'], '/data/nfs_storage/hxjm_datas/result-spool')
        self.assertEqual(configuration['source_streams'], STREAMS)
        self.assertEqual(set(configuration['instances']), {(source, 'botsort') for source in SOURCES.values()})
        self.assertEqual(configuration['batch_size'], 32)
        self.assertEqual(configuration['queue_size'], 256)
        self.assertEqual(configuration['flush_interval_seconds'], 0.2)
        self.assertEqual(configuration['timeout_seconds'], 5)
        self.assertNotIn('fixture-token', repr(configuration))
        self.assertFalse((Path(self.temporary.name) / 'spool').exists())
        os.environ['VIDEO_ANALYSIS_BUSINESS_CONFIG'] = str(self.path)
        self.assertEqual(load_business_config(cameras=CAMERAS, source_ids=SOURCES, algorithm='botsort'),
                         configuration)

    def test_enabled_configuration_requires_all_source_ids(self):
        for source_ids in ({}, {'camera_1': SOURCES['camera_1']},
                           dict(SOURCES, camera_2=SOURCES['camera_1'])):
            with self.subTest(source_ids=source_ids), self.assertRaises(ValueError):
                self.load(source_ids=source_ids)

    def test_sample_worker_requires_an_explicit_origin_instance_and_bounded_settings(self):
        value = fixture()
        sample = {'feature_url': 'http://127.0.0.1:28024',
                  'instance_id': '40000000-0000-4000-8000-000000000001'}
        value['sample_pipeline'] = sample
        loaded = self.load(value)['sample_pipeline']
        self.assertEqual(loaded['threshold'], 0.88)
        self.assertEqual(loaded['queue_size'], 16)
        self.assertEqual(loaded['capability_code'], 'person.reidentification')
        for name, invalid in (('feature_url', None), ('feature_url', 'http://user@localhost:28024'),
                              ('feature_url', 'http://localhost:28024/unexpected'),
                              ('instance_id', 1), ('threshold', -0.1), ('threshold', True),
                              ('threshold', float('inf')), ('queue_size', 0)):
            value['sample_pipeline'] = dict(sample, **{name: invalid})
            with self.subTest(name=name, invalid=invalid), self.assertRaises(ValueError):
                self.load(value)

    def test_missing_extra_or_repeated_mapping_and_wrong_algorithm_are_rejected(self):
        cases = []
        missing = fixture()
        missing['source_streams'].pop(SOURCES['camera_2'])
        cases.append(missing)
        duplicate_stream = fixture()
        duplicate_stream['source_streams'][SOURCES['camera_2']] = STREAMS[SOURCES['camera_1']]
        cases.append(duplicate_stream)
        for mutation in ('missing', 'duplicate', 'wrong_algorithm', 'unknown_source', 'invalid_uuid'):
            value = fixture()
            if mutation == 'missing':
                value['instances'].pop()
            elif mutation == 'duplicate':
                value['instances'].append(deepcopy(value['instances'][0]))
            elif mutation == 'wrong_algorithm':
                value['instances'][0]['algorithm'] = 'deepsort'
            elif mutation == 'unknown_source':
                value['instances'][0]['source_id'] = '10000000-0000-4000-8000-000000000003'
            else:
                value['instances'][0]['instance_id'] = '0' * 32
            cases.append(value)
        for index, value in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(ValueError):
                self.load(value)

    def test_inline_secrets_and_invalid_queue_timing_or_spool_options_are_rejected(self):
        for name, invalid in (('token', 'must-not-be-in-config'), ('batch_size', True),
                              ('batch_size', 0), ('queue_size', -1), ('flush_interval_seconds', 0),
                              ('timeout_seconds', float('nan')), ('spool_dir', 'relative/spool')):
            value = fixture()
            value[name] = invalid
            with self.subTest(field=name, invalid=repr(invalid)), self.assertRaises(ValueError):
                self.load(value)
        os.environ.pop('FIXTURE_BUSINESS_TOKEN')
        with self.assertRaises(ValueError) as raised:
            self.load()
        self.assertNotIn('must-not-be-in-config', str(raised.exception))

    def test_factory_passes_explicit_settings_and_reads_current_token_only_when_used(self):
        configuration = self.load()
        with patch('video_analysis.business_client.BusinessClient') as client_type, \
                patch('video_analysis.business_runtime.BusinessRuntime') as runtime_type, \
                patch('video_analysis.result_spool.ResultSpool') as spool_type, \
                patch('video_analysis.result_delivery.ResultDispatcher') as dispatcher_type:
            client_type.return_value.actor_key = 'service:fixture-tracker'
            delivery = create_delivery(configuration)
            self.assertIs(delivery, dispatcher_type.return_value)
            spool_type.assert_called_once_with('/data/nfs_storage/hxjm_datas/result-spool')
            runtime_type.assert_called_once_with(client_type.return_value, source_streams=STREAMS,
                                                 instances=configuration['instances'])
            token_provider = client_type.call_args.kwargs['token_provider']
            self.assertEqual(token_provider(), 'fixture-token')
            os.environ['FIXTURE_BUSINESS_TOKEN'] = 'rotated-fixture-token'
            self.assertEqual(token_provider(), 'rotated-fixture-token')
            options = dispatcher_type.call_args.kwargs
            self.assertIs(options['units'], runtime_type.return_value.execution_for)
            self.assertIs(options['close_for'], runtime_type.return_value.close_request)
            self.assertIs(options['submit'], client_type.return_value.submit)
            dispatcher_type.return_value.start.assert_not_called()
            client_type.return_value.open_session.assert_not_called()

    def test_storage_failure_never_falls_back_to_a_local_directory(self):
        configuration = self.load()
        with patch('video_analysis.result_spool.ResultSpool', side_effect=OSError('fixture storage offline')) as spool:
            with self.assertRaises(OSError):
                create_delivery(configuration)
            spool.assert_called_once_with('/data/nfs_storage/hxjm_datas/result-spool')

    def test_explicit_disposable_spool_override_does_not_change_default_policy(self):
        value = fixture()
        value.update(spool_dir=str(Path(self.temporary.name) / 'explicit-spool'),
                     batch_size=8, queue_size=16, flush_interval_seconds=0.1, timeout_seconds=2)
        configuration = self.load(value)
        self.assertEqual(configuration['spool_dir'], value['spool_dir'])
        self.assertFalse(Path(value['spool_dir']).exists())


if __name__ == '__main__':
    unittest.main()
