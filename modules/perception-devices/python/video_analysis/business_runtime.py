"""Resolve explicit input sessions and configured algorithm instances off inference."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import os
import threading
import uuid

from .business_client import BusinessRequestError


def _uuid(value):
    if not isinstance(value, str):
        raise ValueError('Business references must be canonical nonzero UUIDs')
    parsed = uuid.UUID(value)
    if parsed.int == 0 or str(parsed) != value:
        raise ValueError('Business references must be canonical nonzero UUIDs')
    return value


def _time(value):
    if not isinstance(value, str):
        raise ValueError('Business times require an explicit timezone')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('Business times require an explicit timezone')
    return parsed.astimezone(timezone.utc)


class BusinessRuntime:
    """Pass execution_for/window_for to ResultDispatcher; no implicit activation.

    source_streams maps source UUIDs to existing camera_stream UUIDs. instances
    maps (source UUID, algorithm) to instance_id and capability_code. Capability,
    result-type and instance registration are explicit deployment prerequisites.
    """
    def __init__(self, client, *, source_streams, instances):
        if not isinstance(source_streams, dict) or not source_streams:
            raise ValueError('Explicit source-to-camera_stream mappings are required')
        self.source_streams = {_uuid(source): _uuid(stream) for source, stream in source_streams.items()}
        if len(set(self.source_streams.values())) != len(self.source_streams):
            raise ValueError('Each source requires its own camera_stream mapping')
        if not isinstance(instances, dict) or not instances:
            raise ValueError('Explicit source/algorithm instances are required')
        self.instances = deepcopy(instances)
        for key, instance in self.instances.items():
            if (not isinstance(key, tuple) or len(key) != 2 or key[0] not in self.source_streams
                    or not isinstance(key[1], str) or not 1 <= len(key[1]) <= 64
                    or not isinstance(instance, dict)):
                raise ValueError('Each instance key must be (configured source UUID, algorithm)')
            _uuid(instance.get('instance_id'))
            code = instance.get('capability_code')
            if not isinstance(code, str) or not 1 <= len(code) <= 64:
                raise ValueError('Each instance requires capability_code')
        self.client = client
        self._lock = threading.RLock()
        self._sessions = {}
        self._units = {}

    def execution_for(self, frames):
        """Resolve on the dispatcher thread; retry uses the original request IDs."""
        if not isinstance(frames, list) or not frames:
            raise ValueError('Execution resolution requires a nonempty frame batch')
        first = frames[0]
        source = _uuid(first.get('source_id'))
        session = _uuid(first.get('stream_session_id'))
        algorithm = first.get('algorithm')
        if (source, algorithm) not in self.instances:
            raise ValueError('No business instance is configured for this source and algorithm')
        metadata = self._session_metadata(first, session)
        if any(frame.get('source_id') != source or frame.get('stream_session_id') != session
               or frame.get('algorithm') != algorithm
               or self._session_metadata(frame, session) != metadata for frame in frames):
            raise ValueError('An execution batch must share one immutable input session and algorithm')
        with self._lock:
            self._open(source, session, metadata)
            key = source, session, algorithm
            if key not in self._units:
                instance = self.instances[(source, algorithm)]
                self._units[key] = {
                    'create': {
                        'request_id': str(uuid.uuid4()), 'task_kind': instance['capability_code'],
                        'business_key': ':'.join(('live', source, session, algorithm, instance['instance_id'])),
                        'capability_code': instance['capability_code'], 'task_mode': 'continuous',
                        'input': {'kind': 'live_video', 'source_id': source, 'stream_session_id': session},
                        'requested_outputs': ['detection.frame'], 'instance_id': instance['instance_id'],
                    },
                    'created': None, 'start': None, 'execution': None,
                    'result_set_id': str(uuid.uuid4()),
                }
            unit = self._units[key]
            if unit['created'] is None:
                created = self.client.create_task(deepcopy(unit['create']))
                self._check_task(created)
                unit['created'] = deepcopy(created)
            if unit['execution'] is None:
                created = unit['created']
                if created.get('state') == 'running' and created.get('run_id') is not None:
                    started = created
                else:
                    if created.get('state') != 'pending':
                        raise BusinessRequestError('TASK_NOT_STARTABLE')
                    if unit['start'] is None:
                        unit['start'] = {'request_id': str(uuid.uuid4()), 'task_id': created['task_id'],
                                         'expected_revision': created['revision'],
                                         'instance_id': self.instances[(source, algorithm)]['instance_id']}
                    started = self.client.start_task(deepcopy(unit['start']))
                self._check_task(started, running=True)
                if started['task_id'] != created['task_id']:
                    raise BusinessRequestError('TASK_RESPONSE_MISMATCH')
                unit['execution'] = {
                    'task_id': started['task_id'], 'run_id': started['run_id'],
                    'result_set_id': unit['result_set_id'],
                    'set_key': 'live:' + session + ':' + algorithm,
                    'capability_code': self.instances[(source, algorithm)]['capability_code'],
                }
            return deepcopy(unit['execution'])

    @staticmethod
    def _session_metadata(frame, session):
        metadata = BusinessRuntime._validated_metadata(frame.get('stream_session'), session)
        if _time(metadata['started_at']) > _time(frame['result']['occurred_at']):
            raise ValueError('Input session cannot start after its frame')
        return metadata

    @staticmethod
    def _validated_metadata(supplied, session):
        names = ('stream_session_id', 'started_at', 'time_origin_at', 'time_basis',
                 'source_timezone', 'source_width', 'source_height')
        if not isinstance(supplied, dict) or any(name not in supplied for name in names):
            raise ValueError('Input frame must carry its original session metadata')
        metadata = {name: supplied[name] for name in names}
        if metadata['stream_session_id'] != session:
            raise ValueError('Input frame session metadata does not match its reference')
        if metadata['time_basis'] not in ('source_clock', 'ingest_clock'):
            raise ValueError('Unsupported input session time basis')
        if (not isinstance(metadata['source_timezone'], str) or not metadata['source_timezone']
                or any(type(metadata[name]) is not int or metadata[name] <= 0
                       for name in ('source_width', 'source_height'))):
            raise ValueError('Input session requires dimensions and an explicit timezone')
        metadata['started_at'] = _time(metadata['started_at']).isoformat()
        metadata['time_origin_at'] = _time(metadata['time_origin_at']).isoformat()
        return metadata

    def open_input(self, source, metadata):
        """Recording and analysis register the same authoritative input session."""
        source = _uuid(source)
        if source not in self.source_streams:
            raise ValueError('Input source is not configured')
        if not isinstance(metadata, dict):
            raise ValueError('Input session metadata is required')
        session = _uuid(metadata.get('stream_session_id'))
        metadata = self._validated_metadata(metadata, session)
        with self._lock:
            self._open(source, session, metadata)
        return session

    def _open(self, source, session, metadata):
        key = source, session
        if key not in self._sessions:
            request = dict(metadata, request_id='stream:' + session, source_id=source,
                           camera_stream_id=self.source_streams[source], session_key='frame-hub:' + session)
            self._sessions[key] = {'request': request, 'opened': False}
        state = self._sessions[key]
        if any(state['request'][name] != value for name, value in metadata.items()):
            raise ValueError('An input session cannot change its original metadata')
        if not state['opened']:
            response = self.client.open_session(deepcopy(state['request']))
            if response.get('stream_session_id') != session or response.get('source_id') != source:
                raise BusinessRequestError('SESSION_RESPONSE_MISMATCH')
            state['opened'] = True

    @staticmethod
    def _check_task(response, *, running=False):
        if not isinstance(response, dict):
            raise BusinessRequestError('INVALID_TASK_RESPONSE')
        try:
            _uuid(response.get('task_id'))
            if type(response.get('revision')) is not int or response['revision'] <= 0:
                raise ValueError()
            if running:
                _uuid(response.get('run_id'))
                if response.get('state') != 'running':
                    raise ValueError()
        except (ValueError, TypeError):
            raise BusinessRequestError('INVALID_TASK_RESPONSE') from None

    @staticmethod
    def window_for(frames):
        """Bound this actual batch; one microsecond makes the last instant inclusive.

        This describes processed frames, not every frame recorded in the interval.
        Closing remains an explicit action after the complete manifest is known.
        """
        if not frames:
            raise ValueError('A coverage window requires processed frames')
        times = [_time(frame['result']['occurred_at']) for frame in frames]
        return {'start_at': min(times).isoformat(timespec='microseconds'),
                'end_at': (max(times) + timedelta(microseconds=1)).isoformat(timespec='microseconds'),
                'closed': False, 'gaps': []}

    @staticmethod
    def close_request(payload):
        """Return a new immutable request closing exactly its original frame manifest.

        Queue it in the same ResultSpool; do not discard the original request until
        all its results are confirmed. This does not close input or recording.
        """
        if not isinstance(payload, dict) or not isinstance(payload.get('analysis_coverage'), dict):
            raise ValueError('Closing coverage requires the original result registration request')
        coverage = payload['analysis_coverage']
        if coverage.get('closed') is not False or coverage.get('gaps') != []:
            raise ValueError('Only an explicit open, gap-free analysis batch can be closed')
        frames = coverage.get('frame_ids')
        results = payload.get('results')
        if (not isinstance(frames, list) or not frames or len(set(frames)) != len(frames)
                or coverage.get('analyzed_frame_count') != len(frames)
                or not isinstance(results, list) or not results
                or any(not isinstance(result, dict) for result in results)
                or not {result.get('frame_id') for result in results}.issubset(set(frames))):
            raise ValueError('Closing requires the complete original frame manifest')
        request_id = payload.get('request_id')
        if not isinstance(request_id, str) or not request_id:
            raise ValueError('Closing requires the original logical request ID')
        closed = deepcopy(payload)
        closed['request_id'] = 'close:' + hashlib.sha256(request_id.encode('utf-8')).hexdigest()
        closed['analysis_coverage']['closed'] = True
        return closed


def create_delivery(configuration):
    """Validate and assemble delivery without touching its runtime storage."""
    from .business_client import BusinessClient
    from .result_delivery import ResultDispatcher
    from .result_spool import ResultSpool

    client = BusinessClient(configuration['api_url'], service_id=configuration['service_id'],
                            token_provider=lambda: os.getenv(configuration['token_env']),
                            timeout=configuration['timeout_seconds'])
    runtime = BusinessRuntime(client, source_streams=configuration['source_streams'],
                              instances=configuration['instances'])
    spool = ResultSpool(configuration['spool_dir'])
    delivery = ResultDispatcher(spool, actor_key=client.actor_key, units=runtime.execution_for,
                            window_for=runtime.window_for, submit=client.submit,
                            close_for=runtime.close_request, batch_size=configuration['batch_size'],
                            queue_size=configuration['queue_size'],
                            flush_interval=configuration['flush_interval_seconds'])
    delivery.business_client = client
    delivery.business_runtime = runtime
    return delivery
