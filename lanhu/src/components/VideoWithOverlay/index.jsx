import React, { memo, useCallback, useEffect, useRef, useState } from 'react';
import WebRTCPlayer from '../CenterPanel/components/MonitorGrid/WebRTCPlayer/index.jsx';
import { useDetections } from '../../contexts/DetectionWebSocketContext.jsx';
import { startAlignedRenderer } from '../../utils/alignedVideoRenderer.js';
import styles from './VideoWithOverlay.module.css';

const StablePlayer = memo(WebRTCPlayer);

export default function VideoWithOverlay({ cameraId, originalVideoUrl, onStatusChange }) {
  const containerRef = useRef(null);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const playbackRef = useRef(null);
  const [videoStatus, setVideoStatus] = useState('连接中...');
  const drawState = useRef({ enabled: true, status: '连接中...' });
  const { latestRef, historyRef, identity } = useDetections(cameraId);
  const statusCallback = useRef(onStatusChange);
  statusCallback.current = onStatusChange;
  drawState.current = { enabled: true, status: videoStatus, mode: 'realtime', identity };

  const handleStatusChange = useCallback((status, source) => {
    setVideoStatus(status);
    statusCallback.current?.(status, source);
  }, []);

  useEffect(() => {
    if (!videoRef.current) return undefined;
    return startAlignedRenderer({ video: videoRef.current, overlay: canvasRef.current, playback: playbackRef.current,
      state: drawState, historyRef, latestRef });
  }, [originalVideoUrl, latestRef, historyRef]);

  return (
    <div className={styles.container} ref={containerRef} data-testid="video-with-overlay" data-camera-id={cameraId}>
      <StablePlayer
        primaryUrl=""
        fallbackUrl={originalVideoUrl}
        onStatusChange={handleStatusChange}
        videoElementRef={videoRef}
        fullscreenTargetRef={containerRef}
      />
      <canvas ref={canvasRef} className={styles.canvas} aria-label="AI 检测框" />
      <canvas ref={playbackRef} className={styles.playback} aria-label="同步原始视频" />
    </div>
  );
}
