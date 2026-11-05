# JoyAI 四路异常监控工具

本次实现对应 `docs/开发协调会议准备.md` 中 tzh 的交付边界，复用 `behavior.assessment/1`、公共任务、成果、事件、资产和报告接口。代码在 `python/joyai_tool`，无需打开旧异常分析页面。

## 流程

1. 从本目录 MediaMTX 读取 1—4 号摄像头。复用项目视频输入解码组件，为本工具的每次接入建立真实输入会话，并通过公共接口登记；不冒用 BoT-SORT 的帧号或会话。
2. 只加载一份官方 INT4 JoyAI 权重，保留与原版相同的约 87.67 亿参数规模。四路分别保持自己的流式上下文，以轮询队列依次推理；四路采集和证据缓存持续进行。轮询频率受实际推理速度影响，不承诺逐帧异常检测。
3. 只筛查打架、跌倒。触发后保存约 10 秒片段，默认前 5 秒、后 5 秒，以 4fps、最长边 960 像素保存原始画面。截图与输入不包含检测框。采集断帧超过 1 秒或片段不足时标记证据不完整。
4. 平时 Qwen 不加载、不占本工具的 GPU 显存；只有封好的可疑片段等待复核时才自动启动一份 Qwen。处理完当前可复核队列后立即停止 Qwen 并释放显存。加载期间继续观察、采集四路视频；失败保留片段等待重试，不能当作已确认。JoyAI 的初筛判断、必要的 JoyAI 片段判断与 Qwen3.8-27B 的视觉复核分别保存。初筛为委托/证据不足时，需再取得 JoyAI 的明确片段判断。复核使用按时间排序的 8 张采样帧，要求输出中文观察、正常活动解释、限制和结论。最终展示必须满足两个模型都确认同一类异常，不能把复核超时或不一致当作确认。
5. 视频、截图可靠写入公共资产目录后，按公共 API 完成资产、成果、事件和报告登记。排除和证据不足也保留事实，但不进入“已确认异常”卡片。按抽样视频复核登记 `partial` 覆盖及 `SAMPLED_VIDEO_REVIEW`，不宣称逐帧完成。SQLite 仅保存投递状态和请求，业务历史仍从公共数据库查询。
6. 大屏“实时告警显示”每 5 秒分别读取当前候选状态和公共报告。JoyAI 检出后立即展示黄色“疑似异常”事件卡片，分别显示采集视频、等待复核、加载复核模型、正在复核和保存结果的进度；视频资产登记完成后即可点击回放。只有双模型确认同类异常并完成公共登记后才显示红色“已确认异常”；复核排除显示灰色“已排除”，证据不足或模型不一致显示黄色“复核未确认”。复核完成时同一事件替换原卡片，不重复展示；当前候选全部保留，旁边展示最近五条复核结果。历史结果仍从公共报告读取。卡片包括截图（登记后）、摄像头和时间；点击取得资产播放凭证，播放片段并展示中文分析报告、时序观察及判断限制。

## 文件与服务

- 权重、Python 环境、上游 JoyAI 适配器、缓存、私有配置：本目录 `.run/joyai/`，不提交 Git，不引用旧目录的 JoyAI 权重或环境。
- 证据：`/data/nfs_storage/hxjm_datas/algorithm-output/joyai/<instance_id>/`，通过 `asset_id` 读取；沿用公共资产七天有效期。
- 地点按用户选择显示“1号摄像头”到“4号摄像头”。以后可在私有 `config.json` 的 `cameras` 中修改 `location`，重启工具生效。
- 大屏统一显示“异常预警模型”，工具接口和模型内部标识仍为 JoyAI。
- 服务端口在 `local-ports.env`：JoyAI 模型 `34201`、流式适配 `34202`、Qwen 复核 `34203`、工具 `34204`，都监听本机回环地址。
- 新后端只给 `joyai-producer` 授予四个公共来源的明确操作权限。令牌保存在 `.run/joyai/config.json` 和 `backend.yml`，不要提交或复制到网页。

## 启动与关闭

先启动本目录系统，再显式启动算法；普通系统启动不会自动加载异常模型；算法启动只加载 JoyAI，Qwen 按需加载：

