# `llm_agent_service` AI 模块完成度评估报告

> 评估日期：2026-09-10  
> 评估范围：`llm_agent_service/` 当前 Git HEAD 中的源码、文档，以及该目录直接引用的 LLM 与数据库访问模块。  
> 评估重点：AI 对话、记忆管理、工具调用、Agent 范式、RAG 和上线所需的基础工程能力。

## 1. 结论摘要

`llm_agent_service` 当前已经完成了一个面向智慧监控场景的**单轮问答与业务查询 Demo**：可以接收文本或图片，根据关键词和熟人姓名进入普通问答、ReID 人员轨迹查询、VAD 异常查询等固定流程，并调用 InternVL 模型生成回答或汇总数据库中的报告。

但它还不是一个真正的通用 AI 对话 Agent。当前实现本质上是：

```text
HTTP 请求
  -> 硬编码关键词/姓名匹配
  -> 固定 Python 业务流程与 SQL 查询
  -> 可选的 LLM 单次生成/总结
  -> 固定结构 JSON
```

下列核心能力尚未形成闭环：

- 没有会话 ID、上下文历史、短期/长期记忆或记忆检索。
- 没有可用的工具注册表、工具协议、模型自主选工具和工具调用循环。
- 没有 ReAct、Plan-and-Execute、状态机或其他 Agent 执行框架。
- 没有基于向量的知识库检索；现有 PostgreSQL 查询属于结构化业务数据检索，只能视为 RAG 的早期雏形。
- 缺少测试、鉴权、限流、可观测性、依赖闭包和并发推理治理，尚不具备生产就绪条件。

按“完整 AI 对话 Agent 服务”目标估算，整体完成度约为 **22%**。若只按“智慧监控固定场景的单轮查询 Demo”衡量，业务链路约完成 **60%**。这两个数字衡量的目标不同，不应混用。

## 2. 评估方法与完成度

评分采用静态源码审查与最小可运行性检查，重点判断能力是否存在真实代码闭环，而不是仅依据 README 描述。

| 模块 | 权重 | 当前完成度 | 加权得分 | 判断 |
|---|---:|---:|---:|---|
| AI 对话基础 | 35% | 45% | 15.75 | 已有单轮文本/图片推理和业务响应；没有多轮、流式、会话治理 |
| 记忆管理 | 15% | 0% | 0 | 未实现 |
| 工具调用 | 15% | 5% | 0.75 | 只有硬编码函数调用；工具注册源码缺失 |
| Agent 范式 | 15% | 5% | 0.75 | 只有规则路由，没有 Agent 循环 |
| RAG | 15% | 20% | 3.00 | 有结构化数据库检索后总结；无向量知识检索链路 |
| 工程与生产化 | 5% | 25% | 1.25 | 有 Flask、配置和错误兜底；依赖、测试、安全和观测不足 |
| **总计** | **100%** | — | **21.5 ≈ 22%** | **可演示，非完整 Agent，非生产就绪** |

完成度为本次代码评审使用的工程估值，用于排期与识别缺口，并非自动化测试覆盖率。

## 3. 当前真实架构

### 3.1 入口与请求链路

- `main.py` 创建 PostgreSQL Engine、加载 InternVL LLM，并启动 Flask 服务。
- `app.py` 暴露：
  - `POST /chat`
  - `POST /reload_persons`
  - `GET /persons`
  - `GET /health`
- `ReidService.process()` 按固定优先级路由：
  1. 包含“超分” -> 返回前端跳转指令，算法本身未实现。
  2. 包含“异常” -> 查询 VAD 数据并汇总。
  3. 命中缓存中的熟人姓名 -> 查询人员轨迹和报告并汇总。
  4. 其他情况 -> 直接调用 LLM 单轮回答。

### 3.2 外部模块依赖

该服务没有独立封装完整的模型和数据层，而是直接依赖仓库内其他服务：

- LLM 实现来自 `llm_report_service/llm/model.py`。
- 图片预处理来自 `llm_report_service/llm/vision.py`。
- ReID、轨迹、报告查询来自 `llm_chat_service/db/`。
- VAD 查询来自 `llm_api_service/db/vad_repo.py`。

