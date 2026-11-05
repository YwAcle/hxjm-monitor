import test from 'node:test';
import assert from 'node:assert/strict';
import { createBusinessApi } from './businessApi.js';

test('garbage page uses public Business endpoints without robot protocol fields', async () => {
  const calls = [];
  const api = createBusinessApi({ fetchImpl: async (url, options) => {
    calls.push({ url, ...options });
    return { ok: true, json: async () => ({ items: [], task_id: 'task' }) };
  } });
  await api.garbageEvents();
  await api.cleanupGarbage({ event_id: 'event', request_id: 'request' });
  assert.equal(calls[0].url, '/api/v1/business/garbage/events');
  assert.equal(calls[0].method, 'GET');
  assert.equal(calls[1].url, '/api/v1/business/garbage/cleanup');
  assert.deepEqual(JSON.parse(calls[1].body), { event_id: 'event', request_id: 'request' });
  assert.equal(calls[1].credentials, 'omit');
});
