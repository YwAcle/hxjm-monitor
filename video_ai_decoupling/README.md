# 原始视频与 AI 检测结果分离 demo

## 目标与当前范围

目标链路：

```text
MediaMTX 原始流 → 前端 WebRTC 播放
同一原始流 → 后端取帧与 AI 检测 → WebSocket JSON → 前端 Canvas
```

当前完成第五步代码接入：前端继续复用一路原始视频播放器，新增 WebSocket
检测接收、独立 AI 状态和透明 Canvas 标注；后端仍提供第四步的持续
“RTSP 取帧 → 本地模型全帧检测 → WebSocket JSON”服务，没有修改或重启。
服务生命周期内只启动一份取帧/分析任务、初始化一次模型，客户端共享结果。
第三步的单次验证入口仍可独立运行并在一次推理后退出。
后端不实例化原检测服务、不画框、不写数据库、不推流。画框仅发生在浏览器 Canvas。
第一版只叠加最新有效结果，不做帧级精确同步、视频缓存、插值或全屏叠加，
不宣称解决移动目标的框滞后。真实摄像头画面上的标注尚未通过本机浏览器验证，
具体原因和已完成的替代检查见文末第五步验证记录。
项目根目录由 `backend/config.py` 的 `__file__` 推导，不依赖服务器绝对路径。
检查时在 hxjm 仓库及其上级目录未找到 `AGENTS.md`。

## 已确认的复用接口

以下路径均相对于 hxjm 根目录。

- `python/deepsort/server.py`
  - 使用 `from deepsort import server as existing_detection`，需将 hxjm/python
    加入模块搜索路径。`detector_adapter.py` 延迟导入该模块，仅在执行检测时使用。
  - `DetectionServer.init_model_context()` 存在，是无参数静态方法；调用后才会
    加载 SAHI/YOLO 模型并返回包含 `sahi`、缓存和推理锁等字段的上下文。
  - 模型路径可由 `DEEPSORT_MODEL` 覆盖，默认是
    `python/deep_sort-master/detection/yolov5mu.pt`。
  - 模块级 `_person_boxes(result)` 存在，接收含 `object_prediction_list` 的
    SAHI 结果，筛选 person、置信度过滤并去重，返回
    `[( [x, y, width, height], score ), ...]`，坐标为像素值。
  - 导入原模块会导入 torch、cv2、SAHI 等现有依赖，但服务启动位于
    `if __name__ == "__main__"` 下。demo 只调用静态模型初始化和 `_person_boxes`，
    不实例化 `DetectionServer`，不调用 `serve()`、`process_frame()`。
  - 使用上下文中的 `sahi` 模型执行 `perform_inference()` 和
    `convert_original_predictions()`，不切片。已安装 SAHI `0.12.6` 要求 RGB，
    因而 adapter 将 OpenCV 的 BGR 帧转为 RGB；不修改原检测文件。
- `lanhu/src/components/CenterPanel/components/MonitorGrid/WebRTCPlayer/index.jsx`
  - 默认导出 `WebRTCPlayer`，参数为 `primaryUrl`、`fallbackUrl`、`onStatusChange`。
  - 状态回调接收 `(status, source)`；播放器内部通过 `buildWhepUrl` 追加 `/whep`，
    因而应传流基础 URL，而非已带 `/whep` 的地址。
  - 现有主路用于算法流、备用路用于原始流。独立页面传入 `primaryUrl=""`，
    `fallbackUrl` 取自 `VITE_ORIGINAL_VIDEO_URL`，避免算法流切换。
  - 未配置地址时不挂载播放器，显示缺少配置的提示，不发起视频请求。
  - 独立页面只 import 原组件，不修改 lanhu。Vite 的 `server.fs.allow`
    只放行 demo 前端目录和原播放器目录，`resolve.dedupe` 对 React/ReactDOM 去重。
- `scripts/start-local.sh`
  - 默认端口：RTMP `11935`、RTSP `18554`、RTP/RTCP `18000/18001`、
    HLS `18888`、WebRTC HTTP/WHEP `18889`、WebRTC ICE UDP `18189`、
    SRT `18890`、回放 `9996`、API `9997`。
  - 端口均支持对应 `MTX_*_PORT` 环境变量覆盖，并映射为 MediaMTX 启动环境变量；
    `VITE_MEDIA_PORT` 默认取 WebRTC 端口。以上是脚本默认值，非运行状态探测。
  - 脚本使用的原始流路径是 `live/camera_${camera_id}`；后续前后端须指向
    同一原始流，不能误用带算法后缀的输出流。

## 第二步运行核对

2026-10-07（Asia/Shanghai）只读检查了现有服务，未启动或停止原业务服务：

- 运行中的 MediaMTX 实际监听 RTSP TCP `18554`、WebRTC HTTP `18889`、
  ICE UDP `18189` 和 API TCP `9997`，不是仅根据脚本默认值推断。
