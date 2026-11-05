import test from 'node:test';
import assert from 'node:assert/strict';
import { confirmedJoyAlarms, joyAlarmCards, queryJoyAlarms } from './joyaiAlarms.js';

test('pending, rejected, expired and conflicting verdicts never appear as confirmed alarms', () => {
  const row = { report_type: 'joyai_anomaly_review', subject_kind: 'event',
    expires_at: new Date(Date.now() + 60000).toISOString(), report_json: {
      confirmed: true, event_type: 'fight', joyai: { decision: 'confirmed', kind: 'fight' },
      review: { decision: 'confirmed', kind: 'fight' } } };
  assert.deepEqual(confirmedJoyAlarms([row]), [row]);
  for (const decision of ['uncertain', 'rejected', 'awaiting_review']) {
    const pending = structuredClone(row); pending.report_json.review.decision = decision;
    assert.deepEqual(confirmedJoyAlarms([pending]), []);
  }
  const mismatch = structuredClone(row); mismatch.report_json.joyai.kind = 'fall';
  const expired = { ...row, expires_at: new Date(0).toISOString() };
  assert.deepEqual(confirmedJoyAlarms([mismatch, expired]), []);
});

test('report queries include review outcomes and skip unrelated reports across pages', async () => {
  const accepted = { report_type: 'joyai_anomaly_review', subject_kind: 'event',
    expires_at: new Date(Date.now() + 60000).toISOString(), report_json: {
      confirmed: true, event_type: 'fall', joyai: { decision: 'confirmed', kind: 'fall' },
      review: { decision: 'confirmed', kind: 'fall' } } };
  const requests = [];
  const api = { searchReports: async body => {
    requests.push(body);
    return body.cursor ? { items: [accepted], has_more: false }
      : { items: [{ ...accepted, report_type: 'other' }], has_more: true, next_cursor: 'page2' };
  } };
  assert.deepEqual(await queryJoyAlarms(undefined, api), [accepted]);
  assert.equal(requests.length, 2);
  assert.equal(requests[0].end_at, requests[1].end_at);
});

test('suspected events show individual progress and become one red card only after agreement', () => {
  const job = { id: 'candidate', camera_id: 'camera_1', camera_name: '1号摄像头',
    event_type: 'fight', occurred_at: new Date().toISOString(), state: 'collecting' };
  const status = { pending_events: [job], reviewer: { state: 'stopped' } };
  let cards = joyAlarmCards([], status);
  assert.equal(cards[0].alarm_state, 'suspected');
  assert.equal(cards[0].review_stage, '正在收集视频');
  assert.equal(cards[0].report_json.video_asset_id, undefined);
  job.state = 'awaiting_review';
  assert.equal(joyAlarmCards([], status)[0].review_stage, '等待复核');
  job.state = 'reviewing'; status.reviewer.state = 'starting';
  assert.equal(joyAlarmCards([], status)[0].review_stage, '正在加载复核模型');
  status.reviewer.state = 'reviewing';
  assert.equal(joyAlarmCards([], status)[0].review_stage, '正在复核');
  job.state = 'registering';
  assert.equal(joyAlarmCards([], status)[0].alarm_state, 'suspected');
  const report = { report_id: 'report', subject_id: 'event', report_type: 'joyai_anomaly_review',
    subject_kind: 'event', expires_at: new Date(Date.now() + 60000).toISOString(),
    report_json: { candidate_id: job.id, confirmed: true, event_type: 'fight',
      joyai: { decision: 'confirmed', kind: 'fight' }, review: { decision: 'confirmed', kind: 'fight' } } };
  cards = joyAlarmCards([report], status);
  assert.equal(cards.length, 1);
  assert.equal(cards[0].alarm_id, 'candidate');
  assert.equal(cards[0].alarm_state, 'confirmed');
  const legacy = structuredClone(report); delete legacy.report_json.candidate_id;
  job.report_id = 'report';
  assert.equal(joyAlarmCards([legacy], status).length, 1);
  delete job.report_id; job.event_id = 'event';
  assert.equal(joyAlarmCards([legacy], status).length, 1);
});

test('rejection, disagreement, failure and expiry cannot appear as confirmed', async () => {
  const base = { report_type: 'joyai_anomaly_review', subject_kind: 'event',
    expires_at: new Date(Date.now() + 60000).toISOString(), report_json: {
      event_type: 'fall', confirmed: false, joyai: { decision: 'confirmed', kind: 'fall' },
      review: { decision: 'rejected', kind: 'none' } } };
  const rejected = { ...base, report_id: 'rejected' };
  const uncertain = structuredClone(base); uncertain.report_id = 'uncertain';
  uncertain.report_json.review.decision = 'uncertain';
  const mismatch = structuredClone(base); mismatch.report_id = 'mismatch';
  mismatch.report_json.confirmed = true;
  mismatch.report_json.review = { decision: 'confirmed', kind: 'fight' };
  const expired = { ...base, expires_at: new Date(0).toISOString() };
  const api = { searchReports: async () => ({ items: [rejected, uncertain, mismatch, expired] }) };
  const reports = await queryJoyAlarms(undefined, api);
  assert.deepEqual(joyAlarmCards(reports, null).map(row => row.alarm_state), ['excluded', 'uncertain', 'uncertain']);
  const status = { pending_events: [{ id: 'retry', event_type: 'fall', state: 'awaiting_review', error: 'timeout' }] };
  const [retry] = joyAlarmCards([], status);
  assert.equal(retry.alarm_state, 'suspected');
  assert.equal(retry.review_stage, '处理失败，等待重试');
});