```bash
cd /data/nfs_storage/hxjm-tzh
export VIDEO_RESULTS_SERVICE_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
bash scripts/start-local.sh

# 首次接入时生成四路来源映射和本目录后端授权；完成后需重启本目录系统。
# 本次已准备好，不必重复执行。
bash scripts/joyai-tool.sh prepare

# 检查 INT4 权重、端口和配置，再启动一份 JoyAI 和四路观察。
# Qwen 在有可疑片段时自动启动，无需手动启动。
bash scripts/joyai-tool.sh check
bash scripts/joyai-tool.sh start
bash scripts/joyai-tool.sh status
```

`prepare` 不会覆盖已有私有配置。初次生成后，重新运行 `start-local.sh` 让后端加载授权，再执行算法 `start`。完整系统重启会先停止本目录现有算法，重启后需重新执行算法 `start`。

```bash
# 只停本目录新增 JoyAI/Qwen/工具，保留网页、媒体和数据库
bash scripts/joyai-tool.sh stop

# 关闭本目录系统及其算法，保留共享数据库和其他项目
bash scripts/stop-local.sh
```

NFS 冷启动读取模型可能较慢，以 JoyAI `/health` 就绪及工具四路状态为准。`joyai_qwen: stopped` 在没有片段时是正常状态。算法状态的 `reviewer.mode=on_demand`，`state` 为 `stopped/starting/ready/reviewing/releasing/error`；大屏对应显示“按需待命／正在加载／已就绪／正在复核／正在释放资源／等待重试”。

当前 JoyAI 使用官方 INT4 权重，保留原模型参数规模，未裁剪层或替换成更小模型；上下文仍为 4096 token、单次并发 1，默认显存预算由 0.82 降到 0.40。BF16 原权重保留在磁盘供回退，运行时不加载。Qwen 沿用主项目 `Qwen3.8-27B-AWQ-INT4` 权重；这是项目中的目录/服务名称，实际配置为 `Qwen3_5ForConditionalGeneration`，含视觉模块。

Qwen 加载超时默认为 1200 秒，可在私有 `config.json` 调整 `review_start_timeout`。冷启动可能数分钟，加上排队与推理，报告不保证即时生成。只停止、清理本目录登记的 Qwen 进程及其子进程；其他项目占用端口时拒绝抢占。加载失败、用户停止或队列暂时无可执行复核时，都清理已启动的 Qwen。连续到达且可执行的片段复用一份 Qwen；等待重试的片段不会让模型无限驻留。

### 模型版本与显存实测

当前模型为官方 `jdopensource/JoyAI-VL-Interaction-INT4`，版本固定为 `1bfadbd2b41c11864cd7c359c7ea961aa6fd835c`。参数规模仍为 **8,767,123,696（约 87.67 亿）**；主要线性层权重采用 INT4，视觉模块等部分保留 BF16。权重文件约 7.03 GiB，均已复制到本目录 `.run/joyai/models/JoyAI-VL-Interaction-INT4/`，运行不引用旧目录。

以下是**切换前 BF16 + Qwen 常驻**的对照数据；不能当作当前 INT4 与按需复核的占用。

2026-11-04 15:08（北京时间）运行中快照，两张卡均为 RTX 4090 D，每张 24564 MiB：

| GPU | 本工具模型进程占用 | 整张卡已用 | 整张卡空闲 |
|---|---|---|---|
| 0 | JoyAI：20210 MiB，约 19.74 GiB | 23547 MiB，约 23.00 GiB | 528 MiB |
| 1 | Qwen 复核：22490 MiB，约 21.96 GiB | 23111 MiB，约 22.57 GiB | 973 MiB |

切换 INT4 后，JoyAI 模型进程实测 **10084 MiB，约 9.85 GiB**，相较原 20210 MiB 下降约 **50%**。vLLM 日志记录权重加载约 7.36 GiB、KV 缓存约 1.80 GiB；进程总量还包含推理工作区等。四路共享一份模型，单次并发与上下文长度未缩减。INT4 改变权重精度，可能影响个别场景判断，需要另外用实际打架、跌倒样本评估。

