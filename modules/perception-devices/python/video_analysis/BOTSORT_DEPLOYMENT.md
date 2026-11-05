# BoT-SORT 运行与构建

正式维护的模型源码位于 modules/perception-devices/vendor/botsort，Video Analysis Adapter 通过该唯一来源加载 YOLOX/FastReID/BoT-SORT。多摄像头调度仍保留独立的 tracker/GMC/帧序号和状态，Worker 共享既有模型，不因页面连接新增模型进程。

部署入口统一为仓库 scripts/start.sh、scripts/stop.sh，配置见 deploy/README.md。原 scripts/start-local.sh、deploy/botsort/shared_service.py 等共享工作区管理器已退役，不再读取或管理其他工作区。

在仓库根目录按本副本配置执行：

```bash
bash scripts/start.sh --config deploy/config/deployment.local.env --only analysis --build-only
bash scripts/start.sh --config deploy/config/deployment.local.env --only analysis
bash scripts/start.sh --config deploy/config/deployment.local.env --only analysis --status
bash scripts/stop.sh --config deploy/config/deployment.local.env --only analysis
```

启动前须配置本项目模型目录、显卡 UUID、来源和已有 Business 身份。Compose 将模型只读挂到 /models，BOTSORT_ROOT=/models/botsort；源码仍来自镜像或本工作区 vendor，不复制模型。缺少模型不得以模拟推理冒充通过。

持续成果经 ResultPublisher/ResultSpool 直接进入 Business；不逐帧创建 Capability 任务。持久化配置继续使用 VIDEO_RESULTS_* 和现有 business.json，不能把 task_output 当作视频帧存储。

轻量回归通过 apps/python.sh 使用本项目已有环境：

```bash
HXJM_PYTHON=/path/to/project/python bash apps/python.sh -m unittest video_analysis.tests.test_algorithm_contract video_analysis.tests.test_worker video_analysis.tests.test_analyzer video_analysis.tests.test_result_spool -q
```

具体接口和本次实际验证范围见 docs/refactor/interfaces.md、docs/refactor/stage-2.md；这些回归不执行真实模型推理。
