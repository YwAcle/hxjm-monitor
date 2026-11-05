# 四路版验证记录

2026-10-19 参考大屏布局更新：网页改为深蓝色三栏，M20 Pro 状态位于左侧，DM-B601 六种状态位于右侧，中间显示四路视频。实际 Edge 验证四路模拟视频持续解码、单路停止/失败隔离/恢复、全部停止/恢复；HTTP/SSE 状态高亮、过期、断线和自动重连均通过。新布局在 1920、1735、1560、1280、800、390 像素宽度检查无横向溢出，浏览器 pageerror 为 0。截图使用明确标记的测试图，不是实物画面。此轮未重新进行实物验证或干净系统安装测试。

环境：Windows、Python 3.12、MediaMTX v1.12.3、FFmpeg 7.1、Microsoft Edge（Playwright headless）。本次验证使用软件生成的视频，未连接实际机器狗和 RealSense。

2026-10-19 完整版复验：30 项 Python 测试通过；四路完整视频链路在 Edge 中实际解码，均 640×360、约 25 FPS；单路失败隔离、恢复、全部停止/重连正常；设备状态与 SSE 断线/恢复验证通过，浏览器 pageerror 为 0。新增 check_camera.py 对实际运行的本机模拟视频源依次完成 TCP、WebSocket、协议包检查；卡片接收诊断从后端读取，四路均显示 forwarding。Windows 安装器沿用原有下载脚本，本次没有在干净系统重新联网安装工具，也没有验证实际机器狗网络和相机。

## 已验证

| 检查 | 结果 |
|---|---|
| Python 自动测试 | 30 项通过，包括原协议/四路视频/状态测试，以及诊断阶段区分、单路配置、诊断过期和 API |
| 模拟视频链路 | 四个独立 FFmpeg 编码器 → 四路 WebSocket 协议 → 四路桥接 → RTSP → MediaMTX → WebRTC → Edge 实际解码 |
| 实际解码统计 | 四路均 640×360，验收记录中四路均约 25 FPS，帧数持续增长 |
| 独立画面 | 四个画面色相、白框位置不同；对实际视频截图计算摘要，四路均不同 |
| 单路停止 | 停止 camera_3，该路释放 video.srcObject，其他三路继续解码 |
| 单路请求失败 | 仅阻断 camera_3 的 WHEP 请求，其他三路仍有新帧；恢复请求后可重新连接 |
| 连接中停止 | 在 camera_2 重新协商期间停止，再次连接后正常恢复 |
| 全部操作 | 停止全部释放四路视频，连接全部后恢复四路实际解码 |
| 混合来源模式 | 单独启动 hardware 配置测试实例：两路 m20、一条 RTSP 拉流、一条外部 publisher；四路均可在浏览器实际解码 |
| 响应式布局 | 桌面为 2×2，390px 手机为单列；1280px 与 390px 无水平溢出 |
| 浏览器错误 | 四路自动验收期间 pageerror 为 0 |
| 设备状态联动 | 单独启动实物模式网页后端，通过 HTTP 上报、SSE 到 Edge，验证机器狗“移动”和机械臂全部六种状态 |
| 状态断线与过期 | 停止上报 5 秒后取消高亮；测试代理切断实际 SSE 连接后显示状态不可用；恢复连接自动更新，无需刷新 |
| 状态来源区分 | 实物模式初始等待上报，模拟模式明确标注并自动变化；未知状态不高亮任何动作 |
| 新面板布局 | 1560px、800px、390px 无水平溢出；保持原摄像头桌面尺寸与手机单列 |

混合来源测试中的上游依然是本机软件测试图，目的是验证实物模式的配置分发、RTSP 按需拉流及外部发布通道，不能据此宣称实际摄像头已连接。

截图见 [桌面四路预览](dashboard-preview.png) 和 [手机预览](mobile-preview.png)。

## 如何复现主要测试

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
```

启动四路模拟服务后，另一个终端执行（另需 Node.js 与本机 Edge）：

```bash
npm install --no-save playwright
node tools/verify_browser.cjs
```

脚本使用真实 RTCPeerConnection，不伪造视频流和浏览器解码统计。输出 artifacts/browser-report.json，并更新 docs 中的截图。artifacts 不包含在源码 ZIP 中。

状态联动复验：保留模拟服务运行，在另一个终端从项目目录启动一个独立、没有相机进程的实物模式网页测试实例：

```bash
python -c "import uvicorn; from settings import Settings; from web_server import create_app; uvicorn.run(create_app(Settings(mode='hardware').load_cameras('cameras.json')), host='127.0.0.1', port=8891)"
```

然后执行 `node tools/verify_telemetry.cjs`，结果写入 artifacts/telemetry-browser-report.json。需使用刚启动、尚未上报过状态的 8891 实例。可用 ROBOT_TEST_URL 与 ROBOT_HARDWARE_TEST_URL 环境变量更改测试地址。该验证通过真实 HTTP 与 SSE 检查页面联动，代理主动切断 SSE 网络连接，未连接实际设备。测试结束用 Ctrl+C 停止两个服务。

## 未覆盖的硬件与部署条件

- M20 视频服务实际启动、真实 IP/端口、前后相机和遥控器并发限制。
- D435/D455 的 USB、驱动、SDK/ROS 话题、彩色采集节点和设备序列号。
- M20 Pro 与 DM-B601 的真实状态 SDK、枚举映射、设备心跳及实物动作与上报的一致性。
- 实物四路无线带宽、1080p/4K 性能、端到端延迟及多相机同步。
- 跨电脑、Tailscale 子网路由、复杂 NAT、公网鉴权与生产部署。
- 持续硬件断流及源恢复的完整现场验收。前端失帧隐藏与自动重连已实现，自动测试覆盖播放停止和单路 WHEP 失败；不等于硬件故障恢复已验证。

当前 FPS 是浏览器实际解码速率，不是端到端延迟；页面在线仅表示近期有新解码帧。每路 camera_N 的显示名称也不证明相应硬件已经接入。