- `GET http://127.0.0.1:9997/v3/paths/get/live/camera_1` 返回
  `name=live/camera_1`、`source.type=rtspSource`、`ready=true`、`tracks=[H264]`。
- `GET http://127.0.0.1:18889/live/camera_1/` 返回 HTTP 200。
  以上确认了本机监听和流就绪，不等同于浏览器 WebRTC 视频播放通过。
- 检查时 TCP `3010` 无监听。demo 开发/预览端口均为 `3010`，设置
  `strictPort: true`，端口被占用时直接报错，不自动切换到其他端口。
- 核对时 lanhu 已安装 React/ReactDOM `18.3.1`、Vite `5.4.21`、
  `@vitejs/plugin-react` `4.7.0`；demo 使用同样版本且依赖安装在自身目录。

## 唯一摄像头配置与启动

**唯一需要修改的文件：`/data/nfs_storage/hxjm/video_ai_decoupling/demo.env`。**
该文件只配置一项，摄像头编号格式为 `camera_` 加正整数：

```dotenv
DEMO_CAMERA_ID=camera_1
```

使用流程固定为：**修改 demo.env 的摄像头编号 → 执行 bash start_demo.sh → 打开或刷新 3010 页面**。

```bash
cd /data/nfs_storage/hxjm/video_ai_decoupling
bash start_demo.sh
```

- 页面：`http://192.168.109.191:3010/`。
- 检测 WS：`ws://192.168.109.191:8010/ws/detections`。
- 每次执行重新读取 `demo.env`，自动生成播放地址
  `http://192.168.109.191:18889/live/<摄像头编号>/` 和取帧地址
  `rtsp://127.0.0.1:18554/live/<摄像头编号>`，不需要修改第二份配置。
- 脚本通过自身位置推导 demo 根目录，也可以在任意工作目录执行
  `bash /data/nfs_storage/hxjm/video_ai_decoupling/start_demo.sh`。
- 先检查两个端口的监听进程、工作目录、实际解释器和完整启动参数；确认是本
  demo 后再核对该进程实际环境与目标摄像头。配置一致且就绪时跳过启动，
  仅摄像头/地址不匹配的 demo 服务需要重启；另一项配置一致时不动它。
  PID 文件过期时按真实监听进程判断，不仅凭 PID 文件存在判断。
  其他进程占用端口或无法确认身份时明确报错，不自动杀进程，也不先启动另一项服务。
- 启动缺失服务或切换摄像头前，只读查询现有 MediaMTX API `127.0.0.1:9997` 的
  `live/<摄像头编号>`，必须返回匹配的路径、`ready=true` 和已有轨道。
  检查和依赖预检通过后才发停止信号；目标流不存在、未就绪或 API 不可达时，
  不停止进程、不改有效前端配置，当前 demo 保持原摄像头运行。
- 重启前再次核对 cwd、可执行文件和完整命令，用绑定具体进程的 pidfd 发送
  `SIGTERM`，等待优雅退出，不使用宽泛 `pkill` 或强制杀进程。
  目标流预检通过后若发生新的启动故障，脚本报错并保留日志，不保证自动回滚。
- 配置一致但服务尚未就绪时等待检查；持续不健康会报错，
  不以重复启动或无条件重启掩盖问题。
- 需要启动时使用 `setsid` 独立后台会话和 `nohup`，关闭终端后继续运行；
  启动总锁和每服务锁避免重复启动。总锁不会继承给后台服务。
- 前端使用当前 Node `v18.20.8` 和现有 Vite。脚本将生成的视频地址和固定 WS 地址
  显式传给 Vite；调用终端里的旧 `VITE_*_URL`、`DEMO_CAMERA_ID`、`DEMO_RTSP_URL`
  不会覆盖 `demo.env`。脚本移除 `frontend/.env.local` 中旧的视频地址覆盖，
  只保留固定 WS 配置和其他无关变量；不要再通过此文件切换摄像头。
- 后端使用 `/home/guest/anaconda3/envs/deepsort/bin/python`，依赖路径是
  `.runtime/python_deps` 和 demo 根目录，使用根据编号生成的 RTSP、UDP、推理间隔 `1` 秒、
  单 Uvicorn worker、8010 端口及本地 `yolov5mu.pt` 配置与当前运行版本相同。
  不安装依赖、不下载模型；缺少 Node/Python/依赖/本地权重时明确报错。
- PID：`frontend/.run/vite.pid`、`.runtime/backend.pid`。
  日志：`frontend/.run/vite.log`、`.runtime/backend.log`，均追加写入，不覆盖旧日志。
- 前端最多等待 `30` 秒；后端最多等待 `90` 秒直到 `/health` 为 `ok`、模型初始化
  一次且已经发布当前摄像头的真实检测。前端核对实际服务返回的 Vite 视频/WS 地址，
  不只检查 HTTP 200。超时不自动终止进程，直接检查对应日志，不要反复重复启动。
