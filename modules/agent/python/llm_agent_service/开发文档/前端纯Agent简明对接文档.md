
> 适用接口：`llm_agent_service` 的 `POST /chat`  
> 默认地址：`http://<AGENT_HOST>:8002`

## 1. 前端需要做什么

当前后端统一使用纯 Agent 处理文本和图片。原有前端请求可以继续使用，建议补充以下能力：

1. 一个聊天会话持续使用同一个 `session_id`，用于保存上下文记忆。
2. 每次请求生成一个新的 `trace_id`，用于查询该次请求的后端日志。
3. 根据 HTTP 状态码和后端 `error_code` 显示错误，不要把所有错误都显示为“Agent 响应超时”。
4. 图片上传前校验格式和大小。

`session_id` 和 `trace_id` 的区别：

```text
session_id：标识一段会话，同一会话的多轮请求保持不变。
trace_id：标识一次请求，每次点击发送都重新生成。
```

二者长度均为 1 至 128 个字符，只能包含字母、数字、`.`、`_`、`:` 和 `-`。推荐使用 UUID。

## 2. 文本请求

```typescript
const traceId = crypto.randomUUID();

const response = await fetch("http://<AGENT_HOST>:8002/chat", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Trace-ID": traceId,
  },
  body: JSON.stringify({
    session_id: currentSessionId,
    prompt: inputText,
  }),
});

const result = await response.json();
```

成功响应示例：

```json
{
  "type": "agent",
  "text": "你好，请问有什么可以帮助你？",
  "agent": {
    "mode": "agent",
    "steps": 1,
    "finish_reason": "final"
  },
  "session_id": "0f159619-6313-4182-a22f-20f32f697fd8",
  "trace_id": "814949c1-b9ae-45f0-83cb-1a87db5d55eb"
}
```

前端主要使用 `text` 展示回答，保存响应中的 `session_id` 和 `trace_id` 即可。`agent` 字段用于调试，不建议依赖其内容实现页面业务逻辑。

## 3. 图片请求

使用 `multipart/form-data` 上传单张图片：

```typescript
const traceId = crypto.randomUUID();
const formData = new FormData();
formData.append("session_id", currentSessionId);
formData.append("trace_id", traceId);
formData.append("prompt", inputText);
formData.append("file", imageFile);

const response = await fetch("http://<AGENT_HOST>:8002/chat", {
  method: "POST",
  body: formData,
});

const result = await response.json();
```

注意：

- 不要手动设置 `Content-Type`，浏览器会自动添加 multipart boundary。
- 只上传图片、不填写文字也可以；后端不会添加默认提示词，由 Agent 结合会话上下文判断如何处理。
- 当前一次请求只支持一张图片。
- 支持 JPEG、PNG、WebP，单张图片最大 10 MB。
- 图片最长边不能超过 8192 像素，总像素不能超过 2500 万。
- 整个请求体最大 20 MB。

## 4. 错误处理

错误响应示例：

```json
{
  "error": "仅支持 JPEG、PNG 和 WebP 图片",
  "error_code": "UNSUPPORTED_IMAGE_FORMAT",
  "trace_id": "814949c1-b9ae-45f0-83cb-1a87db5d55eb"
}
```

推荐统一处理：

```typescript
if (!response.ok) {
  const message = result.error ?? `请求失败：HTTP ${response.status}`;
  console.error("Agent 请求失败", {
    errorCode: result.error_code,
    traceId: result.trace_id,
  });
  throw new Error(message);
}
```

当前可能返回的输入错误码：

| HTTP 状态 | `error_code` | 含义 |
|---|---|---|
| `400` | `MISSING_PROMPT` | 没有文本，也没有图片 |
| `400` | `INVALID_SESSION_ID` | `session_id` 格式错误 |
| `400` | `INVALID_TRACE_ID` | `trace_id` 格式错误 |
| `400` | `PROMPT_TOO_LONG` | 提示词超过 8000 个字符 |
| `400` | `INVALID_IMAGE` | Base64 错误或图片无法解析 |
| `400` | `UNSUPPORTED_IMAGE_FORMAT` | 图片格式不支持 |
| `413` | `IMAGE_TOO_LARGE` | 图片文件超过 10 MB |
| `413` | `IMAGE_DIMENSIONS_TOO_LARGE` | 图片尺寸或总像素超限 |
| `413` | `REQUEST_TOO_LARGE` | 整个请求体超过 20 MB |
| `500` | `INTERNAL_ERROR` | 后端处理失败 |

只有请求被 `AbortController` 主动中止，或者浏览器明确报告网络超时，前端才显示“响应超时”。后端返回 `400`、`413` 或 `500` 时，应优先显示响应中的 `error`。

## 5. TypeScript 类型

```typescript
export interface AgentChatResponse {
  type: "agent";
  text: string;
  session_id: string;
  trace_id: string;
  agent?: {
    mode: "agent";
    steps: number;
    finish_reason: string;
  };
}

export interface AgentErrorResponse {
  error: string;
  error_code: string;
  trace_id: string;
}
```

## 6. 联调检查

1. 连续发送“我叫张三”和“我叫什么”，确认两次请求的 `session_id` 相同。
2. 确认两次请求的 `trace_id` 不同。
3. 只上传一张图片、不输入文字，确认可以正常获得回答。
4. 上传不支持的文件，确认页面显示后端返回的具体错误，而不是“响应超时”。
5. 出现问题时，把响应中的 `trace_id` 提供给后端，通过以下命令查询完整调用链：

```bash
rg '"trace_id":"<TRACE_ID>"' .runtime-cache/service-stack/sglang/agent.log
```
