import React from 'react';
import styles from './RealTimeAlarm.module.css';
import JoyAlarmCards from './JoyAlarmCards';
import lineDeco from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_top_mid.png';
import titleBarBg from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_bg_mid.png';
import titleIcon from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_arrow.png';
import cornerDeco from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_bottom_mid.png';

export default function RealTimeAlarm() {
  return <>
    <div className={styles.decorLine} style={{ backgroundImage: `url(${lineDeco})` }} />
    <div className={`${styles.titleBar} flex-row`} style={{ backgroundImage: `url(${titleBarBg})` }}>
      <div className={styles.titleIcon} style={{ backgroundImage: `url(${titleIcon})` }} />
      <span className={styles.titleText}>实时告警显示</span>
      <div className={styles.cornerDeco} style={{ backgroundImage: `url(${cornerDeco})` }} />
    </div>
    <div className={`${styles.contentContainer} flex-col`}><JoyAlarmCards /></div>
  </>;
}
