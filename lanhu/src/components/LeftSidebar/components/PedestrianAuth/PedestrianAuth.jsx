import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import styles from './PedestrianAuth.module.css';
import { usePedestrianWebSocket } from '../../../../contexts/PedestrianWebSocketContext';

// 导入图片资源
import lineDeco from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_top_mid.png';
import titleBarBg from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_bg_mid.png';
import titleIcon from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_arrow.png';
import cornerDeco from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_bottom_mid.png';
import centerDeco from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/small_header_bottom_center.png';
import arrowLeft from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/pedestrain_arrow_left.png';
import arrowRight from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/pedestrain_arrow_right.png';
import defaultAvatar from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/fad7918871ae4a85a2dbc705aee8f3a5_mergeImage.png';

// 将时间字符串转换为分钟数（从 00:00 开始）
const timeToMinutes = (timeStr) => {
  if (!timeStr) return 0;
  const [hours, minutes] = timeStr.split(':').map(Number);
  return hours * 60 + minutes;
};

// 将分钟数转换回时间字符串
const minutesToTime = (totalMinutes) => {
  // 处理跨天情况
  const normalizedMinutes = ((totalMinutes % (24 * 60)) + 24 * 60) % (24 * 60);
  const hours = Math.floor(normalizedMinutes / 60);
  const minutes = normalizedMinutes % 60;
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
};

// 获取时间段的结束时间（用于 tooltip 显示）
const getEndTime = (timeStr) => {
  const minutes = timeToMinutes(timeStr);
  return minutesToTime(minutes + 10);
};

