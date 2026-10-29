// All matching uses browser monotonic milliseconds. Neither RTSP PTS nor RTP
// timestamps from independent receivers are assumed to share an epoch.
export const HISTORY_MAX = 64;
export const BUFFER_MAX = 32;
export const BUFFER_BYTES_MAX = 32 * 1024 * 1024;
export const SYNC_DELAY_MS = 650;
export const MAX_DELAY_MS = 1000;
// A 1 Hz detector needs to cover one full sample interval, plus modest jitter.
// Keep future matching tight and stop holding a result after 1.2 s of media time.
export const MATCH_TOLERANCE_MS = 1200;
export const MEDIA_ARRIVAL_LAG_MAX_MS = 500;

// Annotation snapshot for one actually presented frame. Expiry still applies
// when selecting a new frame; a frozen image keeps its own original annotation.
export class FrameAnnotations {
  constructor() { this.reset(); }
  reset() { this.frame = null; this.packet = null; }
  select(frame, candidate, now) {
    const frozen = frame === this.frame;
    if (!frozen) {
      this.frame = frame;
      this.packet = candidate && now < candidate.expiresAt ? candidate : null;
    }
    return { packet: this.packet, frozen };
  }
}

export class MediaTimeline {
  constructor() { this.reset(); }
  reset() { this.anchor = null; this.lastPts = null; }
  map(pts, arrival) {
    if (!Number.isFinite(pts) || pts < 0) { this.reset(); return null; }
    const advancing = this.lastPts != null && pts > this.lastPts && pts - this.lastPts < 10000;
    if (!advancing) this.anchor = null;
    const candidate = arrival - pts;
    this.anchor = this.anchor == null ? candidate : Math.min(this.anchor, candidate);
    this.lastPts = pts;
    const estimated = this.anchor + pts;
    if (arrival - estimated > MEDIA_ARRIVAL_LAG_MAX_MS) {
      this.anchor = candidate;
      return arrival; // degraded arrival estimate, never a camera capture time
    }
    return estimated;
  }
}

export class ServerClock {
  constructor() { this.reset(); }
  reset() { this.sample = null; }
  accept(pong, now) {
    const rtt = now - pong.client_ms;
    if (!Number.isFinite(rtt) || rtt < 0 || rtt > 1000 || !Number.isFinite(pong.server_ms)) return false;
    const offset = pong.server_ms - (pong.client_ms + now) / 2;
    if (!this.sample || now - this.sample.at > 15000 || rtt <= this.sample.rtt) {
      this.sample = { offset, rtt, at: now };
    }
    return true;
  }
  toLocal(serverMs, now) {
    return this.sample && now - this.sample.at < 20000 ? serverMs - this.sample.offset : null;
  }
}

export function nearestResult(history, frameAt, now, tolerance = MATCH_TOLERANCE_MS) {
  let best = null;
  let diff = Infinity;
  for (const packet of history) {
    if (now >= packet.expiresAt || packet.frameAt > frameAt + 80) continue;
    const distance = Math.abs(packet.frameAt - frameAt);
    if (distance < diff || (distance === diff && packet.message.frame_id > best?.message.frame_id)) {
      best = packet; diff = distance;
    }
  }
  return diff <= tolerance ? best : null;
}

export class FrameBuffer {
  constructor() { this.frames = []; this.bytes = 0; }
  clear() { for (const f of this.frames) f.bitmap.close(); this.frames = []; this.bytes = 0; }
  shift() { const f = this.frames.shift(); if (f) { this.bytes -= f.bytes; f.bitmap.close(); } }
  push(frame) {
    frame.bytes = frame.bitmap.width * frame.bitmap.height * 4;
    this.frames.push(frame); this.bytes += frame.bytes;
    while (this.frames.length > BUFFER_MAX || this.bytes > BUFFER_BYTES_MAX
      || (this.frames.length && frame.at - this.frames[0].at > MAX_DELAY_MS + 250)) this.shift();
  }
  take(now, delay = SYNC_DELAY_MS) {
    const target = now - Math.min(MAX_DELAY_MS, Math.max(0, delay));
    let index = -1;
    for (let i = 0; i < this.frames.length; i++) if (this.frames[i].at <= target) index = i;
    if (index < 0) return null;
    while (index-- > 0) this.shift();
    const frame = this.frames.shift(); this.bytes -= frame.bytes;
    return frame; // renderer owns/ closes this bitmap, including failures
  }
}
