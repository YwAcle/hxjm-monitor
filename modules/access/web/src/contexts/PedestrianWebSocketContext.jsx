import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';

// 创建 Context
const PedestrianWebSocketContext = createContext(null);

// 解析时间字符串为时间戳
// 把身份记录的 detected_time（识别时间）转成时间戳，用于排序
const parseTimeToTimestamp = (timeStr) => {
  if (!timeStr) return Date.now();
  
  const parsed = new Date(timeStr);
  if (!isNaN(parsed.getTime())) {
    return parsed.getTime();
  }
  
  const match = timeStr.match(/(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})/);
  if (match) {
    const [, year, month, day, hour, min, sec] = match;
    return new Date(year, month - 1, day, hour, min, sec).getTime();
  }
  
  return Date.now();  //兜底方案：用现在的时间
};

// 格式化身份数据
// 如果 name 为空或 '未知'，返回 null（表示需要过滤掉）
const formatIdentity = (identity, timestamp = null) => {
  // 如果 name 为空、null、undefined 或 '未知'，直接返回 null
  const name = identity.name;
  if (!name || name === '未知' || name.trim() === '') {
    return null;
  }
  
  let avatar = identity.avatar;
  
  // 处理 base64 头像
  if (avatar) {
    // 修复格式问题：后端可能发送 base64: 而不是 base64,
    if (avatar.startsWith('data:image')) {
      // 把 ;base64: 替换成 ;base64, （注意：/9j/ 等是 base64 数据的一部分，不是分隔符）
      avatar = avatar.replace(';base64:', ';base64,');
    } else if (!avatar.startsWith('/') && !avatar.startsWith('http')) {
      avatar = `data:image/jpeg;base64,${avatar}`;
    }
  }

  const timeStr = identity.detected_time || '';
  
  // 如果姓名是"冷佳旭"，职称设置为"教师"，否则使用后端返回的职称
  let jobTitle = identity.identity || '访客';
  if (name === '冷佳旭') {
    jobTitle = '教师';
  }
  
  return {
    id: identity.id || identity.target_id,
    name: name,
    avatar: avatar,
    identity: jobTitle,
    camera_id: identity.camera_id || '',
    detected_time: timeStr,
    timestamp: timestamp || parseTimeToTimestamp(timeStr)
  };
};

/**
 * 行人 WebSocket Provider
 * 连接地址: ws://192.168.108.238:8080/ws/pedestrian
 */