- 这是按需启动脚本，不是开机启动或异常退出自动重启的守护服务；不启动 MediaMTX、
  lanhu 或原算法业务，不改变当前页面样式、视频/WS/Canvas 逻辑。

### 集中配置实际验证

- 当前文件已恢复为 `DEMO_CAMERA_ID=camera_1`，两个 demo 服务保持运行。
- 配置不变及旧终端环境变量故意设置为错误地址时，仍从 `demo.env` 生成正确地址，
  连续执行和从 `/tmp` 执行均跳过启动，不更换已就绪的 PID。
- 实际将 `demo.env` 临时改成不存在的 `camera_999999`，API 返回 404，脚本报错退出；
  前后端 PID、有效 `.env.local` 及 camera_1 的真实检测均保持不变，随后还原文件。
- 实际切换 `camera_1 → camera_2 → camera_1`：每次先确认原始流在线，
  只停止已确认的 demo 前后端；检查实际前端视频地址、后端 RTSP/摄像头、
  `/health` 和连续四条真实 WS 检测，均与目标一致，每个新后端仅初始化一次模型。
  camera_2 的四个真实帧为 `100/121/150/170`，均 `1280×720`、检测人数 `1`；
  这仅证明配置、真实取帧和检测消息正确，不替代用户浏览器的视频解码/播放验收。
  最终 camera_1 的四帧为 `134/159/184/209`，均检测到 `2` 人，真实推理耗时分别
  `15.123/18.365/15.398/17.258 ms`，最后保留 camera_1 运行。
- 原播放器、页面样式及 WS/Canvas 逻辑、后端算法/取帧模块的校验值均未变化；
  MediaMTX 原进程启动时间不变，未向 MediaMTX 或原算法业务发送信号。
- 最后用自动化浏览器刷新 `3010`，页面 AI 状态为“检测中”，仅一个业务 WS，
  连续收到 camera_1 帧 `11531/11556/11580/11605/11631`；实际视频请求为
  `http://192.168.109.191:18889/live/camera_1/whep`。该浏览器仍不支持当前 H264，
  视频尺寸为零，不能据此宣称该浏览器实播通过；用户浏览器需自行确认画面。
  最终前端 PID `3590319`、后端 PID `3590316`，均独立后台会话，后端健康为 `ok`。
- 模拟检查包括解析配置、防止执行文件内容、旧环境覆盖、目标路径/在线检查、
  无变化跳过、仅一端需要更新、双端更新、离线不变更、旧 `.env.local` 清理。
- 记录：`.runtime/camera_verification_camera_1.json`、
  `.runtime/camera_verification_camera_2.json`、`.runtime/camera_offline_validation.log`、
  `.runtime/camera_2_switch.log`、`.runtime/camera_1_restore.log`。
  模拟检查命令：`bash .runtime/check_camera_config.sh`。
  最终页面核对记录：`.runtime/camera_page_verification.json`。

### 启动基础回归验证

- `bash -n start_demo.sh` 通过；从 `/tmp` 执行和连续两次重复执行均成功。
  最初同配置的前端 PID `1604385`、后端 PID `2749390` 均跳过启动且保持不变。
  摄像头真实切换后的 PID 以当前 PID 文件为准，后端就绪检查通过。
- 模拟验证：非 demo 进程占用端口、无法读取端口归属、多个端口所有者、过期 PID、
  缺少模型、HTTP 200 但健康状态降级、调用参数和并发启动锁，均按预期拒绝或报告。
- 使用独立测试目录中的短时 `sleep` 进程验证实际后台机制：父 PID 为 `1`，
  独立 SID/PGID、释放总启动锁、保留服务锁、拒绝重复启动、自然退出后释放锁。
  没有为测试加载另一份模型、额外监听端口或停止正在展示的服务。
- 原基础脚本曾仅验证后台机制；本次摄像头切换已实际验证前后端重新启动。
  基础回归脚本 `.runtime/check_start_demo.sh`，摘要
  `.runtime/camera_start_regression.log`；这些运行验证文件不纳入版本控制。

## 环境与页面说明

demo 不是独立拷贝包，跨目录 import 需要保留 hxjm/lanhu；当前依赖已经安装。
服务由 `start_demo.sh` 使用已验证的现有环境启动，不需要重新安装。
播放基础 URL 不带 `/whep`，播放器内部会追加；后端 RTSP 使用本机地址，
浏览器视频和 WS 使用浏览器可访问的服务器 IP，不能改成浏览器自己的 `127.0.0.1`。
当前 `frontend/.env.local` 不再配置摄像头地址：

```dotenv
VITE_DETECTIONS_WS_URL=ws://192.168.109.191:8010/ws/detections
```

`start_demo.sh` 启动 Vite 开发服务，不使用历史 `dist`/preview 产物；切换摄像头
只需修改 `demo.env` 并执行脚本，浏览器打开或刷新 `3010` 即可，不需要手动传地址。

