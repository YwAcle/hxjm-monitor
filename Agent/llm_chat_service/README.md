# llm_chat_service

Chat 与 Agent、Report 共用根目录 `.env` 模型配置，切换方式见 [模型切换指南](../MODEL_SWITCHING.md)。

## Run

```bash
python -m llm_chat_service.main --db-host 127.0.0.1 --db-user root --db-password 123456 --db-name postgres --db-schema public
```

## API

### POST /chat

JSON:

```json
{"prompt":"今天上午 zjh 干了什么？","person_name":"zjh","time_hint":"今天上午","top_k":10}
```

### POST /chat_with_image

multipart/form-data:

- prompt: string
- file: jpg/png
- time_hint: optional
- top_k: optional
