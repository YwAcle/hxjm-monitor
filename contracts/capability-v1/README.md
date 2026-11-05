# 配置式能力扩展 V1

能力定义声明输入、参数与成果类型；实例声明资源范围、执行方式及服务操作；任务固定实例、契约和非敏感执行配置快照；run 持有 lease 与执行令牌；task_output 保存结构化成果。

## 接入步骤

1. 显式执行 `bash contracts/capability-v1/tools/migrate.sh POSTGRES_CONTAINER`。事务内有版本记录及 advisory lock；建议先暂停本副本后端避免与视频写入死锁。重复执行不修改旧数据。正常 start 不自动迁移。
2. 参考 `services.example.yml` 在 Java `hxjm.business.execution` 中配置可信服务操作、独立副本 namespace；迁移完成后才能启用 `enabled`。实例 `instance_key` 必须等于 namespace。服务配置不能由 Agent 或注册请求指定。
3. 使用已有服务身份授权 capabilities.describe/register、instances.configure/query、result_types.register/query、tasks.submit/get，调用目标操作权限；终态接口额外要求 tasks.complete/fail，续租要求 tasks.heartbeat。凭据只使用现有 security.services 的引用，不保存于快照。
4. 环境设置 CAPABILITY_BUSINESS_URL、CAPABILITY_SERVICE_ID、CAPABILITY_SERVICE_TOKEN，运行：

   ```bash
   python3 contracts/capability-v1/tools/register.py --namespace YOUR_NAMESPACE contracts/capability-v1/events.json contracts/capability-v1/reports.json contracts/capability-v1/identities.json contracts/capability-v1/tracklets.json
   ```

   同配置重复执行复用实例；不同配置报冲突，不隐式更新契约。新增兼容服务只需可信服务配置和登记 JSON。
5. Agent 使用现有 requirements，配置上述三项连接配置，使用原 apps/llm/scripts 入口。正式业务始终通过请求级动态目录调用；目录不可用不回退到数据库工具。

## 接口

- `GET /api/v1/business/capabilities/tools`：只读、启用且当前服务身份有目标操作权限的工具；实例限定当前 namespace。
- 原 `POST /tasks` 接受 `input={kind:capability_call,payload:{...}}`、task_mode=once，以及 capability_code、instance_id、requested_outputs、parameters、request_id。global 是实例无来源绑定，不是授权所有来源。payload.source_ids 若给出，仍受现有身份来源授权和实例范围限制。
- `GET /tasks?task_id=...` 返回状态、failure、前 20 项 outputs；`GET /tasks/outputs?task_id=...&limit=20&after=...` 读取更多成果。
- `POST /tasks/complete` 接收 task_id、run_id、expected_revision、execution_token、outputs；outputs 每项包含 result_type、schema_version、payload、producer_result_key，可选 asset_id。同 run/key 同内容幂等，不同内容冲突；失败或恢复后的旧执行不允许完成。
- `POST /tasks/fail` 使用相同执行标识与 error_code；`POST /tasks/heartbeat` 使用 task_id、run_id、execution_token 续租。令牌只交执行者，任务查询不泄露令牌。
- 特征 `/tasks/finish` 与视频 `/results/register` 不改语义。旧任务 runtime_managed；新平台任务不能通过 Worker start，平台不会领取 runtime 任务。

## HTTP 协议与运行限制

V1 只发送一次同步 POST，不跳转、不自动重放。request-mode=payload 直接发送 input.payload；envelope 发送 input 与 parameters。response-mode=business 兼容当前平铺 Business 响应、移除 trace_id；json 支持任意合法 JSON 最终结果。输出按登记成果 Schema 校验。

Executor 默认单次轮询领取一项，短事务领取、事务外网络调用。连接超时默认 2 秒，响应超时默认 5 秒且最多 30 秒，默认响应上限 1 MiB；lease 为 60 秒。执行前复核现有服务授权和能力启用状态；快照不随实例修改改变。发送阶段超时、断连或崩溃标记 REMOTE_OUTCOME_UNKNOWN，不重跑；发送前中断标记 EXECUTION_INTERRUPTED_BEFORE_SEND。

此阶段平台提交使用既有服务身份，不新增用户登录或隔离体系。资源范围仅支持 global 与 camera，不实现设备 SDK 或设备资源平台。持续视频与 ResultSpool/ResultDispatcher 保持独立存储。公共成果元数据的权威定义见 `result-context.schema.json`，阶段接口与设备边界见 `../../docs/refactor/interfaces.md`。

## 验证

- `tests/agent/test_capability_bridge.py`：共享 Schema、目录刷新/失败、并发快照、任务等待。
- Java `CapabilityPlatformDatabaseCheck`：明确的空测试库、并发领取、终态幂等/摘要冲突、lease 恢复、旧回报、namespace/runtime 隔离及 HTTP 故障。
- Java `BusinessIdentityDatabaseCheck`：既有视频成果、事件报告、特征任务等数据库回归。测试临时文件使用 java.io.tmpdir，不访问主项目目录。
- `tests/agent/live_capability_v1.py`：真实 Business 接口、持久化成果及可选远程模型 + 当前 Flask /chat。需要显式配置连接，绝不生成业务数据。
- `validation-current.json` 为本次真实验收证据。空事件结果仅证明真实空查询链路，不能宣称非空事件验收通过。

图库使用同一登记入口，附加 `gallery-image.json gallery-screenshot.json gallery-description.json gallery-select.json`。可信 gallery-business 操作配置见 services.example.yml，目标为现有 Flask 承载的 Business 模块；部署生成器通过 GALLERY_BUSINESS_URL 配置，数据库与特征客户端配置归 Business 模块。完整阶段接口与边界见 ../../docs/refactor/interfaces.md。