这能复用已有代码，但也导致 `llm_agent_service/requirements.txt` 无法单独表达或安装该服务的完整运行依赖。

## 4. 当前已完成的工作

### 4.1 AI 对话基础

已完成：

- 提供统一 `/chat` HTTP 接口，兼容 JSON、表单、文件上传和 base64 图片。
- 支持 InternVL 文本生成与图片理解。
- 普通问题可直接调用 LLM 返回文本。
- 人员和异常查询可将数据库报告拼接成提示词，再让 LLM 生成不超过 100 字的摘要。
- LLM 调用失败时有基础的异常捕获和降级文案。
- 输出采用中文友好的结构化 JSON，可携带摘要、统计、关键帧和回放地址。

局限：

- 当前是严格的单轮请求。底层模型调用明确使用 `history=None`、`return_history=False`。
- `llm_report_service` 虽然定义了流式模型包装器，但当前 `build_llm()` 返回非流式 `InternVLChatLLM`，Flask 接口也没有 SSE/WebSocket 流式输出。
- 没有 system prompt、角色消息、消息协议、停止生成、取消请求、token 预算或上下文裁剪机制。
- 上传任意图片后，`app.py` 会强制把用户问题改为“帮我找任路阳”；包含“黑衣服”和“白色鞋子”时也会改写为固定人员查询。这是临时代码，会破坏真实的多模态对话语义。

### 4.2 结构化业务检索

已完成：

- 自动加载并定时刷新启用的熟人名单，支持手动刷新。
- 支持今天、昨天、前天、具体年月日等基础时间表达式。
- 支持按人员和时间查询轨迹、事件报告，并统计摄像头分布。
- 支持按时间查询异常记录及关联报告。
- 支持读取关键帧 base64，并为轨迹/VAD 构建回放 URL。
- VAD 关联查询失败时，会降级为直接查询 VAD 表。

局限：

- 路由仅依赖“超分”“异常”和熟人姓名的字符串匹配，无法理解改写、指代、同义表达或复合意图。
- 默认时间是“今天”，无法处理时间段、相对小时、范围组合和多轮省略。
- 摄像头无法解析时使用 Python `hash()` 随机映射到 `camera_1..4`，可能产生不真实的数据归属。
- 查询存在明显 N+1 模式：逐条查询摄像头、VAD 报告和媒体信息，数据量增加后延迟会快速上升。

### 4.3 服务基础设施

已完成：

- 基础 Flask 应用、CORS、反向代理头支持和健康检查。
- PostgreSQL 驱动候选回退与 `pool_pre_ping`。
- 熟人缓存更新使用锁保护写入。
- Python 源码可通过 `compileall` 语法编译检查。

## 5. 尚未完成的核心模块

### 5.1 记忆管理：0%

当前没有任何对话记忆实现：

- 请求中没有 `conversation_id`、`session_id` 或 `user_id`。
- 没有消息表、会话表、内存缓存或 Redis 状态。
- 没有保存 user/assistant/tool 消息。
- 没有最近 N 轮窗口、摘要记忆、长期记忆或用户画像。
- 没有记忆检索、过期策略、删除接口、隐私隔离或并发版本控制。
- LLM 每次调用都显式传入空历史。

这意味着“他昨天出现在哪里？”之后继续问“那今天呢？”时，第二个请求无法理解“他”指谁。

### 5.2 工具调用：约 5%

当前代码中存在若干可被工具化的 Python 能力，例如时间解析、人员查询、轨迹查询、异常查询、报告查询和回放构建，但它们都由业务代码直接调用，不是模型工具调用。

缺失项：

- `tools/tool_registry.py` 源文件不存在，但 `tools/__init__.py` 仍导入它，导入 `llm_agent_service.tools` 会直接失败。
- 没有工具名称、描述、JSON Schema、参数校验和统一返回协议。
- 没有模型 function calling/tool calling 请求与响应解析。
- 没有调用超时、重试、权限、幂等、并发限制和审计日志。
- 没有将工具结果作为 `tool` 消息回填模型的闭环。
- README 中描述的 `/tools` 接口实际不存在。

