import test from 'node:test';
import assert from 'node:assert/strict';
import {
  historicalWindow,
  matchHistoricalFrame,
  historicalDetections,
  loadHistoricalWindow,
} from './historicalResults.js';

const asset = {
  asset_id: 'asset-a',
  source_id: 'source-a',
  stream_session_id: 'session-a',
  start_at: '2026-10-27T10:00:00+08:00',
};

function frame(mediaPts, values = {}) {
  return { frame_id: `frame-${mediaPts}`, media_asset_id: asset.asset_id, media_pts_ms: mediaPts,
    targets: [{ bbox: [0.1, 0.2, 0.3, 0.7], confidence: 0.9 }], ...values };
}

test('historical windows use disjoint five-second media ranges', () => {
  assert.deepEqual(historicalWindow(4.999), { key: '0:5000', start_ms: 0, end_ms: 5000 });
  assert.deepEqual(historicalWindow(5), { key: '5000:10000', start_ms: 5000, end_ms: 10000 });
  assert.equal(historicalWindow(-1), null);
  assert.throws(() => historicalWindow(1, 0), TypeError);
});

test('match uses asset and exact media PTS with at most a millisecond rounding tolerance', () => {
  const earlier = frame(1000);
  const exact = frame(1040);
  const items = [earlier, frame(1040, { media_asset_id: 'another-asset' }), exact];
  assert.equal(matchHistoricalFrame(items, asset.asset_id, 1.04), exact);
  assert.equal(matchHistoricalFrame(items, asset.asset_id, 1.0409), exact);
  assert.equal(matchHistoricalFrame(items, asset.asset_id, 1.0411), null);
  assert.equal(matchHistoricalFrame(items, 'another-asset', 1), null);
});

test('an unprocessed frame has no match and never carries previous boxes forward', () => {
  const items = [frame(1000)];
  assert.equal(matchHistoricalFrame(items, asset.asset_id, 1), items[0]);
  assert.equal(matchHistoricalFrame(items, asset.asset_id, 1.02), null);
  assert.equal(matchHistoricalFrame([frame(null)], asset.asset_id, 0), null);
});

test('zero-target frames remain matches and UUID tracklets never become drawing track IDs', () => {
  const empty = frame(1000, { targets: [] });
  assert.equal(matchHistoricalFrame([empty], asset.asset_id, 1), empty);
  assert.deepEqual(historicalDetections(empty), []);
  const detection = frame(1000, { targets: [
    { bbox: [0.1, 0.2, 0.3, 0.7], confidence: null,
      tracklet_id: '10000000-0000-4000-8000-000000000001' },
    { bbox: [0, 0, 1, 1], confidence: 0.95, track_id: 12 },
    { bbox: [0.3, 0, 0.2, 1], confidence: 0.9 },
  ] });
  assert.deepEqual(historicalDetections(detection), [
    { bbox: [0.1, 0.2, 0.3, 0.7], confidence: null },
    { bbox: [0, 0, 1, 1], confidence: 0.95, track_id: 12 },
  ]);
});

test('window loading exhausts pages, retains the abort signal and filters other assets', async () => {
  const controller = new AbortController();
  const calls = [];
  const pages = [
    { items: [frame(5000), frame(5000, { media_asset_id: 'other' })], has_more: true, next_cursor: 'page-2' },
    { items: [frame(5040)], has_more: true, next_cursor: 'page-3' },
    { items: [frame(5080)], has_more: false, next_cursor: null },
  ];
  const api = { results: async (query, signal) => {
    calls.push({ query, signal });
    return pages[calls.length - 1];
  } };
  const items = await loadHistoricalWindow(api, asset, historicalWindow(5), controller.signal);
  assert.deepEqual(items.map(item => item.media_pts_ms), [5000, 5040, 5080]);
  assert.equal(calls.length, 3);
  assert.deepEqual(calls[0].query, {
    source_id: 'source-a', stream_session_id: 'session-a',
    start_at: '2026-10-27T02:00:04.999Z', end_at: '2026-10-27T02:00:10.001Z',
    result_type: 'detection.frame', page_size: 200,
  });
  assert.equal(calls[1].query.cursor, 'page-2');
  assert.equal(calls[2].query.cursor, 'page-3');
  assert.ok(calls.every(call => call.signal === controller.signal));
});

test('query padding retains rounded PTS on both window edges without a negative start', async () => {
  const items = [frame(0), frame(4999), frame(5000)];
  const calls = [];
  const api = { results: async query => {
    calls.push(query);
    const start = Date.parse(query.start_at) - Date.parse(asset.start_at);
    const end = Date.parse(query.end_at) - Date.parse(asset.start_at);
    return { items: items.filter(item => item.media_pts_ms >= start && item.media_pts_ms < end),
      has_more: false };
  } };
  const left = await loadHistoricalWindow(api, asset, historicalWindow(4.9998));
  assert.equal(matchHistoricalFrame(left, asset.asset_id, 4.9998)?.media_pts_ms, 5000);
  assert.equal(calls[0].start_at, '2026-10-27T02:00:00.000Z');
  const right = await loadHistoricalWindow(api, asset, historicalWindow(5.0001));
  assert.equal(matchHistoricalFrame(right.filter(item => item.media_pts_ms !== 5000),
    asset.asset_id, 5)?.media_pts_ms, 4999);
});

test('pagination rejects missing and repeated cursors instead of returning partial data', async () => {
  await assert.rejects(loadHistoricalWindow({ results: async () => ({
    items: [], has_more: true, next_cursor: null,
  }) }, asset, historicalWindow(0)), /游标/);
  let calls = 0;
  await assert.rejects(loadHistoricalWindow({ results: async () => {
    calls += 1;
    return { items: [], has_more: true, next_cursor: 'same' };
  } }, asset, historicalWindow(0)), /游标/);
  assert.equal(calls, 2);
});

test('already-aborted loading never calls the API', async () => {
  const controller = new AbortController();
  controller.abort();
  let calls = 0;
  await assert.rejects(loadHistoricalWindow({ results: async () => { calls += 1; } },
    asset, historicalWindow(0), controller.signal), { name: 'AbortError' });
  assert.equal(calls, 0);
});

test('abort during loading discards the partial window without requesting another page', async () => {
  const controller = new AbortController();
  let calls = 0;
  await assert.rejects(loadHistoricalWindow({ results: async () => {
    calls += 1;
    controller.abort();
    return { items: [frame(0)], has_more: true, next_cursor: 'page-2' };
  } }, asset, historicalWindow(0), controller.signal), { name: 'AbortError' });
  assert.equal(calls, 1);
});
