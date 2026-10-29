const PTS_TOLERANCE_MS = 1;

export function historicalWindow(mediaTime, windowSeconds = 5) {
  if (!Number.isFinite(mediaTime) || mediaTime < 0) return null;
  if (!Number.isFinite(windowSeconds) || windowSeconds <= 0) {
    throw new TypeError('历史窗口长度必须大于零');
  }
  const sizeMs = windowSeconds * 1000;
  const startMs = Math.floor(mediaTime * 1000 / sizeMs) * sizeMs;
  return { key: `${startMs}:${startMs + sizeMs}`, start_ms: startMs, end_ms: startMs + sizeMs };
}

export function matchHistoricalFrame(items, assetId, mediaTime) {
  if (!assetId || !Number.isFinite(mediaTime) || mediaTime < 0) return null;
  const mediaPtsMs = mediaTime * 1000;
  let match = null;
  let closest = Infinity;
  for (const frame of items) {
    if (frame.media_asset_id !== assetId || !Number.isFinite(frame.media_pts_ms)
        || frame.media_pts_ms < 0) continue;
    const distance = Math.abs(frame.media_pts_ms - mediaPtsMs);
    // Only compensate millisecond rounding; an earlier frame is never a fallback.
    if (distance <= PTS_TOLERANCE_MS + Number.EPSILON * Math.max(1, mediaPtsMs)
        && distance < closest) {
      match = frame;
      closest = distance;
    }
  }
  return match;
}

export function historicalDetections(frame) {
  return (Array.isArray(frame?.targets) ? frame.targets : []).flatMap(target => {
    const bbox = target.bbox;
    if (!Array.isArray(bbox) || bbox.length !== 4
        || bbox.some(value => !Number.isFinite(value) || value < 0 || value > 1)
        || bbox[0] >= bbox[2] || bbox[1] >= bbox[3]) return [];
    const detection = {
      bbox,
      confidence: Number.isFinite(target.confidence)
        && target.confidence >= 0 && target.confidence <= 1 ? target.confidence : null,
    };
    if (Number.isSafeInteger(target.track_id) && target.track_id >= 0) {
      detection.track_id = target.track_id;
    }
    return [detection];
  });
}

function throwIfAborted(signal) {
  if (signal?.aborted) throw signal.reason ?? new DOMException('请求已取消', 'AbortError');
}

export async function loadHistoricalWindow(api, asset, window, signal) {
  throwIfAborted(signal);
  const assetStart = Date.parse(asset.start_at);
  if (!asset.asset_id || !asset.source_id || !Number.isFinite(assetStart)
      || !window || !Number.isFinite(window.start_ms) || window.start_ms < 0
      || !Number.isFinite(window.end_ms) || window.end_ms <= window.start_ms) {
    throw new TypeError('录像或历史窗口无效');
  }
  const query = {
    source_id: asset.source_id,
    ...(asset.stream_session_id ? { stream_session_id: asset.stream_session_id } : {}),
    // The display PTS and saved integer milliseconds can straddle a window edge.
    start_at: new Date(assetStart + Math.max(0, window.start_ms - PTS_TOLERANCE_MS)).toISOString(),
    end_at: new Date(assetStart + window.end_ms + PTS_TOLERANCE_MS).toISOString(),
    result_type: 'detection.frame',
    page_size: 200,
  };
  const items = [];
  const cursors = new Set();
  let cursor;
  do {
    throwIfAborted(signal);
    const page = await api.results({ ...query, ...(cursor ? { cursor } : {}) }, signal);
    throwIfAborted(signal);
    if (!Array.isArray(page.items) || typeof page.has_more !== 'boolean') {
      throw new Error('历史结果分页响应无效');
    }
    items.push(...page.items.filter(frame => frame.media_asset_id === asset.asset_id));
    if (!page.has_more) break;
    if (typeof page.next_cursor !== 'string' || !page.next_cursor || cursors.has(page.next_cursor)) {
      throw new Error('历史结果分页游标缺失或重复');
    }
    cursor = page.next_cursor;
    cursors.add(cursor);
  } while (true);
  return items;
}
