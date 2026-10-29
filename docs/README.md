# HXJM 开发文档

**版本：v0.2 · 开发设计基线 · 2026-10-28**

本组文档定义视频接入、录像与逐帧结果保存、样本特征、跨摄像头身份和活动、事件、业务检索、Agent交互及报告的完整协作流程，作为开发和联调的共同依据。

本版历史查询、录像读取与播放、以图查人、人员登记及人员、样本、活动、事件、报告查询均直接访问，不要求用户登录、JWT或Cookie。页面与Agent使用同一共享业务范围：全部已登记视频来源及有效共享业务数据。新查询的 `query_request.owner_user_id` 为NULL，查询图的 `media_asset.meta.owner_actor_key` 为 `shared:business`；查询图最长七天，正式登记图按登记资料保存。不同对话仍由Agent的session_id区分，session_id不是数据权限。原有非空用户归属查询及其私有查询图片不自动改为共享。算法写入、输入会话、录像登记、特征写入和后台生成、修改及管理继续校验身份、操作和来源。版本保持v0.2。

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

| 业务模块 | 负责实现的边界 | 主要调用或接收 | 必须交付和遵守 |
|---|---|---|---|
| 实时目标检测与跟踪 | 从来源会话取得实时帧，维护跟踪上下文，提交实际产生的逐帧类型化成果，并提供实时展示订阅 | `streams.open`、`media.resolve_live`、`results.register`、`observations.subscribe` | 每个结果携带来源、输入帧、时间基准、跟踪上下文和处理版本；实时订阅不代替可靠登记；跟踪器重启不得复用旧上下文和局部编号 |
| 旧跟踪与重识别兼容方向 | 将已有轨迹、图库和特征查询接入统一的轨迹、样本、特征和身份关系 | `tracklets.query`、`samples.register`、`features.register`、`identities.associate` | 旧字段通过适配映射读取；特征必须带特征空间和来源；不新增绕开统一身份关系的公共主表，不让新消费者依赖旧表字段 |
| 事件/音视频分析能力（含行为、打架等事件算法） | 按能力声明读取实时或历史输入，提交事件所需的类型化成果，并关联事件证据 | `capabilities.describe`、`tasks.submit`、`results.register`、`events.register`、`evidence.attach` | 中间结果与业务事件分开；输出必须带覆盖范围、算法版本和失败范围；不能用本地临时库生成与主业务库冲突的事实 |
| 垃圾等目标检测组件 | 提供图片或视频目标检测能力，通过适配层接入统一任务和成果契约 | `assets.query`、`tasks.submit`、`results.register` | 保留组件原始坐标和状态，在适配层转换为公共坐标及结果类型；异步任务、重复提交、依赖不可用和结果有效期按统一规则返回 |
| Agent交互、图像检索和前端选择 | 维护多轮会话、素材上下文、多人候选选择和结果展示，调用共享业务查询 | `agent.chat`、`agent.stream`、`search.by_image`、`search.select_candidate`、`people.appearances`、`reports.get` | 候选编号绑定会话和查询素材；断线可恢复；展示必须依据业务标识和覆盖信息，不从自然语言或模型记忆猜测身份、时间或证据 |
| 独立设备/机器人视频与状态接入 | 将设备视频、文件、遥测和动作结果映射到统一来源、资产、结果和任务对象 | `sources.list`、`assets.register`、`results.register`、`tasks.submit` | 视频、设备状态、设备动作分开建模；状态上报不等于动作完成；设备掉线和重复上报可恢复，不能覆盖历史事实 |
| 主链平台与后台服务 | 维护来源、资产、任务、结果登记、身份/活动/事件/报告查询，以及权限和适配层 | 被上述模块及页面、后台、Agent共同调用 | 负责稳定标识、幂等、事务边界、权限、生命周期和兼容映射；对外只发布统一业务对象，组件协议通过适配层隔离 |

模块负责人在实现前须确认自己的输入来自哪个业务对象、输出交给哪个维护方，以及失败后由谁重试。新增算法只需注册能力、声明输入/输出类型、实现任务状态和成果登记；启动、停用或迁移算法实例不删除已有录像、结果、身份、活动或报告。

### 多人开发的共同规则

