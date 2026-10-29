import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createBusinessApi } from './businessApi.js';

function fixture(replies) {
  const calls = [];
  const values = new Map();
  const api = createBusinessApi({
    storage: { getItem: key => values.get(key), setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) },
    fetchImpl: async (url, options) => {
      calls.push({ url, ...options });
      const [status, body] = replies.shift();
      return { status, ok: status >= 200 && status < 300, json: async () => body };
    },
  });
  return { api, calls, values };
}

test('business queries need no login and ignore stored tokens', async () => {
  const { api, calls } = fixture([[200, { items: [] }], [200, { items: [] }]]);
  await api.sources();
  await api.results({ source_id: 'source' });
  assert.equal(calls[0].url, '/api/v1/business/sources?page_size=200');
  for (const call of calls) {
    assert.equal(call.headers.Authorization, undefined);
    assert.equal(call.headers['X-HXJM-Service-Token'], undefined);
    assert.equal(call.credentials, 'omit');
  }
  assert.equal(api.login, undefined);
});

test('server errors retain status and trace without switching to login', async () => {
  const { api } = fixture([[403, { error: { code: 'FORBIDDEN', message: '禁止访问' }, trace_id: 't' }]]);
  await assert.rejects(api.results({}), error => error.status === 403 && error.code === 'FORBIDDEN' && error.traceId === 't');
});

test('playback tickets accept only unexpired same-origin links without login', async () => {
  const id = '10000000-0000-4000-8000-000000000001';
  const expiry = new Date(Date.now() + 60_000).toISOString();
  const { api, calls } = fixture([
    [200, { url: `/api/v1/business/assets/${id}/content?ticket=example`, expires_at: expiry }],
    [200, { url: 'https://elsewhere.example/video', expires_at: expiry }]]);
  assert.match((await api.playbackTicket(id)).url, /content\?ticket=/);
  assert.equal(calls[0].headers.Authorization, undefined);
  await assert.rejects(api.playbackTicket(id), error => error.code === 'INVALID_RESPONSE');
});

test('source catalogue follows pagination and rejects a repeated cursor', async () => {
  const { api, calls } = fixture([
    [200, { items: [{ source_id: 'a' }], has_more: true, next_cursor: 'next+/' }],
    [200, { items: [{ source_id: 'b' }], has_more: false }]]);
  assert.deepEqual((await api.sources()).items.map(item => item.source_id), ['a', 'b']);
  assert.match(calls[1].url, /cursor=next%2B%2F/);
  const repeated = fixture([
    [200, { items: [], has_more: true, next_cursor: 'same' }],
    [200, { items: [], has_more: true, next_cursor: 'same' }]]).api;
  await assert.rejects(repeated.sources(), error => error.code === 'INVALID_RESPONSE');
});

test('image upload, enrollment and candidate selection work without credentials', async () => {
  const { api, calls } = fixture([
    [200, { asset_id: 'image', state: 'available' }],
    [200, { identity_id: 'person' }],
    [200, { query_id: 'query', state: 'pending' }],
    [200, { query_id: 'query', state: 'pending' }]]);
  const file = new Blob(['image bytes'], { type: 'image/jpeg' });
  await api.uploadImage(file, { request_id: 'upload', asset_id: 'image', purpose: 'query', source_id: null });
  assert.equal(calls[0].url, '/api/v1/business/assets/upload');
  assert.equal(calls[0].headers['Content-Type'], undefined);
  assert.ok(calls[0].body instanceof FormData);
  assert.equal(calls[0].body.get('purpose'), 'query');
  assert.equal(calls[0].body.get('source_id'), null);
  await api.registerIdentity({ identity_id: 'person' });
  await api.createQuery({ query_id: 'query', input_asset_id: 'image' });
  await api.selectCandidate({ query_id: 'query', candidate_id: 'person', expected_revision: 2 });
  assert.equal(calls[1].url, '/api/v1/business/identities/register');
  assert.equal(calls[2].url, '/api/v1/business/queries');
  assert.equal(calls[3].url, '/api/v1/business/queries/select');
  assert.equal(JSON.parse(calls[3].body).expected_revision, 2);
  for (const call of calls) {
    assert.equal(call.headers.Authorization, undefined);
    assert.equal(call.headers['X-HXJM-Service-Token'], undefined);
  }
});

function candidateSelection(api) {
  const source = readFileSync(new URL('../components/BusinessPanel/BusinessObjects.jsx', import.meta.url), 'utf8');
  const handler = source.match(/const choose = async candidate => \{([\s\S]*?)\n  \};/)[1];
  let query = { query_id: 'query', state: 'waiting_input', revision: 3 }, busy = false, nextId = 0;
  const requests = { current: null }, errors = [];
  const choose = () => new Function('busy', 'query', 'selectionRequest', 'id', 'businessApi', 'setBusy', 'setQuery', 'onError',
    `return async candidate => {${handler}}`)(busy, query, requests, () => `request-${++nextId}`, api,
      value => { busy = value; }, value => { query = typeof value === 'function' ? value(query) : value; },
      error => errors.push(error))({ candidate_id: 'person-2' });
  return { choose, errors, current: () => query, busy: () => busy };
}

test('successful candidate selection remains pending when the immediate refresh fails', async () => {
  const failure = new Error('refresh unavailable');
  const selection = candidateSelection({
    selectCandidate: async () => ({ query_id: 'query', state: 'pending', revision: 4 }),
    query: async () => { throw failure; },
  });
  await selection.choose();
  assert.equal(selection.current().state, 'pending');
  assert.equal(selection.current().revision, 4);
  assert.equal(selection.busy(), false);
  assert.deepEqual(selection.errors, [failure]);
});

test('retrying a candidate selection after a lost response keeps the logical request identifier', async () => {
  const submitted = [];
  const selection = candidateSelection({
    selectCandidate: async body => {
      submitted.push(body);
      if (submitted.length === 1) throw new Error('response lost');
      return { query_id: 'query', state: 'pending', revision: 4 };
    },
    query: async () => ({ query_id: 'query', state: 'succeeded', revision: 5, hits: [] }),
  });
  await selection.choose();
  await selection.choose();
  assert.equal(submitted.length, 2);
  assert.deepEqual(submitted[1], submitted[0]);
  assert.equal(selection.current().state, 'succeeded');
});
