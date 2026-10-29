# HXJM 视频监控系统（v0.2）

稳定运行源码位于 `/data/nfs_storage/hxjm`，录像、图片、待投递成果和模型位于 `/data/nfs_storage/hxjm_datas`。
当前交付本机业务端：前端、Java 后端、MediaMTX、视频输入与录像、BoT-SORT 检测和 ReID 特征服务。
远端 Agent 源码位于 `Agent/`，由 Agent 服务器单独启动，不纳入本机业务端启动入口。

## 启动与关闭

```bash
# 首次部署或更新源码后：先停止本机业务端，再准备构建。
bash /data/nfs_storage/hxjm/service.sh business stop
bash /data/nfs_storage/hxjm/service.sh business prepare
bash /data/nfs_storage/hxjm/service.sh business start

# 日常检查与关闭
bash /data/nfs_storage/hxjm/service.sh business status
bash /data/nfs_storage/hxjm/service.sh business stop
```

当前页面地址：`http://192.168.109.191:3004/`；后端端口 `18480`，分析服务端口 `28014`，ReID 特征服务端口 `28024`。
当前计算环境继续使用本机既有 Conda、Java、Node、CMake 和 Maven；不复制整套环境到共享存储。
启动复用现有 MySQL、PostgreSQL 和 Redis，不自动创建容器或初始化数据库。
首次准备前尚无运行副本时，可以直接执行 `prepare`，无需先执行 `stop`。

主机配置保存在 `deploy/hosts/<machine-id>/`，凭据文件保持私有访问权限。
构建与实际运行副本放在本机 `~/.local/state/hxjm/<machine-id前12位>/release`，日志在其 `log/local/`，
进程状态在其 `.run/local-runtime/`；共享源码目录不承载运行中的 PID、锁和构建输出。
业务源码在共享主目录修改，运行副本由准备步骤生成，不在运行副本内直接开发。

具体配置、文件布局及迁移验证结果见 [NFS 主目录启动说明](docs/NFS主目录启动说明.md)。

## 模块与设计文档

| 目录 | 内容 |
| --- | --- |
| `Agent` | 远端 Agent 稳定源码与模型；在 Agent 服务器单独启动，见 [Agent 部署说明](Agent/DEPLOYMENT.md) |
| `lanhu` | 监控前端 |
| `SmartMonitor-wangzj` | 管理与监控业务后端 |
| `mtx` | 媒体服务与 C++ 流处理 |
| `python/frame_hub`、`python/video_analysis` | 统一输入、录像、实时检测和可靠成果投递 |
| `python/reid_feature_service` | ReID 特征服务 |
| `deploy/hosts`、`scripts` | 主机配置与启动维护入口 |
| `docs` | v0.2 需求、架构、数据和接口规格 |

开发规格见 [文档导航](docs/README.md)。其他算法、设备示例及大模型目录保留源码，本次入口不自动启动这些组件。
原 `/home/guest/hxjm-yh` 保留用于代码回退，当前业务端不再依赖其中的项目文件。
其他工作区使用的原公共媒体服务独立维护，本次仅切换其录像路径，不迁移其他工作区代码。
# hxjm-monitor
