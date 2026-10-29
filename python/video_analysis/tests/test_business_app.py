import importlib.util
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch


HAS_FASTAPI = importlib.util.find_spec('fastapi') is not None


@unittest.skipUnless(HAS_FASTAPI, 'FastAPI is required for application lifecycle tests')
class BusinessAppTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from video_analysis import app
        self.module = app
        recording = patch.object(self.module, 'RECORDING_ENABLED', False)
        recording.start()
        self.addCleanup(recording.stop)
        self.application = SimpleNamespace(state=SimpleNamespace())
        self.events = []
        self.analyzer = Mock()
        self.analyzer.start = AsyncMock(side_effect=lambda: self.events.append('analyzer.start'))
        self.analyzer.stop = AsyncMock(side_effect=lambda: self.events.append('analyzer.stop'))
        self.analyzer.health.return_value = {'status': 'ok'}
        self.delivery = Mock()
        self.delivery.start.side_effect = lambda: self.events.append('delivery.start')
        self.delivery.stop.side_effect = lambda: self.events.append('delivery.stop') or True
        self.delivery.status.return_value = {'state': 'running', 'pending_batches': 2}
        self.hub = Mock()
        self.hub.start.side_effect = lambda: self.events.append('hub.start')
        self.hub.stop.side_effect = lambda: self.events.append('hub.stop')

    async def test_disabled_delivery_preserves_legacy_analyzer_and_health(self):
        with patch.object(self.module, 'SOURCE_IDS', {}), \
                patch.object(self.module, 'load_business_config', return_value=None), \
                patch.object(self.module, 'Analyzer', return_value=self.analyzer) as analyzer_type, \
                patch('video_analysis.business_runtime.create_delivery') as factory:
            async with self.module.lifespan(self.application):
                health = await self.module.health(SimpleNamespace(app=self.application))
                self.assertEqual(health, {'status': 'ok'})
                self.assertIsNone(self.application.state.result_delivery)
            analyzer_type.assert_called_once_with()
            factory.assert_not_called()
        self.assertEqual(self.events, ['analyzer.start', 'analyzer.stop'])

    async def test_enabled_delivery_owns_lifecycle_and_is_visible_in_health(self):
        source = '10000000-0000-4000-8000-000000000001'
        with patch.object(self.module, 'CAMERAS', {'camera_1': 'rtsp://fixture.invalid/camera_1'}), \
                patch.object(self.module, 'SOURCE_IDS', {'camera_1': source}), \
                patch.object(self.module, 'load_business_config', return_value={'enabled': 'fixture'}), \
                patch.object(self.module, 'Analyzer', return_value=self.analyzer) as analyzer_type, \
                patch('video_analysis.business_runtime.create_delivery', return_value=self.delivery), \
                patch('frame_hub.hub.FrameHub', return_value=self.hub) as hub_type:
            async with self.module.lifespan(self.application):
                self.assertEqual(self.events, ['delivery.start', 'hub.start', 'analyzer.start'])
                health = await self.module.health(SimpleNamespace(app=self.application))
                self.assertEqual(health['result_delivery'], {'state': 'running', 'pending_batches': 2})
                analyzer_type.assert_called_once_with(frame_hub=self.hub, source_ids={'camera_1': source},
                                                       result_sink=self.delivery)
                hub_type.assert_called_once_with({source: 'rtsp://fixture.invalid/camera_1'})
        self.assertEqual(self.events, ['delivery.start', 'hub.start', 'analyzer.start',
                                       'analyzer.stop', 'hub.stop', 'delivery.stop'])

    async def test_analyzer_start_failure_stops_delivery_and_capture(self):
        source = '10000000-0000-4000-8000-000000000001'
        self.analyzer.start.side_effect = RuntimeError('fixture start failure')
        with patch.object(self.module, 'CAMERAS', {'camera_1': 'rtsp://fixture.invalid/camera_1'}), \
                patch.object(self.module, 'SOURCE_IDS', {'camera_1': source}), \
                patch.object(self.module, 'load_business_config', return_value={'enabled': 'fixture'}), \
                patch.object(self.module, 'Analyzer', return_value=self.analyzer), \
                patch('video_analysis.business_runtime.create_delivery', return_value=self.delivery), \
                patch('frame_hub.hub.FrameHub', return_value=self.hub):
            with self.assertRaisesRegex(RuntimeError, 'fixture start failure'):
                async with self.module.lifespan(self.application):
                    self.fail('A failed startup must not serve requests')
        self.assertEqual(self.events, ['delivery.start', 'hub.start', 'analyzer.stop',
                                       'hub.stop', 'delivery.stop'])

    async def test_sample_worker_waits_for_save_confirmation_and_drains_after_delivery(self):
        worker = Mock()
        worker.start.side_effect = lambda: self.events.append('samples.start')
        worker.stop.side_effect = lambda: self.events.append('samples.stop') or True
        worker.status.return_value = {'completed': 1}
        options = {'feature_url': 'http://127.0.0.1:28024', 'threshold': 0.88,
                   'instance_id': '10000000-0000-4000-8000-000000000001'}
        with patch.object(self.module, 'SOURCE_IDS', {}), \
                patch.object(self.module, 'load_business_config', return_value={'sample_pipeline': options}), \
                patch.object(self.module, 'Analyzer', return_value=self.analyzer) as analyzer_type, \
                patch('video_analysis.business_runtime.create_delivery', return_value=self.delivery), \
                patch('video_analysis.sample_pipeline.LocalSamplePipeline', return_value=worker) as factory:
            async with self.module.lifespan(self.application):
                self.assertIs(self.delivery.on_confirmed, worker.confirmed)
                self.assertIs(analyzer_type.call_args.kwargs['sample_pipeline'], worker)
                factory.assert_called_once_with(self.delivery.business_client, **options, finish_tasks=True)
                health = await self.module.health(SimpleNamespace(app=self.application))
                self.assertEqual(health['sample_pipeline'], {'completed': 1})
        self.assertEqual(self.events, ['samples.start', 'delivery.start', 'analyzer.start',
                                      'analyzer.stop', 'delivery.stop', 'samples.stop'])

    async def test_recording_requires_source_mappings_before_startup(self):
        with patch.object(self.module, 'RECORDING_ENABLED', True), \
                patch.object(self.module, 'SOURCE_IDS', {}), \
                patch.object(self.module, 'load_business_config', return_value=None), \
                patch.object(self.module, 'Analyzer') as analyzer_type:
            with self.assertRaisesRegex(ValueError, 'SOURCE_IDS'):
                async with self.module.lifespan(self.application):
                    self.fail('Recording cannot start without stable sources')
            analyzer_type.assert_not_called()

    async def test_recording_registration_drains_after_the_last_segment_is_closed(self):
        source = '10000000-0000-4000-8000-000000000001'
        registration = Mock()
        registration.start.side_effect = lambda: self.events.append('recording_delivery.start')
        registration.stop.side_effect = lambda: self.events.append('recording_delivery.stop') or True
        registration.status.return_value = {'state': 'running'}
        with patch.object(self.module, 'RECORDING_ENABLED', True), \
                patch.object(self.module, 'RECORDING_RETENTION_SECONDS', 604800), \
                patch.object(self.module, 'CAMERAS', {'camera_1': 'rtsp://fixture.invalid/camera_1'}), \
                patch.object(self.module, 'SOURCE_IDS', {'camera_1': source}), \
                patch.object(self.module, 'load_business_config', return_value={'enabled': 'fixture'}), \
                patch.object(self.module, 'Analyzer', return_value=self.analyzer), \
                patch('video_analysis.business_runtime.create_delivery', return_value=self.delivery), \
                patch('video_analysis.recording_delivery.RecordingDelivery', return_value=registration) as delivery_type, \
                patch('frame_hub.recording.BackgroundRecorder') as recorder_type, \
                patch('frame_hub.hub.FrameHub', return_value=self.hub) as hub_type:
            async with self.module.lifespan(self.application):
                factory = hub_type.call_args.kwargs['recorder_factory']
                factory(source)
                self.assertIs(recorder_type.call_args.kwargs['on_segment'], registration)
                delivery_type.assert_called_once_with(self.delivery.business_client, self.delivery.business_runtime,
                    storage_root=self.module.RECORDING_ROOT, source_ids={source})
                health = await self.module.health(SimpleNamespace(app=self.application))
                self.assertEqual(health['recording_delivery'], {'state': 'running'})
        self.assertEqual(self.events, ['delivery.start', 'recording_delivery.start', 'hub.start', 'analyzer.start',
                                       'analyzer.stop', 'hub.stop', 'recording_delivery.stop', 'delivery.stop'])

    async def test_invalid_configuration_fails_before_capture_or_models_start(self):
        with patch.object(self.module, 'load_business_config', side_effect=ValueError('fixture invalid config')), \
                patch.object(self.module, 'Analyzer') as analyzer_type:
            with self.assertRaisesRegex(ValueError, 'fixture invalid config'):
                async with self.module.lifespan(self.application):
                    self.fail('Invalid configuration must not enable delivery')
            analyzer_type.assert_not_called()


if __name__ == '__main__':
    unittest.main()
