# 机器狗四路视频与设备状态接口文档

版本：四路 Demo v2；核对日期：2026-10-19。对应本目录上一级的现有源码。面向服务器安装和真实前摄观看的逐步操作见 [README](../README.md)。本文约定供前端、视频采集端和设备状态适配程序对接；请求示例优先使用 Linux Bash。

## 0. 当前服务器对接速查

项目目录为 `/home/guest/hxjm-wxl/robot-video-demo`。下表使用 SSH 截图中的服务器地址 `100.127.237.7`；它不是自动探测结果，实际地址变化时应同步替换启动参数和调用地址。狗端 `192.168.126.176:8765` 是配置示例，需设备负责人确认。

| 对接对象 | 服务器跨机地址 | 用法 |
|---|---|---|
| 监控页面 | `http://100.127.237.7:8890/` | 观看电脑浏览器打开 |
| 公共配置 | `http://100.127.237.7:8890/api/config` | 获取四路配置和实际 WHEP URL |
| 进程与接收诊断 | `http://100.127.237.7:8890/api/health` | 排查源连接，不作为播放成功判据 |
| 前摄 WHEP | `http://100.127.237.7:28889/live/camera_1/whep` | POST SDP，浏览器播放器调用 |
| 前摄 WebRTC 媒体 | 服务器 UDP `28189` | 浏览器需可达 |
| 机器狗状态上报 | `http://100.127.237.7:8890/api/devices/dog/state` | POST JSON，仅实物模式 |
| 机械臂状态上报 | `http://100.127.237.7:8890/api/devices/arm/state` | POST JSON，仅实物模式 |
| 状态事件流 | `http://100.127.237.7:8890/api/telemetry/events` | GET，SSE |

这些地址要求启动器包含 `--bind 0.0.0.0 --public-host 100.127.237.7`。安装完成后，仅启用真实前摄的完整命令为：

```bash
cd /home/guest/hxjm-wxl/robot-video-demo
.venv/bin/python run_demo.py \
  --mode hardware \
  --config cameras.front-only.json \
  --robot-host 192.168.126.176 \
  --robot-port 8765 \
  --ffmpeg /usr/bin/ffmpeg \
  --mediamtx /data/nfs_storage/hxjm/mtx/mediamtx/mediamtx \
  --bind 0.0.0.0 \
  --public-host 100.127.237.7
```

当前命令复用已有 MediaMTX 二进制，启动独立进程；不是接入已有大屏的 MediaMTX 服务。Python 必须为 3.11+，依赖和替代工具路径见 README 第 2 节。项目记录验证的 MediaMTX 为 v1.12.3，服务器已有二进制为 v1.15.5，实际启动及播放兼容性需验证。

服务运行时，在另一个**服务器终端**执行下列请求；若从其他电脑调用，将 `127.0.0.1` 换为服务器可达地址：

```bash
curl --fail --silent --show-error http://127.0.0.1:8890/api/config
curl --fail --silent --show-error http://127.0.0.1:8890/api/health
curl --fail --silent --show-error http://127.0.0.1:8890/api/telemetry
curl --fail-with-body -X POST http://127.0.0.1:8890/api/devices/dog/state \
  -H 'Content-Type: application/json' -d '{"state":"standing"}'
curl --fail-with-body -X POST http://127.0.0.1:8890/api/devices/arm/state \
  -H 'Content-Type: application/json' -d '{"state":"stopped"}'
curl --no-buffer --max-time 5 http://127.0.0.1:8890/api/telemetry/events
```

三个 GET 应返回 200；POST 在 hardware 模式返回 200 和完整状态快照。SSE 持续输出 `event: telemetry`；示例使用 5 秒超时主动结束，请求正常时仍会在超时退出，curl 返回码 28 不等于 SSE 失败。手动 POST 只验证显示联动，不证明真实设备处于该状态，也不发送动作指令。

当前前摄配置仍返回四个通道，camera_2～4 的 enabled 为 false；`channel_count=4` 不是已连接相机数量。

## 1. 地址、职责与数据流

默认在同一台电脑运行：

