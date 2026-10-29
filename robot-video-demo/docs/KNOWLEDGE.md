# 需要哪些知识

| 知识 | 要理解的内容 | 对应文件 |
|---|---|---|
| 摄像头取流接口 | 每路分别配置 RTSP、外部发布或 M20 WebSocket；不能只看 IP | cameras.json、bridge_m20.py |
| 网络基础 | IP、端口、localhost、路由、TCP/UDP、防火墙、Tailscale 可达性 | run_demo.py、README 跨机章节 |
| 视频基础 | 分辨率、FPS、H.264、关键帧、SPS/PPS、时间戳 | mock_robot.py、bridge_m20.py |
| 协议和编码区别 | H.264 是编码；WebSocket/RTSP/WebRTC 是不同传输/通信方式 | 整体链路 |
| Python 异步 I/O | 读取 WebSocket、写进程管道、超时、资源释放 | bridge_m20.py |
| FFmpeg | 原始 H.264 输入、RTSP 输出、copy 与转码 | ffmpeg_command() |
| MediaMTX | 接收发布者、流路径、WebRTC 监听和 ICE 地址 | settings.py |
| HTML/CSS/JavaScript | video 元素、布局、fetch、错误处理 | web/ |
| WebRTC / WHEP | offer/answer、ICE、视频轨道、getStats | web/player.js |
| 排错 | 逐段验证，不把进程存活和信令成功当成视频已播放 | README、健康接口 |

## 推荐学习和操作顺序

1. 运行模拟模式，看四路解码帧数持续增加，尝试独立停止其中一路，理解端到端链路及通道隔离。
2. 阅读 cameras.json 与 settings.py：四路来源独立，源地址、发布地址和播放地址是三个不同地址。
3. 阅读 mock_robot.py：图像被编码为 H.264，然后加协议头，模拟厂家消息。
4. 阅读 bridge_m20.py 的 parse_packet、ffmpeg_command 和 relay_session。
5. 阅读 web/player.js 中 CameraPlayer：四个实例分别向各自 WHEP 发 SDP offer，收到 answer 后建立媒体连接。
6. 在真实机器狗网络测试端口，再切 hardware 模式，不同时改整条链路。
7. 本机成功后再测跨电脑/Tailscale，配置 public-host 与 UDP 媒体端口。
8. 最后复用现有 hxjm MediaMTX，把四个目标路径分别配置到 lanhu 四个播放器。

## 关键概念

**WebSocket 不是一种视频格式。**本项目收到的是带自定义头的二进制消息。浏览器 video 无法直接理解这段消息，需要协议解析和适合浏览器的播放链路。

**RTSP 和 H.264 不是同一层。**FFmpeg 可将已有 H.264 复制封装给 RTSP 发布，MediaMTX 再向浏览器提供 WebRTC；必要时才解码再编码。

**SDP 协商通，不代表媒体通。**浏览器 POST 到 WHEP 是 HTTP/TCP，视频通常通过另一个 UDP 端口传输，二者都要可达。

**视频在线应看新帧。**网页使用 getStats 中的 framesDecoded 是否增加判断画面新鲜度，不用后端进程 PID 或视频元素宽度单独判断在线。

**帧率不是延迟。**统计 25 FPS 不能证明端到端延迟很低；原协议时间戳含义未确认，本 Demo 不显示虚假的毫秒级端到端延迟。

**模拟图不是硬件摄像头。**模拟和实物走相同后半条链路，但不能用模拟验证相机驱动、厂家服务、无线网络、编码参数和并发限制。

## 每阶段通过标准

| 阶段 | 通过标准 |
|---|---|
| 模拟链路 | 四路不同测试图在运动，各自 framesDecoded 连续增加 |
| 实物取流 | 接收电脑连通端口，桥接收到符合协议的 H.264 |
| RTSP 发布 | MediaMTX 日志出现 live/camera_1 的发布者和 H.264 轨道 |
| 浏览器观看 | 实际看到镜头前动作，不只是协商成功 |
| 断流 | 超时后画面隐藏，服务恢复后可重连 |
| 跨机 | public-host 为浏览器可达地址，WHEP 和 UDP 均通 |
| 接原大屏 | 正确播放路径，无旧启动脚本抢占相同路径 |
| 四路独立性 | 停止/重连一路，其余三路仍然有新帧 |

四路彩色画面不等于多相机时间同步。D435/D455 的深度图与点云也不是普通 RGB 视频，需要单独设计可视化和数据接口。当前项目仅展示可编码为视频的画面。

这个 Demo 不需要先学习 AI、ROS 或机器人运动学。将来加目标检测时，可以保留视频链路，单独增加检测结果流和前端坐标叠加，但要处理帧时间和坐标缩放。
