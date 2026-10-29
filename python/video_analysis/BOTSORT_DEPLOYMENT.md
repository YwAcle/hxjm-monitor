# 公共 BoT-SORT 部署

主目录 `/data/nfs_storage/hxjm` 运行公共 MediaMTX 和 BoT-SORT。其余开发 worktree
保留自己的业务服务及端口，通过公共服务播放四路视频、订阅框和 ID。
这份部署使用现有 YOLOX-X 与 FastReID，不使用 OSNet。

## 启动和更新

主目录先更新到包含本次改动的版本，然后启动：

```bash
cd /data/nfs_storage/hxjm
bash scripts/start-local.sh --check
bash scripts/start-local.sh
```

其他开发者在自己的 worktree 更新同一版本后，仍使用原启动命令：

```bash
cd /home/guest/hxjm-wsc  # 换成自己的目录
bash scripts/start-local.sh
```

无需在每个 worktree 复制模型、设置四个 worker 或改端口。正常关闭个人项目：

```bash
bash scripts/stop-local.sh
```

该操作保留公共服务。公共服务不随开发终端退出而结束；服务器重启后需再次运行
启动命令，没有安装额外的开机启动单元。脚本不进行 Git 拉取、提交、合并或推送。

必要的七个启动脚本、公共管理器和前端代理均纳入版本控制；`local-ports.env`、
`.run/`、模型权重和二进制继续忽略。各目录使用自己的原端口文件。
`PRIMARY_ROOT` 从 Git 的 common directory 确定，当前 worktree 对应主目录为
`/data/nfs_storage/hxjm`。本说明针对当前同服务器的 Git worktree 部署；独立克隆或新服务器
仍需准备环境、主目录模型和端口文件，不能仅凭 Git 拉取下载权重。

## 运行结构和播放行为

1. 公共媒体从数据库读取 machine_id 1–4 的有效摄像头地址，每路统一接入一次。
2. 公共算法使用一个模型进程，四路分别保留独立 tracker、GMC、帧序号和时钟。
3. 所有页面播放连续 WebRTC，WebSocket 默认只传检测元数据，不传 JPEG。
4. 每路解码只保存最新一帧；推理按轮询取新帧，无等待帧队列，不按浏览器重复推理。
5. 开发目录的本地 MediaMTX 仅为其余原有任务中继公共 RTSP，不再重复连接摄像头或录像。
6. 录像仅保留主目录一份，沿用其分段/保留策略及主后端回调。

默认实时模式下，框是异步结果，最多显示一秒，并受服务端有效期限制。
AI 暂时中断只清空检测框，不覆盖视频。独立视频和检测链路不能保证逐帧严格对齐。
“同帧验收”开关使用与检测帧绑定的干净 JPEG，适合核查算法；该模式画面更新率
受推理速度限制。当前方案解决播放等待推理和多项目重复加载模型，
不把四路 YOLOX-X 的分析速度承诺为每路 20/25 FPS。

保留原检测尺寸、阈值、低分小目标恢复、交叉保护、ReID、score fusion、FP16、融合模型、
ORB GMC 和真实时间步长。短时预测仍使用实线和原 ID，不显示 PRED。
预测显示期限和轨迹保留期限保持现有算法设置，未为降低资源而修改跟踪参数。

## 依赖、端口和地址

主目录需要现有的 Python/CUDA 环境、MediaMTX 二进制、系统 Python 的 PyYAML，
以及启动脚本所需的 Java 8、Maven、Node.js 18+、CMake 和 Docker。
数据库复用 `smartmonitor-mysql` / `hxjm_sm`，仅查询摄像头地址，无表结构或地址写入。
两个模型文件仅需放在主目录：

```text
python/tracker/BoT-SORT/pretrained/bytetrack_x_mot17.pth.tar
python/tracker/BoT-SORT/pretrained/mot17_sbs_S50.pth
```

公共服务沿用主目录 `local-ports.env` 的媒体端口。当前 RTSP `18554`、WebRTC
`18889`、媒体 API `9997`，分析 API 为 `127.0.0.1:28010`。主目录前端 `3000`、
WSC 前端 `3002` 保持原值。SSH 网络浏览器入口分别是
`http://100.127.237.7:3000/`、`http://100.127.237.7:3002/`。

前端同源代理 `/shared-media` 和 `/ws/detections`，浏览器无需直接访问服务器
`127.0.0.1`；WebRTC 媒体仍使用原 ICE UDP 端口。公网/跨网段访问需该端口可达。
局域网硬编码 IP 与数据库摄像头 IP 均未修改。启动器的 `PUBLIC_HOST`、原 Vite
聊天代理和后端默认 `publicHost` 等局域网配置仍保留；涉及对外生成地址时应另外确认，
不可把摄像头 IP 替换为 SSH 地址。

公共启动设置如下，通常无需调整；非默认端口需同时配置客户端目标：

