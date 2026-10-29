# 机器狗视频监控 Demo：服务器操作手册

本手册对应 `/home/guest/hxjm-wxl/robot-video-demo`，用于在 Linux 服务器运行程序、在自己电脑的浏览器观看 M20 机器狗视频。按第 1～7 节顺序操作；已经完成安装的用户，下次直接执行第 7 节。

视频链路：**机器狗 WebSocket H.264 → Python 桥接 → FFmpeg RTSP/TCP → MediaMTX → WebRTC → 浏览器**。接口细节见 [接口文档](docs/INTERFACES.md)。

## 1. 确认操作位置、地址和成功目标

- **服务器终端**：VS Code Remote-SSH 连接服务器后打开的 Bash 终端。下文 Bash 命令都在这里执行。
- **观看电脑**：你自己使用浏览器的电脑。网页地址在这台电脑打开，不是输入终端。
- 建议保留两个服务器终端：终端 A 运行程序；终端 B 做 HTTP 检查。终端 A 运行时不要再输入其他命令。

| 配置 | 本手册使用的值 | 如何确认 |
|---|---|---|
| 项目目录 | `/home/guest/hxjm-wxl/robot-video-demo` | 服务器上的实际源码目录 |
| 浏览器可达的服务器 IP | `100.127.237.7` | 来自当前会话的 SSH 截图，使用前确认仍可达；可在服务器执行 `tailscale ip -4` 查询（如已安装 Tailscale） |
| 狗端视频 IP | `192.168.126.176` | 项目默认示例，须向设备负责人确认 |
| 狗端端口、前摄路径 | `8765`、`/front` | 须确认厂家视频服务已启动 |

如果地址不同，替换后文所有对应 IP。`--public-host` 是**服务器地址**；`--robot-host` 是**狗端地址**，不能混用。主机参数不带 `http://`、端口或路径。

最终成功标志：网页标记为“实物”，第一路出现真实前摄画面；镜头前移动物体，页面同步变化，实际解码帧数持续增长。单纯看到网页、进程运行或 `forwarding` 都不足以证明视频播放成功。

## 2. 准备 Python 和视频工具（首次执行）

### 2.1 本服务器已核查的环境

核查日期：2026-10-19；以下为当时的环境快照，后续可能变化。

| 环境 / 工具 | 已核查状态 | 本项目处理方式 |
|---|---|---|
| `/home/guest/anaconda3/bin/python3` | Python 3.12.7，有 pip、venv、ensurepip | 复用解释器，创建项目 `.venv` |
| 原大屏 `deepsort` / `reid` 环境 | Python 3.9 / 3.10 | 保留原环境；本项目诊断工具需要 Python 3.11+ |
| 本项目 `.venv` | 核查时未创建 | 按下一节创建 |
| FastAPI、Uvicorn、WebSockets | 默认 Python 中未安装 | 从 `requirements.txt` 安装 |
| `/usr/bin/ffmpeg` | 4.4.2，支持 RTSP 输出和 libx264 | 直接使用 |
| `/data/nfs_storage/hxjm/mtx/mediamtx/mediamtx` | v1.15.5，可执行 | 显式指定路径复用二进制 |

不需要重新安装 Python、Node.js、数据库或 CUDA。观看狗端已有视频也不需要在服务器安装 RealSense SDK。项目环境只安装自身依赖，不修改原大屏算法环境。

### 2.2 创建环境并安装依赖

在终端 A 执行：

```bash
cd /home/guest/hxjm-wxl/robot-video-demo
/home/guest/anaconda3/bin/python3 --version
/home/guest/anaconda3/bin/python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
```

成功标志：Python 为 3.11 或更高，pip 安装没有错误，最后显示 `No broken requirements found`。下载失败先检查服务器访问 PyPI 的网络，再重试 pip 安装命令。

运行依赖固定为 `fastapi==0.115.12`、`uvicorn==0.34.2`、`websockets==15.0.1`，间接依赖由 pip 自动安装。`requirements-dev.txt` 中的 pytest、httpx 仅用于开发测试，观看视频无需安装。

继续检查：

