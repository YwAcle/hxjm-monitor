# Garden 垃圾检测服务

这个服务用于接收 `mtx` 推送过来的视频帧，把帧送入微调后的 `Qwen3-VL-2B-Instruct` Garden 模型，并在检测到垃圾时把模型输出流式打印到控制台。

## 目录

- `server.py`: 服务启动入口，负责组装 HTTP / ZMQ / worker
- `garden_config.py`: 默认配置和环境变量解析
- `model_runner.py`: 模型加载与推理执行
- `prompting.py`: prompt 模板装载、占位符渲染、模型 JSON 解析
- `image_utils.py`: 图像解码和预览图生成
- `prompts/`: prompt 模板目录，便于后续扩展更多任务模板
- `robot_dog_api.md`: 面向机器狗的 SSE 接口文档

## 默认约定

- 模型目录: `/home/guest/hxjm/llm-service/garden/Garden`
- IPC 地址: `ipc:///tmp/py_ai_garden.ipc`
- Prompt 模板: `llm-service/garden_service/prompts/garbage_detection.json`

## 启动

```bash
cd /home/guest/hxjm
python3 llm-service/garden_service/server.py
```

启动后除了 ZeroMQ IPC 服务，还会同时打开一个可视化面板：

```bash
http://127.0.0.1:8765
```

同时也会提供面向机器狗的 SSE 推理结果推送接口，对接文档见：

```bash
llm-service/garden_service/robot_dog_api.md
```

## 可选环境变量

```bash
export GARDEN_MODEL_PATH=/home/guest/hxjm/llm-service/garden/Garden
export GARDEN_ZMQ_ADDR=ipc:///tmp/py_ai_garden.ipc
export GARDEN_PROMPT_TEMPLATE=/home/guest/hxjm/llm-service/garden_service/prompts/garbage_detection.json
export GARDEN_TORCH_DTYPE=auto
export GARDEN_DEVICE_MAP=auto
export GARDEN_HTTP_HOST=127.0.0.1
export GARDEN_HTTP_PORT=8765
export GARDEN_MODEL_WORKERS=4
```

`GARDEN_TORCH_DTYPE` 支持 `auto`、`bfloat16`、`float16`、`float32`。

`GARDEN_MODEL_WORKERS` 控制请求处理 worker 数。当前实现为了稳定性采用“多 worker 共享单模型实例”的方式，因此可以同时接入多路摄像头，但模型推理本身会串行进入同一份模型，避免 `device_map=auto` 并发加载导致的崩溃。

## 和 mtx 的连接方式

推荐在 `mtx/config.yaml` 的 AI 任务中使用：

```yaml
- type: garden
  transport: base64
  frame_skip: 25
  ai_thread_num: 1
  queue_size: 1
  zmq_timeout: 120000
```

`base64` 模式适合 Garden 这种只做分析和告警、不需要把检测结果回写到视频帧上的场景。