### 5.3 Agent 范式：约 5%

当前不存在 ReAct 或其他 Agent 执行器。`service/react_agent.py` 不在当前 Git HEAD 中，目录里只有历史 `.pyc` 文件，不能视为可维护源码。

缺失项：

- 没有 Thought/Action/Observation 或原生 tool-call 循环。
- 没有最大步数、停止条件、执行状态、计划修正和失败恢复。
- 没有任务状态机、检查点、人工确认或可恢复执行。
- 没有工具权限边界和高风险动作审批。
- 没有 Agent trace、步骤级耗时、token 与调用成本统计。

因此，README 标题“ReAct 模式”和其中的工作流、工具列表与当前源码不一致；`功能说明.md` 中“规则路由 + 数据检索 + LLM 总结”的描述更符合现实。

### 5.4 RAG：约 20%

当前已有“检索后生成”的基本形态：先按人员、时间、异常等结构化条件查询 PostgreSQL，再把最多 10 段已有报告交给 LLM 汇总。这可以称为**结构化业务数据增强生成**。

但还没有通常意义上的知识库 RAG：

- 没有文档摄取、清洗、切块和元数据设计。
- 没有 embedding 生成与更新任务。
- 代码没有使用 pgvector 相似度查询；文档提到的 `embedding`/`repr_embedding` 字段未进入当前检索链路。
- 没有 query rewrite、混合检索、过滤、rerank 或召回质量评估。
- 没有上下文去重、token 预算、来源编号和答案引用。
- 没有“证据不足则拒答”的 groundedness 约束。
- 数据库中已生成的 `llm_report` 被再次总结，容易累积上游模型错误。

## 6. 文档、依赖与可运行性问题

### 6.1 文档与代码不一致

- README 宣称存在 `service/react_agent.py` 和 `tools/tool_registry.py`，实际均不存在。
- README 宣称提供 `/tools` 和 `/chat_with_image`；实际只有统一 `/chat`，没有 `/tools`。
- README 启动参数包含 `--max-iterations`；`main.py` 没有该参数。
- `功能说明.md` 对“当前不是通用 ReAct Agent”的说明是准确的，应作为现状基线并同步 README。

### 6.2 依赖不闭包

`requirements.txt` 只声明 Flask、Werkzeug 和 SQLAlchemy，但当前源码或直接依赖还需要至少 PostgreSQL 驱动、PyTorch、Transformers、Pydantic、LangChain Core、Pillow、torchvision、NumPy、decord、pytz，以及可选的 flask-cors。

在本次评估所用 Python 环境中：

- `llm_agent_service.config`、`llm_agent_service.db.session` 可导入。
- LLM 模块因缺少 `pydantic` 无法导入。
- `reid_service`/`app` 因缺少 `decord` 无法导入。
- `llm_agent_service.tools` 因源码缺失必然无法导入。

前两类错误可能与当前环境未安装项目完整依赖有关，但至少能证明该目录的 requirements 无法独立部署服务；工具模块错误则是确定的源码缺口。

### 6.3 测试缺失

未发现针对该服务的单元测试、API 测试、数据库集成测试、模型 mock 测试或 Agent/RAG 评测集。当前只能确认 Python 语法通过，不能证明请求链路在目标数据库和模型环境中可运行。

## 7. 生产风险

