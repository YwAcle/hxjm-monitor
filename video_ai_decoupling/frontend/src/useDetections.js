import { useEffect, useRef, useState } from 'react';
import { DETECTION_TTL_MS } from './overlay.js';

export function parseMessage(raw) {
  const message = JSON.parse(raw);
  if (!message || typeof message !== 'object' || Array.isArray(message)) {
    throw new Error('消息必须是 JSON 对象');
  }
  if (!Number.isInteger(message.stream_epoch) || message.stream_epoch < 0) {
    throw new Error('stream_epoch 无效');
  }
  if (message.type === 'status') {
    if (typeof message.component !== 'string' || typeof message.state !== 'string') {
      throw new Error('状态消息字段缺失');
    }
    return message;
  }
  if (message.type !== 'detections' || typeof message.camera_id !== 'string'
      || !Number.isInteger(message.frame_id) || message.frame_id <= 0
      || !Number.isInteger(message.source_width) || message.source_width <= 0
      || !Number.isInteger(message.source_height) || message.source_height <= 0
      || !Number.isFinite(message.frame_ts_ms) || message.frame_ts_ms <= 0
      || !Number.isFinite(message.inference_ms) || message.inference_ms < 0
      || !Array.isArray(message.detections)) {
    throw new Error('检测消息字段无效');
  }
  for (const detection of message.detections) {
    if (detection.label !== 'person' || !Number.isFinite(detection.confidence)
        || detection.confidence < 0 || detection.confidence > 1
        || !Array.isArray(detection.bbox) || detection.bbox.length !== 4
        || detection.bbox.some(value => !Number.isFinite(value) || value < 0 || value > 1)
        || detection.bbox[2] <= detection.bbox[0] || detection.bbox[3] <= detection.bbox[1]) {
      throw new Error('检测框不是有效的归一化 xyxy');
    }
  }
  return message;
}

export function isNewerFrame(message, previous) {
  return !previous || message.stream_epoch > previous.stream_epoch
    || (message.stream_epoch === previous.stream_epoch && message.frame_id > previous.frame_id);
}

export default function useDetections(websocketUrl) {
  const latestRef = useRef(null);
  const [result, setResult] = useState(null);
  const [aiStatus, setAiStatus] = useState('等待连接');

  useEffect(() => {
    let disposed = false;
    let socket = null;
    let reconnectTimer = null;
    let expiryTimer = null;
    let attempt = 0;
    let streamEpoch = null;
    let previousFrame = null;
    let analysisAvailable = true;

    const clearResult = () => {
      clearTimeout(expiryTimer);
      latestRef.current = null;
      setResult(null);
    };
    const advanceEpoch = (epoch) => {
      if (streamEpoch !== null && epoch < streamEpoch) return false;
      if (epoch !== streamEpoch) {
        clearResult();
        previousFrame = null;
        streamEpoch = epoch;
      }
      return true;
    };

    const connect = () => {
      if (disposed) return;
      clearResult();
      setAiStatus('连接中...');
      try {
        const url = new URL(websocketUrl);
        if (!['ws:', 'wss:'].includes(url.protocol)) throw new Error('需要 ws:// 或 wss:// 地址');
        socket = new WebSocket(url.href);
      } catch (error) {
        setAiStatus(`WebSocket 配置错误：${error.message}`);
        return;
      }
      const activeSocket = socket;
      activeSocket.onopen = () => {
        if (disposed) return;
        attempt = 0;
        streamEpoch = null;
        previousFrame = null;
        analysisAvailable = true;
        clearResult();
        setAiStatus('已连接，等待检测');
      };
      activeSocket.onmessage = (event) => {
        if (disposed || socket !== activeSocket) return;
        try {
          const message = parseMessage(event.data);
          if (!advanceEpoch(message.stream_epoch)) return;
          if (message.type === 'status') {
            const states = [message, ...Object.values(message.components || {})];
            const problem = states.find(state => state.error
              || ['reconnecting', 'inference_error', 'model_error', 'stopped'].includes(state.state));
            const pending = states.find(state => ['idle', 'connecting', 'starting', 'loading_model'].includes(state.state));
            analysisAvailable = !problem && !pending;
            if (problem || pending) {
              clearResult();
              setAiStatus(problem ? `分析异常：${problem.error || problem.state}` : '分析准备中...');
            } else {
              setAiStatus(latestRef.current ? '检测中' : '已连接，等待检测');
            }
            return;
          }
          if (!analysisAvailable || !isNewerFrame(message, previousFrame)) return;
          previousFrame = { frame_id: message.frame_id, stream_epoch: message.stream_epoch };
          const packet = { message, receivedAt: performance.now() };
          clearTimeout(expiryTimer);
          latestRef.current = packet;
          setResult(message);
          setAiStatus('检测中');
          expiryTimer = setTimeout(() => {
            if (disposed) return;
            clearResult();
            setAiStatus('检测结果已过期，等待新结果');
          }, DETECTION_TTL_MS);
        } catch (error) {
          clearResult();
          setAiStatus(`消息解析失败：${error.message}`);
        }
      };
      activeSocket.onerror = () => {
        if (disposed) return;
        clearResult();
        setAiStatus('WebSocket 异常，等待重连');
      };
      activeSocket.onclose = () => {
        if (disposed) return;
        clearResult();
        previousFrame = null;
        streamEpoch = null;
        setAiStatus('AI 连接已断开，正在重连');
        reconnectTimer = setTimeout(connect, Math.min(1000 * (2 ** attempt), 10000));
        attempt += 1;
      };
    };

    clearResult();
    if (websocketUrl) connect();
    else setAiStatus('未配置 VITE_DETECTIONS_WS_URL');
    return () => {
      disposed = true;
      clearTimeout(reconnectTimer);
      clearTimeout(expiryTimer);
      latestRef.current = null;
      if (socket) {
        socket.onopen = null;
        socket.onmessage = null;
        socket.onerror = null;
        socket.onclose = null;
        socket.close();
      }
    };
  }, [websocketUrl]);

  return { aiStatus, result, latestRef };
}