test('all eight queued candidates remain visible alongside saved reports', () => {
  const pending_events = Array.from({ length: 8 }, (_, i) => ({ id: `job${i}`, event_type: 'fall',
    state: 'awaiting_review', occurred_at: new Date(1000 + i).toISOString() }));
  const cards = joyAlarmCards([], { pending_events });
  assert.equal(cards.length, 8);
  assert.equal(cards[0].alarm_id, 'job7');
});

test('manual re-review replaces the original card while keeping its event identity', () => {
  const row = { report_id: 'original-report', subject_id: 'same-event', report_type: 'joyai_anomaly_review',
    subject_kind: 'event', expires_at: new Date(Date.now() + 60000).toISOString(), report_json: {
      candidate_id: 'root', confirmed: true, event_type: 'fall', joyai: { decision: 'confirmed', kind: 'fall' },
      review: { decision: 'confirmed', kind: 'fall' } } };
  const status = { reviewer: { state: 'starting' }, pending_events: [{ id: 'attempt',
    root_candidate_id: 'root', manual_review: true, previous_report_id: 'original-report',
    event_id: 'same-event', event_type: 'fall', state: 'reviewing' }] };
  const cards = joyAlarmCards([row], status);
  assert.equal(cards.length, 1);
  assert.equal(cards[0].alarm_id, 'root');
  assert.equal(cards[0].alarm_state, 'suspected');
  assert.equal(cards[0].review_stage, '重新复核 · 正在加载复核模型');
  const reviewed = { ...row, report_id: 'new-report', report_type: 'joyai_anomaly_review:attempt' };
  assert.equal(joyAlarmCards([reviewed], null)[0].alarm_state, 'confirmed');
  status.pending_events[0].state = 'blocked';
  status.pending_events[0].error = '复核失败';
  const failed = joyAlarmCards([row], status);
  assert.equal(failed.length, 1);
  assert.equal(failed[0].alarm_state, 'uncertain');
  assert.equal(failed[0].report_id, 'original-report');
});

test('the latest review of the same event replaces its old report in the card query', async () => {
  const row = { subject_id: 'same-event', subject_kind: 'event',
    expires_at: new Date(Date.now() + 60000).toISOString(), report_json: {
      event_type: 'fall', review: { decision: 'uncertain' } } };
  const latest = { ...row, report_id: 'new', report_type: 'joyai_anomaly_review:attempt' };
  const original = { ...row, report_id: 'old', report_type: 'joyai_anomaly_review' };
  const api = { searchReports: async () => ({ items: [latest, original], has_more: false }) };
  assert.deepEqual(await queryJoyAlarms(undefined, api), [latest]);
});

test('right monitoring reports omit anomaly reports and keep personnel reports', async () => {
  const { monitoringReports } = await import('./monitorReports.js');
  const person = { id: 'person', prompt_type: 'reid', report_json: { event_type: 'stranger' } };
  const other = { id: 'other', prompt_type: 'analysis', report_text: '普通监控报告' };
  assert.deepEqual(monitoringReports([person, other,
    { report_json: { event_type: 'fight' } },
    { report_type: 'joyai_anomaly_review:attempt' }, { report_json: { event_type: 'fall' } },
  ]), [person, other]);
});

test('restart action sends only the selected report and displays backend errors', async () => {
  const { restartJoyReview } = await import('./joyaiAlarms.js');
  const previous = globalThis.fetch;
  try {
    globalThis.fetch = async (url, options) => {
      assert.equal(url, '/api/v1/business/behavior/reviews');
      assert.equal(options.method, 'POST');
      assert.deepEqual(JSON.parse(options.body), { report_id: 'selected' });
      assert.equal(options.headers['X-JoyAI-Token'], undefined);
      return { ok: true, json: async () => ({ status: 'running', pending_reviews: 1 }) };
    };
    assert.equal((await restartJoyReview('selected')).pending_reviews, 1);
    globalThis.fetch = async () => ({ ok: false, json: async () => ({ detail: '原视频片段不存在或已过期' }) });
    await assert.rejects(restartJoyReview('selected'), /原视频片段不存在或已过期/);
  } finally { globalThis.fetch = previous; }
});

test('fire remains in monitoring reports', async () => {
  const { monitoringReports } = await import('./monitorReports.js');
  const fire = { prompt_type: 'vad', vad_id: 'fire', report_json: { event_type: 'fire' } };
  assert.deepEqual(monitoringReports([fire]), [fire]);
});
