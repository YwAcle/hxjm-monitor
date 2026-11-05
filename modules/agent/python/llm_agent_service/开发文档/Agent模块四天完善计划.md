# Agent 模块四天完善计划

> 计划周期：2026-09-14 至 2026-09-17  
> 汇报时间：2026-09-18（周五）  
> 目标模块：`llm_agent_service`  
> 核心目标：将当前“规则路由 + 固定业务函数 + LLM 总结”升级为一个可演示、可测试、可观测的智慧监控领域 Agent。

## 1. 本周目标

本周不追求通用多 Agent 平台，而是完成一个具备标准 Agent 最小闭环的领域 Agent：

```text
用户问题
  -> 会话上下文
  -> Agent 判断下一步动作
  -> 选择并调用只读业务工具
  -> 将工具结果写回上下文
  -> 必要时继续调用工具
  -> 生成有数据依据的最终回答
  -> 返回结构化结果和可观测信息
```

周五应能够明确证明以下能力已经形成闭环：

- 模型能够根据自然语言选择工具，而不只依赖硬编码关键词。
- Agent 能够连续执行多个工具，并在有限步骤内结束。
- 工具参数经过结构化校验，非法参数不会进入数据库查询。
- 同一 `session_id` 支持上下文追问，不同会话互不影响。
- 工具失败、模型失败和循环超限时都有明确降级行为。
- 每次请求可以追踪模型调用、工具调用、耗时和结束原因。
- 核心流程有不依赖真实 GPU 和数据库的自动化测试。
- 保留现有规则流程作为回退路径，降低四天改造风险。

## 2. 当前基线

### 2.1 已有能力

- 已有统一的 `POST /chat` 文本和单图片入口。
- 已支持 SGLang OpenAI 兼容接口和 Transformers 本地回退。
- 已使用 LangChain `BaseChatModel.invoke()` 调用模型。
- 已支持基于 `session_id` 的进程内短期记忆。
- 已有人员轨迹、VAD 异常、报告汇总、回放链接等业务逻辑。
- 已有 `/health`、`/ready` 和清空会话记忆接口。
- 已有 SGLang、图片调用、会话隔离和 dtype 等基础测试。

### 2.2 主要缺口

- 当前仍由 `_process_request()` 中的关键词和姓名匹配决定业务分支。
- `tools/__init__.py` 引用了不存在的 `tool_registry.py` 源文件，旧 `.pyc` 不能作为可维护实现。
- 没有统一工具输入、输出、错误和权限协议。
- 没有“模型选择工具 -> 执行工具 -> 回填结果 -> 再次决策”的循环。
- 没有最大步骤、总超时、重复调用检测和上下文结果裁剪。
- 业务逻辑集中在 `ReidService`，职责过多，难以独立测试。
- 没有请求级 `trace_id`、步骤日志、耗时统计和 Agent 结束原因。
- 当前 `/chat` 非流式，前端只能在完整生成结束后显示结果。
- 会话历史只保存在单进程内存中，服务重启后丢失。

## 3. 周五目标架构

```text
Flask API
  -> 请求校验与 trace_id
  -> AgentService
       -> SessionMemoryStore
       -> AgentExecutor（最大 4 步、总超时）
            -> Agent Prompt
            -> LLM Gateway（SGLang/Transformers）
            -> ToolRegistry
                 -> parse_time_range
                 -> find_person
                 -> query_person_tracklets
                 -> query_person_reports
                 -> query_vad_events
                 -> build_playback_links
            -> 规则路由回退
       -> TraceRecorder
  -> 统一 JSON 响应
```

建议本周先实现**受约束的结构化动作协议**，不要把交付押在 InternVL 原生 function calling 的稳定性上。模型每一步只能返回以下两种结果之一：

```json
{
  "action": "tool",
  "tool_name": "query_vad_events",
  "arguments": {
    "start_ts": "2026-09-13T00:00:00+08:00",
    "end_ts": "2026-09-14T00:00:00+08:00",
    "limit": 20
  }
}
```

或者：

```json
{
  "action": "final",
  "answer": "昨天共检测到 3 起异常事件，主要集中在 camera_2。",
  "citations": ["tool-step-2"],
  "navigate_to": "vad"
}
```

服务端使用 Pydantic 校验动作。选择工具时执行工具并将结果作为 `ToolMessage` 或等价观察消息回填；选择 `final` 时结束循环。

