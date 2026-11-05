"""Register inputs, distinct assessments, event evidence and the review report."""
from datetime import datetime, timedelta
import hashlib
from pathlib import Path
import uuid

from video_analysis.business_client import BusinessClient
from .contracts import CAPABILITY, REVIEW_CAPABILITY, RESULT_TYPE, REPORT_TYPE, VERSION, agreed, capability, review_capability, identifier, iso


class Publisher:
    def __init__(self, config, ledger, client=None):
        self.config, self.ledger = config, ledger
        self.client = client or BusinessClient(config['business_url'], service_id='joyai-producer',
            token_provider=lambda: config['token'], timeout=15)

    def deploy(self):
        definition = capability()
        rows = self.client.get('/capabilities', {'capability_code': CAPABILITY})['items']
        if not rows:
            self.client.post('/capabilities', definition)
        elif rows[0]['contract'] != definition['contract']:
            raise ValueError('Existing JoyAI capability contract differs; do not overwrite it')
        if not self.client.get('/result-types', {'type_code': RESULT_TYPE, 'schema_version': '1'})['items']:
            raise ValueError('Public behavior.assessment/1 is not registered')
        rows = self.client.get('/instances', {'instance_id': self.config['instance_id']})['items']
        if rows and not rows[0].get('enabled'):
            raise ValueError('JoyAI instance is disabled by the business configuration')
        if not rows or rows[0]['implementation_version'] != VERSION:
            revision = rows[0]['revision'] if rows else None
            self.client.post('/instances', {'request_id': identifier(self.config['instance_id'] + ':' + VERSION + ':' + str(revision)),
                'instance_id': self.config['instance_id'], 'instance_key': 'joyai:' + self.config['instance_id'],
                'capability_code': CAPABILITY, 'implementation_code': 'joyai_qwen',
                'implementation_version': VERSION, 'source_ids': [c['source_id'] for c in self.config['cameras'].values()],
                'service_ref': self.config['tool_url'], 'enabled': True,
                **({'expected_revision': revision} if revision else {})})

    def unit(self, camera_id, frame):
        ref = frame.reference
        key = ref.stream_session_id
        unit = self.ledger.get(key)
        if unit is None:
            camera = self.config['cameras'][camera_id]
            unit = {'id': key, 'kind': 'unit', 'camera_id': camera_id, 'source_id': ref.source_id,
                    'session': {'stream_session_id': key, 'source_id': ref.source_id,
                        'camera_stream_id': camera['camera_stream_id'], 'session_key': 'joyai-input:' + key,
                        'started_at': iso(ref.session_started_at_ms / 1000),
                        'time_origin_at': iso(ref.session_time_origin_at_ms / 1000),
                        'time_basis': 'ingest_clock', 'source_timezone': 'Asia/Shanghai',
                        'source_width': ref.session_width, 'source_height': ref.session_height}}
        self.prepare(unit)
        return unit

    def prepare(self, unit):
        call = lambda name, path, body: self.ledger.call(unit, name, path, body, self.client)
        call('session', '/streams/open', {'request_id': 'stream:' + unit['id'], **unit['session']})
        task = call('task', '/tasks', {'request_id': identifier(unit['id'] + ':task'),
            'task_kind': CAPABILITY, 'business_key': 'joyai:' + unit['id'], 'capability_code': CAPABILITY,
            'task_mode': 'continuous', 'input': {'kind': 'live_video', 'source_id': unit['source_id'],
            'stream_session_id': unit['id']}, 'parameters': {}, 'requested_outputs': [RESULT_TYPE],
            'instance_id': self.config['instance_id']})
        started = call('start', '/tasks/start', {'request_id': identifier(unit['id'] + ':start'),
            'task_id': task['task_id'], 'expected_revision': task['revision'], 'instance_id': self.config['instance_id']})
        unit.update(task_id=started['task_id'], run_id=started['run_id'])
        self.ledger.save(unit['id'], 'unit', unit)

    def assessment(self, job, stage, verdict):
        unit = self.ledger.get(job['unit_id'])
        if job.get('manual_review'):
            unit = {**unit, 'task_id': job['review_task_id'], 'run_id': job['review_run_id']}
        else:
            self.prepare(unit)
        decision = {'uncertain': 'insufficient_evidence'}.get(verdict['decision'], verdict['decision'])
        payload = {'behavior_type': job['event_type'], 'decision': decision,
                   'description': (stage + ': ' + verdict['reason'])[:4000]}
        if verdict.get('confidence') is not None:
            payload.update(score=verdict['confidence'], score_semantics='model_self_reported_confidence_0_to_1')
        result_id = identifier(job['id'] + ':' + stage)
        result = {'result_id': result_id, 'producer_result_key': job['id'] + ':' + stage,
                  'start_at': iso(job['start']), 'end_at': iso(job['end']), 'payload': payload}
        if job.get('asset_id'):
            result['payload_asset_id'] = job['asset_id']
        response = self.ledger.call(job, stage + '_result_v1', '/results/register', {
            'request_id': identifier(job['id'] + ':' + stage + ':register:v1'), 'task_id': unit['task_id'],
            'run_id': unit['run_id'], 'result_set_id': identifier(job['id'] + ':' + stage + ':set'),
            'set_key': 'joyai:' + job['id'] + ':' + stage,
            'capability_code': REVIEW_CAPABILITY if job.get('manual_review') else CAPABILITY, 'result_type': RESULT_TYPE,
            'schema_version': '1', 'source_id': unit['source_id'], 'stream_session_id': unit['id'],
            'results': [result], 'processed_at': iso(job['processed_at']), 'analysis_coverage': {
                'start_at': iso(job['start']), 'end_at': iso(job['end']), 'closed': False,
                'analyzed_frame_count': 0, 'frame_ids': [], 'result_ids': [result_id], 'gaps': []}}, self.client)
        accepted = response.get('accepted_result_ids', []) + response.get('duplicate_result_ids', [])
        if result_id not in accepted:
            raise RuntimeError('Behavior result was not acknowledged by the business service')
        return result_id

    def prepare_review(self, job):
        if job.get('review_run_id'):
            return
        definition = review_capability()
        if not self.client.get('/capabilities', {'capability_code': REVIEW_CAPABILITY})['items']:
            self.client.post('/capabilities', definition)
        instance = self.ledger.get('clip-review-instance')
        if instance is None:
            instance = {'id': 'clip-review-instance', 'kind': 'config', 'instance_id': str(uuid.uuid4())}
            self.ledger.save(instance['id'], 'config', instance)
        self.ledger.call(instance, 'configure', '/instances', {
            'request_id': identifier(instance['instance_id'] + ':configure'),
            'instance_id': instance['instance_id'], 'instance_key': 'joyai-clip:' + instance['instance_id'],
            'capability_code': REVIEW_CAPABILITY, 'implementation_code': 'joyai_qwen_clip',
            'implementation_version': VERSION, 'source_ids': [c['source_id'] for c in self.config['cameras'].values()],
            'service_ref': self.config['tool_url'], 'enabled': True}, self.client)
        task = self.ledger.call(job, 'review_task', '/tasks', {
            'request_id': identifier(job['id'] + ':task'), 'task_kind': REVIEW_CAPABILITY,
            'business_key': 'joyai-rereview:' + job['id'], 'capability_code': REVIEW_CAPABILITY,
            'task_mode': 'once', 'input': {'kind': 'recording', 'asset_ids': [job['asset_id']],
                'start_at': iso(job['start']), 'end_at': iso(job['end'])},
            'parameters': {}, 'requested_outputs': [RESULT_TYPE], 'instance_id': instance['instance_id']}, self.client)
        started = self.ledger.call(job, 'review_start', '/tasks/start', {
            'request_id': identifier(job['id'] + ':start'), 'task_id': task['task_id'],
            'expected_revision': task['revision'], 'instance_id': instance['instance_id']}, self.client)
        job.update(review_task_id=started['task_id'], review_run_id=started['run_id'])
        self.ledger.save(job['id'], 'job', job)

    def retire(self, unit):
        """End an idle unit only after its queued evidence has been delivered."""
        if unit.get('retired') or 'start' not in unit.get('calls', {}):
            return
        current = self.client.get('/tasks', {'task_id': unit['task_id']})
        self.ledger.call(unit, 'cancel', '/tasks/cancel', {
            'request_id': identifier(unit['id'] + ':cancel'), 'task_id': unit['task_id'],
            'expected_revision': current['revision'], 'reason': 'JoyAI 输入结束，保留已登记证据及报告'}, self.client)
        import time
        ended = unit.setdefault('ended_at', time.time())
        self.ledger.save(unit['id'], 'unit', unit)
        self.ledger.call(unit, 'close', '/streams/close', {
            'request_id': identifier(unit['id'] + ':close'), 'stream_session_id': unit['id'],
            'expected_state': 'open', 'state': 'closed', 'occurred_at': iso(ended), 'ended_at': iso(ended)}, self.client)
        unit['retired'] = True
        self.ledger.save(unit['id'], 'unit', unit)

    def asset(self, job):
        self.prepare(self.ledger.get(job['unit_id']))
        path = Path(self.config['storage_root']) / job['storage_key']
        content = path.read_bytes()
        response = self.ledger.call(job, 'asset', '/assets/register', {
            'request_id': identifier(job['id'] + ':asset-register'), 'asset_id': identifier(job['id'] + ':video'),
            'producer_key': 'joyai:' + job['id'], 'asset_type': 'algorithm_output',
            'source_id': job['source_id'], 'stream_session_id': job['unit_id'], 'storage_key': job['storage_key'],
            'state': 'available', 'start_at': iso(job['start']), 'end_at': iso(job['end']),
            'content_type': 'video/mp4', 'byte_size': len(content), 'checksum_sha256': hashlib.sha256(content).hexdigest(),
            'expires_at': (datetime.fromisoformat(iso(job['end'])) + timedelta(days=7)).isoformat()}, self.client)
        if response.get('state') != 'available' or response.get('asset_id') != identifier(job['id'] + ':video'):
            raise RuntimeError('Video asset was not acknowledged as available')
        job['asset_id'] = response['asset_id']
        thumbnail = path.with_suffix('.jpg')
        content = thumbnail.read_bytes()
        response = self.ledger.call(job, 'thumbnail', '/assets/register', {
            'request_id': identifier(job['id'] + ':thumbnail-register'), 'asset_id': identifier(job['id'] + ':thumbnail'),
            'producer_key': 'joyai-thumbnail:' + job['id'], 'asset_type': 'algorithm_output',
            'source_id': job['source_id'], 'stream_session_id': job['unit_id'],
            'storage_key': str(Path(job['storage_key']).with_suffix('.jpg')), 'state': 'available',
            'start_at': iso(job['start']), 'end_at': iso(job['end']), 'content_type': 'image/jpeg',
            'byte_size': len(content), 'checksum_sha256': hashlib.sha256(content).hexdigest(),
            'expires_at': (datetime.fromisoformat(iso(job['end'])) + timedelta(days=7)).isoformat()}, self.client)
        if response.get('state') != 'available':
            raise RuntimeError('Thumbnail asset was not acknowledged')
        job['thumbnail_asset_id'] = response['asset_id']
        self.ledger.save(job['id'], 'job', job)

    def publish(self, job):
        """A failed, missing or disagreeing review cannot enter the confirmed alarm list."""
        if not job.get('manual_review'):
            self.asset(job)
        joy_result = self.assessment(job, 'joyai', job['joy_verdict'])
        review_result = self.assessment(job, 'qwen', job['review_verdict'])
        confirmed = agreed(job['event_type'], job['joy_verdict'], job['review_verdict'])
        decision = 'confirmed' if confirmed else (
            'rejected' if job['review_verdict']['decision'] == 'rejected' else 'insufficient_evidence')
        unit = self.ledger.get(job['unit_id'])
        if job.get('manual_review'):
            unit = {**unit, 'task_id': job['review_task_id'], 'run_id': job['review_run_id']}
        coverage = {'schema_version': '1', 'completed': [], 'gaps': [
            {'source_id': job['source_id'], 'stage': 'analysis', 'start_at': iso(job['start']),
             'end_at': iso(job['end']), 'reason_code': 'SAMPLED_VIDEO_REVIEW'}]}
        # Public event/report IDs require UUIDv4; persist them before the first send.
        event_id = job.setdefault('event_id', str(uuid.uuid4()))
        job.setdefault('report_id', str(uuid.uuid4()))
        self.ledger.save(job['id'], 'job', job)
        previous = self.client.get('/events/' + event_id) if job.get('manual_review') else None
        self.ledger.call(job, 'event', '/events/register', {'request_id': identifier(job['id'] + ':event-register'),
            'event_id': event_id, 'event_key': previous['event_key'] if previous else 'joyai:' + job['id'],
            'event_type': 'behavior.' + job['event_type'],
            **({'expected_revision': previous['revision']} if previous else {}),
            'source_id': job['source_id'], 'start_at': iso(job['start']), 'end_at': iso(job['end']),
            'state': 'closed', 'end_reason': 'normal', 'run_id': unit['run_id'],
            'result_ids': [joy_result, review_result], 'objects': [], 'coverage': coverage,
            'conclusion': {'schema_version': '1', 'label': decision,
                           'description': job['review_verdict']['reason']}}, self.client)
        evidence = self.client.get('/events/' + event_id)['evidence']
        camera = self.config['cameras'][job['camera_id']]
        report = {'schema_version': '1', 'candidate_id': job.get('root_candidate_id', job['id']),
            'manual_review': bool(job.get('manual_review')), 'previous_report_id': job.get('previous_report_id'),
            'confirmed': confirmed, 'event_type': job['event_type'],
            'camera_id': job['camera_id'], 'location': camera.get('location', ''), 'camera_name': camera['name'],
            'occurred_at': iso(job['trigger_at']), 'clip_start_at': iso(job['start']),
            'clip_end_at': iso(job['end']), 'clip_seconds': job['evidence']['duration'],
            'video_asset_id': job['asset_id'], 'thumbnail_asset_id': job['thumbnail_asset_id'],
            'trigger_observation': job['observation'],
            'joyai': job['joy_verdict'], 'review': job['review_verdict'],
            'observer_model': 'jdopensource/JoyAI-VL-Interaction-INT4', 'observer_precision': 'INT4',
            'implementation_version': VERSION, 'review_model': self.config['review_model']}
        text = ('打架' if job['event_type'] == 'fight' else '跌倒') + '复核：' + decision + '\n'
        text += '\n'.join(job['review_verdict']['report']['observations'])
        text += '\n' + job['review_verdict']['reason']
        self.ledger.call(job, 'report', '/reports/register', {'request_id': identifier(job['id'] + ':report-register'),
            'report_id': job['report_id'], 'subject_kind': 'event', 'subject_id': event_id,
            'report_type': REPORT_TYPE + ':' + job['id'] if job.get('manual_review') else REPORT_TYPE,
            'completeness': 'partial', 'coverage': coverage,
            'task_id': unit['task_id'], 'run_id': unit['run_id'], 'model_version': self.config['review_model'],
            'report_json': report, 'report_text': text, 'evidence_ids': [e['evidence_id'] for e in evidence]}, self.client)
        job.update(state='published', confirmed=confirmed, event_id=event_id, error=None)
        self.ledger.save(job['id'], 'job', job)
        if job.get('manual_review'):
            self.finish_review(job)

    def finish_review(self, job):
        if not job.get('manual_review') or not job.get('review_task_id'):
            return
        current = self.client.get('/tasks', {'task_id': job['review_task_id']})
        self.ledger.call(job, 'review_finish', '/tasks/cancel', {
            'request_id': identifier(job['id'] + ':finish'), 'task_id': job['review_task_id'],
            'expected_revision': current['revision'], 'reason': '人工片段复核结束，保留成果和历史报告'}, self.client)
