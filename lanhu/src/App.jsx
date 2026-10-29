import React, { useLayoutEffect, useRef } from 'react';
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
  const pageRef = useRef(null);
  useLayoutEffect(() => {
    // Keep the artwork's density uniform; columns and height still use fluid layout.
    const resize = () => {
      const scale = document.documentElement.clientWidth / 2752;
      const page = pageRef.current;
      page.style.setProperty('--dashboard-scale', scale);
      page.style.setProperty('--dashboard-width', `${document.documentElement.clientWidth / scale}px`);
      page.style.setProperty('--dashboard-height', `${window.innerHeight / scale}px`);
    };
    resize();
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);
  return (
    <AlarmWebSocketProvider>
      <PedestrianWebSocketProvider>
        <LLMReportWebSocketProvider>
        <div ref={pageRef} className="page flex-col">
          <div 
            className="container flex-col"
            style={{ backgroundImage: `url(${bgImage})` }}
          >
            <Header />
            <div className="content">
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
