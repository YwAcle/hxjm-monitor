import { SYNC_FRAME_WIDTH, SYNC_FRAME_HEIGHT, SYNC_MAX_BASE64_LENGTH } from '../config/syncPlayback.js';

export const DETECTION_TTL_MS = 3000;

export function parseDetectionMessage(raw) {
  const message = JSON.parse(raw);
  if (!message || Array.isArray(message) || typeof message !== 'object'
      || typeof message.camera_id !== 'string' || !['botsort', 'deepsort'].includes(message.task)
      || typeof message.stream_session_id !== 'string' || !message.stream_session_id
      || typeof message.service_session_id !== 'string' || !message.service_session_id
      || !Number.isInteger(message.session_generation) || message.session_generation < 0
      || !Number.isInteger(message.stream_epoch) || message.stream_epoch < 0) {
    throw new Error('检测消息标识无效');
  }
  if (message.type === 'status') {
    if (typeof message.state !== 'string' || typeof message.component !== 'string'
        || !message.components || typeof message.components !== 'object') {
      throw new Error('分析状态无效');
    }
    return message;
  }
  if (message.type !== 'detections' || !Number.isInteger(message.frame_id) || message.frame_id <= 0
      || !Number.isInteger(message.source_width) || message.source_width <= 0
      || !Number.isInteger(message.source_height) || message.source_height <= 0
      || !Number.isFinite(message.frame_ts_ms) || !Number.isFinite(message.sent_at_ms)
      || message.sent_at_ms < message.frame_ts_ms
      || !Number.isFinite(message.valid_for_ms) || message.valid_for_ms <= 0
      || !Number.isFinite(message.inference_ms) || message.inference_ms < 0
      || !Array.isArray(message.detections) || message.detections.length > 500) {
    throw new Error('检测消息字段无效');
  }
  for (const item of message.detections) {
    const predicted = item.is_prediction === true;
    const tracked = message.algorithm === 'botsort' || item.track_id !== undefined || predicted;
    if (item.label !== 'person'
        || (item.is_prediction !== undefined && typeof item.is_prediction !== 'boolean')
        || (tracked && (!Number.isSafeInteger(item.track_id) || item.track_id <= 0
          || !Number.isSafeInteger(item.missed_frames) || item.missed_frames < 0))
        || (predicted ? item.confidence !== null || item.missed_frames <= 0
          : !Number.isFinite(item.confidence) || item.confidence < 0 || item.confidence > 1)
        || !Array.isArray(item.bbox) || item.bbox.length !== 4
        || item.bbox.some(value => !Number.isFinite(value) || value < 0 || value > 1)
        || item.bbox[2] <= item.bbox[0] || item.bbox[3] <= item.bbox[1]) {
      throw new Error('检测框必须是归一化 xyxy');
    }
  }
  if (message.frame != null) {
    const frame = message.frame;
    if (frame.encoding !== 'jpeg' || frame.frame_id !== message.frame_id
        || !Number.isInteger(frame.width) || frame.width <= 0 || frame.width > SYNC_FRAME_WIDTH
        || !Number.isInteger(frame.height) || frame.height <= 0 || frame.height > SYNC_FRAME_HEIGHT
        || typeof frame.data !== 'string' || frame.data.length > SYNC_MAX_BASE64_LENGTH
        || !/^\/9j\/[A-Za-z0-9+/]*={0,2}$/.test(frame.data)) {
      throw new Error('同步图像与检测帧不匹配');
    }
  }
  return message;
}

export function resultLifetime(message) {
  return Math.max(0, Math.min(message.valid_for_ms, DETECTION_TTL_MS - (message.sent_at_ms - message.frame_ts_ms)));
}

export function isNewerFrame(message, previous) {
  return !previous || message.stream_epoch > previous.stream_epoch
    || (message.stream_epoch === previous.stream_epoch && message.frame_id > previous.frame_id);
}
