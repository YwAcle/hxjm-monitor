# 主监控算法与设备操作整合

开发基于 `refactor/modular-platform-v1@68fdac0`。只读核对并获取 `master@5939272`、`hxjm-tzh@34b8770`，逐文件移植，没有合并旧分支。所有修改留在当前本地工作区，未提交、推送或合并。

## 当前正式运行关系

主监控共用摄像头来源和 MediaMTX，分别运行：

- `analysis`：固定 `botsort`，`BoTSortPipeline` 加载 YOLOX `bytetrack_x_mot17.pth.tar`、BoT-SORT 和 FastReID `mot17_sbs_S50.pth`。Grabber/FrameHub → 独立跟踪状态 → ResultPublisher/Spool → Business `/results/register`；目标框通过原分析流进入 MonitorGrid，轨迹/身份仍由 Business 管理。独立 `reid` 服务继续提供 ClipReID 查询特征。
- `scripts/joyai-tool.sh`：`modules/perception-devices/python/joyai_tool` 运行 JoyAI 观察、证据采集、Qwen 复核和投递恢复。它独立读取同一 MediaMTX；共用 source_id、camera_stream_id 和 ingest_clock 时间语义，自建 stream_session_id，不强行共享 track_id。
- `garbage-analysis`：独立镜像/依赖、端口、GPU、运行目录、能力实例、来源映射和投递队列。使用已有 Grounding DINO，不影响 `analysis`。垃圾页面仍为 `/garbage-cleanup`，共享 Business/Capability/数据库，不启动第二套平台。

主监控不依赖机器狗或垃圾运行实例。Compose 不再允许通过 `VIDEO_ANALYSIS_ALGORITHM=garbage` 替换主跟踪服务；初始化登记也固定先登记 botsort，`GARBAGE_ENABLED=true` 时额外登记 garbage。首次额外登记不会继承跟踪实例 ID。

## JoyAI 复用与边界

从 tzh 迁入 monitor、observer、input、evidence、verdict、review_runtime、ledger、publisher、contracts、app 和测试，以及告警卡片、回放和报告交互。保留四路独立上下文、轮询、约 5 秒前后证据、10 秒/4fps、8 帧时序复核、Qwen 按需加载与空闲释放、双模型同类确认规则。没有改 Prompt、阈值或重新开发模型。

`joyai_tool/input.py` 复用当前 stream_grabber 的解码和时钟映射。JoyAI 的连续会话接口仍由原 live_adapter 负责；视觉复核使用 OpenAI 兼容模型请求，没有为了复用 Agent 的 LangChain 客户端而改变模型消息、采样或资源策略。AI Infra 的 Agent 模型配置不被覆盖。

成果经公共 API 登记为 `behavior.assessment/1`，事件为 `behavior.fight/fall`，证据使用 media_asset/evidence_reference，报告使用 `joyai_anomaly_review`；人工复核创建新任务和新报告，保留原报告及原始 JoyAI 判断，只重新运行 Qwen。SQLite 只保存本地工作、待投递请求和恢复信息。

旧 CLIP/Pose 生产入口在此前重构中已退出正式算法目录，本次没有恢复。旧 VAD 告警查询与旧报告消费限制为 fire；主屏计数改为正式已确认行为事件加旧 fire。新行为卡片使用公共报告查询，不再展示旧 fight/fall 告警。保留原跟踪、陌生人和火灾相关功能及历史表，不做数据库重构。

## 公共接口

- 前端 `GET /api/v1/business/behavior/status`：后端访问配置中的 Runtime，按当前调用者来源过滤状态和队列；不向浏览器返回私有模型地址或 token。
- 前端 `POST /api/v1/business/behavior/reviews`：只接受 `report_id`，先校验报告类型、来源和期限，再协调 Runtime。未配置或未连接时拒绝，历史事件仍可查询。
- 事件/报告/证据/回放继续使用现有 `/events/*`、`/reports/search`、`/reports/query`、`/assets/*`。历史报告按公共游标分页读取。
- Runtime `POST /api/v1/business/tasks/end`：`request_id,task_id,run_id,expected_revision,state,result_ids`，失败另需 `error_code`。仅服务身份且拥有当前 runtime_managed 执行可调用。校验修订号、期限、成果所属 run 和请求的输出类型；一次性成功必须引用成果。连续观察正常结束可不带成果。
- `/tasks/complete|fail` 仍服务 platform_managed，保持 execution_token/lease 约束；未用它绕过 Runtime 模式。

