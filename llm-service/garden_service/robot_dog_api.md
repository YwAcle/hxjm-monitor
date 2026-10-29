# Garden Service SSE 机器人推流接口规范

本文档定义 `garden_service` 面向机器狗或机器人调度系统的企业级 SSE 推流接口规范。

目标是让机器人侧可以稳定订阅大模型推理结果，并具备以下能力：

- 长连接实时消费
- 断线重连与断点续传
- 会话生命周期管理
- 标准化错误模型
- 鉴权与会话级访问控制
- 可扩展的任务命名空间
- 心跳保活与自动清理

本文档是接口规范文档，适合作为机器人侧对接基线。服务端实现应尽量与本文保持一致。

## 1. 设计原则

- 通信模式：`garden_service` 为 SSE 服务端，机器人为 SSE 客户端
- 传输方向：单向事件流，数据从 `garden_service -> 机器人`
- 连接模型：先创建会话，再建立事件流订阅
- 可靠性：支持 `Last-Event-ID` 断点续传和基于 `event id` 的事件重放
- 会话治理：支持 `INIT / ACTIVE / CLOSED / EXPIRED` 生命周期
- 标准事件：统一使用 SSE 标准字段 `event`、`id`、`data`
- 时间标准：所有时间字段统一为 `int64` 毫秒时间戳
- 数据类型：避免 `float`，数值字段统一使用整数或字符串编码的定点数
- 安全性：支持 `Authorization: Bearer <token>` 或 `session_token`

## 2. 服务地址

- 推荐服务地址格式：`http://<garden_service_host>:8765`
- 机器人侧访问时不应使用 `127.0.0.1`
- 应填写部署 `garden_service` 的宿主机可达 IP

当前建议示例：

```text
http://192.168.109.191:8765
```

说明：

- 上述地址基于当前部署约定给出
- 我在当前执行环境内使用 `ifconfig` 仅看到回环口，未读取到业务网卡
- 如宿主机实际 IP 与该地址不一致，应以宿主机网卡地址为准

## 3. 通用约定

### 3.1 协议与编码

- HTTP 版本：`HTTP/1.1` 或更高
- 编码：`UTF-8`
- 普通接口响应：`application/json`
- SSE 响应：`text/event-stream`

### 3.2 鉴权

支持两层鉴权：

- 接口级鉴权：`Authorization: Bearer <access_token>`
- 会话级鉴权：`session_token`

推荐策略：

- 创建会话时使用平台级 `Bearer Token`
- 创建成功后返回 `session_token`
- 建立 SSE 长连接和关闭会话时同时携带 `Bearer Token` 或 `session_token`

推荐请求头：

```http
Authorization: Bearer <access_token>
Accept: application/json
Content-Type: application/json
```

SSE 建议请求头：

```http
Authorization: Bearer <access_token>
Accept: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
Last-Event-ID: 18446744073709551616
```

说明：

- `Last-Event-ID` 为可选
- 若使用会话级鉴权，也可通过请求头 `X-Session-Token: <session_token>` 或查询参数传递
- 生产环境推荐优先使用请求头，不推荐把敏感 token 暴露在 URL

### 3.3 标准错误响应

所有非 SSE HTTP 接口在失败时统一返回：

```json
{
  "error_code": "SESSION_NOT_FOUND",
  "message": "session does not exist or has expired",
  "request_id": "4f6d8b7a1c8a4c1d9ad22d4d9477f0a1",
  "timestamp_ms": 1776241200123
}
```

字段说明：

- `error_code`：机器可识别的错误码
- `message`：面向调用方的错误描述
- `request_id`：服务端请求追踪 ID
- `timestamp_ms`：错误发生时间，毫秒时间戳

建议错误码：

- `UNAUTHORIZED`
- `FORBIDDEN`
- `INVALID_ARGUMENT`
- `SESSION_NOT_FOUND`
- `SESSION_EXPIRED`
- `SESSION_CLOSED`
- `EVENT_REPLAY_UNAVAILABLE`
- `RATE_LIMITED`
- `INTERNAL_ERROR`
- `SERVICE_UNAVAILABLE`

### 3.4 SSE 标准事件格式

统一只使用 SSE 标准字段：

```text
id: 18446744073709551616
event: inference.result
data: {"session_id":"sess_001","timestamp_ms":1776241200123,"payload":{...}}
```

约束：

- 不在 `data` 中重复放 `event_type`
- 事件类型由 `event` 字段表达
- 事件唯一序号由 `id` 字段表达
- `data` 为单行 JSON

## 4. Session 生命周期

### 4.1 状态定义

- `INIT`：会话已创建，但事件流尚未建立
- `ACTIVE`：至少建立过一个有效 SSE 连接，且会话未关闭未过期
- `CLOSED`：调用方主动关闭
- `EXPIRED`：超过 TTL 或空闲超时后自动失效

