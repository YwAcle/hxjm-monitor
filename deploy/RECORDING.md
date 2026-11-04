# 摄像头原始录像

在副本 deployment.local.env 设置 MEDIA_RECORD_ENABLED=true，准备配置时由 bootstrap 渲染 MediaMTX 录像设置。普通启停沿用 scripts/start.sh、scripts/stop.sh；只有 mediamtx 服务承担录像，无额外模型或算法进程。现有配置修改后重启相应服务生效。

- 文件写入 `${DATA_ROOT}/recordings/live/camera_N/YYYY-MM-DD/HH-MM-SS-ffffff.mp4`。本副本 DATA_ROOT 为 `/data/nfs_storage/hxjm-yh/business-data`。
- 保存原始 H264 压缩流，封装为 fragmented MP4，不重编码；前端绘制的检测框不烧入录像。
- 每小时按关键帧切段，实际边界可能稍有偏差；断流或服务重启也会形成新文件。正在写入的文件不一定具备最终时长。
- 保留 168 小时（7 天），MediaMTX 按录像片段起始时间自动清理过期文件；不是按磁盘容量淘汰。配置时间为 recordDeleteAfter。
- sourceOnDemand=false，开启服务即持续拉流录像，无人观看时也录；停止 mediamtx 停止录像，文件保留。不会补录启用前或停机期间的内容。
- 当前容器使用 UTC，因此目录与文件名时间加 8 小时为北京时间。
- 当前使用文件目录管理，不生成旧 frame_hub 的 manifest、不登记 media_asset，也未接入前端录像列表或开启 HTTP playback。需要业务检索/前端回放时另行接入，不能把已保存文件等同于已完成业务录像管理。

录像容量取决于实际码率：每路 1 Mbps 约 10.8 GB/天，4 路总计 4 Mbps 时保留 7 天约 302 GB。无容量配额或磁盘不足自动淘汰机制。

2026-11-04 北京时间 15:21:54 本副本开启，4 路均实际写出 MP4 并经 PyAV 解码验证，画面 1920×1080。文件由本副本 MediaMTX 管理，不修改摄像头或外部 NVR。
