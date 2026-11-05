# 分组启停

工作目录：HXJM 仓库根目录。三个入口复用原有 Compose、JoyAI 和 Agent 管理，不自动安装依赖、下载模型、初始化数据库或向机器狗下发动作。

## 主监控

本副本默认读取 `deploy/config/deployment.local.env`，日常启动无需手动导出环境变量：

```bash
bash scripts/main.sh start
```

本机 JoyAI 配置、独立 Python 3.12 环境及模型保存在 `.run/joyai/`；配置和模型不提交。JoyAI 使用 34301–34304 端口，Qwen 按需加载到独立 GPU。后端通过私有授权配置访问工具接口。四路视频使用本副本 MediaMTX，来源及流 ID 取自当前 Business API 中唯一有效的原始流，不依赖流名称。

本机正式数据库为本项目独立容器中的 `hxjm_monitor_v1`（MySQL）与 `hxjm_business_v1`（PostgreSQL），由统一初始化入口创建；原 `hxjm_sm`、`hxjm` 库保留。原跟踪投递队列保存在运行目录的 `analysis/tracking-results-before-v1-20261105`，不会投递到新库。日常 start 不清库、不重复初始化。

本机共享内存负载较高，私有 deployment 配置设置 `VIDEO_ANALYSIS_MEMORY_RESERVE_GIB=1.5`、`VIDEO_ANALYSIS_MODEL_HEADROOM_GIB=2.5`，即加载前至少 4 GiB 可用、运行中保留 1.5 GiB；Compose 默认仍为 8+4 GiB。2026-11-05 已完成四路真实跟踪、Business 成果登记、JoyAI 四路观察，以及 Qwen 真实 8 帧复核请求的并行检查。复核检查没有写入业务事件或报告，Qwen 检查后释放，日常按需加载；这些检查不代表异常检测准确率评估。

```bash
bash scripts/main.sh start --config deploy/config/deployment.local.env
bash scripts/main.sh status --config deploy/config/deployment.local.env
bash scripts/main.sh stop --config deploy/config/deployment.local.env
```

启动前端、Business/Capability 后端、MediaMTX、推流控制、BoT-SORT/ReID，再启动 JoyAI 观察与按需 Qwen 复核。启动先检查 JoyAI 权重与配置；失败会退出，不假装主监控已完整启动。中途启动失败时保留已启动服务，修正配置后可重新执行 start 或显式 stop。

首次必须完成 [部署准备](../../deploy/README.md) 中的 render、数据库初始化/升级、能力登记，以及 [JoyAI prepare、模型环境与后端授权配置](monitor-device-integration.md)。脚本从同一 deployment 配置导出 RUNTIME_ROOT、DATA_ROOT 和 GPU 配置给 JoyAI；私有 JSON 可用 JOYAI_CONFIG 指定。不会自动执行 setup/prepare。源码需重建时 start 增加 `--build`，仅重建 Compose 服务。

stop 停止本副本主监控与 JoyAI，保留数据库、数据、Agent 和垃圾检测容器；但共享后端与媒体停止后，垃圾业务的查询、成果投递和设备任务协调也会暂停。需要垃圾业务继续运行时不要执行主服务整组 stop，改用原入口 `scripts/stop.sh --only analysis,reid` 并单独停止 JoyAI。没有 JoyAI 配置时仍尝试停止 Compose，最终返回非零并显示错误。

## Agent

```bash
bash scripts/agent.sh start                   # 自动复用或启动本地 vLLM 模型
bash scripts/agent.sh stop
```

沿用 `apps/llm/.env` 与 [Agent 原入口配置](../../apps/llm/README.md)，同时管理 Agent、报告 Worker，以及由原入口创建的本地模型。停止不会关闭复用的外部模型。业务查询依赖公共后端；此入口不自动启动主服务。私有模型连接不使用 deployment 配置替代。

## 垃圾检测与机械狗独立业务

```bash
bash scripts/robot-dog.sh start --config deploy/config/deployment.local.env
bash scripts/robot-dog.sh status --config deploy/config/deployment.local.env
bash scripts/robot-dog.sh stop --config deploy/config/deployment.local.env
```

