import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import styles from './MonitorGrid.module.css';
import WebRTCPlayer from './WebRTCPlayer/index.jsx';
import VideoWithOverlay from '../../../VideoWithOverlay/index.jsx';
import { DetectionWebSocketProvider } from '../../../../contexts/DetectionWebSocketContext.jsx';
import { videoAnalysisEnabled, videoMediaBase, synchronizedAnalysisAllowed } from '../../../../config/videoDeployment.js';

function MonitorGrid() {
  // 视频流地址
  const mediaBaseUrl = videoMediaBase(import.meta.env, window.location);
  const algorithmsEnabled = import.meta.env.VITE_VIDEO_ANALYSIS_MODE === 'local'
    && import.meta.env.VITE_ENABLE_DEEPSORT !== 'false';
  const analysisEnabled = videoAnalysisEnabled(import.meta.env);
  const analysisCameras = (import.meta.env.VITE_VIDEO_ANALYSIS_CAMERAS || 'camera_1,camera_2,camera_3,camera_4').split(',');

  // 摄像头配置 - 包含视频流URL
  // primaryUrl 检测流（带 YOLO 检测框）     fallbackUrl 原始流（无检测框）
  const cameras = [
    {
      id: '001',
      name: '摄像头001',
      primaryUrl: algorithmsEnabled ? `${mediaBaseUrl}/camera_1_deepsort/` : '',
      fallbackUrl: `${mediaBaseUrl}/camera_1/`,
    },
    {
      id: '002',
      name: '摄像头002',
      primaryUrl: algorithmsEnabled ? `${mediaBaseUrl}/camera_2_deepsort/` : '',
      fallbackUrl: `${mediaBaseUrl}/camera_2/`,
    },
    {
      id: '003',
      name: '摄像头003',
      primaryUrl: algorithmsEnabled ? `${mediaBaseUrl}/camera_3_deepsort/` : '',
      fallbackUrl: `${mediaBaseUrl}/camera_3/`,
    },
    {
      id: '004',
      name: '摄像头004',
      primaryUrl: algorithmsEnabled ? `${mediaBaseUrl}/camera_4_deepsort/` : '',
      fallbackUrl: `${mediaBaseUrl}/camera_4/`,
    },
  ];

  // 跟踪每个摄像头的连接状态
  const [cameraStatus, setCameraStatus] = useState({});
  const [annotationsEnabled, setAnnotationsEnabled] = useState(true);
  const [synchronized, setSynchronized] = useState(false);
  const [controlsTarget, setControlsTarget] = useState(null);
  useEffect(() => {
    const onFullscreen = () => setControlsTarget(
      document.fullscreenElement?.matches('[data-testid="video-with-overlay"]') ? document.fullscreenElement : null,
    );
    document.addEventListener('fullscreenchange', onFullscreen);
    return () => document.removeEventListener('fullscreenchange', onFullscreen);
  }, []);

  // 处理状态变化
  const handleStatusChange = (cameraId, status) => {
    setCameraStatus(prev => ({
      ...prev,  // 保留其他摄像头的状态
      [cameraId]: status   // 只更新这一个摄像头的状态
    }));
  };

  // 判断是否已连接
  const isConnected = (cameraId) => {
    return cameraStatus[cameraId] === '算法画面'
      || cameraStatus[cameraId] === '原始画面';
  };

  const renderPlayer = camera => {
    const onStatusChange = status => handleStatusChange(camera.id, status);
    if (analysisEnabled && analysisCameras.includes(`camera_${Number(camera.id)}`)) {
      return <VideoWithOverlay cameraId={`camera_${Number(camera.id)}`} originalVideoUrl={camera.fallbackUrl}
        onStatusChange={onStatusChange} annotationsEnabled={annotationsEnabled} synchronized={synchronized} />;
    }
    return <WebRTCPlayer primaryUrl={camera.primaryUrl} fallbackUrl={camera.fallbackUrl} onStatusChange={onStatusChange} />;
  };

  const controls = (
    <div className={controlsTarget ? styles.fullscreenControls : styles.controls}>
      {synchronizedAnalysisAllowed(import.meta.env) && <button type="button" aria-label="同帧验收模式" aria-pressed={synchronized}
        onClick={() => setSynchronized(value => !value)}
        title="同帧验收时画面随 AI 更新；实时视频中的框可能存在时间偏差">
        {synchronized ? '同帧验收（随 AI 更新）' : '实时视频（异步检测框）'}
      </button>}
      <button type="button" aria-label="显示检测框" aria-pressed={annotationsEnabled}
        onClick={() => setAnnotationsEnabled(value => !value)}>
        检测框：{annotationsEnabled ? '显示' : '隐藏'}
      </button>
    </div>
  );

  return (
    <DetectionWebSocketProvider enabled={analysisEnabled} synchronized={synchronized}>
      <div className={styles.gridContainer}>
        {analysisEnabled && (controlsTarget ? createPortal(controls, controlsTarget) : controls)}
        {/* 第一行摄像头 */}
        <div className={`${styles.cameraRow} flex-row justify-between`}>
          {cameras.slice(0, 2).map((camera) => (
            <div
              key={camera.id}
              className={styles.cameraContainer}
            >
              {/* WebRTC 视频播放器 */}
              <div className={styles.videoWrapper}>
                {renderPlayer(camera)}
              </div>
              <div className={`${styles.cameraFooter} flex-row`}>
                <div className={`${styles.cameraInfo} flex-row justify-between`}>
                  <span className={styles.cameraName}>{camera.name}</span>
                  <div
                    className={isConnected(camera.id) ? styles.statusDotGreen : styles.statusDotRed}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* 第二行摄像头 */}
        <div className={`${styles.cameraRow} flex-row justify-between`}>
          {cameras.slice(2, 4).map((camera) => (
            <div
              key={camera.id}
              className={styles.cameraContainer}
            >
              {/* WebRTC 视频播放器 */}
              <div className={styles.videoWrapper}>
                {renderPlayer(camera)}
              </div>
              <div className={`${styles.cameraFooter} flex-row`}>
                <div className={`${styles.cameraInfo} flex-row justify-between`}>
                  <span className={styles.cameraName}>{camera.name}</span>
                  <div
                    className={isConnected(camera.id) ? styles.statusDotGreen : styles.statusDotRed}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </DetectionWebSocketProvider>
  );
}

export default MonitorGrid;