| 优先级 | 风险 | 影响 |
|---|---|---|
| P0 | 图片请求和服装关键词被强制改写为固定人员 | 返回错误对象，用户输入语义丢失 |
| P0 | 默认数据库地址、用户名和明文密码写在 CLI 默认值中 | 凭证泄露与误连生产库风险 |
| P0 | 无鉴权、无限流、CORS 全开放 | 数据与 GPU 推理接口可被滥用 |
| P0 | 无输入体积限制，且日志打印 base64 前缀和完整问题 | OOM/DoS、图像或敏感信息泄露 |
| P0 | 服务依赖不完整、工具包悬空导入 | 无法可靠构建和部署 |
| P1 | Flask threaded 模式直接共享单个本地大模型，无推理队列或锁 | GPU OOM、线程安全与延迟抖动 |
| P1 | VAD/摄像头/媒体查询存在 N+1 | 高延迟和数据库压力 |
| P1 | API 将内部异常字符串直接返回客户端 | 暴露内部实现和数据库信息 |
| P1 | schema 直接插入 SQL，未做标识符白名单校验 | 配置被污染时存在 SQL 风险 |
| P1 | 存储报告原文直接进入总结提示词 | 间接提示注入与错误累积 |
| P2 | 后台刷新线程没有接入 Flask 生命周期关闭 | 测试、重载和优雅退出不完整 |
| P2 | `CUDA_VISIBLE_DEVICES="1"` 在代码中硬编码 | 部署不可移植，设备参数行为受限 |

## 8. 待完成工作与推荐顺序

### P0：先得到可信、可测试的单轮服务

- 删除两处固定人员 prompt 改写，保留原始用户意图。
- 明确产品基线：若当前阶段采用规则编排，则重写 README；若必须交付 Agent，则恢复并重构工具/Agent 源码。
- 补齐锁定版本的运行依赖，提供可重复的启动方式和环境变量示例。
- 将数据库密码、模型路径、GPU 选择迁移到环境变量/密钥配置，移除不安全默认值。
- 增加请求大小、图片格式、图片像素、prompt 长度和超时限制。
- 增加最小测试集：
  - 时间解析单元测试。
  - 普通、ReID、VAD、超分四类路由测试。
  - 文本与图片 `/chat` API 测试。
  - 数据库和 LLM 使用 fake/mock，确保 CI 不依赖 GPU。
  - 空结果、数据库失败、模型失败的降级测试。
- 验收标准：新环境可按文档一次启动；CI 全通过；用户 prompt 不被静默篡改；基础接口有稳定契约。

### P1：完成真正的多轮 AI 对话

- 定义统一消息模型：`system/user/assistant/tool`、`conversation_id`、`message_id`、时间戳和元数据。
- 建立会话与消息持久化，至少支持最近 N 轮历史。
- 将历史传入模型；超过上下文预算时使用滑动窗口与摘要压缩。
- 增加会话创建、读取、清空/删除接口，并实现用户级数据隔离。
- 接入流式输出（优先 SSE），支持客户端断开、取消和生成超时。
- 增加模型调用队列或独立推理服务，限制并发并记录首 token/总耗时。
- 验收标准：可以正确完成指代、省略和连续追问；会话互不串扰；服务重启后按策略恢复历史。

### P1：工具调用与 Agent 最小闭环

- 将现有确定性函数封装成只读工具：
  - `parse_time_range`
  - `find_person`
  - `list_person_tracklets`
  - `list_person_reports`
  - `list_vad_anomalies`
  - `build_playback`
- 为每个工具定义 JSON Schema、Pydantic 参数/返回模型、超时、错误码和权限标签。
- 优先使用模型原生 tool calling；模型不支持时再实现受约束的 JSON 输出解析。
- 实现有限步 Agent 循环：模型选择工具 -> 校验 -> 执行 -> 写入 tool 消息 -> 模型生成最终答案。
- 设置最大步骤数、总超时、结果长度上限、重复调用检测和失败降级。
- 对工具调用记录 trace，但不向最终用户暴露模型内部思维过程。
- 验收标准：用自然语言的同义表达也能选对工具；无效参数不会执行；循环一定能在预算内终止。

### P1/P2：建设可评估的 RAG

- 先明确知识源：制度文档/设备手册等非结构化知识，与轨迹/VAD 等结构化实时数据分开治理。
- 建立文档摄取、切块、embedding、版本、删除和增量更新流程。
- 使用 pgvector 或独立向量库实现带租户、时间、摄像头等元数据过滤的相似度检索。
- 对实时结构化问题优先使用 SQL 工具；对知识问答使用向量/关键词混合检索，不要把所有问题都塞进同一种 RAG。
- 增加 rerank、上下文去重、token 预算、来源引用和低置信度拒答。
- 建立离线评测集，衡量 Recall@K、引用正确率、答案忠实度和端到端任务成功率。
- 验收标准：答案能返回可核验来源；删除/更新文档后索引同步；证据不足时不编造。

