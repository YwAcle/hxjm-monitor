"""Translate completed inference into a frame result, independently of live display."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import uuid


@dataclass(frozen=True)
class FrameResultInput:
    """Only historical frame metadata; a queued result must not retain image pixels."""
    frame_ts_ms: int
    source_width: int
    source_height: int
    media_pts_ms: object
    public_frame_ref: object

    @classmethod
    def from_capture(cls, captured):
        return cls(captured.frame_ts_ms, captured.source_width, captured.source_height,
                   getattr(captured, 'media_pts_ms', None),
                   getattr(captured, 'public_frame_ref', None))


def _uuid(value):
    parsed = uuid.UUID(value)
    if parsed.int == 0:
        raise ValueError('An object reference cannot be the zero UUID')
    return str(parsed)


def _timestamp(milliseconds):
    if not isinstance(milliseconds, (int, float)) or not math.isfinite(milliseconds):
        raise ValueError('Timestamp must be finite milliseconds')
    return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).isoformat(
        timespec='milliseconds')


def frame_result(captured, detections, *, camera_id, algorithm, tracking_session,
                 session_generation, worker_slot, worker_generation, processed_at_ms,
                 tracking_started_at_ms=None):
    """Create a detached result using the context captured before inference.

    This is an internal handoff. Execution references and a real analysis window
    must be supplied separately before building a results.register request.
    """
    reference = getattr(captured, 'public_frame_ref', None)
    if reference is None:
        raise ValueError('Historical results require a public input frame reference')
    targets = []
    for index, detection in enumerate(detections):
        bbox = detection.get('bbox')
        if (not isinstance(bbox, (list, tuple)) or len(bbox) != 4
                or any(not isinstance(value, (int, float)) or not math.isfinite(value)
                       or not 0 <= value <= 1 for value in bbox)
                or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]):
            raise ValueError('Detection requires a normalized, positive-area xyxy bbox')
        prediction = detection.get('is_prediction', False)
        confidence = detection.get('confidence')
        if type(prediction) is not bool:
            raise ValueError('is_prediction must be a boolean')
        if (not prediction and (not isinstance(confidence, (int, float))
                                or not math.isfinite(confidence) or not 0 <= confidence <= 1)):
            raise ValueError('An observed target requires confidence in [0,1]')
        label = detection.get('label')
        if not isinstance(label, str) or not label:
            raise ValueError('Detection label is required')
        target = {'target_index': index, 'object_type': label, 'class_code': label,
                  'bbox': list(bbox), 'confidence': None if prediction else confidence,
                  'is_prediction': prediction}
        if algorithm == 'botsort':
            local_id = detection.get('track_id')
            if type(local_id) is not int or local_id < 0:
                raise ValueError('A tracked target requires a nonnegative local_track_id')
            target['local_track_id'] = local_id
        targets.append(target)
    pts = getattr(captured, 'media_pts_ms', None)
    if pts is not None and (not isinstance(pts, (int, float))
                            or not math.isfinite(pts) or pts < 0):
        raise ValueError('Input PTS must be nonnegative finite milliseconds or null')
    output = {
        'camera_id': camera_id, 'algorithm': algorithm,
        'source_id': _uuid(reference.source_id),
        'stream_session_id': _uuid(reference.stream_session_id),
        'tracking_context_id': _uuid(tracking_session) if algorithm == 'botsort' else None,
        'session_generation': session_generation,
        'worker_slot': worker_slot, 'worker_generation': worker_generation,
        'processed_at': _timestamp(processed_at_ms),
        'result': {
            'result_id': str(uuid.uuid4()),
            'producer_result_key': 'frame:' + _uuid(reference.frame_id),
            'frame_id': _uuid(reference.frame_id), 'frame_seq': reference.frame_seq,
            'occurred_at': _timestamp(captured.frame_ts_ms),
            'stream_pts_ms': None if pts is None else math.floor(pts + 0.5),
            'time_quality': 'ingest_estimated',
            'media_asset_id': None, 'media_pts_ms': None,
            'source_width': captured.source_width, 'source_height': captured.source_height,
            'targets': targets,
        },
    }
    if algorithm == 'botsort' and tracking_started_at_ms is not None:
        if tracking_started_at_ms > captured.frame_ts_ms:
            raise ValueError('Tracking state cannot start after its input frame')
        output['tracking_context'] = {
            'context_key': 'tracker:' + _uuid(tracking_session),
            'started_at': _timestamp(tracking_started_at_ms),
        }
    if reference.session_started_at_ms is not None:
        origin = getattr(reference, 'session_time_origin_at_ms', None)
        if origin is None:
            origin = reference.session_started_at_ms
        output['stream_session'] = {
            'stream_session_id': output['stream_session_id'],
            'started_at': _timestamp(reference.session_started_at_ms),
            'time_origin_at': _timestamp(origin),
            'time_basis': 'ingest_clock', 'source_timezone': 'UTC',
            'source_width': reference.session_width,
            'source_height': reference.session_height,
        }
    return output


def registration_request(frames, execution, analysis_coverage, *, request_id):
    """Build one immutable request for a single source, input and tracking context.

    The caller supplies an explicit reporting window and its precise frame
    manifest. No frame duration, task, execution or completed coverage is guessed.
    """
    if not frames:
        raise ValueError('A registration batch requires at least one frame')
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
        raise ValueError('request_id must contain 1 to 128 characters')
    first = frames[0]
    group_fields = ('source_id', 'stream_session_id', 'tracking_context_id', 'algorithm')
    if any(any(frame[field] != first[field] for field in group_fields) for frame in frames):
        raise ValueError('A batch must share its source, input, algorithm and tracking context')
    results = [deepcopy(frame['result']) for frame in frames]
    identifiers = [result['frame_id'] for result in results]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError('A batch cannot contain the same input frame twice')
    coverage = deepcopy(analysis_coverage)
    manifest = coverage.get('frame_ids')
    if (not isinstance(manifest, list) or len(set(manifest)) != len(manifest)
            or not set(identifiers).issubset(manifest)
            or coverage.get('analyzed_frame_count') != len(manifest)
            or type(coverage.get('closed')) is not bool
            or not isinstance(coverage.get('gaps'), list)):
        raise ValueError('Analysis coverage requires a precise frame manifest and closed flag')
    start = datetime.fromisoformat(coverage['start_at'].replace('Z', '+00:00'))
    end = datetime.fromisoformat(coverage['end_at'].replace('Z', '+00:00'))
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise ValueError('Analysis window must be a nonempty timezone-aware interval')
    if any(not start <= datetime.fromisoformat(result['occurred_at']) < end for result in results):
        raise ValueError('Every submitted frame must be inside the declared analysis window')
    payload = {name: _uuid(execution[name]) for name in ('task_id', 'run_id', 'result_set_id')}
    for name in ('set_key', 'capability_code'):
        value = execution[name]
        if not isinstance(value, str) or not value or len(value) > (128 if name == 'set_key' else 64):
            raise ValueError('Invalid ' + name)
        payload[name] = value
    payload.update(request_id=request_id, result_type='detection.frame', schema_version='1',
                   source_id=first['source_id'], stream_session_id=first['stream_session_id'],
                   results=results, processed_at=max(frame['processed_at'] for frame in frames),
                   analysis_coverage=coverage)
    if first['tracking_context_id'] is not None:
        context = deepcopy(execution['tracking_context'])
        if not isinstance(context.get('context_key'), str) or not 1 <= len(context['context_key']) <= 128:
            raise ValueError('A tracking context requires its stable context_key')
        started = datetime.fromisoformat(context['started_at'].replace('Z', '+00:00'))
        if started.tzinfo is None or any(started > datetime.fromisoformat(result['occurred_at'])
                                       for result in results):
            raise ValueError('Tracking context cannot start after its observations')
        payload.update(tracking_context_id=first['tracking_context_id'], tracking_context=context)
    return payload