## 4. 范围和优先级

### P0：周五必须完成

- 工具注册表和统一工具协议。
- 至少 5 个只读业务工具。
- 有最大步骤限制的 Agent 执行循环。
- 工具参数校验、错误封装和结果长度限制。
- 会话历史接入 Agent 循环。
- 保留现有规则路由作为可配置回退。
- 请求级 trace 和步骤级结构化日志。
- Agent 核心单元测试、API 测试和固定演示用例。
- README、功能说明和演示文档与真实代码一致。

### P1：完成 P0 后争取

- SSE 流式输出，至少支持 `status`、`tool_start`、`tool_end`、`token`、`done`、`error` 事件。
- 将会话消息持久化到 PostgreSQL，服务重启后可恢复。
- 简单请求限流和输入大小限制。
- `/tools` 只读接口，用于展示已注册工具及其参数 Schema。

### 本周明确不做

- 多 Agent 协作、主管 Agent 或角色群聊。
- 自动执行写数据库、删除、控制摄像头等高风险工具。
- 完整知识库 RAG、文档切块、Embedding、Rerank 和知识库管理后台。
- 跨服务分布式任务队列和复杂工作流恢复。
- 用户画像、长期偏好学习和自动记忆提取。
- 大规模压测和完整生产安全认证。

这些能力可以列入汇报中的下一阶段路线图，但不应挤占本周 Agent 核心闭环时间。

## 5. 建议目录结构

```text
llm_agent_service/
  agent/
    __init__.py
    executor.py            # 有限步 Agent 执行循环
    prompts.py             # Agent 系统提示词和动作协议
    schemas.py             # AgentAction、AgentFinal、AgentStep
    trace.py               # trace_id、步骤耗时和结束原因
  tools/
    __init__.py
    base.py                # ToolSpec、ToolResult、ToolError
    registry.py            # 工具注册、查询和执行
    time_tools.py          # 时间解析工具
    person_tools.py        # 人员解析与人员查询工具
    tracklet_tools.py      # 轨迹查询工具
    vad_tools.py           # VAD 异常查询工具
    report_tools.py        # 报告检索工具
    playback_tools.py      # 回放链接工具
  service/
    agent_service.py       # API 与 AgentExecutor 之间的业务层
    memory.py              # 保留现有短期记忆
    reid_service.py        # 暂时保留，作为工具底层能力和规则回退
  app.py
  config.py
  main.py
tests/
  test_agent_schemas.py
  test_tool_registry.py
  test_agent_executor.py
  test_agent_api.py
  test_agent_scenarios.py
```

不要在第一天立即大规模拆分 `ReidService`。先用薄包装将已有查询能力暴露为工具，保证行为不变；核心闭环稳定后再移动代码。

## 6. 工具协议设计

### 6.1 工具定义

每个工具至少声明：

- `name`：稳定、唯一的英文标识。
- `description`：告诉模型何时使用，避免描述重叠。
- `args_schema`：Pydantic 输入模型。
- `handler`：实际执行函数。
- `timeout_s`：执行超时。
- `result_limit`：最大返回记录数或最大字符数。
- `read_only`：本周所有工具固定为 `True`。

建议统一结果：

```python
class ToolResult(BaseModel):
    ok: bool
    data: dict | list | None = None
    error_code: str | None = None
    error_message: str | None = None
    truncated: bool = False
    elapsed_ms: int
```

### 6.2 本周工具清单

| 工具 | 输入 | 输出 | 用途 |
|---|---|---|---|
| `parse_time_range` | 自然语言时间、当前时间 | 起止时间和标签 | 解析今天、昨天、前天、具体日期 |
| `find_person` | 姓名或查询文本 | 人员 ID、姓名、候选项 | 将自然语言人员描述解析成数据库实体 |
| `query_person_tracklets` | 人员 ID、起止时间、数量 | 轨迹、摄像头、时间 | 查询人员出现记录 |
| `query_person_reports` | 人员 ID、起止时间、数量 | 事件报告列表 | 获取人员行为分析依据 |
| `query_vad_events` | 起止时间、摄像头、数量 | VAD 事件和报告 | 查询异常事件 |
| `build_playback_links` | 轨迹或 VAD 标识 | 回放 URL、预览图 | 为前端返回可播放证据 |

工具返回数据必须满足：

