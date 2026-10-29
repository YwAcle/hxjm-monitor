import assert from 'node:assert/strict';
import test from 'node:test';
import { DetectionChannel, detectionKey } from './detectionChannel.js';
import { parseDetectionMessage } from './detectionProtocol.js';
import { detectionTask } from '../config/videoDeployment.js';

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

test('configured detector routes real status and frame messages for all four cameras', () => {
  assert.equal(detectionTask(), 'botsort');
  for (const task of ['botsort', 'deepsort']) {
    const selected = detectionTask({ VITE_VIDEO_ANALYSIS_ALGORITHM: task });
    const channels = Object.fromEntries([1, 2, 3, 4].map(i => {
      const id = `camera_${i}`;
      return [detectionKey(id, selected), new DetectionChannel(id, selected)];
    }));
    for (const channel of Object.values(channels)) {
      const changes = { task, algorithm: task };
      for (const packet of [status(channel.cameraId, changes), result(channel.cameraId, {
        ...changes, source_width: 1920, source_height: 1080, inference_ms: 50,
      })]) {
        const message = parseDetectionMessage(JSON.stringify(packet));
        assert.equal(channels[detectionKey(message.camera_id, message.task)].accept(message, 0), true);
      }
      assert.equal(channel.snapshot().aiStatus, '检测正常');
    }
  }
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

test('expired live annotations show analysis delay, while a fresh zero-target result recovers normally', () => {
  const c = new DetectionChannel('camera_1');
  c.accept(status('camera_1'), 0);
  c.accept(result('camera_1'), 0);
  assert.equal(c.snapshot().aiStatus, '检测正常', 'zero targets is a valid completed result');
  assert.equal(c.expire(899), false);
  assert.equal(c.snapshot().analysisDelayed, false);
  assert.equal(c.expire(900), true);
  assert.equal(c.snapshot().aiStatus, '分析延迟');
  assert.ok(c.latestRef.current, 'diagnostic mode can retain the valid same-frame packet');
  c.accept(status('camera_1', { components: { capture: { state: 'streaming' }, analyzer: { state: 'detecting' } } }), 950);
  assert.equal(c.snapshot().aiStatus, '分析延迟', 'running status cannot hide an expired annotation');
  c.expire(2000);
  assert.equal(c.latestRef.current, null);
  assert.equal(c.snapshot().aiStatus, '分析延迟');
  c.accept(result('camera_1', { frame_id: 2, frame_ts_ms: 3000, sent_at_ms: 3100 }), 2100);
  assert.equal(c.snapshot().aiStatus, '检测正常');
  assert.equal(c.snapshot().analysisDelayed, false);
});

test('source and model failures keep their own status instead of analysis delay', () => {
  const c = new DetectionChannel('camera_1');
  c.accept(status('camera_1'), 0);
  c.accept(result('camera_1'), 0);
  c.expire(900);
  c.accept(status('camera_1', { components: { capture: { state: 'reconnecting' }, analyzer: { state: 'waiting_source' } } }), 1000);
  assert.equal(c.snapshot().aiStatus, '取帧重连');
  assert.equal(c.snapshot().analysisDelayed, false);
  c.accept(status('camera_1', { components: { capture: { state: 'streaming' }, analyzer: { state: 'model_error' } } }), 1100);
  assert.equal(c.snapshot().aiStatus, '模型加载异常');
  assert.equal(c.snapshot().analysisDelayed, false);
});
