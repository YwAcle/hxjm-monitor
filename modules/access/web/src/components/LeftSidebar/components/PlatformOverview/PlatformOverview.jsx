import React, { useEffect, useState } from 'react';
import styles from './PlatformOverview.module.css';
import { useAlarmWebSocket } from '../../../../contexts/AlarmWebSocketContext';
import { usePedestrianWebSocket } from '../../../../contexts/PedestrianWebSocketContext';

// 导入图片资源
import titleBarBg from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_bg_mid.png';
import titleIcon from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_arrow.png';
import lineDeco from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_bottom_mid.png';
import deviceIcon from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/platform_device.png';
import aiIcon from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/platform_ai.png';
import alertIcon from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/platform_anomaly.png';
import cornerDeco from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_bottom_mid.png';

function PlatformOverview() {
  // 获取告警 WebSocket 数据（用于异常检测次数）
  const { aiCount: alarmAiCount, anomaly } = useAlarmWebSocket();
  // 获取行人 WebSocket 数据（用于 AI 分析次数）
  const { aiCount: pedestrianAiCount } = usePedestrianWebSocket();
  
  // 使用告警 WebSocket 的 aiCount（因为告警推送中包含 ai_count）
  // 如果告警没有值，则使用行人的值作为备选
  const aiCount = alarmAiCount || pedestrianAiCount || 0;
  
  // 调试日志
  useEffect(() => {
    console.log('🔍 [PlatformOverview] AI分析次数:', {
      alarmAiCount,
      pedestrianAiCount,
      显示值: aiCount
    });
  }, [alarmAiCount, pedestrianAiCount, aiCount]);
  
  const [deviceCount, setDeviceCount] = useState(0);

  // 获取设备数量
  useEffect(() => {
    const fetchDeviceStats = async () => {
      try {
        const response = await fetch('/api/device/stats')
        if (response.ok) {
          const data = await response.json();
          if (data.code === 200 && data.data) {
            setDeviceCount(data.data.device_count || 0);
          }
        }
      } catch (error) {
        console.error('获取设备统计失败:', error);
      }
    };

    fetchDeviceStats();
    // 每5分钟更新一次
    const interval = setInterval(fetchDeviceStats, 5 * 60 * 1000);
    
    return () => clearInterval(interval);
  }, []);
  return (
    <>
      {/* 装饰线 */}
      <div 
        className={styles.decorLine}
        style={{ backgroundImage: `url(${lineDeco})` }}
      />
      
      {/* 标题栏 */}
      <div 
        className={`${styles.titleBar} flex-row`}
        style={{ backgroundImage: `url(${titleBarBg})` }}
      >
        <div 
          className={styles.titleIcon}
          style={{ backgroundImage: `url(${titleIcon})` }}
        />
        <span className={styles.titleText}>平台概览</span>
      </div>
      
      {/* 统计区域 */}
      <div className={`${styles.statsContainer} flex-col justify-end`}>
        <div className={`${styles.statsRow} flex-row`}>
          {/* 接入设备 */}
          <img className={styles.statIcon} src={deviceIcon} alt="" />
          <div className={`${styles.statInfo} flex-col justify-between`}>
            <span className={styles.statLabel}>接入设备</span>
            <div className={styles.statValueWrapper}>
              <span className={styles.statValue}>{deviceCount}&nbsp;</span>
              <span className={styles.statValueSpace}></span>
              <span className={styles.statUnit}>个</span>
            </div>
          </div>
          
          {/* AI分析 */}
          <img className={styles.statIconAi} src={aiIcon} alt="" />
          <div className={`${styles.statInfo} flex-col justify-between`}>
            <span className={styles.statLabel}>AI分析</span>
            <div className={styles.statValueWrapper}>
              <span className={styles.statValue}>{aiCount}&nbsp;</span>
              <span className={styles.statValueSpace}></span>
              <span className={styles.statUnit}>次</span>
            </div>
          </div>
          
          {/* 异常检测 */}
          <img className={styles.statIconAlert} src={alertIcon} alt="" />
          <div className={`${styles.statInfo} flex-col justify-between`}>
            <span className={styles.statLabel}>异常检测</span>
            <div className={styles.statValueWrapper}>
              <span className={styles.statValue}>{anomaly.total || 0}&nbsp;</span>
              <span className={styles.statValueSpace}></span>
              <span className={styles.statUnit}>次</span>
            </div>
          </div>
        </div>
        
        {/* 右下角装饰点 */}
        <div className={`${styles.dotDecor} flex-row`}>
          <div className={styles.dot} />
        </div>
        
        {/* 角落装饰 */}
        <div 
          className={styles.cornerDeco}
          style={{ backgroundImage: `url(${cornerDeco})` }}
        />
      </div>
    </>
  );
}

export default PlatformOverview;

