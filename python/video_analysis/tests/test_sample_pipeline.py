import hashlib
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import uuid

import numpy as np

from video_analysis.business_client import BusinessRequestError, BusinessUnavailable
from video_analysis.sample_pipeline import (FirstObservedPerson, LocalSamplePipeline,
                                            ReIDFeatureClient, TextReIDFeatureClient)


def identifier():
    return str(uuid.uuid4())


class FakeClient:
    def __init__(self):
        self.calls = []
        self.paths = []
        self.parameters = []
        self.done = threading.Event()
        self.sample_payloads = []
        self.feature_payloads = []
        self.finish_payloads = []
        self.task_payloads = []
        self.fail_feature_once = False
        self.running_task = None

    def get(self, path, parameters=None):
        self.paths.append(path)
        self.parameters.append((path, parameters))
        return {'items': []}

    def upload_image(self, payload, image):
        self.calls.append('asset')
        assert isinstance(image, bytes) and image[:2] == b'\xff\xd8'
        return {'asset_id': payload['asset_id'],
                'expires_at': (datetime.fromisoformat(payload['occurred_at']) + timedelta(days=7)).isoformat()}

    def register_sample(self, payload):
        self.calls.append('sample')
        self.sample_payloads.append(dict(payload))
        return {'sample_id': payload['sample_id']}

    def register_feature_space(self, payload):
        self.calls.append('space')
        return {'feature_space_id': payload['feature_space_id']}

    def create_task(self, payload):
        self.calls.append('task')
        self.task_payloads.append(dict(payload))
        assert payload['task_mode'] == 'once' and payload['input']['kind'] == 'image'
        if self.running_task is not None:
            return dict(self.running_task, duplicate=True)
        return {'task_id': identifier(), 'revision': 1, 'state': 'pending'}

    def start_task(self, payload):
        self.calls.append('start')
        return {'task_id': payload['task_id'], 'run_id': identifier(), 'revision': 2, 'state': 'running'}

    def register_feature(self, payload):
        self.calls.append('feature')
        self.feature_payloads.append(dict(payload))
        if self.fail_feature_once:
            self.fail_feature_once = False
            raise BusinessUnavailable()
        return {'feature_id': payload['feature_id']}

    def associate_identity(self, payload):
        self.calls.append('identity')
        self.done.set()
        return {'identity_id': identifier()}

    def finish_task(self, payload):
        self.calls.append('finish')
        self.finish_payloads.append(dict(payload))
        assert len(payload['feature_ids']) == 1
        return {'state': 'succeeded'}


class FakeExtractor:
    def definition(self):
        return {'feature_space_id': 'test-space', 'dimensions': 3}

    def extract(self, image, metadata, bbox=None):
        return {'feature_space_id': 'test-space', 'embedding_dim': 3,
                'normalized': True, 'embedding': [1.0, 0.0, 0.0]}


class FakeTextExtractor(FakeExtractor):
    def definition(self):
        return {'feature_space_id': 'text-space', 'dimensions': 3}

    def extract(self, image, metadata, bbox=None):
        return {'feature_space_id': 'text-space', 'embedding_dim': 3,
                'normalized': True, 'embedding': [0.0, 1.0, 0.0]}


class FlakyTextExtractor(FakeTextExtractor):
    def __init__(self):
        self.failures = 1

    def extract(self, image, metadata, bbox=None):
        if self.failures:
            self.failures -= 1
            raise BusinessUnavailable()
        return super().extract(image, metadata, bbox)