1. 先阅读本目录的需求、架构、数据和接口四份文档；实现以接口文档的操作标识和数据库文档的字段定义为准，内部实现不反向改变公共含义。
2. 写入统一业务对象必须携带 `request_id`、`trace_id`、来源或输入引用、执行 `run_id`（适用时）和 `schema_version`；重试沿用请求标识，重新执行新建执行标识。
3. 结果登记、特征计算、事件生成和报告更新均保留已完成范围及缺口。禁止用“空数组”掩盖未分析、未保存、录像不可用或依赖失败。
4. 实时 WebSocket/SSE 只负责展示、通知或流式交互；需要历史查询的结果必须通过可靠登记操作落库，并提供可重试的确认结果。
5. 算法不得把局部 `track_id`、显示序号、姓名或文件名当作跨会话主键；通过 `source_id`、`stream_session_id`、`tracking_context_id`、`tracklet_id` 等公共标识衔接。
6. 修改公共字段、枚举、错误码、事件结构或生命周期时，先更新接口文档和受影响的数据定义，再实现兼容映射；新增字段优先向后兼容，删除或改义必须提供迁移和切换条件。
7. 每个模块至少提供健康状态、输入依赖状态、可重试错误和一条端到端联调样例；远程部署的算法还要提供启停状态、实例版本、心跳和结果回传状态。

### 推荐联调顺序

先用一条来源验证 `sources.list → streams.open → media.resolve_live`，再验证 `observations.subscribe` 的实时消息和 `results.register` 的可靠保存；随后接入录像资产和历史查询，再接样本/特征、身份活动、事件证据和报告；最后接入 Agent 多轮查询、多人选择、后台管理及远程算法启停。每一步先验证稳定标识、时间范围、幂等和覆盖，再验证页面展示，避免先把展示消息当作业务事实。

## 阶段一开发接入

### 阶段一接入范围

阶段一以来源、连续输入会话、能力及实例、业务任务、执行尝试、媒体资产和类型化成果作为公共底座，提供来源查询、录像登记、逐帧及其他算法成果登记、历史查询与媒体读取。公共服务的实际请求路径、字段和授权操作在[接口文档](接口文档.md)“阶段一业务服务 HTTP 接口”中逐项定义。样本、特征、身份、活动、事件及报告继续采用本组文档的业务对象；这些后续模块通过公共标识、输入引用和结果类型接入底座。

接入按以下顺序执行：

1. 依据数据库说明完成阶段一增量结构：保留 camera、camera_stream、media_asset、tracklet，新增本期任务、会话、成果及覆盖等17张表。迁移脚本为[阶段一迁移](../python/base/postgresql/stage1/001_video_results.sql)，不以运行应用代替建库迁移。
2. 明确每路来源的 camera.id，以及属于该来源的启用 camera_stream.id。来源查询返回全部流目录；一个来源存在多个目录时，在接入配置中明确选择。创建来源不会自动创建流目录，也不使用摄像头名称、网络地址或流路径推算 UUID。
3. 配置业务服务的数据库连接、存储根目录、服务身份和来源授权，显式启用业务 API。
4. 通过 result-types、capabilities、instances 接口发布结果结构、能力契约和实例配置。它们是部署初始化操作，运行适配器不会在每次启动时重新创建这些目录。
5. 为实时分析配置来源 UUID、流目录 UUID及实例 UUID。适配器从实际输入帧携带的会话信息打开输入会话，再创建任务和执行尝试，将成果交给可靠登记接口。
6. 统一输入将同一条 PyAV 连接的编码包交给后台录像，解码帧交给 FrameHub。录像封片并生成清单后，后台登记线程通过 assets/register 提交真实文件范围、大小、摘要、来源会话及 recording_alignment。MediaMTX 继续提供独立直播分发，新录像由统一输入生产。
7. 页面、后台和 Agent 通过 results/query、assets/query、media/resolve 读取公共业务对象。正常历史结果查询采用已确认并关闭的成果覆盖及当前结果选择关系；按指定成果集查询可用于查看仍在收集的结果。

### 业务服务开关与授权

业务 API 的开关为 hxjm.business.enabled，默认不启用。启用后使用现有 PostgreSQL 数据源 slaveDataSource；媒体根目录 hxjm.business.storage-root 默认为 /data/nfs_storage/hxjm。来源、任务、成果、覆盖和文件引用写入监控业务库，文件内容保存到受控存储根目录。

