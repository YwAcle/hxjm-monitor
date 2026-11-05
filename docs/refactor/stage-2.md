# 第二阶段进展（2026-11-05）

## 实施结果

当前分支仍为 `codex/compose-deployment`。保留第一阶段已有改动，直接在本地工作区完成迁移；未创建分支、暂存、提交、合并或访问远端。未操作其他部署副本、真实设备或仓库外数据。

真实目录、旧新映射及参考工程分类见 [module-layout.md](module-layout.md)，公共接口见 [interfaces.md](interfaces.md)。六层是代码归属，不新增六套服务：Java 仍由 hxjm-admin 装配，Python 仍沿用现有 Agent、报告、视频运行时及特征服务。

- Capability 抽为 Maven 模块与独立 Java 包，复用原 Registry、Executor、Task、Result、HTTP Adapter。公开 V1 URL 不变。
- BusinessTaskInputs 负责业务输入的授权、状态和到期校验；Capability 通过其公开方法取得资源范围。原 V1 成果、特征、覆盖投影仍有共享数据库结构依赖，尚未全部服务化，不能据此宣称彻底消除跨模块 SQL。
- Agent 不再装配 Business 或导入数据库客户端。图库与 Agent 的同进程组合由 apps/llm/agent.py 完成；报告归属 Business，共享模型调用归属 AI Infra。
- 视频运行时、FrameHub、特征服务、检测及设备协议归属 Perception & Devices。垃圾页面归属 Access，仍由原服务提供；持续结果交付与一次性 task_output 保持各自存储，公共语义沿用同一 result_context Schema。
- Maven parent/module、Spring 包引用、Python 搜索路径、前端资源、Docker COPY、Compose 开发挂载、数据库初始化与启动脚本已切换新目录；没有旧目录转发层或路径别名。

## 退役与来源收敛

退役旧 llm_api_service、llm_chat_service、ReidService、空 Agent 数据库包，以及 Java AiTaskRunController/Service 的 Docker/Conda/进程启动路线；正式前端没有使用该旧路线。媒体访问配置归 Business，旧 AiTaskProperties 移除。旧专属测试与重复启动/打包脚本一起退役。

mtx/python 的 775 个逐字节相同的受版本管理文件删除，32 个差异或独有文件仅存 references/stream-variants。顶层 m20_client 九个重复文件删除，唯一副本随外部机器人控制参考保留。BoT-SORT 与 CLIP-ReID 各有唯一正式源码位置；其不同 ReID 方法不强行合并。第三方基线摘要及上游版本未知情况记录于 source-inventory.json。

机器狗导航、底盘、机械臂、独立面板和视频原型均在 references，不参与正式镜像及 PYTHONPATH。仅保留正式设备接口以便后续接入外部系统。移动时保留现有本地权重、环境及运行资源；未删除录像或真实模型。

## 实际验证

本地检查日志位于忽略目录 `.run/refactor-stage2/`，不作为正式构建产物提交。

| 检查 | 实际结果 |
| --- | --- |
| Agent 全组 | 248 项通过，含 1 项跳过（tmux 不可用） |
| 视频、ReID、设备组 | 70 项通过 |
| 垃圾检测单元组 | 26 项通过；测试自行创建运行目录，不依赖预存文件夹 |
| 模块布局 | 5 项通过，覆盖 Maven、源码边界、算法来源、Schema、镜像 COPY |
| 最后配置/启动器/布局回归 | 27 项通过，含 1 项跳过 |
| React | 74 项测试通过，Vite 生产构建通过 |
| C++ Stream | CMake 编译通过，CTest 1/1 通过 |
| Java 库模块 | JDK 11 离线 test-compile 通过 |
| Java 主应用和集成源码 | 40 个源码直接 javac 编译通过，5 个 main 检查通过，覆盖装配、业务范围与结果契约 |
| 静态检查 | 177 个 Python 文件 AST、requirements 引用、Shell 语法、两套 Compose 配置及 git diff --check 通过 |

React 检查在已有 hxjm/frontend:v0.2-compose1 镜像内、禁用网络执行，复用该旧镜像已有 Node 18 依赖；宿主 Node 12 不满足构建要求。未安装新依赖。Java 主应用直接编译复用原 jar 中第三方依赖，模块类优先使用新编译结果；原 jar 不是此次新打包产物。

**明确阻塞：** 完整 hxjm-admin Maven 打包所需 spring-boot-maven-plugin:2.5.15 不在离线缓存中。本阶段没有联网下载，因此未生成新的可部署后端 jar、未完整重建所有 Docker 镜像。JDK 21 与旧 Lombok 不兼容，检查使用现有 JDK 11。

没有进行真实数据库、模型推理、GPU、设备、能力登记或服务启停验收。静态装配和模拟回归不能替代部署验收。

## 当前入口与下一阶段衔接

以下命令工作目录均为仓库根目录。Java 库编译预期无数据库访问，成功时退出码为零：

```bash
JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64 mvn -o -f apps/backend/pom.xml -pl :hxjm-capability,:hxjm-framework,:hxjm-system,:hxjm-quartz,:hxjm-generator,:hxjm-basedata,:hxjm-interfaceservice -am test-compile -DskipTests -q
```

使用当前仓库已有 Python 依赖运行布局检查，预期 5 项通过：

```bash
HXJM_TEST_PATH="$PWD/apps/llm/.venv/lib/python3.11/site-packages:$PWD/apps/llm/.venv-vllm-qwen/lib/python3.11/site-packages:$PWD/apps/llm/.capability-deps"
PYTHONPATH="$HXJM_TEST_PATH" HXJM_PYTHON="$PWD/apps/llm/.runtime-cache/python/cpython-3.11.15-linux-x86_64-gnu/bin/python3.11" bash apps/python.sh -m unittest tests.deployment.test_module_layout -q
docker compose -f deploy/compose.yml config --no-interpolate --quiet
docker compose -f deploy/compose.yml -f deploy/development.yml config --no-interpolate --quiet
```

正式启动仍使用 scripts/start.sh、scripts/stop.sh；LLM 使用 apps/llm/scripts/start.sh、stop.sh，选项见现有 README。前端入口是 modules/access/web/package.json，后端 reactor 是 apps/backend/pom.xml，Docker 入口是 deploy/containers 与 deploy/compose.yml。部署前需按原配置流程重建镜像，不能直接沿用旧镜像判断新源码已上线。

后续阶段接续：配置外部机器狗协议实现与回报；准备运行环境后登记能力并做真实服务联调；按需要继续收敛原 V1 成果投影的共享表耦合。环境及配置中用户填写的旧绝对路径需按新目录显式调整，本次未修改全局环境。上游第三方版本仍待有依据时确认，不虚构版本号。
