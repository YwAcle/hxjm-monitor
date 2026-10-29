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

from video_analysis.business_client import BusinessUnavailable
from video_analysis.sample_pipeline import FirstObservedPerson, LocalSamplePipeline, ReIDFeatureClient


def identifier():
    return str(uuid.uuid4())


class FakeClient:
    def __init__(self):
        self.calls = []
        self.done = threading.Event()
        self.sample_payloads = []
        self.feature_payloads = []
        self.task_payloads = []
        self.fail_feature_once = False

    def get(self, path, parameters=None):
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
        assert len(payload['feature_ids']) == 1
        return {'state': 'succeeded'}


class FakeExtractor:
    def definition(self):
        return {'feature_space_id': 'test-space', 'dimensions': 3}

    def extract(self, image, metadata, bbox=None):
        return {'feature_space_id': 'test-space', 'embedding_dim': 3,
                'normalized': True, 'embedding': [1.0, 0.0, 0.0]}


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


if __name__ == '__main__':
    unittest.main()
