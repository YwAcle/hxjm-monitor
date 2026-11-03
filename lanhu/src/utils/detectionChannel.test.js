import assert from 'node:assert/strict';
import test from 'node:test';
import { DetectionChannel } from './detectionChannel.js';

const status = (id, changes = {}) => ({
  type: 'status', camera_id: id, task: 'deepsort', service_session_id: 'service',
  stream_session_id: `${id}-a`, session_generation: 0, stream_epoch: 1,
  component: 'service', state: 'ready', components: {
    capture: { state: 'streaming' }, analyzer: { state: 'ready' },
  }, ...changes,
});
const result = (id, changes = {}) => ({ ...status(id), type: 'detections',
  frame_id: 1, frame_ts_ms: 1000, sent_at_ms: 1100, valid_for_ms: 2000,
  detections: [], ...changes,
});

test('four channels route by both camera and task and expire independently', () => {
  const channels = [1, 2, 3, 4].map(i => new DetectionChannel(`camera_${i}`));
  channels.forEach(c => c.accept(status(c.cameraId), 0));
  for (const channel of channels) {
    assert.equal(channel.accept(result(channel.cameraId), 0), true);
    assert.equal(channel.accept(result('unknown'), 0), false);
    assert.equal(channel.accept(result(channel.cameraId, { task: 'other' }), 0), false);
    assert.equal(channel.result.camera_id, channel.cameraId);
  }
  assert.equal(channels[0].expire(2000), true);
  assert.equal(channels[0].result, null);
  assert.ok(channels[1].result);
});

test('worker session replacement rejects old status/results and requires authoritative status', () => {
  const c = new DetectionChannel('camera_1');
  assert.equal(c.accept(result('camera_1'), 0), false);
  c.accept(status('camera_1'), 0);
  c.accept(result('camera_1'), 0);
  const restart = { stream_session_id: 'camera_1-b', session_generation: 1 };
  assert.equal(c.accept(result('camera_1', restart), 0), false);
  assert.equal(c.accept(status('camera_1', { ...restart, state: 'worker_timeout' }), 0), true);
  assert.equal(c.result, null);
  assert.equal(c.accept(status('camera_1'), 0), false);
  assert.equal(c.accept(result('camera_1', { frame_id: 999 }), 0), false);
  c.accept(status('camera_1', restart), 0);
  assert.equal(c.accept(result('camera_1', restart), 0), true);
  assert.equal(c.accept(status('camera_1', { service_session_id: 'older-service', session_generation: 9 }), 0), false);
});

test('stream reconnect clears overlay; rejects old epoch and duplicate frames', () => {
  const c = new DetectionChannel('camera_1');
  c.accept(status('camera_1'), 0);
  c.accept(result('camera_1'), 0);
  c.accept(status('camera_1', { stream_epoch: 2 }), 0);
  assert.equal(c.result, null);
  assert.equal(c.accept(result('camera_1', { frame_id: 999 }), 0), false);
  assert.equal(c.accept(result('camera_1', { stream_epoch: 2, frame_id: 2 }), 0), true);
  assert.equal(c.accept(result('camera_1', { stream_epoch: 2, frame_id: 2 }), 0), false);
  c.reset('AI 已断开');
  assert.equal(c.result, null);
});

test('owner disconnect clears results and history while raw video is independent', () => {
  const c = new DetectionChannel('camera_1');
  c.accept(status('camera_1'), 0);
  c.accept(result('camera_1'), 0);
  assert.equal(c.aiStatus, '检测正常');
  c.reset('服务离线，正在重连');
  assert.equal(c.latestRef.current, null);
  assert.deepEqual(c.historyRef.current, []);
  assert.equal(c.result, null);
  assert.equal(c.aiStatus, '服务离线，正在重连');
  assert.equal(c.accept(result('camera_1', { frame_id: 2 }), 10), false);
});

test('expired detections cannot be kept healthy by status heartbeats', () => {
  const c = new DetectionChannel('camera_1');
  c.accept(status('camera_1'), 0);
  c.accept(result('camera_1'), 0);
  c.expire(2000);
  c.accept(status('camera_1'), 2001);
  assert.equal(c.result, null);
  assert.notEqual(c.aiStatus, '检测正常');
});
