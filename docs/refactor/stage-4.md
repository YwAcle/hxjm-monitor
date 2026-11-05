# 第四阶段：业务接通与垃圾清理框架

当前分支仍为 `codex/compose-deployment`。保留前三阶段工作区；未创建分支、提交、合并、推送或清理历史。仅修改本仓库，没有连接其他部署或真实设备。

## 现有代码审查及归属

| 分类 | 实际代码 | 处理 |
| --- | --- | --- |
| 直接复用 | perception-devices/python/garbage_detection/detector.py | Grounding DINO Tiny，本地模型，PIL RGB 图片输入，已有分块/NMS/类别提示；返回 label、confidence、0..1000 bbox、推理耗时。没有重训或另写模型 |
| 适配复用 | robot-control 的 remote_service.py、tools/m20_remote_client.py、m20_client/web/app.js | 提取真实 WebSocket 路线命令与状态语义到正式 Java Device Adapter，消除硬编码地址；不是 HTTP 机器人任务 API |
| 仅作参考 | robot-video-demo，robot-monitor-ui | 前者是 H264/RTSP 视频桥接与遥测，后者包含 mock/协议草案；不是已验证清理接口，不采用草案替代真实协议 |
| 外部职责 | robot-control 内 route_main、arm_task_adapter、底盘/UDP/机械臂控制 | 不纳入 HXJM 执行进程，保留现有参考，不做本阶段仓库清理 |

旧独立垃圾 Web/服务继续作为已有图片/快照应用保留；主系统新页面不调用它的摄像头线程或机器人逻辑。设备相关参考中没有已完成的监控像素坐标到机器人导航转换，也没有目标级稳定 task_id。

## 正式调用链和代码

- 既有 Agent 仍通过请求级 CapabilityBridge、动态目录、原 Task/HTTP Adapter 调用 Business；不新增静态工具或 Repository 路线。init `register` 现在实际登记 events/reports/identities/tracklets，配置 gallery 地址时登记其能力，清理能力不暴露给 Agent 自主执行。
- 视频持续流程保持摄像头/FrameHub → Analyzer/Worker → AlgorithmSpec → ResultPublisher/Spool → `/results/register`。`garbage_adapter.py` 包装现有 Detector，将 BGR 转 RGB、0..1000 框转归一化 xyxy；不产生人员轨迹，不调用设备。
- `algorithms.py` 增加 garbage 声明；Publisher 按冻结的 result_type 将成果登记到 `algorithm_result`，保留 run/source/time/schema/producer key、确认和恢复机制。无逐帧 Capability 执行，无连续帧写入 task_output。
- `GarbageBusinessService.record` 在标准成果保存事务中登记 `business_event(event_type=garbage.detected)` 和 `evidence_reference`。按来源+类别+3×3区域+捕获时间5分钟桶聚合；相同成果重传不重复创建事件。此规则跨桶会生成新事件，不承诺目标生命周期跟踪。
- `GarbageController` 提供公共查询/提交入口；手动创建原 Capability once 任务，关联 event_id。`CapabilityPlatform` 持有设备会话并管理原 Task Attempt 的 lease/终态；Device Adapter 不接触业务数据库。
- 新 Maven `hxjm-device-adapters` 属于 Perception & Devices，由现有 Spring Boot 后端装配，未增加服务或机器人调度器。Capability 的业务协调仍在同一进程。
- 唯一新增数据库迁移 `0002_device_execution/postgres.sql`，只增加 task_attempt.external_execution 和清理任务事件索引，不增加独立机器人任务/事件表。MySQL 无结构变化。

## 页面和部署入口

正式 React 页面 `/garbage-cleanup`，主监控页有入口；复用 businessApi HTTP 客户端。可看检测时间、来源、类别、区域、置信度、成果/证据引用、任务和执行反馈，手动提交，5秒刷新。不依赖旧监控 WebSocket Provider，不向机器人发控制指令。当前持续成果没有自动保存截图，页面如实显示未提供截图，不用假图代替证据。

算法部署沿用 analysis 服务，新增 `ANALYSIS_RUNTIME=garbage` 构建依赖（已有 torch2.5 环境加 transformers），配置 `VIDEO_ANALYSIS_ALGORITHM=garbage`、`VIDEO_RESULTS_CAPABILITY_CODE=garbage.detection`、`VIDEO_RESULTS_SOURCE_MAP=garbage-sources.json`、本地 GARBAGE_MODEL_PATH 和 GARBAGE_DEVICE。Compose 默认 cuda，继续要求显式分配 analysis GPU；直接 Python 运行支持显式 cpu。一个 Runtime 实例只运行一种算法，本阶段没有让跟踪和垃圾检测在同一 Worker 中混跑。

Docker COPY、Maven reactor、Compose 参数、start 模型预检、bootstrap render/register、权威能力定义均同步更新。算法登记为垃圾模式时不依赖 ReID 特征流水线。公共业务与设备注册复用原登记工具，不另建 Registry。

## 已验证与实际限制

- Java Capability 及依赖离线 test-compile、应用源码/测试 javac、原5项业务与装配检查通过。
- 隔离开发库升级至 PostgreSQL 0002、MySQL 0001；数据库14项检查通过。真实 SQL + 正式服务/Controller + 显式模拟 Adapter 验证成果登记、重传去重、事件查询、重复提交同一任务、模拟终态、task_output 与页面 API；夹具回滚。另验证持久化未知任务阻止新派发。
- Python 当前接口74项检查通过（Agent Bridge/Registry、算法、Publisher 持久化/恢复、录像交付、模块/启动入口）；新增垃圾 Publisher 整个落盘/关闭流程3项通过；配置与布局8项通过。
- React 75项测试、Vite生产构建通过；原包体积警告保留。M20ProtocolCheck 回放真实格式，验证历史快照隔离、快速终态、断线未知、无像素导航和模拟忙碌；不开设备 socket。
- 旧 test_result_delivery 仍针对已退役 result_sink/public_frame_ref/camera_source_ids，运行失败，未为旧机制恢复兼容层；正式 ResultPublisher 用 test_persistence 与 test_garbage 验证。
- 完整 Boot 打包仍缺少离线缓存的 Spring Boot Maven 插件；没有声明产出新完整发布镜像。未安装/构建垃圾模型依赖镜像、运行模型/GPU/真实摄像头、启动完整平台或连接真实机器狗。

任务终态和设备反馈已回写事件投影；当前真实协议仅确认路线完成，事件保持待核实，不伪称某件垃圾已清除。接手人员需要确认真实地址、路线/目标转换、稳定任务状态接口和目标级完成证据，见 `robot-dog-integration.md`。

收尾已停止本次验证启动的 hxjm-refactor-stage3 PostgreSQL/MySQL 容器，保留开发库和版本记录；未停止其他服务。日志位于忽略目录 `.run/refactor-stage4/`，没有写入或展示凭据。
