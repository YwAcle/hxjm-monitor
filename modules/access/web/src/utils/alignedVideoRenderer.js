import { FrameAnnotations, FrameBuffer, MediaTimeline, nearestResult, SYNC_DELAY_MS } from './videoAlignment.js';
import { containRect, drawOverlay, clearOverlay } from './detectionOverlay.js';
import { REALTIME_MAX_RESULT_AGE_MS } from '../config/syncPlayback.js';

// Bounded local presentation delay. The underlying raw WebRTC video never pauses.
export function startAlignedRenderer({ video, overlay, playback, state, historyRef, latestRef }) {
  const buffer = new FrameBuffer();
  const rawAnnotations = new FrameAnnotations();
  const delayedAnnotations = new FrameAnnotations();
  const captureCanvas = document.createElement('canvas');
  let disposed = false;
  let pending = false;
  let raf;
  let vfc;
  let lastCapture = -Infinity;
  let lastProgress = 0;
  let lastTime = -1;
  const mediaTimeline = new MediaTimeline();
  let source = video.srcObject;
  let identity = state.current.identity;
  let wasSync = false;
  let generation = 0;
  let lastFrameAt = null;
  let lastShown = 0;
  let frameSequence = 0;
  let lastObservedFrame = -1;
  const hasFrameCallback = typeof video.requestVideoFrameCallback === 'function';
  const supported = hasFrameCallback && typeof createImageBitmap === 'function';
  const reset = ({ preserveRaw = false } = {}) => {
    generation += 1; buffer.clear(); lastFrameAt = null; mediaTimeline.reset();
    if (!preserveRaw) rawAnnotations.reset();
    delayedAnnotations.reset();
    playback.style.display = 'none'; clearOverlay(overlay);
  };
  const frameCallback = (now, metadata) => {
    if (disposed) return;
    lastProgress = performance.now();
    frameSequence += 1;
    if (source !== video.srcObject) { source = video.srcObject; reset(); }
    // mediaTime is local to this WebRTC receiver. Anchor it on arrival/presentation,
    // never compare it directly to backend RTSP PTS or raw RTP timestamp.
    const receive = metadata.receiveTime;
    const reference = Number.isFinite(receive) && receive <= now + 80 && receive > now - 10000 ? receive : now;
    const pts = metadata.mediaTime * 1000;
    if (Number.isFinite(pts)) {
      if (lastTime >= 0 && pts < lastTime - 500) reset();
      lastTime = pts;
      lastFrameAt = mediaTimeline.map(pts, reference);
    } else lastFrameAt = null;
    overlay.dataset.mediaTime = String(metadata.mediaTime ?? '');
    overlay.dataset.rtpTimestamp = String(metadata.rtpTimestamp ?? '');
    overlay.dataset.captureTime = String(metadata.captureTime ?? '');
    overlay.dataset.receiveTime = String(metadata.receiveTime ?? '');
    if (supported && state.current.mode === 'sync' && lastFrameAt != null && !pending && now - lastCapture >= 1000 / 12
      && !document.hidden && state.current.status === '原始画面' && video.videoWidth > 0) {
      lastCapture = now; pending = true;
      const capturedGeneration = generation;
      const at = performance.now();
      const frameAt = lastFrameAt;
      // Snapshot synchronously inside rVFC; async bitmap creation must not sample a later video frame.
      const scale = Math.min(1, 640 / video.videoWidth, 360 / video.videoHeight);
      captureCanvas.width = Math.max(1, Math.round(video.videoWidth * scale));
      captureCanvas.height = Math.max(1, Math.round(video.videoHeight * scale));
      captureCanvas.getContext('2d').drawImage(video, 0, 0, captureCanvas.width, captureCanvas.height);
      createImageBitmap(captureCanvas).then(bitmap => {
        if (disposed || generation !== capturedGeneration) bitmap.close();
        else buffer.push({ bitmap, at, frameAt });
      }).catch(() => { reset(); }).finally(() => { pending = false; });
    }
    vfc = video.requestVideoFrameCallback(frameCallback);
  };
  if (hasFrameCallback) vfc = video.requestVideoFrameCallback(frameCallback);
  const visibility = () => { reset(); lastProgress = 0; };
  document.addEventListener('visibilitychange', visibility);
  const render = () => {
    if (disposed) return;
    raf = requestAnimationFrame(render);
    const now = performance.now();
    if (!hasFrameCallback) {
      const quality = video.getVideoPlaybackQuality?.();
      const presented = quality ? quality.totalVideoFrames - quality.droppedVideoFrames : video.currentTime;
      if (presented !== lastObservedFrame) {
        lastObservedFrame = presented; lastProgress = now; frameSequence += 1;
      }
    }
    const current = state.current;
    const sync = current.mode === 'sync' && supported && lastFrameAt != null && !document.hidden;
    if (identity !== current.identity || source !== video.srcObject) {
      const sameVideo = source === video.srcObject;
      identity = current.identity; source = video.srcObject;
      // AI capture/worker sessions can restart while the browser still shows the
      // same frozen image. Its snapshot is discarded on the next video frame.
      reset({ preserveRaw: sameVideo && current.mode !== 'realtime' });
    }
    if (wasSync !== sync) {
      generation += 1; buffer.clear(); playback.style.display = 'none';
      delayedAnnotations.reset();
    }
    wasSync = sync;
    const live = current.status === '原始画面' && now - lastProgress < 1000 && !document.hidden;
    const visible = current.status === '原始画面' && video.videoWidth > 0 && !document.hidden;
    if (!visible) { rawAnnotations.reset(); delayedAnnotations.reset(); }
    overlay.dataset.videoLive = String(live && video.videoWidth > 0);
    const rawCandidate = current.mode === 'realtime' || lastFrameAt == null
      ? latestRef.current : nearestResult(historyRef.current, lastFrameAt, now);
    // A live video can freeze or the AI session can disappear. Re-evaluate expiry
    // every paint instead of pinning an annotation to an unchanged video frame.
    const freshRealtime = live && rawCandidate && now < rawCandidate.expiresAt
      && now - rawCandidate.frameAt < REALTIME_MAX_RESULT_AGE_MS;
    const raw = current.mode === 'realtime'
      ? { packet: freshRealtime ? rawCandidate : null, frozen: false }
      : rawAnnotations.select(frameSequence, visible ? rawCandidate : null, now);
    let frameAt = lastFrameAt;
    if (sync && live) {
      const frame = buffer.take(now);
      if (frame) {
        try {
          playback.style.display = 'block';
          const bounds = playback.getBoundingClientRect();
          const dpr = devicePixelRatio || 1;
          const width = Math.round(bounds.width * dpr); const height = Math.round(bounds.height * dpr);
          if (playback.width !== width) playback.width = width;
          if (playback.height !== height) playback.height = height;
          const ctx = playback.getContext('2d');
          const rect = containRect(width, height, frame.bitmap.width, frame.bitmap.height);
          if (rect) {
            ctx.fillStyle = '#000'; ctx.fillRect(0, 0, width, height);
            ctx.drawImage(frame.bitmap, rect.x, rect.y, rect.width, rect.height);
            playback.dataset.frameAt = String(frame.frameAt); playback.dataset.displayAt = String(now);
            playback.dataset.capturedAt = String(frame.at);
            playback.dataset.delayMs = String(now - frame.at);
            lastShown = now; playback.style.display = 'block';
          }
        } finally { frame.bitmap.close(); }
      }
      frameAt = Number(playback.dataset.frameAt) || null;
      if (now - lastShown > 350 || now - Number(playback.dataset.capturedAt) > 1000) playback.style.display = 'none';
    } else { buffer.clear(); playback.style.display = 'none'; }
    // During buffer warm-up or fallback, match the actually visible live video.
    if (playback.style.display !== 'block') frameAt = lastFrameAt;
    const displayed = playback.style.display === 'block'
      ? delayedAnnotations.select(playback.dataset.capturedAt, nearestResult(historyRef.current, frameAt, now), now)
      : raw;
    const { packet, frozen } = displayed;
    drawOverlay(overlay, video, packet, current.enabled && visible, now, frozen);
    overlay.dataset.annotationHeld = String(frozen && !!packet && !live);
    overlay.dataset.alignment = current.mode === 'realtime' ? 'latest-result-realtime'
      : frameAt == null ? 'latest-result-fallback'
      : `${packet?.alignmentKind || 'no-match'}:media-arrival-estimate`;
    overlay.dataset.matchDiffMs = packet && frameAt != null ? String(packet.frameAt - frameAt) : '';
    overlay.dataset.displayFrameAt = String(frameAt ?? '');
    overlay.dataset.bufferFrames = String(buffer.frames.length);
    overlay.dataset.bufferBytes = String(buffer.bytes);
    overlay.dataset.historySize = String(historyRef.current.length);
    overlay.dataset.playbackMode = sync && playback.style.display === 'block' ? 'sync-approximate'
      : current.mode === 'sync' ? 'realtime-fallback' : 'realtime';
    overlay.dataset.playbackDelayMs = playback.style.display === 'block' ? String(now - Number(playback.dataset.capturedAt)) : '0';
    overlay.dataset.targetDelayMs = String(SYNC_DELAY_MS);
  };
  raf = requestAnimationFrame(render);
  return () => {
    disposed = true; reset(); cancelAnimationFrame(raf);
    if (vfc != null) video.cancelVideoFrameCallback?.(vfc);
    document.removeEventListener('visibilitychange', visibility);
    captureCanvas.width = captureCanvas.height = 0;
  };
}
