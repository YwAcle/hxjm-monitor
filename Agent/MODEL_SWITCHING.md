# 模型与推理后端切换

Agent、Report、Chat、SQL demo 和视频分析共用仓库根目录 `.env` 的模型配置。当前本机默认模型是 **Qwen3.8-27B-AWQ-INT4**，默认后端为 vLLM。`.env` 不纳入版本控制；`.env.example` 提供不含密钥的配置模板。已有 `.env` 时直接修改，避免用模板覆盖本地业务配置。

## 一键切换本地部署 / API

根目录 `.env` 中的 `LLM_MODE` 是持久开关；修改后重启业务服务生效：

```dotenv
# local=本地部署；api=调用独立的 LLM_REMOTE_* API 配置
LLM_MODE=local
```

API 只支持 **OpenAI Chat Completions 兼容协议**（Bearer 鉴权），不是厂商任意原生接口。先填好以下配置，再切到 `api`：

```dotenv
LLM_REMOTE_BASE_URL=https://provider.example/v1
LLM_REMOTE_MODEL_ID=your-model-id
LLM_REMOTE_API_KEY=your-api-key
LLM_REMOTE_ENABLE_THINKING=
LLM_REMOTE_RESPONSE_FORMAT=json_object
LLM_HEALTHCHECK=auto
```

- `LLM_REMOTE_BASE_URL` 为接口根地址，客户端会追加 `/chat/completions`；不要填写完整聊天端点。不同服务商的根路径不一定是 `/v1`。
- 两套配置分别保存：本地继续用 `LLM_BASE_URL`（未设置时按端口生成）、`LLM_MODEL_ID`、`LLM_API_KEY`、`LLM_ENABLE_THINKING`；API 用上面的 `LLM_REMOTE_*`。切换模式无需覆盖本地模型、密钥或 GPU 配置。API 模式不会从本地字段回退地址、模型或密钥；地址和模型名缺失立即报错。
- `LLM_REMOTE_ENABLE_THINKING` 默认留空，避免向通用 API 发送 `chat_template_kwargs`。只有服务商明确支持时才设为 `true` / `false`；本地思考设置不会影响 API。
- `LLM_HEALTHCHECK=auto`：本地强制检查 `/models` 与模型名称；API 跳过 `/models`，以适配不提供列表接口的服务商。也可设 `models` 强制检查，或设 `none` 跳过（此时启动脚本直接复用配置的接口，不探测是否需要启动本地模型；本地自动部署应保留 `auto`）。**跳过不是连通性或密钥验证，`/ready` 也不保证远端可用**；网络、鉴权、模型权限和费用须通过实际请求确认。启动/就绪探针不会发送可能计费的聊天请求。
- API 模式绝不启动本地模型，即使 API 地址是 localhost 或 `START_VLLM=1` / `START_SGLANG=1`。无需本地权重或推理引擎，但业务服务本身的 Python 依赖和数据库仍需可用。
- 图片/视频流程需要支持 `image_url` 的视觉模型。`LLM_REMOTE_RESPONSE_FORMAT` 控制 API 结构化输出：`json_schema` 保留严格格式，`json_object` 使用普通 JSON 模式，`none` 不发送 `response_format`，仅依靠提示词与程序侧 JSON 校验；若服务商拒绝 `json_object` 可改为 `none`。只处理原本包含格式参数的请求，普通聊天不会额外添加该参数。本地模式始终保留调用方原始格式；旧配置未设置此项时保持 `json_schema`。修改后重启服务生效。使用第三方 API 会将模型输入的文本与图片发送给服务商，请先确认数据合规和计费。

在仓库根目录可临时覆盖模式，不改写 `.env`：

```bash
./scripts/start_all.sh api       # 仅启动 Agent + Report，连接配置好的 API
./scripts/start_all.sh local     # 使用配置的本地后端，启动或复用本地模型
./scripts/start_all.sh           # 使用 .env 的 LLM_MODE

# 只启动单个业务服务（不管理本地模型进程）
LLM_MODE=api ./scripts/start_agent.sh
LLM_MODE=api ./scripts/start_report.sh

# 仅预览配置，不启动服务，不打印 API 密钥
./scripts/start_all.sh api --show-config
./scripts/start_all.sh local --show-config
```

预览 API 配置前同样需要填写远程地址与模型名。当前 `.env` 默认保留 `local`，不会擅自切换或发送远程请求。

## 一条命令选择本地后端

