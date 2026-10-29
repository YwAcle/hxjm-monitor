import React from 'react';
import { businessApi } from '../../services/businessApi';
import { clearOverlay, drawOverlay } from '../../utils/detectionOverlay';
import { historicalWindow, matchHistoricalFrame, historicalDetections, loadHistoricalWindow } from '../../utils/historicalResults';
import styles from './VideoModal.module.css';

export default function AssetVideoPlayback({ asset }) {
  const videoRef = React.useRef(null);
  const canvasRef = React.useRef(null);
  const [ticket, setTicket] = React.useState(null);
  const [error, setError] = React.useState('');
  const [loading, setLoading] = React.useState(true);
  const [reload, setReload] = React.useState(0);
  const [showBoxes, setShowBoxes] = React.useState(true);
  const [overlayStatus, setOverlayStatus] = React.useState('历史结果加载中…');
  const retryRef = React.useRef(0);
  const offsetRef = React.useRef(Math.max(0, Number(asset.offset_ms) || 0) / 1000);
  const showBoxesRef = React.useRef(showBoxes);
  const renderRef = React.useRef(null);
  const presentedTimeRef = React.useRef(null);
  showBoxesRef.current = showBoxes;

  React.useEffect(() => {
    const controller = new AbortController();
    setTicket(null); setError(''); setLoading(true);
    businessApi.playbackTicket(asset.asset_id, controller.signal).then(data => {
      if (!controller.signal.aborted) setTicket(data);
    }).catch(exception => {
      if (exception.name !== 'AbortError') { setError(exception.message); setLoading(false); }
    });
    return () => controller.abort();
  }, [asset.asset_id, reload]);

  React.useEffect(() => {
    const video = videoRef.current, canvas = canvasRef.current;
    if (!ticket || !video || !canvas) return undefined;
    presentedTimeRef.current = null;
    if (!video.requestVideoFrameCallback) {
      setOverlayStatus('当前浏览器不支持逐帧检测框同步，录像可正常播放');
      return undefined;
    }
    const controller = new AbortController();
    const windows = new Map();
    const pending = new Set();
    const failures = new Map();
    let callbackId;
    let presentedTime = null;
    let status = '';
    const updateStatus = value => {
      if (value !== status) { status = value; setOverlayStatus(value); }
    };
    const load = window => {
      if (!window || windows.has(window.key) || pending.has(window.key) || failures.has(window.key)) return;
      pending.add(window.key);
      loadHistoricalWindow(businessApi, asset, window, controller.signal).then(items => {
        if (controller.signal.aborted) return;
        windows.set(window.key, items);
        // Keep the nearby playback windows; seeking loads another small window.
        if (windows.size > 6) windows.delete(windows.keys().next().value);
        if (video.paused && presentedTime != null) render(presentedTime);
      }).catch(exception => {
        if (exception.name !== 'AbortError' && !controller.signal.aborted) {
          failures.set(window.key, exception.message);
          if (presentedTime != null && historicalWindow(presentedTime)?.key === window.key) {
            clearOverlay(canvas);
            updateStatus(`检测结果未加载：${exception.message}`);
          }
        }
      }).finally(() => pending.delete(window.key));
    };
    const render = mediaTime => {
      presentedTime = mediaTime;
      presentedTimeRef.current = mediaTime;
      const window = historicalWindow(mediaTime);
      if (!window || !showBoxesRef.current) {
        clearOverlay(canvas); updateStatus(showBoxesRef.current ? '此画面无已保存处理结果' : '已隐藏检测框'); return;
      }
      load(window);
      if (window.end_ms - mediaTime * 1000 < 1500) load(historicalWindow(window.end_ms / 1000));
      const items = windows.get(window.key);
      if (!items) {
        clearOverlay(canvas);
        updateStatus(failures.has(window.key) ? `检测结果未加载：${failures.get(window.key)}` : '历史结果加载中…');
        return;
      }
      const frame = matchHistoricalFrame(items, asset.asset_id, mediaTime);
      if (!frame) { clearOverlay(canvas); updateStatus('此画面无已保存处理结果'); return; }
      const detections = historicalDetections(frame);
      drawOverlay(canvas, video, { message: { frame_id: frame.frame_id, detections } }, true, 0, true);
      updateStatus(detections.length ? `当前处理帧：${detections.length} 个目标` : '当前处理帧：无目标');
    };
    renderRef.current = render;
    const onFrame = (_now, metadata) => {
      if (video.seeking) { presentedTime = null; presentedTimeRef.current = null; clearOverlay(canvas); }
      else render(metadata.mediaTime);
      callbackId = video.requestVideoFrameCallback(onFrame);
    };
    const onSeeking = () => { presentedTime = null; presentedTimeRef.current = null; clearOverlay(canvas); };
    const onResize = () => { if (presentedTime != null) render(presentedTime); };
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(onResize);
    observer?.observe(video);
    video.addEventListener('seeking', onSeeking);
    callbackId = video.requestVideoFrameCallback(onFrame);
    load(historicalWindow(offsetRef.current));
    return () => {
      controller.abort();
      video.cancelVideoFrameCallback(callbackId);
      video.removeEventListener('seeking', onSeeking);
      observer?.disconnect();
      renderRef.current = null;
      presentedTimeRef.current = null;
      clearOverlay(canvas);
    };
  }, [asset, ticket]);

  React.useEffect(() => {
    if (presentedTimeRef.current != null) renderRef.current?.(presentedTimeRef.current);
  }, [showBoxes]);

  const retry = () => {
    const video = videoRef.current;
    if (video?.readyState > 0 && Number.isFinite(video.currentTime)) offsetRef.current = video.currentTime;
    setReload(value => value + 1);
  };
  const onVideoError = () => {
    if (!ticket) return;
    setLoading(false);
    if (retryRef.current < 1) {
      retryRef.current += 1;
      retry();
    } else setError('录像暂不可播放，请重试；登录或录像到期后需重新查询');
  };

  return <div className={styles.assetPlayback}>
    <div className={styles.historyToolbar}>
      <label><input type="checkbox" checked={showBoxes} onChange={event => setShowBoxes(event.target.checked)} /> 显示历史检测框</label>
      <span role="status">{overlayStatus}</span>
    </div>
    <div className={styles.webrtcPlayerContainer}>
      <video ref={videoRef} className={styles.videoPlayer} src={ticket?.url} autoPlay controls playsInline preload="metadata"
        onLoadedMetadata={event => {
          const video = event.currentTarget;
          const end = Number.isFinite(video.duration) ? Math.max(0, video.duration - 0.001) : offsetRef.current;
          video.currentTime = Math.min(offsetRef.current, end);
        }}
        onCanPlay={() => setLoading(false)} onPlaying={() => setLoading(false)} onError={onVideoError} />
      <canvas className={styles.historyCanvas} ref={canvasRef} aria-hidden="true" />
      {(loading || error) && <div className={styles.playerOverlay}>
        <span className={error ? styles.playerError : styles.playerStatus}>{error || '正在加载录像…'}</span>
        {error && <button className={styles.retryButton} type="button" onClick={() => { retryRef.current = 0; retry(); }}>重试</button>}
      </div>}
    </div>
  </div>;
}
