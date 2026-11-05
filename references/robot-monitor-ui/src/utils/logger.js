/**
 * 日志工具
 * 统一管理系统日志，支持时间戳、日志级别、自动滚动
 */

import { reactive } from 'vue'

// 全局日志状态（单例，所有组件共享）
const logState = reactive({
  logs: [],
  maxLogs: 200
})

/**
 * 添加一条日志
 * @param {string} message - 日志内容
 * @param {'info'|'warn'|'error'|'success'} level - 日志级别
 */
export function addLog(message, level = 'info') {
  const now = new Date()
  const ts = [
    String(now.getHours()).padStart(2, '0'),
    String(now.getMinutes()).padStart(2, '0'),
    String(now.getSeconds()).padStart(2, '0')
  ].join(':')

  logState.logs.push({
    time: ts,
    message,
    level
  })

  // 超出最大条数时删除最早的
  if (logState.logs.length > logState.maxLogs) {
    logState.logs.splice(0, logState.logs.length - logState.maxLogs)
  }
}

/** 清空日志 */
export function clearLogs() {
  logState.logs.splice(0, logState.logs.length)
}

export function useLogger() {
  return {
    logs: logState.logs,
    addLog,
    clearLogs
  }
}
