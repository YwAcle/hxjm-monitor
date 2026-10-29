# 后端接口文档

> M20-Pro机器狗 + DM-B601机械臂综合监控面板 —— 前后端通信协议说明

## 1. 通信概述

前端与后端之间有两类数据流：

| 数据流 | 协议 | 用途 |
|--------|------|------|
| 状态数据 + 控制指令 | WebSocket (JSON) | 机器狗/机械臂状态机实时推送、前端下发控制指令 |
| 视频画面 | HTTP MJPEG 或 WebSocket(二进制) | 四路摄像头实时画面传输 |

建议后端使用 Python (FastAPI + uvicorn) 或 Node.js 实现，视频流部分可对接 ROS/ROS2 话题或直接调用 RealSense SDK。

---

## 2. WebSocket 状态通道

### 2.1 连接地址

```
ws://<后端IP>:<端口>/ws/robot
```

前端配置位置：`src/config/index.js` → `REAL_WS_URL`

### 2.2 消息格式

所有 WebSocket 消息均为 JSON 文本，统一结构：

```json
{
  "type": "<消息类型>",
  "data": { ... },       // type=robot_status 时存在
  "message": "...",      // type=log 时存在
  "level": "info",       // type=log 时存在: info/warn/error/success
  "command": "...",      // type=command 时存在（前端→后端）
  "params": { ... },     // type=command 时存在（前端→后端）
  "timestamp": 1726000000000
}
```

### 2.3 后端 → 前端：状态推送 (`robot_status`)

后端应以 **10Hz~30Hz** 的频率推送完整机器人状态。

```json
{
  "type": "robot_status",
  "timestamp": 1726000000000,
  "data": {
    "dog": {
      "state": "移动",
      "velocity": 0.12,
      "target_trash": [1.2, 0.3, 0.5],
      "position": [0.45, -0.12],
      "battery": 87
    },
    "arm": {
      "state": "预抓取",
      "gripper": "open",
      "joints": [15.2, -45.8, 80.1, 10.3, -45.0, 0.5],
      "target_place": [0.5, -0.3, 0.1]
    },
    "cameras": {
      "cam_front": { "online": true, "depth_available": false },
      "cam_back":  { "online": true, "depth_available": false },
      "d435":      { "online": true, "depth_available": false },
      "d455":      { "online": true, "depth_available": false }
    }
  }
}
```

#### 字段说明

**dog（机器狗状态）**

| 字段 | 类型 | 说明 |
|------|------|------|
| `state` | string | 状态机当前状态，枚举值：`"趴"` `"站"` `"导航"` `"移动"` |
| `velocity` | float | 底盘线速度，单位 m/s |
| `target_trash` | float[3] | 识别到的目标垃圾坐标 `[x, y, z]`，单位米（机器狗基座坐标系） |
| `position` | float[2] | 机器狗当前在地图中的位置 `[x, y]`，单位米 |
| `battery` | int | 电量百分比 0~100 |

**arm（机械臂状态）**

| 字段 | 类型 | 说明 |
|------|------|------|
| `state` | string | 状态机当前状态，枚举值：`"停止"` `"预抓取"` `"抓取"` `"保持抓取回位等待"` `"预放置"` `"放置"` |
| `gripper` | string | 夹爪状态：`"open"`（张开）/ `"close"`（闭合） |
| `joints` | float[6] | 6个关节角度，单位度，顺序 J1~J6 |
| `target_place` | float[3] | 放置点坐标 `[x, y, z]`，单位米 |

**cameras（摄像头状态）**

| 字段 | 类型 | 说明 |
|------|------|------|
| `online` | bool | 摄像头是否在线 |
| `depth_available` | bool | 深度流当前是否可用（作业时底层独占可能为 false） |

### 2.4 后端 → 前端：日志推送 (`log`)

后端可主动推送日志消息，前端会显示在底部日志面板：

```json
{
  "type": "log",
  "message": "识别到目标垃圾，进入移动姿态调整状态",
  "level": "info",
  "timestamp": 1726000000000
}
```

### 2.5 前端 → 后端：控制指令 (`command`)

前端通过 WebSocket 发送控制指令：

```json
{
  "type": "command",
  "command": "dog_stand",
  "params": {},
  "timestamp": 1726000000000
}
```

#### 指令列表

| command | params | 说明 |
|---------|--------|------|
| `dog_lie` | `{}` | 机器狗趴倒 |
| `dog_stand` | `{}` | 机器狗站立 |
| `dog_navigate` | `{"x": 1.0, "y": 2.0}` | 导航到指定坐标 |
| `dog_stop` | `{}` | 机器狗急停 |
| `arm_stop` | `{}` | 机械臂停止运动 |
| `arm_home` | `{}` | 机械臂回零位 |
| `arm_grasp` | `{"x": 1.2, "y": 0.3, "z": 0.5}` | 执行抓取流程 |
| `arm_place` | `{"x": 0.5, "y": -0.3, "z": 0.1}` | 执行放置流程 |
| `gripper_open` | `{}` | 夹爪张开 |
| `gripper_close` | `{}` | 夹爪闭合 |

> 当前版本 UI 主要用于监控，控制按钮可根据需要在组件中接入 `sendCommand()`。

---

## 3. 视频流接口

### 3.1 方案一：MJPEG（最简单，推荐快速对接）

后端提供 HTTP 端点，以 `multipart/x-mixed-replace` 格式持续推送 JPEG 帧：

```
GET http://<后端IP>:<端口>/stream/<camera_id>
```

