import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import { normalizeImageSrc } from '../utils/imageSrc';
import {
  pruneExpiredAlarms,
  resolveAlarmTiming,
} from './alarmExpiryPolicy';

// 创建 Context
const AlarmWebSocketContext = createContext(null);

// 事件类型到中文名称的映射
const eventTypeMap = {
  fight: '打架监测',
  fire: '烟雾/火灾',
  fall: '摔倒监测',
  stranger: '陌生人预警'
};

// 根据事件类型获取告警等级和标签
// 摔倒(fall) → "注意"（黄色）
// 打架(fight) → "警告"（橙色）
// 火灾(fire) → "危险"（红色）
const getAlarmTypeAndLabel = (eventTypeKey) => {
  switch (eventTypeKey) {
    case 'fire':
      return { type: 'alert', label: '危险' };  // 红色
    case 'fall':
      return { type: 'warning', label: '注意' };  // 黄色
    case 'fight':
      return { type: 'danger', label: '警告' };  // 橙色
    default:
      return { type: 'info', label: '提示' };  // 蓝色
  }
};

// 格式化告警数据
const formatAlarm = (alarm, timestamp = null, timingOptions = {}) => {
  const thumbnail = normalizeImageSrc(alarm.thumbnail); // 修base64图片

  const timeStr = alarm.timestamp || '';
  const timing = resolveAlarmTiming(alarm, timingOptions);  // 计算“发生时间 + 过期时间”
  const now = timingOptions.now ?? Date.now();
  if (!timing || timing.expiresAt <= now) return null; // 已过期，直接丢弃
  
  // 根据事件类型获取告警等级和标签
  const { type, label } = getAlarmTypeAndLabel(alarm.event_type_key);
  
  return {
    id: alarm.id,
    type,
    label,
    title: eventTypeMap[alarm.event_type_key] || alarm.event_type_key,
    time: timeStr,
    timestamp: timestamp ?? timing.occurredAt,  // 用于排序的时间戳
    expiresAt: timing.expiresAt,
    image: thumbnail,
    camera_id: alarm.camera_id,
    record_url: alarm.record_url
  };
};

/**
 * 告警 WebSocket Provider
 */
