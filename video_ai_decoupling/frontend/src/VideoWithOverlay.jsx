import React, { memo, useCallback, useEffect, useRef, useState } from 'react';
import WebRTCPlayer from '../../../lanhu/src/components/CenterPanel/components/MonitorGrid/WebRTCPlayer/index.jsx';
import useDetections from './useDetections.js';
import { clearOverlay, drawOverlay } from './overlay.js';

const StableWebRTCPlayer = memo(WebRTCPlayer);

export default function VideoWithOverlay({ originalVideoUrl, detectionsWebsocketUrl }) {
  const [status, setStatus] = useState('连接中...');
  const [showAnnotations, setShowAnnotations] = useState(true);
  const containerRef = useRef(null);
  const canvasRef = useRef(null);
  const annotationsRef = useRef(showAnnotations);
  const { aiStatus, result, latestRef } = useDetections(detectionsWebsocketUrl);

  const handleStatusChange = useCallback((nextStatus) => {
    setStatus(nextStatus);
  }, []);

  useEffect(() => {
    annotationsRef.current = showAnnotations;
  }, [showAnnotations]);

  useEffect(() => {
    const container = containerRef.current;
    const canvas = canvasRef.current;
    const video = container.querySelector('video');
    let animationId;
    const redraw = () => drawOverlay(canvas, video, latestRef.current, annotationsRef.current);
    const animate = () => {
      redraw();
      animationId = requestAnimationFrame(animate);
    };
    const observer = new ResizeObserver(redraw);
    observer.observe(container);
    if (video) {
      observer.observe(video);
      video.addEventListener('loadedmetadata', redraw);
      video.addEventListener('emptied', redraw);
    }
    window.addEventListener('resize', redraw);
    animationId = requestAnimationFrame(animate);
    return () => {
      cancelAnimationFrame(animationId);
      observer.disconnect();
      window.removeEventListener('resize', redraw);
      video?.removeEventListener('loadedmetadata', redraw);
      video?.removeEventListener('emptied', redraw);
      clearOverlay(canvas);
    };
  }, [originalVideoUrl, latestRef]);

  const videoTone = !originalVideoUrl ? 'error'
    : ['原始画面', '算法画面'].includes(status) ? 'success'
      : status === '连接中...' ? 'pending' : 'error';
  const aiTone = aiStatus === '检测中' ? 'success'
    : /^(等待连接|连接中|已连接|分析准备中)/.test(aiStatus) ? 'pending' : 'error';

  return (
    <section className="video-panel" aria-label="视频播放与检测结果">
      <dl className="status-grid">
        <div className="status-item">
          <dt>视频状态</dt>
          <dd>
            <span className="status-indicator" data-tone={videoTone}>
              <span className="status-dot" aria-hidden="true" />
              <span data-testid="video-status">{originalVideoUrl ? status : '未配置 VITE_ORIGINAL_VIDEO_URL'}</span>
            </span>
          </dd>
        </div>
        <div className="status-item">
          <dt>AI 状态</dt>
          <dd>
            <span className="status-indicator" data-tone={aiTone}>
              <span className="status-dot" aria-hidden="true" />
              <span data-testid="ai-status" role="status">{aiStatus}</span>
            </span>
          </dd>
        </div>
        <div className="status-item">
          <dt>检测数量</dt>
          <dd className="metric-value" data-testid="detection-count">{result ? result.detections.length : '—'}</dd>
        </div>
        <div className="status-item">
          <dt title="模型推理耗时，不代表端到端延迟">推理耗时</dt>
          <dd className="metric-value inference-value" data-testid="inference-ms">{result ? `${result.inference_ms.toFixed(2)} ms` : '—'}</dd>
        </div>
      </dl>
      <div className="overlay-toolbar">
        <span className="toolbar-title">视频预览</span>
        <div className="annotation-controls">
          <label className="annotation-switch">
            <input
              type="checkbox"
              role="switch"
              aria-label="显示标注"
              checked={showAnnotations}
              onChange={event => setShowAnnotations(event.target.checked)}
            />
            <span className="switch-track" aria-hidden="true" />
            <span>显示标注</span>
          </label>
          <span className="toolbar-hint">仅控制检测框显示</span>
        </div>
      </div>
      <div className="video-container" ref={containerRef}>
        {originalVideoUrl && (
          <StableWebRTCPlayer
            primaryUrl=""
            fallbackUrl={originalVideoUrl}
            onStatusChange={handleStatusChange}
          />
        )}
        <canvas className="detection-overlay" ref={canvasRef} aria-label="AI 检测框" />
      </div>
      <footer className="video-notes">
        <p>全屏暂不显示标注。</p>
      </footer>
    </section>
  );
}