页面包含一路播放器、独立的视频/AI 状态、检测数量、推理耗时和“显示标注”开关。
视频区域使用已美化的响应式布局，原始画面按 contain 完整显示，不裁切。
浏览器侧还需要能访问服务器的 HTTP `18889` 和 ICE UDP `18189`，并允许
对应跨域请求；HTTPS 页面不能直接请求 HTTP 视频端点。这里不调整现有服务配置。

## 第二步验证记录

- **构建通过**：在 demo 前端目录执行 `npm run build` 成功，Vite 转换 34 个
  模块并生成 `dist/`。本次构建未设置播放地址，因此不能直接用该产物验证播放；
  请按上述命令带实际地址构建或启动开发页。
- `npm ls` 确认依赖版本与 lanhu 已安装版本一致，React/ReactDOM 去重；
  已生成 `package-lock.json`，后续可使用 `npm ci` 复现安装。
- **开发页 HTTP 检查通过**：短暂启动 demo 的 `3010` 端口，确认入口页面、
  demo JSX、跨目录播放器 JSX 和 `webrtcPolicy.js` 均返回 HTTP 200；
  原播放器的 React import 解析到 demo 自身依赖，而非 lanhu 的另一份 React。
  检查后临时 demo 进程已退出，`3010` 已释放，没有启动或停止原业务服务。
- **真实视频播放未验证**：没有打开浏览器进行播放，也未发起 WHEP 视频协商。
  流 API ready、HTTP 200 和构建成功均不能证明客户端已完成 ICE 协商、
  解码并显示画面。需要浏览器人工确认。

随后已按指令启动 demo 并保持后台运行，监听 `0.0.0.0:3010`，访问地址为
`http://192.168.109.191:3010/`，播放地址为
`http://192.168.109.191:18889/live/camera_1/`。第三步不修改或重启前端。

## 第三步：单次真实取帧与检测

新增 `backend/stream_grabber.py` 和 `backend/check_detection.py`，完善
`backend/config.py` 和 `backend/detector_adapter.py`。不改动原业务文件。

- `DEMO_RTSP_URL` 默认 `rtsp://127.0.0.1:18554/live/camera_1`。
  `DEMO_CAMERA_ID` 默认 `camera_1`；这些是第三步单次验证模块的历史默认值。
  当前演示的摄像头只修改根目录 `demo.env`，启动脚本统一生成两端实际配置。
- 通过 OpenCV FFmpeg 后端读取一张有效 BGR 帧，默认 RTSP over UDP。
  实际 MediaMTX API 的 `rtspTransports` 为 `["udp"]`，RTP/RTCP 实际监听
  `18000/18001`。首次 TCP 取帧尝试收到 461，发生在模型加载前，未执行推理；
  因而只调整 demo 传输方式，不修改原 MediaMTX 配置。
  如服务器改为支持 TCP，可设置 `DEMO_RTSP_TRANSPORT=tcp`；已有的
  `OPENCV_FFMPEG_CAPTURE_OPTIONS` 配置优先，不会被 demo 覆盖。
  打开超时和单次读取超时各为 `5000ms`；不无限重连或等待，成功或异常均释放连接。
- `frame_ts_ms` 是有效帧读取完成时的 Unix 毫秒时间，不是摄像头 PTS；
  `source_width`、`source_height` 是实际原始帧尺寸。
- 每进程缓存一次 `DetectionServer.init_model_context()` 返回的上下文。
  每次验证仅调用一次普通全帧推理，不调用切片推理；首次调用可能包含模型内部 warmup。
- `_person_boxes()` 返回的像素 xywh 转换为 `[x1/W, y1/H, (x1+w)/W, (y1+h)/H]`，
  裁剪到 `[0, 1]`，丢弃裁剪后无面积的框；只返回 person，未检出时为 `[]`。
- `inference_ms` 使用单调高精度计时，包含推理、预测转换与检测框提取，
  不含模型初始化或 RTSP 取帧。预测转换读取 CPU 检测结果，包含 GPU 同步等待。
- stdout 仅输出一条 JSON；模型初始化和诊断日志转到 stderr。
  取帧、依赖或模型失败时 stderr 报告具体错误，以非零状态退出，不输出伪造 JSON。
- 仅使用现有算法环境和本地 `.pt` 权重，初始化前检查文件存在且非空。
  设置 `YOLO_AUTOINSTALL=false`、`YOLO_OFFLINE=true`，不自动安装依赖或下载模型。
  运行缓存/配置位于 demo 的 `.runtime/`；使用 `-B` 避免在原业务源码目录写入字节码。

可重复执行的命令（不要使用前端的 npm 环境代替 Python 算法环境）：

```bash
cd /data/nfs_storage/hxjm/video_ai_decoupling
DEMO_RTSP_URL='rtsp://127.0.0.1:18554/live/camera_1' \
DEMO_RTSP_TRANSPORT='udp' \
DEMO_CAMERA_ID='camera_1' \
/home/guest/anaconda3/envs/deepsort/bin/python -B -m backend.check_detection
```