模型进程数值包含权重、KV 缓存与推理工作区；整卡数值还包含其他已有进程及驱动开销。JoyAI 的 vLLM 会预分配显存，因此观察期间即使暂时没有推理也保留这些显存。Qwen 通过退出进程释放其占用，而非仅清空聊天记录。实时值会变化，可执行：

```bash
nvidia-smi
# 持续每秒刷新
watch -n 1 nvidia-smi
# 按进程查看，单位 MiB
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory --format=csv
```

本目录 INT4 权重和环境已准备好。以后在全新目录安装时，先在 `local-ports.env` 明确配置下列四个端口，再执行 `setup` 准备 JoyAI；脚本固定上游源码版本与官方模型版本。Qwen 权重当前从主项目复制而来，`setup` 不会自动下载它：

```ini
JOYAI_MODEL_PORT=34201
JOYAI_OBSERVER_PORT=34202
JOYAI_REVIEW_PORT=34203
JOYAI_TOOL_PORT=34204
```

```bash
bash scripts/joyai-tool.sh setup
mkdir -p .run/joyai/models
cp -a /data/nfs_storage/hxjm/Agent/models/Qwen3.8-27B-AWQ-INT4 .run/joyai/models/
bash scripts/joyai-tool.sh prepare
# 重启本目录系统加载 backend.yml，再启动算法。
```

## 工具接口

工具目录与健康不触发推理：`GET /tools`、`GET /health`、`GET /status`。工具启动前尚未建立来源会话，不能把端口就绪当作四路已分析。

- `POST /monitoring/start`：请求体 `{}` 表示四路；也可传 `{"camera_ids":["camera_1"]}`。
- `POST /monitoring/stop`：停止采集和观察，不删除已有业务事件、报告、证据。
- 写操作必须带私有 `X-JoyAI-Token`；公共服务写入另带 `X-HXJM-Service-Id` 与 `X-HXJM-Service-Token`。
- 公共能力代码 `joyai_video_anomaly`；输入 `live_video`，输出 `behavior.assessment/1`，报告类型 `joyai_anomaly_review`。公共登记请求使用稳定请求 ID，网络失败重试沿用相同请求及成果 ID。
- `POST /reviews/restart`：请求体 `{"report_id":"已完成报告 UUID"}`，需要 `X-JoyAI-Token`。实时告警卡片的“重新启动大模型复核”按钮通过本目录服务端代理执行，服务令牌不交给浏览器；只接受本工具已有、未过期且原视频仍可读取的报告。同一事件已有重新复核任务时返回当前任务，不重复入队。复核中的按钮禁用，失败后显示错误并允许再次提交。
- 重新复核从已保存的原视频按时间重新采样八帧，只重新运行 Qwen，保留原 JoyAI 判断及原报告。每次使用 `joyai_clip_rereview` 录像能力建立独立的 `once` 任务和 `run_id`，登记新成果并按修订更新同一 `event_id` 的结论；历史报告保持原样，新报告类型为 `joyai_anomaly_review:<复核任务本地 UUID>`，记录 `candidate_id`、`previous_report_id`。前端按同一事件合并，显示最新复核结果。Qwen 不在内存时自动加载，空闲后释放；加载和推理期间卡片显示黄色复核进度，只有满足原 JoyAI 与新 Qwen 同类确认条件才标红。
- 右侧“大模型监控报告”暂不展示 VAD、JoyAI 等异常检测报告，保留人员报告等其他内容；异常片段的进度、回放和复核报告统一在实时告警卡片中查看。
- 本分支补齐公共 `POST /api/v1/business/tasks/cancel`，遵守手册 `tasks.cancel` 的授权、修订号和幂等规则。停止时取消空闲任务并结束本工具输入会话；尚有片段待复核的任务保留，供下次启动续传。进程强制退出或网络中断留下的空闲任务，会在恢复运行后收尾，不删除已登记的证据和报告。

