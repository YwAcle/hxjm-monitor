# LLM Agent Service

Agent 与 Report、Chat 共用根目录 `.env` 中的 `LLM_BASE_URL`、`LLM_MODEL_ID` 和 `LLM_API_KEY`。模型更换说明见 [模型切换指南](../MODEL_SWITCHING.md)。

聊天主动行人检索使用远端服务：图片和截图通过 CLIP-ReID 提取特征，文字描述通过同一服务的 Chinese-CLIP 文本/图片接口提取特征；两套特征空间严格隔离，不读取或修改原库向量。只需配置 `REID_FEATURE_BASE_URL`、`REID_TIMEOUT_S`，以及可选的 `REID_FEATURE_SPACE_ID`、`REID_TEXT_FEATURE_SPACE_ID`、`REID_TEXT_CONTRACT_ID` 和 `REID_TEXT_MAX_CHARS`，不需要本地模型权重或后端切换。接口配置见 [CLIP-ReID接入说明](开发文档/CLIP-ReID接入说明.md)，验证、候选返回及文字检索的边界见 [登记库主动行人检索](开发文档/登记库主动行人检索最小接入.md)。

面向智慧监控大屏的规则路由、数据检索和大模型总结服务。当前实现不是通用 ReAct Agent；它根据异常关键词和熟人姓名选择确定的业务查询流程，并通过 LangChain 调用共享的 SGLang InternVL 服务。

## 功能特性

- **规则路由**：支持普通问答、人员轨迹查询、VAD 异常查询和超分页面跳转
- **业务检索**：读取 PostgreSQL 中的人员、轨迹、异常和已有报告
- **多模态问答**：支持文本和 base64/文件图片，经 SGLang InternVL 处理
- **报告总结**：汇总人员或异常事件的多段报告

## 目录结构

```
llm_agent_service/
├── main.py              # 服务入口
├── app.py               # Flask 应用
├── config.py            # 配置类
├── service/
│   ├── reid_service.py  # 规则路由和业务编排
│   └── __init__.py
├── db/
│   ├── session.py       # 数据库会话
│   └── __init__.py
└── llm/
    └── __init__.py      # 共享 LangChain 模型工厂
```

## 使用方法

### Agent 日志

Agent 的每次决策调用（包括格式纠正重试）通过 OpenAI 兼容接口发送 `response_format.type=json_schema`，服务端约束输出为工具动作或最终答复。工具动作必须包含 `action=tool`、非空 `tool_name` 和对象类型 `arguments`；最终答复必须包含 `action=final` 和非空 `answer`，额外字段被拒绝。客户端继续执行本地动作校验与一次纠正重试。最终自然语言的流式输出不使用此 Schema。服务端必须支持 JSON Schema 结构化输出；不支持时会报告模型调用错误，不自动取消约束。该约束保证动作格式，工具名称及业务参数仍由注册表与工具参数模型校验。

整套 vLLM 服务的 Agent 日志默认位于 `.runtime-cache/service-stack/vllm/agent.log`，SGLang 对应目录为 `.runtime-cache/service-stack/sglang/`。事件采用单行 JSON，可通过同一个 `trace_id` 关联请求与各次工具调用：

全部结构化事件同时写入对应目录的 `agent.jsonl`，每行一个 JSON 对象，使用 UTF-8 编码，不混入启动提示或 traceback，适合 JSONL 查看插件。文件每条事件写入后刷新。可用 `AGENT_JSONL_LOG=/absolute/path/agent.jsonl` 指定其他路径；完整服务入口也会遵循 `SERVICE_STACK_RUNTIME_DIR`。JSONL 保存完整提示词、工具结果和最终回复，图片数据仍按下述规则省略。

日志写入模式在根目录 `.env` 配置，或通过启动环境变量覆盖：

