# AI 流媒体处理系统

实时视频流 AI 处理平台，支持多路摄像头、多 AI 任务并行处理。

## 快速启动

```bash
cd docker
docker-compose up -d          # 启动
docker-compose logs -f        # 查看日志
docker-compose down           # 停止
```

## 配置文件

编辑 `config.yaml`：

```yaml
mediamtx_url: rtsp://127.0.0.1:8554/live

# 各 AI 任务的 IPC 地址
ai_tasks_ipc:
  reid: ipc:///tmp/py_ai_reid.ipc
  sam3: ipc:///tmp/py_ai_sam3.ipc

# 视频流配置
streams:
  - name: camera_1
    rtsp_url: rtsp://admin:password@192.168.1.100:554/Streaming/Channels/101
    keep_original: true
    enabled: true
    ai_tasks:
      - type: reid
        transport: shm

      - type: sam3
        transport: shm
        frame_skip: 3
        zmq_timeout: 120000
```

### 任务配置字段

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `type` | 任务名称 | 必填 |
| `transport` | 传输模式: `shm`(共享内存) / `base64` | `shm` |
| `frame_skip` | 每 N 帧处理一次 | 1 |
| `ai_thread_num` | AI 线程数 | 2 |
| `queue_size` | 帧队列大小 | 25 |
| `zmq_timeout` | 超时(ms) | 5000 |
| `ipc_addr` | IPC 地址(覆盖全局) | - |

## 播放地址

```
WebRTC: http://127.0.0.1:8889/live/camera_1_reid
RTSP:   rtsp://127.0.0.1:8554/live/camera_1_reid
```

---

## 新增 AI 算法

**无需修改 C++ 代码，只需两步：**

### 1. 创建 Python 服务

复制模板并实现 `process_frame`：

```bash
cp -r python/sam3 python/my_algo
```

编辑 `python/my_algo/server.py`：

```python
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from base.server_base import BaseServer
from base.shm_utils import open_and_map, close_map

DEFAULT_IPC_ADDR = "ipc:///tmp/py_ai_my_algo.ipc"

class MyAlgoServer(BaseServer):
    def __init__(self):
        addr = os.getenv("MY_ALGO_ZMQ_ADDR", DEFAULT_IPC_ADDR)
        super().__init__(addr)

    @staticmethod
    def init_model_context():
        # 加载模型（只调用一次）
        return {"model": load_my_model()}

    def process_frame(self, meta: dict, model_ctx: dict):
        # 读取共享内存中的帧
        shm_name = meta.get("shmName")
        shm_len = int(meta.get("shmLen", 0))
        width = int(meta.get("width"))
        height = int(meta.get("height"))
        
        fd, mm, _ = open_and_map(shm_name)
        frame = np.frombuffer(mm[:shm_len], dtype=np.uint8).reshape(height, width, 3)
        
        # 你的算法处理
        result = model_ctx["model"].predict(frame)
        
        # 写回结果
        mm[:shm_len] = result.tobytes()
        close_map(fd, mm)

def main():
    server = MyAlgoServer()
    server.serve()

if __name__ == "__main__":
    main()
```

### 2. 添加配置

在 `config.json` 中添加任务：

```json
{
    "ai_tasks_ipc": {
        "my_algo": "ipc:///tmp/py_ai_my_algo.ipc"
    },
    "streams": [
        {
            "ai_tasks": [
                {
                    "type": "my_algo",
                    "transport": "shm"
                }
            ]
        }
    ]
}
```

### 传输模式说明

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `shm` | 共享内存传输，处理后回读结果 | 需要渲染的任务 (reid, sam3) |
| `base64` | Base64 传输，发送后不回读 | 只做分析/上报的任务 |