模型默认复用 hxjm/python/deep_sort-master/detection/yolov5mu.pt；
如需其他已存在的本地权重，在同一命令前配置 `DEEPSORT_MODEL=/实际路径/model.pt`。
不要传模型下载 URL 或不存在的权重文件。

### 本次真实验证结果

2026-10-07 16:14:23.085（Asia/Shanghai）取得原始帧；验证命令退出状态为 0。

- 环境：现有 `/home/guest/anaconda3/envs/deepsort/bin/python`，PyTorch
  `2.5.1+cu121`、SAHI `0.12.6`、Ultralytics `8.4.135`、OpenCV `5.0.0`。
  未安装或重装依赖，未下载模型。
- 使用本地 `yolov5mu.pt`，设备为 CUDA（NVIDIA GeForce RTX 4090 D）。
  成功取帧后只执行一次完整检测调用，初始化日志只有一次。
- `camera_id=camera_1`，`frame_ts_ms=1791360863085`，原始尺寸 `1280×720`。
- `inference_ms=2498.7`；这是首次调用，可能包含内部 warmup，不代表稳定帧率。
- 真实检测到 **1 人**，confidence 为 `0.761249840259552`；归一化 xyxy 为
  `[0.1828125, 0.4888888888888889, 0.29296875, 0.8069444444444445]`。
- 完整 JSON 保存在 `.runtime/check_detection.json`，诊断日志为
  `.runtime/check_detection.log`；首次 TCP 取帧失败记录为 `.runtime/rtsp_tcp_failure.log`，
  该失败发生在模型加载前，不计为真实推理。
- 额外模拟检查通过：延迟导入、上下文只初始化一次、本地权重缺失、BGR/RGB 转换、
  xywh/归一化 xyxy 转换、边界裁剪、无检测空列表、连接释放、超时参数与 JSON 错误输出。
  模拟检查未加载真实模型，也未增加真实推理次数。
- GPU 预检发现 `nvidia-smi` 的 NVML 驱动/库版本不匹配警告；PyTorch 的 CUDA
  可用且本次 GPU 推理成功，没有修改驱动或处理其他系统问题。
- 原检测源码、lanhu 播放器及依赖配置、demo 前端入口播放器与配置的校验值保持不变。

本步不启动 WebSocket、不添加 Canvas；3010 页面继续独立播放原始流，
不消费终端检测 JSON。第三步的历史验证到此结束，第四步见下一节。

## 第四步：持续检测与共享 WebSocket

新增 `backend/app.py`、`backend/analyzer.py` 和 `backend/requirements.txt`，
完善第三步配置、检测适配器和取帧模块。未修改前端、原检测代码或业务启动脚本。

### 任务与缓冲约束

- FastAPI lifespan 为整个服务创建一个 `Analyzer`。必须使用 **一个 Uvicorn worker**，
  不使用 `--reload` 或多 worker，否则会创建多份应用生命周期。
- 一个 `demo-rtsp` 线程持续解码原始 RTSP/UDP，只覆盖一个最新帧槽；
  没有无限帧队列。分析线程持有本次输入帧快照，不受后续最新帧替换影响。
- 一个分析协程配合 `max_workers=1` 的推理线程池，初始化和推理都在线程池执行。
  推理串行，不阻塞 WebSocket 的 asyncio 事件循环，也不会因客户端连接重新加载模型。
- `DEMO_INFERENCE_INTERVAL_SECONDS` 默认 `1`，限制相邻推理开始时间的最小间隔。
  推理耗时更长时等待当前推理完成，不重叠、不补做积压任务，不承诺每秒完成一次。
- `frame_id` 是每次成功读取的帧序号，因此推送序号递增但通常不连续。
  同一帧不会再次分析，包括前一次分析失败的帧。
- `stream_epoch` 在每次成功重新建立 RTSP 连接时递增；本次服务内 `frame_id`
  跨重连保持递增。服务重启会重置这两个计数，客户端应在新服务连接时清空旧序号状态。
- `frame_ts_ms` 和尺寸直接来自实际被分析的输入帧，不在推理结束时重取最新帧时间。
  仍是接收端 Unix 时间，不是摄像头 PTS。
- 拉流失败后清除最新帧，发布独立 `type=status` 异常消息，按
  `DEMO_RECONNECT_DELAY_SECONDS`（默认 `2` 秒）重连。打开/读取超时仍各 `5` 秒。
  若推理期间连接失效或已进入新 epoch，该旧连接结果被丢弃。
- 成功推理且无人时正常推送 `detections: []`。推理错误发布状态消息，不伪装成空检测；
  模型初始化失败报告 `model_error`，不循环重新加载模型。
