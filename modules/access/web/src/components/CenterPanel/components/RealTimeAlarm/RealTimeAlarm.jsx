import React, { useEffect, useState, useRef, useMemo } from 'react';
import styles from './RealTimeAlarm.module.css';
import { useAlarmWebSocket } from '../../../../contexts/AlarmWebSocketContext';
import { normalizeImageSrc } from '../../../../utils/imageSrc';
import VideoModal from '../../../VideoModal/VideoModal';

// 导入图片资源
import lineDeco from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_top_mid.png';
import titleBarBg from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_bg_mid.png';
import titleIcon from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_arrow.png';
import cornerDeco from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_bottom_mid.png';


function RealTimeAlarm() {
  // 使用 WebSocket Hook 获取告警数据
  const { recentAlarms, isConnected } = useAlarmWebSocket();
  
  // 视频播放弹窗状态
  const [videoModal, setVideoModal] = useState({
    visible: false,
    url: '',
    title: '',
    time: ''
  });

  // 只显示最新的 5 条告警（按时间戳倒序，最新的在最前面/最左边）
  // 使用 useMemo 优化，避免每次渲染都重新计算
  // 排序时如果时间戳相同，使用 id 作为次要排序条件，确保排序稳定
  const displayAlarms = useMemo(() => {
    return recentAlarms
      .slice()  // 创建副本
      .sort((a, b) => {
        // 首先按时间戳倒序（最新的在前）
        const timeDiff = b.timestamp - a.timestamp;
        if (timeDiff !== 0) return timeDiff;
        // 如果时间戳相同，按 id 倒序（确保新告警在最前面）
        return (b.id || '').localeCompare(a.id || '');
      })
      .slice(0, 5);  // 只取前 5 条
  }, [recentAlarms]);

  // 调试日志
  useEffect(() => {
    console.log('🎯 [RealTimeAlarm] 显示告警数:', displayAlarms.length);
  }, [recentAlarms]);

  // 处理图片 URL（支持 base64 和普通 URL）
  const getImageUrl = (image) => {
    return normalizeImageSrc(image);
  };

  // 点击告警图片，播放回放视频
  const handleAlarmClick = (alarm) => {
    if (alarm.record_url) {
      console.log('🎬 [RealTimeAlarm] 播放回放视频:', alarm.record_url);
      setVideoModal({
        visible: true,
        url: alarm.record_url,
        title: alarm.title,
        time: alarm.time
      });
    } else {
      console.log('⚠️ [RealTimeAlarm] 该告警没有回放视频');
    }
  };

  // 关闭视频弹窗
  const closeVideoModal = () => {
    setVideoModal({
      visible: false,
      url: '',
      title: '',
      time: ''
    });
  };

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
        <span className={styles.titleText}>实时告警显示</span>
        <div 
          className={styles.cornerDeco}
          style={{ backgroundImage: `url(${cornerDeco})` }}
        />
      </div>
      
      {/* 告警列表 */}
      <div className={`${styles.contentContainer} flex-col justify-end`}>
        <div className={`${styles.alarmGrid} flex-row`}>
          <div className={`${styles.alarmList} flex-row`}>
            {displayAlarms.length > 0 ? (
              displayAlarms.map((alarm) => (
                <div 
                  key={alarm.id}
                  className={`${styles.alarmItem} ${alarm.record_url ? styles.clickable : ''} flex-col justify-end`}
                  style={{ 
                    backgroundImage: `url(${getImageUrl(alarm.image)})`,
                    backgroundSize: 'cover',
                    backgroundPosition: 'center'
                  }}
                  onClick={alarm.record_url ? () => handleAlarmClick(alarm) : undefined}
                  title={alarm.record_url ? '点击播放回放视频' : '录像不存在或已过期'}
                  aria-disabled={!alarm.record_url}
                >
                  {/* 标签 */}
                  <div 
                    className={`${styles.alarmLabel} flex-col`}
                    style={{ 
                      backgroundColor: alarm.type === 'alert' 
                        ? 'rgba(249, 71, 71, 1)'  // 红色 - 危险
                        : alarm.type === 'danger'
                        ? 'rgb(255, 132, 0)'  // 橙色 - 警告（打架）
                        : alarm.type === 'warning'
                        ? 'rgba(255, 218, 54, 0.66)' // 黄色 - 注意（摔倒）
                        : 'rgba(62, 161, 250, 1)' // 蓝色 - 提示
                    }}
                  >
                    <span className={styles.labelText}>{alarm.label}</span>
                  </div>
                  {/* 底部信息 */}
                  <div className={`${styles.alarmInfo} flex-col`}>
                    <div className={`${styles.alarmTextGroup} flex-col justify-between`}>
                      <span className={styles.alarmTitle}>{alarm.title}</span>
                      <span className={styles.alarmTime}>{alarm.time}</span>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div style={{ 
                width: '100%', 
                height: '180px', 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'center',
                color: 'rgba(255, 255, 255, 0.5)',
                fontSize: '16px'
              }}>
                {isConnected ? '暂无告警数据' : '正在连接...'}
              </div>
            )}
          </div>
        </div>
        
        {/* 右下角装饰点 */}
        <div className={`${styles.dotDecor} flex-row`}>
          <div className={styles.dot} />
        </div>
      </div>
      
      {/* 视频播放弹窗 */}
      <VideoModal
        visible={videoModal.visible}
        url={videoModal.url}
        title={videoModal.title}
        time={videoModal.time}
        onClose={closeVideoModal}
      />
    </>
  );
}

export default RealTimeAlarm;