| 环境变量 | 默认值 | 用途 |
| --- | --- | --- |
| SHARED_BOTSORT_PYTHON | /home/guest/anaconda3/envs/botsort39/bin/python | 公共算法环境 |
| SHARED_BOTSORT_GPU | 0 | 公共模型所在 GPU；选择设备不保证该 GPU 独占 |
| SHARED_BOTSORT_CUDA_GRAPH | 1 | 固定尺寸检测 CUDA Graph，0 关闭；更改后统一重启公共服务 |
| SHARED_BOTSORT_ANALYSIS_PORT | 28010 | 公共分析 API |
| SHARED_BOTSORT_RECORD | yes | 主目录单份录像，no 显式关闭 |
| SHARED_BOTSORT_SOURCE_TRANSPORT | 沿用主目录原配置 | 摄像头上游 RTSP 传输方式 |
| VIDEO_ANALYSIS_SHARED_ORIGIN | http://127.0.0.1:28010 | 启动前端代理的公共分析目标 |
| SHARED_MEDIA_ORIGIN | 从主目录 WebRTC 端口读取 | 启动前端代理的公共媒体目标 |

公共算法固定一个 worker，OpenCV 计算线程为 8，OpenMP/BLAS/Torch 和每路 FFmpeg
解码线程为 1。`MALLOC_ARENA_MAX=2`、`MALLOC_TRIM_THRESHOLD_=131072` 限制并及时
回收 glibc 空闲堆内存，不在逐帧处理中强制清理分配器。当前 GPU 0 同时有其他 VLLM
任务；公共模型只加载一次，但 CPU/GPU 性能仍受其他服务负载影响。
摄像头分辨率、源帧率和检测输入尺寸不变。

公共服务推理前要求主机 `MemAvailable` 至少 4 GiB；加载模型另需 3 GiB，
即加载准入线为 7 GiB。内存不足时停止/暂停模型并按退避策略等待，不通过降低
保护线反复加载。独立 `local` 实验模式仍默认保留 8 GiB、加载另需 4 GiB；这些
默认值与公共启动器的明确配置不同。保留模型加载超时、推理超时和指数退避。数值异常仅重置
出错摄像头 tracker，不重载整份模型；滤波协方差使用稳定更新。

## 同帧吞吐优化及边界

本轮保留四路轮询、取最新帧和完成后立即发布的调度。检测预处理使用字节查表，
保留原 float64 运算再转 float32 的舍入，输出与原实现逐元素一致。YOLOX 解码网格
按尺寸缓存；GMC 将匹配点筛选改成 NumPy 批量运算，仍使用全部 ORB 描述子、
原 BF 匹配、筛选阈值和 RANSAC，回归样本中的点与变换矩阵逐元素一致。

检测器默认捕获固定 `1×3×800×1440` FP16 CUDA Graph，减少重复 CPU 发射开销；
每次返回独立输出副本，避免 YOLOX 原地后处理污染下次结果。启用时先校验捕获/回放
与普通模型输出一致，失败则让监督器处理该 worker，不复用出错 CUDA 上下文。
需要关闭时使用 `SHARED_BOTSORT_CUDA_GRAPH=0` 并统一重启。FastReID 不再导入
推理未使用的训练入口。模型、输入尺寸、检测及关联阈值、ReID 与跟踪规则保持现有设置。

同帧吞吐仍需按四路实际 JPEG `frame_id` 换帧测量，不能以连续 WebRTC 帧率代替。
本轮自动检查通过：算法 47 项、分析服务 36 项、公共管理器 9 项。
数值等价和合成回归不能代替原视频中的小目标、交叉遮挡和 ID 稳定性验收，
这些场景仍需用已验证视频回归。当前优化不承诺四路逐帧检测。

2026-10-25 最终配置在主目录 3000 页面测量 40 秒，四路同帧 JPEG 实际更新
1.50–1.52 FPS，平均换帧间隔 661–664 ms，最长间隔 1018 ms；图框配对错误、
推理失败和模型重启均为 0。优化前同一测法约 0.53–0.55 FPS、平均间隔约 1.83 秒。
本轮改善约 2.7 倍，仍未达到同帧流畅播放要求；不能用原始 WebRTC 帧率替代该结果。
3002 当时未启动，最终复测使用 3000，不代表远端客户端或全天负载验收。

最终配置另采样 45 秒，公共进程树 RSS 峰值约 2.98 GiB，平均 CPU 约 3.18 个逻辑核，
模型显存约 1594 MiB，主机 MemAvailable 最低约 5.18 GiB；测量期间单模型持续运行。
CUDA Graph 的固定工作区增加显存使用，启动器的 glibc 设置降低 CPU 常驻内存。
四路 CPU 并发批调度 A/B 未提高实流吞吐，且增加结果等待，已移除；GPU 精确 BF
匹配也仅节省约 22 ms/四路，未加入生产。进一步提升需评估 TensorRT 等执行后端，
并重新验证原视频检测、ReID 和轨迹结果；当前环境仅有 CPU ONNX Runtime，无 TensorRT。
报告位于工作区 `.run/performance/{exact-final,final-resources}.json`，不纳入 Git。

