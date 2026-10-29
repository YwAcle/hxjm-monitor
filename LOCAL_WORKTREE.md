# 开发工作区启动

> 协作方式更新（2026-10-29，v0.2）：本文件保留旧工作区／worktree方式的历史操作说明。后续开发采用独立账号、独立clone仓库和按需求创建的功能分支，以[协同开发流程](COLLABORATION_WORKFLOW.md)为准；旧目录迁移前仍需保留未交付改动。本文中的旧工作区启动说明不代表新账号下启动配置已验证。

在各自工作区根目录运行：

```bash
bash scripts/start-local.sh --check
bash scripts/start-local.sh
```

启动器及其必要依赖已纳入 Git；其它私有 `scripts/` 文件、`local-ports.env`
和 `.run/` 继续忽略。拉取代码不会同步模型权重、运行状态或私人端口配置。
启动器读取各工作区自己的 `local-ports.env`，保留原前端、后端和媒体端口。

默认 `VIDEO_ANALYSIS_MODE=shared`。公共 BoT-SORT 和 MediaMTX 在主目录运行，
工作区页面通过自己的 Vite 代理订阅同一份视频和检测结果。普通启动不会额外
加载一套跟踪模型；停止某个工作区应用也不会停止公共视频和算法服务。

启动器通过 `git rev-parse --git-common-dir` 发现主目录 `PRIMARY_ROOT`，通常为
`/data/nfs_storage/hxjm`。主目录必须先拉取并部署包含
`deploy/botsort/shared_service.py` 的版本；开发分支启动器只调用主目录的公共
管理器，不把开发分支算法代码替换到公共服务。主目录尚未更新时启动会明确报错。

公共媒体端口从主目录 `local-ports.env` 读取，分析 API 默认使用 `28010`。
摄像头的真实地址仍由公共服务读取 `ba_machine.video_url`，不修改数据库 IP。
主目录应用复用公共 MediaMTX；其它工作区的本地 MediaMTX 只中继公共 RTSP，
不再次直连摄像头，也不重复录像。录像由公共媒体服务保留一份。

公共服务的维护命令在主目录运行：

```bash
python3 deploy/botsort/shared_service.py status --root /data/nfs_storage/hxjm
python3 deploy/botsort/shared_service.py start --root /data/nfs_storage/hxjm
```

`bash scripts/stop-local.sh` 只停止本工作区应用，公共服务保持运行。
更改公共模型、摄像头源或公共服务时，应由维护者在主目录操作；开发者无需
为打开自己的页面启动独立算法。现有专用启动器中其它业务服务的配置仍需在
迁移时核对，避免把私人扩展逻辑当作共享启动器的一部分。

需要在自己的工作区单独试验算法时，显式选择本地模式：

```bash
VIDEO_ANALYSIS_MODE=local bash scripts/start-local.sh
```

本地模式会读取自己的 `.run/video-analysis.env`，使用本工作区媒体和分析端口，
额外占用模型资源及摄像头连接。结束试验后用普通命令重启即可回到共享模式。
