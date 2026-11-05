# 当前数据库规范

## 权威入口与归属

正式结构只维护在 `modules/infrastructure/database/migrations/`，由 `bootstrap/bootstrap.py` 执行。逻辑维护归属记录在同目录 `table-ownership.json`；Infrastructure 管理执行工具，不因此拥有全部业务数据。清单中的 code_references 是源码定位线索，包含读与写，不能直接当作写入权限。

当前基线 `0001_current`：MySQL 29 张业务/平台表，加 1 张版本表；PostgreSQL 48 张业务/能力表，加 1 张版本表。没有为了减少表数合并不同生命周期的对象。


### mysql

| 数据域 | 维护模块 | 表 |
| --- | --- | --- |
| 设备与视频来源 | Business | `alg_bk_machine_fr`, `alg_bk_management`, `ba_algmodel`, `ba_algtype`, `ba_machine` |
| 人员、身份、轨迹与搜索 | Business | `face_database`, `face_person`, `face_recognition_events`, `face_recognition_events_v1`, `face_stranger` |
| 平台配置、权限、日志、调度、生成器 | Infrastructure | `gen_table`, `gen_table_column`, `sys_config`, `sys_dept`, `sys_dict_data`, `sys_dict_type`, `sys_job`, `sys_job_log`, `sys_logininfor`, `sys_menu`, `sys_notice`, `sys_oper_log`, `sys_post`, `sys_role`, `sys_role_dept`, `sys_role_menu`, `sys_user`, `sys_user_post`, `sys_user_role` |
| 结构版本 | Infrastructure | `hxjm_schema_history` |

### postgres

| 数据域 | 维护模块 | 表 |
| --- | --- | --- |
| 视频分析与算法结果 | Business | `algorithm_result`, `analysis_frame`, `detection_observation`, `input_frame`, `processing_coverage`, `result_selection`, `result_set`, `tracking_context` |
| 事件、活动、证据与媒体 | Business | `asset_reference`, `business_event`, `episode`, `episode_media_link`, `episode_tracklet_link`, `event_object_link`, `evidence_reference`, `media_asset`, `vad` |
| 能力、任务与执行成果 | Capability | `business_task`, `capability_definition`, `capability_instance`, `result_type`, `task_attempt`, `task_output` |
| 设备与视频来源 | Business | `camera`, `camera_stream`, `device_registry`, `device_state_observation`, `device_task_binding`, `device_task_feedback`, `stream_session` |
| 人员、身份、轨迹与搜索 | Business | `feature`, `feature_contribution`, `feature_space`, `identity`, `identity_link`, `query_candidate`, `query_request`, `reid_match`, `reid_target`, `sample`, `search_hit`, `stranger_target`, `track_identity_assignment`, `tracklet` |
| 报告与业务应用 | Business | `llm_report`, `report_evidence_link` |
| 幂等与事件投递 | Business | `outbox_event`, `request_deduplication` |
| 结构版本 | Infrastructure | `hxjm_schema_history` |

## 核心语义与访问边界

