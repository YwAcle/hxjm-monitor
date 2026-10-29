import assert from 'node:assert/strict';
import test from 'node:test';
import { isNewerFrame, parseDetectionMessage, resultLifetime } from './detectionProtocol.js';
import { containRect, mapBox } from './detectionOverlay.js';

const packet = (changes = {}) => ({
  type: 'detections', task: 'deepsort', camera_id: 'camera_1', stream_session_id: 'session-a',
  service_session_id: 'service-a', session_generation: 0,
  stream_epoch: 1, frame_id: 10, source_width: 1920, source_height: 1080,
  frame_ts_ms: 10000, sent_at_ms: 10100, valid_for_ms: 2900, inference_ms: 50,
  detections: [{ label: 'person', confidence: 0.8, bbox: [0.1, 0.2, 0.3, 0.9] }], ...changes,
});

test('BoT-SORT predictions retain identity without inventing confidence', () => {
  const detection = { label: 'person', track_id: 7, is_prediction: true, missed_frames: 3,
    confidence: null, bbox: [0.1, 0.2, 0.3, 0.9] };
  const message = (changes = {}) => JSON.stringify(packet({ task: 'botsort', algorithm: 'botsort',
    detections: [{ ...detection, ...changes }] }));
  assert.equal(parseDetectionMessage(message()).detections[0].track_id, 7);
  assert.equal(parseDetectionMessage(message({ is_prediction: false, missed_frames: 0, confidence: 0.9 }))
    .detections[0].confidence, 0.9);
  for (const changes of [{ confidence: -1 }, { confidence: 0.9 }, { track_id: 0 },
    { track_id: null }, { missed_frames: -1 }, { missed_frames: 0 }, { is_prediction: false }]) {
    assert.throws(() => parseDetectionMessage(message(changes)));
  }
});

test('rejects invalid coordinates, missing sessions and non-finite timing', () => {
  for (const invalid of [
    { stream_session_id: '' }, { inference_ms: null },
    { detections: [{ label: 'person', confidence: 0.8, bbox: [0.5, 0.2, 0.1, 0.9] }] },
    { source_width: 0 }, { sent_at_ms: 9000 },
  ]) assert.throws(() => parseDetectionMessage(JSON.stringify(packet(invalid))));
});

test('zero targets are a valid update; delayed results do not get a fresh three seconds', () => {
  assert.deepEqual(parseDetectionMessage(JSON.stringify(packet({ detections: [] }))).detections, []);
  assert.equal(resultLifetime(packet({ sent_at_ms: 12500, valid_for_ms: 500 })), 500);
  assert.equal(resultLifetime(packet({ sent_at_ms: 13500, valid_for_ms: 3000 })), 0);
});

test('ignores duplicate and old-epoch results', () => {
  assert.equal(isNewerFrame(packet(), packet()), false);
  assert.equal(isNewerFrame(packet({ frame_id: 11 }), packet()), true);
  assert.equal(isNewerFrame(packet({ stream_epoch: 0, frame_id: 100 }), packet()), false);
});

test('maps normalized boxes into the displayed image, including letterboxing', () => {
  const rect = containRect(800, 600, 1920, 1080);
  assert.deepEqual(rect, { x: 0, y: 75, width: 800, height: 450 });
  assert.deepEqual(mapBox([0.25, 0.2, 0.75, 0.8], rect), { x: 200, y: 165, width: 400, height: 270.00000000000006 });
  assert.equal(containRect(0, 600, 1920, 1080), null);
});

test('synchronized frames must belong to this exact detection and obey image limits', () => {
  const frame = { encoding: 'jpeg', frame_id: 10, width: 640, height: 360, data: '/9j/AAAA' };
  assert.equal(parseDetectionMessage(JSON.stringify(packet({ frame }))).frame.frame_id, 10);
  for (const change of [{ frame_id: 11 }, { encoding: 'png' }, { width: 4096 },
    { height: -1 }, { data: 'https://example.com/image.jpg' }, { data: '/9j/' + 'A'.repeat(2796204) }]) {
    assert.throws(() => parseDetectionMessage(JSON.stringify(packet({ frame: { ...frame, ...change } }))));
  }
});
