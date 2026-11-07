# BoT-SORT 轨迹持久化交接

代码在个人目录开发，正式生产端应随代码合并到算法所属目录后启用。默认关闭持久化。
普通个人项目仍只订阅共享算法，不启动第二套模型或正式入库任务。浏览器连接数不影响入库。

本功能没有启动时自动执行的数据库迁移，没有自动创建来源、算法能力或实例，没有硬编码生产UUID。
新增的生产端文件队列只保存结果和标识，不保存视频帧、JPEG或模型向量。
新生产端使用独立的`tracking_client.py`和`tracking_spool.py`，不替换已有业务模块的客户端、队列接口。

## 数据路径

`BoT-SORT → analyzer._analyze → ResultPublisher → ResultSpool → Java /api/v1/business/results/register → PostgreSQL`。

入队发生在JPEG编码结果等待、展示TTL检查、会话展示过滤和WebSocket合并之前。
模型IPC返回完整检测列表；实时展示仍最多500个目标，持久化不使用这个展示截断。
没有浏览器订阅也会按原有调度分析和入库。现有取最新帧和跳帧策略不变，只保存实际产出的帧。

## 部署前核验

1. 在目标数据库核对现有迁移，确认stage1及业务服务依赖的后续结构。不要重复运行建表脚本。
   `python/base/postgresql/stage1/check_tracking_persistence.sql`是只读预检，检查关键列和轨迹唯一索引；
   它不证明来源、实例、权限、数据库容量和NFS回放已经就绪。本次开发未执行该SQL。
2. 后端启用`hxjm.business.enabled=true`，`slaveDataSource`连接目标PostgreSQL。
3. 每个摄像头已有`camera`和启用的`camera_stream`。映射使用真实UUID，不把`camera_1`或MySQL整数ID当UUID。
4. 登记/确认跟踪能力、`detection.frame`版本`1`及启用的`capability_instance`。
   能力应支持`live_video`和`continuous`，契约允许实际提交的参数，输出包含`detection.frame`。
   实例的实现标识、实现版本必须与实际部署代码及生产端配置一致。后端单项载荷限制需容纳实际目标数。
5. 在后端的受控配置中设置服务身份及来源范围，例如：

```yaml
hxjm:
  business:
    enabled: true
    security:
      services:
        botsort-producer:
          token: ${VIDEO_RESULTS_SERVICE_TOKEN}
          operations:
            - instances.query
            - streams.open
            - streams.close
            - tasks.submit
            - tasks.start
            - tasks.finish
            - results.register
            - tracking.close
            # 开启 VIDEO_SAMPLES_ENABLED 时还需要样本与查询处理权限。
            - assets.upload
            - media.resolve
            - samples.register
            - samples.process
            - feature_spaces.register
            - features.register
            - identities.associate
            - queries.process
            - queries.get
            - queries.candidates
            - search.execute
          source-ids:
            - 实际来源UUID
```

令牌由后端与算法服务各自安全加载，不将其提交Git。不要把示例占位值当作真实配置。

## 生产端配置

在算法所属目录复制`deploy/botsort/video-results.env.example`为被Git忽略的`local-results.env`，
复制`video-results-sources.example.json`为`local-results-sources.json`，填入每一路真实的来源、
流目录、实例UUID。实际默认分析四路，四路均须映射。时区默认为`Asia/Shanghai`。

填写实际服务令牌和实现版本，最后将`VIDEO_RESULTS_PERSIST_ENABLED`设为`true`。
共享启动器自动填本项目Java后端的业务API地址；直接运行或做配置检查时需要明确提供完整地址。
若参数契约要求阈值等参数，通过`VIDEO_RESULTS_PARAMETERS_JSON`保存与实际运行一致的非敏感参数。

队列目录使用服务账号可写的持久本地磁盘，位于Git之外。默认示例使用账号的XDG状态目录。
不要使用/tmp，不要与其他实例共用，也不要在NFS上使用SQLite WAL。
本实现使用本地文件锁、fsync和原子替换，支持的部署目标是持久本地文件系统；NFS不作为已验证目标。
同一队列同时只有一个所有者。

默认批次最多10帧、约512KiB，等待上限0.5秒；单帧不可拆，超出批字节阈值时仍作为单帧提交，
由后端成果类型载荷上限校验。队列默认512MiB，保留控制事件与确认记录空间。
来源和执行版本快照随队列保留，修改当前配置不会把旧成果重新绑定到新实例。

`scripts/local-common.sh`只在算法所属目录加载`local-results.env`。个人项目强制关闭正式持久化。
共享管理器保留生产端配置以启动算法进程；MediaMTX不会继承`VIDEO_RESULTS_*`凭据，
算法进程通过服务身份访问后端。

## 轨迹样本与双特征空间

