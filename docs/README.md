# HXJM 开发文档

**版本：v0.2 · 开发设计基线 · 2026-10-26**

本组文档定义视频接入、录像与逐帧结果保存、样本特征、跨摄像头身份和活动、事件、业务检索、Agent交互及报告的完整协作流程，作为开发和联调的共同依据。

## 文档导航

| 文档 | 编号 | 负责定义 |
|---|---|---|
| [软件需求规格说明书](软件需求规格说明书.md) | HXJM-SRS-001 | 使用场景、功能行为、业务及统计规则、质量要求、验收条件和追踪关系 |
| [系统架构说明书](系统架构说明书.md) | HXJM-ARCH-001 | 系统边界、模块职责、运行时序、数据维护、故障处理及替换边界 |
| [数据库说明文档](数据库说明文档.md) | HXJM-DATA-001 | 库表目录、物理字段、标识/唯一与引用约束、DDL、读写事务、生命周期及兼容迁移 |
| [接口文档](接口文档.md) | HXJM-API-001 | 模块输入输出、权限、状态、错误、重复处理、业务任务及组件接入协议 |

建议按需求、架构、数据、接口的顺序阅读，再依据需求中的验收场景开展联调。需求说明书同时承担产品需求与验收定义，各项分析直接编入对应文档。

## 模块协作与接口责任

下表是当前版本的协作基线。表中的“负责”表示对公共输入、输出和联调结果负责，不限制负责人选择语言、模型、部署方式或内部数据结构。每个模块只通过本文件及接口文档定义的业务对象协作；不得直接读取其他模块的私有表、私有缓存或服务器文件路径。

| 当前工作方向 | 负责实现的边界 | 主要调用或接收 | 必须交付和遵守 |
|---|---|---|---|
| `hxjm-wsc`：实时目标检测与跟踪 | 从来源会话取得实时帧，维护跟踪上下文，提交实际产生的逐帧类型化成果，并提供实时展示订阅 | `sources.list`、`media.resolve`、`results.register`；组件实时接口 `component.analysis.health`、`component.analysis.subscribe` | 每个结果携带来源、输入帧、时间基准、跟踪上下文和处理版本；实时订阅不代替可靠登记；跟踪器重启不得复用旧上下文和局部编号 |
| `wyf`：特征服务及旧跟踪、重识别适配 | 提供截图人员检测、单图与同轨迹多图特征计算，将已有轨迹、图库和特征接入统一样本、特征和身份关系 | `component.reid.health`、`component.reid.detect_person_crops`、`component.reid.extract_image`、`component.reid.extract_tracklet`；业务 `samples.register`、`samples.get`、`features.register`、`people.appearances`、`identities.associate` | 计算服务返回向量与特征空间，业务调用方完成可靠登记；旧字段通过适配映射读取，不让新消费者依赖旧表字段 |
| `hxjm-tzh`：事件/音视频分析能力（含行为、打架等事件算法） | 按能力声明读取实时或历史输入，提交事件所需的类型化成果，并关联事件证据 | `capabilities.describe`、`tasks.submit`、`results.register`、`events.register`、`evidence.attach` | 中间结果与业务事件分开；输出必须带覆盖范围、算法版本和失败范围；不能用本地临时库生成与主业务库冲突的事实 |
| `hxjm-dk`：垃圾等目标检测组件 | 提供图片或视频目标检测能力，通过适配层接入统一任务和成果契约 | `assets.query`、`tasks.submit`、`results.register` | 保留组件原始坐标和状态，在适配层转换为公共坐标及结果类型；异步任务、重复提交、依赖不可用和结果有效期按统一规则返回 |
| `hxjm-zwd`：Agent交互、图像检索和前端选择 | 维护多轮会话、素材上下文、多人候选选择和结果展示，调用共享业务查询 | Agent 组件 `POST /chat`、`POST /chat/stream`、`DELETE /sessions/{session_id}/memory`、`GET /tools`；业务 `search.by_image`、`search.select_candidate`、`search.get`、`people.appearances`、`reports.get` | 候选编号绑定会话和查询素材；业务查询与任务可按标识恢复，原生 SSE 回答不承诺断点续传；展示依据业务标识和覆盖信息 |
| `hxjm-wxl`：独立设备/机器人视频与状态接入 | 将设备视频、文件、遥测和动作结果映射到统一来源、资产、结果和任务对象 | `sources.list`、`assets.register`、`results.register`、`tasks.submit` | 视频、设备状态、设备动作分开建模；状态上报不等于动作完成；设备掉线和重复上报可恢复，不能覆盖历史事实 |
| `hxjm-fyk`：平台后端、统一查询与登记 | 维护来源、资产、任务、成果登记和正式人员登记，提供身份、轨迹、活动、事件、报告查询及后台权限 | `sources.list`、`streams.open`、`streams.update`、`assets.register`、`tasks.submit`、`tasks.update`、`results.register`、`identities.enroll`、`people.appearances`、`statistics.query`、`activities.get`、`events.query`、`events.get`、`evidence.get`、`reports.query`、`reports.get` | 为页面、后台、算法与 Agent 提供同一业务语义；负责稳定标识、幂等、事务边界、权限、生命周期及兼容映射，组件协议在适配层转换 |

