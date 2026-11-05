# 从零把 M20 机器狗摄像头显示到网页

本手册的默认部署：项目运行在你的 Windows 电脑，浏览器也在同一台电脑；机器狗只提供视频。先验证模拟，再接前摄像头，最后扩展到四路。所有终端命令都在包含 run_demo.py 的项目根目录执行，除非明确说明在机器狗或服务器执行。

## 1. 这套项目使用什么技术

```text
M20 摄像头 → 厂家视频服务
                  │ WebSocket 二进制：24 字节头 + H.264
                  ▼
            bridge_m20.py（你的电脑）
                  │ 校验 magic/version/camera_id，去掉头
                  ▼
            FFmpeg（你的电脑）
                  │ RTSP 发布，TCP 传输；默认不重新编码
                  ▼
            MediaMTX（你的电脑）
                  │ WHEP 协商 + WebRTC 媒体
                  ▼
            浏览器 video（HTML/CSS/原生 JavaScript）

FastAPI：提供网页、配置、进程/源诊断以及设备状态 SSE。
```

H.264 是视频编码；WebSocket、RTSP、WebRTC 是不同段的通信协议。FFmpeg 负责把已编码数据送入 RTSP 发布链路；MediaMTX 负责接收和分发；浏览器通过 WebRTC 接收。RTSP 通常不能直接放进 video 的 src。本项目没有用逐帧 JPEG、RTMP/FLV、HLS，也无需 Node.js 来运行网页。

默认 codec=copy 尽量保留原始 H.264，节省 CPU；若厂家编码与浏览器不兼容，可通过 `--codec h264` 让 FFmpeg 重编码为 H.264 baseline/yuv420p/无 B 帧。它不能修复网络不通或错误的视频协议。不保证固定毫秒延迟，也不做相机同步。

## 2. 准备什么

- Windows 10/11 电脑、Python 3.12、Edge/Chrome；初次安装需能访问 PyPI/GitHub。
- 解压完整项目，保持 web/、tools/、docs/ 和 Python 源码在同一个目录；ZIP 不含虚拟环境和可执行工具。
- 机器狗实际 IP、视频服务端口/路径及服务启动方法。开机或遥控器有画面不代表外部服务已开放。
- 电脑与机器狗网络互通；初次建议同一现场。实际网络连接方式以厂家说明为准。

厂家需确认：`ws://192.168.126.176:8765/front`、`/back` 是否实际可用；二进制格式是否为 `!8sBBHIQ` 的 24 字节头加 H.264 Annex-B；是否允许遥控器和外部客户端并发。当前代码按你提供的接收客户端约定实现，不是所有机器狗通用 SDK。

## 3. Windows 第一次安装

双击 `setup_windows.cmd`，它会在项目内创建 `.venv`，安装 Python 依赖并下载校验工具；不修改系统 PATH。装好后窗口显示 Setup complete。若没有 Python，请从 python.org 安装 Python 3.12（启用 Python Launcher），再运行。

