import React, { useMemo } from 'react';
import styles from './AnomalyStats.module.css';
import { useAlarmWebSocket } from '../../../../contexts/AlarmWebSocketContext';

// 导入图片资源
import sectionBg from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_bg_samll.png';
import lineDeco from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_bottom_small.png';
import titleIcon from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_arrow.png';
import cornerDeco from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_top_small.png';
import chartBg from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/椭圆形.png';

function AnomalyStats() {
  // 获取告警 WebSocket 数据
  const { anomaly } = useAlarmWebSocket();

  // 事件类型配置（从上到下：火灾/打架/摔倒/陌生人）
  // 颜色交换：陌生人和火灾交换，摔倒和打架交换
  const eventTypeConfig = {
    fire: { key: 'fire', label: '火灾', color: '#E74C3C' },        
    fight: { key: 'fight', label: '打架', color: '#F5A623' },     
    fall: { key: 'fall', label: '摔倒', color: '#3EA1FA' },        
    stranger: { key: 'stranger', label: '陌生人', color: '#00D4FF' }, 
  };

  // 将 WebSocket 数据转换为图表数据格式
  const data = useMemo(() => {
    if (!anomaly || !anomaly.items || anomaly.items.length === 0) {
      // 返回默认空数据
      return Object.values(eventTypeConfig).map(config => ({
        ...config,
        value: 0
      }));
    }

    // 按配置的顺序映射数据
    return Object.values(eventTypeConfig).map(config => {
      const item = anomaly.items.find(i => i.type === config.key);
      return {
        ...config,
        value: item ? item.count : 0
      };
    });
  }, [anomaly]);

  // 计算总数（使用 WebSocket 数据中的 total，如果没有则从 data 计算）
  const total = anomaly?.total || data.reduce((sum, item) => sum + item.value, 0);

  // 圆环图参数 - 173px 大小
  const radius = 60;
  const strokeWidth = 10;
  const circumference = 2 * Math.PI * radius; // 约376.99
  const gap = 4; // 每段之间的间隙
  const totalGap = gap * data.length; // 总间隙
  const availableLength = circumference - totalGap; // 可用于绘制的长度

  // 计算每段的长度和偏移量
  const segments = data.map((item, index) => {
    // 按比例计算该段长度
    const segmentLength = (item.value / total) * availableLength;
    
    // 计算偏移量：前面所有段的长度 + 间隙
    let offset = 0;
    for (let i = 0; i < index; i++) {
      const prevLength = (data[i].value / total) * availableLength;
      offset += prevLength + gap;
    }
    
    return {
      ...item,
      length: segmentLength,
      offset: -offset,
      dasharray: `${segmentLength} ${circumference - segmentLength}`
    };
  });

  return (
    <div className={`${styles.container} flex-col`}>
      {/* 标题区域 */}
      <div 
        className={`${styles.headerSection} flex-col`}
        style={{ backgroundImage: `url(${sectionBg})` }}
      >
        <div 
          className={styles.decorLine}
          style={{ backgroundImage: `url(${lineDeco})` }}
        />
        <div className={`${styles.titleRow} flex-row justify-between`}>
          <div 
            className={styles.titleIcon}
            style={{ backgroundImage: `url(${titleIcon})` }}
          />
          <span className={styles.titleText}>异常事件统计</span>
        </div>
        {/* 角落装饰 */}
        <div 
          className={styles.cornerDeco}
          style={{ backgroundImage: `url(${cornerDeco})` }}
        />
      </div>

      {/* 内容区域 */}
      <div className={styles.contentContainer}>
        {/* 左侧甜甜圈图 - 173px x 173px */}
        <div 
          className={styles.chartContainer}
          style={{ backgroundImage: `url(${chartBg})` }}
        >
          <svg className={styles.donutChart} viewBox="0 0 160 160">
            {segments.map((segment, index) => (
              <circle
                key={segment.key}
                cx="80"
                cy="80"
                r={radius}
                fill="none"
                stroke={segment.color}
                strokeWidth={strokeWidth}
                strokeDasharray={segment.dasharray}
                strokeDashoffset={segment.offset}
              />
            ))}
          </svg>
          {/* 中心文字 */}
          <div className={styles.chartCenter}>
            <div className={styles.chartValue}>{total}</div>
            <div className={styles.chartLabel}>异常次数</div>
          </div>
        </div>

        {/* 右侧图例 */}
        <div className={styles.legendContainer}>
          {data.map((item) => (
            <div key={item.key} className={styles.statItem}>
              <div className="flex-row align-center" style={{ flex: 1 }}>
                <div 
                  className={styles.statDot} 
                  style={{ backgroundColor: item.color }}
                />
                <span className={styles.statLabel}>{item.label}</span>
              </div>
              <span className={styles.statValue}>{item.value}</span>
            </div>
          ))}
        </div>
        
        {/* 右下角装饰点 */}
        <div className={styles.bottomDot} />
      </div>
    </div>
  );
}

export default AnomalyStats;