- 只返回回答所需字段，不直接暴露完整数据库行。
- 时间统一为带时区的 ISO 8601 字符串。
- 图片 Base64 不放入模型上下文，只在最终 API 数据区按需返回。
- 默认限制记录数量，例如 20 条；总结果超过限制时设置 `truncated=true`。
- 数据库异常转换为稳定错误码，不把 SQL 和密码返回给模型或前端。

## 7. Agent 执行循环

### 7.1 推荐状态

```python
class AgentState(BaseModel):
    trace_id: str
    session_id: str
    user_prompt: str
    messages: list[BaseMessage]
    steps: list[AgentStep]
    started_at: datetime
    deadline_at: datetime
```

### 7.2 执行规则

1. 读取当前会话最近 N 条消息。
2. 加入 Agent 系统提示词、工具描述和当前用户问题。
3. 调用模型生成结构化动作。
4. 校验动作 JSON 和工具参数。
5. 如果是工具动作，执行工具并记录结果。
6. 将压缩后的工具结果写回消息上下文。
7. 重复步骤 3 至 6，最多 4 步。
8. 如果模型返回最终回答，结束并保存会话。
9. 如果超时、重复调用或达到最大步数，走确定性降级回答。

必须实现以下护栏：

- `max_steps=4`，防止无限循环。
- `request_timeout_s`，限制整个 Agent 请求时间。
- 相同工具和完全相同参数最多连续调用一次。
- 工具名不在注册表时，不执行任何函数。
- 参数校验失败时将简短错误作为观察返回，允许模型修正一次。
- 工具结果进入模型前裁剪，避免数据库大量结果撑爆上下文。
- 不向前端暴露模型内部思维过程，只返回工具步骤摘要。
- Agent 失败时调用现有 `_process_request()` 规则流程兜底。

## 8. 四天执行计划

### 第一天：工具基础设施和契约

### 上午

- 冻结当前 `/chat` 请求和响应样例，避免改造过程中破坏前端。
- 建立 `agent/schemas.py`，定义动作、最终回答、步骤和结束原因。
- 建立 `tools/base.py` 和 `tools/registry.py`。
- 修复 `tools/__init__.py` 对不存在源码的引用。
- 明确工具错误码：`INVALID_ARGUMENTS`、`NOT_FOUND`、`DB_ERROR`、`TIMEOUT`、`RESULT_TRUNCATED`。

### 下午

- 将时间解析、人员查询、轨迹查询、VAD 查询、报告查询封装成只读工具。
- 为每个工具增加 Pydantic 参数模型和返回裁剪。
- 工具内部优先复用现有 Repository 和 `ReidService` 能力，不复制 SQL。
- 增加 `GET /tools`，返回名称、描述和参数 Schema，不暴露处理函数。

### 当日测试

- 注册表拒绝重复工具名。
- 未知工具返回稳定错误。
- 缺少参数、错误类型和越界 `limit` 无法执行。
- 时间解析、空查询结果、数据库异常均有测试。
- 测试使用 fake engine/repository，不依赖真实数据库和 GPU。

### 第一天完成标准

- `/tools` 能列出至少 5 个工具。
- 可以在 Python 测试中通过注册表直接调用每个工具。
- 工具输入输出均可序列化为 JSON。
- 现有 `/chat` 行为和测试不回归。

### 第二天：Agent 决策和执行闭环

### 上午

- 编写 Agent 系统提示词，明确工具选择、证据使用和停止条件。
- 实现动作 JSON 提取和 Pydantic 校验。
- 实现 `AgentExecutor` 的有限步循环。
- 支持 `tool` 和 `final` 两类动作。

### 下午

- 将 `session_id` 历史接入 Agent 状态。
- 工具观察结果以结构化消息写回模型。
- 增加重复调用检测、最大步骤、总超时和上下文裁剪。
- 在 `AgentService` 中增加模式开关：

```text
AGENT_MODE=agent       使用新 Agent
AGENT_MODE=rules       只使用原规则流程
AGENT_MODE=hybrid      Agent 失败后回退规则流程，建议默认
```

- 保持 `/chat` 原响应字段兼容，只新增可选字段：

```json
{
  "trace_id": "...",
  "agent": {
    "mode": "agent",
    "steps": 3,
    "finish_reason": "final"
  }
}
```

### 当日测试