| 服务 | 默认地址 | 调用方 |
|---|---|---|
| 网页与业务 API | `http://127.0.0.1:8890` | 浏览器、状态适配程序 |
| M20 上游前摄 | `ws://192.168.126.176:8765/front` | Python 桥接 / 诊断工具 |
| M20 上游后摄 | `ws://192.168.126.176:8765/back` | Python 桥接 / 诊断工具 |
| RTSP 发布入口 | `rtsp://127.0.0.1:28554/live/camera_N` | FFmpeg / 外部采集端 |
| WHEP 播放入口 | `http://127.0.0.1:28889/live/camera_N/whep` | 浏览器播放器 |
| WebRTC 媒体端口 | UDP 28189 | 浏览器与 MediaMTX |

N 为 1～4。上游地址是设备示例，须向设备负责人确认。业务 API 与 WHEP 不在同一端口；RTSP 和 WebSocket 地址不能直接填入 HTML video.src 播放。

```text
视频：设备 WebSocket → bridge_m20.py → FFmpeg RTSP/TCP → MediaMTX → WebRTC → 浏览器
状态：设备 SDK/ROS → 设备侧适配程序 → HTTP POST → telemetry.py → SSE → 浏览器
```

设备负责人提供摄像头服务、设备状态回调及真实枚举；本项目提供通用接收接口。视频传输不包含机器狗/机械臂状态机消息，HTTP 状态上报也不是动作控制接口。

## 2. 启动配置约定

### 2.1 run_demo.py 参数

| 参数 | 默认 | 含义 |
|---|---|---|
| --mode | simulated | simulated / hardware |
| --config | 项目目录 cameras.json | 四路 JSON 配置；相对路径按当前工作目录解析 |
| --robot-host | 192.168.126.176 | 生成 M20 源地址的设备主机 |
| --robot-port | 8765 | M20 源端口 |
| --fps | 25 | M20 无容器 H.264 的假设帧率；模拟模式的生成帧率 |
| --codec | copy | copy 保留编码；h264 为 M20 桥接转码 |
| --bind | 127.0.0.1 | 仅可为 127.0.0.1 / 0.0.0.0 |
| --public-host | 127.0.0.1 | 浏览器可达的后端地址，用于 WHEP 地址及 ICE 候选 |
| --web-port | 8890 | HTTP/SSE |
| --rtsp-port | 28554 | RTSP/TCP |
| --whep-port | 28889 | WHEP HTTP |
| --ice-port | 28189 | WebRTC UDP |
| --mock-port | 28765 | 模拟源 WebSocket，仅模拟模式使用 |
| --ffmpeg | 自动查找 | FFmpeg 可执行文件完整路径 |
| --mediamtx | 自动查找 | MediaMTX 可执行文件完整路径 |

主机参数为 IPv4 或主机名，不含协议、端口、路径；本启动器不接受 IPv6。端口范围 1～65535，五个服务端口号不能重复；全局 fps 为整数 1～60。工具优先使用显式路径，再查本项目 .runtime 和系统 PATH。

启动器自行创建 MediaMTX，不能当作接入已有 hxjm MediaMTX 的启动命令。若需复用已有服务，应单独配置桥接，并确认目标路径和端口，见第 4 节。

### 2.2 cameras.json 结构

```json
{
  "cameras": [
    {"id":"camera_1","name":"机器狗 · 前摄像头","source":"m20","camera":"front","url":""},
    {"id":"camera_2","name":"机器狗 · 后摄像头","source":"m20","camera":"back","url":""},
    {"id":"camera_3","name":"机械臂 · D435 彩色画面","source":"publisher"},
    {"id":"camera_4","name":"机器狗 · D455 彩色画面","source":"publisher"}
  ]
}
```

| 字段 | 类型 / 必填 | 约束 |
|---|---|---|
| cameras | array / 是 | 恰好四项 |
| id | string / 是 | camera_1～camera_4，各一个；加载后按 id 排序 |
| name | string / 是 | 非空白，输入长度 1～80；首尾空白会去除 |
| source | string / 是 | m20 / rtsp / publisher / disabled |
| camera | string / 否 | front / back；省略为 front，仅 M20 相机编号有实际意义 |
| url | string / 否 | 省略为空；m20 为 ws/wss，rtsp 为 rtsp/rtsps |
| fps | integer / 否 | 1～60，省略继承全局 --fps |
| codec | string / 否 | copy / h264，省略继承全局 --codec |

