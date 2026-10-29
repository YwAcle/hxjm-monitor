export const MAX_PLAYBACK_RETRIES = 2;
export const RECORDING_FINALIZATION_GRACE_MS = 15_000;
export const RECORDING_POLL_INTERVAL_MS = 2_000;

export function classifyPlaybackPreflightResponse(status, ok) {
  if (status === 404) {
    return 'missing';
  }
  if (status >= 500) {
    return 'retryable';
  }
  if (ok || status === 405) {
    return 'playable';
  }
  return 'unavailable';
}

export function canRetryPlayback(retryCount) {
  return retryCount < MAX_PLAYBACK_RETRIES;
}

export function getPendingRecordingRetryDelay(url, now = Date.now()) {
  try {
    const playbackUrl = new URL(url);
    const startMs = Date.parse(playbackUrl.searchParams.get('start'));
    const durationS = Number(playbackUrl.searchParams.get('duration'));
    if (!Number.isFinite(startMs) || !Number.isFinite(durationS) || durationS <= 0) {
      return null;
    }

    const readyAt = startMs + durationS * 1000;
    if (now > readyAt + RECORDING_FINALIZATION_GRACE_MS) {
      return null;
    }
    return Math.max(1_000, Math.min(RECORDING_POLL_INTERVAL_MS, readyAt - now));
  } catch {
    return null;
  }
}
