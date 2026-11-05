/*
 * WebRTC 低延迟播放器。
 * 优先播放算法流；算法流不可用或停止产出画面时，保持原画面直到原始流就绪。
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  ALGORITHM_PROBE_INTERVAL,
  FRAME_STALE_TIMEOUT,
  PRIMARY_CONNECT_TIMEOUT,
  buildWhepUrl,
  whepSessionUrl,
  releaseWhepSession,
} from './webrtcPolicy.js';

const ICE_GATHERING_TIMEOUT = 1000;
const RECONNECT_DELAYS = [2000, 5000, 10000];

const WebRTCPlayer = ({ primaryUrl, fallbackUrl, onStatusChange, videoElementRef, fullscreenTargetRef }) => {
  const [status, setStatus] = useState('连接中...');  //当前显示状态
  const [isFullscreen, setIsFullscreen] = useState(false); //是否全屏
  const videoRef = useRef(null); // <video> DOM 元素引用
  const containerRef = useRef(null);    // 外层容器引用  
  const onStatusChangeRef = useRef(onStatusChange); // 存回调函数

  useEffect(() => {
    onStatusChangeRef.current = onStatusChange;
  }, [onStatusChange]);

  const toggleFullscreen = () => {
    const target = fullscreenTargetRef?.current || containerRef.current;
    if (!target) return;

    if (!document.fullscreenElement) {
      target.requestFullscreen().catch((error) => {
        console.error(`无法进入全屏: ${error.message}`);
      });
    } else {
      document.exitFullscreen();
    }
  };

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(document.fullscreenElement === (fullscreenTargetRef?.current || containerRef.current));
    };

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, [fullscreenTargetRef]);

  useEffect(() => {
    if (videoElementRef) videoElementRef.current = videoRef.current;
    return () => {
      if (videoElementRef) videoElementRef.current = null;
    };
  }, [videoElementRef]);

  useEffect(() => {
    const video = videoRef.current;  // <video> 元素 
    let disposed = false;         // 组件是否已卸载（卸载后停止一切）
    let activeConnection = null;  // ★ 当前正在播放的连接
    let candidateConnection = null;  // 正在建立的"候选"连接
    let lastVideoFrameAt = 0;     // 最后一次收到画面的时间
    let frameCallbackId = null;   // 帧回调的 id
    let frameWatchTimer = null;   // 画面监控定时器
    let primaryProbeTimer = null; // 算法流探活定时器
    let reconnectTimer = null;    // 重连定时器
    let reconnectAttempt = 0;     // 重连次数
    let switching = false;        // ★ 是否正在"切换中"（防止并发切换）

    //  记录"刚收到一帧画面"的时间
    const markVideoFrame = () => {
      lastVideoFrameAt = performance.now();
    };
    video?.addEventListener('timeupdate', markVideoFrame);

    // 更新状态，并通知父组件
    const updateStatus = (nextStatus, source = null) => {
      if (disposed) return;
      setStatus(nextStatus);
      onStatusChangeRef.current?.(nextStatus, source);
    };

    const clearTimer = (timer) => {
      if (timer) clearTimeout(timer);
      return null;
    };

    const closeConnection = (connection) => {
      releaseWhepSession(connection);
      if (!connection || connection.closed) return;
      connection.closed = true;
      connection.abortController.abort();
      connection.pc.ontrack = null;
      connection.pc.oniceconnectionstatechange = null;
      connection.pc.onicegatheringstatechange = null;
      connection.pc.close();
      if (connection.previewVideo) {
        connection.previewVideo.pause();
        connection.previewVideo.srcObject = null;
      }
    };

    const waitForIceGathering = (pc, abortController) => new Promise((resolve) => {
      if (pc.iceGatheringState === 'complete' || abortController.signal.aborted) {
        resolve();
        return;
      }

      let timeoutId;
      const finish = () => {
        if (timeoutId) clearTimeout(timeoutId);
        pc.onicegatheringstatechange = null;
        abortController.signal.removeEventListener('abort', finish);
        resolve();
      };

      pc.onicegatheringstatechange = () => {
        if (pc.iceGatheringState === 'complete') finish();
      };
      abortController.signal.addEventListener('abort', finish, { once: true });
      timeoutId = setTimeout(finish, ICE_GATHERING_TIMEOUT);
    });

    const waitForFirstFrame = (stream, connection, timeoutMs) => new Promise((resolve, reject) => {
      if (connection.abortController.signal.aborted) {
        reject(new DOMException('连接已取消', 'AbortError'));
        return;
      }

      const previewVideo = document.createElement('video');
      connection.previewVideo = previewVideo;
      previewVideo.muted = true;
      previewVideo.autoplay = true;
      previewVideo.playsInline = true;
      previewVideo.srcObject = stream;

      let timeoutId;
      let previewFrameId;
      let settled = false;

      const finish = (error) => {
        if (settled) return;
        settled = true;
        if (timeoutId) clearTimeout(timeoutId);
        if (previewFrameId != null && previewVideo.cancelVideoFrameCallback) {
          previewVideo.cancelVideoFrameCallback(previewFrameId);
        }
        previewVideo.onloadeddata = null;
        connection.abortController.signal.removeEventListener('abort', onAbort);
        if (error) reject(error);
        else resolve();
      };

      const onAbort = () => finish(new DOMException('连接已取消', 'AbortError'));
      const onFrame = () => finish();

      previewVideo.onloadeddata = onFrame;
      if (previewVideo.requestVideoFrameCallback) {
        previewFrameId = previewVideo.requestVideoFrameCallback(onFrame);
      }
      connection.abortController.signal.addEventListener('abort', onAbort, { once: true });
      timeoutId = setTimeout(
        () => finish(new Error(`${connection.source} 流在 ${timeoutMs}ms 内没有视频帧`)),
        timeoutMs,
      );
      previewVideo.play().catch(() => {
        // 静音的隐藏 video 通常允许自动播放；最终仍以首帧或超时作为判断。
      });
    });

    const waitForStream = (streamPromise, abortController) => new Promise((resolve, reject) => {
      if (abortController.signal.aborted) {
        reject(new DOMException('连接已取消', 'AbortError'));
        return;
      }

      const onAbort = () => {
        abortController.signal.removeEventListener('abort', onAbort);
        reject(new DOMException('连接已取消', 'AbortError'));
      };
      abortController.signal.addEventListener('abort', onAbort, { once: true });

      streamPromise.then((stream) => {
        abortController.signal.removeEventListener('abort', onAbort);
        resolve(stream);
      });
    });

    const connectSource = async (source, url, timeoutMs) => {
      if (!url) throw new Error(`${source} 流地址为空`);

      const abortController = new AbortController();
      const pc = new RTCPeerConnection({ iceServers: [] });
      const connection = {
        source,
        pc,
        abortController,
        stream: null,
        sessionUrl: null,
        previewVideo: null,
        closed: false,
        onFailure: null,
      };
      candidateConnection = connection;

      const streamPromise = new Promise((resolve) => {
        pc.ontrack = (event) => {
          const stream = event.streams[0] || new MediaStream([event.track]);
          connection.stream = stream;
          resolve(stream);
        };
      });

      pc.oniceconnectionstatechange = () => {
        if (
          pc.iceConnectionState === 'failed'
          || pc.iceConnectionState === 'disconnected'
          || pc.iceConnectionState === 'closed'
        ) {
          connection.onFailure?.(pc.iceConnectionState);
        }
      };

      const timeoutId = setTimeout(() => abortController.abort(), timeoutMs);
      try {
        pc.addTransceiver('video', { direction: 'recvonly' });
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        await waitForIceGathering(pc, abortController);

        if (abortController.signal.aborted) {
          throw new DOMException('连接超时', 'AbortError');
        }

        const requestUrl = buildWhepUrl(url);
        const response = await fetch(requestUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/sdp' },
          body: pc.localDescription.sdp,
          signal: abortController.signal,
        });

        if (!response.ok) {
          throw new Error(`WHEP HTTP ${response.status}`);
        }

        connection.sessionUrl = whepSessionUrl(response.headers.get('Location'), requestUrl, window.location.href);
        if (connection.closed || disposed || abortController.signal.aborted) {
          throw new DOMException('连接已取消', 'AbortError');
        }

        await pc.setRemoteDescription({
          type: 'answer',
          sdp: await response.text(),
        });

        const stream = await waitForStream(streamPromise, abortController);
        await waitForFirstFrame(stream, connection, timeoutMs);
        return connection;
      } catch (error) {
        closeConnection(connection);
        throw error;
      } finally {
        clearTimeout(timeoutId);
        if (candidateConnection === connection) candidateConnection = null;
      }
    };

    const startFrameWatcher = () => {
      markVideoFrame();
      if (!video?.requestVideoFrameCallback) return;
      if (frameCallbackId != null && video.cancelVideoFrameCallback) {
        video.cancelVideoFrameCallback(frameCallbackId);
      }

      const onFrame = () => {
        if (disposed) return;
        markVideoFrame();
        frameCallbackId = video.requestVideoFrameCallback(onFrame);
      };
      frameCallbackId = video.requestVideoFrameCallback(onFrame);
    };

    const activateConnection = (connection) => {
      if (disposed) {
        closeConnection(connection);
        return;
      }

      const previousConnection = activeConnection;
      activeConnection = connection;
      reconnectAttempt = 0;
      connection.onFailure = (reason) => {
        if (activeConnection !== connection || disposed) return;
        console.warn(`${connection.source} 流连接中断: ${reason}`);
        if (connection.source === 'algorithm') {
          switchToFallback();
        } else {
          activeConnection = null;
          closeConnection(connection);
          if (video) video.srcObject = null;
          updateStatus('未连接', null);
          scheduleReconnect();
        }
      };

      if (video) {
        video.srcObject = connection.stream;
        video.play().catch(() => {});
      }
      if (connection.previewVideo) {
        connection.previewVideo.pause();
        connection.previewVideo.srcObject = null;
        connection.previewVideo = null;
      }
      startFrameWatcher();
      closeConnection(previousConnection);

      const nextStatus = connection.source === 'algorithm' ? '算法画面' : '原始画面';
      updateStatus(nextStatus, connection.source);
    };

    const schedulePrimaryProbe = () => {
      primaryProbeTimer = clearTimer(primaryProbeTimer);
      if (disposed || !primaryUrl || activeConnection?.source !== 'original') return;
      primaryProbeTimer = setTimeout(async () => {
        primaryProbeTimer = null;
        if (disposed || switching || activeConnection?.source !== 'original') return;

        switching = true;
        try {
          const connection = await connectSource(
            'algorithm',
            primaryUrl,
            PRIMARY_CONNECT_TIMEOUT,
          );
          activateConnection(connection);
        } catch (error) {
          if (error?.name !== 'AbortError') {
            console.debug('算法流尚未恢复:', error.message);
          }
        } finally {
          switching = false;
          if (activeConnection?.source === 'original') schedulePrimaryProbe();
        }
      }, ALGORITHM_PROBE_INTERVAL);
    };

    async function switchToFallback() {
      if (disposed || switching || activeConnection?.source === 'original') return;
      switching = true;
      primaryProbeTimer = clearTimer(primaryProbeTimer);
      try {
        const connection = await connectSource(
          'original',
          fallbackUrl,
          PRIMARY_CONNECT_TIMEOUT,
        );
        activateConnection(connection);
        schedulePrimaryProbe();
      } catch (error) {
        if (error?.name !== 'AbortError') {
          console.warn('原始流连接失败:', error.message);
        }
        if (!activeConnection) updateStatus('未连接', null);
        scheduleReconnect();
      } finally {
        switching = false;
      }
    }

    const scheduleReconnect = () => {
      reconnectTimer = clearTimer(reconnectTimer);
      if (disposed) return;
      const delay = RECONNECT_DELAYS[
        Math.min(reconnectAttempt, RECONNECT_DELAYS.length - 1)
      ];
      reconnectAttempt += 1;
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        startPlayback();
      }, delay);
    };

    const startPlayback = async () => {
      if (disposed || switching) return;
      switching = true;
      if (!activeConnection) updateStatus('连接中...', null);
      try {
        if (primaryUrl) {
          const connection = await connectSource(
            'algorithm',
            primaryUrl,
            PRIMARY_CONNECT_TIMEOUT,
          );
          activateConnection(connection);
        } else {
          const connection = await connectSource(
            'original',
            fallbackUrl,
            PRIMARY_CONNECT_TIMEOUT,
          );
          activateConnection(connection);
        }
      } catch (primaryError) {
        if (primaryError?.name !== 'AbortError') {
          console.debug('算法流不可用，切换原始流:', primaryError.message);
        }
        // 算法流和原始流使用同一个 MediaMTX。网络层连接失败时，
        // 继续请求原始路径只会产生相同的 ERR_CONNECTION_REFUSED。
        if (primaryError instanceof TypeError) {
          if (!activeConnection) updateStatus('未连接', null);
          scheduleReconnect();
          return;
        }
        try {
          const connection = await connectSource(
            'original',
            fallbackUrl,
            PRIMARY_CONNECT_TIMEOUT,
          );
          activateConnection(connection);
          if (primaryUrl) schedulePrimaryProbe();
        } catch (fallbackError) {
          if (fallbackError?.name !== 'AbortError') {
            console.warn('算法流和原始流均不可用:', fallbackError.message);
          }
          if (!activeConnection) updateStatus('未连接', null);
          scheduleReconnect();
        }
      } finally {
        switching = false;
      }
    };

    frameWatchTimer = setInterval(() => {
      const source = activeConnection?.source;
      if (
        source
        && lastVideoFrameAt > 0
        && performance.now() - lastVideoFrameAt >= FRAME_STALE_TIMEOUT
      ) {
        if (source === 'algorithm') {
          console.warn('算法流超过 3 秒没有新画面，切换原始实时流');
          switchToFallback();
        } else if (!switching) {
          console.warn('原始流超过 3 秒没有新画面，重新连接');
          const staleConnection = activeConnection;
          activeConnection = null;
          closeConnection(staleConnection);
          if (video) video.srcObject = null;
          updateStatus('未连接', null);
          scheduleReconnect();
        }
      }
    }, 500);

    startPlayback();

    return () => {
      disposed = true;
      if (frameWatchTimer) clearInterval(frameWatchTimer);
      primaryProbeTimer = clearTimer(primaryProbeTimer);
      reconnectTimer = clearTimer(reconnectTimer);
      if (frameCallbackId != null && video?.cancelVideoFrameCallback) {
        video.cancelVideoFrameCallback(frameCallbackId);
      }
      closeConnection(candidateConnection);
      closeConnection(activeConnection);
      if (video) {
        video.removeEventListener('timeupdate', markVideoFrame);
        video.srcObject = null;
      }
    };
  }, [primaryUrl, fallbackUrl]);

  const connected = status === '算法画面' || status === '原始画面';

  return (
    <div
      ref={containerRef}
      onDoubleClick={toggleFullscreen}
      style={{
        textAlign: 'center',
        background: '#0a0a1a',
        position: 'relative',
        width: '100%',
        height: '100%',
        cursor: 'pointer',
      }}
      title="双击全屏"
    >
      {!connected && (
        <div style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#0a0a1a',
          color: 'rgba(255, 255, 255, 0.6)',
          zIndex: 10,
          fontSize: '16px',
          fontFamily: 'PingFangSC-Regular',
        }}>
          {status === '连接中...' ? '连接中...' : '未连接摄像头'}
        </div>
      )}
      <video
        ref={videoRef}
        style={{ width: '100%', height: '100%', background: '#000', objectFit: 'contain' }}
        autoPlay
        muted
        playsInline
      />

      <button
        onClick={toggleFullscreen}
        style={{
          position: 'absolute',
          bottom: '12px',
          right: '12px',
          padding: '6px 10px',
          background: 'rgba(0, 0, 0, 0.6)',
          color: '#fff',
          border: '1px solid rgba(65, 177, 255, 0.5)',
          borderRadius: '4px',
          cursor: 'pointer',
          fontSize: '12px',
          zIndex: 20,
          opacity: 0.7,
        }}
        title={isFullscreen ? '退出全屏 (ESC)' : '全屏'}
      >
        {isFullscreen ? '⛶ 退出' : '⛶ 全屏'}
      </button>
    </div>
  );
};

export default WebRTCPlayer;
