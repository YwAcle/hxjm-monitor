# 开发工作区启动

BoT-SORT 轨迹入库默认关闭，开发与合并后的正式启用步骤见
[轨迹持久化交接说明](python/video_analysis/PERSISTENCE.md)。个人项目仍订阅共享算法，
正式入库由算法所属目录统一负责。

在各自项目根目录运行：

```bash
bash scripts/start-local.sh --check
bash scripts/start-local.sh
bash scripts/stop-local.sh
```

启动器会先检查 Docker，再编译。如果账号已加入 `docker` 组，但当前终端还没
刷新组权限，会自动通过 `sg docker` 以同一用户重新启动，无需每次手动添加前缀。
若账号尚未加入组，仍需管理员配置；Docker 不可用时会立即报错并保留原始原因。
停止脚本会按现有进程的运行组自动切换已有授权，兼容 `sg docker` 启动的服务。
即使进程记录丢失，也会按本项目目录识别并清理遗留的 Vite 进程。
有端口配置时，停止后会检查本项目应用的 TCP 监听端口；仍有监听则报错，
不会显示停止成功。MySQL、PostgreSQL、Redis 的共享端口不在该检查范围内。

每个项目读取自己的 `local-ports.env`，运行自己的前端、后端、ai_stream。
`local-video.env` 指定唯一算法目录：

```bash
HXJM_ANALYSIS_ROOT="${HXJM_ANALYSIS_ROOT:-/data/nfs_storage/hxjm}"
```

只有 `/data/nfs_storage/hxjm` 会启动 BoT-SORT 模型和推理进程，分析接口默认是
`http://127.0.0.1:28010`。算法所属目录独立于 Git 主仓库；复制或独立克隆项目
不会获得算法启动权。只有算法目录允许显式选择 `VIDEO_ANALYSIS_MODE=local`。

某个工作区需要在本目录内验证算法和入库管线时，可在该目录创建被 Git 忽略的
`local-video.local.env`，覆盖不提交的归属设置：

```bash
# /data/nfs_storage/hxjm-zwd/local-video.local.env
HXJM_ANALYSIS_ROOT="/data/nfs_storage/hxjm-zwd"
```

它覆盖受版本控制的 `local-video.env` 默认值，只作用于本目录，并用本目录的
端口、队列和 `local-results.env`。同一时间只应有一套 BoT-SORT 占用模型和这些
来源；切换到本目录前先停止主目录服务，避免两个生产端争用同一特征实例和 GPU。

`/data/nfs_storage/hxjm-wsc/hxjm-monitor` 只通过 WebSocket 订阅检测框、跟踪 ID
和分析状态，不启动或准备模型，不启动 ReID/VAD/DeepSORT 推理进程。
即使主算法未运行，也可正常启动个人项目；页面会提示 AI 服务离线并重连，
不会启动本地算法作为替代。个人页面不提供订阅 JPEG 画面的同帧验收模式。

视频独立于算法订阅。个人 MediaMTX 使用自己的端口（当前 RTSP 18754、WebRTC
19089），从 MySQL `ba_machine.video_url` 直接拉摄像头；不从主目录中继视频。
页面的 `/shared-media` 是保留的代理路径名，上游始终是本项目的 MediaMTX，
不表示共享主目录媒体。个人流不重复录像；录像仍由主目录负责。

主目录停止时，会完整停止所属的共享服务管理器、BoT-SORT、模型子进程和
MediaMTX；MySQL、PostgreSQL、Redis 保持运行。个人项目的视频不受影响，
检测框在断线或结果过期时清除。个人项目停止时，不会调用主目录的停止命令。
启动或停止个人项目会清理旧启动器在个人目录下遗留的共享算法/媒体进程。
启停命令应使用启动这些进程的同一账号，不能依靠另一个账号停止其进程。

独立视频连接没有共同的精确采集时间，实时检测框采用带有效期的近似叠加，
不承诺与个人视频严格同帧。

首次应用此修复，请以当前服务所属账号（本机是 `wangshc`）依次执行：

```bash
bash /data/nfs_storage/hxjm-wsc/hxjm-monitor/scripts/stop-local.sh
bash /data/nfs_storage/hxjm/scripts/stop-local.sh
bash /data/nfs_storage/hxjm/scripts/start-local.sh
bash /data/nfs_storage/hxjm-wsc/hxjm-monitor/scripts/start-local.sh
```

之后两套项目各自使用普通启停命令即可。停止主目录时，无需再额外手动停止
共享媒体。已有模型文件不需要删除，也不会被个人项目加载。
