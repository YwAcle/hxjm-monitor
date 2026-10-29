# 服务启动入口

在仓库根目录执行。各脚本读取根目录 `.env`，同名环境变量可临时覆盖。模型与 GPU 资源统一使用 `LLM_*` 字段，配置模板见 [../.env.example](../.env.example)，完整说明见 [../MODEL_SWITCHING.md](../MODEL_SWITCHING.md)。

| 命令 | 启动内容 |
| --- | --- |
| `./scripts/start_all.sh vllm` | 复用或启动 vLLM 接口，再启动报告 Worker 和 Agent |
| `./scripts/start_all.sh sglang` | 复用或启动 SGLang 接口，再启动报告 Worker 和 Agent |
| `./scripts/start_all.sh` | 按 `.env` 的 `LLM_BACKEND` 启动完整服务 |
| `./scripts/start_all.sh sglang --show-config` | 只查看最终模型配置，不启动服务、不打印密钥 |
| `./scripts/start_sglang.sh` | 只启动 SGLang 模型接口 |
| `./scripts/start_vllm.sh` | 只启动 vLLM 模型接口 |
| `./scripts/start_agent.sh` | 等待已有模型接口及模型名称匹配，只启动 Agent |
| `./scripts/start_report.sh` | 等待已有模型接口及模型名称匹配，只启动报告 Worker |

切换实际推理引擎前先停止旧模型服务。完整入口会复用已有兼容接口，退出时只停止自己启动的进程。两个后端都使用 `LLM_MODEL_PATH`、`LLM_MODEL_ID`、`LLM_SERVER_PORT`、`LLM_TP_SIZE` 等公共配置，无需维护两套路径和端口。

临时覆盖 GPU 和并行数：

```bash
CUDA_VISIBLE_DEVICES=4,6 LLM_TP_SIZE=2 ./scripts/start_all.sh sglang
```

旧的根目录和服务目录启动路径保留为兼容入口，实际启动逻辑集中在 `scripts/`。
