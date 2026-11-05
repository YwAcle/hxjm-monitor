import { createBusinessApi } from './businessApi.js';

export function confirmedJoyAlarms(items) {
  return items.filter(row => (row.report_type === 'joyai_anomaly_review' || row.report_type?.startsWith('joyai_anomaly_review:'))
    && row.subject_kind === 'event' && row.report_json?.confirmed === true
    && row.report_json.joyai?.decision === 'confirmed' && row.report_json.review?.decision === 'confirmed'
    && ['fight', 'fall'].includes(row.report_json.event_type)
    && row.report_json.joyai.kind === row.report_json.event_type
    && row.report_json.review.kind === row.report_json.event_type
    && Date.parse(row.expires_at) > Date.now());
}

export function joyAlarmCards(reports, status) {
  const pendingEvents = status?.pending_events || [];
  const saved = reports.filter(row => !pendingEvents.some(job => job.manual_review
    && (job.event_id === row.subject_id || job.root_candidate_id === row.report_json.candidate_id)))
    .map(row => ({ ...row,
    alarm_id: row.report_json.candidate_id || row.subject_id || row.report_id,
    alarm_state: confirmedJoyAlarms([row]).length ? 'confirmed'
      : row.report_json.review?.decision === 'rejected' ? 'excluded' : 'uncertain',
  }));
  const stages = { collecting: '正在收集视频', awaiting_review: '等待复核',
    reviewing: status?.reviewer?.state === 'starting' ? '正在加载复核模型' : '正在复核',
    registering: '复核完成，正在保存结果', blocked: '处理失败，可重新提交', incomplete: '视频不完整，可重新提交' };
  const pending = pendingEvents.filter(job => stages[job.state]
    && ['fight', 'fall'].includes(job.event_type)
    && !saved.some(row => row.report_json.candidate_id === job.id
      || (job.report_id && row.report_id === job.report_id)
      || (job.event_id && row.subject_id === job.event_id)))
    .map(job => ({ alarm_id: job.root_candidate_id || job.id,
      alarm_state: ['blocked', 'incomplete'].includes(job.state) ? 'uncertain' : 'suspected',
      report_id: ['blocked', 'incomplete'].includes(job.state) ? job.previous_report_id : undefined,
      review_stage: (job.manual_review ? '重新复核 · ' : '') + (job.error ? '处理失败，等待重试' : stages[job.state]),
      report_json: { ...job, candidate_id: job.root_candidate_id || job.id, confirmed: false,
        review: { reason: job.observation }, processing_error: job.error },
    })).sort((a, b) => Date.parse(b.report_json.occurred_at) - Date.parse(a.report_json.occurred_at));
  return [...pending, ...saved];
}

export async function queryJoyAlarms(signal, api = createBusinessApi()) {
  const end = new Date(), start = new Date(end.getTime() - 7 * 86400000);
  const rows = [], cursors = new Set();
  let cursor;
  do {
    const response = await api.searchReports({ start_at: start.toISOString(), end_at: end.toISOString(),
      limit: 100, ...(cursor ? { cursor } : {}) }, signal);
    for (const row of (response.items || []).filter(row => (row.report_type === 'joyai_anomaly_review'
      || row.report_type?.startsWith('joyai_anomaly_review:'))
      && row.subject_kind === 'event' && ['fight', 'fall'].includes(row.report_json?.event_type)
      && ['confirmed', 'rejected', 'uncertain'].includes(row.report_json.review?.decision)
      && Date.parse(row.expires_at) > Date.now())) {
      if (!rows.some(saved => saved.subject_id && saved.subject_id === row.subject_id)) rows.push(row);
    }
    if (rows.length >= 5 || !response.has_more) return rows.slice(0, 5);
    if (typeof response.next_cursor !== 'string' || !response.next_cursor || cursors.has(response.next_cursor)) {
      throw new Error('异常报告分页游标无效');
    }
    cursor = response.next_cursor;
    cursors.add(cursor);
  } while (true);
}

export async function restartJoyReview(reportId) {
  const response = await fetch('/api/v1/business/behavior/reviews', {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify({ report_id: reportId }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : data.error?.message || '重新复核失败，请稍后重试');
  return data;
}

export async function queryBehaviorStatus(signal) {
  const response = await fetch('/api/v1/business/behavior/status', { signal, cache: 'no-store' });
  const body = await response.json();
  if (!response.ok || body.error) throw new Error(body.error?.message || '异常监控未连接');
  return body;
}

export async function queryReviewHistory(eventId, signal, api = createBusinessApi()) {
  const items = [];
  let cursor = {};
  do {
    const page = await api.reports({ subject_kind: 'event', subject_id: eventId, ...cursor }, signal);
    items.push(...(page.items || []));
    cursor = page.has_more ? page.next_cursor : null;
  } while (cursor);
  return items.filter(row => row.report_type?.startsWith('joyai_anomaly_review'));
}