- 模型一次选择工具后给出最终回答。
- 模型连续选择两个工具后给出最终回答。
- 模型输出非法 JSON 后重试或回退。
- 模型选择未知工具时不执行。
- 模型重复调用相同工具时终止。
- 达到最大步骤后一定结束。
- 相同会话能理解“那今天呢”，不同会话不会串扰。

### 第二天完成标准

- 至少三个自然语言问题不依赖关键词路由即可完成工具选择。
- 一次请求能够完成至少两个工具的连续调用。
- Agent 在任何测试条件下都能在步数和时间预算内结束。
- `AGENT_MODE=rules` 可以一键回退现有实现。

### 第三天：可靠性、可观测性和可选流式输出

### 上午

- 为每个请求生成 `trace_id`，前端传入时沿用，否则由服务生成。
- 输出结构化日志，至少包括：
  - `trace_id`、`session_id`；
  - Agent 模式和步骤编号；
  - 模型耗时、工具耗时；
  - 工具名、参数摘要、结果数量；
  - 最终结束原因和错误码。
- 删除 Base64 前缀、完整图片和敏感数据库信息日志。
- 增加 prompt 长度、图片字节数、图片像素和请求体上限。

### 下午

- 优先完成 Agent 失败降级、数据库超时和模型超时测试。
- 如果上午任务稳定，再增加 `POST /chat/stream` SSE 接口。
- SSE 事件建议如下：

```text
event: status      Agent 开始处理
event: tool_start  即将调用某个工具
event: tool_end    工具完成，只返回摘要
event: token       最终回答文本片段
event: done        最终结构化响应
event: error       稳定错误码和可展示信息
```

- 若 SGLang 最终回答可以流式生成，则接入 `llm.stream()`；工具决策阶段仍可以非流式。
- 客户端断开后停止继续向客户端写入，并记录断开原因。

### 当日测试

- 每个请求都有唯一 `trace_id`。
- 日志中不出现图片 Base64 和数据库密码。
- 模型不可用、数据库不可用、工具超时均返回稳定结果。
- 若实现 SSE，验证事件顺序和结束事件，客户端断开不导致服务崩溃。

### 第三天完成标准

- 能通过一个 `trace_id` 还原该请求调用了哪些工具及其耗时。
- 主要失败场景不会返回堆栈或 SQL 给前端。
- `/health` 和 `/ready` 仍可正确区分进程存活与依赖就绪。
- 流式输出如果未达到稳定标准，可以保留在功能分支，不影响 P0 演示。

### 第四天：场景评测、联调和汇报材料

### 上午

- 建立 20 至 30 条小型 Agent 回归集，覆盖人员、轨迹、异常、时间、多轮和失败场景。
- 使用固定 fake 工具结果验证工具选择，不依赖线上数据波动。
- 在测试环境连接真实 PostgreSQL 和 SGLang 做一次端到端冒烟测试。
- 记录成功率、平均工具步数、P50/P95 延迟和失败分类。
- 修复阻塞演示的 P0 问题，停止新增非必要功能。

### 下午

- 准备周五演示数据，确保演示人员、日期、轨迹和 VAD 确实存在。
- 编写一键启动、健康检查和冒烟测试命令。
- 更新 README、功能说明、前端接口文档和架构图。
- 保存演示请求与预期结果，避免现场临时设计问题。
- 准备规则模式和 Transformers 模式作为回退方案。

### 第四天完成标准

- 自动化测试全部通过。
- 至少 5 个真实场景端到端执行成功。
- 演示脚本从服务启动到最终回答可以重复执行。
- 所有汇报数字都有日志或测试结果支撑。
- 周五原则上只演示和汇报，不再进行架构性改动。

## 9. 必测场景

