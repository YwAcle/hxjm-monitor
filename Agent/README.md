# Agent 智能监控服务

监控大屏的对话助手与报告生成后端。`Agent/` 下包含两个可独立运行的 Python 服务，共用模型配置、数据库连接约定和日志输出方式。

## 服务组成

| 服务 | 入口 | 职责 | 端口 |
| --- | --- | --- | --- |
| `llm_agent_service` | `llm_agent_service/main.py` | 对话 Agent：大模型决策 + 只读工具，处理轨迹/报告/异常查询、截图找人和图片超分 | `8002` |
| `llm_report_service` | `llm_report_service/main.py` | 报告 Worker：扫描事件片段，调用视觉模型生成结构化监控报告 | 无 HTTP |

两者都通过 `llm_report_service/llm` 中的模型客户端访问推理服务；`llm_agent_service` 不复刻一套模型代码。模型地址、模型名、思考开关、响应格式统一由 `LLM_*` / `LLM_REMOTE_*` 决定，所以两个服务必须读取同一份配置。

## 目录结构

```
Agent/
├── llm_agent_service/          # 对话 Agent
│   ├── app.py                  # Flask 路由、请求校验、SSE
│   ├── main.py                 # 启动入口与命令行参数
│   ├── config.py               # DbConfig / ServiceConfig
│   ├── observability.py        # 单行 JSON 事件日志
│   ├── agent/                  # 决策循环、提示词、动作 Schema
│   ├── tools/                  # 工具注册表与 11 个默认工具
│   ├── service/                # Agent 编排、ReID、行人检索、记忆、图片资产
│   ├── db/                     # PostgreSQL 访问层
│   ├── llm/                    # 模型工厂
│   ├── 开发文档/               # 前后端对接与方案文档
│   ├── 功能说明.md             # 功能、流程、接口、配置
│   └── README.md               # 实现与联调细节
├── llm_report_service/         # 报告 Worker 与共享模型客户端
│   ├── llm/                    # ChatSGLang / ChatVLLM、配置解析
│   ├── service/                # 报告生成流程
│   ├── db/                     # 报告相关数据访问
│   ├── 功能说明.md
│   └── start_*.sh              # 兼容旧路径的转发脚本
├── scripts/                    # 启动、配置解析、校验脚本
│   ├── start_all.sh            # 模型接口 + 报告 Worker + Agent
│   ├── start_vllm.sh
│   ├── start_sglang.sh
│   ├── start_agent.sh
│   ├── start_report.sh
│   └── README.md               # 启动命令速查
├── tests/                      # 离线单元测试
├── .env.example                # 配置模板
├── 模型与推理配置说明.md        # 模型部署、API 切换与引擎参数
└── AGENTS.md                   # 协作与 Git 约定
```

旧目录 `llm_api_service`、`llm_chat_service` 已删除；原先仍被引用的数据访问模块已合并进 `llm_agent_service/db/`。

## 快速开始

```bash
cd Agent
cp .env.example .env        # 首次部署，按环境修改
```

按 `.env` 中的 `LLM_BACKEND` 启动全套：

```bash
./scripts/start_all.sh
```

指定引擎：

```bash
./scripts/start_all.sh vllm
./scripts/start_all.sh sglang
```

只启动部分服务（前提是模型接口已就绪且模型名匹配）：

```bash
./scripts/start_agent.sh      # Agent，默认 8002
./scripts/start_report.sh     # 报告 Worker
./scripts/start_vllm.sh       # 本地 vLLM
./scripts/start_sglang.sh     # 本地 SGLang
```

`LLM_MODE=api` 时不会启动本地模型，直接使用 `LLM_REMOTE_BASE_URL` 指向的兼容接口。

查看最终生效的模型配置而不启动服务：

```bash
./scripts/start_all.sh sglang --show-config
```

脚本读取 `Agent/.env`，同名环境变量可临时覆盖，例如：

```bash
CUDA_VISIBLE_DEVICES=4,6 LLM_TP_SIZE=2 ./scripts/start_all.sh sglang
```

## 配置

