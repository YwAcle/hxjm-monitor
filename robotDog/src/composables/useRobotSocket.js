/**
 * useRobotSocket - 机器人状态 WebSocket 通信 composable
 *
 * 职责：
 * 1. 建立/维护与后端的 WebSocket 连接
 * 2. 自动重连（断线后按间隔重试）
 * 3. 接收后端推送的状态 JSON，更新响应式状态
 * 4. 提供 sendCommand 方法向前端发送控制指令
 *
 * 后端推送消息格式见 docs/API.md
 */

import { reactive, ref, onUnmounted } from 'vue'
import { USE_MOCK, REAL_WS_URL, WS_RECONNECT_INTERVAL, WS_MAX_RECONNECT } from '../config/index.js'
import { addLog } from '../utils/logger.js'

export function useRobotSocket() {
  // ===== 响应式状态 =====
  const connected = ref(false)
  const reconnectCount = ref(0)

  // 机器人完整状态（与后端推送的 JSON 结构对应）
  const robotState = reactive({
    timestamp: Date.now(),
    dog: {
      state: '趴',              // 趴 | 站 | 导航 | 移动
      velocity: 0,              // 底盘速度 m/s
      target_trash: [0, 0, 0],  // 目标垃圾坐标 [x, y, z]
      position: [0, 0],         // 机器狗当前位置 [x, y]
      battery: 100              // 电量百分比
    },
    arm: {
      state: '停止',            // 停止 | 预抓取 | 抓取 | 保持抓取回位等待 | 预放置 | 放置
      gripper: 'open',          // open | close
      joints: [0, 0, 0, 0, 0, 0], // 6轴关节角度(度)
      target_place: [0, 0, 0]   // 放置点坐标
    },
    cameras: {
      cam_front: { online: true, depth_available: false },
      cam_back:  { online: true, depth_available: false },
      d435:      { online: true, depth_available: true },
      d455:      { online: true, depth_available: true }
    }
  })

  let ws = null
  let reconnectTimer = null
  let manualClose = false

  /**
   * 构造 WebSocket URL
   * Mock 模式下连接 Vite 开发服务器的 /ws/robot 路径
   */
  function getWsUrl() {
    if (USE_MOCK) {
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
      return `${proto}//${location.host}/ws/robot`
    }
    return REAL_WS_URL
  }

  /**
   * 连接 WebSocket
   */
  function connect() {
    manualClose = false
    const url = getWsUrl()
    addLog(`正在连接后端服务: ${url}`, 'info')

    try {
      ws = new WebSocket(url)
    } catch (e) {
      addLog(`WebSocket 创建失败: ${e.message}`, 'error')
      scheduleReconnect()
      return
    }

    ws.onopen = () => {
      connected.value = true
      reconnectCount.value = 0
      addLog('后端服务连接成功', 'success')
    }

    ws.onmessage = (event) => {
      handleMessage(event.data)
    }

    ws.onclose = () => {
      connected.value = false
      if (!manualClose) {
        addLog('后端连接断开，尝试重连...', 'warn')
        scheduleReconnect()
      }
    }

    ws.onerror = () => {
      addLog('WebSocket 连接错误', 'error')
    }
  }

  /**
   * 处理收到的消息
   */
  function handleMessage(data) {
    let msg
    try {
      msg = JSON.parse(data)
    } catch {
      addLog(`收到非JSON数据: ${data}`, 'warn')
      return
    }

    switch (msg.type) {
      case 'robot_status':
        updateRobotState(msg.data)
        break
      case 'log':
        addLog(msg.message, msg.level || 'info')
        break
      case 'pong':
        // 心跳响应，无需处理
        break
      default:
        console.warn('未知消息类型:', msg.type)
    }
  }

  /**
   * 更新机器人状态（增量合并）
   */
  function updateRobotState(data) {
    if (!data) return
    robotState.timestamp = data.timestamp || Date.now()

    if (data.dog) {
      const prevDogState = robotState.dog.state
      Object.assign(robotState.dog, data.dog)
      if (data.dog.state && data.dog.state !== prevDogState) {
        addLog(`机器狗状态切换: ${prevDogState} → ${data.dog.state}`, 'info')
      }
    }

    if (data.arm) {
      const prevArmState = robotState.arm.state
      Object.assign(robotState.arm, data.arm)
      if (data.arm.state && data.arm.state !== prevArmState) {
        addLog(`机械臂状态切换: ${prevArmState} → ${data.arm.state}`, 'info')
      }
    }

    if (data.cameras) {
      Object.assign(robotState.cameras, data.cameras)
    }
  }

  /**
   * 安排重连
   */
  function scheduleReconnect() {
    if (reconnectTimer) return
    if (reconnectCount.value >= WS_MAX_RECONNECT) {
      addLog(`已达最大重连次数(${WS_MAX_RECONNECT})，停止重连`, 'error')
      return
    }
    reconnectCount.value++
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connect()
    }, WS_RECONNECT_INTERVAL)
  }

  /**
   * 发送控制指令给后端
   * @param {string} command - 指令名称
   * @param {object} params - 指令参数
   *
   * 指令列表见 docs/API.md
   */
  function sendCommand(command, params = {}) {
    if (!connected.value || !ws) {
      addLog('未连接后端，指令发送失败', 'error')
      return false
    }
    const msg = JSON.stringify({
      type: 'command',
      command,
      params,
      timestamp: Date.now()
    })
    ws.send(msg)
    addLog(`发送指令: ${command}`, 'info')
    return true
  }

  /**
   * 主动断开连接
   */
  function disconnect() {
    manualClose = true
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (ws) {
      ws.close()
      ws = null
    }
    connected.value = false
  }

  onUnmounted(() => {
    disconnect()
  })

  return {
    connected,
    robotState,
    connect,
    disconnect,
    sendCommand
  }
}