- m20：url 为空时按 robot-host、robot-port 和 camera 拼接；显式 url 优先。路径和认证方式需匹配设备实际服务。
- rtsp：必须有包含视频路径的源地址，MediaMTX 按需拉流；本项目不为该源自动转码。
- publisher：等待外部程序发布到 live/camera_N，url 不用填写；fps/codec 不会配置外部编码器。
- disabled：不创建流路径；条目仍保留在 API 和页面中。
- simulated 模式加载并验证四项基本字段后，将所有 source（包括 disabled）替换成四路独立测试源，并统一使用全局 fps。API 中 source 此时为 simulated，不能把 simulated 写作实物配置的 source。
- 修改文件须重启；不支持通过 HTTP 写入配置，也不支持热加载。不要把摄像头凭证提交到公开仓库。

## 3. M20 上游 WebSocket 二进制协议

这是当前桥接实现所接受的格式，须与厂家服务核对，不能仅凭设备型号推断兼容性。

连接后服务连续发送二进制消息；每条消息结构：

```text
24 字节固定包头（网络大端 !8sBBHIQ） + 非空 H.264 Annex-B 字节流片段
```

| 偏移（从 0 开始） | 字段 | 长度 | 本项目约束 |
|---|---|---|---|
| 0 | magic | 8 字节 | ASCII M20H264 后接 0x00 |
| 8 | version | 1 字节 | 1 |
| 9 | camera_id | 1 字节 | front=0，back=1；须匹配所接通道 |
| 10 | flags | 2 字节 | 保留；不推测厂家语义 |
| 12 | sequence | 4 字节 | 保留；不凭未知序号语义丢弃数据 |
| 16 | timestamp | 8 字节 | 厂家单位未知，不用于计算真实端到端延迟 |
| 24 | payload | 剩余字节 | 非空 H.264 Annex-B 数据，不是 JPEG |

桥接忽略文本、短消息、错误 magic/version/camera_id 和空载荷。通过验证的 payload 按接收顺序交给 FFmpeg，不要求每条消息都对应一张完整图像。模拟源使用微秒时间戳，仅是测试实现，不代表厂家也是该单位；后两路模拟包使用 camera_id=0，不代表真实 M20 有四个原生接口。

默认连接、有效数据等待或写管道背压超时为 15 秒；失败清理当前 FFmpeg 后重连，等待时间由 2 秒递增至最多 30 秒。WebSocket 直连，不使用系统 HTTP 代理；操作系统的 Tailscale 路由仍生效。

### 接收诊断工具

在项目根目录执行，先停止正在接该设备的桥接，避免单客户端限制：

```bash
.venv/bin/python check_camera.py --host 192.168.126.176 --port 8765 --camera front --timeout 5 --json
```

也可用 --ws-url 覆盖地址。timeout 是每阶段超时，不是整个命令的总时限。成功输出结构示例，计数以实际为准：

```json
[
  {"stage":"tcp","ok":true,"detail":"TCP 端口可达，不代表视频可用。"},
  {"stage":"websocket","ok":true,"detail":"WebSocket 握手成功。"},
  {"stage":"packet","ok":true,"messages":1,"payload_bytes":16828,"detail":"收到符合 M20 包头约定的数据；仍需验证 H.264 解码及浏览器播放。"}
]
```

失败会停在第一个未通过阶段，最后一项含 ok=false、error_type、detail；WebSocket/包阶段失败还可含 messages、invalid_messages。退出码 0 为收到有效协议包，1 为诊断失败，2 为参数错误。工具不存视频，不证明 H.264 可解码，也不发送机器人动作指令。

## 4. RTSP 发布接口与外部采集

每路唯一发布目标为：

```text
rtsp://后端地址:28554/live/camera_1
rtsp://后端地址:28554/live/camera_2
rtsp://后端地址:28554/live/camera_3
rtsp://后端地址:28554/live/camera_4
```

M20 桥接采用 RTSP/TCP，默认 FFmpeg 使用 -c:v copy；codec=h264 使用 libx264、baseline、yuv420p、无 B 帧、低延迟编码。裸 H.264 没有容器时间轴，FFmpeg 按配置 fps 生成发布时间轴，不保证精确复现硬件采集时间。

