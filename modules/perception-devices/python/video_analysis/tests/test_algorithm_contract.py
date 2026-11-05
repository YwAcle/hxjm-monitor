"""Same-mode extension must not require a worker/scheduler branch or load a model."""
import unittest
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from unittest.mock import patch
from video_analysis.algorithms import ALGORITHMS, AlgorithmSpec, algorithm_spec
from video_analysis.analyzer import Analyzer
from video_analysis.detector_adapter import PersonDetector


class AlgorithmContractTests(unittest.TestCase):
    def test_new_tracker_uses_existing_scheduling_semantics(self):
        spec = AlgorithmSpec('person.tracking', 'some.adapter:Tracker', True, '0.05')
        with patch.dict(ALGORITHMS, {'another_tracker': spec}):
            analyzer = Analyzer(algorithm='another_tracker', cameras={'camera_1': 'rtsp://fake'})
            self.assertIs(analyzer.algorithm_spec, spec)
            self.assertTrue(analyzer.algorithm_spec.tracking)
            self.assertEqual(spec.describe('another_tracker')['capability_code'], 'person.tracking')
        with self.assertRaises(ValueError):
            algorithm_spec('another_tracker')

    def test_detector_adapts_native_call_without_tracking(self):
        with patch('video_analysis.detector_adapter.initialize_detector') as initialize, \
             patch('video_analysis.detector_adapter.detect_people', return_value=([], 1)) as detect:
            adapter = algorithm_spec('deepsort').create()
            self.assertIsInstance(adapter, PersonDetector)
            frame = object()
            self.assertEqual(adapter.infer(frame, {'camera_id': 'camera_1'}), ([], 1))
            initialize.assert_called_once_with()
            detect.assert_called_once_with(frame)
            self.assertFalse(algorithm_spec('deepsort').tracking)

    def test_descriptors_match_shared_schema_without_model_imports(self):
        schema = json.loads((Path(__file__).parents[5]/'contracts/capability-v1/algorithm.schema.json').read_text())
        validator = Draft202012Validator(schema)
        for name, spec in ALGORITHMS.items():
            validator.validate(spec.describe(name))
