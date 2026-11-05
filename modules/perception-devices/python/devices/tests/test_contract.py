import unittest
from devices import DeviceFeedback


class DeviceContractTests(unittest.TestCase):
    def test_feedback_uses_existing_fenced_completion(self):
        output = dict(result_type='device.action', schema_version='1',
                      producer_result_key='action:1', payload={'completed': True})
        body = DeviceFeedback('task', 'run', 'succeeded', (output,)).completion(
            expected_revision=3, execution_token='token')
        self.assertEqual(body, dict(task_id='task', run_id='run', expected_revision=3,
                                   execution_token='token', outputs=[output]))
        failed = DeviceFeedback('task', 'run', 'failed', error_code='DEVICE_OFFLINE')
        self.assertEqual(failed.completion(expected_revision=3, execution_token='token')['error_code'],
                         'DEVICE_OFFLINE')

    def test_running_or_invalid_feedback_cannot_complete_task(self):
        for feedback in (DeviceFeedback('t', 'r', 'running'),
                         DeviceFeedback('t', 'r', 'succeeded'),
                         DeviceFeedback('t', 'r', 'failed')):
            with self.assertRaises(ValueError):
                feedback.completion(expected_revision=1, execution_token='token')