### 4.2 生命周期规则

1. 创建会话后进入 `INIT`
2. 首次成功建立 SSE 连接后转为 `ACTIVE`
3. 客户端调用关闭接口后转为 `CLOSED`
4. 若超过 TTL 或空闲时间未续期，则转为 `EXPIRED`
5. `CLOSED` 和 `EXPIRED` 为终态

### 4.3 TTL 与自动清理

建议服务端维护两个时间窗口：

- `ttl_ms`：会话最大生存时间，默认建议 `3600000`
- `idle_timeout_ms`：空闲超时时间，默认建议 `300000`

自动清理要求：

- 服务端定时扫描 `CLOSED` / `EXPIRED` 会话
- 清理会话元数据、鉴权 token、事件缓存
- 清理周期建议 `30000 ms`
- 已过期会话再次访问时返回 `SESSION_EXPIRED`

### 4.4 事件缓存与重放窗口

为支持断点续传，每个会话应维护事件缓存。

建议参数：

- `replay_buffer_size`：默认 `1000`
- `replay_window_ms`：默认 `300000`

清理策略：

- 优先按时间窗口淘汰
- 若仍超限，再按最老事件淘汰

## 5. 事件 ID 与断点续传

### 5.1 event id 规则

- `id` 必须全局递增，推荐使用 `uint64` 十进制字符串
- 同一会话内不得重复
- 客户端应将最近成功处理的 `id` 持久化

### 5.2 Last-Event-ID 机制

客户端重连时应携带：

```http
Last-Event-ID: 18446744073709551616
```

服务端行为：

- 若缓存中存在该 ID 之后的事件，则按顺序重放
- 若该 ID 过旧且缓存已淘汰，返回 HTTP `409` 或发送 `error` 事件后断开
- 若该 ID 大于当前最新事件 ID，返回 `INVALID_ARGUMENT`

### 5.3 重放语义

重放期间事件顺序要求：

1. 先发送 `stream.resumed`
2. 再按 `id` 递增顺序发送历史事件
3. 历史事件补齐后切换到实时推送

重放不应产生新的事件 ID，必须使用原始事件 ID。

## 6. 接口定义

## 6.1 创建会话

- 方法：`POST`
- 路径：`/api/robot-dog/sessions`

用途：

- 创建机器人订阅会话
- 分配 `session_id`
- 分配 `session_token`
- 下发 TTL、重放窗口和事件流地址

请求体示例：

```json
{
  "client_name": "robot_dog_alpha",
  "client_instance_id": "dog-alpha-001",
  "subscriptions": [
    {
      "camera_id": "camera_1",
      "task": "vision.garden.garbage.detect"
    },
    {
      "camera_id": "camera_2",
      "task": "vision.garden.garbage.detect"
    }
  ],
  "delivery": {
    "alert_only": false,
    "heartbeat_interval_ms": 15000,
    "replay_buffer_size": 1000
  }
}
```

字段说明：

- `client_name`：客户端名称
- `client_instance_id`：客户端实例 ID，用于多设备部署场景
- `subscriptions`：订阅列表
- `subscriptions[].camera_id`：摄像头 ID
- `subscriptions[].task`：任务命名空间，当前建议 `vision.garden.garbage.detect`
- `delivery.alert_only`：是否仅接收异常事件
- `delivery.heartbeat_interval_ms`：期望心跳周期
- `delivery.replay_buffer_size`：建议缓存大小

成功响应示例：

```json
{
  "session_id": "sess_7f84f6c0c30d4c87baf6bdf7d4d62d5a",
  "session_token": "st_5b53f53d3d3b49af8d3cb1d77f2a8c14",
  "status": "INIT",
  "created_at_ms": 1776241200123,
  "expires_at_ms": 1776244800123,
  "ttl_ms": 3600000,
  "idle_timeout_ms": 300000,
  "heartbeat_interval_ms": 15000,
  "replay_window_ms": 300000,
  "replay_buffer_size": 1000,
  "events_url": "/api/robot-dog/sessions/sess_7f84f6c0c30d4c87baf6bdf7d4d62d5a/events",
  "close_url": "/api/robot-dog/sessions/sess_7f84f6c0c30d4c87baf6bdf7d4d62d5a",
  "request_id": "4f6d8b7a1c8a4c1d9ad22d4d9477f0a1",
  "timestamp_ms": 1776241200123
}
```

失败响应示例：

```json
{
  "error_code": "INVALID_ARGUMENT",
  "message": "subscriptions must not be empty",
  "request_id": "4f6d8b7a1c8a4c1d9ad22d4d9477f0a1",
  "timestamp_ms": 1776241200123
}
```

