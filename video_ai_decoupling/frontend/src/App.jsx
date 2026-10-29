import React from 'react';
import VideoWithOverlay from './VideoWithOverlay.jsx';

const originalVideoUrl = (import.meta.env.VITE_ORIGINAL_VIDEO_URL || '').trim();
const detectionsWebsocketUrl = (import.meta.env.VITE_DETECTIONS_WS_URL || '').trim();

export default function App() {
  return (
    <main className="app">
      <header className="page-header">
        <div className="page-heading">
          <h1>视频与 AI 结果分离演示</h1>
          <p>原始视频独立播放 · AI 检测结果实时叠加</p>
        </div>
        <div className="flow-diagram" aria-label="两条链路的静态说明">
          <div className="flow-path">
            <span className="flow-label">视频链路</span>
            <span>原始视频</span>
            <span className="flow-arrow" aria-hidden="true">→</span>
            <span className="flow-destination">独立播放</span>
          </div>
          <div className="flow-path">
            <span className="flow-label">检测链路</span>
            <span>AI 分析</span>
            <span className="flow-arrow" aria-hidden="true">→</span>
            <span>结果推送</span>
            <span className="flow-arrow" aria-hidden="true">→</span>
            <span className="flow-destination">前端标注</span>
          </div>
        </div>
      </header>
      <VideoWithOverlay
        originalVideoUrl={originalVideoUrl}
        detectionsWebsocketUrl={detectionsWebsocketUrl}
      />
    </main>
  );
}
