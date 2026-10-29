import React, { useState } from 'react';
import styles from './MonitorGrid.module.css';
import WebRTCPlayer from './WebRTCPlayer/index.jsx';
import VideoWithOverlay from '../../../VideoWithOverlay/index.jsx';
import { DetectionWebSocketProvider } from '../../../../contexts/DetectionWebSocketContext.jsx';
import { videoMediaBase } from '../../../../config/videoDeployment.js';

function MonitorGrid() {
  // 视频流地址
  const mediaBaseUrl = videoMediaBase(import.meta.env, window.location);
  const algorithmsEnabled = import.meta.env.VITE_VIDEO_ANALYSIS_MODE === 'local'
    && import.meta.env.VITE_ENABLE_DEEPSORT !== 'false';
  const analysisEnabled = import.meta.env.VITE_VIDEO_ANALYSIS_ENABLED !== 'false';
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
        onStatusChange={onStatusChange} />;
    }
    return <WebRTCPlayer primaryUrl={camera.primaryUrl} fallbackUrl={camera.fallbackUrl} onStatusChange={onStatusChange} />;
  };

  return (
    <DetectionWebSocketProvider enabled={analysisEnabled}>
      <div className={styles.gridContainer}>
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