## 6.2 建立 SSE 事件流

- 方法：`GET`
- 路径：`/api/robot-dog/sessions/{session_id}/events`

请求头：

```http
Authorization: Bearer <access_token>
X-Session-Token: <session_token>
Accept: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
Last-Event-ID: 18446744073709551616
```

说明：

- `Authorization` 与 `X-Session-Token` 可按部署策略二选一或同时启用
- 首次建立连接可不带 `Last-Event-ID`
- 断线重连时建议必须带 `Last-Event-ID`

服务端响应头建议：

```http
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-store
Connection: keep-alive
X-Accel-Buffering: no
```

### 6.2.1 标准事件类型

推荐事件命名采用命名空间风格：

- `session.ready`
- `stream.resumed`
- `inference.result`
- `heartbeat`
- `error`
- `session.closed`
- `session.expired`

### 6.2.2 session.ready

用途：

- 表示 SSE 通道已建立
- 若当前会话状态为 `INIT`，此时切换为 `ACTIVE`

示例：

```text
id: 18446744073709551610
event: session.ready
data: {"session_id":"sess_7f84f6c0c30d4c87baf6bdf7d4d62d5a","status":"ACTIVE","created_at_ms":1776241200123,"expires_at_ms":1776244800123,"timestamp_ms":1776241201123}
```

### 6.2.3 stream.resumed

用途：

- 表示服务端接受了 `Last-Event-ID`
- 后续将开始重放历史事件

示例：

```text
id: 18446744073709551611
event: stream.resumed
data: {"session_id":"sess_7f84f6c0c30d4c87baf6bdf7d4d62d5a","resume_from_event_id":"18446744073709551616","replay_start_event_id":"18446744073709551617","timestamp_ms":1776241210000}
```

### 6.2.4 inference.result

用途：

- 推送单条推理结果
- `task` 使用可扩展命名空间

示例：

```text
id: 18446744073709551617
event: inference.result
data: {"session_id":"sess_7f84f6c0c30d4c87baf6bdf7d4d62d5a","timestamp_ms":1776241210123,"source":"garden_service","camera_id":"camera_1","task":"vision.garden.garbage.detect","frame":{"timestamp_ms":1776241210001,"index":"2350","pts":"705000","video_path":"live/camera_1_garden"},"result":{"status":"ALERT","has_target":true,"target_type":"plastic_bottle","confidence_milli":850,"scene_description":"室内办公区域，地面散落着一个塑料瓶，周围有办公设备和家具，环境整洁度一般。","reason":"地面上有一个塑料瓶，属于散落的废弃物，符合垃圾定义，且位于可见范围内，存在污染风险。","suggestion":"清理地面上的塑料瓶，确保办公区域整洁。"},"metrics":{"latency_ms":"1820"}}
```

字段说明：

- `task`：任务命名空间，后续可扩展到更多视觉任务
- `frame.timestamp_ms`：帧时间戳，毫秒
- `frame.index`：帧序号，字符串表示的整数
- `frame.pts`：底层视频时间戳，字符串表示的整数
- `result.status`：建议枚举 `NORMAL` / `ALERT`
- `result.has_target`：泛化布尔标记，避免未来仅限垃圾场景
- `result.target_type`：目标类型，例如 `plastic_bottle`
- `result.confidence_milli`：千分制整型置信度，例如 `850` 表示 `0.850`
- `metrics.latency_ms`：推理耗时，字符串表示的整数毫秒

说明：

- 为增强扩展性，`has_garbage` 已泛化为 `has_target`
- 若当前仅处理垃圾检测，机器人侧可在 `task == vision.garden.garbage.detect` 时按垃圾语义解释
- 所有延迟和时间相关字段均避免 `float`

### 6.2.5 heartbeat

用途：

- 标准保活事件
- 无新业务事件时定期发送

示例：

```text
id: 18446744073709551618
event: heartbeat
data: {"session_id":"sess_7f84f6c0c30d4c87baf6bdf7d4d62d5a","timestamp_ms":1776241225000}
```

要求：

- 心跳应使用标准 SSE 事件，不再使用注释行
- 客户端收到后只更新连接活性，不参与业务处理

### 6.2.6 error

用途：

- SSE 通道内的业务错误或恢复失败通知

示例：

```text
id: 18446744073709551619
event: error
data: {"session_id":"sess_7f84f6c0c30d4c87baf6bdf7d4d62d5a","error_code":"EVENT_REPLAY_UNAVAILABLE","message":"requested replay range is no longer available","timestamp_ms":1776241228000}
```

错误事件发送后，服务端可根据错误类型：

- 保持连接并继续推送
- 或主动关闭连接

建议策略：

- 可恢复错误：发送 `error`，保持连接
- 不可恢复错误：发送 `error` 后断开连接