模块负责人在实现前须确认自己的输入来自哪个业务对象、输出交给哪个维护方，以及失败后由谁重试。新增算法只需注册能力、声明输入/输出类型、实现任务状态和成果登记；启动、停用或迁移算法实例不删除已有录像、结果、身份、活动或报告。

### 多人开发的共同规则

1. 先阅读本目录的需求、架构、数据和接口四份文档；实现以接口文档的操作标识和数据库文档的字段定义为准，内部实现不反向改变公共含义。
2. 请求与响应按各接口卡片的适用字段提交：需要去重的写操作沿用 `request_id`，`trace_id` 按卡片传入或由接收方生成；来源、输入引用、`run_id` 和 `schema_version` 只在对应操作或类型载荷要求时提供。重试沿用逻辑请求标识，重新执行新建执行标识。
3. 结果登记、特征计算、事件生成和报告更新均保留已完成范围及缺口。禁止用“空数组”掩盖未分析、未保存、录像不可用或依赖失败。
4. 实时 WebSocket/SSE 只负责展示、通知或流式交互；需要历史查询的结果必须通过可靠登记操作落库，并提供可重试的确认结果。
5. 算法不得把局部 `track_id`、显示序号、姓名或文件名当作跨会话主键；通过 `source_id`、`stream_session_id`、`tracking_context_id`、`tracklet_id` 等公共标识衔接。
6. 修改公共字段、枚举、错误码、事件结构或生命周期时，先更新接口文档和受影响的数据定义，再实现兼容映射；新增字段优先向后兼容，删除或改义必须提供迁移和切换条件。
7. 每个模块至少提供健康状态、输入依赖状态、可重试错误和一条端到端联调样例；远程部署的算法还要提供启停状态、实例版本、心跳和结果回传状态。

### 推荐联调顺序

先用一条来源验证 `sources.list → streams.open → media.resolve`，再验证 `component.analysis.subscribe` 的实时消息和 `results.register` 的可靠保存；随后验证 `assets.register`、`assets.query`、`results.query` 与历史回放，再接样本、特征、身份活动、事件证据和报告；最后接入 Agent 多轮查询、多人选择、后台管理及 `instances.configure`、`instances.query` 的算法实例配置与就绪查询。每一步先验证稳定标识、时间范围、幂等和覆盖，再验证页面展示。

## 定义归属与协作

- 业务行为、保留规则和统计口径以需求说明书为准。
- 模块职责、主链协作和运行边界以架构说明书为准。
- 数据库、表、字段、标识、键约束、数据关系、读写事务与生命周期以数据库说明文档为准。
- 交换字段、调用前后条件、错误和交互协议以接口文档为准。

数据库保存结构化业务数据、关系和特征；`/data/nfs_storage`保存录像、图片及大型文件产物。页面、后台、算法和Agent通过相同业务对象协作。设计规定公共契约，模块内部的数据布局和实现技术由相应实现维护。