export function AlarmWebSocketProvider({ children }) {
  const [aiCount, setAiCount] = useState(0); // AI分析次数
  const [anomaly, setAnomaly] = useState({ total: 0, items: [] }); //异常统计
  const [recentAlarms, setRecentAlarms] = useState([]); //最近告警列表
  const [isConnected, setIsConnected] = useState(false); //是否连接
  
  const wsRef = useRef(null);  //存webSocket连接对象
  const heartbeatRef = useRef(null); // 存心跳定时器
  const reconnectTimeoutRef = useRef(null);  // 存重连定时器
  const reconnectAttempts = useRef(0); //重连次数计数
  
  // 使用 ref 存储最新的 setter 函数，避免闭包问题
  const settersRef = useRef({
    setAiCount,
    setAnomaly,
    setRecentAlarms,
    setIsConnected
  });
  
  // 每次渲染时更新 ref
  useEffect(() => {
    settersRef.current = {
      setAiCount,
      setAnomaly,
      setRecentAlarms,
      setIsConnected
    };
  });

  // 处理 WebSocket 消息
  const handleMessage = useCallback((event) => {
    try {
      const msg = JSON.parse(event.data); // 把收到的字符串转成json对象
      console.log('📨 [AlarmWS] 收到消息:', msg.type);

      const { setAiCount, setAnomaly, setRecentAlarms } = settersRef.current;

      switch (msg.type) { //按消息类型分别处理
        case 'init': // 首次连接，全量初始化 AI分析次数  异常统计   最近告警信息
          if (msg.data) {
            console.log('📋 [AlarmWS] 处理 init 数据');
            setAiCount(msg.data.ai_count || 0); // AI分析次数
            setAnomaly(msg.data.anomaly || { total: 0, items: [] });  // 异常统计
            
            // 格式化告警数据
            const now = Date.now();
            let formattedAlarms = (msg.data.recent_alarms || []) // 最近告警数组
              .map(alarm => formatAlarm(alarm, null, { now })) //丢弃过期告警信息
              .filter(Boolean);
            
            // 按时间戳排序（最新的在前）并只保留 5 条
            // 如果时间戳相同，使用 id 作为次要排序条件，确保排序稳定
            formattedAlarms = formattedAlarms
              .sort((a, b) => {
                const timeDiff = b.timestamp - a.timestamp;
                if (timeDiff !== 0) return timeDiff;
                return (b.id || '').localeCompare(a.id || '');
              })
              .slice(0, 5);
            
            setRecentAlarms(formattedAlarms);
            console.log('📋 [AlarmWS] 初始化完成，告警数:', formattedAlarms.length);
          }
          break;

        case 'new_alarm': // 实时推送的新告警
          if (msg.data) {
            console.log('🚨 [AlarmWS] 收到新告警!');
            
            // 更新 AI分析次数和异常统计
            if (msg.data.ai_count !== undefined) {
              console.log('📊 [AlarmWS] 更新 AI 分析次数:', msg.data.ai_count);
              setAiCount(msg.data.ai_count);
            }

            if (msg.data.anomaly_update) {
              console.log('📈 [AlarmWS] 更新异常统计:', msg.data.anomaly_update);
              setAnomaly(prev => {
                const newItems = prev.items.map(item =>
                  item.type === msg.data.anomaly_update.type
                    ? { ...item, count: msg.data.anomaly_update.count }
                    : item
                );
                
                const exists = newItems.some(item => item.type === msg.data.anomaly_update.type);
                if (!exists && msg.data.anomaly_update.type) {
                  newItems.push({
                    type: msg.data.anomaly_update.type,
                    count: msg.data.anomaly_update.count
                  });
                }

                const updated = {
                  total: msg.data.anomaly_update.total,
                  items: newItems
                };
                console.log('📈 [AlarmWS] 异常统计已更新:', updated);
                return updated;
              });
            }

            // 适配实际后端格式：可能是 msg.data.alarm 或直接是 msg.data
            const alarmData = msg.data.alarm || msg.data;
            
            // 只要有 thumbnail 就认为是有效的告警数据
            if (alarmData && (alarmData.thumbnail || alarmData.id)) {
              // 使用当前时间戳（毫秒）作为排序依据
              const nowTimestamp = Date.now();
              const uniqueId = alarmData.id || `alarm_${nowTimestamp}_${Math.random().toString(36).substr(2, 9)}`;
              
              // 生成时间字符串
              const now = new Date(nowTimestamp);
              const timeStr = alarmData.timestamp || 
                `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ` +
                `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`;
              
              // 构建完整的告警对象
              const completeAlarmData = {
                id: uniqueId,
                alarm_level: alarmData.alarm_level || 'warning',
                event_type_key: alarmData.event_type_key || 'fight',
                camera_id: alarmData.camera_id || '',
                thumbnail: alarmData.thumbnail || '',
                record_url: alarmData.record_url || '',
                timestamp: timeStr,
                expires_at: alarmData.expires_at
              };
              
              setRecentAlarms(prev => {
                // 确保新告警的时间戳总是最大的（比现有告警的最大时间戳大）
                // 这样可以保证新告警始终排在最前面
                const maxTimestamp = prev.length > 0 
                  ? Math.max(...prev.map(a => a.timestamp))
                  : 0;
                const newTimestamp = Math.max(nowTimestamp, maxTimestamp + 1);
                
                const formattedAlarm = formatAlarm(
                  completeAlarmData,
                  newTimestamp,
                  { now: nowTimestamp, allowReceivedAtFallback: true },
                );
                if (!formattedAlarm) return prev;
                console.log('🚨 [AlarmWS] 新告警:', formattedAlarm.time, 'timestamp:', formattedAlarm.timestamp);
                
                // 添加新告警，按时间戳排序（最新的在前），只保留 5 条
                // 如果时间戳相同，使用 id 作为次要排序条件，确保排序稳定
                const newAlarms = [formattedAlarm, ...prev]
                  .sort((a, b) => {
                    const timeDiff = b.timestamp - a.timestamp;
                    if (timeDiff !== 0) return timeDiff;
                    return (b.id || '').localeCompare(a.id || '');
                  })
                  .slice(0, 5);
                console.log('🚨 [AlarmWS] 告警列表已更新，当前数量:', newAlarms.length);
                console.log('🚨 [AlarmWS] 告警顺序:', newAlarms.map(a => ({ id: a.id, time: a.time, timestamp: a.timestamp })));
                return newAlarms;
              });
            }
          }
          break;

        case 'pong':
          break;

        case 'error':
          console.error('❌ [AlarmWS] 服务器错误:', msg.message || msg);
          break;

        default:
          console.warn('⚠️ [AlarmWS] 未知消息类型:', msg.type);
      }
    } catch (error) {
      console.error('[AlarmWS] 解析消息失败:', error);
    }
  }, []);

  // 连接函数
  const connect = useCallback(() => {
    // 如果已经有连接，先关闭
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      wsRef.current.close();
      wsRef.current = null;
    }

    // 建立连接 + 选择协议
    console.log('🔌 [AlarmWS] 正在连接...');
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // 建立连接
    const ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws/alarm`);  // ws/alarm 靠vite.config.js 里的代理 
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('✅ [AlarmWS] 已连接');
      settersRef.current.setIsConnected(true);
      reconnectAttempts.current = 0;
      
      // 启动心跳
      if (heartbeatRef.current) {
        clearInterval(heartbeatRef.current);
      }
      heartbeatRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 30000);
    };

    ws.onmessage = handleMessage;

    ws.onclose = (event) => {
      console.log('❌ [AlarmWS] 断开连接', event.code);
      settersRef.current.setIsConnected(false);
      
      if (heartbeatRef.current) {
        clearInterval(heartbeatRef.current);
        heartbeatRef.current = null;
      }
      
      // 非主动关闭则重连 WebSocket 关闭时会带一个"关闭码" 1000代表正常关闭
      if (event.code !== 1000) {
        const delay = Math.min(3000 * Math.pow(2, reconnectAttempts.current), 30000);
        reconnectAttempts.current += 1;
        console.log(`🔄 [AlarmWS] ${delay / 1000}秒后重连...`);
        
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, delay);
      }
    };

    ws.onerror = (error) => { // WebSocket 的规则是：出错误后紧接着一定会触发 onclose
      console.error('⚠️ [AlarmWS] 连接错误');
    };
  }, [handleMessage]);

  // 手动重连
  const manualReconnect = useCallback(() => {
    reconnectAttempts.current = 0;
    connect();  //调用连接函数
  }, [connect]);

  // 组件挂载时连接
  useEffect(() => {
    connect();

    return () => {
      if (heartbeatRef.current) {
        clearInterval(heartbeatRef.current);
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect]);

  // 页面长期打开时也要及时移除已跨过保留期的告警。
  useEffect(() => {
    const removeExpired = () => {
      setRecentAlarms(prev => {
        const next = pruneExpiredAlarms(prev);
        return next.length === prev.length ? prev : next;
      });
    };
    removeExpired();
    const timer = setInterval(removeExpired, 30000);
    return () => clearInterval(timer);
  }, []);

  // 调试：监控状态变化
  useEffect(() => {
    console.log('📊 [AlarmWS Provider] 告警列表更新:', recentAlarms.length, '条');
  }, [recentAlarms]);
  
  useEffect(() => {
    console.log('📊 [AlarmWS Provider] AI分析次数状态更新:', aiCount);
  }, [aiCount]);
  
  useEffect(() => {
    console.log('📊 [AlarmWS Provider] 异常统计状态更新:', anomaly);
  }, [anomaly]);

  const value = {
    aiCount,
    anomaly,
    recentAlarms,
    isConnected,
    reconnect: manualReconnect
  };

  return (
    <AlarmWebSocketContext.Provider value={value}>
      {children}
    </AlarmWebSocketContext.Provider>
  );
}

/**
 * 使用告警 WebSocket 数据的 Hook
 */
export function useAlarmWebSocket() {
  const context = useContext(AlarmWebSocketContext);
  if (!context) {
    throw new Error('useAlarmWebSocket 必须在 AlarmWebSocketProvider 内部使用');
  }
  return context;
}