在仓库根目录执行：

```bash
./scripts/start_all.sh vllm
./scripts/start_all.sh sglang
```

两条命令均强制 `local` 模式，启动模型接口、报告 Worker 和 Agent，使用同一份模型和资源配置。省略位置参数时读取 `.env` 的 `LLM_MODE` 和 `LLM_BACKEND`。也可使用 `LLM_MODE=local LLM_BACKEND=sglang ./scripts/start_all.sh` 临时覆盖，或直接修改 `.env` 设置长期默认值。

只查看最终模型配置，不启动服务、不覆盖日志，也不打印 API key：

```bash
./scripts/start_all.sh vllm --show-config
./scripts/start_all.sh sglang --show-config
```

完整入口会复用 `LLM_BASE_URL` 上模型名称匹配的兼容接口，不会终止已运行的模型。**要切换实际推理引擎，应先在旧服务终端按 Ctrl+C，再运行新后端命令。** Ctrl+C 只停止该启动脚本创建的进程；复用的外部模型需在其原启动入口停止。两个后端共用一个端口时不能同时启动。

## 公共配置

```dotenv
LLM_BACKEND=vllm
LLM_MODEL_PATH=./Qwen3.8-27B-AWQ-INT4
LLM_MODEL_ID=Qwen/Qwen3.8-27B-AWQ-INT4
LLM_SERVER_HOST=0.0.0.0
LLM_SERVER_PORT=8000
LLM_API_KEY=unused

CUDA_VISIBLE_DEVICES=2,3
LLM_TP_SIZE=2
LLM_CONTEXT_LENGTH=65536
LLM_GPU_MEMORY_UTILIZATION=0.85
LLM_DTYPE=bfloat16
LLM_ENABLE_THINKING=false
LLM_CHAT_TEMPLATE=./scripts/chat_templates/qwen3_5_no_thinking.jinja
```

| 配置 | 用途 |
| --- | --- |
| `LLM_MODEL_PATH` | 两个后端加载的模型目录或模型 ID；以 `.` 开头的相对路径按仓库根目录解析 |
| `LLM_MODEL_ID` | 客户端请求名称，也是本地服务的 `served-model-name`；可省略，默认取模型目录名 |
| `LLM_SERVER_HOST` / `LLM_SERVER_PORT` | 模型服务监听地址和端口 |
| `LLM_BASE_URL` | 客户端地址；本机默认根据端口生成 `http://127.0.0.1:<port>/v1`，通常无需设置 |
| `CUDA_VISIBLE_DEVICES` / `LLM_TP_SIZE` | 可见 GPU 和张量并行数 |
| `LLM_CONTEXT_LENGTH` | vLLM 的 `max-model-len` / SGLang 的 `context-length` |
| `LLM_GPU_MEMORY_UTILIZATION` | vLLM 的 `gpu-memory-utilization` / SGLang 的 `mem-fraction-static`；两者语义略有区别，切换后仍需按实际显存调整 |
| `LLM_DTYPE` / `LLM_CHAT_TEMPLATE` | 公共数据类型和聊天模板；未指定模板时尝试使用模型目录的 `chat_template.jinja` |

本机显式保留 `Qwen/Qwen3.8-27B-AWQ-INT4` 别名，以匹配最近运行的服务。**更换模型时，同步修改或删除 `LLM_MODEL_ID`**，避免客户端继续请求旧模型名称。当前上下文配置为 65536，与最近运行的 AWQ 服务保持一致；没有进行满长度或并发压力测试。

Shell 启动入口与 Python 客户端共用 `llm_report_service/llm/settings.py` 解析配置。启动检查除接口可访问外，还会验证 `/models` 返回的模型 ID。接口可达但名称不匹配时立即报错，避免启动成功后聊天才返回 404。

## 后端独有配置

两个引擎仍使用各自的 Python 环境：

```dotenv
VLLM_ENV_ROOT=./.venv-vllm-qwen
SGLANG_ENV_ROOT=/path/to/sglang-env
```

`VLLM_PYTHON_BIN`、`SGLANG_PYTHON_BIN` 可覆盖各自的解释器。SGLang 还沿用启动脚本中的 CUDA Toolkit、编译器与缓存配置；环境必须存在且已安装支持当前模型的引擎。切换脚本不会自动安装依赖，也不保证任意版本都支持 AWQ 模型。

保留的 vLLM 性能配置：

