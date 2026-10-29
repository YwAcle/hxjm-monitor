/**
 * Vite 插件：Mock WebSocket 服务
 *
 * 在 Vite 开发服务器中挂载一个 WebSocket 服务端点 /ws/robot，
 * 模拟机器狗和机械臂的完整协同作业流程，无需真实硬件即可演示。
 *
 * 模拟场景（每步 3 秒，循环）：
 *   趴→站→导航到垃圾→移动对位+预抓取→抓取→回位等待→
 *   导航到放置点→移动对位+预放置→放置→回站→生成新目标
 *
 * 生产构建时此插件不会被打包，前端将连接 config/index.js 中配置的真实后端。
 */

import { WebSocketServer } from 'ws'

// 完整作业场景脚本：每一步持续 3 秒，循环播放
// 流程：趴→站→导航到垃圾→移动对位→机械臂抓取→回位等待→导航到放置点→移动对位→放置→回站
const SCENARIO = [
  { dog: '趴',   arm: '停止' },
  { dog: '站',   arm: '停止' },
  { dog: '导航', arm: '停止' },
  { dog: '移动', arm: '预抓取' },
  { dog: '移动', arm: '抓取' },
  { dog: '站',   arm: '保持抓取回位等待' },
  { dog: '导航', arm: '保持抓取回位等待' },
  { dog: '移动', arm: '预放置' },
  { dog: '站',   arm: '放置' },
  { dog: '站',   arm: '停止' }
]

export function mockWebSocketPlugin() {
  return {
    name: 'mock-websocket-server',
    configureServer(server) {
      if (!server.httpServer) return

      const wss = new WebSocketServer({ noServer: true })

      // 升级 HTTP 连接为 WebSocket
      server.httpServer.on('upgrade', (req, socket, head) => {
        if (req.url === '/ws/robot') {
          wss.handleUpgrade(req, socket, head, (ws) => {
            wss.emit('connection', ws, req)
          })
        }
      })

      // 模拟状态
      let stepIdx = 0
      let dogVelocity = 0
      let targetTrash = [1.2, 0.3, 0.5]
      let position = [0, 0]
      let battery = 87
      let gripper = 'open'
      let joints = [0, -30, 60, 0, -30, 0]
      let targetPlace = [0.5, -0.3, 0.1]

      wss.on('connection', (ws) => {
        console.log('[Mock] 前端已连接')

        // 发送初始状态
        sendState(ws)

        // 接收前端指令
        ws.on('message', (raw) => {
          try {
            const msg = JSON.parse(raw.toString())
            if (msg.type === 'command') {
              console.log('[Mock] 收到指令:', msg.command, msg.params)
              handleCommand(msg.command, msg.params)
            }
          } catch (e) {
            console.error('[Mock] 消息解析失败:', e.message)
          }
        })

        ws.on('close', () => {
          console.log('[Mock] 前端已断开')
        })
      })

      // 广播状态给所有连接
      function broadcast(data) {
        const str = JSON.stringify(data)
        wss.clients.forEach((client) => {
          if (client.readyState === 1) { // OPEN
            client.send(str)
          }
        })
      }

      function sendState(ws) {
        ws.send(JSON.stringify({
          type: 'robot_status',
          data: buildState()
        }))
      }

      function buildState() {
        const step = SCENARIO[stepIdx]
        return {
          timestamp: Date.now(),
          dog: {
            state: step.dog,
            velocity: dogVelocity,
            target_trash: targetTrash,
            position: position,
            battery: battery
          },
          arm: {
            state: step.arm,
            gripper: gripper,
            joints: joints,
            target_place: targetPlace
          },
          cameras: {
            cam_front: { online: true, depth_available: false },
            cam_back:  { online: true, depth_available: false },
            d435:      { online: true, depth_available: step.dog === '趴' || step.dog === '站' },
            d455:      { online: true, depth_available: step.dog === '趴' || step.dog === '站' }
          }
        }
      }

      // 处理前端指令
      function handleCommand(command, _params) {
        switch (command) {
          case 'dog_stand':
            stepIdx = 1
            break
          case 'dog_lie':
            stepIdx = 0
            break
          case 'arm_stop':
            stepIdx = 0
            break
          case 'arm_home':
            stepIdx = 0
            break
        }
        broadcast({ type: 'robot_status', data: buildState() })
      }

      // ===== 状态机自动模拟 =====
      // 每 3 秒推进一步，按 SCENARIO 脚本循环模拟完整作业流程
      setInterval(() => {
        const prevStep = SCENARIO[stepIdx]
        stepIdx = (stepIdx + 1) % SCENARIO.length
        const step = SCENARIO[stepIdx]

        // 根据机器狗状态更新参数
        switch (step.dog) {
          case '趴':
            dogVelocity = 0
            break
          case '站':
            dogVelocity = 0
            break
          case '导航':
            dogVelocity = 0.8
            position = [
              +(position[0] + (Math.random() - 0.3) * 0.1).toFixed(2),
              +(position[1] + (Math.random() - 0.5) * 0.1).toFixed(2)
            ]
            break
          case '移动':
            dogVelocity = 0.12
            // 接近目标垃圾
            targetTrash = targetTrash.map(v => +(v * 0.9).toFixed(2))
            break
        }

        // 根据机械臂状态更新夹爪和关节
        switch (step.arm) {
          case '停止':
            gripper = 'open'
            joints = [0, -30, 60, 0, -30, 0]
            // 上一步是"放置"则说明刚完成一轮，生成新目标
            if (prevStep.arm === '放置') {
              targetTrash = [
                +(Math.random() * 2 + 0.5).toFixed(1),
                +(Math.random() * 0.6 - 0.3).toFixed(1),
                +(Math.random() * 0.3 + 0.3).toFixed(1)
              ]
            }
            break
          case '预抓取':
            gripper = 'open'
            joints = [15, -45, 80, 10, -45, 0]
            break
          case '抓取':
            gripper = 'close'
            joints = [20, -50, 90, 15, -50, 5]
            break
          case '保持抓取回位等待':
            gripper = 'close'
            joints = [5, -35, 65, 5, -35, 0]
            break
          case '预放置':
            gripper = 'close'
            joints = [-10, -40, 70, -5, -40, -10]
            break
          case '放置':
            gripper = 'open'
            joints = [-15, -45, 75, -10, -45, -15]
            break
        }

        // 电量缓慢下降
        battery = Math.max(10, +(battery - 0.01).toFixed(1))

        broadcast({ type: 'robot_status', data: buildState() })
      }, 3000)

      // 每 1 秒更新一次高频数据（速度波动、关节微调）
      setInterval(() => {
        const step = SCENARIO[stepIdx]
        if (step.dog === '导航' || step.dog === '移动') {
          dogVelocity += (Math.random() - 0.5) * 0.05
          dogVelocity = Math.max(0, Math.min(1, +dogVelocity.toFixed(2)))
        }
        // 关节微小抖动模拟真实硬件
        joints = joints.map(j => +(j + (Math.random() - 0.5) * 0.3).toFixed(2))
      }, 1000)

      console.log('[Mock] WebSocket 服务已启动: ws://localhost:5173/ws/robot')
    }
  }
}
