"""Public capability and the two-model alarm gate."""
import uuid
from datetime import datetime, timezone

CAPABILITY = 'joyai_video_anomaly'
RESULT_TYPE = 'behavior.assessment'
REPORT_TYPE = 'joyai_anomaly_review'
REVIEW_CAPABILITY = 'joyai_clip_rereview'
VERSION = 'joyai-int4-qwen3.8-ondemand-v2'
OPERATIONS = ['sources.query', 'streams.open', 'streams.close', 'capabilities.describe',
              'capabilities.register', 'result_types.query', 'instances.query', 'instances.configure',
              'tasks.submit', 'tasks.start', 'tasks.get', 'tasks.cancel', 'results.register',
              'assets.register', 'assets.query', 'media.resolve', 'events.register',
              'events.query', 'reports.register', 'reports.query']


def identifier(key):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'hxjm:joyai:' + key))


def iso(stamp):
    return datetime.fromtimestamp(round(stamp * 1000) / 1000, timezone.utc).isoformat(timespec='milliseconds')


def agreed(kind, joy, review):
    """Only two validated, affirmative verdicts for the same kind can alert."""
    return kind in ('fight', 'fall') and all(
        isinstance(v, dict) and v.get('decision') == 'confirmed' and v.get('kind') == kind
        for v in (joy, review))


def capability():
    return {'request_id': identifier('capability-v1'), 'capability_code': CAPABILITY,
            'display_name': 'JoyAI 四路打架/跌倒观察与 Qwen 视觉复核',
            'object_types': ['person'], 'input_kinds': ['live_video'],
            'contract': {'input_schema': {'type': 'object', 'properties': {
                'kind': {'type': 'string', 'enum': ['live_video']},
                'source_id': {'type': 'string'}, 'stream_session_id': {'type': 'string'}},
                'required': ['kind', 'source_id', 'stream_session_id'], 'additionalProperties': False},
                'parameters_schema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
                'output_types': [RESULT_TYPE]}}


def review_capability():
    return {'request_id': identifier('clip-rereview-capability-v1'), 'capability_code': REVIEW_CAPABILITY,
            'display_name': '异常片段人工重新复核', 'object_types': ['person'], 'input_kinds': ['recording'],
            'contract': {'input_schema': {'type': 'object', 'properties': {
                'kind': {'type': 'string', 'enum': ['recording']},
                'asset_ids': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1},
                'start_at': {'type': 'string'}, 'end_at': {'type': 'string'}},
                'required': ['kind', 'asset_ids', 'start_at', 'end_at'], 'additionalProperties': False},
                'parameters_schema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
                'output_types': [RESULT_TYPE]}}


def tool_description():
    return {'name': CAPABILITY, 'version': VERSION, 'task_modes': ['continuous'],
            'description': '观察四路视频中的打架和跌倒；疑似事件先展示，双模型确认后标红；支持原片段人工重新复核。',
            'input_kinds': ['live_video'], 'output_types': [{'result_type': RESULT_TYPE, 'schema_version': '1'}],
            'operations': {'health': 'GET /health', 'capabilities.describe': 'GET /tools',
                           'tasks.submit': 'POST /monitoring/start', 'tasks.get': 'GET /status',
                           'tasks.cancel': 'POST /monitoring/stop', 'reviews.restart': 'POST /reviews/restart'},
            'input_schema': {'type': 'object', 'properties': {
                'camera_ids': {'type': 'array', 'items': {'type': 'string',
                    'enum': ['camera_1', 'camera_2', 'camera_3', 'camera_4']}, 'minItems': 1, 'uniqueItems': True}},
                'additionalProperties': False},
            'authentication': '写操作须使用 X-JoyAI-Token；公共业务写入另用服务身份。'}
