import React from 'react';
import GarbageCleanup from './pages/GarbageCleanup';
import Header from './components/Header/Header';
import LeftSidebar from './components/LeftSidebar';
import CenterPanel from './components/CenterPanel';
import RightSidebar from './components/RightSidebar';
import { AlarmWebSocketProvider } from './contexts/AlarmWebSocketContext';
import { PedestrianWebSocketProvider } from './contexts/PedestrianWebSocketContext';
import { LLMReportWebSocketProvider } from './contexts/LLMReportWebSocketContext';
import './App.css';

// 导入背景图片
import bgImage from './view/lanhu_shipinjiankonguisheji1230/assets/img/SketchPnge2486eab041bdf49e148a671e595a136df1f286c3210c3e1e42c15d79712325b.png';

function App() {
  if (window.location.pathname === "/garbage-cleanup") return <GarbageCleanup />;
  return (
    <AlarmWebSocketProvider>
      <PedestrianWebSocketProvider>
        <LLMReportWebSocketProvider>
        <div className="page flex-col">
          <div 
            className="container flex-col"
            style={{ backgroundImage: `url(${bgImage})` }}
          >
            <Header />
            <a href="/garbage-cleanup" style={{position:"absolute", top:24, left:24, zIndex:10, color:"white"}}>垃圾检测与清理</a>
            <div className="content flex-row justify-between">
              <LeftSidebar />
              <CenterPanel />
              <RightSidebar />
            </div>
          </div>
        </div>
        </LLMReportWebSocketProvider>
      </PedestrianWebSocketProvider>
    </AlarmWebSocketProvider>
  );
}

export default App;
