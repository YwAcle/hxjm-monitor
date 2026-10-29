import { HISTORY_MAX } from './videoAlignment.js';
import { isNewerFrame, resultLifetime } from './detectionProtocol.js';
import { REALTIME_MAX_RESULT_AGE_MS } from '../config/syncPlayback.js';

export const detectionKey = (cameraId, task = 'deepsort') => `${cameraId}:${task}`;

// One channel owns its session, ordering and expiry. A result cannot establish a session.
export class DetectionChannel {
  constructor(cameraId, task = 'deepsort') {
    this.cameraId = cameraId;
    this.task = task;
    this.latestRef = { current: null };
    this.historyRef = { current: [] };
    this.revision = 0;
    this.reset('等待检测');
  }

  reset(status) {
    this.captureState = null;
    this.analyzerState = null;
    this.session = null;
    this.service = null;
    this.generation = -1;
    this.epoch = -1;
    this.previous = null;
    this.everDetected = false;
    this.available = false;
    this.clear(status);
  }

  clear(status) {
    this.latestRef.current = null;
    this.historyRef.current = [];
    this.revision += 1;
    this.result = null;
    this.analysisDelayed = false;
    this.aiStatus = status;
  }

  accept(message, now, clock) {
    if (message.camera_id !== this.cameraId || message.task !== this.task) return false;
    if (this.service && message.service_session_id !== this.service) return false;
    if (message.session_generation < this.generation) return false;
    const newSession = this.session !== message.stream_session_id;
    if (newSession) {
      if (message.type !== 'status' || message.session_generation <= this.generation) return false;
      this.service = message.service_session_id;
      this.session = message.stream_session_id;
      this.generation = message.session_generation;
      this.epoch = -1;
      this.previous = null;
      this.everDetected = false;
      this.available = false;
      this.clear('等待检测');
    } else if (message.session_generation !== this.generation) return false;
    if (message.stream_epoch < this.epoch) return false;
    if (message.stream_epoch !== this.epoch) {
      this.epoch = message.stream_epoch;
      this.previous = null;
      this.everDetected = false;
      this.clear('等待检测');
    }
    if (message.type === 'status') {
      const capture = message.components.capture?.state;
      const analyzer = message.components.analyzer?.state;
      this.captureState = capture;
      this.analyzerState = analyzer;
      const noSource = !['streaming'].includes(capture);
      const failed = ['worker_timeout', 'inference_error', 'model_error'].includes(analyzer)
        || ['worker_timeout', 'inference_error', 'model_error'].includes(message.state);
      this.available = !noSource && !failed && !['loading_model', 'no_new_frame'].includes(analyzer);
      this.analysisDelayed = this.analysisDelayed && !noSource && ['ready', 'detecting'].includes(analyzer);
      if (noSource || failed || analyzer === 'loading_model' || analyzer === 'no_new_frame') {
        this.clear(noSource ? (capture === 'reconnecting' ? '取帧重连' : '等待视频源')
          : failed ? (analyzer === 'model_error' ? '模型加载异常' : '推理异常')
            : analyzer === 'loading_model' ? '模型加载中' : '暂无新结果');
      } else this.aiStatus = this.analysisDelayed ? '分析延迟'
        : this.result ? '检测正常' : this.everDetected ? '暂无新结果' : '等待检测';
      return true;
    }
    if (!this.available || !isNewerFrame(message, this.previous)) return false;
    const ttl = resultLifetime(message);
    if (ttl > 0) {
      const mapped = clock?.toLocal(message.frame_ts_ms, now);
      const frameAt = mapped ?? now - (message.sent_at_ms - message.frame_ts_ms);
      // Reject impossible future timestamps even when the local clock is skewed.
      if (frameAt > now + 80 || now - frameAt > 3000) return false;
      this.previous = message;
      const packet = { message, expiresAt: now + Math.min(ttl, 3000 - Math.max(0, now - frameAt)),
        frameAt, receivedAt: now, alignmentKind: mapped == null ? 'arrival_estimate' : 'server_clock_estimate' };
      this.latestRef.current = packet;
      // Exact playback needs only the newest pair; never retain a JPEG history.
      this.historyRef.current = message.frame ? [packet] : [...this.historyRef.current.filter(p => now < p.expiresAt), packet]
        .sort((a, b) => a.frameAt - b.frameAt).slice(-HISTORY_MAX);
      this.result = message;
      this.everDetected = true;
      this.analysisDelayed = ['ready', 'detecting'].includes(this.analyzerState)
        && now - frameAt >= REALTIME_MAX_RESULT_AGE_MS;
      this.aiStatus = this.analysisDelayed ? '分析延迟' : '检测正常';
    } else return false;
    return true;
  }

  expire(now) {
    let changed = false;
    const packet = this.latestRef.current;
    if (packet && !this.analysisDelayed && this.available
        && ['ready', 'detecting'].includes(this.analyzerState)
        && now >= Math.min(packet.expiresAt, packet.frameAt + REALTIME_MAX_RESULT_AGE_MS)) {
      this.analysisDelayed = true;
      this.aiStatus = '分析延迟';
      changed = true;
    }
    this.historyRef.current = this.historyRef.current.filter(p => now < p.expiresAt);
    if (this.latestRef.current && now >= this.latestRef.current.expiresAt) {
      this.latestRef.current = null;
      this.result = null;
      this.aiStatus = this.analysisDelayed ? '分析延迟' : '暂无新结果';
      return true;
    }
    return changed;
  }

  snapshot() {
    return { latestRef: this.latestRef, historyRef: this.historyRef, result: this.result, aiStatus: this.aiStatus,
      analysisDelayed: this.analysisDelayed,
      captureState: this.captureState, analyzerState: this.analyzerState, revision: this.revision,
      identity: `${this.service}:${this.session}:${this.epoch}` };
  }
}