也可在项目文件夹空白处右键“在终端中打开”，用 PowerShell 逐条执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tools/install_tools.py
```

下载失败时按 README 的官方来源手动准备 `.runtime/mediamtx.exe` 与 `.runtime/ffmpeg.exe`。不要解压后直接双击 index.html，那样没有后台和视频服务。

## 4. 不接实物先验证模拟视频

双击 `run_simulated.cmd`，或 PowerShell 执行：

```powershell
.\.venv\Scripts\python.exe run_demo.py --mode simulated
```

保持窗口运行，浏览器打开 http://127.0.0.1:8890/。四个不同颜色的测试视频会运动，页面应显示 4/4，各路已解码帧不断增加；设备状态标记模拟。可独立停止和重连一路，其他三路应继续播放。

这个步骤会真实经过 WebSocket → FFmpeg → RTSP → MediaMTX → WebRTC；不是仅显示图片。验证完成，到启动窗口按 Ctrl+C 停止，再进行下一步。不要同时启动两套默认端口相同的实例。

## 5. 测试机器狗，不启动播放器

机器狗按厂家要求开机并启动视频服务。电脑连接到厂家指定网络。在项目 PowerShell 执行（示例 IP 需以实际值为准）：

```powershell
Test-NetConnection 192.168.126.176 -Port 8765
.\.venv\Scripts\python.exe check_camera.py --host 192.168.126.176 --port 8765 --camera front
```

也可双击 `check_camera.cmd` 检查默认地址。诊断依次验证 TCP、WebSocket 握手、有效 M20 包，默认每阶段 5 秒超时，不发送设备控制指令，不保存画面。成功收到协议包也不代表 H.264 一定可解码，下一步仍需真实播放验收。

| 失败阶段 | 检查内容 |
|---|---|
| tcp | 实际 IP、开机、Wi-Fi/网线、路由、防火墙、视频端口是否监听 |
| websocket | 厂家路径是否 /front、认证/服务实现是否正确、是否允许外部连接 |
| packet：没有消息 | 视频源是否启动、是否有客户端限制或厂家要求的订阅步骤 |
| packet：消息不合法 | magic、版本、相机编号或格式与现有协议不一致 |

如果使用 Tailscale，要让执行项目的电脑/服务器能访问相机，单独装在你的电脑上不一定能访问远端 192.168.* 私有地址。需设备侧 Tailscale 节点或正确的子网路由，且检查网段重叠。不要通过关闭整个防火墙来排错。

诊断会短暂占用一个视频连接。若厂家只允许一个客户端，先关闭遥控器之外的测试接收器/本项目桥接，测试结束再启动项目；是否可中断遥控器画面要按现场要求决定。

## 6. 接入真实前摄像头

双击 `run_hardware.cmd`，它默认使用 cameras.front-only.json，只接前摄像头，其他三个窗口禁用。默认机器狗地址为 192.168.126.176:8765。需要改地址时，用项目 PowerShell：

```powershell
.\run_hardware.cmd --robot-host 192.168.126.176 --robot-port 8765
```

等价 Python 命令：

```powershell
.\.venv\Scripts\python.exe run_demo.py --mode hardware --config cameras.front-only.json --robot-host 192.168.126.176 --robot-port 8765
```

打开 http://127.0.0.1:8890/，确认标记“实物”。镜头前移动物体，网页应跟随变化，已解码帧持续增长；第一路在线即可，不要求 4/4。卡片下方新增接收诊断，分别显示正在握手、等待包、协议不符或已转发给 FFmpeg。

单路配置 url 留空时，使用命令行 robot-host/robot-port 拼接地址。若填写了 url，它优先于命令行 host/port；修改地址后必须重启后台。启动终端会打印代码目录和摄像头配置绝对路径，避免启动了不同副本。

127.0.0.1 是本机网页服务；192.168.126.176 是机器狗。浏览器和服务在同一台电脑时，不要把 public-host 改成机器狗 IP。

## 7. 扩展四路

停止单路实例后，启动读取 cameras.json 的四路版：

```powershell
.\.venv\Scripts\python.exe run_demo.py --mode hardware --config cameras.json --robot-host 192.168.126.176
```

前后两路 source=m20、camera=front/back，分别读 /front 和 /back。D435/D455 默认 source=publisher，需要在它们 USB 连接的主机上用 RealSense SDK/ROS 采集 RGB，编码为兼容 H.264 后发布到指定路径；仅改相机名字不会打开硬件。如果已有 RTSP 地址，把 source 改为 rtsp 并填 url，MediaMTX 会按需拉流。

本项目没有厂家 RealSense 序列号/安装位置/SDK 环境，不包含能直接用于未知设备的 USB 驱动适配器。不默认支持深度图、点云、四路并发或硬件时间同步。

## 8. 服务器运行，另一台电脑观看

先在真正运行项目的服务器测试机器狗连接。项目日志位于该服务器；你本机端口能通不证明服务器能通。Ubuntu 示例，在包含 run_demo.py 的目录执行：

```bash
sudo apt install python3-venv ffmpeg
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python tools/install_tools.py
.venv/bin/python check_camera.py --host 192.168.126.176 --port 8765
```

先运行模拟验证环境，Ctrl+C 后，再用服务器实际局域网/Tailscale IPv4 替换下面的示例 100.100.100.100：

```bash
.venv/bin/python run_demo.py --mode hardware --config cameras.front-only.json --robot-host 192.168.126.176 --bind 0.0.0.0 --public-host 100.100.100.100
```

浏览器打开 http://100.100.100.100:8890/。当前演示使用 HTTP，部分浏览器在非 localhost 非安全上下文中可能限制 WebRTC；若提示缺少安全上下文，要配置 HTTPS/WHEP HTTPS（见接口文档边界），不能通过忽略证书警告解决。

| 默认端口 | 用途 | 谁需要访问 |
|---|---|---|
| 机器狗 TCP 8765 | WebSocket 摄像头服务 | 运行桥接的电脑/服务器访问机器狗 |
| 后端 TCP 8890 | 网页、配置、SSE 状态 API | 浏览器，或上报状态的桥接程序 |
| MediaMTX TCP 28889 | WHEP 连接协商 | 浏览器 |
| MediaMTX UDP 28189 | WebRTC 媒体 | 浏览器 |
| MediaMTX TCP 28554 | RTSP 发布/拉流 | 同机 FFmpeg 或外部发布者 |
| 模拟 TCP 28765 | 模拟 WebSocket | 同机模拟桥接 |

端口都可用 --web-port/--rtsp-port/--whep-port/--ice-port/--mock-port 调整，以免与 hxjm 和其他人冲突。仅 SSH 转发 8890 不一定能打通 WHEP 和 UDP 视频；建议首次用同机浏览器，通过后再规划跨机网络。RTSP TCP 端口不需要为了浏览器观看而对所有外部机器开放。

## 9. 状态信息、接口和现有大屏

dog/arm 状态通过独立 HTTP 上报，前端用 SSE 每秒接收；不是从视频推断。实物模式没接状态源时显示待接入，5 秒无上报显示过期。具体见 INTERFACES.md，厂家 SDK/ROS 到通用状态码的映射仍需提供真实协议后实现。

复用到现有前端：沿用 web/player.js 的 WHEP 播放逻辑，在你的组件中创建 video、RTCPeerConnection、接收远端 track 赋给 video.srcObject；销毁时关闭连接并 DELETE WHEP 会话。现有播放器依赖本项目 HTML 模板，不能只复制脚本就指望任意页面自动出现窗口。也可以保留本项目作为独立监控页，通过链接打开。

## 10. 没有画面时的检查顺序

1. 网页打不开：检查后台启动窗口、8890 端口，确认没有直接双击 HTML。
2. 看到彩条：当前为 simulated 模式；实物模式不会自动回退成彩条。
3. WebSocket 不通：运行 check_camera.py，先解决相机网络和服务。
4. 有协议包无视频：检查 `.runtime/logs/8890/bridge_camera_1.log` 与 mediamtx.log，确认已向 live/camera_1 发布 H.264。有效协议包不保证编码正确。
5. 已发布但浏览器无新帧：确认 WHEP/UDP 可达和 H.264 兼容性；必要时尝试 --codec h264。浏览器 F12 控制台的 WHEP 错误也有帮助。
6. 端口占用：先确认原实例，优先到它的启动终端 Ctrl+C；不要按程序名结束所有 Python/FFmpeg，尤其多人共享服务器。

## 11. 源码从哪里读

| 文件 | 用途 |
|---|---|
| run_demo.py | 校验端口、生成 MediaMTX 配置、管理子进程、启动后端 |
| settings.py / cameras*.json | 地址、端口及各路来源 |
| bridge_m20.py | WebSocket 协议解析、FFmpeg 管道、重连 |
| check_camera.py | 分阶段摄像头诊断 |
| source_diagnostics.py | 记录接收阶段，不泄露上游地址和账号密码 |
| mock_robot.py | 四路独立测试图 H.264 编码与厂家包头模拟 |
| web_server.py | FastAPI 网页、配置、健康和状态接口 |
| telemetry.py | 设备状态存储、过期、模拟演示 |
| web/index.html / style.css | 网页结构与样式 |
| web/player.js | WHEP/WebRTC、解码统计、单路重连与源诊断展示 |
| web/telemetry.js | 实时状态面板 |
| tests/ / tools/verify_*.cjs | 后端测试与真实浏览器验证 |

默认项目用于本机和可信网络测试，没有生产鉴权、HTTPS、录像或机器人控制。发布到公网需要另行设计认证、TLS、来源限制和 ICE/TURN，不能把默认端口直接开放到互联网。
