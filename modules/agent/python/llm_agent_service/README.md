# HXJM Agent 模块

本包只维护决策循环、会话/图片上下文、动态 Capability Tool Bridge、纯本地辅助工具和 Agent HTTP 接入。正式业务能力来自请求级目录，不直接使用图库、报告 Repository 或算法内部对象。

部署装配入口为仓库 apps/llm/agent.py，启动配置和现有模型环境由 apps/llm/scripts 管理。图库路由由装配入口挂载，实现在 modules/business/python/business_api，Agent 包不导入该实现。

公共 HTTP 接口包括 /chat、/chat/stream、/tools、/ready 和会话记忆清理。旧 /persons、/reload_persons 及旧 ReidService、llm_chat_service、llm_api_service 已退役，不保留兼容调用。

安装与运行请从仓库根目录遵循 apps/llm/README.md；跨模块契约以 contracts/capability-v1 和 docs/refactor/interfaces.md 为准。测试在 tests/agent。