- `ba_machine` 是设备管理的整数编号目录；`camera` 是分析来源的 UUID 目录，一个设备可有多个通道。新种子通过 camera.management_device_id/channel_code 显式绑定设备和 raw 通道，camera_stream 描述实际媒体流；不能互换整数设备 ID、camera_code、source UUID。两库不引入分布式外键，跨库绑定由 Business 维护。视频源的流配置与设备目录字段不自动双向同步。
- `identity` 是新身份关联事实；`tracklet` 是跟踪上下文中的轨迹，不是人员。sample、feature、feature_space 区分样本、特征与模型空间；feature_contribution 保留聚合依据。
- reid_target 是仍被图库 API、ScreenMapper 和报告读取的注册图库；stranger_target/reid_match 仍被现有人员页面/报告链路使用，不能因有 identity 就直接删除。face_database 是现有人脸模板 API，face_person/face_stranger 与 face_recognition_events_v1 服务另一条现有人脸事件链路，旧 face_recognition_events 查询/写入 API 也仍在使用。此阶段不把模型特定图库、人脸模板和身份事实强行等同，也没有完成各历史人脸 API 向新身份 API 的业务迁移。
- `result_set` 是持续生产的一组结果；analysis_frame/detection_observation 保存结构化帧与目标，algorithm_result 保存其他算法成果。`task_output` 是请求驱动任务的通用成果，保留独立存储。成果引用同一任务/来源/Schema 语义，不把逐帧结果塞入 task_output。
- `business_task` 是逻辑任务，`task_attempt` 是一次执行尝试；current_run、代次、lease 与 fencing 字段不可合并。task_output 用 (task_id,run_id) 复合外键保证成果属于该任务的执行尝试。
- `business_event` 管理事件事实，episode 管理持续活动，vad 是仍被页面和报告使用的行为输入；evidence_reference、asset_reference、report_evidence_link 表达不同引用关系与保留期限。llm_report 的不同来源关联不能仅按相似名称删除。
- request_deduplication 管理 API 幂等结果；outbox_event 管理待投递事实，二者不合并。二者由现有 BusinessStore 统一写入，不是其他模块任意写业务表的入口。
- 四张 device_* 表保留已确定的设备目录、状态、任务绑定与反馈语义，供已有设备公共协议后续衔接；当前没有新建真实设备或设备执行服务。
- 垃圾检测使用既有 garbage.detection 成果类型、business_event 与业务任务链路；本阶段不虚构垃圾清理专表或机器人控制数据库。

Agent、算法运行时不直接操作上述 Business 私有表；持续结果通过 Business API 登记。人脸 FaceDatabase 的 Controller/Service/Mapper/Domain 已由 hxjm-system 迁入 Business hxjm-algdeployment，公开 `/system/face_database` URL 保留。

仍有明确的同进程协作边界：Business 的持续结果登记会更新任务 last_input/保留期限/租约，TrackingLifecycleService 会关闭关联任务；Capability 的成果查询也保留原 V1 的业务投影 SQL。它们沿用原共享事务及状态校验，并非本阶段已全部改成跨服务 API。任务定义与执行语义归 Capability，业务成果归 Business；后续若继续拆分部署，需先处理这些协作写入，不能直接切断表访问。

## 移除内容及依据

| 移除结构 | 依据 |
| --- | --- |
| MySQL face_recognition_events_copy | 正式 Mapper、业务服务及主前端无引用的备份副本 |
| MySQL tbl_cameras、tbl_floors、tbl_testTexts、tbl_videos | 旧演示结构，正式 Java/Python/前端无引用；现用设备/来源与媒体资产另有权威模型 |
| PostgreSQL ai_task_run、task_attempt.legacy_run_id 及相关约束/索引 | 第二阶段已退役旧进程启动路线，正式源码不再引用 |
| PostgreSQL legacy_identity_map | 仅历史迁移/验证使用的导入映射；允许重建，无需历史映射 |
| PostgreSQL reid_target_vit | 正式图库使用 reid_target，未发现正式 ViT 表访问链路 |
| PostgreSQL unified_event | 原注释即说明“暂不接入”的草案表，无正式调用；保留正在使用的 business_event |
| 旧 schema-manifest.json、hxjm_deployment_version 机制 | 手工列名清单不能覆盖 Capability 后续字段；改用版本摘要与实际结构指纹，不再维护另一套列定义 |
| 零散 algtypeMenu.sql、algmodelMenu.sql | 指向旧管理 UI、依赖未初始化的 parent_id=2009，未被正式入口执行 |

历史 stage1..stage4 SQL/合成 fixture 仅在 references/database-snapshots/retired-initializers 供追溯，不作为执行入口。原硬编码连接的校验/应用程序、数据库配置示例及旧全量快照已退役。不要在新库上再执行这些旧 SQL。

## 初始化、升级与重建规则

唯一入口：`modules/infrastructure/database/bootstrap/bootstrap.py`，镜像内路径 `/opt/init/bootstrap.py`。Compose 只读挂载当前 bootstrap 与 migrations；独立镜像同时 COPY 两者。以下命令工作目录为仓库根目录。

