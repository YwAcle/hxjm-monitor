import assert from 'node:assert/strict';
import test from 'node:test';
import { startExactRenderer } from './exactVideoRenderer.js';

function rendererHarness(t) {
  const saved = Object.fromEntries(['window', 'document', 'performance', 'requestAnimationFrame',
    'cancelAnimationFrame', 'createImageBitmap'].map(key => [key, globalThis[key]]));
  let now = 1000;
  let callback;
  const decodes = [];
  const bitmaps = [];
  const listeners = {};
  globalThis.performance = { now: () => now };
  globalThis.window = { devicePixelRatio: 1 };
  globalThis.document = { hidden: false,
    addEventListener(name, cb) { listeners[name] = cb; },
    removeEventListener(name) { delete listeners[name]; } };
  globalThis.requestAnimationFrame = cb => { callback = cb; return 1; };
  globalThis.cancelAnimationFrame = () => {};
  globalThis.createImageBitmap = () => new Promise((resolve, reject) => decodes.push({ resolve, reject }));
  const strokes = [];
  const context = { setTransform() {}, clearRect() {}, save() {}, restore() {}, beginPath() {}, rect() {},
    clip() {}, fillRect() {}, fillText() {}, drawImage() {}, measureText: () => ({ width: 10 }),
    strokeRect: (...box) => strokes.push(box) };
  const canvas = () => ({ width: 640, height: 360, dataset: {}, style: {},
    getContext: () => context,
    getBoundingClientRect: () => ({ width: 640, height: 360, left: 0, top: 0 }) });
  const overlay = canvas();
  const playback = canvas();
  const state = { current: { enabled: true, identity: 'session-a' } };
  const packet = (id, x = 0.1) => ({ receivedAt: now, frameAt: now,
    expiresAt: now + 3000, message: { frame_id: id,
      frame: { data: '/9j/AAAA', width: 640, height: 360 },
      detections: [{ confidence: 0.9, bbox: [x, 0.2, x + 0.1, 0.8] }] } });
  const latestRef = { current: packet(1) };
  const stop = startExactRenderer({ overlay, playback, state, latestRef });
  t.after(() => {
    stop();
    for (const [key, value] of Object.entries(saved)) {
      if (value === undefined) delete globalThis[key]; else globalThis[key] = value;
    }
  });
  const settle = async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); };
  return { overlay, playback, state, latestRef, packet, bitmaps, strokes, stop, decodes,
    tick(ms = 0) { now += ms; callback(); },
    visibility(hidden) { document.hidden = hidden; listeners.visibilitychange(); },
    async decode({ broken = false } = {}) {
      const pending = decodes.shift();
      assert.ok(pending, 'a frame should be decoding');
      if (broken) pending.reject(new Error('corrupt JPEG'));
      else {
        const bitmap = { width: 640, height: 360, closed: false, close() { this.closed = true; } };
        bitmaps.push(bitmap); pending.resolve(bitmap);
      }
      await settle();
    },
  };
}

test('async decoding pairs each image with its own boxes and releases replaced images', async t => {
  const h = rendererHarness(t);
  h.tick();
  h.latestRef.current = h.packet(2, 0.5);
  await h.decode(); h.tick();
  assert.equal(h.playback.dataset.frameId, '1');
  assert.equal(h.overlay.dataset.frameId, '1');
  assert.equal(h.strokes.at(-1)[0], 64);
  await h.decode(); h.tick();
  assert.equal(h.playback.dataset.frameId, '2');
  assert.equal(h.overlay.dataset.frameId, '2');
  assert.equal(h.strokes.at(-1)[0], 320);
  assert.equal(h.bitmaps[0].closed, true);
  h.state.current.enabled = false; h.tick();
  assert.equal(h.overlay.dataset.drawnBoxes, '0');
  assert.equal(h.playback.dataset.frameId, '2');
});

test('a detection gap or expiry keeps the displayed image and its own boxes together', async t => {
  const h = rendererHarness(t);
  h.tick(); await h.decode(); h.tick();
  h.tick(600);
  assert.equal(h.playback.style.display, 'block');
  assert.equal(h.playback.dataset.frameId, '1');
  assert.equal(h.overlay.dataset.playbackMode, 'sync-exact');
  assert.equal(h.overlay.dataset.videoLive, 'false');
  assert.equal(h.overlay.dataset.drawnBoxes, '1');
  assert.equal(h.overlay.dataset.frameId, '1');
  h.tick(3000);
  h.latestRef.current = null; h.tick();
  assert.equal(h.playback.dataset.frameId, '1');
  assert.equal(h.playback.style.display, 'block');
  assert.equal(h.overlay.dataset.drawnBoxes, '1');
  assert.equal(h.overlay.dataset.frameId, '1');
  h.state.current.enabled = false; h.tick();
  assert.equal(h.overlay.dataset.drawnBoxes, '0');
  h.state.current.enabled = true; h.tick();
  assert.equal(h.overlay.dataset.drawnBoxes, '1');
  h.latestRef.current = h.packet(2); h.tick();
  assert.equal(h.playback.dataset.frameId, '1');
  assert.equal(h.overlay.dataset.frameId, '1');
  await h.decode(); h.tick();
  assert.equal(h.playback.dataset.frameId, '2');
  assert.equal(h.overlay.dataset.frameId, '2');
  assert.equal(h.overlay.dataset.videoLive, 'true');
});