在可靠持久化之上可显式开启样本管线：`VIDEO_SAMPLES_ENABLED=true`，并提供
特征服务地址`VIDEO_SAMPLES_FEATURE_URL`、特征能力实例
`VIDEO_SAMPLES_INSTANCE_ID`及可选阈值/队列/轮询参数，见
`deploy/botsort/video-results.env.example`。样本管线沿用轨迹生产端的服务身份，
该身份还需具备上面列出的样本、图片、特征和查询操作权限，否则首次登记即被拒绝。
样本管线随`video_analysis.app`
的lifespan启动和停止，`/health`的`sample_pipeline`字段报告队列和两个特征空间的状态。
它只消费后端已确认的帧：`/results/register`确认后才复制该帧的整身裁剪图，
不经过展示JPEG或展示TTL过滤。

默认同时写两个互不比较的特征空间：

- CLIP-ReID图片空间（3072维）：写入`feature`并按阈值产生身份关联，与原有图片
  ReID检索一致。
- Chinese-CLIP文本空间（512维）：写入同一批历史裁剪图，保留`tracklet_id`但不写
  身份关联，供“全部历史图像”文本检索。登记照片也会在该空间编码并关联
  `identity_id`。

两个空间各自登记、各自建任务/run，特征按`(run_id, producer_feature_key)`去重，
互不覆盖。文本空间只支持整身裁剪图，不传bbox。设置
`VIDEO_SAMPLES_TEXT_ENABLED=false`可回到只写CLIP-ReID图片空间。

样本轮询同时覆盖`purpose=enrollment`（图片空间和文本空间各一次）和
`purpose=history`（文本空间，用于补齐此前未编码的历史裁剪图）；同一空间已有ready
特征的样本不会重复编码。因此不再需要单独运行
`python -m video_analysis.enrollment_text_worker`，该worker仍可作为纯文本空间的
独立后端使用。文本编码与图片编码在同一后台线程执行；特征服务不可用时样本按可重试
错误退避，不影响跟踪与轨迹入库。

## 标识与时间

算法解码连接作为明确的输入接入实例登记，`session_key`以`analysis:`开头。
它不是另一套独立录像解码连接的同帧证明。

- 组件`camera_id`经配置映射`source_id`。
- 一次连续算法输入对应公共`stream_session_id`；连接代次、时钟回退或PTS回退建立新会话。
- 组件跟踪会话、尺寸变化和模型重启建立新`tracking_context_id`。
- 每个跟踪上下文使用独立continuous业务任务及run，输入仍连续时复用公共输入会话。
- 首次生成的UUIDv4、帧生产键、请求和上下文持久保存；重传不重新生成。
- `frame_seq`沿用该输入接入实例的真实解码序号，跳帧不重新编号。
- 当前帧时间属于接入估时，登记为`ingest_estimated`，不宣称摄像头采集时钟精度。
- 组件`media_pts_ms`按已知流内定位映射为公共`stream_pts_ms`，四舍五入为毫秒整数。
  公共`media_asset_id/media_pts_ms`在没有可靠录像定位时均为null。

当前实现不新增录像精确对帧管线。录像若来自独立连接，需另行建立可核验的帧/资产定位，
不能直接把算法流内PTS写成录像文件偏移。后端现有资产登记和帧定位接口继续保留。

## 轨迹语义和结束

`(tracking_context_id,local_track_id)`映射唯一`tracklet.id`；局部编号不是人员身份。
全部逐帧框保存到`detection_observation`；轨迹摘要不代替逐帧观测。
预测保存为`predicted`，不推进真实出现时间、轨迹真实起点或身份活跃，也不顺延轨迹摘要期限。
首次收到没有先前真实观测的预测时，保留该帧预测观测但不伪造轨迹出现，`tracklet_id`可空。

只有跟踪器明确最终移除的编号才发送normal结束事件。目标没有出现在展示结果里不等于移除。
输入故障、模型重置、背压暂停和服务停止通过observation_interrupted收束。
先确认旧帧，再按同摄像头队列顺序关闭轨迹/上下文/任务，最后关闭输入会话。
结束的tracklet.end_ts使用最后真实观测时间，不使用停止服务的当前时间。
崩溃恢复先补交旧队列，按持久的最后帧收束旧上下文，再处理新输入；不会恢复内存中的旧tracker。

新增接口`POST /api/v1/business/tracking/close`只允许拥有对应任务和来源权限的服务身份调用。
操作权限为`tracking.close`，请求字段为：

| 字段 | 含义 |
|---|---|
| request_id | 稳定幂等键 |
| source_id、task_id、run_id、tracking_context_id | 原生产执行及其上下文 |
| close_context | true关闭上下文；false只结束给出的局部号 |
| local_track_ids | 结束的局部号；关闭上下文时可为空 |
| ended_at | 排在已保存帧之后的排他边界 |
| end_reason | normal / observation_interrupted / cancelled |
| reason_code | tracker_removed、analysis_failed等原因 |
| gap_start_at、gap_end_at | 可选的明确分析缺口，必须成对提供 |

