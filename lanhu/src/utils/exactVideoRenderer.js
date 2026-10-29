import { containRect, clearOverlay, drawOverlay } from './detectionOverlay.js';
import { SYNC_STALL_MS } from '../config/syncPlayback.js';

// The image and detections travel in one packet. No RTSP/WebRTC clock estimate
// participates in exact mode. At most one displayed and one decoding frame.
export function startExactRenderer({ overlay, playback, state, latestRef }) {
  let disposed = false;
  let raf;
  let pending = false;
  let attempted = null;
  let shown = null;
  let lastFrameId = 0;
  let identity = state.current.identity;
  let generation = 0;
  let windowStart = performance.now();
  let count = 0;
  let fps = 0;

  const reset = () => {
    generation += 1;
    attempted = null;
    shown?.bitmap.close();
    shown = null;
    // ActiveVAU keeps the last painted frame through jitter. A session reset
    // clears it, but the exact surface stays opaque until a new pair is ready.
    playback.style.display = 'block';
    const context = playback.getContext('2d');
    if (context) {
      context.fillStyle = '#000';
      context.fillRect(0, 0, playback.width, playback.height);
    }
    playback.dataset.frameId = '';
    clearOverlay(overlay);
    overlay.dataset.imageFrameId = '';
    overlay.dataset.playbackMode = 'sync-waiting';
    overlay.dataset.alignment = 'waiting-exact-frame';
    overlay.dataset.videoLive = 'false';
  };
  const usable = (packet, now) => packet && packet.message.frame && now < packet.expiresAt
    && now - packet.receivedAt < SYNC_STALL_MS && !document.hidden;

  const decode = packet => {
    pending = true;
    attempted = packet;
    const decodingGeneration = generation;
    const data = Uint8Array.from(atob(packet.message.frame.data), char => char.charCodeAt(0));
    createImageBitmap(new Blob([data], { type: 'image/jpeg' })).then(bitmap => {
      const frame = packet.message.frame;
      if (disposed || generation !== decodingGeneration || state.current.identity !== identity
          || !latestRef.current || !usable(packet, performance.now())
          || packet.message.frame_id <= lastFrameId
          || bitmap.width !== frame.width || bitmap.height !== frame.height) {
        bitmap.close();
        return;
      }
      shown?.bitmap.close();
      shown = { packet, bitmap };
      lastFrameId = packet.message.frame_id;
      count += 1;
    }).catch(() => { /* A broken image cannot borrow another frame's boxes. */ })
      .finally(() => { pending = false; });
  };

  const render = () => {
    if (disposed) return;
    raf = requestAnimationFrame(render);
    const now = performance.now();
    const current = state.current;
    const latest = latestRef.current;
    if (identity !== current.identity) { identity = current.identity; lastFrameId = 0; reset(); }
    if (now - windowStart >= 1000) {
      fps = count * 1000 / (now - windowStart);
      count = 0; windowStart = now;
    }
    overlay.dataset.fps = fps.toFixed(1);
    if (document.hidden || typeof createImageBitmap !== 'function') return;
    if (usable(latest, now) && latest.message.frame_id > lastFrameId
        && latest !== attempted && !pending) decode(latest);
    if (!shown) return;

    const { packet, bitmap } = shown;
    playback.style.display = 'block';
    const bounds = playback.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const width = Math.round(bounds.width * dpr);
    const height = Math.round(bounds.height * dpr);
    const rect = containRect(width, height, bitmap.width, bitmap.height);
    const context = playback.getContext('2d');
    if (!rect || !context) return;
    if (playback.width !== width) playback.width = width;
    if (playback.height !== height) playback.height = height;
    context.fillStyle = '#000';
    context.fillRect(0, 0, width, height);
    context.drawImage(bitmap, rect.x, rect.y, rect.width, rect.height);
    // Both canvases commit in the same animation callback, before browser paint.
    const live = !!latest && usable(packet, now);
    // The displayed bitmap owns this annotation snapshot, just as in
    // FrameAnnotations. Stalls/expiry affect status and new-frame admission;
    // they must not erase the boxes from an image that is still displayed.
    drawOverlay(overlay, {
      readyState: 4, paused: false, videoWidth: bitmap.width, videoHeight: bitmap.height,
      getBoundingClientRect: () => bounds,
    }, packet, current.enabled, now, true);
    playback.style.display = 'block';
    playback.dataset.frameId = String(packet.message.frame_id);
    overlay.dataset.imageFrameId = String(packet.message.frame_id);
    overlay.dataset.playbackMode = 'sync-exact';
    overlay.dataset.alignment = live ? 'same-inference-frame' : 'paused-exact-frame';
    overlay.dataset.videoLive = String(live);
    overlay.dataset.playbackDelayMs = String(Math.max(0, now - packet.frameAt));
  };
  const visibility = () => reset();
  document.addEventListener('visibilitychange', visibility);
  reset();
  raf = requestAnimationFrame(render);
  return () => {
    if (disposed) return;
    disposed = true; reset(); playback.style.display = 'none'; cancelAnimationFrame(raf);
    document.removeEventListener('visibilitychange', visibility);
  };
}