服务身份在 hxjm.business.security.services 下逐一配置。每项包含独立 token、允许的 operations 和 source-ids；空授权不允许调用，操作名和来源 UUID 均须明确列举。实时成果适配服务的最小权限示例：

~~~yaml
hxjm:
  business:
    enabled: true
    storage-root: /data/nfs_storage/hxjm_datas
    security:
      services:
        tracker-adapter:
          token: ${HXJM_TRACKER_SERVICE_TOKEN}
          operations:
            - streams.open
            - tasks.submit
            - tasks.start
            - results.register
            - assets.register
          source-ids:
            - 10000000-0000-4000-8000-000000000001
~~~

令牌由部署环境注入，不写入代码、配置示例或结果队列。服务请求同时发送 X-HXJM-Service-Id 和 X-HXJM-Service-Token；修改授权会影响后续请求，不能依赖曾经成功调用取得长期权限。

| 接入身份 | 按职责授予的操作 |
|---|---|
| 来源与目录初始化服务 | sources.register、sources.query、capabilities.register、result_types.register、instances.configure |
| 实时或离线成果适配服务 | streams.open、streams.close、tasks.submit、tasks.start、tasks.get、results.register；仅授予实际需要的项目 |
| 录像文件生产服务 | streams.open、assets.register；需要解析和读取媒体时增加 assets.query、media.resolve |
| 页面、后台、Agent 查询 | sources.query、capabilities.describe、tasks.get、assets.query、results.query、media.resolve；需要创建业务任务时增加 tasks.submit |

本版历史查询、录像读取与播放、以图查人、人员登记及人员、样本、活动、事件、报告查询均直接访问，不要求用户登录、JWT或Cookie。页面与Agent使用同一共享业务范围：全部已登记视频来源及有效共享业务数据。新查询的 `query_request.owner_user_id` 为NULL，查询图的 `media_asset.meta.owner_actor_key` 为 `shared:business`；查询图最长七天，正式登记图按登记资料保存。不同对话仍由Agent的session_id区分，session_id不是数据权限。原有非空用户归属查询及其私有查询图片不自动改为共享。算法写入、输入会话、录像登记、特征写入和后台生成、修改及管理继续校验身份、操作和来源。

### 监控首页布局

桌面监控首页填满浏览器可用区域，三栏按约1∶2∶1分配宽度，主体占满标题下方的剩余高度。页面装饰和文字按窗口宽度保持一致的视觉比例，各栏宽高由布局分配；窗口缩放不裁切整页，也不留下页面外白边。四路摄像头维持两行两列，视频按原始比例完整显示，比例差异形成的黑边不拉伸填充；检测框按视频实际显示范围绘制。列表、报告和对话在各自区域滚动，输入框保持可见，报告保留原有展开／折叠操作。空报告和空告警不因无数据自动收缩。历史查询与录像弹窗独立于首页布局，按浏览器窗口定位。

### 实时成果适配配置

未设置 VIDEO_ANALYSIS_BUSINESS_CONFIG 时，实时分析继续提供原有实时功能，不创建可靠成果队列或业务 API 客户端。设置该变量后，它指向一份 JSON 配置文件，文件只保存服务位置、标识、映射和令牌环境变量名。

| 配置项 | 类型及必填 | 规则 |
|---|---|---|
| api_url | 字符串，必填 | 完整业务根地址，路径为 /api/v1/business；不携带账号、令牌或查询参数 |
| service_id | 字符串，必填 | 与业务服务中配置的服务身份一致 |
| token_env | 字符串，必填 | 存放当前服务令牌的环境变量名；启动时必须已注入 |
| source_streams | 对象，必填 | source UUID 到 camera_stream UUID 的映射；完整覆盖本服务全部已配置来源 |
| instances | 数组，必填 | 每项为 source_id、algorithm、instance_id、capability_code；完整覆盖全部来源与本进程当前算法，不重复绑定 |
| spool_dir | 绝对路径，可选 | 默认 /data/nfs_storage/hxjm_datas/result-spool；目录准备和文件访问在后台执行。存储不可用时投递状态进入 retrying，实时分析继续；不切换本地临时目录 |
| timeout_seconds | 正数，可选 | 单次业务 HTTP 调用超时秒数，默认5 |
| batch_size | 正整数，可选 | 单批最多汇集的实际帧结果数，默认32 |
| queue_size | 正整数，可选 | 等待后台保存的内存帧队列容量，默认256；满时明确报告交接失败 |
| flush_interval_seconds | 正数，可选 | 后台组批等待秒数，默认0.2 |