- 每个客户端分别只有一个最新检测槽和一个最新状态槽，旧消息可被覆盖；
  状态消息附带完整 `components` 快照。发布过程不等待任何客户端发送。
- 每次 WebSocket 发送有 `DEMO_WS_SEND_TIMEOUT_SECONDS`（默认 `5` 秒）超时，
  超时关闭该客户端（1013），不影响其他客户端或分析。接收任务单独监测断开。
  `sent_at_ms` 在每个客户端开始发送时填写，允许同一帧的不同客户端值略有差异。
- 退出时先通知停止，等待当前推理完成，释放 RTSP 连接并 join 取帧线程和推理线程池；
  不通过强行中断 CUDA 推理来清理线程。

### 依赖与启动

检查发现原 deepsort 环境没有 FastAPI/Uvicorn/WebSocket 支持，因此仅将必要 API
依赖安装到 **demo 内的 `.runtime/python_deps`**，没有修改原算法环境。
已安装 FastAPI `0.115.12`、Uvicorn `0.34.3`、websockets `15.0.1` 及必要传递依赖。
算法仍使用现有 deepsort Python、torch、SAHI、Ultralytics 和本地权重，不下载模型。

首次准备依赖时可执行；当前服务器已经完成，不必重复安装：

```bash
cd /data/nfs_storage/hxjm/video_ai_decoupling
/home/guest/anaconda3/envs/deepsort/bin/python -B -m pip install \
  --target .runtime/python_deps --cache-dir .runtime/pip-cache \
  --disable-pip-version-check --no-input --no-compile --only-binary=:all: \
  -r backend/requirements.txt
```

当前后端已在后台运行，**不要绕过统一脚本重复启动占用 8010**。
日常恢复或切换摄像头使用：

```bash
cd /data/nfs_storage/hxjm/video_ai_decoupling
bash start_demo.sh
```

- 健康接口：`http://192.168.109.191:8010/health`。
- WebSocket：`ws://192.168.109.191:8010/ws/detections`。
- 本次后端 PID `1816527`，PID 文件 `.runtime/backend.pid`，日志 `.runtime/backend.log`。
- 当前前端仍为 `http://192.168.109.191:3010/`，PID `1604385` 未变。
- `/health` 返回服务/取帧/分析状态、模型初始化次数、连接数、最近十次推理耗时等。
  HTTP 200 不代表正在产出检测，应同时检查 JSON 的 `status` 和计数。
- 这是无鉴权的内网 demo，不应直接暴露到公网。

### 消息示例

本次 WebSocket 实际收到的一条检测消息：

```json
{
  "type": "detections",
  "camera_id": "camera_1",
  "frame_ts_ms": 1791362148866,
  "source_width": 1280,
  "source_height": 720,
  "inference_ms": 15.625,
  "detections": [
    {
      "label": "person",
      "confidence": 0.4798084497451782,
      "bbox": [0.16484375, 0.5013888888888889, 0.315625, 0.6944444444444444]
    }
  ],
  "frame_id": 2308,
  "stream_epoch": 1,
  "sent_at_ms": 1791362148926
}
```

本次连接实际收到的独立状态消息（没有 `detections` 字段）：

```json
{
  "type": "status",
  "camera_id": "camera_1",
  "component": "service",
  "state": "ok",
  "error": null,
  "components": {
    "capture": {"state": "streaming", "error": null},
    "analyzer": {"state": "ready", "error": null}
  },
  "stream_epoch": 1,
  "sent_at_ms": 1791362148086
}
```

实际拉流异常时，同一类状态消息的 `component=capture`、`state=reconnecting`，
`error` 包含具体错误；不是检测消息，也没有空检测数组。

### 本次连续真实验证

2026-10-07 16:35:59（Asia/Shanghai）完成实际 WebSocket 验证：

- 同时连接两个正常客户端和一个暂停消费的客户端，`/health` 确认连接数为 `3`。
- 两个正常客户端收到完全相同的六个帧序号及检测内容（逐客户端发送时间除外），
  所有消息的框均为合法归一化 xyxy，帧时间早于发送时间。
- 每条真实消息为 `1280×720`、epoch `1`，这六帧各检测到 `1` 人。

| frame_id | inference_ms | 人数 |
| --- | --- | --- |
| 2308 | 15.625 | 1 |
| 2348 | 15.465 | 1 |
| 2384 | 14.920 | 1 |
| 2431 | 16.164 | 1 |
| 2458 | 15.241 | 1 |
| 2486 | 14.739 | 1 |

- 模型加载日志只有 `1` 次，`/health.model_initializations=1`；客户端连接未触发模型加载。
- 暂停消费的三秒内发布计数从 `100` 增至 `103`；所有客户端断开后连接数回到 `0`，
  发布计数仍从 `110` 增至 `111`，分析不依赖客户端在线。
- 完整验证摘要 `.runtime/ws_validation.json`，六条原始检测消息
  `.runtime/ws_messages.jsonl`。本机重复验证命令（服务保持运行）：

