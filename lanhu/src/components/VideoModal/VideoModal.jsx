import React from 'react';
import ReactDOM from 'react-dom';
import styles from './VideoModal.module.css';
import AssetVideoPlayback from './AssetVideoPlayback';
import {
  MAX_PLAYBACK_RETRIES,
  canRetryPlayback,
  classifyPlaybackPreflightResponse,
  getPendingRecordingRetryDelay
} from './videoPlaybackPolicy';

// 视频播放器组件
function VideoPlayback({ url }) {
  const videoRef = React.useRef(null);
  const [status, setStatus] = React.useState('加载中...');
  const [error, setError] = React.useState(null);
  const [buffered, setBuffered] = React.useState(0);
  const [videoSrc, setVideoSrc] = React.useState(null);
  const [loadVersion, setLoadVersion] = React.useState(0);
  const timeoutRef = React.useRef(null);
  const retryTimeoutRef = React.useRef(null);
  const requestRef = React.useRef(null);
  const retryCountRef = React.useRef(0);
  const generationRef = React.useRef(0);
  const mountedRef = React.useRef(false);
  const startLoadRef = React.useRef(null);

  const LOAD_TIMEOUT = 30000; // 30秒超时

  const clearTimeouts = React.useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = null;
    }
  }, []);

  const cancelPendingWork = React.useCallback(() => {
    clearTimeouts();
    if (requestRef.current) {
      requestRef.current.abort();
      requestRef.current = null;
    }
  }, [clearTimeouts]);

  // 验证视频 URL
  const validateUrl = React.useCallback((value) => {
    if (!value || typeof value !== 'string') {
      return false;
    }
    try {
      const urlObj = new URL(value, window.location.href);
      return urlObj.protocol === 'http:' || urlObj.protocol === 'https:';
    } catch {
      return false;
    }
  }, []);

  const scheduleRetry = React.useCallback((message) => {
    if (!mountedRef.current) {
      return;
    }

    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current);
    }

    if (!canRetryPlayback(retryCountRef.current)) {
      setStatus('加载失败');
      setError(message);
      setVideoSrc(null);
      return;
    }

    retryCountRef.current += 1;
    setStatus(`加载失败，正在重试... (${retryCountRef.current}/${MAX_PLAYBACK_RETRIES})`);
    setError(null);
    setBuffered(0);
    setVideoSrc(null);

    retryTimeoutRef.current = setTimeout(() => {
      retryTimeoutRef.current = null;
      if (mountedRef.current) {
        startLoadRef.current?.();
      }
    }, 2000);
  }, []);

  const scheduleRecordingRetry = React.useCallback((delayMs) => {
    if (!mountedRef.current) {
      return;
    }
    clearTimeouts();
    setStatus('录像正在生成，等待分段完成...');
    setError(null);
    setBuffered(0);
    setVideoSrc(null);

    retryTimeoutRef.current = setTimeout(() => {
      retryTimeoutRef.current = null;
      if (mountedRef.current) {
        startLoadRef.current?.();
      }
    }, delayMs);
  }, [clearTimeouts]);

  const startLoad = React.useCallback(async () => {
    cancelPendingWork();
    const generation = ++generationRef.current;

    if (!validateUrl(url)) {
      if (mountedRef.current) {
        setStatus('加载失败');
        setError('无效的视频地址');
        setVideoSrc(null);
      }
      return;
    }

    setStatus('正在检查录像...');
    setError(null);
    setBuffered(0);
    setVideoSrc(null);

    const controller = new AbortController();
    requestRef.current = controller;

    try {
      // MediaMTX reports 404 for HEAD even when the recording can be read.
      // A one-byte GET verifies the same endpoint the video element will use.
      const response = await fetch(url, {
        headers: { Range: 'bytes=0-0' },
        cache: 'no-store',
        signal: controller.signal
      });
      if (!mountedRef.current || generation !== generationRef.current) {
        return;
      }
      requestRef.current = null;

      const responseType = classifyPlaybackPreflightResponse(response.status, response.ok);
      // Some MediaMTX versions ignore Range and begin a full response. The
      // player will issue its own request after this check, so release it now.
      if (response.body) {
        response.body.cancel().catch(() => {});
      }
      if (responseType === 'missing') {
        const pendingRecordingDelay = getPendingRecordingRetryDelay(url);
        if (pendingRecordingDelay !== null) {
          scheduleRecordingRetry(pendingRecordingDelay);
          return;
        }
        setStatus('加载失败');
        setError('录像不存在或已过期');
        return;
      }
      if (responseType === 'retryable') {
        scheduleRetry(`回放服务暂时不可用（${response.status}）`);
        return;
      }
      if (responseType === 'unavailable') {
        setStatus('加载失败');
        setError(`回放地址不可用（${response.status}）`);
        return;
      }

      setStatus('加载中...');
      setVideoSrc(url);
      setLoadVersion((value) => value + 1);
    } catch (requestError) {
      if (requestError.name === 'AbortError'
        || !mountedRef.current
        || generation !== generationRef.current) {
        return;
      }
      requestRef.current = null;
      scheduleRetry('网络错误，请检查网络连接');
    }
  }, [cancelPendingWork, scheduleRecordingRetry, scheduleRetry, url, validateUrl]);

  startLoadRef.current = startLoad;

  React.useEffect(() => {
    mountedRef.current = true;
    retryCountRef.current = 0;
    startLoad();

    return () => {
      mountedRef.current = false;
      generationRef.current += 1;
      cancelPendingWork();
      const video = videoRef.current;
      if (video) {
        video.pause();
        video.removeAttribute('src');
      }
    };
  }, [cancelPendingWork, startLoad]);

  const handleLoadStart = () => {
    if (!mountedRef.current) return;
    setStatus('加载中...');
    setError(null);
    setBuffered(0);
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    timeoutRef.current = setTimeout(() => {
      if (videoRef.current && videoRef.current.readyState < 3) {
        scheduleRetry('视频加载超时，请稍后重试');
      }
    }, LOAD_TIMEOUT);
  };

  const handleProgress = () => {
    if (!mountedRef.current) return;
    if (videoRef.current) {
      const buffered = videoRef.current.buffered;
      if (buffered.length > 0) {
        const bufferedEnd = buffered.end(buffered.length - 1);
        const duration = videoRef.current.duration;
        if (duration > 0) {
          const bufferedPercent = (bufferedEnd / duration) * 100;
          setBuffered(bufferedPercent);
          
          // 如果缓冲超过10%，清除超时定时器
          if (bufferedPercent > 10 && timeoutRef.current) {
            clearTimeout(timeoutRef.current);
            timeoutRef.current = null;
          }
        }
      }
    }
  };

  const handleLoadedData = () => {
    if (!mountedRef.current) return;
    clearTimeouts();
    retryCountRef.current = 0;
    setStatus('播放中');
  };

  const handleCanPlay = () => {
    if (!mountedRef.current) return;
    clearTimeouts();
    retryCountRef.current = 0;
    setStatus('播放中');
  };

  const handleCanPlayThrough = () => {
    if (!mountedRef.current) return;
    clearTimeouts();
    setStatus('播放中');
    setBuffered(100);
  };

  const handlePlaying = () => {
    if (!mountedRef.current) return;
    clearTimeouts();
    retryCountRef.current = 0;
    setStatus('播放中');
  };

  const handleWaiting = () => {
    if (!mountedRef.current) return;
    setStatus('缓冲中...');
  };

  const handleError = (e) => {
    if (!mountedRef.current) return;
    console.error('🎬 [VideoPlayback] 视频加载失败:', e);
    clearTimeouts();
    
    const video = videoRef.current;
    let errorMsg = '无法加载视频';
    
    if (video) {
      switch (video.error?.code) {
        case 1: // MEDIA_ERR_ABORTED
          errorMsg = '视频加载被中止';
          break;
        case 2: // MEDIA_ERR_NETWORK
          errorMsg = '网络错误，请检查网络连接';
          break;
        case 3: // MEDIA_ERR_DECODE
          errorMsg = '视频解码失败';
          break;
        case 4: // MEDIA_ERR_SRC_NOT_SUPPORTED
          errorMsg = '视频格式不支持';
          break;
        default:
          errorMsg = '无法加载视频，请检查视频地址是否有效';
      }
    }
    
    if (video?.error?.code === 2) {
      scheduleRetry(errorMsg);
    } else {
      setStatus('加载失败');
      setError(errorMsg);
    }
  };

  return (
    <div className={styles.webrtcPlayerContainer}>
      {status !== '播放中' && (
        <div className={styles.playerOverlay}>
          {error ? (
            <>
              <span className={styles.playerError}>❌ {error}</span>
              <span className={styles.playerHint}>
                {error === '录像不存在或已过期' ? '该告警仍可查看图片和信息' : '请检查视频地址或稍后重试'}
              </span>
              <button
                className={styles.retryButton}
                onClick={() => {
                  retryCountRef.current = 0;
                  startLoadRef.current?.();
                }}
              >
                重试
              </button>
            </>
          ) : (
            <>
              <span className={styles.playerStatus}>{status}</span>
              {buffered > 0 && buffered < 100 && (
                <div className={styles.progressContainer}>
                  <div className={styles.progressBar}>
                    <div 
                      className={styles.progressFill} 
                      style={{ width: `${buffered}%` }}
                    />
                  </div>
                  <span className={styles.progressText}>{Math.round(buffered)}%</span>
                </div>
              )}
            </>
          )}
        </div>
      )}
      <video 
        key={`${url}_${loadVersion}`}
        ref={videoRef}
        className={styles.videoPlayer}
        src={videoSrc || undefined}
        autoPlay 
        controls
        playsInline
        preload="auto"
        onLoadStart={handleLoadStart}
        onProgress={handleProgress}
        onLoadedData={handleLoadedData}
        onCanPlay={handleCanPlay}
        onCanPlayThrough={handleCanPlayThrough}
        onPlaying={handlePlaying}
        onWaiting={handleWaiting}
        onError={handleError}
        onLoadedMetadata={(e) => {
          console.log('[VideoModal] 📊 视频元数据加载完成:', {
            url,
            duration: e.target.duration,
            videoWidth: e.target.videoWidth,
            videoHeight: e.target.videoHeight
          });
        }}
      />
    </div>
  );
}

