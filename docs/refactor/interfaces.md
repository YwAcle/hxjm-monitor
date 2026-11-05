# 第一阶段公共接口

权威定义：业务能力使用 `contracts/capability-v1/{events,reports,identities,tracklets,gallery-*}.json`；算法描述使用同目录 `algorithm.schema.json`；公开成果元数据使用 `result-context.schema.json`。此文只说明调用关系，不复制 Schema。

## Agent 与 Business

正式路径为 Agent → 请求级 CapabilityBridge → `/api/v1/business/tasks` → 原 CapabilityPlatform/HTTP Adapter → Business API → 原 task_output。不重建 Registry、Executor、Agent 决策循环。

| 能力 | 动态工具 | Business API |
| --- | --- | --- |
| business.identities.query | query_business_identities | POST /identities/query |
| business.tracklets.query | query_business_tracklets | POST /tracklets/query |
| business.events.query | query_business_events | POST /events/query |
| business.reports.query | query_business_reports | POST /reports/search |

工具参数来自登记定义的 `input_schema.properties.payload`。可选 agent.context_inputs 将声明的字符串参数绑定为服务端 image_base64；目录投影原样传给工具，执行器覆盖模型伪造的值，不按工具名称识别图片。新增同类图片能力无需再修改 AgentExecutor。姓名先解析为 Business identity UUID，轨迹与报告再使用 identity_ids；不把旧 person_id 与 identity_id 混用。时间使用带时区 ISO8601；人员发现可不带时间，带时必须成对提交 start_at/end_at。Business 继续负责分页、来源授权和真实业务规则。

Agent 必须配置 CAPABILITY_BUSINESS_URL（以 `/api/v1/business` 结尾）、CAPABILITY_SERVICE_ID、CAPABILITY_SERVICE_TOKEN。不再使用 CAPABILITY_BRIDGE_ENABLED 开关，不回退旧数据库工具。目录失败返回 503；能力任务 failed 返回失败码并保留 task_id；pending/running/waiting_input 不表示空查询或成功。查询任务仍用 get_capability_task。

Agent `create_app(svc_cfg, llm)` 不接受 engine/db_cfg，`/ready` 检查目录和模型。`/persons`、`/reload_persons` 和 Agent 数据库/ReID CLI 参数退役；前端业务查询使用已有 Business API。纯本地 parse_time、super_resolve_image、会话记忆和会话图片保留。

## 图库 Business 接口

`modules/business/python/business_api` 拥有登记图库数据库访问、CLIP-ReID/Chinese-CLIP 客户端和截图选择状态，保留原 reid_target 数据与特征协议。由现有 Flask 进程承载，不新增微服务；Agent 决策模块不导入图库实现或 Repository。图库资源懒加载，不影响 Agent 无数据库启动。

四项能力 business.gallery.image/screenshot/description/select 经原 HTTP Adapter 调用 `POST /api/v1/business/gallery/{image,screenshot,description,select}`，分别暴露动态工具 search_pedestrians_by_image/search_pedestrians_in_screenshot/search_pedestrians_by_description/select_gallery_candidate。输入以 gallery-*.json 为准；共用 business.gallery.result。单项成功 payload 投影为原候选卡片形状，并保留 capability_task 引用；多成果和未完成任务保留任务形状。

截图返回 selection_required 后等待用户明确选择；选择传 source_asset_id 和 candidate_id，不接收 bbox。原图和检测框仅在 Business 进程保存五分钟，选择完成即消费；过期返回 selection_expired，要求重新上传。Agent 会话只保存脱敏工具引用，清空聊天不等于撤销已提交的业务任务。截图引用是服务侧短期随机引用，不是已登记证据 asset_id。

配置现有 CAPABILITY_SERVICE_ID/TOKEN 作为服务身份，并准备 DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME、REID_FEATURE_BASE_URL。Java 可信操作目标使用 GALLERY_BUSINESS_URL（现有 Flask 地址，须能从 backend 访问）；compose init 按该可选值生成 gallery-business 操作。不能使用容器自己的 localhost 指代另一个进程。未配置时不生成图库操作，不伪造可用状态。Business 端沿用服务令牌鉴权，不新增用户认证。

## 算法与视频运行时

视频扩展点为 `modules/perception-devices/python/video_analysis/algorithms.py` 的 AlgorithmSpec、Algorithm 协议及 ALGORITHMS。工厂是可信源码配置，不接受 Agent 指定导入路径。新增同模式算法只增加自己的 Adapter 和一项声明；Worker 不再按实现名称分流，调度器依据 tracking 保持摄像头粘性、上下文失效和重启语义。模型只在 spawned Worker 中导入和创建。

视频 Adapter 输入为 BGR uint8 图像和捕获元数据；infer 返回 `(detections, inference_ms)`。detections 保持已有归一化 xyxy、label、confidence、track_id/is_prediction 语义；last_removed_tracks 提供关闭的本地轨迹 ID。已有模型配置仍归各 Adapter，通过现有环境配置读取，不另造配置系统。

历史 `deepsort` 名称实际对应 YOLO 人员检测，描述为 person.detection；BoT-SORT 对应 person.tracking。原人员跟踪成果登记仍要求 tracking Adapter；第四阶段垃圾检测按声明的 garbage.detection 类型复用同一 Publisher，写通用算法成果，不伪造人员轨迹。

