# M20-Pro机器狗 + DM-B601机械臂综合监控面板

实时监控 M20-Pro 四足机器狗与 DM-B601 六轴机械臂协同作业的前端 UI 面板，包含四路摄像头画面、双设备状态机可视化、系统日志。

![tech](https://img.shields.io/badge/Vue-3.4-brightgreen) ![tech](https://img.shields.io/badge/Vite-5.2-purple) ![tech](https://img.shields.io/badge/WebSocket-实时通信-blue)

---

#111
## 快速开始

### 环境要求

- Node.js >= 16
- npm >= 8（或 pnpm / yarn）

### 安装与运行

```bash
# 1. 安装依赖
npm install

# 2. 启动开发服务器（自带 Mock 数据，无需硬件即可演示）
npm run dev

# 3. 浏览器打开
#    http://localhost:5173
```

启动后你将看到：
- 四路摄像头模拟画面（Canvas 动画，带 REC 标识和时间戳）
- 机器狗状态机自动循环：趴 → 站 → 导航 → 移动
- 机械臂状态机自动循环：停止 → 预抓取 → 抓取 → 保持抓取回位等待 → 预放置 → 放置
- 底部实时日志输出

### 构建生产版本

```bash
npm run build    # 产物在 dist/ 目录
npm run preview  # 本地预览构建产物
```

---

## 对接真实硬件

### 第一步：修改配置

编辑 `src/config/index.js`：

```js
// 将 USE_MOCK 改为 false
export const USE_MOCK = false

// 填写真实后端 WebSocket 地址
export const REAL_WS_URL = 'ws://192.168.1.100:8080/ws/robot'

// 修改每个摄像头的流类型和地址
export const CAMERAS = [
  {
    id: 'cam_front',
    name: '机器狗前置摄像头',
    type: 'mjpeg',                    // 改为 'mjpeg' 或 'ws-jpeg'
    mjpegUrl: 'http://192.168.1.100:8080/stream/cam_front',
    // ...
  },
  // ...
]
```

### 第二步：后端按接口文档实现

详见 [`docs/API.md`](docs/API.md)，包含：
- WebSocket 状态推送协议（JSON 格式）
- 视频流四种方案（MJPEG / WS-JPEG / WS-H264 / WebRTC）
- 控制指令列表
- Python FastAPI 参考代码
- 深度相机硬件限制说明

### 第三步：重启开发服务器

```bash
npm run dev
```

---

## 项目结构

```
robot-monitor-ui/
├── index.html                  # HTML 入口
├── package.json                # 依赖与脚本
├── vite.config.js              # Vite 配置（含 Mock WebSocket 插件）
├── README.md                   # 本文档
├── docs/
│   └── API.md                  # 后端接口文档
├── public/
│   └── favicon.svg             # 站点图标
└── src/
    ├── main.js                 # 应用入口
    ├── App.vue                 # 根组件（页面布局）
    ├── global.css              # 全局样式与 CSS 变量
    ├── config/
    │   └── index.js            # 全局配置（后端地址、摄像头列表、状态枚举与颜色）
    ├── composables/
    │   ├── useRobotSocket.js   # WebSocket 通信：连接管理、状态接收、指令发送、自动重连
    │   └── useVideoStream.js   # 视频流处理：支持 mock/mjpeg/ws-jpeg/ws-h264 四种模式
    ├── components/
    │   ├── TopBar.vue          # 顶部标题栏（标题、连接状态、时间、ping）
    │   ├── VideoCard.vue       # 单个摄像头视频卡片（标题、指示灯、RGB/深度切换、画面）
    │   ├── DogStatePanel.vue   # M20-Pro 机器狗状态面板（当前状态、流程条、参数）
    │   ├── ArmStatePanel.vue   # DM-B601 机械臂状态面板（当前状态、流程图、关节角度）
    │   ├── StateFlow.vue       # 通用状态流转指示器（可复用）
    │   └── LogPanel.vue        # 底部系统日志面板
    ├── mock/
    │   └── mockPlugin.js       # Vite 插件：内置 Mock WebSocket 服务，模拟完整作业流程
    └── utils/
        └── logger.js           # 日志工具（单例，全局共享日志状态）
```

---

## 架构设计

### 数据流

```
┌──────────────┐    WebSocket/JSON     ┌──────────────────┐
│   后端服务    │ ◄──────────────────►  │  useRobotSocket  │
│ (机器人驱动)  │    robot_status       │  (composable)    │
└──────┬───────┘    command            └────────┬─────────┘
       │                                       │ 响应式状态
       │ MJPEG / WS-JPEG                       ▼
       ▼                                ┌──────────────┐
┌──────────────┐                        │   App.vue    │
│  摄像头硬件   │                        │  (页面组装)   │
│ D435 / D455  │                        └──────┬───────┘
└──────────────┘                               │
                    ┌───────────┬───────────┬───┴───┬───────────┐
                    ▼           ▼           ▼       ▼           ▼
              VideoCard   DogStatePanel  ArmState  LogPanel   TopBar
              (×4)                     Panel
```

### 核心设计决策

1. **Composable 模式**：WebSocket 和视频流逻辑封装为 `useRobotSocket` / `useVideoStream`，组件只负责展示，方便复用和测试。

2. **多视频流方案兼容**：`useVideoStream` 通过配置中的 `type` 字段支持四种流模式，切换硬件方案时只需改配置，无需改组件代码。

3. **Mock 即开发**：Vite 插件内置 Mock WebSocket 服务器，完整模拟状态机循环，前端开发不依赖硬件。`USE_MOCK = false` 一键切换真实后端。

4. **自动重连**：WebSocket 断线后按 3 秒间隔自动重连，最多 10 次，重连状态在 UI 上可见。

5. **状态机可视化**：`StateFlow` 组件将状态数组渲染为流程图，当前状态高亮发光、已完成状态变暗，直观展示作业进度。

---

## 页面布局

```
┌─────────────────────────────────────────────────────────┐
│  M20-Pro机器狗 + DM-B601机械臂综合监控面板   ● 14:20:05  │  ← TopBar
├──────────────────────────────────┬──────────────────────┤
│ 机器狗前置摄像头      ●  RGB/深度 │                      │
│ ┌──────────────────────────────┐ │  M20-Pro机器狗状态    │
│ │                              │ │  ┌──────────────────┐│
│ │      实时视频画面             │ │  │ 移动(姿态调整)   ││  ← DogStatePanel
│ │                              │ │  └──────────────────┘│
│ └──────────────────────────────┘ │  趴→站→导航→移动     │
│ 机器狗后置摄像头      ●  RGB/深度 │  速度/坐标/电量       │
│ ┌──────────────────────────────┐ ├──────────────────────┤
│ │      实时视频画面             │ │                      │
│ └──────────────────────────────┘ │  DM-B601机械臂状态    │
│ 机械臂D435摄像头      ●  RGB/深度 │  ┌──────────────────┐│
│ ┌──────────────────────────────┐ │  │ 预抓取           ││  ← ArmStatePanel
│ │      实时视频画面             │ │  └──────────────────┘│
│ └──────────────────────────────┘ │  停止→预抓取→抓取→...│
│ 机身D455深度相机      ●  RGB/深度 │  夹爪/关节/放置点     │
│ ┌──────────────────────────────┐ │                      │
│ │      深度伪彩色画面           │ │                      │
│ └──────────────────────────────┘ │                      │
├──────────────────────────────────┴──────────────────────┤
│ [14:20:05] 识别到目标垃圾，进入移动姿态调整状态           │  ← LogPanel
│ [14:20:08] 机械臂状态切换: 停止 → 预抓取                 │
└─────────────────────────────────────────────────────────┘
```

---

## 状态机说明

### M20-Pro 机器狗

| 状态 | 颜色 | 说明 |
|------|------|------|
| 趴 | 灰色 | 初始/低功耗姿态 |
| 站 | 蓝色 | 站立待命 |
| 导航 | 黄色 | 全局路径规划与移动 |
| 移动 | 绿色 | 识别垃圾后精确对位、抓取姿态调整 |

### DM-B601 机械臂

| 状态 | 颜色 | 说明 |
|------|------|------|
| 停止 | 灰色 | 静止在初始位置 |
| 预抓取 | 天蓝 | 运动到垃圾上方预备位置 |
| 抓取 | 绿色 | 下降并闭合夹爪 |
| 保持抓取回位等待 | 浅绿 | 夹紧垃圾回到安全高度，等待移动到放置点 |
| 预放置 | 橙色 | 运动到放置点上方 |
| 放置 | 青色 | 下降并张开夹爪释放垃圾 |

---

## 深度相机注意事项

D435/D455 在作业过程中能否同时输出深度数据流，取决于后端架构和 USB 带宽：

- 如果后端使用 RealSense SDK 多管道配置，RGB 和深度可以同时输出。
- 如果底层抓取算法独占深度管道，作业期间深度流不可用，后端应将 `cameras.d435.depth_available` 设为 `false`。
- 前端已预留处理逻辑：深度不可用时可禁用"深度"切换按钮（当前按 `supportDepth` 配置控制，可扩展为动态读取 `depth_available`）。
- 机器狗前后普通 RGB 摄像头不受影响，全程可输出画面。

---

## 常见问题

### Q: 启动后视频画面是动画？
A: 默认 `USE_MOCK = true`，使用 Canvas 模拟画面。对接真实硬件后改为 `false` 即可。

### Q: 如何添加控制按钮（如下发指令）？
A: 在组件中引入 `useRobotSocket` 的 `sendCommand` 方法，调用 `sendCommand('dog_stand')` 即可。指令列表见 `docs/API.md`。

### Q: 视频流延迟高怎么办？
A: MJPEG 延迟约 200~500ms，适合调试；生产环境建议使用 `ws-jpeg`（延迟 ~100ms）或 `ws-h264`（延迟 ~50ms）。

### Q: 后端用什么框架？
A: 不限制。接口文档提供了 Python FastAPI 参考代码，也可用 Node.js、ROS2 rosbridge 等实现，只要遵循 WebSocket JSON 协议即可。

### Q: 可以在工控机/平板上全屏显示吗？
A: 可以。页面使用 flex 布局自适应，按 F11 全屏即可。窄屏下右侧状态面板会自动变为横向排列。

---

## 技术栈

- **Vue 3** (Composition API + `<script setup>`)
- **Vite 5** (开发服务器 + 构建工具)
- **原生 WebSocket** (实时通信，无额外依赖)
- **Canvas API** (视频渲染 + Mock 动画)
- **ws** (Mock WebSocket 服务器，仅开发依赖)

无 UI 组件库依赖，全部样式手写，体积小、启动快。

---

## License

MIT