```dotenv
VLLM_MAX_NUM_SEQS=2
VLLM_LIMIT_MM_PER_PROMPT='{"image":4,"video":0}'
VLLM_ATTENTION_BACKEND=TRITON_ATTN
VLLM_MAX_NUM_BATCHED_TOKENS=8192
VLLM_NO_USAGE_STATS=1
```

图片上限包含报告和视频分析传入的抽帧图片；调整帧数时需同步考虑图片上限和显存。`VLLM_ENFORCE_EAGER`、`VLLM_REASONING_PARSER`、`VLLM_DEFAULT_CHAT_TEMPLATE_KWARGS` 等仅在确实需要覆盖时设置。vLLM 默认从公共 `LLM_ENABLE_THINKING` 生成模板参数，无需重复配置同样的 JSON。

当前无思考模板服务于 Qwen3.5 架构的 Qwen3.8 模型，保留多模态占位符。vLLM 0.17.1 的 Responses 路径需要此模板；在该版本下，不要仅设置 `LLM_ENABLE_THINKING=false` 后重新启用 `qwen3` reasoning parser，否则正文可能被归入推理字段。换用其他模型时应同时检查模板适配。

历史环境依赖入口仍保留：`llm_report_service/requirements-vllm-qwen.txt` 用于 Qwen 部署，`llm_report_service/requirements-vllm-cu118.txt` 用于旧版 InternVL 环境。旧版 vLLM 0.9.2 不支持当前 Qwen3.5 架构；不要通过切换配置混用这两个环境。

旧部署的 `VLLM_MODEL_PATH` / `SGLANG_MODEL_PATH`、`*_MODEL_NAME`、`*_PORT`、`*_TP_SIZE`、`VLLM_MAX_MODEL_LEN` / `SGLANG_CONTEXT_LENGTH`、各自的显存比例、模板和 dtype 字段仍作为回退项。公共字段优先；新的 `.env` 无需同时维护两套配置。

## 单独启动与远程接口

```bash
./scripts/start_vllm.sh       # 只启动 vLLM，强制选择 vLLM 配置
./scripts/start_sglang.sh     # 只启动 SGLang，强制选择 SGLang 配置
./scripts/start_agent.sh      # 等待已有模型接口，启动 Agent
./scripts/start_report.sh     # 等待已有模型接口，启动报告 Worker
```

模型启动脚本允许追加引擎原生参数，例如 `./scripts/start_vllm.sh --enforce-eager`。根目录与服务目录中的旧入口仍转发到 `scripts/`；`start_services_vllm.sh` 和 `start_services_sglang.sh` 分别固定选择对应后端。

新配置推荐使用 `LLM_MODE=api` 和独立的 `LLM_REMOTE_*`，见上文。旧部署只设置 `LLM_BACKEND`、`LLM_BASE_URL`、`LLM_MODEL_ID`、`LLM_API_KEY` 的远程兼容服务写法仍然可用：默认为 `local` 模式，但远程地址在 `auto` 策略下不会启动本地模型，并要求提供 `/models` 和 `/chat/completions`。图片工作流还要求支持 `image_url` 多模态输入。

## 超时、日志和优先级

- `LLM_CONNECT_TIMEOUT_S`、`LLM_REQUEST_TIMEOUT_S`、`LLM_MAX_RETRIES` 控制客户端超时与重试。`LLM_MAX_NEW_TOKENS` 是 Agent/Report 启动脚本的默认生成长度。
- `LOG_WRITE_MODE=overwrite` 或 `append` 统一控制日志，无需重复设置每个服务的日志模式；需要例外时再设置 `AGENT_LOG_WRITE_MODE` 等覆盖项。
- 模型日志默认写入 `.runtime-cache/llm-report-service/{vllm,sglang}.log`；Agent 与 Report 日志写入 `.runtime-cache/service-stack/<backend>/`，API 模式写入 `.runtime-cache/service-stack/api/`。
- `START_VLLM=auto|1|0` / `START_SGLANG=auto|1|0` 控制完整入口是否启动本地模型；`*_STARTUP_TIMEOUT_S` 默认 300 秒。
- 本地请求应将 `127.0.0.1,localhost` 加入 `NO_PROXY`；外部已设置该变量时，在其原列表中补充。

公共字段与对应旧字段同时存在时优先使用公共字段。同一字段的值优先级为：命令行参数 > 进程环境变量 > 根目录 `.env` > 默认值。完整入口的后端位置参数优先于 `LLM_BACKEND` 环境变量。
