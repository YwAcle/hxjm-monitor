"""Publish reports through Business; local files contain only retry state."""
import json
from pathlib import Path
from uuid import uuid4
from shared_files import write_text

CAPABILITY = 'business.report.generate'
RESULT_TYPE = 'business.report.reference'
REPORT_TYPE = 'llm_business_summary'


class ReportPublisher:
    def __init__(self, client, state_dir, model_version):
        self.client = client
        self.state_dir = Path(state_dir)
        self.model_version = model_version

    def load(self, kind, subject_id):
        path = self.state_dir / f'{kind}-{subject_id}.json'
        return json.loads(path.read_text()) if path.exists() else None

    def save(self, work):
        path = self.state_dir / f"{work['kind']}-{work['subject_id']}.json"
        temporary = path.with_suffix('.tmp')
        write_text(temporary, json.dumps(work, ensure_ascii=False))
        temporary.replace(path)

    def call(self, work, name, path, body):
        call = work.setdefault('calls', {}).get(name)
        if call is None:
            call = {'path': path, 'body': dict(body, request_id=str(uuid4()))}
            work['calls'][name] = call
            self.save(work)
        if 'response' not in call:
            call['response'] = self.client.post(call['path'], call['body'])
            self.save(work)
        return call['response']

    def publish(self, kind, subject_id, document, report_text, evidence_ids):
        work = self.load(kind, subject_id)
        if work is None:
            work = {'kind': kind, 'subject_id': subject_id, 'report_id': str(uuid4()),
                    'document': document, 'report_text': report_text,
                    'evidence_ids': evidence_ids, 'model_version': self.model_version}
            self.save(work)
        if work.get('done'):
            return work['report_id']
        task = self.call(work, 'task', '/tasks', {
            'task_kind': CAPABILITY, 'business_key': 'llm-report:' + kind + ':' + subject_id,
            'capability_code': CAPABILITY, 'task_mode': 'once',
            'input': {'kind': kind, kind + '_id': subject_id}, 'parameters': {},
            'requested_outputs': [RESULT_TYPE]})
        run = self.call(work, 'start', '/tasks/start', {
            'task_id': task['task_id'], 'expected_revision': task['revision']})
        self.call(work, 'report', '/reports/register', {
            'report_id': work['report_id'], 'subject_kind': kind, 'subject_id': subject_id,
            'report_type': REPORT_TYPE, 'completeness': 'partial',
            'coverage': {'schema_version': '1', 'completed': [], 'gaps': []},
            'task_id': run['task_id'], 'run_id': run['run_id'],
            'model_version': work['model_version'], 'report_json': work['document'],
            'report_text': work['report_text'], 'evidence_ids': work['evidence_ids']})
        self.call(work, 'end', '/tasks/end', {
            'task_id': run['task_id'], 'run_id': run['run_id'],
            'expected_revision': run['revision'], 'state': 'succeeded',
            'outputs': [{'result_type': RESULT_TYPE, 'schema_version': '1',
                         'producer_result_key': work['report_id'],
                         'payload': {'report_id': work['report_id'],
                                     'subject_kind': kind, 'subject_id': subject_id}}]})
        work['done'] = True
        self.save(work)
        return work['report_id']
