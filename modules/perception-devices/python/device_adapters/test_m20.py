import json
import unittest
from unittest.mock import Mock
from .m20 import M20Operations
from .m20_protocol import build_json_message


class M20Test(unittest.TestCase):
    def test_known_protocol_commands_and_no_automatic_retry(self):
        transport = Mock()
        transport.send_request.return_value = {'PatrolDevice': {'Items': {'ErrorCode': 0}}}
        device = M20Operations('test-device', transport)
        for operation, expected in [('localization.get', 1007), ('navigation.status', 1007),
                                    ('perception.status', 2002), ('posture.stand', 2),
                                    ('posture.sit', 2), ('navigation.cancel', 1004)]:
            result = device.execute(operation, task_ref='test-task')
            self.assertEqual(expected, json.loads(transport.send_request.call_args.args[0])['PatrolDevice']['Type'])
            self.assertEqual('acknowledged', result['state'])
            self.assertFalse(result['physical_completion_confirmed'])
        device.execute('navigation.submit', dict(x=1, y=2, z=0, yaw=.5))
        items = json.loads(transport.send_request.call_args.args[0])['PatrolDevice']['Items']
        self.assertEqual((1, 2, 0), (items['PosX'], items['PosY'], items['Value']))
        transport.reset_mock()
        transport.send_request.return_value = None
        self.assertEqual('unknown', device.execute('navigation.cancel')['state'])
        transport.send_request.assert_called_once()
        with self.assertRaises(ValueError):
            device.execute('navigation.submit', {'bbox': [0, 0, 1, 1]})

    def test_aos_binary_header_matches_original_wire_format(self):
        packet = build_json_message('{}', 17)
        self.assertEqual(bytes.fromhex('eb91eb90'), packet[:4])
        self.assertEqual(2, int.from_bytes(packet[4:6], 'little'))
        self.assertEqual(17, int.from_bytes(packet[6:8], 'little'))
        self.assertEqual(b'{}', packet[16:])