单路配置示例：

~~~json
{
  "api_url": "https://business.example.invalid/api/v1/business",
  "service_id": "tracker-adapter",
  "token_env": "HXJM_TRACKER_SERVICE_TOKEN",
  "source_streams": {
    "10000000-0000-4000-8000-000000000001": "20000000-0000-4000-8000-000000000001"
  },
  "instances": [
    {
      "source_id": "10000000-0000-4000-8000-000000000001",
      "algorithm": "botsort",
      "instance_id": "30000000-0000-4000-8000-000000000001",
      "capability_code": "tracking"
    }
  ],
  "spool_dir": "/data/nfs_storage/hxjm_datas/result-spool",
  "timeout_seconds": 5,
  "batch_size": 32,
  "queue_size": 256,
  "flush_interval_seconds": 0.2
}
~~~

该示例对应的摄像头与来源设置：

~~~bash
export VIDEO_ANALYSIS_CAMERAS='{"camera_1":"rtsp://media.example.invalid/live/camera_1"}'
export VIDEO_ANALYSIS_SOURCE_IDS='{"camera_1":"10000000-0000-4000-8000-000000000001"}'
export VIDEO_ANALYSIS_BUSINESS_CONFIG="/absolute/path/to/business.json"
~~~

四路运行时，VIDEO_ANALYSIS_SOURCE_IDS、source_streams 和 instances 必须完整列出四路映射。服务令牌通过 token_env 指定的变量独立注入。每个投递进程独占自己的 spool_dir；部署多个独立写入进程时，显式分配不同队列目录。

### 帧、成果确认与历史查询

FrameHub 在同一进程内共享每路解码帧及其 source_id、stream_session_id、frame_id、frame_seq。输入重连建立新的输入会话，跟踪器重置建立新的跟踪上下文。后台适配器使用帧上保留的输入会话起点与尺寸，避免把队列中的旧帧关联到重连后的会话。

统一输入分别维护实际接入开始时刻和媒体 PTS 零点对应的时间原点，公共帧及录像清单保留相同元信息。输入 PTS 与文件内偏移使用非负整数毫秒，毫秒的小数按四舍五入转换。旧实时消息的 stream_session_id 保留分析上下文语义；input_stream_session_id 返回真实输入会话，tracking_context_id 返回跟踪上下文 UUID。可靠成果的 stream_session_id 始终为公共输入会话 UUID。

### 统一输入与后台录像配置

业务侧采集环境、PyAV依赖及PYTHONPATH由业务侧主机配置和本机运行副本管理，当前共享源码与运行布局见 [业务侧NFS部署说明](NFS主目录启动说明.md)，不再将旧开发工作区路径作为当前运行位置；每路配置 VIDEO_ANALYSIS_SOURCE_IDS、业务配置 source_streams 和 instances，服务 token 由 token_env 指定的环境变量提供。

| 配置项 | 默认值 | 规则 |
|---|---|---|
| VIDEO_ANALYSIS_RECORDING_ENABLED | false | 设为 true 启用统一输入和后台录像；必须同时设置完整来源 UUID 映射 |
| VIDEO_ANALYSIS_RECORDING_ROOT | /data/nfs_storage/hxjm_datas | 存储根目录；与公共后端 hxjm.business.storage-root 一致，录像写入 recordings 子目录 |
| VIDEO_ANALYSIS_RECORDING_SEGMENT_SECONDS | 3600 | 目标分段秒数，到达后等待下一个关键帧封片；封片后登记并开放历史读取 |
| VIDEO_ANALYSIS_RECORDING_QUEUE_SIZE | 256 | 每来源等待录像写入的编码包数量上限；交接不等待磁盘写入 |
| VIDEO_ANALYSIS_RECORDING_RETENTION_SECONDS | 604800 | 七天；启用业务登记时固定采用该期限 |
| VIDEO_ANALYSIS_DECODE_THREADS | 1 | 每路解码线程数，允许1至8；不为每路创建随主机核心数增长的解码池 |