```bash
.venv/bin/python -c 'import sys, fastapi, uvicorn, websockets; from websockets.asyncio.client import connect; print(sys.executable); print("Python dependencies OK")'
/usr/bin/ffmpeg -hide_banner -version
/usr/bin/ffmpeg -hide_banner -encoders 2>/dev/null | rg libx264
/data/nfs_storage/hxjm/mtx/mediamtx/mediamtx --version
```

应看到项目 `.venv` 解释器、`Python dependencies OK`、FFmpeg 版本、libx264 编码器和 MediaMTX 版本。没有 `rg` 时，编码器检查可改用 `grep libx264`。

如果是在另一台服务器，需使用其 Python 3.11+ 路径，并安装 FFmpeg。Ubuntu 缺少系统工具时，可由有管理员权限的用户执行 `sudo apt install python3-venv ffmpeg`；系统 Python 本身也必须满足版本要求。

### 2.3 MediaMTX 版本与备用安装方式

下文主流程使用已有 v1.15.5 二进制，**会新建本 Demo 自己的 MediaMTX 进程和配置**，不会连接到原大屏的视频服务。项目旧验证记录使用 v1.12.3；本轮尚未完成服务器播放验证。

如果已有路径不存在，或者启动日志提示配置版本不兼容，可运行项目安装器下载固定 v1.12.3（需要服务器访问 GitHub）：

```bash
.venv/bin/python tools/install_tools.py
.runtime/mediamtx --version
```

然后将后文每条启动命令的 `--mediamtx /data/nfs_storage/hxjm/mtx/mediamtx/mediamtx` 替换为 `--mediamtx /home/guest/hxjm-wxl/robot-video-demo/.runtime/mediamtx`。不要覆盖原大屏的二进制或配置。

## 3. 确认观看网络和端口

| 方向 | 协议 / 默认端口 | 用途 |
|---|---|---|
| 观看电脑 → 服务器 | TCP 8890 | 网页、业务 API、状态 SSE |
| 观看电脑 → 服务器 | TCP 28889 | WHEP 视频会话协商 |
| 观看电脑 ↔ 服务器 | UDP 28189 | WebRTC 视频媒体 |
| 服务器 → 机器狗 | TCP 8765 | 上游 WebSocket 视频 |
| 本机 FFmpeg → 本机 MediaMTX | TCP 28554 | RTSP 发布 |
| 本机模拟源 → 本机桥接 | TCP 28765 | 仅模拟模式使用 |

跨机观看需路由、防火墙及 Tailscale ACL 允许对应流量。服务器能通过 SSH 访问，不代表它能访问狗端 `192.168.*` 网络；如使用 Tailscale，狗端节点或子网路由也需要配置。仅转发 8890 通常只能打开页面，视频仍可能不通。

启动前可检查端口是否已有监听：

```bash
ss -ltnp '( sport = :8890 or sport = :28554 or sport = :28889 or sport = :28765 )'
ss -lunp '( sport = :28189 )'
```

无对应监听通常表示端口可用，最终以启动器绑定结果为准。若有监听，先确认所属程序；自己的旧 Demo 在其终端按 Ctrl+C 停止。不要按进程名批量结束其他人的 Python、FFmpeg 或 MediaMTX。

## 4. 先启动四路模拟视频，验证服务器和浏览器

在终端 A 执行；若当前有旧 Demo，先在其终端按 Ctrl+C：

```bash
cd /home/guest/hxjm-wxl/robot-video-demo
.venv/bin/python run_demo.py \
  --mode simulated \
  --ffmpeg /usr/bin/ffmpeg \
  --mediamtx /data/nfs_storage/hxjm/mtx/mediamtx/mediamtx \
  --bind 0.0.0.0 \
  --public-host 100.127.237.7
```

成功启动后，终端持续运行，并显示大屏地址。现在在**自己电脑的浏览器**打开：

**http://100.127.237.7:8890/**

模拟成功标志：明确标记“模拟”，四路不同的测试视频都在变化，在线计数 4/4，解码帧数持续增长。任选一路停止、再连接，其他路应继续播放。模拟画面不是机器狗实拍。