```bash
# 无需连接、依赖安装或凭据，输出各数据库有序版本及摘要。
python3 modules/infrastructure/database/bootstrap/bootstrap.py plan
# 明确填写本副本配置；普通初始化拒绝任何已有表，不会自动清空。
bash scripts/start.sh --config /absolute/path/to/development.local.env --scope isolated --init-db
bash scripts/start.sh --config /absolute/path/to/development.local.env --scope isolated --check-db
bash scripts/start.sh --config /absolute/path/to/development.local.env --scope isolated --upgrade-db
```

配置通过环境提供 MYSQL/POSTGRES 的 HOST、PORT、DATABASE、USER、PASSWORD；数据库名必须明确提供。初始化管理员密码来自 INIT_ADMIN_PASSWORD，不在源码提供默认密码。摄像头从 CAMERAS_FILE 输入，登记设备、来源和 raw 流；不连接摄像头。平台只写管理员角色/关联、最小配置及 behavior.assessment、garbage.detection 成果 Schema，不复制历史业务行。跟踪/ReID 与 HTTP 业务能力仍通过现有受控 API 登记，`register` 不与建库混为一谈。

两库分别在 hxjm_schema_history 记录版本、SQL SHA256、实际结构指纹与应用时间。新库按相同有序迁移完整执行，upgrade 仅执行未应用版本；执行前先核验两库已应用历史及结构。check 同时核验文件摘要、结构漂移与待执行版本。行数据、序列当前位置和自增计数不参与结构指纹。

后续变更只新增 `migrations/0002_description/{mysql,postgres}.sql` 等有序目录；只影响一种数据库时只添加对应文件。已应用的 SQL 不原地改写；不写 psql 的 `\i`/`\if`、BEGIN/COMMIT 或额外版本表，事务与版本由入口管理。新增表同步维护 table-ownership.json，并更新直接相关业务代码/检查。旧无版本快照不自动收编；本轮允许丢弃数据，使用明确隔离库重建。

**重建是显式破坏性操作。** 先核对 Docker 项目标签、配置文件、挂载目录、运行环境和连接库名；不得仅凭 localhost 判定独立。仅对确认为本项目独立开发库的连接设置 HXJM_DATABASE_ENV=isolated-local，并向同一入口执行：

```text
bootstrap.py rebuild --confirm 'mysql@实际HOST:PORT/hxjm_实际开发库;postgres@实际HOST:PORT/hxjm_实际开发库'
```

确认串必须与两个实际配置目标完全一致；只允许明确 hxjm_* 库名及本地/Compose 内部端点，拒绝外部端点及 PostgreSQL 额外业务 Schema。程序先校验实际连接的数据库名，再重建指定 MySQL 数据库和指定 PostgreSQL 数据库内 public Schema，保留密码/连接配置；它不删除磁盘目录。环境标识是操作者的明确声明，不会自动证明该数据库没有其他使用者。

MySQL DDL 不能整体回滚，两库也不构成分布式事务；失败不会伪装为完整成功。部分初始化失败后须查明原因，再对确认隔离的库显式重建；不要手工伪造版本记录。PostgreSQL 每份迁移事务执行。暂不引入迁移框架、自动重试或后台数据库修改任务。


## 第四阶段增量

`0002_device_execution/postgres.sql` 增加 Capability 所有的 `task_attempt.external_execution` JSONB，保存外部执行反馈及模拟标识；增加按清理事件查任务的索引。不增加表，不修改0001或历史校验和。垃圾事件/证据仍由 Business 写入 business_event/evidence_reference，清理任务/执行/成果仍由 Capability 写入原业务任务模型。新环境 initialize 顺序应用0001、0002；既有经确认的开发库走同一个 bootstrap upgrade，不另写快照。


第五阶段发布整理：历史 SQL 快照仅保留在本地参考目录，不纳入新分支的文件树；正式初始化、升级和代码检查仍只使用上述 migrations。未清理或重写旧 Git 历史。