录像文件键为 recordings/{source_id}/{stream_session_id}/{asset_id}.mp4。文件旁的 .manifest.json 保存登记请求、原始会话元信息和时钟映射；.manifest.json.ack 保存清单摘要与登记确认。未设置 VIDEO_ANALYSIS_BUSINESS_CONFIG 时只执行文件录制；完成历史查询链路时必须配置业务投递，并为同一服务身份授予 streams.open 与 assets.register。登记线程在启动后及收到封片通知时扫描清单，重试沿用清单中的原请求标识，确认标记匹配时跳过重复提交。

/health 的 recording 按来源返回队列、接收/拒绝/写入包数、已封片数和最近错误；recording_delivery 返回待登记数、已确认数、被拒绝清单数及线程状态。文件已封片、已登记和成果已保存是三个独立状态，分别核对。

### 成果确认与实时发布

实时分析通过 ResultDispatcher.defer 交接无像素的帧元数据和完整检测列表；历史成果载荷的构造、会话及任务解析、组批、NFS 写入和 HTTP 提交均在后台执行。交接使用有容量上限的内存队列，不等待文件或数据库确认；交接失败通过 result_handoff 和 result_delivery 状态报告，不阻塞实时推理。ResultSpool 初始化不执行 NFS 目录检查或创建；后台首次访问时准备目录，失败后进入 retrying 并保留已接收的未确认结果继续重试。

实时检测不设置按服务器可用内存数值暂停模型加载或推理的门槛。实际发生的内存分配失败、模型进程退出和推理超时仍由进程监督及重试逻辑处理。

单帧历史载荷校验失败计入 invalid_frames 并记录 last_invalid_error，不计为保存成功；同批及后续有效帧继续登记。执行配置或批次契约错误仍作为投递配置故障报告。

调用结果登记接口取得每条成果的接受或重复确认后，才清理对应未确认请求。启用 close_for 后，完整批次全部确认时，先持久保存一个新的 closed=true 覆盖确认请求，再删除原请求；覆盖确认也走同一投递与重试流程。普通历史查询据结果选择关系返回当前采用的结果。开放覆盖、未登记帧或未处理范围不能解释为没有目标。

同一成果集内，各 result_type、schema_version 和处理窗口分别维护覆盖清单，不能互相覆盖。服务端使用成果集标识、窗口起止、成果类型和结构版本生成 coverage_key，并在 frame_manifest_json 中保存 result_type、schema_version、完整输入帧或成果清单、已保存标识和缺口。重复投递沿用同一类型、版本和窗口；生产方不自行生成覆盖键。

一个任务请求多种 requested_outputs 时，各类型按共同的处理窗口分别提交并关闭覆盖。只有该成果集内每个请求类型的有效、已闭合、可靠保存范围都覆盖本次声明窗口，且该执行仍是当前执行，服务才自动采用该窗口中尚未选定的范围。某一类型保存成功仅确认该类型，其他类型未齐时已保存成果仍可按 result_set_id 查询；默认历史查询等待全部请求类型就绪。后续重算保留已采用关系，不直接替换原范围。

可靠登记保留完整检测结果，包括零目标帧和预测目标；现有实时 WebSocket 仍保留每帧最多500个目标的展示上限，展示截断不限制可靠登记。逐帧的 stream_pts_ms 表示输入流的媒体位置；只有完成实际文件对齐后才填写 media_asset_id 与 media_pts_ms。录像登记、分析成果与历史查询分别说明自身覆盖。

普通实时订阅在推理完成后发布结构化结果，不等待 JPEG 编码。frames=1 用于同帧图像与检测结果的诊断查看，每路摄像头最多保留一个正在执行的图片编码任务；编码繁忙时跳过该次诊断图片，图片错误不重置已成功的推理或跟踪状态。主监控画面独立持续播放，过期框退出显示并提示分析延迟，下一条有效结果到达后恢复；有效零目标结果清空标注并恢复正常分析状态。

FrameHub 的共享范围是当前进程。远端算法通过显式适配器使用公共来源、会话、任务、结果结构和资产读取接口；本阶段不提供跨网络取帧服务。后续增加算法、迁移算法服务器或替换内部处理实现时，继续沿用这些标识、成果类型、确认和查询契约。

