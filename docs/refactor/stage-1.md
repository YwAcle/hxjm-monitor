# 第一阶段进展（2026-11-05）

第二阶段已迁移物理路径；本文件保留第一阶段检查记录，当前目录、构建限制与检查命令见 stage-2.md。

## 已修改

- 开始时为 codex/compose-deployment，工作区干净。本阶段只在当前副本修改；没有创建分支、提交、合并或远端同步。
- Agent 入口原先同时初始化 ReidService/GallerySearchService、数据库工具和动态工具。现已只通过动态 Capability 调正式业务，保留两项纯本地辅助工具，移除提示词里的旧工具路由；截图续接迁移到 Business 端。
- 在既有 events/reports 定义外增加 identities/tracklets 定义及可信 HTTP 操作配置；部署配置生成器同步补齐 tracklets.query 操作权限。没有另建注册平台。
- 视频 Worker 的具体算法选择移到声明式 Adapter 工厂；调度器和 frame_result 使用 tracking 属性。新增算法描述接口，保留原视频、ReID、垃圾检测的实际执行方式。
- task_output 查询和视频历史查询增加同一 result_context 公共投影；未修改结果存储、去重或 Spool 文件格式，无新数据库迁移。
- 提供设备最小协议与向既有终态接口的回报转换。未运行硬件操作。
- 报告模块拥有的共享模型传输、设置及图像工具移动到 modules/ai-infra/python/ai_infra，同步源码与直接相关测试导入，不添加旧路径转发层。

## 旧调用与衔接边界

旧 find_person、list_known_persons、query_person_tracklets、query_person_reports、query_reports_by_time、query_vad_events 不再注册；分别由身份、轨迹、报告、事件 Business 能力替代。Agent 不再启动人员缓存，不再依赖业务库就绪。

图片、文字、截图检索和明确选人已迁至 modules/business/python/business_api，并增加四份 gallery-* 能力定义。原图库及特征协议保留，正式 Agent 不直接装配图库服务。截图选择从 Agent 私有调用改为标准任务工具，保留原候选卡片和任务引用。旧 ReidService 仍为未装配的历史模块，不能作为正式调用回退；部分直接测试该旧模块或旧应用装配的历史测试尚未迁移，不声称全套 Agent 测试通过。

设备 SDK、设备资源授权/范围、长任务取消与 lease 策略留待设备接入阶段。原 resource_scope 仍只支持 global/camera。没有测试真实硬件或为其登记假实例。

本阶段没有执行能力登记、数据库操作、服务重启或真实模型调用。使用新 Agent 前，必须在目标副本启用并配置既有 Executor、登记四份基础业务及四份图库定义并配置现有服务身份；仅代码编译和模拟检查通过不等于已部署。

## 验证与环境

- JDK 11 离线 `hxjm-algdeployment -am test-compile` 通过。系统默认 JDK 21 与原 Lombok 不兼容；不改全局 JDK、不升级项目依赖。
- ResultContextCheck 使用权威 JSON Schema 验证 once/continuous 元数据、空观测时间和素材引用，通过；BusinessSchemaCheck、BusinessResultCheck 亦通过，覆盖 Schema 子集、零目标、预测目标、503 个目标和非法引用/边界框。
- 第一组 68 项 Python 检查通过：Agent API/Registry/Bridge、模型配置/API 模式/报告客户端、算法扩展、Worker、ResultSpool、设备回报。
- 补充组 53 项通过（与上组有重叠）：新增能力 Schema/失败语义、Agent API、视频调度器、ReID API。另有最终接口组 29 项通过，覆盖通用图片上下文绑定、失败码、Agent 无数据库启动/资源释放、算法描述 Schema 和设备回报；不累加重叠项。
- 首轮试跑暴露环境路径和历史测试问题：虚拟环境 Python 链接指向旧挂载点；使用当前仓库实际解释器及现有 site-packages 运行，未安装依赖。历史 test_vllm_service 仍引用已不存在的 start_vllm.sh；历史 test_full_results 预期源码中已无的 full_results 参数/500 条截断，不扩展修复这些旧行为。
- Maven dependency 插件未缓存，离线生成 classpath 不可用；Java 独立检查只使用当前已有 backend jar 提取的依赖，不下载。

