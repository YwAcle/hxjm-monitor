/**
 * useVideoStream - 视频流处理 composable
 *
 * 支持多种视频流类型:
 * - mock:    Canvas 模拟动画（开发演示）
 * - mjpeg:   <img> 标签直接显示 MJPEG 流（最简单，后端 multipart/x-mixed-replace）
 * - ws-jpeg: WebSocket 接收 JPEG 二进制帧，绘制到 Canvas（低延迟）
 * - ws-h264: WebSocket 接收 H.264 裸流（需引入 jsmpeg 解码器，预留接口）
 *
 * 使用方法:
 *   const { canvasRef, imgRef, start, stop, switchView } = useVideoStream(cameraConfig)
 *   onMounted(start)
 *   onUnmounted(stop)
 */

import { ref, onUnmounted, watch } from 'vue'
import { USE_MOCK } from '../config/index.js'
import { addLog } from '../utils/logger.js'

export function useVideoStream(camera) {
  const canvasRef = ref(null)   // Canvas 引用（用于 ws-jpeg / mock）
  const imgRef = ref(null)      // Img 引用（用于 mjpeg）
  const online = ref(false)
  const currentView = ref('rgb') // rgb | depth

  let ws = null
  let mockAnimId = null
  let mockCanvasCtx = null
  let reconnectTimer = null

  /**
   * 根据配置获取实际流类型
   * Mock 模式下强制使用 mock
   */
  function getStreamType() {
    if (USE_MOCK) return 'mock'
    return camera.type
  }

  /**
   * 启动视频流
   */
  function start() {
    const type = getStreamType()
    switch (type) {
      case 'mock':
        startMock()
        break
      case 'mjpeg':
        startMjpeg()
        break
      case 'ws-jpeg':
        startWsJpeg()
        break
      case 'ws-h264':
        startWsH264()
        break
      default:
        addLog(`未知视频流类型: ${type}`, 'error')
    }
  }

  /**
   * 停止视频流
   */
  function stop() {
    if (ws) {
      ws.close()
      ws = null
    }
    if (mockAnimId) {
      cancelAnimationFrame(mockAnimId)
      mockAnimId = null
    }
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    online.value = false
  }

  // ===== MJPEG 方式 =====
  function startMjpeg() {
    if (!imgRef.value) return
    const url = currentView.value === 'depth'
      ? camera.mjpegUrl + '?view=depth'
      : camera.mjpegUrl
    imgRef.value.src = url
    online.value = true
    addLog(`${camera.name} MJPEG 流已连接`, 'success')
  }

  // ===== WebSocket JPEG 帧方式 =====
  function startWsJpeg() {
    const url = currentView.value === 'depth'
      ? camera.wsUrl + '?view=depth'
      : camera.wsUrl

    try {
      ws = new WebSocket(url)
    } catch (e) {
      addLog(`${camera.name} 视频流连接失败: ${e.message}`, 'error')
      scheduleReconnect()
      return
    }

    ws.binaryType = 'arraybuffer'

    ws.onopen = () => {
      online.value = true
      addLog(`${camera.name} 视频流已连接`, 'success')
    }

    ws.onmessage = (event) => {
      // 收到 JPEG 二进制帧，解码绘制到 Canvas
      const blob = new Blob([event.data], { type: 'image/jpeg' })
      const url = URL.createObjectURL(blob)
      const img = new Image()
      img.onload = () => {
        const canvas = canvasRef.value
        if (canvas) {
          const ctx = canvas.getContext('2d')
          canvas.width = img.width
          canvas.height = img.height
          ctx.drawImage(img, 0, 0)
        }
        URL.revokeObjectURL(url)
      }
      img.src = url
    }

    ws.onclose = () => {
      online.value = false
      scheduleReconnect()
    }

    ws.onerror = () => {
      online.value = false
    }
  }

  // ===== WebSocket H.264 方式（预留） =====
  function startWsH264() {
    // 需要引入 jsmpeg: npm install jsmpeg
    // 示例:
    // import JSMpeg from 'jsmpeg-player'
    // const player = new JSMpeg.Player(camera.wsUrl, { canvas: canvasRef.value })
    addLog(`${camera.name} H.264 流需要安装 jsmpeg 依赖，当前为预留接口`, 'warn')
    // 降级为 mock 展示
    startMock()
  }

  function scheduleReconnect() {
    if (reconnectTimer) return
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      if (getStreamType() === 'ws-jpeg') startWsJpeg()
    }, 3000)
  }

  // ===== Mock 模拟画面 =====
  function startMock() {
    const canvas = canvasRef.value
    if (!canvas) return
    mockCanvasCtx = canvas.getContext('2d')
    canvas.width = 640
    canvas.height = 360
    online.value = true

    let frame = 0
    const scene = camera.mockScene || 'corridor'

    const render = () => {
      mockAnimId = requestAnimationFrame(render)
      frame++
      const ctx = mockCanvasCtx
      const w = canvas.width
      const h = canvas.height

      // 清空
      ctx.fillStyle = '#0a0f1e'
      ctx.fillRect(0, 0, w, h)

      switch (scene) {
        case 'corridor':
          drawCorridor(ctx, w, h, frame)
          break
        case 'room':
          drawRoom(ctx, w, h, frame)
          break
        case 'arm':
          drawArmView(ctx, w, h, frame)
          break
        case 'depth':
          drawDepthView(ctx, w, h, frame, currentView.value === 'depth')
          break
      }

      // 画面左上角 REC 标识
      if (frame % 60 < 40) {
        ctx.fillStyle = '#ff3333'
        ctx.beginPath()
        ctx.arc(20, 20, 5, 0, Math.PI * 2)
        ctx.fill()
      }
      ctx.fillStyle = '#ff3333'
      ctx.font = '12px Consolas'
      ctx.fillText('REC', 30, 24)

      // 时间戳
      const now = new Date()
      ctx.fillStyle = 'rgba(255,255,255,0.6)'
      ctx.font = '11px Consolas'
      ctx.fillText(now.toLocaleTimeString(), w - 75, 20)
    }
    render()
  }

  // 模拟走廊场景
  function drawCorridor(ctx, w, h, frame) {
    // 透视走廊
    const cx = w / 2
    const offset = Math.sin(frame * 0.02) * 3
    ctx.strokeStyle = '#1a3a5c'
    ctx.lineWidth = 1
    for (let i = 0; i < 10; i++) {
      const t = i / 10
      const y = h * 0.3 + t * h * 0.7
      const spread = t * w * 0.45
      ctx.beginPath()
      ctx.moveTo(cx - spread + offset, y)
      ctx.lineTo(cx + spread + offset, y)
      ctx.stroke()
    }
    // 两侧墙线
    ctx.strokeStyle = '#2a5a8c'
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.moveTo(0, h * 0.3)
    ctx.lineTo(cx + offset, h)
    ctx.moveTo(w, h * 0.3)
    ctx.lineTo(cx + offset, h)
    ctx.stroke()

    // 远处机器狗剪影
    ctx.fillStyle = '#1a3050'
    const dogY = h * 0.35 + Math.sin(frame * 0.03) * 2
    ctx.fillRect(cx - 15 + offset, dogY, 30, 20)
    ctx.fillRect(cx - 18 + offset, dogY + 5, 6, 12)
    ctx.fillRect(cx + 12 + offset, dogY + 5, 6, 12)
  }

  // 模拟房间场景
  function drawRoom(ctx, w, h, frame) {
    // 地面
    ctx.fillStyle = '#1a2540'
    ctx.fillRect(0, h * 0.5, w, h * 0.5)
    // 墙壁
    ctx.fillStyle = '#0f1828'
    ctx.fillRect(0, 0, w, h * 0.5)
    // 货架
    ctx.fillStyle = '#1e3050'
    ctx.fillRect(w * 0.1, h * 0.15, 60, h * 0.35)
    ctx.fillRect(w * 0.75, h * 0.1, 80, h * 0.4)
    // 机器狗
    const dx = w * 0.4 + Math.sin(frame * 0.015) * 20
    const dy = h * 0.55
    ctx.fillStyle = '#2a4060'
    ctx.fillRect(dx - 20, dy - 15, 40, 25)
    ctx.fillRect(dx - 25, dy + 5, 8, 15)
    ctx.fillRect(dx + 17, dy + 5, 8, 15)
    // 头
    ctx.fillStyle = '#3a5070'
    ctx.fillRect(dx - 8, dy - 25, 16, 12)
  }

  // 模拟机械臂视角（地面垃圾）
  function drawArmView(ctx, w, h, frame) {
    // 地面纹理
    ctx.fillStyle = '#2a2a2a'
    ctx.fillRect(0, 0, w, h)
    ctx.fillStyle = '#333'
    for (let i = 0; i < 50; i++) {
      const x = (i * 137 + frame * 0.1) % w
      const y = (i * 89) % h
      ctx.fillRect(x, y, 3, 2)
    }
    // 垃圾物体
    const objs = [
      { x: w * 0.6, y: h * 0.5, r: 12, color: '#8b4513' },
      { x: w * 0.35, y: h * 0.65, r: 8, color: '#d4a017' },
      { x: w * 0.7, y: h * 0.7, r: 10, color: '#556b2f' }
    ]
    objs.forEach(o => {
      ctx.fillStyle = o.color
      ctx.beginPath()
      ctx.arc(o.x, o.y, o.r, 0, Math.PI * 2)
      ctx.fill()
    })
    // 机械臂夹爪（画面上方）
    const gripOffset = Math.sin(frame * 0.03) * 5
    ctx.fillStyle = '#4a5568'
    ctx.fillRect(w / 2 - 25 + gripOffset, 0, 50, 30)
    ctx.fillStyle = '#2d3748'
    ctx.fillRect(w / 2 - 20 + gripOffset, 25, 8, 25)
    ctx.fillRect(w / 2 + 12 + gripOffset, 25, 8, 25)
    // 检测框
    ctx.strokeStyle = '#76ff03'
    ctx.lineWidth = 2
    ctx.setLineDash([4, 4])
    ctx.strokeRect(w * 0.6 - 20, h * 0.5 - 20, 40, 40)
    ctx.setLineDash([])
    ctx.fillStyle = '#76ff03'
    ctx.font = '10px Consolas'
    ctx.fillText('trash 0.92', w * 0.6 - 20, h * 0.5 - 24)
  }

  // 模拟深度图（伪彩色）
  function drawDepthView(ctx, w, h, frame, isDepth) {
    if (isDepth) {
      // 深度伪彩色
      const imgData = ctx.createImageData(w, h)
      for (let y = 0; y < h; y++) {
        for (let x = 0; x < w; x++) {
          const i = (y * w + x) * 4
          // 模拟深度值：中心近，边缘远
          const dx = (x - w / 2) / (w / 2)
          const dy = (y - h / 2) / (h / 2)
          let depth = Math.sqrt(dx * dx + dy * dy)
          depth = Math.min(1, depth + Math.sin(frame * 0.02 + x * 0.02) * 0.05)
          // 伪彩色映射 (蓝->青->绿->黄->红)
          const r = depth < 0.5 ? depth * 2 * 255 : 255
          const g = depth < 0.3 ? depth * 3 * 255 : (depth < 0.7 ? 255 : (1 - depth) * 3 * 255)
          const b = depth < 0.3 ? 255 : (depth < 0.5 ? (0.5 - depth) * 2 * 255 : 0)
          imgData.data[i] = r
          imgData.data[i + 1] = g
          imgData.data[i + 2] = b
          imgData.data[i + 3] = 255
        }
      }
      ctx.putImageData(imgData, 0, 0)
      // 垃圾物体高亮
      ctx.fillStyle = 'rgba(255,255,0,0.3)'
      ctx.beginPath()
      ctx.arc(w * 0.55, h * 0.6, 20, 0, Math.PI * 2)
      ctx.fill()
    } else {
      // RGB 模式：复用 arm 场景
      drawArmView(ctx, w, h, frame)
    }
  }

  /**
   * 切换 RGB/深度视图
   */
  function switchView(view) {
    if (view === currentView.value) return
    if (view === 'depth' && !camera.supportDepth) return
    currentView.value = view
    // 重连流以切换视图
    stop()
    setTimeout(start, 100)
  }

  onUnmounted(stop)

  return {
    canvasRef,
    imgRef,
    online,
    currentView,
    start,
    stop,
    switchView
  }
}