## 人员主链与 Agent 接入

本地人员主链的HTTP入口统一为 `/api/v1/business`。接口文档第8章逐项描述实际请求字段、响应、权限和失败处理，第9章交付远端Agent的对接职责。

数据库依次执行[人员业务结构迁移002](../python/base/postgresql/stage2/002_identity_business.sql)与[报告主题约束迁移003](../python/base/postgresql/stage2/003_report_subject_constraint.sql)。003移除旧 `ck_llm_report_source_exclusive`，新报告主题关联统一由 `ck_report_subject` 约束；002历史文件保持不变。

| 开发环节 | 接入顺序及必须保留的业务引用 |
|---|---|
| 历史轨迹特征 | 从可靠保存的真实观测取得样本图片，assets/upload → samples/register → features/register → identities/associate；保留input_frame_id、tracklet_id、sample_id、feature_id及feature_space_id |
| 正式登记图库 | 上传独立登记图片并调用identities/register；特征处理器从samples/pending读取待提取样本，再登记同空间特征 |
| 特征处理任务 | 服务建立自己的任务及执行，特征登记成功后调用tasks/finish；该完成入口只适用于请求feature.embedding的一次性任务 |
| 用户图片查询 | 用户上传query素材并创建queries；处理器读取queries/pending、登记查询样本、提交queries/candidates；多人时用户queries/select，随后处理器提取特征并调用search |
| 人员活动与路线 | identities/associate组织身份及活动；activities/query或activities/{id}读取跨摄像头路线，reports/query读取当前报告，媒体入口解析录像证据 |
| 事件算法 | 先可靠登记类型化成果，再events/register关联业务结论、参与对象及证据；events/{id}和主题报告接口供页面、后台及Agent读取 |
| Agent交互 | 页面通过同源/api代理直接访问；Agent不要求或转发用户JWT，仅按session_id隔离。本地业务接口采用共享查询归属及媒体读取；后台处理继续使用自身服务身份 |

首期每条轨迹选择首个真实人员有效框，采用单样本特征，聚合类型为single。采样、特征聚合及匹配在各自处理模块内适配；增加多样本策略时，同步调整该模块内的采样去重、特征任务标识及聚合规则，选框器仅负责候选选择。调整后仍使用样本、贡献关系、特征空间、身份及活动公共契约，不要求其他消费者改变输入输出。人员活动无新真实观测后的正常结束窗口由hxjm.business.local-reports.inactivity-seconds配置，默认60秒。活动结束后本地生成person_route结构化报告，不等待远端Agent；录像或覆盖补齐后沿用report_id更新revision和内容。

本阶段本地交付素材保存、查询候选、样本特征、身份活动、事件、报告及受控媒体读取。远端负责人接入免登录工具调用、对话上下文及SSE展示，详见接口文档第9章；本地验证使用HTTP请求模拟工具调用，不要求远端服务先启动。对话或模型框架替换时继续使用业务query_id、identity_id、activity_id、event_id和report_id，不把模型记忆当作业务数据存储。

## yh Agent 首版接入状态

本轮yh侧优先打通“直接访问→图片查询→多人选人→查询进度与命中→明确选定目标→人员活动→已有路线报告→录像回放”的正常流程。Agent负责理解用户意图、调用业务接口、组织回答和处理交互；检测、特征提取、检索、录像定位、数据关联、存储及业务规则由本地业务侧管理。本首版读取已有person_route报告，不生成或登记独立Agent分析报告。