```dotenv
# append 保留历史；overwrite 在对应进程启动时清空文件。
LOG_WRITE_MODE=append
# 单独覆盖某个日志的模式（可选，优先于统一配置）：
AGENT_LOG_WRITE_MODE=overwrite
AGENT_JSONL_WRITE_MODE=append
REPORT_LOG_WRITE_MODE=overwrite
MODEL_LOG_WRITE_MODE=append
```

`AGENT_LOG_WRITE_MODE` 控制完整服务入口的 `agent.log`，`REPORT_LOG_WRITE_MODE` 控制 `report.log`，`MODEL_LOG_WRITE_MODE` 控制本地启动模型时的 `vllm.log` 或 `sglang.log`，`AGENT_JSONL_WRITE_MODE` 控制 Python Agent 的 JSONL。当前 `.env` 设置所有日志默认追加。配置变化在下次启动生效；复用已有模型时不改动其日志。覆盖模式仅在启动时清空一次，之后持续写入。未配置统一模式时保留原行为：文本日志覆盖、JSONL 追加。所有模式只接受 `append` 和 `overwrite`。

临时让全部日志覆盖：

```bash
LOG_WRITE_MODE=overwrite LLM_BACKEND=vllm ./scripts/start_all.sh
```

如果单独启动服务时自己使用 shell 的 `>` / `>>` 重定向标准输出，该重定向的覆盖或追加行为由你的命令决定。

导出旧的混合日志（目标文件必须尚不存在）：

```bash
python scripts/export_agent_jsonl.py \
  .runtime-cache/service-stack/vllm/agent.log \
  .runtime-cache/service-stack/vllm/agent-history.jsonl
```

- `request_start.prompt`：普通 `/chat` 与流式 `/chat/stream` 的完整用户提示词，多行文本以 JSON 转义保存。
- `agent_start.user_prompt`：执行器收到的完整用户提示词。
- `tool_start.arguments`：具体调用参数。
- `tool_end.result`：工具实际返回的结构化结果，包含 `ok`、`data`、`error_code`、`error_message`、`truncated` 和 `elapsed_ms`，日志不按模型观察结果的字符限制截断。
- `agent_end.answer`：Agent 决策完成时的完整答复。
- `request_end.response_text`：普通请求返回的完整文本，或流式请求所有 `delta` 文本的拼接结果。流式接口先执行工具决策，再基于原始问题和工具证据进行唯一一次正文流式生成；完成后用同一份正文记录 `agent_end.answer` 和会话历史。流式生成异常时两个日志保留已输出正文，状态为 `error`，不保存未完成问答。

图片 Base64 和图片 Data URL 会替换为长度标记，其余业务结果保留。普通工具决策与直接图片超分调用均记录这些事件。修改日志代码后需要重启 Agent 服务。

```bash
rg '"trace_id":"<TRACE_ID>"' .runtime-cache/service-stack/vllm/agent.log
```

### 启动服务

```bash
DB_USER=root \
DB_PASSWORD=123456 \
DB_NAME=postgres \
./scripts/start_agent.sh
```

### API 接口

#### 1. 聊天接口（文本）

```bash
curl -X POST http://localhost:8002/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "browser-001", "prompt": "今天张三做了什么？"}'
```

后续问题使用相同的 `session_id` 即可携带最近的对话历史：

```bash
curl -X POST http://localhost:8002/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "browser-001", "prompt": "我刚才问了谁？"}'
```

未提供 `session_id` 时服务会自动生成，并在响应中返回；客户端需要保存并在下一轮继续传入。

#### 2. 聊天接口（带图片）

需要实时显示图片分析正文时，使用支持文件上传的 SSE 接口：

```bash
curl -N http://localhost:8002/chat/stream \
  -H "Accept: text/event-stream" \
  -F "prompt=请描述这张图片的内容" \
  -F "session_id=browser-001" \
  -F "file=@image.jpg"
```