test('a new zero-target image clears held boxes only when that image is displayed', async t => {
  const h = rendererHarness(t);
  h.tick(); await h.decode(); h.tick();
  h.tick(3500); h.latestRef.current = null; h.tick();
  h.latestRef.current = h.packet(2);
  h.latestRef.current.message.detections = [];
  h.tick();
  assert.equal(h.playback.dataset.frameId, '1');
  assert.equal(h.overlay.dataset.frameId, '1');
  assert.equal(h.overlay.dataset.drawnBoxes, '1');
  await h.decode(); h.tick();
  assert.equal(h.playback.dataset.frameId, '2');
  assert.equal(h.overlay.dataset.frameId, '2');
  assert.equal(h.overlay.dataset.drawnBoxes, '0');
});

test('expired unseen packets cannot replace a held image or its boxes', async t => {
  const h = rendererHarness(t);
  h.tick(); await h.decode(); h.tick();
  h.latestRef.current = h.packet(2);
  h.latestRef.current.expiresAt = performance.now();
  h.tick(600);
  assert.equal(h.decodes.length, 0);
  assert.equal(h.playback.dataset.frameId, '1');
  assert.equal(h.overlay.dataset.frameId, '1');
  assert.equal(h.overlay.dataset.drawnBoxes, '1');
});

test('late older or duplicate packets cannot replace the displayed frame after a gap', async t => {
  const h = rendererHarness(t);
  h.latestRef.current = h.packet(10); h.tick(); await h.decode(); h.tick();
  h.tick(600);
  h.latestRef.current = h.packet(9); h.tick();
  assert.equal(h.decodes.length, 0);
  assert.equal(h.playback.dataset.frameId, '10');
  h.latestRef.current = h.packet(10); h.tick();
  assert.equal(h.decodes.length, 0);
  h.latestRef.current = h.packet(11); h.tick(); await h.decode(); h.tick();
  assert.equal(h.playback.dataset.frameId, '11');
});

test('session changes discard pending images and never reveal the raw video while waiting', async t => {
  const h = rendererHarness(t);
  h.tick(); await h.decode(); h.tick();
  h.latestRef.current = h.packet(2); h.tick();
  h.state.current.identity = 'session-b'; h.latestRef.current = null; h.tick();
  await h.decode(); h.tick();
  assert.equal(h.playback.style.display, 'block');
  assert.equal(h.playback.dataset.frameId, '');
  assert.equal(h.overlay.dataset.playbackMode, 'sync-waiting');
  assert.equal(h.overlay.dataset.drawnBoxes, '0');
  assert.ok(h.bitmaps.every(bitmap => bitmap.closed));
  h.latestRef.current = h.packet(1); h.tick(); await h.decode(); h.tick();
  assert.equal(h.playback.dataset.frameId, '1');
  h.latestRef.current = h.packet(2); h.tick();
  h.stop(); await h.decode();
  assert.equal(h.playback.style.display, 'none');
  assert.ok(h.bitmaps.every(bitmap => bitmap.closed));
});

test('corrupt images leave the last exact image visible and visibility changes release resources', async t => {
  const h = rendererHarness(t);
  h.tick(); await h.decode(); h.tick();
  h.latestRef.current = h.packet(2); h.tick(); await h.decode({ broken: true }); h.tick(600);
  assert.equal(h.playback.style.display, 'block');
  assert.equal(h.playback.dataset.frameId, '1');
  assert.equal(h.overlay.dataset.drawnBoxes, '1');
  assert.equal(h.overlay.dataset.frameId, '1');
  h.latestRef.current = h.packet(3); h.tick();
  h.visibility(true); await h.decode(); h.tick();
  assert.ok(h.bitmaps.every(bitmap => bitmap.closed));
  assert.equal(h.playback.dataset.frameId, '');
  h.visibility(false);
  h.latestRef.current = h.packet(4); h.tick(); await h.decode(); h.tick();
  assert.equal(h.playback.dataset.frameId, '4');
});