状态包括各摄像头的最近输入时间、最近推理时间、完成观察次数、队列长度、失败原因和未完成候选。`pending_events` 仅返回当前未完成事件的摄像头、时间、类型、进度、已登记资产标识等展示元数据，不返回采样帧、存储路径或内部投递请求。`observing` 只说明最近成功执行过观察，不代表每一帧都已处理。Qwen 未就绪时保留等待复核，不能发布已确认告警。

## 检查

```bash
PYTHONPATH=python python3 -B -m unittest joyai_tool.test_tool -v
python3 -B scripts/test_local_runtime.py -q
cd lanhu && npm test && npm run build
```

日志在 `log/local/joyai_model.log`、`joyai_observer.log`、`joyai_qwen.log`、`joyai_tool.log`。

### 2026-11-04 INT4 与按需复核验收

- 一份 INT4 JoyAI 持续观察四路摄像头，Qwen 加载、推理和退出期间观察次数继续增长。浏览器四路视频均正常播放，显示“异常预警模型”和复核模型的加载状态，无页面脚本错误。
- 人工选取并明确标注“联调验收、非自动检出”的现场正常 10 秒片段，经实际投递队列触发 Qwen 自动启动。JoyAI 未确认异常，Qwen 输出中文时序报告并明确排除打架；视频、截图、判断、事件、报告均完成公共登记，没有进入确认告警。报告 ID：`855c1ab6-c9e9-4da5-af02-937d9aef09b4`。
- 本次 Qwen 从触发启动到可用约 8 分钟，16:20:45 就绪，16:21:17 前完成推理，16:21:19 由工具自动停止，未通过人工停止代替验收。随后状态为 `reviewer.state=stopped`、`pending_reviews=0`，其 API 与推理进程均退出。
- 停止后 JoyAI 为 **10084 MiB（9.85 GiB）**，Qwen 为 **0 MiB（本工具无驻留进程）**。GPU 1 整卡仍使用约 615 MiB，其中其他已有进程使用 592 MiB；这是其他服务和驱动占用，不是 Qwen 残留。
- 新增工具检查 13 项、运行管理检查 32 项、告警前端检查 2 项及前端生产构建通过。另验证仅采集中的片段、等待重试的片段不会让 Qwen 常驻；启动失败、超时、加载中停止及释放失败重试均有检查。

复核请求增加 JSON 输出约束，修复 INT4 偶尔返回不完整报告而无法进入后续复核的问题；仍保留严格判定校验，无效响应不会确认异常。验收结果与显存记录在本目录被 Git 忽略的 `.run/joyai/ondemand-test-result.json`、`memory-migration.json`，浏览器截图在同目录 `live-page.png`、`idle-page.png`、`alarm-ui-test.png`。

2026-11-03—04 切换前 BF16 与常驻复核的验收记录：

- 两个真实模型健康接口成功；一份 JoyAI 对四路分别完成数百次流式观察。重启工具后四路恢复 `observing`，无遗留运行错误。
- 浏览器四路视频均为 1920×1080，播放时间持续增长，无页面脚本异常；大屏显示 `4/4 路正在观察`。
- 人工选取现场正常办公的真实 10 秒视频进行联调：JoyAI 未确认、Qwen 明确排除打架。视频/截图、两份模型判断、事件、报告均经真实公共接口登记，报告保留“联调验收、非自动检出”说明；没有进入确认告警卡片。浏览器通过公共播放凭证播放该视频，时长 10 秒，并成功读取截图。
- 单独用标注“界面验收模拟数据”的响应验证确认卡片、点击播放及中文分析报告展示，未把模拟确认结果写入公共数据库。截图在 `.run/joyai/alarm-ui-test.png`。
- 已实测停止旧输入任务、拒绝过期修订号、重复收尾幂等，以及取消后证据和报告仍可读取。新增 Python 工具检查 6 项、启动管理 32 项及前端检查通过，Java 8 干净构建和前端生产构建通过。

尚未使用真实打架/跌倒样本评估检出率和漏报率，不能把上述联调当作准确率验收。切换前正常片段的复核实测 JoyAI 约 9 秒、Qwen 约 29 秒；按需方式还需加上 Qwen 冷启动、触发后采集及排队时间，告警存在延迟，不是逐帧即时判定。