export function PedestrianWebSocketProvider({ children }) {
  const [aiCount, setAiCount] = useState(0);  // Ai分析次数
  const [flow, setFlow] = useState({ //人流曲线
    total_today: 0,
    start_time: '',
    end_time: '',
    data_points: []
  });
  const [identities, setIdentities] = useState([]);  // 身份列表
  const [isConnected, setIsConnected] = useState(false);  // webSocket的连接状态
  
  const wsRef = useRef(null);  // webSocket连接对象
  const heartbeatRef = useRef(null); // 心跳计时器
  const reconnectTimeoutRef = useRef(null); // 重连计时器
  const reconnectAttempts = useRef(0); // 重连次数
  
  // 使用 ref 存储最新的 setter 函数
  const settersRef = useRef({
    setAiCount,
    setFlow,
    setIdentities,
    setIsConnected
  });
  
  useEffect(() => {
    settersRef.current = {
      setAiCount,
      setFlow,
      setIdentities,
      setIsConnected
    };
  });

  // 处理 WebSocket 消息
  const handleMessage = useCallback((event) => {
    try {
      const msg = JSON.parse(event.data);
      console.log('📨 [PedestrianWS] 收到消息:', msg.type);

      const { setAiCount, setFlow, setIdentities } = settersRef.current;

      switch (msg.type) {
        case 'init':
          if (msg.data) {
            console.log('📋 [PedestrianWS] 处理 init 数据');
            
            // 更新 AI 分析次数
            if (msg.data.ai_count !== undefined) {
              setAiCount(msg.data.ai_count);
            }
            
            // 更新人流量数据
            if (msg.data.flow) {
              const dataPoints = msg.data.flow.data_points || [];
              console.log('📋 [PedestrianWS] 初始化人流数据，共', dataPoints.length, '个点');
              if (dataPoints.length > 0) {
                console.log('📋 [PedestrianWS] 时间范围:', dataPoints[0]?.time, '-', dataPoints[dataPoints.length - 1]?.time);
              }
              setFlow({
                total_today: msg.data.flow.total_today || 0,
                start_time: msg.data.flow.start_time || '',
                end_time: msg.data.flow.end_time || '',
                data_points: dataPoints
              });
            }
            
            // 格式化并排序身份列表（最新的在前），只保留 20 条
            if (msg.data.identities) {
              let formattedIdentities = msg.data.identities
                .map(id => formatIdentity(id))
                .filter(id => id !== null); // 过滤掉 name 为 '未知' 的数据
              formattedIdentities = formattedIdentities
                .sort((a, b) => b.timestamp - a.timestamp)
                .slice(0, 20);
              setIdentities(formattedIdentities);
              console.log('📋 [PedestrianWS] 初始化身份列表:', formattedIdentities.length, '条');
            }
          }
          break;

        // 处理 metrics 消息类型（每2秒发送）
        case 'metrics':
          if (msg.data) {
            console.log('📊 [PedestrianWS] 收到 metrics 数据:', JSON.stringify(msg.data));
            
            // 更新 AI 分析次数（如果存在）
            if (msg.data.ai_count !== undefined) {
              console.log('📊 [PedestrianWS] 更新 AI 分析次数:', msg.data.ai_count);
              setAiCount(msg.data.ai_count);
            }
            
            // 检查是否带有 flow_update 字段
            if (msg.data.flow_update) {
              // 带 flow_update：更新曲线和今日人流量
              const updateTime = msg.data.flow_update.time; //时间点
              const updateCount = msg.data.flow_update.count; //该时间点的人数
              const updateTotal = msg.data.flow_update.total_today; //今日总人数
              
              console.log('📈 [PedestrianWS] 更新人流曲线，time:', updateTime, 'count:', updateCount, 'total:', updateTotal);
              
              setFlow(prev => {
                // 创建新的数组引用，确保 React 能检测到变化
                const newDataPoints = prev.data_points.map(p => ({ ...p }));
                
                // 查找是否存在该时间点
                const existingIndex = newDataPoints.findIndex(p => p.time === updateTime);
                if (existingIndex >= 0) {
                  console.log('📈 [PedestrianWS] 更新已存在的时间点:', updateTime);
                  newDataPoints[existingIndex] = { time: updateTime, count: updateCount };
                } else {
                  console.log('📈 [PedestrianWS] 添加新时间点:', updateTime);
                  // 新增时间点
                  newDataPoints.push({ time: updateTime, count: updateCount });
                  // 按时间排序
                  newDataPoints.sort((a, b) => a.time.localeCompare(b.time));
                  // 如果超过48个点，移除最早的
                  if (newDataPoints.length > 48) {
                    newDataPoints.shift();
                  }
                }
                
                console.log('📈 [PedestrianWS] 更新后 data_points 数量:', newDataPoints.length, '最后一个:', newDataPoints[newDataPoints.length - 1]?.time);
                
                return {
                  ...prev,
                  total_today: updateTotal !== undefined ? updateTotal : prev.total_today,
                  data_points: newDataPoints
                };
              });
            } else if (msg.data.total_today !== undefined) {
              // 不带 flow_update：只更新今日总人流量
              console.log('👥 [PedestrianWS] 更新今日人流量:', msg.data.total_today);
              setFlow(prev => ({
                ...prev,
                total_today: msg.data.total_today
              }));
            }
          }
          break;
        
        // 新身份识别
        case 'new_identity':
          if (msg.data) {
            console.log('👤 [PedestrianWS] 收到新身份识别!');
            
            // 更新 AI 分析次数（如果存在）
            if (msg.data.ai_count !== undefined) {
              console.log('👤 [PedestrianWS] 更新 AI 分析次数:', msg.data.ai_count);
              setAiCount(msg.data.ai_count);
            }

            // 更新今日总人流量（直接从 data.total_today 读取）
            if (msg.data.total_today !== undefined) {
              console.log('👤 [PedestrianWS] 更新今日人流量:', msg.data.total_today);
              setFlow(prev => ({
                ...prev,
                total_today: msg.data.total_today
              }));
            }

            // 添加新身份到列表
            const identityData = msg.data.identity;
            if (identityData && (identityData.id || identityData.name || identityData.avatar)) {
              // 如果 name 为空或 '未知'，直接丢弃这条数据
              const name = identityData.name;
              if (!name || name === '未知' || name.trim() === '') {
                console.log('👤 [PedestrianWS] 丢弃未知身份数据');
                return;
              }
              
              const nowTimestamp = Date.now();
              const uniqueId = identityData.id || `identity_${nowTimestamp}`;
              
              // 使用后端提供的时间，或生成当前时间
              const timeStr = identityData.detected_time || 
                (() => {
                  const now = new Date(nowTimestamp);
                  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ` +
                    `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`;
                })();
              
              const completeIdentityData = {
                id: uniqueId,
                name: name,
                avatar: identityData.avatar || '',
                identity: identityData.identity || '访客',
                camera_id: identityData.camera_id || '',
                detected_time: timeStr
              };
              
              const formattedIdentity = formatIdentity(completeIdentityData, nowTimestamp);
              
              // 再次检查（formatIdentity 也会检查，但这里双重保险）
              if (!formattedIdentity) {
                console.log('👤 [PedestrianWS] 格式化后丢弃未知身份数据');
                return;
              }
              
              console.log('👤 [PedestrianWS] 新身份:', formattedIdentity.name, formattedIdentity.detected_time);
              
              setIdentities(prev => {
                // 添加新身份，按时间戳排序（最新的在前），只保留 20 条
                const newIdentities = [formattedIdentity, ...prev]
                  .sort((a, b) => b.timestamp - a.timestamp)
                  .slice(0, 20);
                console.log('👤 [PedestrianWS] 身份列表已更新，当前数量:', newIdentities.length);
                return newIdentities;
              });
            }
          }
          break;

        case 'pong':
          break;

        case 'error':
          console.error('❌ [PedestrianWS] 服务器错误:', msg.message || msg);
          break;

        default:
          console.warn('⚠️ [PedestrianWS] 未知消息类型:', msg.type);
      }
    } catch (error) {
      console.error('[PedestrianWS] 解析消息失败:', error);
    }
  }, []);

  // 连接函数
  const connect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      wsRef.current.close();
      wsRef.current = null;
    }

    console.log('🔌 [PedestrianWS] 正在连接...');
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws/pedestrian`);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('✅ [PedestrianWS] 已连接');
      settersRef.current.setIsConnected(true);
      reconnectAttempts.current = 0;
      
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
      console.log('❌ [PedestrianWS] 断开连接', event.code);
      settersRef.current.setIsConnected(false);
      
      if (heartbeatRef.current) {
        clearInterval(heartbeatRef.current);
        heartbeatRef.current = null;
      }
      
      if (event.code !== 1000) {
        const delay = Math.min(3000 * Math.pow(2, reconnectAttempts.current), 30000);
        reconnectAttempts.current += 1;
        console.log(`🔄 [PedestrianWS] ${delay / 1000}秒后重连...`);
        
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, delay);
      }
    };

    ws.onerror = () => {
      console.error('⚠️ [PedestrianWS] 连接错误');
    };
  }, [handleMessage]);

  // 手动重连
  const manualReconnect = useCallback(() => {
    reconnectAttempts.current = 0;
    connect();
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

  // 调试：监控状态变化
  useEffect(() => {
    console.log('📊 [PedestrianWS Provider] 身份列表更新:', identities.length, '条');
  }, [identities]);
  
  // 调试：监控 flow 状态变化
  useEffect(() => {
    console.log('📈 [PedestrianWS Provider] flow 状态更新:', {
      total_today: flow.total_today,
      data_points_count: flow.data_points?.length,
      last_point: flow.data_points?.[flow.data_points.length - 1]
    });
  }, [flow]);

  const value = {
    aiCount,
    flow,
    identities,
    isConnected,
    reconnect: manualReconnect
  };

  return (
    <PedestrianWebSocketContext.Provider value={value}>
      {children}
    </PedestrianWebSocketContext.Provider>
  );
}

/**
 * 使用行人 WebSocket 数据的 Hook
 */
export function usePedestrianWebSocket() {
  const context = useContext(PedestrianWebSocketContext);
  if (!context) {
    throw new Error('usePedestrianWebSocket 必须在 PedestrianWebSocketProvider 内部使用');
  }
  return context;
}