在终端 B 执行：

```bash
curl --fail --silent --show-error http://127.0.0.1:8890/api/config | /home/guest/anaconda3/bin/python3 -m json.tool
curl --fail --silent --show-error http://127.0.0.1:8890/api/health | /home/guest/anaconda3/bin/python3 -m json.tool
```

应看到 `mode: simulated`、四路配置，以及 mediamtx、mock、四路 bridge 的进程信息。HTTP 正常但视频不正常时，按第 9 节排查，先不要切实物。

浏览器需支持 WebRTC/H.264，优先使用较新的 Chrome 或 Edge。如果提示编码不支持，需换支持 H.264 的浏览器；若提示安全上下文或 Mixed Content，见第 9 节。不能用打开 HTML 文件代替运行后端。

## 5. 停止模拟，诊断机器狗前摄

在终端 A 按 **Ctrl+C**，等命令提示符恢复，再执行：

```bash
cd /home/guest/hxjm-wxl/robot-video-demo
.venv/bin/python check_camera.py \
  --host 192.168.126.176 \
  --port 8765 \
  --camera front \
  --timeout 5 \
  --json
```

成功标志：`tcp`、`websocket`、`packet` 三阶段均为 `"ok": true`。收到协议包只证明格式符合约定，下一步仍需检验视频解码。

| 未通过阶段 | 应检查 |
|---|---|
| tcp | 狗端开机、服务器到狗的路由、实际 IP、端口和视频服务 |
| websocket | `/front` 路径、厂家鉴权、视频服务是否支持外部客户端 |
| packet | 厂家实际是否输出 24 字节 M20 包头 + H.264，前摄相机编号是否为 0 |

