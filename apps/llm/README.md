# Agent 与报告进程装配

此目录只维护现有 LLM 应用的环境配置、模型资源和进程启动。正式源码分别在 modules/agent/python、modules/business/python 和 modules/ai-infra/python；不保留旧 llm_chat_service、llm_api_service 或 ReidService 回退入口。

从仓库根目录使用：

```bash
cp apps/llm/.env.example apps/llm/.env
bash scripts/agent.sh start
bash scripts/agent.sh stop
```

日常入口固定使用本地 vLLM，无需选择 api/local；兼容的已运行模型由现有管理器检查并复用，否则启动本地模型。实际启动前须配置模型及现有 Capability 服务身份，并登记业务能力。Agent 正式入口是本目录 agent.py；该装配文件在同一 Flask 进程挂载 Business 图库路由。报告入口是 `llm_report_service.main`，由 start_report.sh 通过模块方式启动。Agent 包本身不导入图库 Repository 或报告实现。

scripts/internal/load_env.sh 设置新模块搜索路径并读取本目录 .env。虚拟环境与模型默认相对于本目录；可用 AGENT_PYTHON_BIN、REPORT_PYTHON_BIN、VLLM_ENV_ROOT、SGLANG_ENV_ROOT 指定本项目已有环境。源码迁移保留了原本地环境、模型和缓存；已有环境中的绝对路径或坏链接不会自动修复。不要直接把其他项目环境作为默认环境。

跨模块契约及登记方式见 ../../docs/refactor/interfaces.md，目录与验证记录见 ../../docs/refactor/stage-2.md。启动脚本会实际请求模型或启动服务；本阶段只执行配置、模拟与构建检查，没有执行这些启动命令。

服务依赖聚合入口为 apps/llm/requirements.txt；只向本项目指定环境安装。通用模型依赖由 modules/ai-infra/python/requirements.txt 维护，Agent 不再声明数据库驱动依赖。模型推理后端的可选依赖文件仍在 Business 报告模块，本阶段未安装。