## 公共服务维护

以下命令由公共服务所有者（当前为 guest）运行：

```bash
cd /data/nfs_storage/hxjm
python3 deploy/botsort/shared_service.py status
python3 deploy/botsort/shared_service.py check
curl -fsS http://127.0.0.1:28010/health
```

`phase=running` 表示媒体和分析 API 已监听。应进一步在 health 确认四路 capture
为 streaming、published_count 持续增长、failures/restarts 不增长。
公共日志在 `.run/shared-botsort/{supervisor,media,analysis,bootstrap}.log`；单份日志
默认上限 8 MiB，保留三份轮转文件。含源地址的运行 YAML 权限为 0600。

正常个人启动不会重启已运行的公共服务。主目录算法代码/依赖更新，或数据库摄像头
地址变更后，由所有者统一重启公共服务应用更新：

```bash
cd /data/nfs_storage/hxjm
python3 deploy/botsort/shared_service.py stop
python3 deploy/botsort/shared_service.py start
```

这会短暂中断所有订阅者，页面自动重连。`start` 遇到非公共进程占用端口会拒绝启动，
不会擅自终止其他服务。新改造首次上线前，需用原主目录关闭脚本释放旧主目录媒体端口。
不同 Unix 用户可以消费公共接口，但不要以其他用户维护其私有运行状态目录。

## 独立算法实验与验证

需要运行自己修改的算法时显式选择：

```bash
VIDEO_ANALYSIS_MODE=local bash scripts/start-local.sh
```

仅此模式读取自己的 `.run/video-analysis.env` 并额外加载模型，资源消耗会增加；
默认公共模式忽略旧文件里的四 worker 设置。只播放本地原始视频可使用：

```bash
VIDEO_ANALYSIS_MODE=local START_VIDEO_ANALYSIS=no bash scripts/start-local.sh
```

回到公共模式重新运行普通启动命令即可。维护/回归检查：

```bash
python3 -B -m unittest discover -s deploy/botsort/tests -v
python3 -B -m unittest discover -s scripts -p 'test_local_runtime.py' -v
PYTHONPATH=python /home/guest/anaconda3/envs/botsort39/bin/python -B \
  -m unittest discover -s python/video_analysis/tests -v
(cd python/tracker/BoT-SORT && /home/guest/anaconda3/envs/botsort39/bin/python -B \
  -m unittest discover -s tests -v)
(cd lanhu && npm test && npm run build)
```

实流验收应同时打开至少两个项目的四路页面，测量实际 video frame callbacks
和最长停顿，确认浏览器增加后模型进程仍为一个。浏览器仅阻断 AI WebSocket 时
视频应继续播放；关闭任一开发项目后公共媒体/模型 PID 应保持不变。
短时间实测不替代长期负载测试；摄像头上游丢包和外部 GPU/CPU 任务仍可影响质量。

## 历史记录：2026-10-25 首轮上线实测

以下数据记录本轮同帧吞吐优化之前的部署，不能作为当前同帧速度或资源验收结果。

主目录与 WSC 已同步部署，原端口和摄像头地址保持不变。两个独立测试浏览器
同时打开 3000/3002 的八路 1080p 视频，45 秒内无两秒以上停顿，最长呈现间隔
约 200 ms，实际呈现 15.5–16.4 FPS。另对 3002 连续观察 5 分钟：四路解码均约
25 FPS，WebRTC framesDropped 均为 0。前三路 freezeCount 为 0，第 4 路记录
3 次短冻结、合计 609 ms；实际呈现 15.4–17.0 FPS，最长呈现间隔约 267 ms。测试浏览器在服务器上运行，最终客户端呈现速度仍应
以开发者自己的浏览器为准。

仅阻断测试浏览器 AI WebSocket、切换同帧验收、关闭主目录业务项目后，
3002 原始视频均继续播放；主目录业务随后已恢复。公共媒体/API/模型 PID 保持不变，
模型初始化 1 次、重启 0 次，四路推理失败均为 0。同帧模式图像和检测 frame_id 一致。

60 秒公共服务资源采样：模型显存 1124 MiB，全部公共进程 RSS 峰值约 3.8 GiB，
CPU 平均合计约 2.2 个逻辑核（服务器共 32 核）。未发现 WSC 本地重复模型。
AI 结果每路约 0.60–0.62 FPS，未承诺逐帧检测；视频播放不再跟随此更新率。

自动检查通过：算法 37 项、分析服务 34 项、公共管理器 8 项、启动器 11 项，
前端 71 项及生产构建。实测报告在当前工作区 `.run/shared-browser-verification.json`、
`.run/shared-long-verification.json`、`.run/shared-resource-sample.json`，不纳入 Git。
本次短时观察不代表全天候稳定性验收。
