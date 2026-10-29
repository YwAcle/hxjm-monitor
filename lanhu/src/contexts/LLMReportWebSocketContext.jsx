import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';

// 创建 Context
const LLMReportWebSocketContext = createContext(null);

/**
 * LLM Report WebSocket Provider
 * 接收大模型日志报告推送
 */
export function LLMReportWebSocketProvider({ children }) {
  const [reports, setReports] = useState([]);  // 报告数据
  const [isConnected, setIsConnected] = useState(false); //webSocket连接状态
  
  const wsRef = useRef(null); // webSocket连接对象
  const heartbeatRef = useRef(null); // 心跳计时器
  const reconnectTimeoutRef = useRef(null);  // 重连计时器
  const reconnectAttempts = useRef(0); // 重连次数
  
  // 使用 ref 存储最新的 setter 函数
  const settersRef = useRef({
    setReports,
    setIsConnected
  });
  
  useEffect(() => {
    settersRef.current = {
      setReports,
      setIsConnected
    };
  });

  // 处理 WebSocket 消息
  const handleMessage = useCallback((event) => {
    try {
      const msg = JSON.parse(event.data);
      console.log('📋 [LLMReportWS] 收到消息:', msg.type, msg.op);

      const { setReports } = settersRef.current;

      if (msg.type === 'llm_report') {
        if (msg.op === 'init') {
          // 初始化：设置历史记录
          const items = msg.data?.items || [];
          console.log('📋 [LLMReportWS] 初始化，收到', items.length, '条历史记录');
          setReports(items);
        } else if (msg.op === 'append') {
          // 追加：添加新记录
          const items = msg.data?.items || [];
          console.log('📋 [LLMReportWS] 追加', items.length, '条新记录');
          setReports(prev => {
            // 合并并保留最新的 100 条（防止内存溢出）
            const newReports = [...prev, ...items];
            if (newReports.length > 100) {
              return newReports.slice(-100);
            }
            return newReports;
          });
        }
      } else if (msg.type === 'pong') {
        //TODO 可能会出现半开连接
        // 心跳响应
      } else if (msg.type === 'error') {
        console.error('❌ [LLMReportWS] 服务器错误:', msg.message);
      }
    } catch (error) {
      console.error('[LLMReportWS] 解析消息失败:', error);
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

    console.log('🔌 [LLMReportWS] 正在连接...');
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws/llm-report`);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('✅ [LLMReportWS] 已连接');
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
      console.log('❌ [LLMReportWS] 断开连接', event.code);
      settersRef.current.setIsConnected(false);
      
      if (heartbeatRef.current) {
        clearInterval(heartbeatRef.current);
        heartbeatRef.current = null;
      }
      
      // 非主动关闭则重连
      if (event.code !== 1000) {
        const delay = Math.min(3000 * Math.pow(2, reconnectAttempts.current), 30000);
        reconnectAttempts.current += 1;
        console.log(`🔄 [LLMReportWS] ${delay / 1000}秒后重连...`);
        
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, delay);
      }
    };

    ws.onerror = (error) => {
      console.error('⚠️ [LLMReportWS] 连接错误');
    };
  }, [handleMessage]);

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

  const value = {
    reports,
    isConnected
  };

  return (
    <LLMReportWebSocketContext.Provider value={value}>
      {children}
    </LLMReportWebSocketContext.Provider>
  );
}

/**
 * 使用 LLM Report WebSocket 数据的 Hook
 */
export function useLLMReportWebSocket() {
  const context = useContext(LLMReportWebSocketContext);
  if (!context) {
    throw new Error('useLLMReportWebSocket 必须在 LLMReportWebSocketProvider 内部使用');
  }
  return context;
}