| 项目 | 当前交付与边界 |
|---|---|
| 业务接入 | yh已完成业务HTTP客户端、原7个业务工具并扩展至17个工具（含本地能力）、无JWT入口、会话引用及普通/SSE响应的代码接入；设置AGENT_BUSINESS_BASE_URL启用business模式，不直查业务数据库或NFS |
| 当前业务地址 | http://192.168.109.191:18480/api/v1/business；单次请求超时AGENT_BUSINESS_TIMEOUT_S默认15秒 |
| 直接访问与会话 | 不调用/getInfo，不要求或转发用户JWT、Cookie或Agent服务身份头；仅按session_id隔离，相同会话号共用上下文；不同会话可引用同一共享query_id，本地选中状态独立，业务选择冲突由revision控制 |
| 页面协作 | 现有/api同源代理保留session_id及请求体，不要求Authorization；普通响应保留data并提供result别名，results返回本轮全部结构化结果，SSE沿用result事件；页面需识别person_query等新业务类型及归一化候选框 |
| 报告与回放 | 保留已有报告的report_id、revision、report_json、coverage及证据；回放保留全部录像分段和offset_ms，页面直接申请播放凭证 |
| 单帧记录 | 正常展示；首次与最后观测时间相同不调用区间解析、不扩大范围；无可用录像定位时提示“当前记录暂无可用回放”，继续其他流程 |
| 验证范围 | Agent入口、业务客户端、工具与执行器已用模拟业务HTTP响应验证，覆盖无JWT普通/SSE、不同session_id隔离及错误传播；2026-10-27旧部署下Agent服务器无凭据访问sources曾收到401，仅为历史网络探测，不代表新版状态；模型接口已完成最小生成；业务侧直接访问、实际Agent工具流程、浏览器选人及播放整链尚待联合验证 |