### 6.2.7 session.closed

用途：

- 表示会话被显式关闭

示例：

```text
id: 18446744073709551620
event: session.closed
data: {"session_id":"sess_7f84f6c0c30d4c87baf6bdf7d4d62d5a","timestamp_ms":1776241300000}
```

### 6.2.8 session.expired

用途：

- 表示会话已过期

示例：

```text
id: 18446744073709551621
event: session.expired
data: {"session_id":"sess_7f84f6c0c30d4c87baf6bdf7d4d62d5a","timestamp_ms":1776241500000}
```

## 6.3 查询会话状态

为方便机器人侧治理，建议补充会话查询接口。

- 方法：`GET`
- 路径：`/api/robot-dog/sessions/{session_id}`

成功响应示例：

```json
{
  "session_id": "sess_7f84f6c0c30d4c87baf6bdf7d4d62d5a",
  "status": "ACTIVE",
  "created_at_ms": 1776241200123,
  "last_active_at_ms": 1776241215000,
  "expires_at_ms": 1776244800123,
  "ttl_ms": 3600000,
  "idle_timeout_ms": 300000,
  "last_event_id": "18446744073709551618",
  "request_id": "4f6d8b7a1c8a4c1d9ad22d4d9477f0a1",
  "timestamp_ms": 1776241216000
}
```

## 6.4 关闭会话

- 方法：`DELETE`
- 路径：`/api/robot-dog/sessions/{session_id}`

成功响应示例：

```json
{
  "session_id": "sess_7f84f6c0c30d4c87baf6bdf7d4d62d5a",
  "status": "CLOSED",
  "closed_at_ms": 1776241300000,
  "request_id": "4f6d8b7a1c8a4c1d9ad22d4d9477f0a1",
  "timestamp_ms": 1776241300000
}
```

失败响应示例：

```json
{
  "error_code": "SESSION_NOT_FOUND",
  "message": "session does not exist",
  "request_id": "4f6d8b7a1c8a4c1d9ad22d4d9477f0a1",
  "timestamp_ms": 1776241300000
}
```

## 7. 幂等性与高可用建议

### 7.1 客户端建议

- 持久化保存最近成功消费的 `Last-Event-ID`
- 断线后自动重连
- 重连时带上 `Last-Event-ID`
- 对 `inference.result` 按 `id` 去重
- 对会话过期与鉴权失败做明确告警

### 7.2 服务端建议

- 每个会话维护独立事件缓存
- 事件 ID 单调递增
- 会话状态变更需原子化
- 自动清理过期会话与事件缓存
- 长连接写失败时及时回收资源
- 为每个请求和会话生成可观测的 `request_id`

### 7.3 负载均衡建议

若部署多实例，建议满足以下之一：

- 基于 `session_id` 做粘性路由
- 或使用共享事件存储以支持跨实例重放

否则 `Last-Event-ID` 重放能力可能在多实例场景下失效。

## 8. 任务命名空间建议

为避免后续扩展时字段含义漂移，建议采用命名空间风格任务名：

- `vision.garden.garbage.detect`
- `vision.garden.garbage.classify`
- `vision.security.intrusion.detect`
- `vision.safety.smoke.detect`

原则：

- 一级表示领域，例如 `vision`
- 二级表示子系统，例如 `garden`
- 后续层级表示能力与动作，例如 `garbage.detect`

## 9. 迁移建议

从当前简化版文档迁移到本规范时，建议重点调整：

- 使用 `event + id + data` 标准结构，去掉 `data.event_type`
- 将心跳从注释改为标准 `heartbeat` 事件
- 所有时间字段统一为 `*_ms`
- 置信度改为 `confidence_milli`
- 推理耗时改为整型毫秒或数字字符串
- 增加 `Last-Event-ID`、事件缓存和重放策略
- 增加 `session_token`、TTL 和自动清理机制

## 10. 最小对接流程

1. 机器人使用 `Bearer Token` 调用创建会话接口
2. 获取 `session_id`、`session_token`、`events_url`
3. 建立 SSE 长连接并接收 `session.ready`
4. 消费 `inference.result`
5. 持久化最新 `id`
6. 断线后携带 `Last-Event-ID` 自动重连
7. 不再需要订阅时调用关闭接口

## 11. 当前实现说明

当前仓库中的 `garden_service` 已具备 SSE 原型能力，但本文档中的以下内容属于企业级增强项，服务端实现需要逐步补齐：

- `Last-Event-ID` 重放
- 完整状态机与 TTL
- `session_token` 鉴权
- 标准 `error` 事件
- 标准 `heartbeat` 事件
- 会话查询接口
- 多实例下的共享重放能力

建议以后续迭代按本文档收敛接口与实现。