| 编号 | 用户问题 | 预期工具链 | 验收点 |
|---|---|---|---|
| A01 | “张三昨天出现在哪里？” | 时间解析 -> 人员查询 -> 轨迹查询 | 返回真实摄像头和时间 |
| A02 | “把最近两段回放给我” | 使用上轮人员和时间 -> 回放工具 | 验证多轮指代 |
| A03 | “那今天呢？” | 使用上轮人员 -> 时间解析 -> 轨迹查询 | 验证省略和会话记忆 |
| A04 | “昨天有哪些异常？” | 时间解析 -> VAD 查询 | 不依赖“固定 VAD 流程”直接回答 |
| A05 | “哪一个摄像头异常最多？” | 时间解析 -> VAD 查询 -> 聚合回答 | 工具数据必须成为回答依据 |
| A06 | “总结张三昨天的行为” | 人员 -> 时间 -> 报告查询 | 报告为空时明确说明 |
| A07 | “你好” | 不调用业务工具或直接 final | 避免所有问题都查数据库 |
| A08 | “查询不存在的人” | 人员查询 | 不编造人员和轨迹 |
| A09 | 非法日期或超大 limit | 参数校验 | 不执行危险查询 |
| A10 | 模型反复选择同一工具 | 重复检测 -> 回退 | 有限步骤内结束 |
| A11 | 数据库断开 | 工具错误 -> 降级回答 | 不泄露 SQL 和凭证 |
| A12 | SGLang 不可用 | 模型错误 -> 统一错误 | `/ready` 返回 503 |
| A13 | 两个不同 session 同时提问 | 独立会话 | 历史不串扰 |
| A14 | 图片问答后追问 | 多模态回答 -> 文本历史 | 明确当前不持久化原图的边界 |

## 10. 测试分层

### 单元测试

- Pydantic 动作和参数模型。
- 工具注册、查找、参数验证和错误转换。
- 动作解析、最大步骤和重复调用检测。
- 会话历史裁剪和隔离。

### Agent 合约测试

使用脚本化 Fake LLM，依次返回预设动作：

```text
第 1 次：调用 parse_time_range
第 2 次：调用 query_vad_events
第 3 次：返回 final
```

这样可以稳定验证 Agent 循环，而不受真实模型随机性影响。

### API 测试

- `/chat` 文本、图片、非法参数和会话 ID。
- `/tools` Schema。
- `/health`、`/ready`。
- 如果完成 SSE，测试事件序列和错误事件。

### 端到端冒烟测试

- 真实 PostgreSQL + SGLang，只运行少量固定用例。
- 不将完整端到端测试作为每次单元测试的前提。
- 记录模型版本、Prompt 版本和测试数据时间范围。

## 11. 可观测指标

每次 Agent 请求至少记录：

```text
agent_requests_total
agent_requests_success_total
agent_requests_fallback_total
agent_request_duration_ms
agent_steps_total
agent_finish_reason
llm_calls_total
llm_call_duration_ms
tool_calls_total{tool_name,status}
tool_call_duration_ms{tool_name}
```

如果四天内不接 Prometheus，也应先通过结构化 JSON 日志记录同样字段，后续可以直接转成指标。

周五建议汇报以下数字：

- 注册工具数量。
- 自动化测试数量和通过率。
- 场景评测通过数与总数。
- Agent 工具选择准确率。
- 平均每个请求工具步骤数。
- 成功请求平均耗时、P95 耗时。
- 回退规则流程的次数和原因。
- 多轮会话隔离测试结果。

不要只汇报“已经接入 LangChain”或“已经实现 Agent”，要用可复现数据证明闭环。

## 12. API 兼容策略

现有前端请求保持不变：

```json
{
  "prompt": "张三昨天在哪里？",
  "session_id": "browser-001"
}
```

现有核心响应字段也保持不变：

```json
{
  "type": "normal",
  "text": "...",
  "session_id": "browser-001"
}
```

只增加可选字段：

```json
{
  "trace_id": "01J...",
  "agent": {
    "mode": "agent",
    "steps": 3,
    "tools": ["parse_time_range", "find_person", "query_person_tracklets"],
    "finish_reason": "final"
  }
}
```

生产环境可隐藏 `tools`，演示环境通过 `AGENT_DEBUG_RESPONSE=1` 开启。不得返回模型思维链，只返回动作名称和执行摘要。

## 13. 配置建议

建议新增：

```text
AGENT_MODE=hybrid
AGENT_MAX_STEPS=4
AGENT_TIMEOUT_S=120
AGENT_TOOL_TIMEOUT_S=10
AGENT_MAX_TOOL_RESULT_CHARS=12000
AGENT_DEBUG_RESPONSE=0
AGENT_ENABLE_STREAMING=0
AGENT_MAX_PROMPT_CHARS=8000
AGENT_MAX_IMAGE_BYTES=10485760
```

所有参数加入 `ServiceConfig` 和命令行参数，并在启动日志中打印非敏感配置。数据库密码和 API Key 不得打印。