| camera_id | 摄像头 |
|-----------|--------|
| `cam_front` | 机器狗前置摄像头 |
| `cam_back` | 机器狗后置摄像头 |
| `d435` | 机械臂D435摄像头 |
| `d455` | 机身D455深度相机 |

查询参数：
- `view=rgb`（默认）：RGB 彩色画面
- `view=depth`：深度伪彩色画面（仅 D435/D455 支持）

**后端响应头示例：**
```
HTTP/1.1 200 OK
Content-Type: multipart/x-mixed-replace; boundary=frame

--frame
Content-Type: image/jpeg

<JPEG 二进制数据>
--frame
Content-Type: image/jpeg

<JPEG 二进制数据>
...
```

前端配置：将 `src/config/index.js` 中对应摄像头的 `type` 改为 `'mjpeg'`，并填写 `mjpegUrl`。

### 3.2 方案二：WebSocket JPEG 帧（低延迟）

```
ws://<后端IP>:<端口>/ws/<camera_id>?view=rgb
```

后端将每一帧编码为 JPEG 后以二进制帧推送，前端解码绘制到 Canvas。
延迟低于 MJPEG，但后端实现稍复杂。

前端配置：`type` 改为 `'ws-jpeg'`，填写 `wsUrl`。

### 3.3 方案三：WebSocket H.264（最低延迟，需额外解码）

```
ws://<后端IP>:<端口>/ws/<camera_id>?view=rgb&codec=h264
```

后端推送 H.264 裸流，前端需引入 [jsmpeg](https://github.com/phoboslab/jsmpeg) 等解码器。
适合带宽受限或需要 30fps 以上高帧率的场景。

前端配置：`type` 改为 `'ws-h264'`，并安装 jsmpeg 依赖。

### 3.4 方案四：WebRTC（生产级最低延迟）

适合正式部署，需要后端实现 WebRTC 信令服务器。当前前端预留接口，可根据需要扩展。

---

## 4. 深度相机使用注意事项

### 4.1 硬件限制

D435/D455 深度相机在工作过程中能否同时对外输出深度数据流，取决于：

1. **后端架构**：如果深度数据仅用于本地检测/点云计算，且使用了 RealSense SDK 的多进程/多管道配置，可以同时输出 RGB 和深度流。
2. **USB 带宽**：D435/D455 通过 USB3.0 连接时带宽充足；USB2.0 下可能无法同时开启 RGB+深度。
3. **驱动独占**：如果底层抓取算法独占了深度管道，则作业期间 `depth_available` 应为 `false`。

### 4.2 推荐做法

- 后端通过 `cameras.d435.depth_available` 和 `cameras.d455.depth_available` 字段实时告知前端深度流是否可用。
- 前端在深度流不可用时自动禁用"深度"切换按钮（当前代码已根据 `supportDepth` 配置处理，可扩展为根据 `depth_available` 动态禁用）。
- RGB 画面在任何状态下都应保持可用。

---

## 5. 后端参考实现（Python FastAPI 伪代码）

```python
from fastapi import FastAPI, WebSocket
from fastapi.responses import StreamingResponse
import asyncio, json, cv2

app = FastAPI()

# ===== 视频流（MJPEG）=====
async def generate_frames(cam_id: str, view: str = "rgb"):
    cap = cv2.VideoCapture(0)  # 实际替换为 RealSense / ROS 话题
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if view == "depth":
            # 伪彩色映射
            frame = cv2.applyColorMap(frame, cv2.COLORMAP_JET)
        _, buf = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n')
        await asyncio.sleep(1/30)

@app.get("/stream/{cam_id}")
async def video_feed(cam_id: str, view: str = "rgb"):
    return StreamingResponse(
        generate_frames(cam_id, view),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

# ===== WebSocket 状态通道 =====
@app.websocket("/ws/robot")
async def ws_robot(ws: WebSocket):
    await ws.accept()
    while True:
        # 实际从机器人驱动/ROS话题获取状态
        state = get_robot_state()
        await ws.send_text(json.dumps({
            "type": "robot_status",
            "data": state,
            "timestamp": int(asyncio.get_event_loop().time() * 1000)
        }))
        # 接收前端指令
        msg = await ws.receive_text()
        cmd = json.loads(msg)
        await handle_command(cmd)
        await asyncio.sleep(1/30)
```

---

## 6. 状态机流转说明

### 6.1 M20-Pro 机器狗状态机

```
趴 ──→ 站 ──→ 导航 ──→ 移动(抓取姿态调整)
                ↑                    │
                └────────────────────┘
                (放置完成后重新导航)
```

- **趴**：初始/低功耗姿态
- **站**：站立待命
- **导航**：根据垃圾位置进行全局路径规划与移动
- **移动**：到达垃圾附近后，进行精确对位和抓取姿态调整

### 6.2 DM-B601 机械臂状态机

```
停止 ──→ 预抓取 ──→ 抓取 ──→ 保持抓取回位等待 ──→ 预放置 ──→ 放置 ──→ 停止
```

- **停止**：静止在零位/初始位置
- **预抓取**：运动到垃圾上方预备位置
- **抓取**：下降并闭合夹爪
- **保持抓取回位等待**：夹紧垃圾回到安全高度，等待机器狗移动到放置点
- **预放置**：运动到放置点上方
- **放置**：下降并张开夹爪，释放垃圾

两个状态机的协同：机器狗进入"移动"状态后，机械臂开始执行"预抓取→抓取→保持抓取回位等待"；机器狗导航到放置点后，机械臂继续"预放置→放置"。