## 继续工作命令

工作目录均为 `/data/nfs_storage/hxjm-yh/hxjm-monitor`。

```bash
JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64 mvn -o -f apps/backend/pom.xml -pl :hxjm-algdeployment -am test-compile -DskipTests -q
```

预期完成相关 Java 编译，不接触数据库。Python 检查使用仓库内解释器和已有依赖，通过 apps/python.sh 配置模块路径；具体命令见 stage-2.md。

以下是需要用户在目标副本准备好配置后显式执行的能力登记，不在本阶段自动执行：

```bash
python3 contracts/capability-v1/tools/register.py --namespace YOUR_NAMESPACE contracts/capability-v1/events.json contracts/capability-v1/reports.json contracts/capability-v1/identities.json contracts/capability-v1/tracklets.json contracts/capability-v1/gallery-{image,screenshot,description,select}.json
```

要求设置 CAPABILITY_BUSINESS_URL、CAPABILITY_SERVICE_ID、CAPABILITY_SERVICE_TOKEN，且已有 V1 迁移与执行配置生效；预期逐项返回 capability_code 和 instance_id。定义冲突时停止，不自动覆盖已有契约。接口详情见 interfaces.md。

当前接口组可执行命令（使用已有依赖，不安装）：

```bash
HXJM_TEST_PATH="$PWD/apps/llm/.venv/lib/python3.11/site-packages:$PWD/apps/llm/.venv-vllm-qwen/lib/python3.11/site-packages:$PWD/apps/llm/.capability-deps"
PYTHONPATH="$HXJM_TEST_PATH" HXJM_PYTHON="$PWD/apps/llm/.runtime-cache/python/cpython-3.11.15-linux-x86_64-gnu/bin/python3.11" bash apps/python.sh -m unittest tests.agent.test_agent_api tests.agent.test_tool_registry tests.agent.test_capability_bridge tests.agent.test_reid_config video_analysis.tests.test_algorithm_contract devices.tests.test_contract -q
```

该基础接口组预期 29 项模拟/边界检查通过；没有真实模型推理或网络业务请求。

## 图库迁移后的最终验证

- 83 项 apps/llm/图库检查通过：test_gallery_business_api、test_gallery_search、test_reid_screenshot、test_clipreid_client、test_text_reid_client、test_agent_api、test_tool_registry、test_capability_bridge、test_reid_config、test_agent_stream。覆盖真实 Flask Business 路由与模拟 Capability 任务 Adapter，未调用真实数据库或模型。
- 截图普通/SSE 两轮选择、工具引用记忆、服务器框防篡改、一次性消费、过期/取消、服务鉴权、输入 Schema、懒加载失败与资源释放均有针对性检查。
- 上述测试发现的旧 app.ReidService 装配已在直接相关图库及流式测试中替换。旧 multipart 聊天组合测试由新 Capability 图库集成检查替代；multipart 远端协议仍由 ClipReIDTests/ScreenshotProtocolTests 独立检查。

启用图库前还需在目标环境配置 GALLERY_BUSINESS_URL、图库数据库与已有特征服务，并执行上述显式登记命令。未执行服务启停、能力登记或真实模型验收；本地代码与模拟检查通过不能代替部署验收。

- 补充运行时组 109 项通过（与先前组有重叠，不累加）：Agent 日志/请求限制、模型设置/API 模式/报告客户端、算法契约、Worker、Analyzer、ResultSpool、设备及 ReID API。

- 最终静态检查：71 个新增/修改 Python 文件语法、相关 JSON 解析、start_agent.sh 语法和 git diff --check 通过。部署 render 在内存捕获输出，验证配置/不配置 GALLERY_BUSINESS_URL 两种情况；未写配置文件或访问数据库。