成功复核的任务终态为 succeeded（即使业务结论是排除/证据不足）；模型超时和格式错误不算成功，人工任务以 failed/REVIEW_TIMEOUT 或 REVIEW_INVALID_RESPONSE 收尾。持续观察遇到模型失败保留本地待重试状态，不生成确认告警。完成请求丢失回执时保留原始幂等请求并重试，收到回执后才将工作标为 published。真正中止可使用 Runtime cancelled；设备失联保存 unknown 原因，绝不自动重发动作。

## 启动

工作目录为仓库根目录。先按 `deploy/README.md` 填写当前副本的私有 deployment.local.env。不要使用其他项目环境或稳定数据目录。

```bash
# 主监控基础服务和跟踪/ReID（已有权重、镜像、GPU 配置）
bash scripts/start.sh --config deploy/config/deployment.local.env

# JoyAI 准备与运行：复用相同副本配置，不将字面量配置当 shell 执行
source scripts/start.sh
configure --config deploy/config/deployment.local.env
bash scripts/joyai-tool.sh prepare
# prepare 新增 config/joyai-backend.yml 后重启当前副本 backend 加载服务授权。
# 首次接入需要重建当前后端/前端镜像；源码更新不会改变正在运行的旧镜像。
bash scripts/stop.sh --config deploy/config/deployment.local.env --only backend
bash scripts/start.sh --config deploy/config/deployment.local.env --only backend
bash scripts/joyai-tool.sh check
bash scripts/joyai-tool.sh start
bash scripts/joyai-tool.sh status
```

JoyAI 必须显式提供四个本机端口、JOYAI_GPU、JOYAI_REVIEW_GPU、DATA_ROOT、RUNTIME_ROOT、JOYAI_BACKEND_TOOL_URL。Compose 后端通过 host.docker.internal 访问主机工具时，配置 JOYAI_TOOL_BIND_HOST 为可达接口（示例 0.0.0.0），状态和写接口均校验服务令牌；模型端口仍只监听回环。`/health` 只返回就绪标志。host 证据根目录必须正是后端挂载到 `/data` 的 DATA_ROOT。

`JOYAI_CONFIG` 可指定当前副本的私有 JSON；默认 `.run/joyai/config.json`。`JOYAI_PYTHON` 指向专用模型环境。`setup` 是显式安装/下载操作，本次没有执行；它按上游固定 revision 准备 JoyAI 源码/INT4 模型。另需准备脚本 weights 检查的 Qwen3.8-27B-AWQ-INT4 完整本地视觉权重。未具备时 check/start 明确失败。无需改 Agent 的模型配置。启停脚本只处理此副本带随机归属标记的四类 JoyAI 进程，没有移植旧工程的跨目录资产链接、端口扫描或旧服务清理。

垃圾独立运行：私有配置设置 GARBAGE_ENABLED=true、GARBAGE_GPU_UUID、GARBAGE_MODEL_PATH；按既有部署流程 render 后重启加载配置，再执行：

```bash
bash scripts/start.sh --config deploy/config/deployment.local.env --register
bash scripts/start.sh --config deploy/config/deployment.local.env --only garbage-analysis --build
# 只停止垃圾检测，不影响主监控和公共组件
bash scripts/stop.sh --config deploy/config/deployment.local.env --only garbage-analysis
```

垃圾页面可以在机器狗离线时查询事件。真实设备派发仍默认关闭；本次未启动以上正式推理服务或发送硬件指令。

## 验证记录

实际检查：Maven 离线 test-compile（Capability 及依赖）、Admin 主类/集成检查编译、模块装配/契约/结果校验，前端测试与 Vite 构建，JoyAI/设备协议单测，部署配置和入口测试。独立 stage3 本地测试库运行 GarbageFlowCheck，验证标准成果、事件去重、Capability 模拟执行、成果持久化、页面 API、未知执行阻止再派发，三项设备操作契约经通用注册表执行，以及 Runtime succeeded 收尾和重复回执；事务回滚，测试库使用后停止。

没有安装模型依赖、下载权重、运行真实 JoyAI/Qwen/BoT-SORT 推理或连接真实机器狗。并行 GPU 容量、四路真实视频证据时钟、真实模型格式和真实设备反馈仍须在部署环境联调，当前检查不代表这些已通过。