MediaMTX 负责协议接入和分发，不是通用转码器。RTSP 直拉及外部 publisher 须自行提供浏览器兼容的视频编码。不要让两个发布者同时抢占同一路径。

### 外部发布测试（可复制）

此测试仅验证第三路发布入口，不是采集 D435。终端 A 在项目根目录启动：

```bash
.venv/bin/python run_demo.py --mode hardware --config cameras.json \
  --ffmpeg /usr/bin/ffmpeg \
  --mediamtx /data/nfs_storage/hxjm/mtx/mediamtx/mediamtx
```

默认第三路为 publisher。在同目录终端 B 发布测试图：

```bash
/usr/bin/ffmpeg -re -f lavfi -i 'testsrc2=size=640x360:rate=25' \
  -an -c:v libx264 -preset ultrafast -tune zerolatency \
  -pix_fmt yuv420p -profile:v baseline -bf 0 -g 50 \
  -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:28554/live/camera_3
```

第三路应显示测试图；两路 M20 不在线不影响此测试。这里终端 A 的示例默认监听服务器回环地址，仅供同机访问。观看电脑在其他机器时，应在终端 A 的启动命令追加 `--bind 0.0.0.0 --public-host 100.127.237.7`（实际地址不同需替换），再从浏览器打开 `http://100.127.237.7:8890/`。先 Ctrl+C 停止终端 B，再停止 A。

真实 RealSense/USB/ROS 接入时，以设备 SDK/ROS 图像替换测试图输入，由设备侧持续编码、发布。外部设备不能用 127.0.0.1 代表后端；需要后端 --bind 0.0.0.0，并设置 --public-host 和访问规则。

### 独立桥接到已有 MediaMTX（进阶）

以下不会启动 MediaMTX，须先有运行中的 RTSP 服务及对应可发布路径；不可与总启动器同时发布同一通道：

```bash
.venv/bin/python bridge_m20.py \
  --host 192.168.126.176 --port 8765 --camera front \
  --rtsp-url rtsp://127.0.0.1:28554/live/camera_1 \
  --ffmpeg /usr/bin/ffmpeg --fps 25 --codec copy
```

必须显式指定目标地址。独立 bridge_m20.py 保留旧版默认目标端口 18554，而本四路总启动器默认用 28554；复制示例时不要混用。已有 hxjm 的端口、发布路径须以该服务真实配置为准。

## 5. 浏览器 WHEP / WebRTC 接口

调用对象为 MediaMTX，不是 FastAPI：

| 操作 | 地址 | 请求 / 响应 |
|---|---|---|
| POST | /live/camera_N/whep，端口 28889 | application/sdp；offer → answer |
| DELETE | POST 返回 Location 指向的会话资源 | 释放播放会话 |

现有播放器流程：

1. 创建 RTCPeerConnection，添加 video recvonly。
2. 创建 SDP offer，等 ICE 候选收集完成，再 POST，Content-Type 为 application/sdp。
3. 成功返回 201，响应体是 SDP answer；如有 Location，保存其会话地址。
4. setRemoteDescription；在 ontrack 中将媒体流赋给 video.srcObject。
5. 停止或重连时关闭本地连接，并尝试 DELETE 会话资源。
6. 通过 getStats 的 framesDecoded 增长判断画面有效，而非仅凭 connectionState。

这是完整 offer 模式，没有实现 trickle ICE PATCH。四路共享 HTTP/UDP 监听端口，但各有自己的流路径、连接和会话。页面“停止”只停止该路浏览器播放，不停止后端采集或机器人摄像头。

无新解码帧约 3.5 秒会隐藏旧画面，约 12 秒重建该路连接；连接失败会重试。浏览器需支持实际源编码；H.265 等源不能假定可直接播放。默认无外部 STUN/TURN。

## 6. HTTP API 总表

