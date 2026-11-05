# HXJM 视频监控平台

正式源码按六层职责组织，部署进程继续复用现有 React、Spring Boot、Python 和媒体服务。目录与依赖映射见 [模块说明](docs/refactor/module-layout.md)，公共接口见 [接口说明](docs/refactor/interfaces.md)，数据库维护见 [数据库规范](docs/refactor/database.md)，已接入流程和限制见 [第四阶段记录](docs/refactor/stage-4.md)。

| 位置 | 维护内容 |
| --- | --- |
| modules/access | 主 React 前端（含 `/garbage-cleanup`）、原独立图片检测页面 |
| modules/agent | Agent 决策循环、上下文和 Capability Tool Bridge |
| modules/capability | Java 能力目录、HTTP/设备 Adapter 协调、任务与执行器 |
| modules/business | Java 业务服务、Python 图库和报告生成 |
| modules/perception-devices | FrameHub、视频运行时、算法、设备适配、C++ 推流 |
| modules/infrastructure | 通用 Java/Python 基础组件、数据库初始化与迁移 |
| modules/ai-infra | 公共模型配置、LLM/VLM 客户端 |
| apps | 后端 Maven reactor、LLM 进程装配和 Python 模块运行入口 |
| contracts | 跨模块契约的权威来源 |
| references | 非正式部署的实验、演示、外部机器人和历史实现参考 |

在仓库根目录执行现有业务端入口：

日常分组启停见 [启停说明](docs/refactor/service-control.md)：`bash scripts/main.sh start|stop|status`（主监控）、`bash scripts/agent.sh start|stop`（Agent）、`bash scripts/robot-dog.sh start|stop|status`（独立垃圾/机械狗业务）。

```bash
bash scripts/start.sh --help
bash scripts/start.sh --config deploy/config/deployment.local.env --status
bash scripts/start.sh --config deploy/config/deployment.local.env
bash scripts/stop.sh --config deploy/config/deployment.local.env
```

首次部署、配置生成与数据库初始化以 [部署说明](deploy/README.md) 为准。Agent/报告服务仍单独管理，入口为 `apps/llm/scripts/start.sh`、`apps/llm/scripts/stop.sh`，见 [LLM 应用说明](apps/llm/README.md)。模块移动后须重新构建相关镜像再部署，旧镜像不能证明新源码生效。

Python 模块使用 `HXJM_PYTHON=/path/to/project/python bash apps/python.sh -m <package>`；Maven 入口为 `apps/backend/pom.xml`，后端仍只有一个 Spring Boot 应用。不将 references 加入正式 PYTHONPATH 或 Compose，不启动或修改其他工作区的服务。


新增同类型能力时维护自己的服务/Adapter 和 `contracts/capability-v1/` 定义，通过现有注册入口接入；不要修改 Agent 决策循环或复制任务平台。垃圾清理复用主系统事件和 Capability，真实机器狗协议及剩余对接工作见 [接手说明](docs/refactor/robot-dog-integration.md)。模拟运行不表示真实设备集成完成。

基本构建命令（使用本项目对应环境）：

```bash
mvn -f apps/backend/pom.xml -pl :hxjm-admin -am package -DskipTests
npm --prefix modules/access/web ci
npm --prefix modules/access/web run build
```

数据库新环境使用现有 `--init-db`（仅空库），已采用版本记录的开发库使用 `--upgrade-db`；两者均执行唯一的 `modules/infrastructure/database/migrations/`。历史数据库快照不随此分支发布，不使用旧快照替代当前迁移。


当前检查范围：前端测试与生产构建、Java 库编译和应用装配检查、Python 当前接口检查已通过；本机完整 Maven package 仍受离线缓存缺少构建插件限制。真实模型、摄像头和机器狗需在配置完成后另行联调，详见阶段记录。

主监控 BoT-SORT 与 JoyAI/Qwen 并行、垃圾业务独立启动及设备操作接手方式，见 [当前整合说明](docs/refactor/monitor-device-integration.md)。
