# SmartMonitor Docker 部署说明 11111222333313123324324
# SmartMonitor Docker 部署说明 1111122234

本仓库包含前端、后端、流媒体服务和算法服务。应用通过 `scripts/start-local.sh` 启动，数据库通过 Docker Compose 管理。

Worktree 协同开发、分支同步、合并发布及冲突处理见 [Git Worktree 协同开发使用手册](GIT_USAGE.md)。

## 目录

- `lanhu`: 前端大屏。
- `SmartMonitor-wangzj`: Java 后端服务。
- `mtx`: MediaMTX 配置和 C++ `ai-stream` 流处理服务。
- `python/reid`: 行人 ReID 算法服务。
- `python/vad`: 异常行为检测算法服务。
- `python/sam3`: SAM3 算法代码，默认不启动。
- `python/garden`: garden 算法代码，默认不启动。
- `llm-service`: 大模型服务，默认不启动。
- `scripts`: Docker 部署辅助脚本。

## 一键启动

目标机器需要安装 Docker、Docker Compose 插件，并允许当前用户使用 Docker。默认启动链路不强制依赖 NVIDIA Docker runtime。

WYF 工作区本地启动方式、端口配置和故障定位详见 [WYF 本地开发启动](LOCAL_WORKTREE.md)。
```bash
bash scripts/start.sh
```

本机使用 Git worktree 开发时，启动与关闭方式见 [Worktree 本地运行说明](LOCAL_WORKTREE.md)：

```bash
bash scripts/start-local.sh --check
bash scripts/start-local.sh
bash scripts/stop-local.sh
```

默认使用主目录 `/home/guest/hxjm` 的公共 BoT-SORT；每个开发项目都启动自己的 MediaMTX、摄像头源、前端和后端。只有检测 WebSocket 订阅主目录算法服务，各页面共享框和 ID。视频默认连续 WebRTC 播放，算法慢或暂时不可用只影响检测框；“同帧验收”可选，画面更新率会受算法吞吐限制。

必要启动脚本已经纳入版本控制。主目录执行 `bash scripts/start-local.sh` 时启动公共 BoT-SORT 和主目录自己的媒体服务；其他 worktree 启动自己的媒体服务，并在算法可用时订阅公共检测，算法未启动时仍可播放自己的原始视频。主目录执行 `bash scripts/stop-local.sh` 时只停止 BoT-SORT，其他 worktree 的媒体服务不受影响。`local-ports.env`、`.run/`、模型权重仍是本机文件。部署、公共服务维护和独立算法实验命令见 [BoT-SORT 部署说明](python/video_analysis/BOTSORT_DEPLOYMENT.md)。

首次启动仍需 Docker、MediaMTX、Java 8、Maven、Node.js 18+、CMake、PyYAML 和现有 `/home/guest/anaconda3/envs/botsort39/bin/python` 环境。启动器构建当前目录 Java/C++、运行当前前端源码，不执行 Git 拉取、合并或推送，不自动安装或修改 Conda 依赖。业务数据库共用，Redis 逻辑数据库与应用端口按各目录原配置隔离。

运行记录位于 `.run/local-runtime/`，应用日志位于 `log/local/`，公共服务日志位于主目录 `.run/shared-botsort/`。默认 `START_ALGORITHMS=no`，不会再启动旧 DeepSORT。需要单独实验算法时显式使用 `VIDEO_ANALYSIS_MODE=local`，这会额外占用模型资源，不属于公共部署默认行为。

本地开发算法时，`python/reid` 仍按原方式运行：

```bash
conda activate reid
cd python/reid
python server.py
```

VAD 与 SAM3 使用各自独立的 Conda 环境，可一次性创建：

```bash
bash scripts/setup_algorithm_envs.sh
```

分别启动：

```bash
conda activate vad
python python/vad/server.py

conda activate sam3
python python/sam3/server.py
```

SAM3 首次启动会按 Ultralytics 的模型机制获取 `sam3.pt`，需要可访问外网且磁盘空间充足。GPU 驱动不可用时可以完成环境安装和导入检查，但实际推理会退回 CPU，速度会很慢。

Docker 部署时不需要手动激活 conda。`ai-reid` 镜像基于 GPU 版 PyTorch 镜像构建，并通过 `python/reid/requirements-docker.txt` 固化了 `reid` conda 环境里的运行依赖。

如果需要启用 GPU runtime，先确认宿主机 `nvidia-smi` 和 Docker GPU 测试都正常，再使用 GPU override：

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

VAD 默认不启动；需要异常行为检测时使用 VAD override 和 profile：

```bash
docker compose -f docker-compose.yml -f docker-compose.vad.yml --profile vad up -d --build
```

启动后常用地址：

- 前端: `http://localhost:3000`
- 后端: `http://localhost:8080`
- MediaMTX WebRTC: `http://localhost:8889`

更多部署、检查和关闭命令见 [DOCKER_DEPLOY.md](DOCKER_DEPLOY.md)。

执行： /home/guest/hxjm/video_ai_decoupling/start_demo.sh
cd /home/guest/hxjm/video_ai_decoupling

bash start_demo.sh
wyfwyf__newnewnew

asfdsafsdafadsf

sdfsdfdsf

test1

hahahahaha
