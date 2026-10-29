import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { parseDetectionMessage } from '../utils/detectionProtocol.js';
import { DetectionChannel, detectionKey } from '../utils/detectionChannel.js';
import { ServerClock } from '../utils/videoAlignment.js';
import { detectionSocketPath, detectionTask } from '../config/videoDeployment.js';

const DetectionContext = createContext(null);
const CAMERA_IDS = ['camera_1', 'camera_2', 'camera_3', 'camera_4'];
const TASK = detectionTask(import.meta.env);

export function DetectionWebSocketProvider({ enabled, children }) {
  const channelsRef = useRef(null);
  if (!channelsRef.current) channelsRef.current = Object.fromEntries(
    CAMERA_IDS.map(id => [detectionKey(id, TASK), new DetectionChannel(id, TASK)]),
  );
  const [channels, setChannels] = useState({});

  useEffect(() => {
    let disposed = false;
    let socket;
    let reconnectTimer;
    let heartbeatTimer;
    let clockTimer;
    const clock = new ServerClock();
    let attempt = 0;
    const all = Object.values(channelsRef.current);
    const refresh = () => {
      if (!disposed) setChannels(Object.fromEntries(all.map(c => [detectionKey(c.cameraId, c.task), c.snapshot()])));
    };
    const reset = status => { all.forEach(c => c.reset(status)); refresh(); };
    const connect = () => {
      if (disposed) return;
      reset('连接中');
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      socket = new WebSocket(`${protocol}//${window.location.host}${detectionSocketPath()}`);
      const current = socket;
      const watchHeartbeat = () => {
        clearTimeout(heartbeatTimer);
        heartbeatTimer = setTimeout(() => {
          if (disposed || socket !== current) return;
          reset('响应超时');
          current.close();
        }, 5000);
      };
      current.onopen = () => {
        if (disposed || socket !== current) return;
        attempt = 0;
        reset('等待检测');
        watchHeartbeat();
        clock.reset();
        const ping = () => { if (current.readyState === WebSocket.OPEN) current.send(JSON.stringify({ type: 'clock_ping', client_ms: performance.now() })); };
        ping();
        clearInterval(clockTimer);
        clockTimer = setInterval(ping, 5000);
      };
      current.onmessage = event => {
        if (disposed || socket !== current) return;
        try {
          const raw = JSON.parse(event.data);
          if (raw.type === 'clock_pong') { clock.accept(raw, performance.now()); return; }
          const message = parseDetectionMessage(event.data);
          const channel = channelsRef.current[detectionKey(message.camera_id, message.task)];
          if (!channel) return;
          if (channel.accept(message, performance.now(), clock)) {
            watchHeartbeat();
            refresh();
          }
        } catch {
          // Malformed messages have no trusted routing key; close and clear all channels.
          reset('检测消息异常');
          current.close();
        }
      };
      current.onerror = () => current.close();
      current.onclose = () => {
        if (disposed || socket !== current) return;
        clearTimeout(heartbeatTimer);
        clearInterval(clockTimer);
        reset('连接已断开，正在重连');
        reconnectTimer = setTimeout(connect, Math.min(1000 * (2 ** attempt++), 10000));
      };
    };
    reset(enabled ? '连接中' : '分析未启用');
    if (enabled) connect();
    const expiryTimer = setInterval(() => {
      let changed = false;
      all.forEach(c => { if (c.expire(performance.now())) changed = true; });
      if (changed) refresh();
    }, 100);
    const visibility = () => {
      if (!document.hidden && enabled) {
        reset('等待检测');
        clock.reset();
        socket?.close(); // discard queued pre-background results and re-establish sessions
      }
    };
    document.addEventListener('visibilitychange', visibility);
    return () => {
      disposed = true;
      clearInterval(expiryTimer);
      clearTimeout(reconnectTimer);
      clearTimeout(heartbeatTimer);
      clearInterval(clockTimer);
      document.removeEventListener('visibilitychange', visibility);
      all.forEach(c => c.reset('连接已断开'));
      if (socket) {
        socket.onopen = socket.onmessage = socket.onerror = socket.onclose = null;
        socket.close();
      }
    };
  }, [enabled]);

  return <DetectionContext.Provider value={channels}>{children}</DetectionContext.Provider>;
}

export function useDetections(cameraId, task = TASK) {
  const channels = useContext(DetectionContext);
  const emptyRef = useRef(null);
  const emptyHistory = useRef([]);
  return channels?.[detectionKey(cameraId, task)] || {
    latestRef: emptyRef, historyRef: emptyHistory, result: null, aiStatus: '等待检测',
  };
}
