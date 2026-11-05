# LLM Report WebSocket 接口文档

## 1. 说明

- 该 WebSocket 用于向前端实时推送 `llm_report` 表中的新数据。
- 后端采用 **每 3 秒轮询一次 DB** 的方式检测新增记录，有新记录即推送。
- 首次连接会下发最近 N 条历史记录作为初始化数据。
- 为避免页面刷新时 `init` 与增量推送并发导致重复：服务端保证对同一个连接 **先发送 `init`，在 `init` 发送完成前不会发送 `append`**。

## 2. 连接信息

- **协议**：WebSocket
- **URL**：`ws://{host}:{server.port}/ws/llm-report`
- **示例**：`ws://192.168.108.238:8080/ws/llm-report`

### 2.1 配置项（后端）

在 `hxjm-admin/src/main/resources/application.yml`：

```yml
smartmonitor:
  ws:
    llmReport:
      pollDelayMs: 3000
      initLimit: 20
      initLookbackSeconds: 3600
      pushLimit: 200
```

说明：

- `pollDelayMs`：轮询间隔（ms）。
- `initLimit`：首次连接下发的历史条数。
- `initLookbackSeconds`：首次连接只下发最近 N 秒内的数据（默认 3600s=最近 1 小时；页面刷新不会重复下发很久以前的数据）。
- `pushLimit`：单次轮询最多推送条数（防止积压导致单包过大）。

## 3. 消息协议

### 3.1 客户端 -> 服务端

#### 3.1.1 心跳

- **请求**

```json
{ "type": "ping" }
```

- **响应**

```json
{ "type": "pong" }
```

### 3.2 服务端 -> 客户端

#### 3.2.1 初始化消息（首次连接）

- `type` 固定为 `llm_report`
- `op` 固定为 `init`
- `data.items` 为最近 N 条记录（按时间升序排列，方便前端按序追加渲染）

```json
{
  "type": "llm_report",
  "op": "init",
  "data": {
    "items": [
      {
        "id": "30f30dcf-7957-4261-b20d-e33e77264c12",
        "episode_id": "",
        "vad_id": 14,
        "prompt_type": "vad",
        "report_json": {
          "summary": "...",
          "confidence": 0.8,
          "event_type": "non-violence",
          "risk_level": "low",
          "key_observations": ["...", "..."]
        },
        "report_text": "监控显示一名穿绿色上衣的人员在办公室内行走...",
        "created_at": "2026-01-05 07:18:57.138 +00"
      }
    ],
    "cursor": {
      "id": "30f30dcf-7957-4261-b20d-e33e77264c12",
      "created_at": 1736061537138
    }
  }
}
```

字段说明：

- `id`：`llm_report.id`
- `episode_id`：`llm_report.episode_id`
- `vad_id`：`llm_report.vad_id`
- `prompt_type`：`llm_report.prompt_type`（如 `reid` / `vad`）
- `report_json`：`llm_report.report_json`（JSON 对象）
- `report_text`：`llm_report.report_text`
- `created_at`：`llm_report.created_at`（字符串，含毫秒与时区偏移）

补充：

- `data.cursor.created_at` 是毫秒时间戳（用于前端排查/调试），前端可不使用。

#### 3.2.2 追加消息（有新记录产生）

- `type` 固定为 `llm_report`
- `op` 固定为 `append`
- `data.items` 为本次新增的记录（按时间升序）

```json
{
  "type": "llm_report",
  "op": "append",
  "data": {
    "items": [
      {
        "id": "...",
        "episode_id": "...",
        "vad_id": 15,
        "prompt_type": "vad",
        "report_json": { "summary": "..." },
        "report_text": "...",
        "created_at": "2026-01-05 07:19:00.001 +00"
      }
    ],
    "cursor": {
      "id": "...",
      "created_at": 1736061540001
    }
  }
}
```

#### 3.2.3 错误消息

```json
{ "type": "error", "message": "init_failed" }
```

## 4. 前端对接建议

- 前端只需要处理两种业务消息：
  - `type=llm_report, op=init`：初始化填充历史日志
  - `type=llm_report, op=append`：新增日志追加到列表尾部
- 建议前端维护 `items` 的上限（例如最多保留 500~1000 条）避免内存持续增长。