## 14. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| InternVL 工具选择 JSON 不稳定 | Agent 无法可靠执行 | 严格动作 Schema、一次修复提示、失败回退规则路由 |
| SGLang 版本不完整支持原生工具调用 | function calling 无法使用 | 本周使用结构化动作协议，不依赖原生 tool calling |
| 重构 `ReidService` 引入回归 | 原有演示功能损坏 | 工具先做薄包装，保留 `AGENT_MODE=rules` |
| 数据库真实数据变化 | 演示结果不可预测 | 准备固定人员、日期和只读冒烟数据 |
| 工具结果过长 | 上下文过大、响应变慢 | 查询 limit、字段白名单、字符上限和摘要 |
| 模型循环调用工具 | 超时和资源浪费 | 最大 4 步、重复调用检测、总超时 |
| SSE 占用过多时间 | P0 功能延期 | SSE 是 P1，第三天核心稳定后才实现 |
| 会话内存重启丢失 | 演示连续性受影响 | 汇报时明确边界；PostgreSQL 持久化作为 P1 |

## 15. 每日收尾检查

每天结束前固定执行：

```bash
python -m py_compile <当天修改的 Python 文件>
python -m unittest discover -s tests -p 'test_agent*.py'
git diff --check
curl http://127.0.0.1:8002/health
curl http://127.0.0.1:8002/ready
```

同时记录：

- 当天完成项；
- 未完成项和原因；
- 新增测试数；
- 一个可运行请求和结果；
- 第二天第一项任务。

## 16. 周五演示流程

建议控制在 8 至 10 分钟。

### 1. 现状和问题，约 1 分钟

说明原系统依赖关键词进入固定流程，无法自主组合工具；已有业务数据查询能力是本次改造基础。

### 2. 架构变化，约 2 分钟

展示：

```text
规则路由
  -> 工具注册表
  -> 有限步 Agent
  -> 会话状态
  -> trace 和评测
```

### 3. 现场演示，约 4 分钟

依次演示：

1. “张三昨天出现在哪里？”
2. “给我最近两段回放。”
3. “那今天呢？”
4. “昨天有哪些异常，哪个摄像头最多？”
5. 展示某个 `trace_id` 对应的工具调用步骤和耗时。

### 4. 工程质量，约 1 分钟

展示测试结果、失败降级、会话隔离和一键回退配置。

### 5. 下一阶段，约 1 分钟

下一阶段按以下顺序推进：

1. PostgreSQL 会话持久化和多实例共享。
2. 可引用的知识库 RAG。
3. 鉴权、限流、审计和 Prometheus 指标。
4. 写操作工具和人工审批节点。
5. 复杂任务的 LangGraph 检查点和恢复。

## 17. 最终验收清单

- [ ] `tools` 目录中存在可维护的源码，不依赖历史 `.pyc`。
- [ ] 至少注册 5 个只读工具。
- [ ] 每个工具都有名称、描述、参数 Schema 和统一结果。
- [ ] Agent 能执行“决策、工具、观察、继续决策、最终回答”闭环。
- [ ] Agent 最大步骤、总超时和重复调用限制有效。
- [ ] 非法工具名和非法参数不会执行数据库函数。
- [ ] 同一会话支持连续追问，不同会话互不串扰。
- [ ] 现有单图片对话仍然可用。
- [ ] Agent 失败时可以自动或配置回退规则流程。
- [ ] 每个请求都有 `trace_id` 和结束原因。
- [ ] 日志不包含图片 Base64、数据库密码和完整 SQL 异常。
- [ ] 核心测试不依赖真实 GPU 和数据库。
- [ ] 至少 20 条场景评测已执行并统计结果。
- [ ] 真实 SGLang 和 PostgreSQL 冒烟测试通过。
- [ ] README、功能说明和 API 文档与当前实现一致。
- [ ] 周五演示问题、数据和回退命令已经预演。

## 18. 完成定义

满足以下条件时，本周可以对外表述为“完成智慧监控领域 Agent 最小可用版本”：

1. 模型可以自主选择并组合只读业务工具。
2. 工具调用经过参数校验并形成有限步执行闭环。
3. 多轮会话、异常降级和执行追踪能够实际运行。
4. 关键场景有自动化测试和端到端演示证据。
5. 原规则流程仍可一键回退。

如果只完成工具封装，没有模型决策和工具结果回填循环，应准确表述为“完成 Agent 工具层”，不能表述为“完整 Agent 已完成”。