项目接受的源不是任意 WebSocket 图像。狗端服务必须输出本项目约定的二进制格式，见 [上游协议](docs/INTERFACES.md#3-m20-上游-websocket-二进制协议)。遥控器有画面不能证明该服务已经开放。

诊断会临时连接视频服务；不要同时运行本项目桥接。设备如限制单客户端，还需协调其他接收端。诊断通过后命令会退出，再执行下一节。

## 6. 启动真实前摄并验收

终端 A 执行：

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

刷新 **http://100.127.237.7:8890/**，依次确认：

1. 模式为“实物”，不是模拟。
2. 第一路出现真实前摄画面；镜头前移动物体，页面跟着变化。
3. 第一路“实际解码”帧数持续增长，在线计数通常为 1/4；另外三路禁用符合当前配置。
4. 设备状态面板显示“待接入”属正常：视频不自动提供机器狗或机械臂动作状态。

若有效包计数增长但没有解码画面，先查看第 9 节日志。确认是 H.264 兼容性问题后，在终端 A 按 Ctrl+C，执行以下转码命令：

```bash
cd /home/guest/hxjm-wxl/robot-video-demo
.venv/bin/python run_demo.py \
  --mode hardware \
  --config cameras.front-only.json \
  --robot-host 192.168.126.176 \
  --robot-port 8765 \
  --codec h264 \
  --ffmpeg /usr/bin/ffmpeg \
  --mediamtx /data/nfs_storage/hxjm/mtx/mediamtx/mediamtx \
  --bind 0.0.0.0 \
  --public-host 100.127.237.7
```

它会启用 libx264 转码，增加 CPU 开销；不能修复网络或包头错误。若已按第 2.3 节更换 MediaMTX 路径，这里也使用更换后的路径。

默认 `--fps 25` 只是软件假设，真实帧率需厂家确认后通过 `--fps` 修改。FPS 统计不等于端到端延迟。

## 7. 下次如何启动、如何关闭

安装只做一次。下次打开服务器终端，执行第 6 节完整命令即可，无需 `conda activate`，也无需先启动 lanhu、Java 或数据库。若换了 MediaMTX 安装路径，记得使用替换后的路径。

停止：在运行程序的终端按 Ctrl+C，等待退出。启动器会清理自己启动的桥接、FFmpeg 和 MediaMTX。关闭网页或点击“停止全部”只停止浏览器播放，后台仍在运行。当前是前台运行方式，首次联调请保持 SSH 会话和终端开启。

## 8. 前摄成功后，再扩展后摄、外接相机和状态

### 8.1 视频配置

默认 `cameras.json` 中，camera_1/2 是狗的前后摄，camera_3/4 是 D435/D455 的外部发布入口。首次前摄成功后，可按实际设备修改配置；停止服务，将启动命令的 `--config cameras.front-only.json` 改为 `--config cameras.json`，再启动。

| source | 用法 |
|---|---|
| m20 | 连接厂家 WebSocket；camera 填 front/back，url 为空时使用命令行狗端地址 |
| rtsp | 已有摄像头 RTSP 地址时填写 url，MediaMTX 按需拉流 |
| publisher | 外部采集程序将 H.264 通过 RTSP/TCP 发布到对应路径 |
| disabled | 暂不接入，通道禁用 |

配置必须保留 camera_1～camera_4 共四项。改文件后重启；如果显式填写了 m20 的 url，它会覆盖 `--robot-host`/`--robot-port` 拼接结果。可使用被 Git 忽略的 `cameras.local.json` 保存本地设备配置，并用 `--config cameras.local.json` 加载。

D435/D455 需要在 USB 所连接的主机上，用 RealSense SDK/ROS 另行采集、编码后发布；本项目没有内置该采集程序。目标分别为：

```text
rtsp://100.127.237.7:28554/live/camera_3
rtsp://100.127.237.7:28554/live/camera_4
```

外部采集端还需能访问服务器 TCP 28554。不要让两个程序同时发布同一路径。模拟模式会把四路都替换成测试源，包括配置为 disabled 的通道；只看实物必须使用 hardware。

### 8.2 状态接口测试（可选，不是观看视频的前提）

实物模式运行时，在终端 B 测试显示联动：

```bash
curl --fail-with-body -X POST http://127.0.0.1:8890/api/devices/dog/state \
  -H 'Content-Type: application/json' \
  -d '{"state":"standing"}'
curl --fail-with-body -X POST http://127.0.0.1:8890/api/devices/arm/state \
  -H 'Content-Type: application/json' \
  -d '{"state":"stopped"}'
```

成功返回两台设备状态快照，对应状态短暂高亮；5 秒无新上报会过期。此操作只更新页面显示，不会让狗站起或让机械臂停止。真实联动需 SDK/ROS 适配程序读取实际状态并持续上报，约定见 [接口文档](docs/INTERFACES.md)。

## 9. 日志和逐项排错

默认网页端口为 8890，运行时配置和日志自动生成在：

```text
.runtime/mediamtx-8890.yml
.runtime/logs/8890/mediamtx.log
.runtime/logs/8890/bridge_camera_1.log
.runtime/logs/8890/camera_1.json
.runtime/logs/8890/mock.log             # 仅模拟模式
```

服务运行时，在终端 B 查看：

```bash
cd /home/guest/hxjm-wxl/robot-video-demo
tail -n 80 .runtime/logs/8890/mediamtx.log
tail -n 80 .runtime/logs/8890/bridge_camera_1.log
curl --fail --silent --show-error http://127.0.0.1:8890/api/health | /home/guest/anaconda3/bin/python3 -m json.tool
```

| 现象 | 处理步骤 |
|---|---|
| ModuleNotFoundError | 确认用 `.venv/bin/python`，重跑第 2 节依赖安装和导入检查 |
| asyncio 没有 timeout | 使用第 2 节 Python 3.12 创建的环境；不要用旧算法解释器运行诊断 |
| 找不到 FFmpeg / MediaMTX | 核对显式路径、执行权限；MediaMTX 缺失按 2.3 安装 |
| MediaMTX 启动失败 | 查 mediamtx.log，分辨端口占用、配置不兼容或其他启动错误 |
| Address already in use | 检查第 3 节端口，确认旧实例；自己的旧实例在其终端 Ctrl+C |
| 浏览器打不开网页 | 先用服务器本机 curl 检查 8890，再检查浏览器所用服务器 IP、TCP 8890 和路由 |
| 网页能打开，模拟视频也没有 | 浏览器 F12 查看 WHEP 请求；核对配置中的 whep_url，检查 TCP 28889、UDP 28189、H.264 支持 |
| WHEP URL 指向 127.0.0.1 | 停止后用正确的 `--public-host` 完整重启，刷新网页 |
| 页面有四路动画，但不是真实狗 | 当前是 simulated；停止后执行第 6 节 hardware 命令 |
| connect_error / stream_error | 停止服务，按第 5 节分阶段诊断；结合桥接和 MediaMTX 日志定位 |
| invalid | 核对厂家包头、协议版本、相机编号，不能靠转码修复 |
| forwarding，但没有画面 | 只说明数据交给 FFmpeg，继续查 RTSP 发布、关键帧、编码、WHEP/ICE；编码不兼容时尝试 `--codec h264` |
| 后两路一直等待 | publisher 没有外部供流；名字叫 D435/D455 不代表已自动接上相机 |
| 视频正常，状态仍待接入 | 视频与状态是独立接口，按第 8.2 节对接上报 |

需要更换端口时，可追加 `--web-port 8891 --rtsp-port 28555 --whep-port 28890 --ice-port 28190 --mock-port 28766`。示例各端口号须互不相同且可用；网页改访问 8891，网络放行改为对应端口，日志改查 `.runtime/logs/8891/`。

当前是 HTTP Demo，无内置登录、录像和持久化；用于可信网络联调。若浏览器明确要求安全上下文，或页面经 HTTPS 代理后出现 Mixed Content，需要为网页和 WHEP 同时部署 HTTPS，并调整 `settings.py` 的 WHEP 地址生成和 `web_server.py` 的 CSP；当前没有一个命令行开关可以完成。普通网页反代也不代替 WebRTC UDP 连通。不要以忽略证书警告作为修复。

## 10. 目录用途与其他操作系统

| 文件 / 目录 | 用途 |
|---|---|
| run_demo.py | 总启动器，管理视频服务、桥接和网页后端 |
| bridge_m20.py / check_camera.py | 上游取流、RTSP 推流 / 分阶段诊断 |
| mock_robot.py | 四路 H.264 测试视频源 |
| settings.py / cameras*.json | 配置读取、流路径和 MediaMTX 配置生成 / 摄像头配置 |
| web_server.py | FastAPI 页面、API、SSE |
| telemetry.py / source_diagnostics.py | 设备状态和过期判断 / 视频接收阶段诊断 |
| web/ | HTML、CSS、WebRTC 播放器和状态展示 |
| docs/ | [接口](docs/INTERFACES.md)、[原理教程](docs/FROM-ZERO.md)、[基础知识](docs/KNOWLEDGE.md)、[验证记录](docs/VALIDATION.md)及截图 |
| tools/ | 工具下载、源码打包、浏览器验证 |
| tests/ | Python 自动化测试 |
| .vscode/ | F5 调试配置和推荐扩展 |
| .venv/ / .runtime/ / artifacts/ | 本地环境 / 工具、配置与日志 / 验证产物，不提交 Git |

Windows 在本机独立运行时，安装 Python 3.11+ 后可依次使用 `setup_windows.cmd`、`run_simulated.cmd`、`check_camera.cmd`、`run_hardware.cmd`，本机浏览器访问 `http://127.0.0.1:8890/`。`run_hardware.cmd` 默认只接前摄；Linux 不执行这些 cmd，也不使用 Windows 的 `.venv` 或 exe。VS Code 的原 F5 配置默认本机回环地址，服务器跨机观看请使用本手册命令。

开发者可选执行已有测试：

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests -q
```

源码打包：`.venv/bin/python tools/package_demo.py`，输出上一级 `robot-camera-complete.zip`，不包含运行环境、二进制和日志。

本手册按源码、依赖清单及本服务器工具检查编写。本轮仅更新文档，尚未安装项目环境、启动视频服务或验收真实 M20、D435/D455、DM-B601；已有模拟验证见 docs/VALIDATION.md。现场能否成功显示，还需按上述步骤确认设备协议、网络和浏览器解码。