前端用 `fetch` 读取 SSE `delta`，上传文件时不要手动设置 `Content-Type`。接口也继续支持 JSON Base64 图片。详细示例见 [前端流式对接](开发文档/前端流式对接.md)。普通 JSON 返回接口仍保留：

```bash
curl -X POST http://localhost:8002/chat \
  -F "prompt=识别图片中的人员" \
  -F "session_id=browser-001" \
  -F "file=@image.jpg"
```

#### 3. 存活检查

```bash
curl http://localhost:8002/health
```

#### 4. 就绪检查

```bash
curl http://localhost:8002/ready
```

#### 5. 清空会话记忆

```bash
curl -X DELETE http://localhost:8002/sessions/browser-001/memory
```

## 配置参数

- `--llm-base-url`: SGLang OpenAI API 根地址
- `--llm-model`: SGLang 对外模型名
- `--llm-api-key`: SGLang API Key
- `--max-new-tokens`: LLM 每次生成的最大token数（默认：512）
- `--agent-request-timeout-s`: Agent 单次请求总超时，单位秒（默认：180）
- `--agent-answer-max-new-tokens`: 最终正文生成的token上限（默认：2048）；达到上限时返回已生成内容并标记 `finish_reason=length`
- `--db-*`: PostgreSQL 连接参数
- `--playback-base-url`: 视频回放服务地址
- `--reid-feature-base-url`: CLIP-ReID / Chinese-CLIP 远端特征服务地址
- `--reid-timeout-s`: 特征服务单次请求超时，单位秒（默认：15）
- `--reid-feature-space-id`: 可选，固定 CLIP-ReID 图片特征空间
- `--reid-text-feature-space-id`: 可选，固定 Chinese-CLIP 文本特征空间
- `--reid-text-contract-id`: 可选，固定 Chinese-CLIP 文本契约版本
- `--reid-text-max-chars`: 文字检索描述的最大字符数（默认：200）
- `--memory-max-sessions`: 进程内最多保留的会话数量，默认 1000
- `--memory-max-messages`: 每个会话最多保留的 LangChain 消息数，默认 20
- `--image-asset-ttl-s`: 会话图片保留时间，单位秒（默认：1800）
- `--image-asset-max-per-session`: 每个会话最多保留的上传图片数（默认：4）
- `--image-asset-max-bytes-per-session`: 每个会话图片总字节上限（默认：32 MB）
- `--image-asset-max-total-bytes`: 全部会话图片总字节上限，超出时淘汰最早图片（默认：256 MB）

## 会话记忆

- 使用 `langchain_core.chat_history.InMemoryChatMessageHistory` 保存消息。
- 不同 `session_id` 的历史完全隔离。
- 同一会话的并发请求会串行处理，避免消息顺序错乱。
- 只保存用户文本和模型回答；上传图片不会以 base64 形式写入历史。
- 图片单独保存在会话图片资产库中：同一会话内按摘要去重，受 TTL、会话数量和字节上限约束。
- 用户追问并引用此前图片（如“上图”“刚才那张图”“第一张图”）时，服务端会把对应图片重新附加到本轮消息；图片检索和超分工具也使用这张图片。
- 引用的图片已过期或不存在时，本轮不附加图片，并向模型说明需让用户重新上传，避免根据文字猜测画面。
- 用户只上传图片、没有输入文字时，沿用会话中上一条用户请求；例如先说“帮我找图里的人”、被提示上传后再上传图片，会继续找人而不是变成描述图片。
- 客户端若仍自动注入“请描述这张图片的内容”等默认提示词，在上一轮助手刚要求上传图片时同样按纯图片请求处理；其余场景保持描述语义。
- `DELETE /sessions/<session_id>/memory` 同时清空聊天历史和会话图片。
- 当前记忆和图片资产都保存在 Agent 进程内，服务重启后清空，多进程或多服务器实例之间不共享。

数据库默认地址为 `100.127.237.7:5432`，无需在 `.env` 配置数据库 IP。