class SamplePipelineTests(unittest.TestCase):
    def fixture(self, queue_size=2):
        client = FakeClient()
        pipeline = LocalSamplePipeline(client, threshold=0.88, instance_id=identifier(),
                                       extractor=FakeExtractor(), queue_size=queue_size,
                                       finish_tasks=True)
        frame = SimpleNamespace(frame=np.zeros((30, 20, 3), dtype=np.uint8),
                                frame_ts_ms=int(time.time() * 1000), source_width=20, source_height=30,
                                public_frame_ref=SimpleNamespace(source_id=identifier(),
                                                                 stream_session_id=identifier(), frame_id=identifier()))
        detection = {'label': 'person', 'track_id': 7, 'bbox': [0.1, 0.1, 0.8, 0.9],
                     'confidence': 0.9, 'is_prediction': False}
        return client, pipeline, frame, detection, identifier()

    def acknowledge(self, pipeline, frame, context, *, accepted=True):
        result = identifier()
        payload = {'source_id': frame.public_frame_ref.source_id,
                   'results': [{'result_id': result, 'frame_id': frame.public_frame_ref.frame_id}]}
        response = {'accepted_result_ids': [result] if accepted else [], 'duplicate_result_ids': [],
                    'tracklets': [{'tracking_context_id': context, 'local_track_id': 7,
                                  'tracklet_id': identifier()}]}
        pipeline.confirmed(payload, response)

    def test_no_prediction_sampling_and_capacity_can_retry_after_full(self):
        client, pipeline, frame, detection, context = self.fixture(queue_size=1)
        self.assertEqual(list(FirstObservedPerson().select([dict(detection, is_prediction=True)])), [])
        self.assertEqual(pipeline.offer(frame, [detection], tracking_context_id=context), 1)
        self.assertEqual(pipeline.offer(frame, [dict(detection, track_id=8)], tracking_context_id=context), 0)
        self.assertEqual(pipeline.offer(frame, [detection], tracking_context_id=context), 0)
        self.assertEqual(client.calls, [])
        self.assertEqual(pipeline.status()['awaiting_frame_confirmation'], 1)
        self.assertFalse(np.shares_memory(next(iter(pipeline._jobs.values())).crop, frame.frame))

    def test_waits_for_accepted_frame_before_sample_and_feature_registration(self):
        client, pipeline, frame, detection, context = self.fixture()
        pipeline.offer(frame, [detection], tracking_context_id=context)
        pipeline.start()
        try:
            self.acknowledge(pipeline, frame, context, accepted=False)
            self.assertFalse(client.done.wait(0.15))
            self.assertNotIn('asset', client.calls)
            self.acknowledge(pipeline, frame, context)
            self.assertTrue(client.done.wait(3))
        finally:
            pipeline.stop()
        self.assertLess(client.calls.index('asset'), client.calls.index('sample'))
        self.assertLess(client.calls.index('feature'), client.calls.index('identity'))
        self.assertIn('finish', client.calls)
        self.assertEqual(client.sample_payloads[0]['input_frame_id'], frame.public_frame_ref.frame_id)
        self.assertEqual(pipeline.status()['completed_samples'], 1)
        self.assertEqual(pipeline.offer(frame, [detection], tracking_context_id=context), 0)
        self.assertEqual(pipeline.offer(frame, [detection], tracking_context_id=identifier()), 0)

    def test_local_track_number_can_be_reused_in_new_tracking_context(self):
        _, pipeline, frame, detection, context = self.fixture()
        self.assertEqual(pipeline.offer(frame, [detection], tracking_context_id=context), 1)
        self.assertEqual(pipeline.offer(frame, [detection], tracking_context_id=identifier()), 1)

    def test_dependency_retry_reuses_payload_and_does_not_upload_twice(self):
        client, pipeline, frame, detection, context = self.fixture()
        pipeline.offer(frame, [detection], tracking_context_id=context)
        self.acknowledge(pipeline, frame, context)
        job = next(iter(pipeline._jobs.values()))
        client.fail_feature_once = True
        with self.assertRaises(BusinessUnavailable):
            pipeline._process(job)
        pipeline._process(job)
        self.assertEqual(client.calls.count('asset'), 1)
        self.assertEqual(client.calls.count('sample'), 1)
        self.assertEqual(client.calls.count('task'), 1)
        self.assertEqual(client.feature_payloads[0], client.feature_payloads[1])

    def test_enrollment_feature_keeps_identity_and_permanent_expiry(self):
        client, pipeline, _, _, _ = self.fixture()
        client.image_content = Mock(return_value=b'fixture-image')
        row = {'sample_id': identifier(), 'asset_id': identifier(),
               'identity_id': identifier(), 'occurred_at': datetime.now(timezone.utc).isoformat(),
               'expires_at': None}
        pipeline._enrollment(row)
        feature = client.feature_payloads[0]
        self.assertEqual(feature['sample_id'], row['sample_id'])
        self.assertEqual(feature['identity_id'], row['identity_id'])
        self.assertIsNone(feature['expires_at'])
        self.assertNotIn('identity', client.calls)
        # A second feature space must not reuse the task key of another one.
        self.assertIn(':space:test-space:', client.task_payloads[0]['business_key'])

    def test_history_sample_keeps_tracklet_without_identity_association(self):
        client, pipeline, _, _, _ = self.fixture()
        client.image_content = Mock(return_value=b'fixture-image')
        row = {'sample_id': identifier(), 'asset_id': identifier(),
               'tracklet_id': identifier(), 'identity_id': None,
               'occurred_at': datetime.now(timezone.utc).isoformat(),
               'expires_at': (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()}
        pipeline._history_sample(row)
        feature = client.feature_payloads[0]
        self.assertEqual(feature['sample_id'], row['sample_id'])
        self.assertEqual(feature['tracklet_id'], row['tracklet_id'])
        self.assertIsNone(feature['identity_id'])
        self.assertEqual(feature['expires_at'], row['expires_at'])
        self.assertEqual(feature['contributions'], [{'sample_id': row['sample_id']}])
        # History text features never create a CLIP-ReID identity assignment.
        self.assertNotIn('identity', client.calls)
        self.assertIn(':space:test-space:', client.task_payloads[0]['business_key'])

    def test_live_pipeline_writes_image_and_text_features_in_one_pass(self):
        client = FakeClient()
        pipeline = LocalSamplePipeline(client, threshold=0.88, instance_id=identifier(),
                                       extractor=FakeExtractor(), text_extractor=FakeTextExtractor(),
                                       queue_size=2, finish_tasks=True)
        frame = SimpleNamespace(frame=np.zeros((30, 20, 3), dtype=np.uint8),
                                frame_ts_ms=int(time.time() * 1000), source_width=20, source_height=30,
                                public_frame_ref=SimpleNamespace(source_id=identifier(),
                                                                 stream_session_id=identifier(),
                                                                 frame_id=identifier()))
        detection = {'label': 'person', 'track_id': 7, 'bbox': [0.1, 0.1, 0.8, 0.9],
                     'confidence': 0.9, 'is_prediction': False}
        context = identifier()
        pipeline.offer(frame, [detection], tracking_context_id=context)
        self.acknowledge(pipeline, frame, context)
        job = next(iter(pipeline._jobs.values()))
        pipeline._process(job)

        features = {payload['feature_space_id']: payload for payload in client.feature_payloads}
        self.assertEqual(set(features), {'test-space', 'text-space'})
        self.assertNotEqual(features['test-space']['feature_id'],
                            features['text-space']['feature_id'])
        for payload in features.values():
            self.assertEqual(payload['sample_id'], job.sample_id)
            self.assertEqual(payload['tracklet_id'], job.tracklet_id)
        self.assertIsNone(features['text-space']['identity_id'])
        # Only the CLIP-ReID space may assign an identity; finishing is per-space.
        self.assertEqual(client.calls.count('identity'), 1)
        self.assertEqual(client.calls.count('finish'), 2)
        self.assertEqual(len(client.task_payloads), 2)
        self.assertNotEqual(client.task_payloads[0]['business_key'],
                            client.task_payloads[1]['business_key'])
        self.assertEqual(pipeline.status()['feature_spaces'],
                         {'image': 'test-space', 'text': 'text-space'})

    def test_text_space_retry_keeps_the_already_written_image_feature(self):
        client = FakeClient()
        pipeline = LocalSamplePipeline(client, threshold=0.88, instance_id=identifier(),
                                       extractor=FakeExtractor(),
                                       text_extractor=FlakyTextExtractor(), finish_tasks=True)
        frame = SimpleNamespace(frame=np.zeros((30, 20, 3), dtype=np.uint8),
                                frame_ts_ms=int(time.time() * 1000), source_width=20, source_height=30,
                                public_frame_ref=SimpleNamespace(source_id=identifier(),
                                                                 stream_session_id=identifier(),
                                                                 frame_id=identifier()))
        detection = {'label': 'person', 'track_id': 7, 'bbox': [0.1, 0.1, 0.8, 0.9],
                     'confidence': 0.9, 'is_prediction': False}
        context = identifier()
        pipeline.offer(frame, [detection], tracking_context_id=context)
        self.acknowledge(pipeline, frame, context)
        job = next(iter(pipeline._jobs.values()))
        with self.assertRaises(BusinessUnavailable):
            pipeline._process(job)
        self.assertEqual([payload['feature_space_id'] for payload in client.feature_payloads],
                         ['test-space'])
        pipeline._process(job)
        self.assertEqual([payload['feature_space_id'] for payload in client.feature_payloads],
                         ['test-space', 'text-space'])
        self.assertEqual(client.calls.count('asset'), 1)
        self.assertEqual(client.calls.count('sample'), 1)
        self.assertEqual(client.calls.count('finish'), 2)

    def test_text_lane_enrollment_feature_keeps_identity_without_association(self):
        client = FakeClient()
        pipeline = LocalSamplePipeline(client, threshold=0.88, instance_id=identifier(),
                                       extractor=FakeExtractor(), text_extractor=FakeTextExtractor())
        client.image_content = Mock(return_value=b'fixture-image')
        row = {'sample_id': identifier(), 'asset_id': identifier(),
               'identity_id': identifier(), 'occurred_at': datetime.now(timezone.utc).isoformat(),
               'expires_at': None}
        text_encoder = next(encoder for encoder in pipeline._encoders if encoder.role == 'text')
        pipeline._enrollment(row, text_encoder)
        feature = client.feature_payloads[0]
        self.assertEqual(feature['feature_space_id'], 'text-space')
        self.assertEqual(feature['identity_id'], row['identity_id'])
        self.assertNotIn('identity', client.calls)

    def test_live_dual_space_polls_enrollment_and_history(self):
        client = FakeClient()
        pipeline = LocalSamplePipeline(client, threshold=0.88, instance_id=identifier(),
                                       extractor=FakeExtractor(), text_extractor=FakeTextExtractor(),
                                       poll_interval_seconds=0.05)
        pipeline.start()
        try:
            deadline = time.time() + 2
            while not any(path == '/samples/pending' and parameters.get('feature_space_id') == 'text-space'
                          and parameters.get('purpose') == 'history'
                          for path, parameters in client.parameters):
                if time.time() > deadline:
                    self.fail('text history lane did not poll')
                time.sleep(0.01)
        finally:
            self.assertTrue(pipeline.stop())
        pending = {(parameters['purpose'], parameters['feature_space_id'])
                   for path, parameters in client.parameters if path == '/samples/pending'}
        self.assertIn(('enrollment', 'test-space'), pending)
        self.assertIn(('enrollment', 'text-space'), pending)
        self.assertIn(('history', 'text-space'), pending)

    def test_invalid_sample_purpose_is_rejected(self):
        for purpose in ('query', '', 'History'):
            with self.subTest(purpose=purpose), self.assertRaises(ValueError):
                LocalSamplePipeline(FakeClient(), threshold=0.88, instance_id=identifier(),
                                    extractor=FakeExtractor(), sample_purpose=purpose)

    def test_restarted_worker_resumes_an_already_started_task(self):
        client, pipeline, _, _, _ = self.fixture()
        client.image_content = Mock(return_value=b'fixture-image')
        client.running_task = {'task_id': identifier(), 'run_id': identifier(),
                               'state': 'running', 'revision': 2}
        row = {'sample_id': identifier(), 'asset_id': identifier(), 'identity_id': identifier(),
               'occurred_at': datetime.now(timezone.utc).isoformat(), 'expires_at': None}
        pipeline._enrollment(row)
        self.assertNotIn('start', client.calls)
        self.assertEqual(client.feature_payloads[0]['run_id'], client.running_task['run_id'])
        self.assertEqual(client.finish_payloads[0]['run_id'], client.running_task['run_id'])

    def test_same_sample_with_new_instance_creates_distinct_business_task(self):
        client, pipeline, _, _, _ = self.fixture()
        client.image_content = Mock(return_value=b'fixture-image')
        row = {'sample_id': identifier(), 'asset_id': identifier(), 'identity_id': identifier(),
               'occurred_at': datetime.now(timezone.utc).isoformat(), 'expires_at': None}
        pipeline._enrollment(row)
        replacement = LocalSamplePipeline(client, threshold=0.88, instance_id=identifier(),
                                          extractor=FakeExtractor())
        replacement._enrollment(row)
        first, second = [payload['business_key'] for payload in client.task_payloads]
        self.assertNotEqual(first, second)
        self.assertIn(row['sample_id'], first)
        self.assertIn(pipeline.instance_id, first)
        self.assertIn(replacement.instance_id, second)

    def test_query_multiple_people_waits_without_search_or_identity(self):
        client, pipeline, _, _, _ = self.fixture()
        client.image_content = Mock(return_value=b'fixture-image')
        pipeline.extractor.detect = Mock(return_value={'image_width': 100, 'image_height': 200,
            'candidates': [{'candidate_id': '1', 'bbox': [0, 0, 30, 100], 'confidence': 0.9},
                           {'candidate_id': '2', 'bbox': [40, 0, 80, 100], 'confidence': 0.8}]})
        client.post = Mock(return_value={'state': 'waiting_input', 'revision': 2})
        row = {'query_id': identifier(), 'input_asset_id': identifier(), 'revision': 1,
               'object_type': 'person', 'expires_at': (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()}
        pipeline._query(row)
        self.assertEqual(len(client.sample_payloads), 2)
        self.assertTrue(all(p['purpose'] == 'query' for p in client.sample_payloads))
        self.assertEqual(client.post.call_args.args[0], '/queries/candidates')
        self.assertNotIn('feature', client.calls)
        self.assertNotIn('identity', client.calls)

    def test_query_selected_person_extracts_selected_crop_and_searches(self):
        client, pipeline, _, _, _ = self.fixture()
        client.image_content = Mock(return_value=b'fixture-image')
        selected_sample = identifier()
        bbox = {'schema_version': '1', 'xyxy': [0.1, 0.2, 0.8, 0.9],
                'source_width': 100, 'source_height': 200}
        current = {'state': 'pending', 'revision': 3, 'input_sample_id': selected_sample,
                   'candidates': [{'sample_id': selected_sample, 'bbox_json': json.dumps(bbox)}]}
        client.get = Mock(return_value=current)
        client.post = Mock(return_value={'state': 'succeeded'})
        pipeline.extractor.extract = Mock(wraps=pipeline.extractor.extract)
        row = {'query_id': identifier(), 'input_asset_id': identifier(), 'revision': 3,
               'input_sample_id': selected_sample, 'object_type': 'person',
               'expires_at': (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()}
        pipeline._query(row)
        self.assertEqual(pipeline.extractor.extract.call_args.kwargs['bbox'], [10, 40, 80, 180])
        self.assertEqual(client.feature_payloads[0]['sample_id'], selected_sample)
        self.assertEqual(client.post.call_args.args[0], '/search')
        self.assertEqual(client.post.call_args.args[1]['expected_revision'], 3)
        self.assertEqual(client.post.call_args.args[1]['feature_id'], client.feature_payloads[0]['feature_id'])
        self.assertIn('finish', client.calls)
        self.assertNotIn('identity', client.calls)

    def test_query_without_person_finishes_without_feature_or_search(self):
        client, pipeline, _, _, _ = self.fixture()
        client.image_content = Mock(return_value=b'fixture-image')
        pipeline.extractor.detect = Mock(return_value={'image_width': 100, 'image_height': 200,
                                                       'candidates': []})
        client.post = Mock(return_value={'state': 'succeeded', 'revision': 2})
        row = {'query_id': identifier(), 'input_asset_id': identifier(), 'revision': 1,
               'object_type': 'person', 'expires_at': (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()}
        pipeline._query(row)
        self.assertEqual(client.post.call_args.args[0], '/queries/candidates')
        self.assertEqual(client.post.call_args.args[1]['candidates'], [])
        self.assertEqual(client.feature_payloads, [])
        self.assertEqual(client.sample_payloads, [])

    def test_extractor_definition_requires_exact_hash(self):
        client = ReIDFeatureClient('http://localhost:28024')
        text = json.dumps({'weights': 'fixture', 'preprocess': 'rgb_resize_tensor_v1'})
        client._request = Mock(return_value={'ready': True, 'feature_space_id': 'fixture',
            'definition_text': text, 'definition_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'embedding_dim': 3})
        self.assertEqual(client.definition()['definition_text'], text)

    def test_text_extractor_uses_the_text_health_block_and_endpoint(self):
        client = TextReIDFeatureClient('http://localhost:28024')
        text = json.dumps({'schema': 'hxjm.feature-space.v1'})
        health = {'ready': True, 'text_reid': {
            'ready': True, 'alignment_verified': True, 'feature_space_id': 'fs-fixture',
            'embedding_dim': 512, 'definition_text': text,
            'definition_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'definition_version': 'canonical_json_v1'}}
        requests = []
        client._request = Mock(side_effect=lambda path, *args: (
            requests.append((path, args)), health if path == '/health'
            else {'feature_space_id': 'fs-fixture', 'embedding_dim': 512,
                  'normalized': True, 'embedding': [1.0]})[1])
        definition = client.definition()
        self.assertEqual(definition['feature_space_id'], 'fs-fixture')
        self.assertEqual(definition['feature_kind'], 'text_reid')
        self.assertEqual(definition['dimensions'], 512)
        client.extract(b'\xff\xd8image', {'request_id': identifier()})
        self.assertEqual(requests[0][0], '/health')
        self.assertEqual(requests[1][0], '/v1/reid/text-reid-image-features')

    def test_text_extractor_rejects_unready_or_unaligned_health(self):
        client = TextReIDFeatureClient('http://localhost:28024')
        text = json.dumps({'schema': 'hxjm.feature-space.v1'})
        base = {'ready': True, 'alignment_verified': True, 'feature_space_id': 'fs-fixture',
                'embedding_dim': 512, 'definition_text': text,
                'definition_sha256': hashlib.sha256(text.encode()).hexdigest()}
        for changes in ({'ready': False}, {'alignment_verified': False},
                        {'definition_sha256': '0' * 64}, {'embedding_dim': 0},
                        {'feature_space_id': ''}):
            client._request = Mock(return_value={'text_reid': dict(base, **changes)})
            with self.subTest(changes=changes), \
                    self.assertRaises((BusinessRequestError, BusinessUnavailable)):
                client.definition()
        client._request = Mock(return_value={'ready': True})
        with self.assertRaises(BusinessUnavailable):
            client.definition()

    def test_enrollment_only_pipeline_ignores_live_frames_and_queries(self):
        client = FakeClient()
        pipeline = LocalSamplePipeline(client, threshold=0.88, instance_id=identifier(),
                                       extractor=FakeExtractor(), poll_interval_seconds=0.05,
                                       enrollment_only=True)
        frame = SimpleNamespace(frame=np.zeros((30, 20, 3), dtype=np.uint8),
                                frame_ts_ms=int(time.time() * 1000), source_width=20, source_height=30,
                                public_frame_ref=SimpleNamespace(source_id=identifier(),
                                                                 stream_session_id=identifier(), frame_id=identifier()))
        detection = {'label': 'person', 'track_id': 7, 'bbox': [0.1, 0.1, 0.8, 0.9],
                     'confidence': 0.9, 'is_prediction': False}
        context = identifier()
        self.assertEqual(pipeline.offer(frame, [detection], tracking_context_id=context), 0)
        pipeline.confirmed({'source_id': frame.public_frame_ref.source_id, 'results': []},
                           {'accepted_result_ids': [], 'duplicate_result_ids': [],
                            'tracklets': [{'tracking_context_id': context, 'local_track_id': 7,
                                           'tracklet_id': identifier()}]})
        pipeline.start()
        deadline = time.time() + 2
        while '/samples/pending' not in client.paths and time.time() < deadline:
            time.sleep(0.01)
        self.assertTrue(pipeline.stop())
        self.assertIn('/samples/pending', client.paths)
        self.assertNotIn('/queries/pending', client.paths)
        self.assertIsNone(pipeline._thread)
        self.assertEqual(pipeline.status()['mode'], 'enrollment_only')
        self.assertEqual(pipeline.status()['queued_samples'], 0)

    def test_history_worker_polls_history_samples_in_the_text_space(self):
        client = FakeClient()
        pipeline = LocalSamplePipeline(client, threshold=0.88, instance_id=identifier(),
                                       extractor=FakeExtractor(), poll_interval_seconds=0.05,
                                       enrollment_only=True, sample_purpose='history')
        pipeline.start()
        deadline = time.time() + 2
        while '/samples/pending' not in client.paths and time.time() < deadline:
            time.sleep(0.01)
        self.assertTrue(pipeline.stop())
        pending = [parameters for path, parameters in client.parameters
                   if path == '/samples/pending']
        self.assertTrue(pending)
        self.assertEqual(pending[0]['purpose'], 'history')
        self.assertEqual(pending[0]['feature_space_id'], 'test-space')
        self.assertNotIn('/queries/pending', client.paths)
        self.assertEqual(pipeline.status()['sample_purpose'], 'history')
        self.assertEqual(pipeline.status()['mode'], 'history_only')


class EnrollmentWorkerConfigTests(unittest.TestCase):
    def test_requires_credentials_origin_and_canonical_instance(self):
        from video_analysis.enrollment_text_worker import config_from_env
        base = {'ENROLLMENT_TEXT_BUSINESS_URL': 'http://127.0.0.1:8080/api/v1/business',
                'ENROLLMENT_TEXT_SERVICE_ID': 'video-analysis',
                'ENROLLMENT_TEXT_SERVICE_TOKEN': 'fixture-token',
                'ENROLLMENT_TEXT_INSTANCE_ID': identifier()}
        config = config_from_env(base)
        self.assertEqual(config['feature_url'], 'http://127.0.0.1:28024')
        self.assertEqual(config['capability_code'], 'person.reidentification')
        for name, value in (('ENROLLMENT_TEXT_SERVICE_TOKEN', ''),
                            ('ENROLLMENT_TEXT_BUSINESS_URL', ''),
                            ('ENROLLMENT_TEXT_INSTANCE_ID', str(uuid.uuid4()).upper()),
                            ('ENROLLMENT_TEXT_INSTANCE_ID',
                             '00000000-0000-0000-0000-000000000000')):
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                config_from_env(dict(base, **{name: value}))

    def test_sample_purpose_defaults_to_enrollment_and_accepts_history(self):
        from video_analysis.enrollment_text_worker import build_pipeline, config_from_env
        base = {'ENROLLMENT_TEXT_BUSINESS_URL': 'http://127.0.0.1:8080/api/v1/business',
                'ENROLLMENT_TEXT_SERVICE_ID': 'video-analysis',
                'ENROLLMENT_TEXT_SERVICE_TOKEN': 'fixture-token',
                'ENROLLMENT_TEXT_INSTANCE_ID': identifier()}
        self.assertEqual(config_from_env(base)['sample_purpose'], 'enrollment')
        history = config_from_env(dict(base, ENROLLMENT_TEXT_SAMPLE_PURPOSE='history'))
        self.assertEqual(history['sample_purpose'], 'history')
        pipeline = build_pipeline(history)
        self.assertEqual(pipeline.sample_purpose, 'history')
        self.assertTrue(pipeline.enrollment_only)
        for value in ('', 'query', 'History'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                config_from_env(dict(base, ENROLLMENT_TEXT_SAMPLE_PURPOSE=value))


if __name__ == '__main__':
    unittest.main()
