/**
 * 全局配置文件
 *
 * 对接真实后端时，只需修改此文件中的地址即可。
 * USE_MOCK = true  时连接 Vite 开发服务器内置的 Mock WebSocket；
 * USE_MOCK = false 时连接下方配置的真实后端地址。
 */

// 是否使用 Mock 数据（开发演示用，无硬件时设为 true）
export const USE_MOCK = false

// 真实后端 WebSocket 地址（状态机 + 控制指令）
// 格式: ws://<后端IP>:<端口>/ws/robot
export const REAL_WS_URL = 'ws://192.168.126.176:8765/front'

// 视频流配置
// type 可选:
//   'mock'    - Mock 模拟画面（Canvas 动画）
//   'mjpeg'   - MJPEG 视频流，直接用 <img src> 显示，后端持续推送 JPEG 帧
//   'ws-jpeg' - WebSocket 传输 JPEG 二进制帧，前端解码到 Canvas（低延迟推荐）
//   'ws-h264' - WebSocket 传输 H.264 裸流，需引入 jsmpeg 等解码器
//   'webrtc'  - WebRTC 视频流（最低延迟，需后端配合）
export const CAMERAS = [
  {
    id: 'cam_front',
    name: '机器狗前置摄像头',
    type: 'ws-h264',           // 对接真实硬件时改为 'mjpeg' 或 'ws-jpeg'
    wsUrl: 'ws://192.168.126.176:8765/front',
    supportDepth: false,    // 普通RGB摄像头，不支持深度图
    mockScene: 'corridor'   // Mock 场景: corridor / room / arm / depth
  }
]

// 机器狗状态枚举
export const DOG_STATES = ['趴', '站', '导航', '移动']

// 机械臂状态枚举
export const ARM_STATES = ['停止', '预抓取', '抓取', '保持抓取回位等待', '预放置', '放置']

// 状态对应的颜色（CSS 变量名，在 global.css 中定义）
export const DOG_STATE_COLORS = {
  '趴': '#6b7280',
  '站': '#3b82f6',
  '导航': '#eab308',
  '移动': '#76ff03'
}

export const ARM_STATE_COLORS = {
  '停止': '#6b7280',
  '预抓取': '#0ea5e9',
  '抓取': '#22c55e',
  '保持抓取回位等待': '#4ade80',
  '预放置': '#f97316',
  '放置': '#06b6d4'
}

// 重连配置
export const WS_RECONNECT_INTERVAL = 3000  // WebSocket 断线重连间隔(ms)
export const WS_MAX_RECONNECT = 10          // 最大重连次数
