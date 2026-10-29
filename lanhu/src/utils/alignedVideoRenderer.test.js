import assert from 'node:assert/strict';
import test from 'node:test';
import { startAlignedRenderer } from './alignedVideoRenderer.js';
import { REALTIME_MAX_RESULT_AGE_MS } from '../config/syncPlayback.js';

function rendererHarness(t) {
  const saved = Object.fromEntries(['window', 'document', 'performance', 'requestAnimationFrame',
    'cancelAnimationFrame', 'createImageBitmap'].map(key => [key, globalThis[key]]));
  let now = 1000;
  let paint;
  let onFrame;
  let snapshots = 0;
  const strokes = [];
  const listeners = {};
  const context = { setTransform() {}, clearRect() {}, save() {}, restore() {}, beginPath() {}, rect() {},
    clip() {}, fillRect() {}, fillText() {}, drawImage() {}, measureText: () => ({ width: 10 }),
    setLineDash(value) { assert.deepEqual(value, []); }, strokeRect: (...box) => strokes.push(box) };
  const canvas = () => ({ width: 640, height: 360, dataset: {}, style: {},
    getContext: () => context,
    getBoundingClientRect: () => ({ width: 640, height: 360, left: 0, top: 0 }) });
  globalThis.window = { devicePixelRatio: 1 };
  globalThis.performance = { now: () => now };
  globalThis.document = { hidden: false, createElement: () => canvas(),
    addEventListener(name, callback) { listeners[name] = callback; },
    removeEventListener(name) { delete listeners[name]; } };
  globalThis.requestAnimationFrame = callback => { paint = callback; return 1; };
  globalThis.cancelAnimationFrame = () => {};
  globalThis.createImageBitmap = () => { snapshots += 1; throw new Error('Live video must not be copied'); };
  const video = { srcObject: {}, videoWidth: 1280, videoHeight: 720, paused: false, readyState: 4,
    requestVideoFrameCallback(callback) { onFrame = callback; return 1; }, cancelVideoFrameCallback() {},
    getBoundingClientRect: () => ({ width: 640, height: 360, left: 0, top: 0 }),
    pause() { throw new Error('AI renderer must not pause raw video'); } };
  const overlay = canvas();
  const playback = canvas();
  const state = { current: { mode: 'realtime', status: '原始画面', enabled: true, identity: 'session-a' } };
  const packet = id => ({ frameAt: now - 400, expiresAt: now + 3000, receivedAt: now,
    message: { frame_id: id, service_session_id: 'service-a', stream_session_id: 'stream-a',
      session_generation: 1, stream_epoch: 1,
      detections: [{ track_id: 1, confidence: 0.9, bbox: [.1, .1, .2, .8] }] } });
  const latestRef = { current: packet(1) };
  const stop = startAlignedRenderer({ video, overlay, playback, state, latestRef, historyRef: { current: [] } });
  t.after(() => {
    stop();
    for (const [key, value] of Object.entries(saved)) {
      if (value === undefined) delete globalThis[key]; else globalThis[key] = value;
    }
  });
  return { video, overlay, playback, state, latestRef, packet, strokes,
    tick(ms = 0) { now += ms; paint(); },
    frame() { onFrame(now, { mediaTime: now / 1000 }); },
    snapshots: () => snapshots };
}

test('live playback never displays an AI image or freezes boxes with the video frame', t => {
  const h = rendererHarness(t);
  h.frame(); h.tick();
  assert.equal(h.playback.style.display, 'none');
  assert.equal(h.overlay.dataset.frameId, '1');
  // A newer detection must replace the old one even before the next video callback.
  h.latestRef.current = h.packet(2); h.tick();
  assert.equal(h.overlay.dataset.frameId, '2');
  h.tick(REALTIME_MAX_RESULT_AGE_MS - 399);
  assert.equal(h.overlay.dataset.drawnBoxes, '0', 'old boxes expire even on an unchanged video frame');
  assert.equal(h.playback.style.display, 'none');
  assert.equal(h.snapshots(), 0);
});

test('AI disconnect, restart and result expiry only clear live annotations', t => {
  const h = rendererHarness(t);
  h.frame(); h.tick();
  h.latestRef.current = null; h.tick();
  assert.equal(h.overlay.dataset.drawnBoxes, '0');
  assert.equal(h.playback.style.display, 'none');
  h.latestRef.current = h.packet(2); h.frame(); h.tick();
  assert.equal(h.overlay.dataset.drawnBoxes, '1');
  h.state.current.identity = 'session-b'; h.latestRef.current = null; h.tick();
  assert.equal(h.overlay.dataset.drawnBoxes, '0');
  assert.equal(h.playback.style.display, 'none');
  assert.equal(h.video.paused, false);
  h.latestRef.current = h.packet(3);
  h.latestRef.current.expiresAt = performance.now();
  h.frame(); h.tick();
  assert.equal(h.overlay.dataset.drawnBoxes, '0');
});

test('boxes ease toward the next position for the same track without delaying video', t => {
  const h = rendererHarness(t);
  h.frame(); h.tick();
  assert.equal(h.strokes.at(-1)[0], 64);
  h.latestRef.current = h.packet(2);
  h.latestRef.current.message.detections[0].bbox = [.5, .1, .6, .8];
  h.tick();
  const firstStep = h.strokes.at(-1)[0];
  assert.ok(firstStep > 64 && firstStep < 320);
  h.tick(16);
  assert.ok(h.strokes.at(-1)[0] > firstStep && h.strokes.at(-1)[0] <= 320);
  assert.equal(h.video.paused, false);
  assert.equal(h.playback.style.display, 'none');
  h.latestRef.current = null; h.tick();
  assert.equal(h.overlay.dataset.drawnBoxes, '0', 'a missing result clears its smoothed box immediately');
});

test('stalled or disconnected raw video cannot retain a live overlay', t => {
  const h = rendererHarness(t);
  h.frame(); h.tick();
  h.tick(1100); h.latestRef.current = h.packet(2); h.tick();
  assert.equal(h.overlay.dataset.drawnBoxes, '0');
  assert.equal(h.overlay.dataset.videoLive, 'false');
  h.frame(); h.tick();
  assert.equal(h.overlay.dataset.drawnBoxes, '1');
  h.state.current.status = '未连接'; h.tick();
  assert.equal(h.overlay.dataset.drawnBoxes, '0');
  assert.equal(h.playback.style.display, 'none');
});

test('a late AI packet never delays live presentation or restores expired boxes', t => {
  const h = rendererHarness(t);
  h.latestRef.current.frameAt = performance.now() - REALTIME_MAX_RESULT_AGE_MS;
  h.frame(); h.tick();
  assert.equal(h.overlay.dataset.drawnBoxes, '0');
  assert.equal(h.overlay.dataset.playbackMode, 'realtime');
  assert.equal(h.playback.style.display, 'none');
  h.frame(); h.tick(20);
  assert.equal(h.video.paused, false);
  assert.equal(h.snapshots(), 0);
  h.latestRef.current = h.packet(2); h.frame(); h.tick();
  assert.equal(h.overlay.dataset.frameId, '2', 'a fresh result can resume annotations without replacing the video');
  assert.equal(h.playback.style.display, 'none');
});