下列路径位于 FastAPI 的 8890 端口，默认无需认证。请求/响应 JSON 使用 UTF-8；SSE 除外。业务 API 禁止缓存。当前关闭了 /docs、/redoc 交互文档页，以本文为准。HTTP 接口仅提供页面、配置、诊断和设备状态；视频媒体不通过这些 JSON 或 SSE 接口传输。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | / | HTML 监控页面 |
| GET | /api/config | 前端公共配置 |
| GET | /api/health | 子进程与接收阶段诊断 |
| GET | /api/telemetry | 两台设备状态快照 |
| GET | /api/telemetry/events | SSE 状态快照流 |
| POST | /api/devices/dog/state | 上报机器狗观察状态 |
| POST | /api/devices/arm/state | 上报机械臂观察状态 |

不存在启动/停止摄像头、修改配置或控制机器人动作的业务 API。

### 6.1 GET /api/config

成功 200。下例为默认四路实物配置的完整结构：

```json
{
  "mode": "hardware",
  "channel_count": 4,
  "cameras": [
    {"id":"camera_1","name":"机器狗 · 前摄像头","source":"m20","fps_assumption":25,"codec":"copy","path":"live/camera_1","whep_url":"http://127.0.0.1:28889/live/camera_1/whep","enabled":true},
    {"id":"camera_2","name":"机器狗 · 后摄像头","source":"m20","fps_assumption":25,"codec":"copy","path":"live/camera_2","whep_url":"http://127.0.0.1:28889/live/camera_2/whep","enabled":true},
    {"id":"camera_3","name":"机械臂 · D435 彩色画面","source":"publisher","fps_assumption":25,"codec":"copy","path":"live/camera_3","whep_url":"http://127.0.0.1:28889/live/camera_3/whep","enabled":true},
    {"id":"camera_4","name":"机器狗 · D455 彩色画面","source":"publisher","fps_assumption":25,"codec":"copy","path":"live/camera_4","whep_url":"http://127.0.0.1:28889/live/camera_4/whep","enabled":true}
  ]
}
```

mode 为 simulated/hardware；channel_count 固定为 4。source 在模拟时为 simulated，实物时为配置来源。enabled=false 表示禁用，不表示其他通道已经有视频。fps_assumption 是配置值，不是测得的实时帧率；codec 只对桥接编码生效。即使禁用仍返回该通道的 path/whep_url，但不创建流。

不返回上游 URL、用户名或密码。相比旧单路接口，播放器应遍历 cameras，不能读取旧的顶层 whep_url/source_url。

### 6.2 GET /api/health

成功 200。以下为只启用前摄、正在转交数据时的结构示例；PID、计数和错误以现场为准：