联调按[接口文档第9章](接口文档.md#9-远端-agent-接入交付)执行。页面及Agent直接调用已开放的查询、登记与媒体接口，不提供用户令牌或虚构用户ID。后台图片处理器仍使用独立服务凭据。本轮更新不启动页面、后端或远端Agent；部署更新与联合验证分别执行。

单帧帧定位能力可由业务侧后续核实，不阻塞非空区间回放。姓名到身份、全局事件列表及全局报告发现已完成本地业务查询代码；远端适配与实际联合联调分别验收；详见接口文档第9.8节。本轮不调整数据库、既有业务规则或后台处理协议。

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

### v0.2 免登录查询增量更新

已有阶段二数据库执行 [004_shared_queries.sql](../python/base/postgresql/stage2/004_shared_queries.sql)，仅放宽public.query_request.owner_user_id非空限制，不改写原有归属、主键或关联。新库依次执行001_video_results.sql、002_identity_business.sql、003_report_subject_constraint.sql和004_shared_queries.sql。页面移除登录、验证码和退出入口；业务请求和Agent请求不附带Authorization或Cookie。人员登记操作直接生效，共享查询可由拿到query_id的页面或Agent继续选择候选；并发选择仍通过revision返回409，过期仍返回410。

本轮本地检查：前端测试和生产构建通过；后端离线编译、打包以及身份、历史结果和重复处理检查通过。在本机PostgreSQL服务器创建的path/uuid两套临时数据库内，已验证共享图片上传、NULL归属查询、候选提交及选择、登记、重复请求和到期处理，测试库已删除。004_shared_queries.sql已应用当前业务库。应用与远端Agent未启动，本轮没有进行浏览器或远端联合验收。


### yh旧版能力恢复交付（v0.2，2026-10-28）

现有联调进程不自动重启。已验证过sources无凭据200、模型就绪和yh普通对话，不等于本轮新增接口已部署或完成真实业务验收；此前401及“应用未启动”属于历史记录。

| 旧版能力 | yh本轮交付 | 业务侧配合 |
|---|---|---|
| 时间解释、看图/计数/读图、历史图片追问及2/4倍插值放大 | 本地能力与会话图片缓存 | 无新增接口 |
| 登记名单、完整姓名解析 | 目录适配、重名选择、total与分页边界 | identities/query已实现精确姓名筛选和分页 |
| 按姓名查轨迹 | 姓名→真实身份→轨迹查询与展示 | tracklets/query已实现 |
| 按人员/时间查报告 | 已有报告发现与事实组织，不写入 | reports/search已实现，按业务发生时间筛选 |
| 最新/时段事件 | 模式及时间语义分离、错误传播 | events/query已实现，返回全类型业务事件 |
| 单人/多人图查人、活动、路线报告与回放 | 保留共享接口主链，增加自然序号及原任务衔接 | 按既有接口联合验收 |
| 文字外观搜人 | 按本轮决定暂缓 | 本轮不要求 |

**给另一侧的交付入口是[接口文档第9.8节](接口文档.md#98-yh-agent-旧版能力恢复与本地查询契约v02)**。该节明确查询路由、字段、分页、排序、错误、示例和页面结果类型；本地业务服务负责数据与算法关系，远端Agent按这些HTTP契约适配工具，不直连数据库或复制业务关联逻辑。五份文档继续为v0.2，无数据库迁移。完整工具用法及示例问题由远端Agent项目的使用说明维护。

## 本地发现查询交付（v0.2，2026-10-28）

本地补齐姓名精确匹配和身份分页、POST tracklets/query、POST events/query、POST reports/search。页面与Agent免登录共享查询，数据库结构不变；事件入口返回全部业务事件，不把正常事件当作异常。按姓名取身份后查轨迹及已有报告，按业务发生时间发现事件和报告。人员关联、来源及发生时间从现有关系取得，报告只读当前修订。

页面支持登记目录、轨迹、事件、报告、来源、时间、明确选择、图片查人及图片放大结果，普通和SSE保留同一轮全部工具产出；已有图片选人和媒体分段播放继续使用公共业务标识。代码更新不自动重启服务，也不代替远端Agent工具、真实图片及录像播放的联合验收。

## 稳定运行目录

本机业务端的主目录、主机配置、启停及日志位置见 [NFS 主目录启动说明](NFS主目录启动说明.md)。版本保持 v0.2。


## 文档统一维护

项目规格统一维护于共享根目录的 `docs`，Agent 不再保存重复副本；业务端和 Agent 端共同阅读、维护本目录，版本继续为 v0.2。Agent 专属部署与使用说明保留在 Agent 项目内。

Agent 契约对齐及历史入口探测见[接口文档第9.10节](接口文档.md#910-yh-agent契约对齐与实际入口探测)。Agent 使用业务算法的事件结论，事件查询返回全类型业务事件；该节历史探测结果不代表当前运行状态，部署与联合验收单独记录。


## 近期算法与设备接入设计交付（v0.2，2026-10-29）

**状态：设计已补齐；005数据库迁移已应用，四张设备表、三项关联字段和两类结果JSON定义已建立。新增接口、设备适配和授权扩展仍待实现。** 当前代码／文档根为`/data/nfs_storage/hxjm`，文件数据根仍为`/data/nfs_storage/hxjm_datas`。

| 阅读目的 | 文档与内容 |
|---|---|
| 建表、字段、约束、DDL和清理 | [数据库说明文档第12章](数据库说明文档.md)：四张设备表完整字典、三项增列、七用途约束、JSON、事务与兼容 |
| 请求响应与联调 | [接口文档第10章](接口文档.md)：状态、巡检、反馈、产物发现及媒体用途读取；每个接口给出字段、示例、权限和边界 |
| 场景、业务规则及验收 | [软件需求规格说明书](软件需求规格说明书.md)：第10章明确打架、跌倒、垃圾和机器狗近期范围 |
| 模块职责与数据流 | [系统架构说明书](系统架构说明书.md)：第14章说明适配器、任务、成果、事件、文件和查询的衔接 |

新增表为device_registry、device_state_observation、device_task_binding、device_task_feedback；新增关联为camera.device_id、result_set.device_task_binding_id和asset_reference.device_task_feedback_id。已有任务、执行、成果、事件、人员和文件体系继续复用，不按算法另建主表。原六选一用途约束必须替换为七选一，不能简单追加检查约束。

近期行为算法保存四类实际判断及可用证据，不保存骨骼；场景按摄像头；机器狗先调用设备已有路线或任务模板，不编辑路线。设备状态历史保存变化和周期采样（建议默认30秒可配置），实时展示维持原频率。控制写入需要服务身份及设备权限，共享查询不开放设备控制。

联调顺序为设备目录和视频→状态变化／采样→公共任务和执行→设备确认／反馈→文件及明确绑定的算法成果→统一查询。页面、后台和Agent可直接读取已有事实并通过授权入口发起任务，报告按需生成。接入方应逐项核对设备模板编号、协议字段和类型化载荷；业务含义调整先协商，并同步维护v0.2，不自行改变同名字段语义。

数据库迁移已通过临时隔离库21项约束／关系／事务验证后应用到当前业务库，原数据未改写或删除；结构备份和结果见[005应用报告](../deploy/database-reports/005-apply.json)，执行方式见[数据库迁移说明](../python/base/postgresql/stage3/README.md)。设备、接口及Agent联调尚未执行，不将建表、组件演示或设计示例计为业务接入完成。
