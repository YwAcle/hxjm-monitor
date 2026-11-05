# 机器狗对接：当前真实协议与接手入口

本次仅实现 HXJM 侧流程，没有连接或控制真实硬件。模拟模式不是外部系统的替身协议，也不构成真实验收。

## 已确认的来源与复用

- `references/robot-control/src/m20_rebot_moving_grasp/remote_service.py` 是权威 `/control` WebSocket 服务；`tools/m20_remote_client.py` 和其 `m20_client/web/app.js` 展示客户端调用。正式 Java `M20RouteAdapter` 按这些实现提取命令、响应和状态解析，没有导入机器人 SDK。
- 服务通常监听 `ws://HOST:8765/control`。客户端发送 `{"action":"start","route":"route1","loops":1,"request_id":"HXJM_RUN_UUID"}`。路线仅支持 route1..route4，必须由机器狗侧预先完成标注。
- 命令返回 `{"type":"response","request_id":"...","ok":true,"state":"starting","route":"route1","loops":1}`；拒绝时 `ok:false` 并带 `error`。
- 建连立即推送一次历史状态，随后推送 `type:status`、`state`、`route`、`loops`、`pid`、`message`、`failure`、`logs`、`updated_at`。正式适配器忽略命令确认前的历史快照，确认后仅处理相应路线。
- 状态 idle/starting/running/stopping/succeeded/failed/stopped/unavailable 来自现有服务。HXJM 将启动/运行/停止中映射 running，succeeded 映射成功，failed/stopped 映射失败。其他不可归属状态、断线、超时或重启丢失会话均保留 unknown 原因。
- Demo 还支持 status、stop，但本阶段不提供前端控制/取消，也不向真实设备发送这些命令。

**该协议没有稳定外部任务 ID，也没有服务端 request_id 去重。** `external_task_id` 保持 null，`protocol_request_id` 保存 HXJM run UUID；pid 只作信息，不冒充任务 ID。通过同一次连接关联反馈；失联绝不重连重发 start。数据库中的未知执行记录还会阻止同一 endpoint 的后续真实派发，返回 DEVICE_RECONCILIATION_REQUIRED。解除前需人工核对机器狗并确认旧执行结论，不能靠重启后端规避。

## 定位和执行语义

当前 Demo 执行的是预标注路线巡检，机器狗侧自行检测、导航和抓取。没有监控 bbox → 地图坐标转换，也没有按单个监控目标精确拾取的已确认接口。

HXJM 只接受经现场确认的 **source UUID → route1..route4** 映射。前端仅提交 event_id/request_id，不能指定设备 URL、路线或控制命令。配置映射表示该来源应触发哪条路线，不表示图像坐标已转成导航坐标。没有映射就拒绝提交。

路线成功会回写关联任务与事件的 cleanup 投影，**不会自动关闭事件或声称该垃圾已经清除**。模拟同样不会关闭事件。后续如果外部系统提供目标级完成凭据，修改 Adapter 的目标转换/反馈及 Business 的完成判定即可；不要改 AgentExecutor 或视频算法。

## 内部接口与状态

- `GET /api/v1/business/garbage/events`：最近 100 条有效垃圾事件，附来源、检测内容、证据引用、关联任务、设备反馈、可用路线和 cleanup_enabled。
- `POST /api/v1/business/garbage/cleanup`：`{"request_id":"UUID","event_id":"UUID"}`。来源授权在 Business 校验；事务内按事件串行创建，重复点击返回原任务，失败/未知也不会自动生成第二条动作指令。
- 注册能力 `garbage.cleanup`，成果 `device.cleanup/1`；权威定义 `contracts/capability-v1/garbage-cleanup.json`。
- 复用 `business_task`、`task_attempt`、`task_output`，任务查询仍使用现有 `/tasks`。启动确认不代表完成；持续反馈由原 Capability 定时 tick 读取适配器状态，成功后才写标准成果。
- `task_attempt.external_execution` 保存 simulated、state、protocol_request_id、external_task_id、route 和真实返回信息。任务失败保留 error_code；没有设备状态时不编造成功。

## 配置、注册和切换

