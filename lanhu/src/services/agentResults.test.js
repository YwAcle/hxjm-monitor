import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { collectAgentResults, agentResultItems } from './agentResults.js';

const directory = { type: 'person_directory', items: [{ identity_id: 'person-1', display_name: '张三' }], has_more: true, next_cursor: 'opaque' };
const events = { type: 'event_search', items: [{ event_type: 'fall', conclusion_json: { description: '跌倒记录' } }] };

test('普通响应保留全部结果顺序，并去除最后结果的别名副本', () => {
  assert.deepEqual(collectAgentResults({ type: 'normal', results: [directory, events], data: events, result: events }), [directory, events]);
  assert.deepEqual(collectAgentResults({ type: 'normal', text: '普通回答' }), []);
  assert.deepEqual(collectAgentResults({ data: directory }), [directory]);
});
test('多次SSE结果保留查询及后续报告，不混淆候选与命中', () => {
  const pending = { type: 'person_query', query_id: 'query-1', state: 'waiting_input', candidates: [{ candidate_id: 'stable-A' }], hits: [] };
  const done = { type: 'person_query', query_id: 'query-1', state: 'succeeded', candidates: [], hits: [{ identity_id: 'person-1' }] };
  assert.equal(agentResultItems(pending)[0].candidate_id, 'stable-A');
  assert.equal(agentResultItems(done)[0].identity_id, 'person-1');
  assert.deepEqual(collectAgentResults(done, collectAgentResults(pending)), [pending, done]);
});
test('结构化卡片展示业务内容、缺口及分页，不把全部事件称为异常', async t => {
  const server = await createServer({ configFile: false, root: new URL('../../', import.meta.url).pathname,
    server: { middlewareMode: true }, appType: 'custom' });
  t.after(() => server.close());
  const { default: Cards } = await server.ssrLoadModule('/src/components/RightSidebar/AgentBusinessResults.jsx');
  const render = results => renderToStaticMarkup(React.createElement(Cards, { results }));
  const html = render([directory, events, { type: 'person_tracklets', items: [{ source_name: '门口', first_observed_at: '2026-10-28T10:00:00+08:00', last_observed_at: '2026-10-28T10:00:00+08:00' }], coverage_json: { gaps: [{}] } }]);
  for (const text of ['张三', '后续记录', '跌倒记录', '门口', '处理缺口']) assert.ok(html.includes(text), text);
  assert.doesNotMatch(html, /异常|opaque|next_cursor/);
  assert.doesNotMatch(render([{ type: 'unknown', data: { secret: 'raw-json' } }]), /raw-json/);
  const image = render(collectAgentResults({ type: 'super_resolution', data: { image_base64: 'data:image/png;base64,aGVsbG8=', result_size: [100, 200], scale: 2 } }));
  assert.match(image, /图片放大结果/); assert.match(image, /100×200/); assert.match(image, /2倍/);
  const selection = render([{ type: 'person_query', state: 'waiting_input', candidates: [{ candidate_id: 'stable-A' }] }]);
  assert.match(selection, /选择第二个/); assert.match(selection, /图片目标 1/);
  const report = render([{ type: 'report_search', items: [{ report_id: 'r', revision: 2, completeness: 'partial', report_json: { route: [{ source_id: 's', recordings: [{ asset_id: 'a', state: 'available' }, { asset_id: 'b', state: 'available' }] }] } }] }]);
  assert.match(report, /播放分段 1/); assert.match(report, /播放分段 2/); assert.match(report, /报告覆盖不完整/);
  const evidence = render([{ type: 'report_search', items: [{ report_type: 'event_analysis', evidence: [{ asset_id: 'evidence-asset' }] }] }]);
  assert.match(evidence, /1\. event_analysis/); assert.match(evidence, /播放分段 1/);
});