function PedestrianAuth() {
  // 使用 WebSocket 数据
  const { flow, identities, isConnected } = usePedestrianWebSocket();
  
  // Hover 状态
  const [hoveredPoint, setHoveredPoint] = useState(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const svgRef = useRef(null);

  // 调试日志
  useEffect(() => {
    console.log('🎯 [PedestrianAuth] 身份列表更新:', identities.length, '条');
  }, [identities]);
  
  // 调试：监控 flow 数据变化
  useEffect(() => {
    const lastPoint = flow.data_points?.[flow.data_points.length - 1];
    console.log('📈 [PedestrianAuth] 人流数据更新:', {
      点数: flow.data_points?.length,
      今日: flow.total_today,
      最后一个点: lastPoint ? `${lastPoint.time} (${lastPoint.count}人)` : '无'
    });
  }, [flow.data_points, flow.total_today]);

  // 按姓名去重，每个人只保留最新的一条记录，且最新的在最前面
  const displayIdentities = useMemo(() => {
    // 使用 Map，key 为姓名，value 为身份信息对象
    const nameMap = new Map();
    
    // 遍历所有身份信息，按时间戳倒序处理（最新的先处理）
    const sortedIdentities = identities
      .slice()
      .sort((a, b) => b.timestamp - a.timestamp);
    
    // 对于每个身份信息，如果姓名已存在，则用新的替换旧的（因为已按时间倒序，新的在前面）
    sortedIdentities.forEach(identity => {
      const name = identity.name;
      if (name) {
        // 如果姓名已存在，删除旧的，添加新的（这样最新的会在最前面）
        nameMap.delete(name);
        nameMap.set(name, identity);
      }
    });
    
    // 将 Map 转换为数组，按插入顺序（即时间倒序，最新的在最前面）
    const uniqueIdentities = Array.from(nameMap.values());
    
    // 限制最多显示 20 条
    return uniqueIdentities.slice(0, 20);
  }, [identities]);

  // 处理头像 URL
  const getAvatarUrl = (avatar) => {
    if (!avatar) return defaultAvatar;
    
    if (avatar.startsWith('data:image')) {
      // 修复格式：把 ;base64: 替换成 ;base64,
      return avatar.replace(';base64:', ';base64,');
    }
    
    if (!avatar.startsWith('http') && !avatar.startsWith('/')) {
      return `data:image/jpeg;base64,${avatar}`;
    }
    
    return avatar;
  };

  // 图表参数
  const chartWidth = 598;
  const chartHeight = 140;
  const padding = { left: 35, right: 15, top: 10, bottom: 35 };
  const graphWidth = chartWidth - padding.left - padding.right;
  const graphHeight = chartHeight - padding.top - padding.bottom;
  const maxValue = 50;

  // 处理跨天数据：检测是否有跨午夜的数据
  // 如果同时存在凌晨数据(00:00-06:00)和晚间数据(18:00-23:59)，将凌晨数据视为次日
  const processedFlowData = useMemo(() => {
    if (!flow.data_points || flow.data_points.length === 0) {
      return [];
    }
    
    const points = flow.data_points.map(p => ({
      time: p.time,
      minutes: timeToMinutes(p.time),
      value: p.count || 0
    }));
    
    // 检测是否跨天：同时有凌晨(0-6点)和晚间(18-24点)的数据
    const hasEarlyMorning = points.some(p => p.minutes < 6 * 60);
    const hasLateNight = points.some(p => p.minutes >= 18 * 60);
    const isCrossDay = hasEarlyMorning && hasLateNight;
    
    return points.map(p => {
      // 如果是跨天数据，将凌晨时间加24小时（当作次日显示）
      const adjustedMinutes = (isCrossDay && p.minutes < 6 * 60) 
        ? p.minutes + 24 * 60 
        : p.minutes;
      
      return {
        time: p.time,
        endTime: getEndTime(p.time),
        minutes: adjustedMinutes,
        value: p.value
      };
    });
  }, [flow.data_points]);

  // 计算时间范围（用于确定 X 轴范围）
  // 始终显示 8 小时的窗口，不足8小时从0开始，超过就向右平移
  const timeRange = useMemo(() => {
    const WINDOW_HOURS = 8; // 固定显示 8 小时
    const WINDOW_MINUTES = WINDOW_HOURS * 60;
    
    if (processedFlowData.length === 0) {
      // 默认显示 00:00 - 08:00
      return { startMinutes: 0, endMinutes: WINDOW_MINUTES };
    }
    
    const times = processedFlowData.map(d => d.minutes);
    const maxTime = Math.max(...times);
    
    // 结束时间向上取整到小时
    const endHour = Math.ceil((maxTime + 1) / 60);
    let endMinutes = endHour * 60;
    
    // 确保至少显示 8 小时
    if (endMinutes < WINDOW_MINUTES) {
      endMinutes = WINDOW_MINUTES;
    }
    
    // 起始时间 = 结束时间 - 8小时
    const startMinutes = endMinutes - WINDOW_MINUTES;
    
    console.log('📊 [Chart] 时间范围:', {
      maxTime,
      startMinutes,
      endMinutes,
      显示: `${Math.floor(startMinutes/60)}:00 - ${Math.floor(endMinutes/60)}:00`
    });
    
    return {
      startMinutes,
      endMinutes
    };
  }, [processedFlowData]);

  // 生成整点刻度标签
  const hourLabels = useMemo(() => {
    const labels = [];
    const startHour = Math.floor(timeRange.startMinutes / 60);
    const endHour = Math.floor(timeRange.endMinutes / 60);
    
    for (let h = startHour; h <= endHour; h++) {
      // 处理超过24小时的情况（跨天）
      const displayHour = h >= 24 ? h - 24 : h;
      const labelMinutes = h * 60; // 保留原始分钟数用于定位
      labels.push({
        text: `${String(displayHour).padStart(2, '0')}:00`,
        minutes: labelMinutes
      });
    }
    return labels;
  }, [timeRange]);

  // 根据分钟数计算 X 坐标
  const getXFromMinutes = useCallback((minutes) => {
    const totalMinutes = timeRange.endMinutes - timeRange.startMinutes;
    if (totalMinutes === 0) return padding.left;
    const ratio = (minutes - timeRange.startMinutes) / totalMinutes;
    return padding.left + ratio * graphWidth;
  }, [timeRange, graphWidth, padding.left]);

  // 计算所有数据点的坐标（只显示时间窗口内的数据）
  const dataPoints = useMemo(() => {
    // 只保留在时间窗口范围内的数据点
    const filteredData = processedFlowData.filter(item => {
      return item.minutes >= timeRange.startMinutes && item.minutes <= timeRange.endMinutes;
    });
    
    return filteredData.map(item => ({
      x: getXFromMinutes(item.minutes),
      y: padding.top + graphHeight - (Math.min(item.value, maxValue) / maxValue) * graphHeight,
      time: item.time,           // 时间段开始点（如 23:30）
      endTime: item.endTime,     // 时间段结束点（如 23:40）
      value: item.value
    }));
  }, [processedFlowData, timeRange, getXFromMinutes, graphHeight, padding.top, maxValue]);

  // 生成贝塞尔曲线平滑路径
  const generateSmoothPath = useCallback(() => {
    if (dataPoints.length === 0) return '';
    if (dataPoints.length === 1) return `M ${dataPoints[0].x} ${dataPoints[0].y}`;

    const tension = 0.3;
    let path = `M ${dataPoints[0].x} ${dataPoints[0].y}`;
    
    for (let i = 0; i < dataPoints.length - 1; i++) {
      const p0 = dataPoints[i === 0 ? 0 : i - 1];
      const p1 = dataPoints[i];
      const p2 = dataPoints[i + 1];
      const p3 = dataPoints[i + 2 >= dataPoints.length ? dataPoints.length - 1 : i + 2];
      
      const cp1x = p1.x + (p2.x - p0.x) * tension;
      const cp1y = p1.y + (p2.y - p0.y) * tension;
      const cp2x = p2.x - (p3.x - p1.x) * tension;
      const cp2y = p2.y - (p3.y - p1.y) * tension;
      
      path += ` C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${p2.x} ${p2.y}`;
    }
    
    return path;
  }, [dataPoints]);

  // 生成填充区域路径
  const generateAreaPath = useCallback(() => {
    if (dataPoints.length === 0) return '';
    
    const linePath = generateSmoothPath();
    const firstX = dataPoints[0].x;
    const lastX = dataPoints[dataPoints.length - 1].x;
    const bottomY = padding.top + graphHeight;
    
    return `${linePath} L ${lastX} ${bottomY} L ${firstX} ${bottomY} Z`;
  }, [dataPoints, generateSmoothPath, graphHeight, padding.top]);

  // 处理鼠标移动，找到最近的数据点
  const handleMouseMove = useCallback((e) => {
    if (dataPoints.length === 0 || !svgRef.current) return;
    
    const svgRect = svgRef.current.getBoundingClientRect();
    const mouseX = e.clientX - svgRect.left;
    const mouseY = e.clientY - svgRect.top;
    
    // 检查是否在图表区域内
    if (mouseX < padding.left || mouseX > chartWidth - padding.right ||
        mouseY < padding.top || mouseY > padding.top + graphHeight) {
      setHoveredPoint(null);
      return;
    }
    
    // 找到最近的数据点
    let closestPoint = null;
    let minDistance = Infinity;
    
    dataPoints.forEach(point => {
      const distance = Math.abs(point.x - mouseX);
      if (distance < minDistance) {
        minDistance = distance;
        closestPoint = point;
      }
    });
    
    // 只有在距离足够近时才显示（50px 范围内）
    if (closestPoint && minDistance < 50) {
      setHoveredPoint(closestPoint);
      setTooltipPos({ x: closestPoint.x, y: closestPoint.y });
    } else {
      setHoveredPoint(null);
    }
  }, [dataPoints, chartWidth, graphHeight, padding]);

  const handleMouseLeave = useCallback(() => {
    setHoveredPoint(null);
  }, []);

  // Y轴刻度
  const yTicks = [50, 40, 30, 20, 10, 0];

  // 将数据分成两列显示
  const leftColumnData = displayIdentities.filter((_, i) => i % 2 === 0);
  const rightColumnData = displayIdentities.filter((_, i) => i % 2 === 1);

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
        <span className={styles.titleText}>行人身份认证</span>
        {/* 角落装饰和今日人流量 */}
        <div 
          className={`${styles.cornerDeco} flex-row`}
          style={{ backgroundImage: `url(${cornerDeco})` }}
        >
          <span className={styles.flowLabel}>今日总人流量</span>
          <div className={styles.flowValueWrapper}>
            <span className={styles.flowValue}>{flow.total_today || displayIdentities.length}</span>
            <span className={styles.flowUnit}>&nbsp;人</span>
          </div>
        </div>
      </div>
      
      {/* 内容区域 */}
      <div className={`${styles.contentContainer} flex-col`}>
        {/* 图表标题 - 带左右箭头 */}
        <div className={`${styles.chartTitleRow} flex-row justify-between`}>
          <div 
            className={styles.chartArrowLeft}
            style={{ backgroundImage: `url(${arrowLeft})` }}
          />
          <span className={styles.chartTitle}>今日人流量</span>
          <div 
            className={styles.chartArrowRight}
            style={{ backgroundImage: `url(${arrowRight})` }}
          />
        </div>
        <div 
          className={`${styles.centerDeco1} flex-row`}
          style={{ backgroundImage: `url(${centerDeco})` }}
        >
        </div>

        {/* SVG 图表 */}
        <div className={styles.chartWrapper}>
          <svg 
            ref={svgRef}
            width={chartWidth} 
            height={chartHeight} 
            viewBox={`0 0 ${chartWidth} ${chartHeight}`}
            className={styles.chart}
            onMouseMove={handleMouseMove}
            onMouseLeave={handleMouseLeave}
          >
            {/* 定义渐变 */}
            <defs>
              <linearGradient id="areaGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="rgba(65, 177, 255, 0.4)" />
                <stop offset="100%" stopColor="rgba(65, 177, 255, 0)" />
              </linearGradient>
              {/* 发光效果 */}
              <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
                <feMerge>
                  <feMergeNode in="coloredBlur"/>
                  <feMergeNode in="SourceGraphic"/>
                </feMerge>
              </filter>
            </defs>

            {/* Y轴网格线 */}
            {yTicks.map((tick, index) => {
              const y = padding.top + (index / (yTicks.length - 1)) * graphHeight;
              return (
                <g key={tick}>
                  <line
                    x1={padding.left}
                    y1={y}
                    x2={chartWidth - padding.right}
                    y2={y}
                    stroke="rgba(255, 255, 255, 0.1)"
                    strokeWidth="1"
                  />
                  <text
                    x={padding.left - 8}
                    y={y + 4}
                    fill="rgba(255, 255, 255, 0.7)"
                    fontSize="12"
                    textAnchor="end"
                  >
                    {tick}
                  </text>
                </g>
              );
            })}

            {/* 填充区域 */}
            <path
              d={generateAreaPath()}
              fill="url(#areaGradient)"
            />

            {/* 曲线 */}
            <path
              d={generateSmoothPath()}
              fill="none"
              stroke="#41B1FF"
              strokeWidth="2"
            />

            {/* X轴标签 - 只显示整点，位置根据实际时间计算 */}
            {hourLabels.map((label, index) => {
              const x = getXFromMinutes(label.minutes);
              return (
                <text
                  key={index}
                  x={x}
                  y={chartHeight - 5}
                  fill="rgba(255, 255, 255, 0.8)"
                  fontSize="11"
                  textAnchor="middle"
                >
                  {label.text}
                </text>
              );
            })}

            {/* Hover 时显示的垂直参考线 */}
            {hoveredPoint && (
              <line
                x1={hoveredPoint.x}
                y1={padding.top}
                x2={hoveredPoint.x}
                y2={padding.top + graphHeight}
                stroke="rgba(65, 177, 255, 0.5)"
                strokeWidth="1"
                strokeDasharray="4 2"
              />
            )}

            {/* Hover 时显示的数据点 */}
            {hoveredPoint && (
              <g filter="url(#glow)">
                <circle
                  cx={hoveredPoint.x}
                  cy={hoveredPoint.y}
                  r="6"
                  fill="#41B1FF"
                  stroke="#fff"
                  strokeWidth="2"
                />
              </g>
            )}
          </svg>
          
          {/* Tooltip 浮层 */}
          {hoveredPoint && (
            <div 
              className={styles.chartTooltip}
              style={{
                left: tooltipPos.x,
                top: tooltipPos.y - 80
              }}
            >
              <div className={styles.tooltipTime}>
                {hoveredPoint.time} ~ {hoveredPoint.endTime}
              </div>
              <div className={styles.tooltipValue}>{hoveredPoint.value} 人</div>
            </div>
          )}
        </div>
        
        {/* 行人身份信息标题 */}
        <div className={`${styles.infoTitleRow} flex-row justify-between`}>
          <div 
            className={styles.arrowLeft}
            style={{ backgroundImage: `url(${arrowLeft})` }}
          />
          <span className={styles.infoTitle}>行人身份信息</span>
          <div 
            className={styles.arrowRight}
            style={{ backgroundImage: `url(${arrowRight})` }}
          />
        </div>
        <div 
          className={`${styles.centerDeco2} flex-row`}
          style={{ backgroundImage: `url(${centerDeco})` }}
        >
        </div>
        
        {/* 人员列表 - 可滚动区域，两列布局 */}
        <div className={styles.personListWrapper}>
          {displayIdentities.length > 0 ? (
            <div className={styles.personListContainer}>
              {/* 左列 */}
              <div className={styles.personColumn}>
                {leftColumnData.map((person) => (
                  <div key={person.id} className={styles.personCard}>
                    <div 
                      className={styles.avatar}
                      style={{ backgroundImage: `url(${getAvatarUrl(person.avatar)})` }}
                    />
                    <div className={styles.personInfo}>
                      <span className={styles.personName}>{person.name}</span>
                      <span className={styles.personDetail}>{person.identity}</span>
                      <span className={styles.personTime}>{person.detected_time}</span>
                    </div>
                  </div>
                ))}
              </div>
              {/* 右列 */}
              <div className={styles.personColumn}>
                {rightColumnData.map((person) => (
                  <div key={person.id} className={styles.personCard}>
                    <div 
                      className={styles.avatar}
                      style={{ backgroundImage: `url(${getAvatarUrl(person.avatar)})` }}
                    />
                    <div className={styles.personInfo}>
                      <span className={styles.personName}>{person.name}</span>
                      <span className={styles.personDetail}>{person.identity}</span>
                      <span className={styles.personTime}>{person.detected_time}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div style={{ 
              width: '100%', 
              height: '100%', 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center',
              color: 'rgba(255, 255, 255, 0.5)',
              fontSize: '16px'
            }}>
              {isConnected ? '暂无身份数据' : '正在连接...'}
            </div>
          )}
        </div>
        
        {/* 右下角装饰点 */}
        <div className={`${styles.dotDecor} flex-row`}>
          <div className={styles.dot} />
        </div>
      </div>
    </>
  );
}

export default PedestrianAuth;