- 模板：`.env.example`
- 模型与引擎切换：`模型与推理配置说明.md`
- Agent 全部参数、默认值与错误码：`llm_agent_service/功能说明.md`
- 启动脚本行为：`scripts/README.md`

常用变量：

| 变量 | 作用 |
| --- | --- |
| `LLM_MODE` | `local` 使用本地推理引擎，`api` 使用远端兼容接口 |
| `LLM_REMOTE_BASE_URL` / `LLM_REMOTE_MODEL_ID` / `LLM_REMOTE_API_KEY` | API 模式连接信息 |
| `LLM_REMOTE_ENABLE_THINKING` | 远端思考开关；留空表示交给服务商默认（通常为开启） |
| `LLM_BACKEND` / `LLM_SERVER_PORT` / `LLM_MODEL_PATH` | 本地引擎选择、端口与权重路径 |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` / `DB_SCHEMA` | 业务库连接 |
| `AGENT_REQUEST_TIMEOUT_S` / `AGENT_ANSWER_MAX_NEW_TOKENS` | 请求超时与回答长度 |
| `REID_FEATURE_BASE_URL` / `REID_FEATURE_SPACE_ID` / `REID_TEXT_*` | 行人检索特征服务 |
| `AGENT_MEDIA_ROOT` | 预览图可读取的媒体根目录 |
| `LOG_WRITE_MODE` | 日志落盘方式 |

真实密钥只写在未入库的 `.env` 中，不要提交。

## HTTP 接口一览

Agent（默认 `http://127.0.0.1:8002`）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/chat` | 非流式对话 |
| POST | `/chat/stream` | SSE 流式对话（`status` / `delta` / `result` / `done` / `error`） |
| GET | `/tools` | 当前工具与参数 Schema |
| GET | `/persons` | 已登记人员名单 |
| POST | `/reload_persons` | 重新加载熟人缓存 |
| DELETE | `/sessions/<session_id>/memory` | 清除会话记忆与图片 |
| GET | `/health` | 存活检查 |
| GET | `/ready` | 数据库与模型就绪检查 |

请求示例：

```bash
curl -N http://127.0.0.1:8002/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"今天有谁出现在三号摄像头","session_id":"demo-1"}'
```

报告 Worker 不提供 HTTP 接口，按数据库中的事件片段持续处理。

## 测试

离线运行，不需要数据库、模型或摄像头：

```bash
cd Agent
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -t tests
```

分为 Agent（API、SSE、执行器、工具、时间解析、行人检索、图片资产）与报告（模型配置、数据库访问、vLLM/SGLang 启动参数）两组。注意：

- `test_agent_schemas` 依赖 `jsonschema`，环境中缺包时会直接报错；
- 模型配置类用例假设 `LLM_MODE=local`，在 `api` 模式下会因跳过 `/models` 探测而失败，属测试环境差异。

## 日志

运行日志写入 `.runtime-cache/service-stack/{api,vllm,sglang}/`：

| 文件 | 内容 |
| --- | --- |
| `agent.log` | Agent 可读日志 |
| `agent.jsonl` | 单行 JSON 事件：`request_start`、`agent_action`、`llm_call_end`、`tool_end` 等 |
| `report.log` | 报告 Worker 日志 |

排查请求时先用 `trace_id` 串起 `request_start` → `llm_call_end` → `tool_end` → `request_end`，看 `elapsed_ms`、`steps`、`finish_reason`。图片内容不会写入日志。

## 文档索引

| 文档 | 内容 |
| --- | --- |
| `llm_agent_service/功能说明.md` | 服务定位、处理流程、工具清单、检索能力、接口、配置、边界 |
| `llm_agent_service/README.md` | 实现细节与联调说明 |
| `llm_agent_service/开发文档/` | 前端流式对接、会话接入、截图找人与多人选择、CLIP-ReID 接入、超分接入 |
| `llm_report_service/功能说明.md` | 报告 Worker 的流程与数据依赖 |
| `模型与推理配置说明.md` | 本地/远端模型切换、引擎参数、日志与超时 |
| `scripts/README.md` | 启动命令速查 |
| `AGENTS.md` | 协作规范与 Git 流程 |