```bash
cd /data/nfs_storage/hxjm/video_ai_decoupling
PYTHONPATH="$PWD/.runtime/python_deps:$PWD" \
/home/guest/anaconda3/envs/deepsort/bin/python -B .runtime/check_websocket.py
```

本机模拟验证脚本 `.runtime/check_pipeline.py` 还验证了：最新槽容量、状态独立、
输入帧时间归属、旧帧不重复推理、间隔上限、串行工作线程、模型单次初始化、
慢发送超时注销、推理/模型错误、拉流失败重连与 epoch 递增、连接释放和线程退出。
上述模拟检查不读取真实流或加载真实模型：

```bash
PYTHONPATH="$PWD/.runtime/python_deps:$PWD" \
/home/guest/anaconda3/envs/deepsort/bin/python -B .runtime/check_pipeline.py
```

### 验证边界

- 为保持现有服务稳定，没有人为断开真实摄像头/MediaMTX；真实拉流中断后的恢复
  尚未通过故障注入验证，已用模拟捕获失败验证重连及新 epoch。
- 本次暂停消费没有刻意填满操作系统发送缓冲；真实网络极慢/阻塞压力场景未完整压测。
  有界槽覆盖和发送超时关闭已在模拟检查中通过。
- 真实样本始终有一人，未捕获真实无人画面；无人输出空数组路径通过模拟验证。
- 为保持后端运行，未停止当前真实服务测试 SIGTERM 收尾；退出时等待/释放/join
  已模拟验证，CUDA 驱动永久卡死时的强制回收不在本步验证范围。
- NVML 预检警告仍属于原系统驱动问题；PyTorch CUDA 实际持续推理成功，未修改驱动。
- 第四步当时未改动前端接收 WebSocket、未添加 Canvas；以下为第五步新增接入记录。

## 第五步：浏览器接收与 Canvas 标注

### 原因核对与接入文件

检查确认 3010 的进程工作目录是
`/data/nfs_storage/hxjm/video_ai_decoupling/frontend`，入口为 `index.html → src/main.jsx → src/App.jsx`。
原先该入口仍只有第二步视频组件，未实现 AI 接收、Canvas 或标注开关，
不是访问到了另一份 lanhu 页面。现在 `App` 已挂载新版 `VideoWithOverlay`。

- `frontend/src/useDetections.js`：单个 WS 连接，解析后端实际 `detections` 和
  `status` 消息；断开后按 1/2/4/8/10 秒退避重连，连接成功后重置退避。
  不向服务器发送业务指令，不影响后端模型或取帧任务。
- `frontend/src/overlay.js`：归一化 xyxy 映射、`object-fit: contain` 黑边计算、
  DPR Canvas 分辨率和 `person 置信度%` 绘制，不添加没有来源的目标编号。
- `frontend/src/VideoWithOverlay.jsx`：透明 Canvas、独立状态、数量、耗时和开关；
  原组件仍使用 `primaryUrl=""` 和原来的 `fallbackUrl`。
  播放器经 `memo` 包装，状态回调稳定；检测/开关更新不改变播放器参数或 key。
- `frontend/src/App.jsx`、`frontend/src/styles.css`、`frontend/.env.example`：页面接入、
  叠加层样式和 WS 环境变量。第五步最初在 `.env.local` 保存了本机地址；
  现在摄像头只从根目录 `demo.env` 读取，`.env.local` 仅保留固定 WS 地址。

后端协议已经同时从源码和真实连接确认：检测消息有 `type=detections`、
`camera_id`、`frame_ts_ms`、`source_width/height`、`inference_ms`、`detections`、
`frame_id`、`stream_epoch`、`sent_at_ms`；`bbox` 是原始帧上的归一化 xyxy。
状态消息有 `type=status`、`component/state/error` 和完整 `components` 快照，
不含检测数组。实际样本保存在 `.runtime/overlay_protocol_samples.json`，
完整消息结构可参见第四步示例；第五步实际连接的 epoch 已为 `2`。

### 清框和生命周期

- 用浏览器 `performance.now()` 记录有效检测的本地接收时间，连续 3000ms
  没有更新就清框，不依赖服务器与浏览器的时钟是否一致。渲染时也检查期限。
- 空数组立即清框并显示检测数量 `0`；断开、解析错误、取帧/分析异常或模型准备中
  清框并显示独立 AI 状态。异常未恢复前不接受滞留的检测消息，避免旧框重新出现。
- 状态判断同时检查 `components`；不能仅见顶层 `state=ok` 就忽略内部分析错误。
- 同一 WS 会话内只接受更高 epoch，epoch 变化清旧结果并重置帧排序；
  同一 epoch 内仅接受严格递增 `frame_id`。新 WS 会话重新建立排序基准，
  允许后端重启后的计数重置，不把新服务当作永远过期的帧。