关闭请求、轨迹修改、任务终态、分析缺口和outbox在同一PG事务内处理。
重复请求返回原确认；已关闭上下文不接收新的帧成果，但已有相同成果仍可重复确认。

## 可靠提交、容量和到期

每个摄像头一个有序发送通道；一个摄像头的权限/协议错误不会阻止其他通道提交。
同批仅包含同上下文的完整帧，提交前冻结完整请求并持久化。
服务端已经提交但响应丢失时原样重传；部分确认后只补交可重试的未确认成果，
使用新request_id，但保留原成果ID、生产键和完整窗口清单。
HTTP 200、旧AjaxResult、页面登录响应均不能当作可靠登记确认。

不可重试的拒绝会暂停该通道并保留原数据。修正权限/协议配置后重启生产端重试，不要删除队列或换ID绕过冲突。
若原载荷存在永久内容冲突，原确认可能已被幂等缓存；须人工核对缺口和补算，不能只靠重启消除冲突。
队列高水位暂停新的推理调度；录像/播放独立继续，恢复时重建跟踪上下文并保存分析缺口。
持久写入失败会暂停后续推理，健康状态明确报错。模型结果产出到持久写入前仍有不可消除的崩溃窗口，
不能承诺无限磁盘或任意故障下零丢失；恢复后根据有效录像补算或保留缺口。

逐帧成果按原发生时间七天到期，重试不续期。已到期的待提交成果本地回收并保留轻量到期摘要，
摘要计数是回收尝试次数（崩溃重放可能重复），不代替服务端审计。
冻结批次若跨越到期边界，保留原请求，全部待确认帧到期后再整体回收。
不换时间戳重新登记。若后端已将输入会话或任务判为到期，不会强行复活原执行；需要核对缺口并开始新的合法输入。
JSON状态文件内的当前活跃轨迹以实际移除事件清除，已完成上下文/输入在确认后回收。
进程停止时不承诺清空队列；下次启动继续处理。

`/health`新增`persistence`，包含队列数量/字节、最老等待时间、阻塞通道及错误码。
`process_*`计数属于本次生产端进程；确认数可以包含重启前积压，不与当前进程产出数直接比较。
过期临时文件数会单独显示；它们不作为可靠入队确认，需要离线核对。
持久化模块日志只输出错误代码，不输出令牌、请求正文或摄像头凭据。

## 离线检查

以下命令只解析代码、验证临时文件和假HTTP响应，不启动项目、数据库、模型或摄像头：

```bash
PYTHONPATH=python python3 -B -m video_analysis.persistence_check
PYTHONPATH=python python3 -B -m unittest discover -s python/video_analysis/tests -p 'test_persistence.py' -v
PYTHONPATH=python python3 -B -m unittest discover -s python/video_analysis/tests -p 'test_analyzer_persistence_offline.py' -v
bash -n scripts/local-common.sh deploy/botsort/video-results.env.example
JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 mvn -o -f SmartMonitor-wangzj/pom.xml -pl hxjm-algdeployment -am -DskipTests test-compile
```

要检查填写后的配置，在独立shell加载local-results.env、明确设置业务API URL并临时开启持久化，
运行`PYTHONPATH=python python3 -B -m video_analysis.persistence_check --config`。
此命令不创建队列、不访问后端、不执行SQL。`--journal /绝对队列路径`只读校验已有JSON格式，
不领取队列所有权，也不发送或回收文件。

## 合并后的人工验收和回退

开发提交合并到主目录实际目标分支后，由维护者核验迁移、权限、来源及版本，配置正式生产端。
先用单摄像头确认轨迹/帧数量、重复确认、真实观测时间、结束事件和历史查询，再扩展四路。
需要执行真实PostgreSQL事务、GPU推理和录像定位验收；离线测试不证明这些运行结果。
本次开发不启动任何上述服务，也不执行迁移、预检SQL或故障注入。

现有测试基线有一项已知不一致：`test_business_config.py`导入`config.load_business_config`，
而当前仓库版本未提供该函数，因而无法收集该测试。与本次功能无关，未补建另一套配置流程。
依赖真实运行环境的历史测试不属于此次离线通过范围。

本次离线校验：29项持久化测试、6项分析器边界测试及39项原客户端/队列/运行时测试全部通过，
共74项；Python 3.9语法、Shell语法及JDK 8 Maven离线编译通过。

回退时关闭`VIDEO_RESULTS_PERSIST_ENABLED`，保留持久队列与已保存数据库事实；
不自动删除新增字段，不清空已提交历史。修复后使用原队列恢复。