工作目录为仓库根目录。沿用已有个人部署配置文件和启动脚本，禁止直接使用别的部署目录。先按数据库规范在确认的开发库执行 `bash scripts/start.sh --config YOUR_PRIVATE_ENV --upgrade-db`，增加 `0002_device_execution` 的执行反馈列和事件任务索引，不清空数据库。

在私有配置中设置：

```dotenv
CLEANUP_MODE=simulation
CLEANUP_SOURCE_ROUTES={"已登记摄像头UUID":"route1"}
CAPABILITY_EXECUTOR_ENABLED=true
```

随后使用现有 `--render` 生成后端配置、重新装配并启动该开发后端，再使用 `--register`。register 通过原 Capability API 登记公共业务能力，配置图库地址时登记图库能力，开启清理时登记清理能力；simulation 显式登记 m20_mock。默认 CLEANUP_MODE=disabled；不存在自动模拟回退。事件查询不依赖此开关或机器狗在线。

真实联调前，由对接人员改为 `CLEANUP_MODE=m20`、`M20_CONTROL_URL=ws://真实服务:8765/control`，确认现场路线后重新 render。模拟和真实实例必须使用不同的 INSTANCE_NAMESPACE，或通过已有实例配置接口显式更新/停用旧实例；登记工具遇到既有定义不一致会拒绝覆盖。若部署同时保留多个实例，应明确指定/停用旧实例，不能让真实与模拟同时参与同一清理能力的选择。

此阶段没有执行真实模式命令。真实启用后一次清理提交会触发外部巡检，必须由对接人员在可控现场操作。

## 后续只需接手的位置

1. 连接地址与来源路线：私有部署配置、`CleanupProperties`；真实协议变更：`modules/perception-devices/java/hxjm-device-adapters/.../M20RouteAdapter.java` 的 command/submit/Exchange/poll。
2. 确认服务是否能新增稳定 task_id、按 task_id 查询和请求去重。取得这些接口后替换当前会话关联，不扫描硬件或推测协议。
3. 若要精确拾取，外部系统需确认目标图片/目标 ID/区域/地图位置中实际接受的格式，再在 Adapter 内完成真实转换。当前没有像素导航算法。
4. 若要自动确认事件已清除，外部需返回目标级执行证据，Business 再更新关闭规则。内部导航、底盘、机械臂与抓取仍由外部系统维护。

本地验证入口为 `GarbageFlowCheck`（隔离开发库，全部夹具回滚）和 `M20ProtocolCheck`（协议包回放，不开 socket）。模拟实现内置于 Adapter，仅显式 m20_mock 使用；无独立模拟平台或默认成功回退。

## 本次后续：设备操作沉淀

实际进一步阅读 `machine_dog/m20_protocol.py`、`m20_adapter.py`、`route_pickup.py`、`interface.py` 以及 `arm/arm_task_adapter.py`；核对 remote_service、m20_remote_client、m20_client/web/app.js 与视频桥接 Demo。分类如下：

| 类别 | 实现与用途 | 正式复用位置/限制 |
| --- | --- | --- |
| A 直接复用 | Grounding DINO 图片检测；AOS 报文构造、Message ID 关联、单次 UDP 请求 | 原垃圾 Detector 不改；AOS 协议提取到 `modules/perception-devices/python/device_adapters/m20_protocol.py`，保留导航报文的原格式 |
| B 适配复用 | `/control` WebSocket start/status/stop、异步状态推送 | Java `M20RouteAdapter`，现支持 `route.start`、`device.status`、`route.stop`；status 响应没有 ok 字段，按真实快照解析；stop 接受不等于停止完成，等待 stopped/idle 等反馈 |
| B 适配复用 | M20 UDP 定位、导航状态、感知状态、站立、趴下、单点导航、导航取消 | Python `device_adapters.m20.M20Operations` 提供七项明确操作，可注入传输和超时；未创建第二个设备服务或默认派发到硬件 |
| C 仅内部实现 | route_pickup 的路线巡检→D455 接近→D435 找位/IK→抓取→hold→去 bin→drop→返回断点；ArmTaskAdapter 的 prepare_grasp/grasp_current_target/hold/drop/safe_home/emergency_stop | 保留在 references；由外部路线流程组合，HXJM 不重写。当前没有独立对外的机械臂/抓取服务协议，不能宣称可以通过 `/control` 单独调用抓取 |
| C 仅内部实现 | D455/D435 深度坐标、机器人当前地图位姿、恢复点 | 不等于监控相机 bbox→地图目标转换，未迁入监控算法 |
| 参考 | robot-video-demo 的 H264/RTSP 与遥测桥接、旧 UI、接口抽象桩 | 视频格式/流程参考，不复制现有 MediaMTX 或平台组件 |
| D 缺失 | 从监控图片/目标 ID 提交精确拾取任务、稳定外部任务 ID、按 ID 恢复查询、目标级拾取结果证明 | 需要设备团队提供协议与标定，当前不伪造 |

