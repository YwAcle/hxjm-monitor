# 2026-11-04 本副本验收

## 已通过

- Java 8 Maven package/test-compile（构建进程限制 1.2 GiB、2 CPU，堆 512 MiB）。
- PostgreSQL 独立空测试库：共享 Schema 正反例、global 任务、重复提交、双 Executor 竞争领取、完成幂等、摘要冲突、发送前后 lease 恢复、旧执行回报、namespace/runtime 隔离、续租及 HTTP 超时/错误/重定向/非法响应/响应大小限制。
- 原有 BusinessIdentityDatabaseCheck 和 BusinessDiscoveryDatabaseCheck：样本/特征、跨来源身份与活动、事件/报告、特征任务完成、向量检索与访问范围。
- Agent 全量 277 项中 275 项通过、1 项跳过、1 项旧启动脚本测试错误（见下）。包含动态 Bridge、静态工具、普通聊天、SSE 与请求级 Registry。
- ResultSpool 19 项、ResultDispatcher 17 项通过；部署入口 9 项通过。
- 本副本迁移实际完成；重复迁移无变化。两份能力配置重复登记复用原实例。
- 真实事件与报告链路的 task/run 标识见 validation-current.json。报告直接查询与持久化成果均为 3 条；事件均为 0 条。未写入合成事件。
- 当前仓库 Flask /chat 使用现有远程模型，自动选择 query_business_events，任务成功、成果入库并生成回答，耗时约 19.4 秒。没有启动本地模型或修改远端 Agent。

## 未通过或未覆盖

- 旧 test_vllm_service.test_launch_arguments_and_quoted_env 引用上一任务已删除的 Agent/llm_report_service/start_vllm.sh，FileNotFoundError。本轮未恢复废弃入口。
- video_analysis 全量测试在当前 Python 环境运行失败：缺少 torch/PyAV 等算法依赖，另有旧 Worker/录制测试与上游运行时接口不一致；本轮仅确认相关 ResultSpool/ResultDispatcher 回归及现有分析容器健康，未宣称全部视频测试通过。
- 真实事件库无数据，非空事件结果验收未完成。当前库有真实报告，通过第二能力验证非空成果。
- “监控事件”同时可能匹配旧视频异常工具；本次模型验收使用“业务事件目录最新3条，非视频异常检测”的自然语言，未指定工具名。动态能力优先提示不保证模型对含混问题总选择相同能力。
- Flask test client 验证了当前代码的完整请求处理链路；未将本机前端改接新的常驻 Agent，当前页面仍可连接原远程 Agent，不能把页面视为已部署本次 Agent 代码。

## 运维过程

首次迁移与视频写入产生死锁，事务全部回滚；暂停本副本后端后成功迁移。重启遇到主机 iptables 入口缺失，用户恢复后重试成功。其他人的服务、远端 Agent 和模型未停止。仅本副本后端镜像及配置更新，现有算法/媒体进程持续运行。