## 版本与维护规则

本轮文档统一为**v0.2**；本版本内的补充、修正及持续讨论均沿用v0.2，只有明确决定发布新版本时才更改版本号。报告内容的`revision`、接口载荷的`schema_version`与文档版本分别维护。

每份核心文档保留编号、版本、日期、范围、目标读者、关联文档和修订记录。需求编号保持稳定，修改一条业务规则时同步更新受影响的架构、数据、接口和验收条目；详细定义只在归属文档维护。

文档按开发规格编写，规格基线与功能交付状态分别管理。涉及新的业务取舍先通过团队讨论明确，再纳入正文；实现细节在不改变公共契约的前提下由开发环节决定。

## 编制参考

| 参考资料 | 采用内容 |
|---|---|
| [阿里巴巴Java开发手册（P3C）](https://github.com/alibaba/p3c) | Java命名、异常和代码质量检查要点；不作为API契约格式标准 |
| [腾讯云MySQL使用规范](https://cloud.tencent.com/document/product/236/13390) | 库表、索引与SQL设计检查；按数据引擎与项目负载裁剪 |
| [arc42](https://arc42.org/overview/) | 系统上下文、模块职责、运行场景及跨模块规则的组织方式 |
| [IBM数据建模说明](https://www.ibm.com/think/topics/data-modeling) | 概念、逻辑与物理模型分层；本版展开物理字段、约束与增量DDL |
| [PostgreSQL约束](https://www.postgresql.org/docs/current/ddl-constraints.html)及[pgvector](https://github.com/pgvector/pgvector) | 唯一/外键/空值、有效关系索引、向量类型与检索限制 |
| [OpenAPI 3.1.1](https://spec.openapis.org/oas/v3.1.1.html) | 请求、响应、参数、认证和错误等接口描述要素 |
| [Apifox接口设计指南](https://docs.apifox.com/api-design-guidelines) | 接口卡片、公共参数、响应结构、示例及错误状态的组织方式 |
| [腾讯WeKnora API文档](https://github.com/Tencent/WeKnora/blob/main/website-docs/04-api/01-api-overview.md) | Agent鉴权、RBAC、统一错误、分页、异步任务与SSE恢复的参考 |
| [阿里云ECS API参考](https://help.aliyun.com/zh/ecs/developer-reference/api-ecs-2014-05-26-describeinstances) | 按操作描述权限、参数类型/必填/示例、分页、返回字段和兼容变更 |
| [火山引擎OpenAPI公共参数与签名](https://www.volcengine.com/docs/6291/64948) | 参考字节系公开云接口的公共请求参数、认证和签名边界；不引入其具体云产品协议 |
| [CloudWeGo Hertz Swagger示例](https://github.com/cloudwego/hertz-examples/tree/main/bizdemo/hertz_swagger_gen) | 从IDL明确路径、请求体、校验、枚举和响应的做法 |
| [NASA软件工程文档内容建议](https://nodis3.gsfc.nasa.gov/displayDir.cfm?Internal_ID=N_PR_7150_002D_&page_name=Chapter6) | 按项目规模裁剪交付物，将需求、设计与验证关系直接关联 |

依据团队规模与主链开发需要裁剪文档内容，采用统一术语、明确约束和可验证结果。数据库说明文档固定本版的库表、字段、约束及必要访问索引，兼容保留MySQL hxjm_sm与PostgreSQL postgres.public。开发语言、队列、具体算法和Agent框架在公共契约下选择与替换。

公开资料中没有一份可以直接套用的“阿里、腾讯或字节统一项目接口文档格式”。本版采用 OpenAPI/Apifox 的参数与响应组织方式，参考阿里云、腾讯 WeKnora、火山引擎和 CloudWeGo 的公开接口结构；Agent 的 SSE、断线恢复、算法远程健康和组件兼容规则在接口文档中补充描述。参考公开结构不表示项目采用相应厂商的框架或服务。