// 统一的视频弹窗组件
function VideoModal({ visible, url, playback, title, time, onClose }) {
  const modalRef = React.useRef(null);
  React.useEffect(() => {
    if (!visible) return undefined;
    const previousFocus = document.activeElement;
    modalRef.current?.focus();
    return () => previousFocus?.focus();
  }, [visible]);
  if (!visible) return null;

  const handleKeys = event => {
    event.stopPropagation();
    if (event.key === 'Escape') { onClose(); return; }
    if (event.key !== 'Tab') return;
    const controls = [...modalRef.current.querySelectorAll('button:not(:disabled), input:not(:disabled), video[controls]')];
    const first = controls[0], last = controls[controls.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === modalRef.current)) {
      event.preventDefault(); last?.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault(); first?.focus();
    }
  };

  // 使用 Portal 渲染到 body，避免受父容器样式影响
  return ReactDOM.createPortal(
    <div className={styles.videoModalOverlay} onClick={onClose}>
      <div ref={modalRef} className={styles.videoModalContent} role="dialog" aria-modal="true" aria-label={title || '录像回放'}
        tabIndex={-1} onKeyDown={handleKeys} onClick={(e) => e.stopPropagation()}>
        {/* 弹窗标题栏 */}
        <div className={styles.videoModalHeader}>
          <div className={styles.videoModalTitle}>
            <span className={styles.videoModalTitleText}>{title}</span>
            <span className={styles.videoModalTime}>{time}</span>
          </div>
          <button className={styles.videoModalClose} aria-label="关闭录像" onClick={onClose}>
            ✕
          </button>
        </div>
        {/* 视频播放器 */}
        <div className={styles.videoModalBody}>
          {playback ? <AssetVideoPlayback key={playback.asset_id} asset={playback} /> : <VideoPlayback url={url} />}
        </div>
      </div>
    </div>,
    document.body
  );
}

export default VideoModal;