```json
{
  "status": "ok",
  "processes": {
    "mediamtx": {"running":true,"returncode":null,"pid":12000},
    "bridge_camera_1": {"running":true,"returncode":null,"pid":12001}
  },
  "sources": [
    {"id":"camera_1","stage":"forwarding","detail":"已收到有效协议包并交给 FFmpeg；最终播放以浏览器解码为准。","packets":100,"invalid_packets":0,"age_seconds":0.3,"error_type":null},
    {"id":"camera_2","stage":"disabled","detail":"此路已禁用。"},
    {"id":"camera_3","stage":"disabled","detail":"此路已禁用。"},
    {"id":"camera_4","stage":"disabled","detail":"此路已禁用。"}
  ]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| status | string | 当前为 ok；仅说明 HTTP 接口可响应 |
| processes | object | 本启动器创建的子进程；不是操作系统所有进程 |
| running | boolean | 子进程尚未退出 |
| returncode | integer / null | 未退出为 null，已退出为进程返回码 |
| pid | integer | 子进程 PID |
| sources | array | 各通道接收阶段 |
| id / stage / detail | string | 通道、阶段、说明；每项必有 |
| packets / invalid_packets | integer，可缺省 | 当前接收会话的有效/无效包计数；重连/错误可能重置 |
| age_seconds | number，可缺省 | 诊断文件距离本次读取的秒数，不是视频延迟 |
| error_type | string / null，可缺省 | 异常类型，不包含原始凭证或完整异常消息 |

| stage | 含义 |
|---|---|
| waiting | 等待接收程序/诊断文件 |
| connecting | 正在建立 WebSocket |
| connected | 握手完成，等待有效包 |
| forwarding | 已将符合协议的数据交给 FFmpeg |
| invalid | 消息不符合约定的 M20 协议 |
| connect_error | WebSocket 建立失败 |
| stream_error | 接收或管道转发中断 |
| stopped | 接收程序停止 |
| external | RTSP/publisher 来源，内部桥接诊断不适用 |
| disabled | 配置禁用 |
| stale | 诊断文件超过 50 秒未更新 |

模拟进程还包含 mock、bridge_camera_1～4；实物模式只为 m20 来源创建桥接。无诊断文件时可缺少计数字段。内部文件在 .runtime/logs/网页端口/camera_N.json，保存 updated_at 等内部字段，不是额外 HTTP API。页面每 2 秒读取诊断，forwarding 超过 8 秒未更新另行提示等待源恢复。

forwarding 不证明 FFmpeg 成功发布，也不证明浏览器解码；external 也不证明外部设备在线。健康响应不以视频异常自动改成 HTTP 500。

## 7. 设备实时状态接口

<a id="设备实时状态接口"></a>

以下约定适用于 GET /api/telemetry、SSE 和两个 POST 的成功响应。

### 7.1 状态码

| device | state | 页面显示及含义 |
|---|---|---|
| dog | lying | 趴 |
| dog | standing | 站 |
| dog | navigating | 导航 |
| dog | adjusting | 移动：扫描到垃圾后，相对目标调整最终抓取位置和姿态 |
| arm | stopped | 停止；不等于急停、断电或安全锁定 |
| arm | pre_grasp | 预抓取 |
| arm | grasping | 抓取 |
| arm | holding_return | 保持抓取并回到初始位置等待；一个组合状态，不据此证明已回位 |
| arm | pre_place | 预放置 |
| arm | placing | 放置 |
| dog / arm | unknown | 仍有上报，但实际状态未知，页面不高亮具体动作 |

这些是本项目的通用码，不是厂家 SDK 原始枚举。后端不强制状态转换次序，也不执行动作。

### 7.2 POST /api/devices/{device}/state

设备侧适配程序调用，仅 hardware 模式接受。device 为 dog 或 arm。

请求头 Content-Type: application/json；请求体**只允许 state 字段**，值必须为 1～40 字符的字符串，且属于对应设备状态集合：

```json
{"state":"adjusting"}
```

成功 200：返回第 7.3 节所述的**两台设备完整状态快照**，不是简单的 success 布尔值。

Windows PowerShell 手动测试（服务须运行于实物模式）：

```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8890/api/devices/dog/state' -ContentType 'application/json' -Body '{"state":"adjusting"}'
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8890/api/devices/arm/state' -ContentType 'application/json' -Body '{"state":"holding_return"}'
```

Linux 设备侧测试：

```bash
curl -i -X POST http://127.0.0.1:8890/api/devices/dog/state -H 'Content-Type: application/json' -d '{"state":"standing"}'
```

跨机时把 127.0.0.1 换为后端实际可达地址。手动测试会更新显示，但不是实物状态验证。

| HTTP 状态 | 条件 |
|---|---|
| 200 | 状态已接收，返回完整快照 |
| 404 | device 不是 dog/arm |
| 409 | 模拟模式拒绝实物状态上报 |
| 422 | 状态不属于该设备，或请求体缺字段、类型错误、多余字段、JSON 无效 |

业务错误示例：

```json
{"detail":"该设备不支持此状态码"}
```

请求结构校验错误由 FastAPI 返回 detail 数组，各项含 type、loc、msg 等字段；不要假定 detail 永远是字符串。请求体先校验，因此同时存在多种问题时不保证按表格顺序报错。错误上报不更新已有设备状态。

设备侧 Python 调用示例，放入真实 SDK/ROS 回调适配程序中；不是可自动识别设备状态的采集程序：

```python
import json
from urllib.request import Request, urlopen

def report_state(base_url, device, state):
    body = json.dumps({"state": state}).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}/api/devices/{device}/state",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=2) as response:
        return json.load(response)

