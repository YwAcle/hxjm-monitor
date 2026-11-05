# 六层目录与依赖

逻辑层、代码模块与进程分别管理；目录不代表新增服务或数据库。

```text
hxjm-monitor/
├── modules/
│   ├── access/{web,garbage-web}/
│   ├── agent/python/llm_agent_service/
│   ├── capability/java/hxjm-capability/
│   ├── business/
│   │   ├── java/{hxjm-algdeployment,hxjm-basedata,hxjm-interfaceservice}/
│   │   └── python/{business_api,llm_report_service}/
│   ├── perception-devices/
│   │   ├── python/{frame_hub,video_analysis,reid_feature_service,deepsort,devices,garbage_detection}/
│   │   ├── stream/                  # C++ 推流及其 cppzmq 依赖
│   │   └── vendor/{botsort,reid}/   # 正式使用的第三方算法源码
│   ├── infrastructure/
│   │   ├── java/{hxjm-common,hxjm-framework,hxjm-system,hxjm-quartz,hxjm-generator}/
│   │   ├── python/base/
│   │   └── database/{bootstrap,migrations}/
│   └── ai-infra/python/ai_infra/
├── apps/{backend,llm}/             # Maven reactor / Spring Boot 与 LLM 装配
├── apps/python.sh                 # 显式模块搜索路径，不安装或复制包
├── contracts/capability-v1/
├── deploy/{containers,config}/     # Compose、镜像与部署配置
├── scripts/{start.sh,stop.sh}
├── tests/{agent,deployment,performance}/
├── references/                    # 非正式依赖，见下表
└── docs/refactor/
```

## 迁移映射与维护边界

| 旧位置 | 当前唯一维护位置或处理 |
| --- | --- |
| lanhu | modules/access/web |
| garbage_detection/static、open.html | modules/access/garbage-web；现有检测进程继续提供静态访问 |
| Agent/llm_agent_service | modules/agent/python/llm_agent_service；进程装配移到 apps/llm/agent.py |
| Agent/business_api、llm_report_service | modules/business/python；Agent 不直接导入它们 |
| Agent/ai_infra | modules/ai-infra/python/ai_infra |
| Agent/scripts、环境和模型 | apps/llm；本地资源保留，未删除权重或录像 |
| Agent/tests | tests/agent；旧运行时专属测试退役，其余随公开接口调整 |
| SmartMonitor-wangzj | apps/backend Maven reactor，库源码按职责迁到 modules/*/java |
| business/service/Capability*、CapabilityTaskController | 独立 hxjm-capability Maven 模块、capability Java 包，仍由 hxjm-admin 装配 |
| python/frame_hub、video_analysis、reid_feature_service、deepsort | modules/perception-devices/python；deepsort 是原人员检测实现名称 |
| python/tracker/BoT-SORT | modules/perception-devices/vendor/botsort |
| python/reid/CLIP-ReID、config/cnn_base.yml、已有 weights | modules/perception-devices/vendor/reid；权重仍为本地资源，不加入镜像源码 |
| python/base、base/postgresql | modules/infrastructure/python/base；旧 PostgreSQL 初始化在第三阶段退役，当前基线见 database/migrations |
| mtx（不含重复 Python） | modules/perception-devices/stream |
| deploy/init | modules/infrastructure/database/bootstrap；init 镜像仍挂载 /opt/init |

Capability 仅保留通用 capability_call 输入语义；直播、录像、图片、活动、事件、查询对象的授权、状态和到期校验移到 BusinessTaskInputs。Capability 通过其公开方法取得 sources/expiry，不再自行读取这些输入对象的内部表。Business 的查询、证据、报告服务仍管理业务事实；Capability 自身表及成果登记机制保持 V1。

Java 依赖是 hxjm-admin → hxjm-capability → hxjm-algdeployment → 基础模块；Business 不反向依赖 Capability Maven 模块。保持原 artifactId、Spring 根扫描范围、HTTP 路径和原配置前缀，补齐 Capability 的标准异常处理范围。跨模块集成检查由 hxjm-admin 的 src/test 装配。

Python 包名称保持稳定，物理路径通过 apps/python.sh 或现有 LLM 脚本显式配置；没有旧目录符号链接、转发模块或复制包。AI Infra 不导入 Agent/Business；Agent 不导入业务实现或数据库客户端。apps/llm/agent.py 是两者同进程装配点。

持续视频仍是 FrameHub → Video Analysis → ResultPublisher/Spool → Business；不经 Agent 或逐帧创建任务。前端可直接请求 Business；自然语言交互才走 Agent → Capability。设备只保留 devices 协议，机器狗导航、底盘和机械臂不进入正式模块。

## 参考工程与第三方来源

| 位置 | 定位 |
| --- | --- |
| references/robot-control | 原 code_only 的外部机器人控制参考，包含唯一保留的 m20_client 工具；不启动、不导入正式模块 |
| references/robot-monitor-ui | 原 robotDog 的独立 Vue/Mock 面板，不是主 React 前端 |
| references/robot-video-demo | 机器狗视频协议与模拟演示，保留供外部接口联调参考 |
| references/video-ai-prototype | 原 video_ai_decoupling，视频叠加原型；使用的检测源码路径已更新，不作为正式服务 |
| references/legacy-algorithms | 旧 ZMQ/ReID/SAM/FastSAM/VAD、演示和非正式算法；不纳入正式镜像或 PYTHONPATH |
| references/stream-variants | mtx/python 去重后剩余的 32 个差异/独有文件，仅供核对，不是可独立运行的第二源码树 |
| references/legacy-admin-ui | 原 ruoyi-ui 管理/演示工程，不纳入主前端构建 |
| references/garden-llm、database-snapshots | 未接入的园区原型与历史数据库设计快照，不自动执行 |

mtx/python 的 775 个逐字节相同的版本管理文件已删除。BoT-SORT 内部 FastReID 与 CLIP-ReID 是不同方法/模型依赖，不按相似目录名合并；旧算法参考树中也可能保留不同实现，但正式镜像只复制 vendor 这一来源。m20_client 顶层九个文件与 code_only/m20_client 全部相同，前者已去重。

第三方许可及原 README 随源码保留。本仓库未提供可信的上游 commit 标记，不能把现有副本称为某个已验证上游版本；source-inventory.json 记录迁移基线、源码树摘要及出处。原有本地模型兼容、跟踪行为等修改均原样保留，本阶段不重新实现模型。需要更新第三方版本时先核对本地差异及权重/特征契约。

数据库已由第三阶段统一治理，当前表归属、初始化与升级入口见 [database.md](database.md)。


第四阶段增量：`modules/perception-devices/java/hxjm-device-adapters` 保存 M20 外部协议适配，由现有 Java 应用装配；`modules/access/web/src/pages/GarbageCleanup.jsx` 是主前端 `/garbage-cleanup` 页面。算法仍维护在原 garbage_detection，video_analysis/garbage_adapter.py 仅转换运行接口；Business 服务与清理协调分别维护在原 Business/Capability Maven 模块。参考机器人控制工程没有移入正式硬件执行链。