只启停独立 `garbage-analysis`，不切换或停止主监控算法。页面仍是正式前端 `/garbage-cleanup`；设备 Adapter 和任务执行器在公共 Java 后端内，没有另一套应被此入口启动的机器狗守护服务。公共前端、后端、媒体必须已启动；不需要主监控推理时可用原入口 `scripts/start.sh --only frontend,backend,mediamtx,stream` 启动这些共享服务。

首次配置 GARBAGE_ENABLED、GARBAGE_GPU_UUID、GARBAGE_MODEL_PATH，按部署入口 render、加载后端配置并 register。清理默认 disabled；模拟需显式 CLEANUP_MODE=simulation 和 CAPABILITY_EXECUTOR_ENABLED=true，详见 [设备对接说明](robot-dog-integration.md)。此入口不更改清理模式、不登记真实设备、不执行路线或抓取；真实设备动作仍须现场授权。stop 不取消已提交任务、不发送机器人停止命令，公共后端仍会管理已有任务。

main/robot-dog 支持 `--config`、`--scope`，start 另支持 `--build`；不接受 `--only`，避免破坏分组隔离。省略 action 或使用 `--help` 只显示帮助。

## Agent 业务配置与共享权限

当前本地 Agent 配置已对齐本副本的 hxjm-pipeline 身份、宿主机 Business 地址和已发布 PostgreSQL/ReID 端口。后端图库回调使用 `http://host.docker.internal:8002`；这是容器访问宿主机的地址，不用容器自身回环地址。配置、生成配置和已运行后端分别核验，写入 env 不表示后端已重新加载。

正常部署顺序：生成配置，构建并重新加载后端，登记能力，最后 `bash scripts/agent.sh start`。这会影响当前副本后端，操作前应与正在使用该副本的人员协调：

```bash
bash scripts/start.sh --render
bash scripts/start.sh --only backend --build
bash scripts/start.sh --register
bash scripts/agent.sh start
```

无需选择 api/local。启动前业务检查失败直接报错，不以静态工具、旧数据库地址或模拟成果回退。

部署私有配置和 Agent 私有配置均设置 `HXJM_SHARED_UIDS=1006,1021`，对应 va 与 spjk 的实际数字身份。bootstrap、JoyAI 配置以及新报告投递文件使用公共共享文件写入函数：先在同目录写入临时文件并设置显式读写 ACL，再原子替换；不再用 chmod(0600) 屏蔽协作身份。ACL 不受支持或权限不足直接失败，不覆盖旧配置，不自动 chmod 777。其他账号需在这两个私有配置中追加实际 UID。Git 不保存 ACL；新服务器检出后还需配置工程目录的访问/默认继承 ACL。模型、第三方工具及其输出权限不由该函数保证。

### 本次实际验证（2026-11-05）

当前副本已 render、重建并重新加载后端、register，实际 `/execution/status` 为 enabled；八项业务/图库工具及报告生成实例已登记。图库数据库查询和 ReID `/health` 通过。通过正式 Agent ToolRegistry 提交了真实事件查询，任务 `f1048e52-5544-4d17-8e80-4a5efd634154` 进入 succeeded，保存 1 项 Business 查询成果；该检查没有让模型决策，也没有模拟业务返回。

Java 在 JDK 17 下离线 test-compile/package（跳过测试执行）通过，正式后端 Docker 构建（JDK 8）通过。报告 API 请求、失败回执重试、ACL 重写及拒绝时保留旧配置等针对性 Python 测试通过。新增 Java Runtime 内联成果回归夹具已编译，未启动其要求的独立 stage3 数据库执行。

本地 vLLM 单独导入在 60 秒内未完成。随后一键启动在 tmux 缺失处停止；已尝试获授权安装，但 sudo 要求交互密码。需在本机终端 `sudo apt-get install -y tmux` 后再次 `bash scripts/agent.sh start`。目前未验证真实模型加载、图文请求、模型驱动工具调用或模型报告生成；不将工具桥真实查询通过描述为完整 Agent 联调通过。
