import test from 'node:test';
import assert from 'node:assert/strict';
import { resolveReportPlayback } from './reportPlayback.js';

test('structured reports open recording assets instead of obsolete playback URLs', async () => {
  const result = await resolveReportPlayback({
    record_url: 'http://old.example/get',
    report_json: { route: [{ source_id: 'camera', stream_session_id: 'session', recordings: [
      { asset_id: 'pending', state: 'preparing' },
      { asset_id: 'recording', state: 'available', start_at: '2026-10-28T03:51:49.739Z', first_media_pts_ms: 120 },
    ] }] },
  }, {});
  assert.equal(result.playback.asset_id, 'recording');
  assert.equal(result.playback.offset_ms, 120);
  assert.equal(result.playback.source_id, 'camera');
  assert.equal(result.playback.stream_session_id, 'session');
  assert.equal(result.url, undefined);
});

test('Agent reports reuse the current structured report for the same activity without inventing a time range', async () => {
  const calls = [];
  const result = await resolveReportPlayback({ episode_id: 'activity', record_url: 'http://old.example/get' }, {
    async reports(body) {
      calls.push(body);
      return { items: [{ report_json: { route: [{ source_id: 'camera', recordings: [
        { asset_id: 'recording', state: 'available', first_media_pts_ms: 120 },
      ] }] } }] };
    },
  });
  assert.equal(result.playback.asset_id, 'recording');
  assert.deepEqual(calls, [{ subject_kind: 'activity', subject_id: 'activity' }]);
  assert.equal(result.playback.offset_ms, 120);
});

test('missing new recordings do not fall back to the obsolete recording service', async () => {
  await assert.rejects(resolveReportPlayback({ episode_id: 'activity', record_url: 'http://old.example/get' }, {
    reports: async () => ({ items: [] }),
  }), /录像暂不可用/);
  await assert.rejects(resolveReportPlayback({ report_json: { route: [] }, record_url: 'http://old.example/get' }, {}), /录像暂不可用/);
});

test('standalone legacy reports keep their explicit video URL', async () => {
  assert.deepEqual(await resolveReportPlayback({ record_url: '/video.mp4' }, {}), { url: '/video.mp4' });
});
