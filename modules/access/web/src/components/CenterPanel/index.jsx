import React from 'react';
import MonitorGrid from './components/MonitorGrid/MonitorGrid';
import RealTimeAlarm from './components/RealTimeAlarm/RealTimeAlarm';
import styles from './CenterPanel.module.css';

function CenterPanel() {
  return (
    <div className={`${styles.container} flex-col`}>
      <MonitorGrid />
      <RealTimeAlarm />
    </div>
  );
}

export default CenterPanel;

