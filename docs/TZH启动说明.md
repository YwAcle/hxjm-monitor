# TZH 新目录启动说明

适用目录：`/data/nfs_storage/hxjm-tzh`，GitHub 分支 `hxjm-tzh`。

这份分支包含前端、Java 后端、C++ 控制及独立 MediaMTX，订阅 `/data/nfs_storage/hxjm` 所属的公共 BoT-SORT；个人目录不会加载公共跟踪模型。新增的 JoyAI 四路异常工具使用本目录独立环境和模型，由 `scripts/joyai-tool.sh` 显式启动，告警进入大屏“实时告警显示”；请使用本目录指令。

## 启动

在当前已具备 Node.js 18、Java 8、Maven、Docker 权限的服务器账户下执行：

```bash
cd /data/nfs_storage/hxjm-tzh
bash scripts/start-local.sh --check

# 当前分支的 application.yml 要求此变量非空。
# 为本目录个人后端生成令牌；不要复用其他业务端的私有令牌。
export VIDEO_RESULTS_SERVICE_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
bash scripts/start-local.sh
```

每次新开终端启动时，执行上面的 export 后再启动。该随机令牌仅用于此个人后端的服务身份配置，公共算法仍向其原有业务端投递，不会因启动本目录改变投递目标。若后续有外部服务需调用本目录受保护接口，再配置双方持久保存的服务身份。

首次启动自动构建 C++ 和 Java、运行 npm ci 安装本目录前端依赖，需要等待完成及所需依赖下载。启动期间不要重复执行启动命令。

启动成功后访问：

- 网页：`http://192.168.109.191:3011/`
- 后端：`http://192.168.109.191:24180/`

## 关闭

新增四路 JoyAI 异常监控见 [JoyAI工具接入说明](JoyAI工具接入说明.md)。系统启动完成后，使用 `bash scripts/joyai-tool.sh start` 显式加载同参数规模的 JoyAI INT4 并开始四路观察；Qwen 仅在有可疑片段时自动启动，完成队列后释放显存。仅关闭算法使用 `bash scripts/joyai-tool.sh stop`。下面的整套关闭命令也会停止本目录新增模型。

```bash
cd /data/nfs_storage/hxjm-tzh
bash scripts/stop-local.sh
```

停止仅针对这个新目录，不会停止原 `/home/guest/hxjm-tzh` 的系统、主项目公共算法或共享数据库。

## 配置与依赖

已创建被 Git 忽略的 `local-ports.env`，前端 `3011`、后端 `24180`、Redis 数据库 `11`；RTSP `34102`、RTP/RTCP `34112/34113`、WebRTC `34106`、媒体 API `34110`、C++ 控制 `34111`。新增异常工具使用 `34201—34204`。其余监听也在该文件中，已检查未与可见项目配置冲突。JoyAI 权重和环境在本目录 `.run/joyai/`，授权文件独立生成，不复用旧目录私有令牌。

MediaMTX 要求 RTP 为偶数、RTCP 等于 RTP 加 1。原配置 `34103/34104` 不符合要求，现已修正；`start-local.sh --check` 和正常启动都会先校验这两个条件，错误时会在编译及启动前退出。

本机缺少的 MediaMTX 可执行文件由脚本从 `/data/nfs_storage/hxjm/mtx/mediamtx/mediamtx` 复用，启动的是本目录独立进程。视频直接从数据库中登记的摄像头拉取，个人流不重复录像。

公共算法接口默认 `http://127.0.0.1:28010`。2026-11-03 本次启动验收时 `/health` 返回 HTTP 200、`status=ok`、`algorithm=botsort`，网页四路均显示“AI：检测正常”。若主算法之后离线，本目录仍可播放原始视频，但检测框/跟踪结果会离线，需由主算法维护者恢复。不要为了恢复检测框把个人目录改成本地算法模式。

`service.sh` 引用的 `scripts/host-service.py` 在此分支缺失；README 中的 `scripts/start.sh` 也缺失。当前使用已存在并完成预检的 `scripts/start-local.sh`，不直接套用主目录的 `service.sh business ...` 指令。

若改用新建的 Linux 用户 tzh，核对时它属于 sudo 组但不属于 docker 组。可由管理员执行以下命令后重新登录 tzh，再检查 `docker info` 和 `node --version`（要求 18+）：

```bash
sudo usermod -aG docker tzh
```

项目克隆及本次端口文件由 guest 账户创建；切换到 tzh 前还需确认该账户可读写项目目录及 Git 元数据，并能使用 Java 8、Maven 和 Node，不建议使用 sudo 启动整套开发服务。

## 检查与日志

```bash
cd /data/nfs_storage/hxjm-tzh
bash scripts/start-local.sh --check
bash scripts/stop-local.sh --check
tail -n 80 log/local/build-backend.log
tail -n 80 log/local/build-ai-stream.log
tail -n 80 log/local/mediamtx.log
tail -n 80 log/local/backend.log
tail -n 80 log/local/frontend.log
```

`NOTICE: relation ... already exists, skipping` 表示数据库对象已经存在，初始化会跳过，是正常提示。

若 MediaMTX 报 `no space left on device`，先检查磁盘及 inode；它也可能表示 Linux 文件监听数量耗尽。本次复测曾遇到此错误：磁盘剩余空间充足，但 guest 的可见 inotify 监听约 65528 个，接近系统上限 65536；随后独立启动探测及完整重试成功。没有停止其他人的编辑器，也没有修改系统参数。若再次发生，管理员可以执行：

```bash
sudo sysctl -w fs.inotify.max_user_watches=524288
```

此命令临时提高文件监听上限，重启服务器后会恢复；需要长期保留时由管理员写入 `/etc/sysctl.d/`。也可关闭自己不用的 VS Code 工作区，减少监听占用。处理后重新执行启动命令。

2026-11-03 已实际完成 C++/Java 编译及本目录完整启动：前端 `3011`、后端验证码接口 `24180/captchaImage`、媒体 API 均返回 HTTP 200。四路摄像头均通过 FFmpeg 解码；Chrome 打开本目录网页后，四路 WHEP 请求均返回 HTTP 201，视频为 1920×1080，连续两秒观察到播放时间和帧数增长，无页面脚本异常。31 项启动/运行管理回归测试全部通过。浏览器验收记录保存在 `.run/local-runtime/startup-browser.json` 和 `startup-browser.png`。
