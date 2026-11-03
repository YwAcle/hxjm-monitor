# 模型与推理后端配置

日常只使用两个入口，从项目根目录执行：

```bash
bash Agent/scripts/start.sh
bash Agent/scripts/stop.sh
```

启动读取 `Agent/.env`，同名进程环境变量优先。后台启动 Agent、报告 Worker，复用已有模型接口或启动本地模型；详细行为和日志位置见 [启动说明](scripts/README.md)。旧的独立服务及兼容启动入口已移除。

## 本地模型

```dotenv
LLM_MODE=local
LLM_BACKEND=vllm
LLM_MODEL_PATH=./Qwen3.8-27B-AWQ-INT4
LLM_MODEL_ID=Qwen/Qwen3.8-27B-AWQ-INT4
LLM_SERVER_HOST=0.0.0.0
LLM_SERVER_PORT=8000
LLM_API_KEY=unused
CUDA_VISIBLE_DEVICES=6
LLM_TP_SIZE=1
LLM_CONTEXT_LENGTH=16384
LLM_GPU_MEMORY_UTILIZATION=0.55
LLM_DTYPE=bfloat16
LLM_ENABLE_THINKING=false
LLM_CHAT_TEMPLATE=./scripts/chat_templates/qwen3_5_no_thinking.jinja
VLLM_ENV_ROOT=./.venv-vllm-qwen
VLLM_MAX_NUM_SEQS=1
VLLM_LIMIT_MM_PER_PROMPT='{"image":4,"video":0}'
VLLM_MAX_NUM_BATCHED_TOKENS=2048
VLLM_ATTENTION_BACKEND=TRITON_ATTN
VLLM_ENFORCE_EAGER=true
```

模型及模板以 `.` 开头的相对路径按 `Agent/` 解析；环境路径建议填写绝对路径。`AGENT_PYTHON_BIN` 和 `REPORT_PYTHON_BIN` 指向业务环境，`VLLM_PYTHON_BIN` 或 `VLLM_ENV_ROOT` 指向推理环境；SGLang 使用 `SGLANG_ENV_ROOT` / `SGLANG_PYTHON_BIN`。不自动安装依赖或下载模型。

当前本地模型名称来自原部署，实际 config 架构为 `Qwen3_5ForConditionalGeneration`，量化为 compressed-tensors INT4。权重、Python 3.11、vLLM 0.17.1 及业务环境均从本地部署复制。16K 上下文、单卡、单请求及 eager 模式用于适应共享 GPU 的可用显存，未验证满上下文和并发负载。

`LLM_BASE_URL` 默认由端口生成 `http://127.0.0.1:<port>/v1`，可显式覆盖。端口被占用时等待并复用其兼容接口，不重复启动引擎。`/models` 返回的 ID 必须匹配 `LLM_MODEL_ID`，否则报错；更换模型时需同步修改模型名称。停止只释放本入口创建的模型，复用的外部模型由原入口管理。

临时选择本地后端：

```bash
bash Agent/scripts/start.sh vllm
bash Agent/scripts/start.sh sglang
bash Agent/scripts/start.sh --show-config
```

vLLM 的 `VLLM_ENFORCE_EAGER`、attention backend、模板等参数应与模型和版本一致。当前 Qwen3.5 架构模板保留多模态占位符并关闭思考；不能随意套用于其他模型。切换推理引擎前先停止原引擎，启动命令不会替换占用端口的服务。

## 远程 API

```dotenv
LLM_MODE=api
LLM_REMOTE_BASE_URL=https://provider.example/v1
LLM_REMOTE_MODEL_ID=your-model-id
LLM_REMOTE_API_KEY=your-api-key
LLM_REMOTE_ENABLE_THINKING=
LLM_REMOTE_RESPONSE_FORMAT=json_object
LLM_HEALTHCHECK=auto
```

仅支持 OpenAI Chat Completions 兼容接口；URL 填根路径，不含 `/chat/completions`。API 模式不启动本地模型，也不从本地字段回退远程地址、模型及密钥。图片流程还需要模型支持 `image_url`。

`LLM_HEALTHCHECK=auto` 在本地核对 `/models`，API 模式跳过该接口；`models` 强制检查，`none` 跳过。跳过检查不等于验证连通性、鉴权或计费权限，`/ready` 不保证跳过检查的远程 API 实际可调用。启动不会发送可能计费的聊天请求。

`LLM_REMOTE_RESPONSE_FORMAT` 支持 `json_schema`、`json_object`、`none`，仅控制原本带结构化格式的请求。`LLM_REMOTE_ENABLE_THINKING` 默认留空，避免向不支持的服务商发送模型特有参数。

## 超时和日志

- `LLM_CONNECT_TIMEOUT_S`、`LLM_REQUEST_TIMEOUT_S`、`LLM_MAX_RETRIES` 控制模型请求。
- `AGENT_REQUEST_TIMEOUT_S`、`AGENT_ANSWER_MAX_NEW_TOKENS` 控制整次请求超时及最终回答长度。
- `VLLM_STARTUP_TIMEOUT_S` / `SGLANG_STARTUP_TIMEOUT_S` 控制模型加载及端口复用等待，`AGENT_STARTUP_TIMEOUT_S` 控制业务就绪等待。
- `LOG_WRITE_MODE=append|overwrite` 统一控制业务及模型日志，可用各服务的日志模式变量覆盖。
- 私网模型健康检查直连，避免系统代理影响本地服务。