Video Analysis、ReID、垃圾检测新增只读 `GET /v1/algorithms`：items 为统一描述，runtime.state 为 ready/busy/degraded/unavailable，details 可保留本地状态。ReID 继续使用 person.reidentification / feature.embedding、真实 feature_space_id 和原 multipart API；垃圾检测继续原一次性图片/摄像头快照 API 与原坐标语义。描述接口不自动注册能力、不加载模型、不改变原推理协议。不同模式不强行共用视频帧接口。

## 结果

`GET /tasks` 的 outputs、`GET /tasks/outputs` 以及视频历史结果项增加 result_context，均符合唯一的 result-context.schema.json。原 payload、成果 ID、分页与幂等协议保留。

producer_id 是任务执行身份；source_ids 是明确绑定或显式请求的来源，空列表不表示全部摄像头。occurred_at 是观测时间，查询成果没有观测时间时为 null；registered_at 为数据库接收时间，不冒充模型处理时间。结果 producer_result_key、task_id/run_id 和 capability_code 来自已有持久化记录；evidence_refs 只登记已有素材引用，具体业务证据仍留在原 payload/证据 API。

持续视频仍直接经 ResultPublisher/Spool → `/results/register`，写 result_set/analysis_frame/algorithm_result；一次性 HTTP 能力仍经 `/tasks/complete` 写 task_output。不得把连续帧塞入 task_output。不修改已有 lease、执行令牌、去重和重试规则。

## 设备

最小公共接口在 `python/devices/__init__.py`：DeviceDescription、DeviceTask、DeviceStatus、DeviceFeedback、DeviceAdapter。Adapter 实现 describe/submit/status/feedback，并自行翻译设备协议。device_id 不是 camera source_id；摄像头继续使用既有来源与流 API。

协调方分配 task_id/run_id，设备必须保留它们作为外部执行引用；回报必须属于同一 run。运行中通过既有 heartbeat 管理，终态由协调方提供 expected_revision/execution_token，将 DeviceFeedback.completion 转为既有 complete/fail 请求。成功输出仍按登记 result_type/schema_version 校验。设备反馈不能获得或自行生成执行令牌。

本阶段仅提供 Adapter 接口，不添加 device 资源范围、设备表、SDK、硬件服务或后台调度。异步设备执行的 lease/取消策略和可信操作配置由后续阶段在现有任务平台内接入；当前同步 HTTP Executor 不伪装成长时间硬件任务。

## AI Infra

modules/ai-infra/python/ai_infra 提供共享 ModelConfig、settings、build_chat_model、ChatSGLang/ChatVLLM、图像编解码。Agent、报告及旧聊天模块直接引用这里；报告专用 prompt/parser 仍在报告服务。保留现有 invoke/stream/check_health/close、超时和重试行为。不新增模型路由平台；本地视觉算法继续其已有模型生命周期。


## 第四阶段业务接通

正式垃圾链路及真实协议限制以 `stage-4.md` 和 `robot-dog-integration.md` 为准。能力定义新增 `garbage-cleanup.json`，标准检测类型仍为既有 garbage.detection/1。公共入口为 GET `/api/v1/business/garbage/events`、POST `/api/v1/business/garbage/cleanup`；后者只接收 event_id/request_id，路线和设备地址只来自可信配置。设备异步执行复用现有 Java Capability tick/Task Attempt，不再限于同步 HTTP；真实反馈按同一 run 会话关联，不具备稳定外部 ID时如实返回 null，失联未知不重发。前述第一阶段的设备占位说明由此增量实现替代，Python公共协议保留用于其他设备接入。

## 本地报告 Worker 与运行时成果

正式报告 Worker 仅扫描未过期、已结束且具有权威身份的活动，以及 Business 中正式的 fire/behavior.fire 事件，保留已有模型提示词与生成实现。旧 VAD 数字 ID 不冒充 Business 事件 UUID；只有旧 VAD 行、尚无正式事件的火灾不会自动生成新版报告，须先由对应成果生产链登记正式事件。

报告依次调用 `/tasks` → `/tasks/start` → `/reports/register` → `/tasks/end`；能力定义为 `report-generation.json`。报告主体、执行引用、模型标识和证据引用通过 Business 校验，有效期由主体推导。报告标记 partial，不把抽样或缺失媒体声称为完整覆盖。`task_output` 保存 `business.report.reference/1`，正文仍由 Business 报告 API 查询。

`POST /tasks/end` 在原 `result_ids` 外支持 `outputs`，每项为 `result_type,schema_version,producer_result_key,payload`。Runtime 与任务归属、当前 run、revision 和过期检查保持不变；按提交任务时冻结的输出契约校验内容与大小。一次性成功必须引用已登记算法成果或提交有效内联成果。失败/取消不得提交内联成功成果。原 request_id 重试保持幂等，不修改 platform_managed 的完成入口。

本地报告投递状态保存于 REPORT_RUNTIME_DIR；请求发送前保存原始请求，回执丢失重发同一请求；不会重跑模型并覆盖原报告。该状态不是第二套业务报告库。

`GET /execution/status` 以 capabilities.describe 权限返回后端实际加载的 enabled 标志，不返回服务地址或令牌。Agent 启动前检查该接口、八项业务/图库能力、报告能力实例、图库数据库和 ReID 健康接口；失败直接退出。`/ready` 仍是模型/目录就绪检查，业务启动检查也不替代真实任务验收。