Java 适配器实现 `DeviceAdapter`，`DeviceAdapters` 由 Spring 收集。CapabilityPlatform 仅按可信 adapter/device-operation 配置调用，不含 M20 类名、路线编号或垃圾事件更新。设备终态发布通用 TaskExecutionChanged，边界上的 GarbageTaskProjection 调用 Business 更新清理投影。新增同类设备主要增加 Adapter 和配置。

### 公共能力调用

`contracts/capability-v1/device-m20-{status,route,stop}.json` 是正式定义，复用 `/tasks` 与 `/tasks/outputs`；没有另一套调度器。启用 CLEANUP_MODE 后统一 `--register` 会额外登记三项能力：

- `device.m20.status`：payload `{source_ids:[已授权来源UUID]}`，可信操作 device.status，权限 devices.query，只读，可进入 Agent 动态工具目录。
- `device.m20.route`：payload 另需 `route:route1..route4`，可信操作 route.start，权限 devices.execute。
- `device.m20.stop`：同 status 输入，可信操作 route.stop，权限 devices.execute。停止的是该服务当前路线；外部协议不支持按 HXJM task_id 精确取消。

通过现有服务身份提交 task_mode=once、input.kind=capability_call、capability_code、登记后的 instance_id、requested_outputs=[device.operation]；`input.payload` 使用上述字段。设备引用由服务/实例固定，不接受用户传入设备 URL。三个操作均使用 task/run 引用和标准成果 device.operation/1；真实协议没有外部 task ID，仍返回 null。

可信配置为 `hxjm.business.execution.services.robot-dog.<operation>`：adapter=m20_route、url=明确 `/control` 地址、device-operation、required-operation、credential-ref。路线配置 exclusive=true，查询/停止为 false。核心执行器只处理此通用标志；有未确认动作时阻止新的独占派发，但允许查询/停止。实际终态、错误和 simulated 标识进入原 task_attempt/task_output。查询操作 succeeded 仅表示拿到了快照，设备可能仍为 unavailable/failed；必须查看 device_state。

`m20_mock` 是独立注册的适配器，只接受 mock://local，返回 simulated=true；不是网络失败兜底。默认 CLEANUP_MODE=disabled、CAPABILITY_EXECUTOR_ENABLED=false。页面仍以事件触发清理为主，没有添加移动/机械臂遥控台。

### 直接复用 AOS 操作

Python `M20Operations(device_ref, transport, timeout=...)` 的 `describe()` 返回操作表；`execute(operation, parameters, task_ref=...)` 返回 device_ref、task_ref、原始响应和 acknowledged/rejected/unknown。实际传输显式构造 `UdpJsonTransport(已确认地址, 端口)`；注入 fake transport 可以离线检查，无需加载机器人 SDK。

已有操作：localization.get、navigation.status、perception.status、posture.stand、posture.sit、navigation.submit、navigation.cancel。导航要求明确标定的 x/y/z/yaw，不接受检测框。超时不重发，acknowledged 不代表运动完成，physical_completion_confirmed 始终为 false，需后续查询/现场确认。

这一层是已提取的协议库，**没有把七项 UDP 操作自动注册为平台可远程执行的能力**；当前平台对外实际可调用的是三个 `/control` 操作。若要开放 UDP 维护操作，设备团队应确认网络、固件、坐标系和权限后，在设备边界接入该库；不用改垃圾检测、Agent 或 Capability 核心。拾取组合仍由已有机器人流程执行，不从 HXJM 逐条拼接未经验证的动作。

本次只运行协议回放、fake transport 和明确模拟设备测试。真实路线、停止、UDP、导航与机械臂均未联调。