- 只在本组件容器内查询 `<video>`，按其 `videoWidth/videoHeight` 和实际边界
  计算 contain 区域，再映射到 Canvas，不将黑边当作画面。
  使用 ResizeObserver、元数据事件、窗口 resize 和动画帧更新尺寸/DPR；
  卸载时清理观察器、监听、动画帧、WS 和计时器。
- Canvas 的 `pointer-events: none`，不拦截原播放器；标注开关只控制 Canvas，
  不关闭 WS 或视频。原播放器全屏容器不包含这个 Canvas，全屏暂不显示标注。

### 2026-10-07 实际验证结果

**构建与真实 WS 接收通过，不等同于真实摄像头画面上的框已验证。**

- `npm run build` 通过，Vite `5.4.21` 转换 `36` 个模块。
- 浏览器加载的确为新版标题和组件，显示视频/AI 独立状态、检测数量、耗时和开关；
  实际连接 `ws://192.168.109.191:8010/ws/detections`，单页只建立一个业务 WS。
  浏览器连续收到真实状态消息和真实检测，以下三帧各检测到 `1` 人：

| frame_id | stream_epoch | inference_ms |
| --- | --- | --- |
| 53702 | 2 | 16.968 |
| 53742 | 2 | 22.609 |
| 53747 | 2 | 16.876 |

- 真实页面中 Canvas 尺寸非零，DPR=2 时为 `1920×1080`，指针事件不拦截视频。
  原始摄像头视频在本机自动化浏览器中未成功解码，`videoWidth/Height=0`，
  因而 Canvas 正确保持透明，没有把收到检测消息当作画面可用。
- 本机现有 Chromium 的 WebRTC 编解码器没有 H264；现有 Firefox 的 capabilities
  虽列出 H264，但实际发出的 SDP offer 也没有 H264。两者 WHEP 均返回 HTTP 400；
  对应 MediaMTX 日志明确记录 `codecs not supported by client`。
  原始视频基础 URL 未改动，播放器及 MediaMTX 未修改，不能据此声称用户浏览器
  已播放或真实人物框已对齐，也没有更换原始流、转码或安装浏览器编解码器。
- 为验证 Canvas 行为，仅在自动化测试页内给原 `<video>` 临时绑定了
  **1280×720 浏览器生成的模拟视频**，未修改页面业务代码、后端或摄像头流。
  真实 WS 检测可触发非透明框和 `person XX%` 标签，但该测试不是摄像头对齐验证。
- 在上述模拟视频上，浏览器检查通过：关闭/恢复标注、视频元素及流身份不变、
  WS 连接不变；窗口从 1100px 改为 800px 和 390px 后黑边映射及 DPR=2 均正确。
  另用仅在测试页注入的协议消息验证空数组、乱序帧、epoch 切换、解析错误、
  内部分析错误和恢复、按本地接收时间约 3 秒过期清框。
- 只关闭测试页的真实 WS，Canvas 清空、模拟视频时间仍推进，自动重连后重新接收
  真实检测并绘制。没有停止 8010、MediaMTX 或原业务。**真实原始视频在 WS 断开时
  是否持续播放尚未验证**，因为本机自动化浏览器始终未解码成功。
- 浏览器检查没有未捕获的页面 JS 错误；预期的 WHEP 400/播放器连接失败另行记录，
  不将其描述为“控制台完全无错误”。

复查证据和重复命令（服务应保持运行；浏览器驱动仅在 demo 的忽略目录内）：

```bash
cd /data/nfs_storage/hxjm/video_ai_decoupling
node .runtime/check_overlay.mjs
node .runtime/check_overlay_browser.mjs
node .runtime/probe_whep.mjs
cd frontend
npm run build
```

- `.runtime/overlay_browser_validation.json`：真实 WS 消息及显式区分的模拟验证结果。
- `.runtime/overlay_real_page.png`：真实页面，AI 状态正常但自动化浏览器视频未连接。
- `.runtime/overlay_synthetic_video.png`：有明确模拟水印的视频及标注，不是真实摄像头画面。
- `.runtime/whep_diagnostic.json`：Firefox 实际 SDP、编解码器和 HTTP 400 记录。

3010 前端 PID `1604385`、8010 后端 PID `1816527` 保持运行。
Vite 检测到新增 `.env.local` 后自动重新加载配置，PID 没变；没有停止或重启后端。
与接入前基线比对，后端取帧/分析/adapter、原算法文件、原播放器和启动脚本的
SHA-256 均未变化。`/health` 仍报告 `model_initializations=1`。

### 仍待真实浏览器确认

用支持当前原始 H264 流的浏览器访问 `http://192.168.109.191:3010/`，确认视频状态为
“原始画面”后，检查真实人物框、窗口缩放、标注开关，以及只断开 AI WS 时视频继续。
目前不宣称这些真实摄像头检查通过，也不承诺最新检测与显示画面帧精确同步。
第五步到此停止，等待下一步指令。
