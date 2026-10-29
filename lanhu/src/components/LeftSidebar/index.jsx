import React from 'react';
import PlatformOverview from './components/PlatformOverview/PlatformOverview';
import ModelAccess from './components/ModelAccess/ModelAccess';
import AnomalyStats from './components/AnomalyStats/AnomalyStats';
import PedestrianAuth from './components/PedestrianAuth/PedestrianAuth';
import styles from './LeftSidebar.module.css';

function LeftSidebar() {
  return (
    <div className={`${styles.container} flex-col`}>
      {/* 平台概览 */}
      <PlatformOverview />
      
      {/* 接入小模型 + 异常事件统计 */}
      <div className={`${styles.middleSection} flex-row justify-between`}>
        <ModelAccess />
        <AnomalyStats />
      </div>
      
      {/* 行人身份认证 */}
      <PedestrianAuth />
    </div>
  );
}

export default LeftSidebar;
