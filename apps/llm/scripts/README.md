# Agent 启动与停止

在项目根目录执行：

```bash
bash apps/llm/scripts/start.sh
bash apps/llm/scripts/stop.sh
```

`start.sh` 读取 `apps/llm/.env`，后台启动 Agent 和报告 Worker；本地模式下模型接口可用时直接复用，端口已占用但尚未就绪时等待已有服务，不重复加载权重。只有端口空闲且使用本地模型模式时，才启动配置的 vLLM / SGLang。复用接口仍须通过鉴权及模型名称检查；端口上的服务不是兼容模型接口时明确报错，不杀占用者。API 模式不启动本地模型。

启动成功会等待 Agent `/ready` 返回数据库和模型均就绪。重复启动不会创建第二套进程。服务在独立的、按当前目录标识的 tmux 会话中运行，关闭终端不影响运行。启动和停止串行执行。

`stop.sh` 不要求模型配置仍然有效，只停止本入口创建的 Agent、报告 Worker 和模型进程组，保留复用的模型。其他入口创建的服务不属于本入口管理；首次迁移需先从原入口停止业务服务。不要使用按端口杀进程的命令。

配置预览、临时选择模型模式：

```bash
bash apps/llm/scripts/start.sh --show-config
bash apps/llm/scripts/start.sh api
bash apps/llm/scripts/start.sh vllm
CUDA_VISIBLE_DEVICES=6 LLM_TP_SIZE=1 bash apps/llm/scripts/start.sh local
```

需要 Bash、Python 3.8+、tmux、setsid 和 curl；Agent 与推理引擎使用 `.env` 指定的独立 Python 环境。查看 [模型配置说明](../MODEL_SWITCHING.md)。修改配置后执行停止、启动；更换复用模型时，应由该模型原来的启动入口重启模型。

日志默认位置（均相对于 `apps/llm/`）：

- `.runtime-cache/launcher/stack.log`：启动、等待、退出原因。
- `.runtime-cache/service-stack/<vllm|sglang|api>/agent.log`、`report.log`、`agent.jsonl`：业务日志。
- `.runtime-cache/llm-report-service/<vllm|sglang>.log`：本入口启动的模型日志。

`scripts/` 顶层只有启动、停止两个可执行入口。`internal/` 保存配置解析、各服务启动实现及进程管理，`tools/` 保存独立检索验证和日志导出工具，`chat_templates/` 保存模型模板。旧的转发启动入口已移除。

## 文字检索的部署依赖

`REID_FEATURE_BASE_URL` 必须指向实际运行的 ReID HTTP 服务；该地址与 LLM `/v1` 及 Agent `8002` 地址不同。

本次检查发现旧地址 `http://100.127.237.7:28024` 拒绝连接。部署配置中的 `http://192.168.109.191:28124` 可访问，但其 `/health` 没有 `text_reid` 字段，OpenAPI 仅有 `/health`、`/v1/reid/person-crops`、`/v1/reid/image-features`、`/v1/reid/tracklet-features`。当前 `modules/perception-devices/python/reid_feature_service/server.py` 同样未实现 Chinese-CLIP 文本能力，因此不能仅通过改地址实现文字找人。这是服务地址及能力缺失，不是已确认的 GPU 资源故障。

文字检索还需要部署匹配的 Chinese-CLIP 编码服务，提供 `/v1/reid/text-features`、`/v1/reid/text-reid-image-features` 和包含 `text_reid` 的健康检查（特征空间、文本契约及对齐验证）。不可把普通 CLIP-ReID 3072 维图片向量用于 Chinese-CLIP 文本检索。完整契约见 [登记库主动行人检索](../llm_agent_service/开发文档/登记库主动行人检索最小接入.md)。
