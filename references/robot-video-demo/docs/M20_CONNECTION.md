# 按 README_frontend_zh.md 接入机械狗视频

现有视频接入链路：摄像头 RTSP → 视频服务 → WebSocket `/all` → 本服务器桥接 → MediaMTX → 浏览器 WebRTC。

`192.168.126.176:8765` 是所附客户端文档中的视频服务地址，不是原始相机 RTSP 地址。前后摄都连接 `ws://192.168.126.176:8765/all`，用包头 camera_id=0/1 分流。本项目只接收视频，不发送启动或停止巡检指令。

## 在服务器启动

```bash
cd /home/guest/hxjm-wxl/robot-video-demo
.venv/bin/python run_demo.py \
  --mode hardware \
  --config cameras.json \
  --ffmpeg /usr/bin/ffmpeg \
  --bind 0.0.0.0 \
  --public-host 192.168.109.191 \
  --web-port 18990 \
  --rtsp-port 29554 \
  --whep-port 29889 \
  --ice-port 29189 \
  --mock-port 29765
```

电脑浏览器访问 `http://192.168.109.191:18990/`。前后摄实际解码帧持续增长才表示播放成功。第三、四路为独立外部发布入口，不包含在 `/all` 中。摄像头配置中的 30 FPS 对应所附视频工具的默认值，源端改变帧率后应同步修改。

在启动终端按 Ctrl+C 停止，或在另一个服务器终端执行：

```bash
cd /home/guest/hxjm-wxl/robot-video-demo
kill -TERM "$(cat .runtime/run-demo-18990.pid)"
```

服务器出现 `no space left on device` 且 MediaMTX 日志包含 `confwatcher` 时，可能是 inotify 文件监控配额耗尽，并非磁盘已满。启动器会自动使用环境变量重新加载相同的端口和摄像头配置，不需要修改系统配额。此方式不监听 YAML 文件变化，修改摄像头配置后请重启。生成的 YAML 仍保留在 `.runtime/mediamtx-18990.yml` 供检查。

## 检查真实视频

停止本项目桥接后，在服务器分别检查两路：

```bash
.venv/bin/python check_camera.py --host 192.168.126.176 --port 8765 --camera front --timeout 8 --json
.venv/bin/python check_camera.py --host 192.168.126.176 --port 8765 --camera back --timeout 8 --json
```

工具默认使用 `/all`。TCP 和 WebSocket 通过，但 packet 失败且 messages=0，说明接口没有发送视频消息；不能通过改网页或自动启动巡检来解决。页面的“已连接但没有视频”诊断会提示检查源端 RTSP。

需要在实际运行视频服务的设备上检查上游。所附文档将其称为 Jetson；可接显示器和键盘打开终端，或由已获授权且持有登录信息的设备负责人 SSH 登录。

```bash
sudo journalctl -u m20-remote.service -n 80 --no-pager
timeout 15s ffprobe -v error -rtsp_transport tcp -show_streams rtsp://10.21.31.103:8554/video1
timeout 15s ffprobe -v error -rtsp_transport tcp -show_streams rtsp://10.21.31.103:8554/video2
```

上述 RTSP 是压缩包默认值，可能被源端环境变量 `M20_IP`、`M20_RTSP_PORT` 或启动参数 `--front-url`、`--back-url` 覆盖。需以源端实际运行参数为准。超时检查源端到相机的网络及地址；404 检查路径和相机发布服务；401 检查认证；能读出视频信息后再检查视频转发进程。

浏览器直接使用 WebCodecs 时需要 localhost 或 HTTPS；本项目使用服务器桥接后的 WebRTC，不要求将现有页面替换为压缩包里的 canvas 页面。

## 本次修改对照

| 文件 | 修改前 | 修改后 |
| --- | --- | --- |
| `settings.py`、`bridge_m20.py`、`check_camera.py` | 未显式填写 URL 时使用 `/front`、`/back` | 默认统一为文档支持的 `/all` |
| `cameras.json`、`cameras.front-only.json` | 前后摄未指定帧率，继承 25 FPS | 显式使用视频工具默认的 30 FPS；已有 `/all` 地址保留 |
| `bridge_m20.py` | 另一摄像头的包计入无效包；连接后立即转发 | 按 camera_id 正常过滤；等到关键帧才启动转发，支持关键帧标记及 IDR 检测 |
| `check_camera.py` | 另一摄像头的包也计入协议错误 | 正常忽略另一摄像头的合法数据 |
| `bridge_m20.py`、`source_diagnostics.py` | 已连接但无视频显示通用错误 | 增加“接口已连接但无视频”和“等待关键帧”的页面提示 |
| `run_demo.py`、`settings.py` | inotify 配额不足会使 MediaMTX 启动失败 | 仅在已确认的文件监控配额错误时，自动改用同等环境变量配置启动 |
| `tests/test_bridge.py`、`tests/test_demo.py` | 缺少上述协议和启动配置覆盖 | 增加分流、关键帧等待、无视频诊断、默认路径、帧率和环境变量配置检查 |
| `README.md`、`docs/INTERFACES.md`、本文 | 默认路径和包头说明过时 | 按所附文档更新，并补充启动、停止和源端排查方法 |

本次没有修改机械狗源设备上的程序、地址或巡检设置。