# SDK/ROS 回调收到真实状态后：
# report_state("http://后端IP:8890", "dog", 映射后的状态码)
```

建议每秒提供一次新鲜状态；重复相同状态会刷新心跳，但不增加历史。设备失联时停止重发缓存值。当前按后端接收顺序覆盖，没有 source_timestamp、sequence、幂等键或去重；适配端应顺序发送，丢弃重连前积压的旧状态。dog 和 arm 独立更新。

### 7.3 GET /api/telemetry

成功 200，返回 JSON 快照。

| 顶层字段 | 类型 | 说明 |
|---|---|---|
| mode | string | simulated / hardware |
| server_time | string | 后端 UTC ISO 8601 时间，毫秒精度 |
| stale_after_seconds | number | 当前为 5 |
| devices | array | dog、arm 两项，顺序固定 |

每个设备字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id / name | string | 设备标识、显示名称 |
| states | array | 可显示的已知状态定义，每项 code/label/description；不含 unknown |
| connection | string | waiting 从未上报；online 新鲜；stale 已过期 |
| reported_state | string / null | 最近收到的状态，过期仍保留供参考 |
| reported_label | string | 最近上报的中文标签，无上报时为“未知” |
| current_state | string / null | 仅 online 时等于上报状态；waiting/stale 为 null |
| received_at | string / null | 后端收到最近上报的 UTC 时间，不是设备采集时间 |
| age_seconds | number / null | 距离接收的时间；按单调时钟计算，保留三位小数 |
| history | array | 最近最多 6 次状态变化，新到旧，每项 state/label/received_at |

hardware 模式刚启动时的完整示例（server_time 为示例值）：

```json
{
  "mode": "hardware",
  "server_time": "2026-10-19T01:00:00.000+00:00",
  "stale_after_seconds": 5.0,
  "devices": [
    {
      "id": "dog",
      "name": "M20 Pro 机器狗",
      "states": [
        {"code":"lying","label":"趴","description":"机器狗处于趴下姿态。"},
        {"code":"standing","label":"站","description":"机器狗处于站立姿态。"},
        {"code":"navigating","label":"导航","description":"机器狗正在执行导航任务。"},
        {"code":"adjusting","label":"移动","description":"扫描到垃圾后，相对于目标垃圾调整最终抓取位置和姿态。"}
      ],
      "connection": "waiting",
      "reported_state": null,
      "reported_label": "未知",
      "current_state": null,
      "received_at": null,
      "age_seconds": null,
      "history": []
    },
    {
      "id": "arm",
      "name": "DM-B601 机械臂",
      "states": [
        {"code":"stopped","label":"停止","description":"机械臂状态机上报停止；此状态不等同于急停或断电。"},
        {"code":"pre_grasp","label":"预抓取","description":"机械臂进入抓取前的准备阶段。"},
        {"code":"grasping","label":"抓取","description":"机械臂正在执行抓取动作。"},
        {"code":"holding_return","label":"保持抓取并回到初始位置等待","description":"保持抓取，回到初始位置并等待下一步任务；是否已回位须由设备另行确认。"},
        {"code":"pre_place","label":"预放置","description":"机械臂进入放置前的准备阶段。"},
        {"code":"placing","label":"放置","description":"机械臂正在执行放置动作。"}
      ],
      "connection": "waiting",
      "reported_state": null,
      "reported_label": "未知",
      "current_state": null,
      "received_at": null,
      "age_seconds": null,
      "history": []
    }
  ]
}
```

最后上报满 5 秒时 connection=stale，current_state=null，不应再高亮上一次动作。上报 unknown 时 connection 可以 online，current_state 为 unknown，但不高亮具体动作。历史与最新状态仅存内存，重启丢失。

模拟模式每秒生成演示心跳，约每 4 秒切换步骤，拒绝外部状态更新以避免混用。实物模式不会生成演示心跳。

### 7.4 GET /api/telemetry/events（SSE）

响应 Content-Type: text/event-stream，每秒一条名为 telemetry 的事件。data 是与 GET /api/telemetry 相同的完整 JSON 快照，而非增量；每条事件以空行结束。

浏览器接收示例：

```javascript
const events = new EventSource('/api/telemetry/events');
events.addEventListener('telemetry', event => {
  const snapshot = JSON.parse(event.data);
  // 用 snapshot.devices 更新各设备；按 connection 判断是否可高亮。
  console.log(snapshot);
});
events.onerror = () => {
  // 清除动作高亮，显示连接中断；EventSource 会自动尝试重连。
};
// 页面销毁时：events.close();
```

当前没有 event id、历史重放或持久事件队列；慢客户端获取后续最新快照，不保证收到每一次快速转换。代理需关闭缓冲、缓存，允许长连接；后端已发送 X-Accel-Buffering: no 和 Cache-Control: no-store。

本项目页面在 SSE 断开或连续约 3.5 秒无快照时会清除高亮；这是前端与后端的连接故障，与单个设备 5 秒无上报的 stale 不同。

## 8. 网络部署与验收

| 条件 | 应确认 |
|---|---|
| 本机默认模式 | 页面、WHEP、RTSP 只监听回环地址 |
| 跨机模式 | --bind 0.0.0.0，--public-host 填浏览器可达的后端地址 |
| 摄像头输入 | 后端到 M20 TCP 8765 可达，WebSocket 路径和协议正确 |
| 浏览器播放 | 后端 TCP 8890、TCP 28889、UDP 28189 可达 |
| 外部发布 | 采集端到后端 TCP 28554 可达 |
| Tailscale | 节点授权、ACL、狗端地址或子网路由均已准备 |
| HTTPS 页面 | WHEP 也须 HTTPS，不能混合不安全内容；当前代码地址生成及 CSP 需配套调整 |

默认允许 WHEP 跨域来源 *，但没有配置流发布/播放认证；HTTP 状态接口也无鉴权。仅用于可信网络联调。生产部署需用户/来源校验、HTTPS、访问范围限制，并按拓扑配置 ICE、必要时 STUN/TURN。只配置一个网站反向代理或 SSH 转发网页端口，不保证视频媒体可达。

建议按以下顺序验收：

1. 四路模拟播放、在线计数和各路停止/重连正常。
2. 停止模拟，狗端 TCP → WebSocket → 协议包诊断通过。
3. 仅前摄实物播放，确认场景确实随设备变化。
4. 按实际能力增加后摄及外接相机；无法供流的通道明确禁用/等待。
5. 实物模式手动状态 POST 成功，5 秒无上报变 stale。
6. 设备 SDK/ROS 替换手动上报，确认映射、心跳和设备失联行为。
7. 最后验证跨机浏览器、Tailscale 与实际网络中断恢复。

尚待设备负责人提供：真实视频协议与鉴权、并发上限和帧率、RealSense/ROS 采集方式、M20 与 DM-B601 状态回调及枚举。本项目的软件模拟验证不等于上述硬件均已兼容或已验收。

## 9. 调用错误与责任边界

| 现象 | 检查位置 |
|---|---|
| POST 返回 404 | device 只能填 dog 或 arm；确认路径拼写 |
| POST 返回 409 | 当前为 simulated；停止后以 hardware 重新启动 |
| POST 返回 422 | 仅允许 state 字段，值需匹配本设备状态枚举；检查 JSON 和字段类型 |
| curl 连接失败 | 确认 HTTP 服务存活，地址、端口、路由正确 |
| /api/health 返回 200，但无视频 | 查看 sources 阶段、FFmpeg/MediaMTX 日志和浏览器实际解码；该 API 不验证完整媒体链路 |
| WHEP 请求失败 | 浏览器网络面板核对 URL、SDP、源就绪状态和 H.264 协商；WHEP 错误由 MediaMTX 返回，不遵循 FastAPI detail 格式 |
| WHEP 成功但无新帧 | 检查 UDP 28189、ICE 候选地址、源关键帧和浏览器编解码能力 |
| 状态 POST 成功后高亮消失 | 5 秒无新上报按设计过期；设备适配程序需持续上报新鲜状态 |

来源诊断文件和生成的 MediaMTX 配置位于 `.runtime/`，属于内部运行产物，不是稳定的外部接口。默认日志目录 `.runtime/logs/8890/` 随网页端口变化；同一端口再次启动会重写进程日志。接口没有配置热更新、摄像头启停、录像、历史状态持久化或机器人动作控制能力。

本轮按现有源码更新接口文档和 Linux 示例，未启动服务或执行实物调用。部署步骤和现场排错以 README 为入口，历史软件验证范围见 [VALIDATION.md](VALIDATION.md)。