### P2：生产化与持续评估

- 增加 JWT/API Key、RBAC、限流、审计和敏感字段脱敏。
- 增加结构化日志、request/trace ID、Prometheus 指标和模型/工具调用追踪。
- 合并批量 SQL，消除 N+1 查询，并补充时间与关联字段索引。
- 增加健康检查层级：进程、数据库、模型就绪状态分开。
- 增加灰度、回滚、模型版本和 prompt 版本记录。
- 建立覆盖普通问答、工具选择、多轮记忆、RAG 忠实度和安全攻击的回归集。

## 9. 推荐目标架构

```text
API 层
  -> 鉴权 / 限流 / 请求校验 / SSE
  -> Conversation Service
       -> 会话消息存储 + 短期窗口 + 摘要/长期记忆
       -> Agent Orchestrator（有限状态、有限步数）
            -> LLM Gateway
            -> Tool Registry
                 -> 人员/轨迹 SQL 工具
                 -> VAD/报告 SQL 工具
                 -> 回放工具
                 -> 知识检索工具
            -> RAG Pipeline
                 -> 文档摄取/切块/Embedding
                 -> 混合检索/Rerank/引用
       -> Trace / Metrics / Audit / Evaluation
```

建议保留现有规则路由作为高置信、低延迟的快捷路径或 Agent 失败时的 fallback，而不是继续让所有能力堆积在 `ReidService` 单个类中。

## 10. 最终判断

当前最有价值的资产不是 ReAct Agent，而是已经跑通的监控业务查询逻辑、数据表访问、结构化前端响应和本地多模态模型接入。这些能力适合被重新封装为 Agent 的受控只读工具。

下一阶段不建议先追求复杂多 Agent。应依次完成：**移除临时代码与补测试 -> 多轮会话与记忆 -> 统一工具协议与有限步单 Agent -> 可引用 RAG -> 安全、观测和评测**。完成前两阶段后，服务才可称为可用的 AI 对话服务；完成工具与 RAG 闭环后，才可称为较完整的领域 Agent。

## 附录：关键代码证据索引

| 结论 | 代码证据 |
|---|---|
| `/chat` 是唯一聊天入口 | `llm_agent_service/app.py:84-146` |
| 图片与服装描述会被强制改写 | `llm_agent_service/app.py:122-133` |
| 真实实现为四分支规则路由 | `llm_agent_service/service/reid_service.py:741-791` |
| 人员报告由 LLM 二次汇总 | `llm_agent_service/service/reid_service.py:331-350`、`:412-432` |
| VAD 数据与报告检索后汇总 | `llm_agent_service/service/reid_service.py:504-646` |
| LLM 调用不传递历史 | `llm_report_service/llm/model.py:140-148`、`:207-217` |
| 服务实际构建非流式 LLM | `llm_report_service/llm/model.py:242-249` |
| 工具注册表为悬空导入 | `llm_agent_service/tools/__init__.py:3` |
| README 中的 ReAct 文件/API 与源码不一致 | `llm_agent_service/README.md:15-27`、`:59-70` |
| 服务依赖声明不完整 | `llm_agent_service/requirements.txt:1-3` |
| 数据库凭证与 GPU 选择存在硬编码默认值 | `llm_agent_service/main.py:8`、`:30-35` |


最合适的改造顺序
建议分四步，不要一次把所有东西重写：
1. 将 InternVLChatLLM(LLM) 改成 ChatInternVL(BaseChatModel)，完成 invoke()、stream() 和多轮消息转换。
2. 将所有业务中的 ._call() 改成 .invoke()，并使用 SystemMessage、HumanMessage。
3. 使用 LangGraph MessagesState + checkpointer 管理会话历史，不在模型实例内部保存历史。
4. 把 ReID、VAD、轨迹和 RAG 封装成工具或图节点，再根据 InternVL 的工具调用可靠性决定是否让模型自主选工具。
