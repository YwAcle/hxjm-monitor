"""Build historical samples and identities off the live inference path."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import math
import socket
import threading
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from .business_client import (BusinessClient, BusinessRequestError, BusinessUnavailable,
                              _NoRedirect, image_multipart)


LOG = logging.getLogger(__name__)


class FirstObservedPerson:
    """Replace this selector to change sampling without changing persistence."""
    name = 'first_observed'

    def select(self, detections):
        for detection in detections:
            box = detection.get('bbox')
            if (detection.get('label') == 'person' and not detection.get('is_prediction', False)
                    and type(detection.get('track_id')) is int and detection['track_id'] >= 0
                    and isinstance(box, (list, tuple)) and len(box) == 4
                    and all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in box)
                    and box[2] > box[0] and box[3] > box[1]):
                yield detection


class ReIDFeatureClient:
    """The existing extractor receives crops, never business service credentials."""
    def __init__(self, base_url, timeout=30):
        parts = urlsplit(base_url)
        if (parts.scheme not in ('http', 'https') or not parts.hostname
                or parts.username is not None or parts.password is not None
                or parts.query or parts.fragment or parts.path not in ('', '/')):
            raise ValueError('Feature service requires an explicit HTTP origin')
        self.base_url, self.timeout = base_url.rstrip('/'), timeout
        self._opener = build_opener(_NoRedirect())

    def _request(self, path, data=None, content_type=None):
        headers = {'Accept': 'application/json'}
        if content_type:
            headers['Content-Type'] = content_type
        request = Request(self.base_url + path, data=data, headers=headers,
                          method='GET' if data is None else 'POST')
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                return BusinessClient._decode(response.read(BusinessClient.MAX_RESPONSE_BYTES + 1))
        except HTTPError as error:
            status = error.code
            error.close()
            failure = BusinessUnavailable if status in (408, 429, 502, 503, 504) else BusinessRequestError
            raise failure('FEATURE_SERVICE_ERROR', status) from None
        except (URLError, OSError, socket.timeout, TimeoutError):
            raise BusinessUnavailable('FEATURE_SERVICE_UNAVAILABLE') from None

    def definition(self):
        health = self._request('/health')
        if health.get('ready') is not True:
            raise BusinessUnavailable('FEATURE_SERVICE_NOT_READY')
        text = health.get('definition_text')
        if not isinstance(text, str) or hashlib.sha256(text.encode()).hexdigest() != health.get('definition_sha256'):
            raise BusinessRequestError('FEATURE_DEFINITION_MISSING')
        dimensions = health.get('embedding_dim')
        if type(dimensions) is not int or not 1 <= dimensions <= 16000:
            raise BusinessRequestError('INVALID_FEATURE_DIMENSIONS')
        return {
            'feature_space_id': health['feature_space_id'], 'definition_text': text,
            'definition_sha256': health['definition_sha256'],
            'definition_version': health.get('definition_version', '1'),
            'object_type': 'person', 'feature_kind': 'reid', 'dimensions': dimensions,
            'dtype': 'float32', 'normalization': 'l2', 'metric': 'cosine',
        }

    def extract(self, image, metadata, bbox=None):
        fields = {'metadata': json.dumps(metadata, separators=(',', ':'))}
        if bbox is not None:
            fields['bbox'] = json.dumps(bbox)
        data, content_type = image_multipart(fields, image)
        return self._request('/v1/reid/image-features', data, content_type)

    def detect(self, image, metadata):
        data, content_type = image_multipart({'metadata': json.dumps(metadata, separators=(',', ':'))}, image)
        return self._request('/v1/reid/person-crops', data, content_type)


@dataclass
class _Sample:
    key: tuple
    source_id: str
    session_id: str
    frame_id: str
    occurred_at: str
    expires_at: str
    bbox: dict
    crop: object
    asset_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sample_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    feature_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tracklet_id: str = None
    image: bytes = None
    calls: dict = field(default_factory=dict)
    responses: dict = field(default_factory=dict)
    retry_at: float = 0
    pixel_bbox: object = None


class LocalSamplePipeline:
    """Bounded crop queue; only acknowledged historical observations are processed.

    shortcut: pending crops are memory-only; restart recovery from persisted frames
    can be added when offline reprocessing is introduced.
    """
    def __init__(self, client, *, feature_url=None, threshold, instance_id=None,
                 capability_code='person.reidentification', queue_size=16,
                 selector=None, extractor=None, execution_for=None, finish_tasks=False,
                 poll_interval_seconds=2):
        if type(queue_size) is not int or queue_size <= 0:
            raise ValueError('Sample queue size must be positive')
        if type(threshold) not in (int, float) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError('Identity threshold must be in [0,1]')
        if execution_for is None:
            if instance_id is None or uuid.UUID(instance_id).int == 0:
                raise ValueError('A feature capability instance is required')
        self.client, self.threshold = client, threshold
        self.instance_id, self.capability_code = instance_id, capability_code
        self.queue_size, self.finish_tasks = queue_size, finish_tasks
        self.selector = selector or FirstObservedPerson()
        self.extractor = extractor or ReIDFeatureClient(feature_url)
        self.execution_for = execution_for
        self.poll_interval_seconds = poll_interval_seconds
        self._condition = threading.Condition()
        self._jobs, self._selected = {}, {}
        self._selection_cleanup_at = 0
        self._thread, self._stopping = None, False
        self._space, self._space_request = None, None
        self._completed = self._failed = self._full = 0
        self._last_error = None
        self._material_thread = None
        self._material_stop = threading.Event()
        self._material_cache = {}
        self._material_completed = self._material_failed = 0
        self._material_error = None
        self._space_lock = threading.Lock()

    def start(self):
        with self._condition:
            if self._thread is not None or self._stopping:
                raise RuntimeError('Sample worker cannot be restarted')
            self._thread = threading.Thread(target=self._run, name='history-samples', daemon=True)
            self._thread.start()
            self._material_thread = threading.Thread(target=self._poll_materials,
                                                     name='query-enrollment-features', daemon=True)
            self._material_thread.start()

    def offer(self, captured, detections, *, tracking_context_id, algorithm='botsort'):
        """Copy selected crops only; no encoding, extraction or network on this path."""
        reference = getattr(captured, 'public_frame_ref', None)
        if reference is None or algorithm != 'botsort' or not tracking_context_id:
            return 0
        now = time.time()
        occurred = datetime.fromtimestamp(captured.frame_ts_ms / 1000, timezone.utc)
        expiry = occurred + timedelta(days=7)
        if expiry.timestamp() <= now:
            return 0
        accepted = 0
        with self._condition:
            if self._stopping:
                return 0
            # Prune periodically rather than scanning historical tracks on every live frame.
            if now >= self._selection_cleanup_at:
                self._selected = {key: end for key, end in self._selected.items() if end > now}
                self._selection_cleanup_at = now + 60
            for detection in self.selector.select(detections):
                key = reference.source_id, tracking_context_id, detection['track_id']
                if key in self._jobs or key in self._selected:
                    continue
                if len(self._jobs) >= self.queue_size:
                    self._full += 1
                    break
                height, width = captured.frame.shape[:2]
                box = detection['bbox']
                x1, y1 = math.floor(box[0] * width), math.floor(box[1] * height)
                x2, y2 = min(width, math.ceil(box[2] * width)), min(height, math.ceil(box[3] * height))
                if x2 <= x1 or y2 <= y1:
                    continue
                crop = captured.frame[y1:y2, x1:x2].copy()
                self._jobs[key] = _Sample(
                    key, reference.source_id, reference.stream_session_id, reference.frame_id,
                    occurred.isoformat(timespec='milliseconds'), expiry.isoformat(timespec='milliseconds'),
                    {'schema_version': '1', 'xyxy': list(box),
                     'source_width': captured.source_width, 'source_height': captured.source_height}, crop)
                accepted += 1
            self._condition.notify_all()
        return accepted

    def confirmed(self, payload, response):
        """Called after results.register confirms each accepted or duplicate frame."""
        confirmed = set(response.get('accepted_result_ids', [])) | set(response.get('duplicate_result_ids', []))
        frames = {result['frame_id'] for result in payload.get('results', [])
                  if result.get('result_id') in confirmed}
        mappings = {(str(item['tracking_context_id']), item['local_track_id']): item['tracklet_id']
                    for item in response.get('tracklets', [])}
        with self._condition:
            for key, job in self._jobs.items():
                if (job.source_id == payload.get('source_id') and job.frame_id in frames
                        and (str(key[1]), key[2]) in mappings):
                    job.tracklet_id = mappings[(str(key[1]), key[2])]
            self._condition.notify_all()

    def status(self):
        with self._condition:
            return {'queued_samples': len(self._jobs),
                    'awaiting_frame_confirmation': sum(job.tracklet_id is None for job in self._jobs.values()),
                    'completed_samples': self._completed, 'failed_samples': self._failed,
                    'full_handoffs': self._full, 'last_error': self._last_error,
                    'thread_alive': self._thread is not None and self._thread.is_alive(),
                    'materials': {'completed': self._material_completed, 'failed': self._material_failed,
                                  'last_error': self._material_error,
                                  'thread_alive': self._material_thread is not None and self._material_thread.is_alive()},
                    'strategy': self.selector.name}

    def stop(self, timeout=5):
        with self._condition:
            self._stopping = True
            self._condition.notify_all()
            thread = self._thread
        self._material_stop.set()
        if thread is not None:
            thread.join(timeout)
        if self._material_thread is not None:
            self._material_thread.join(timeout)
        return ((thread is None or not thread.is_alive())
                and (self._material_thread is None or not self._material_thread.is_alive()))

    def _once(self, job, name, payload, call):
        if name not in job.responses:
            if name not in job.calls:
                job.calls[name] = dict(payload(), request_id=str(uuid.uuid4()))
            job.responses[name] = call(job.calls[name])
        return job.responses[name]

    def _process(self, job):
        if job.image is None:
            import cv2
            ok, encoded = cv2.imencode('.jpg', job.crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not ok:
                raise BusinessRequestError('SAMPLE_ENCODING_FAILED')
            job.image, job.crop = encoded.tobytes(), None
        asset = self._once(job, 'asset', lambda: {
            'asset_id': job.asset_id, 'purpose': 'history', 'source_id': job.source_id,
            'input_frame_id': job.frame_id, 'tracklet_id': job.tracklet_id,
            'occurred_at': job.occurred_at,
        }, lambda fields: self.client.upload_image(fields, job.image))
        expiry = min(datetime.fromisoformat(job.expires_at),
                     datetime.fromisoformat(asset['expires_at'].replace('Z', '+00:00'))).isoformat()
        self._once(job, 'sample', lambda: {
            'sample_id': job.sample_id, 'purpose': 'history', 'asset_id': job.asset_id,
            'input_frame_id': job.frame_id, 'tracklet_id': job.tracklet_id,
            'occurred_at': job.occurred_at, 'expires_at': expiry, 'bbox': job.bbox,
            'quality': {'schema_version': '1', 'selection_strategy': self.selector.name},
        }, self.client.register_sample)
        self._register_embedding(job, expiry)

    def _ensure_space(self):
        with self._space_lock:
            if self._space is not None:
                return
            if self._space_request is None:
                self._space_request = dict(self.extractor.definition(), request_id=str(uuid.uuid4()))
            self.client.register_feature_space(self._space_request)
            self._space = dict(self._space_request)

    def _register_embedding(self, job, expiry, *, identity_id=None, associate=True):
        self._ensure_space()
        if self.execution_for is not None:
            if 'execution' not in job.responses:
                job.responses['execution'] = self.execution_for(job)
            execution = job.responses['execution']
        else:
            created = self._once(job, 'task', lambda: {
                'task_kind': self.capability_code,
                'business_key': 'sample:' + job.sample_id + ':instance:' + self.instance_id,
                'capability_code': self.capability_code, 'task_mode': 'once',
                'input': {'kind': 'image', 'asset_ids': [job.asset_id]},
                'requested_outputs': ['feature.embedding'], 'instance_id': self.instance_id,
                **({'expires_at': expiry} if expiry is not None else {}),
            }, self.client.create_task)
            execution = self._once(job, 'execution', lambda: {
                'task_id': created['task_id'], 'expected_revision': created['revision'],
                'instance_id': self.instance_id,
            }, self.client.start_task)
        if 'embedding' not in job.responses:
            metadata = {'request_id': job.feature_id, 'source_asset_id': job.asset_id,
                        **({'stream_session_id': job.session_id} if job.session_id else {}),
                        **({'track_id': job.tracklet_id} if job.tracklet_id else {}),
                        **({'frame_ids': [job.frame_id]} if job.frame_id else {})}
            embedding = (self.extractor.extract(job.image, metadata, bbox=job.pixel_bbox)
                         if job.pixel_bbox is not None else self.extractor.extract(job.image, metadata))
            if (embedding.get('feature_space_id') != self._space['feature_space_id']
                    or embedding.get('embedding_dim') != self._space['dimensions']
                    or embedding.get('normalized') is not True):
                raise BusinessRequestError('FEATURE_SPACE_CHANGED')
            job.responses['embedding'] = embedding
        embedding = job.responses['embedding']
        self._once(job, 'feature', lambda: {
            'feature_id': job.feature_id, 'feature_space_id': self._space['feature_space_id'],
            'run_id': execution['run_id'], 'producer_feature_key': 'sample:' + job.sample_id,
            'embedding': embedding['embedding'], 'sample_id': job.sample_id,
            'tracklet_id': job.tracklet_id, 'identity_id': identity_id, 'aggregation_method': 'single',
            'input_count': 1, 'used_count': 1, 'contributions': [{'sample_id': job.sample_id}],
            'processed_at': datetime.now(timezone.utc).isoformat(), 'expires_at': expiry,
        }, self.client.register_feature)
        if associate:
            self._once(job, 'identity', lambda: {
                'tracklet_id': job.tracklet_id, 'feature_id': job.feature_id,
                'run_id': execution['run_id'], 'threshold': self.threshold,
            }, self.client.associate_identity)
        if self.finish_tasks:
            self._once(job, 'finish', lambda: {
                'task_id': execution['task_id'], 'run_id': execution['run_id'],
                'expected_revision': execution['revision'], 'feature_ids': [job.feature_id],
            }, self.client.finish_task)

    def _material_job(self, kind, row):
        identifier = row['sample_id'] if kind == 'enrollment' else row['query_id']
        key = kind, identifier, 0
        if key not in self._material_cache:
            asset = row['asset_id'] if kind == 'enrollment' else row['input_asset_id']
            occurred = row.get('occurred_at') or datetime.now(timezone.utc).isoformat()
            job = _Sample(key, None, None, None, occurred, row.get('expires_at'), {}, None,
                          asset_id=asset)
            if kind == 'enrollment':
                job.sample_id = identifier
            job.responses['_pending_row'] = dict(row)
            self._material_cache[key] = job
        return self._material_cache[key]

    def _enrollment(self, row):
        job = self._material_job('enrollment', row)
        if job.image is None:
            job.image = self.client.image_content(job.asset_id)
        self._register_embedding(job, job.expires_at, identity_id=row['identity_id'], associate=False)
        return job

    def _query(self, row):
        job = self._material_job('query', row)
        if job.image is None:
            job.image = self.client.image_content(job.asset_id)
        if row.get('input_sample_id') is None:
            if 'detected' not in job.responses:
                job.responses['detected'] = self.extractor.detect(job.image, {
                    'request_id': str(uuid.uuid4()), 'source_asset_id': job.asset_id})
            detection = job.responses['detected']
            candidates = []
            width, height = detection['image_width'], detection['image_height']
            for candidate in detection['candidates']:
                name = 'candidate:' + candidate['candidate_id']
                normalized = [candidate['bbox'][0] / width, candidate['bbox'][1] / height,
                              candidate['bbox'][2] / width, candidate['bbox'][3] / height]
                bbox = {'schema_version': '1', 'xyxy': normalized,
                        'source_width': width, 'source_height': height}
                sample = self._once(job, name, lambda box=bbox: {
                    'sample_id': str(uuid.uuid4()), 'purpose': 'query', 'asset_id': job.asset_id,
                    'query_id': row['query_id'], 'occurred_at': job.occurred_at,
                    'expires_at': row['expires_at'], 'bbox': box,
                    'quality': {'schema_version': '1', 'selection_strategy': 'person_detection'},
                }, self.client.register_sample)
                candidates.append({'candidate_id': candidate['candidate_id'], 'sample_id': sample['sample_id'],
                                   'object_type': row['object_type'], 'bbox': bbox,
                                   'confidence': candidate['confidence']})
            response = self._once(job, 'candidates', lambda: {
                'query_id': row['query_id'], 'expected_revision': row['revision'],
                'candidates': candidates,
            }, lambda payload: self.client.post('/queries/candidates', payload))
            if response['state'] != 'pending':
                return job
        current = self.client.get('/queries/' + row['query_id'])
        if current['state'] != 'pending':
            return job
        selected = next(item for item in current['candidates']
                        if item['sample_id'] == current['input_sample_id'])
        bbox = selected.get('bbox_json', selected.get('bbox'))
        if isinstance(bbox, str):
            bbox = json.loads(bbox)
        width, height = bbox['source_width'], bbox['source_height']
        xyxy = bbox['xyxy']
        job.sample_id = current['input_sample_id']
        job.pixel_bbox = [math.floor(xyxy[0] * width), math.floor(xyxy[1] * height),
                          min(width, math.ceil(xyxy[2] * width)), min(height, math.ceil(xyxy[3] * height))]
        self._register_embedding(job, job.expires_at, associate=False)
        self._once(job, 'search', lambda: {
            'query_id': row['query_id'], 'feature_id': job.feature_id,
            'expected_revision': current['revision'], 'threshold': self.threshold, 'limit': 20,
        }, lambda payload: self.client.post('/search', payload))
        return job

    def _poll_materials(self):
        """Consume backend-owned enrollment/query work; keep the original user owner."""
        blocked = set()
        while not self._material_stop.is_set():
            try:
                self._ensure_space()
                enrolled = self.client.get('/samples/pending', {
                    'purpose': 'enrollment', 'feature_space_id': self._space['feature_space_id'], 'limit': 4})
                queries = self.client.get('/queries/pending', {'limit': 4})
                for kind, response in (('enrollment', enrolled), ('query', queries)):
                    name = 'sample_id' if kind == 'enrollment' else 'query_id'
                    present = {row[name] for row in response['items']}
                    response['items'].extend(job.responses['_pending_row']
                                             for key, job in list(self._material_cache.items())
                                             if key[0] == kind and key[1] not in present)
                for kind, rows, processor in (('enrollment', enrolled['items'], self._enrollment),
                                              ('query', queries['items'], self._query)):
                    for row in rows:
                        if self._material_stop.is_set():
                            return
                        identifier = row['sample_id'] if kind == 'enrollment' else row['query_id']
                        key = kind, identifier, row.get('revision', 0)
                        if key in blocked:
                            continue
                        try:
                            job = processor(row)
                        except Exception as error:
                            self._material_error = type(error).__name__ + ': ' + str(error)
                            if not getattr(error, 'retryable', False):
                                blocked.add(key)
                                self._material_cache.pop((kind, identifier, 0), None)
                                self._material_failed += 1
                            LOG.error('Pending %s processing failed: %s', kind, error)
                        else:
                            self._material_cache.pop(job.key, None)
                            self._material_completed += 1
                            self._material_error = None
            except Exception as error:
                self._material_error = type(error).__name__ + ': ' + str(error)
                LOG.error('Pending material poll failed: %s', error)
            # Requests and candidate records have the same finite retention as their input.
            now = time.time()
            for key, job in list(self._material_cache.items()):
                if job.expires_at and datetime.fromisoformat(job.expires_at.replace('Z', '+00:00')).timestamp() <= now:
                    self._material_cache.pop(key, None)
            self._material_stop.wait(self.poll_interval_seconds)

    def _run(self):
        while True:
            with self._condition:
                if self._stopping:
                    return
                now = time.time()
                for key, job in list(self._jobs.items()):
                    if datetime.fromisoformat(job.expires_at).timestamp() <= now:
                        del self._jobs[key]
                        self._failed += 1
                job = next((candidate for candidate in self._jobs.values()
                            if candidate.tracklet_id is not None and candidate.retry_at <= time.monotonic()), None)
                if job is None:
                    self._condition.wait(0.2)
                    continue
            try:
                self._process(job)
            except Exception as error:
                with self._condition:
                    self._last_error = type(error).__name__ + ': ' + str(error)
                    if getattr(error, 'retryable', False):
                        job.retry_at = time.monotonic() + 1
                    else:
                        self._jobs.pop(job.key, None)
                        self._selected[job.key] = datetime.fromisoformat(job.expires_at).timestamp()
                        self._failed += 1
                LOG.error('Historical sample processing failed: %s', error)
            else:
                with self._condition:
                    self._jobs.pop(job.key, None)
                    self._selected[job.key] = datetime.fromisoformat(job.expires_at).timestamp()
                    self._completed += 1
                    self._last_error = None
