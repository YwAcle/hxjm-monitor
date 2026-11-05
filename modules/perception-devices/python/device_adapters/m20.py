"""Reusable AOS operations extracted from robot-control's M20 adapter.

Commands acknowledge receipt, not physical completion. No retries or automatic
combinations: route pickup/grasp stays in the external robot process.
"""
import math
from . import m20_protocol as protocol

OPERATIONS = {
    'localization.get': {'command': '1007/2', 'effect': 'read'},
    'navigation.status': {'command': '1007/1', 'effect': 'read'},
    'perception.status': {'command': '2002/1', 'effect': 'read'},
    'posture.stand': {'command': '2/22 MotionParam=1', 'effect': 'motion'},
    'posture.sit': {'command': '2/22 MotionParam=4', 'effect': 'motion'},
    'navigation.submit': {'command': '1003/1', 'effect': 'motion', 'required': ['x', 'y', 'z', 'yaw']},
    'navigation.cancel': {'command': '1004/1', 'effect': 'motion'},
}


class M20Operations:
    def __init__(self, device_ref, transport, *, timeout=10):
        self.device_ref, self.transport, self.timeout = device_ref, transport, timeout

    def describe(self):
        return OPERATIONS

    def execute(self, operation, parameters=None, *, task_ref=None):
        parameters = parameters or {}
        if operation not in OPERATIONS:
            raise ValueError('Unsupported M20 AOS operation: ' + operation)
        if operation == 'navigation.submit':
            if set(parameters) != {'x', 'y', 'z', 'yaw'} or any(
                isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v)
                for v in parameters.values()
            ):
                raise ValueError('Explicit calibrated map x/y/z/yaw are required, never image pixels')
            payload = protocol.single_point_nav_request(parameters, point_id=None)
        else:
            if parameters:
                raise ValueError('This operation accepts no parameters')
            payload = {
                'localization.get': protocol.map_location_request,
                'navigation.status': protocol.nav_status_request,
                'perception.status': protocol.perception_state_request,
                'posture.stand': lambda: protocol.motion_state_request(1),
                'posture.sit': lambda: protocol.motion_state_request(4),
                'navigation.cancel': protocol.cancel_nav_request,
            }[operation]()
        response = self.transport.send_request(payload, timeout=self.timeout)
        valid = isinstance(response, dict) and isinstance(response.get('PatrolDevice'), dict)
        return {'operation': operation, 'device_ref': self.device_ref, 'task_ref': task_ref,
                'state': 'unknown' if not valid else 'acknowledged' if protocol.response_ok(response) else 'rejected',
                'error': 'OUTCOME_UNKNOWN' if response is None else 'INVALID_DEVICE_RESPONSE' if not valid else None,
                'response': response, 'physical_completion_confirmed': False}
