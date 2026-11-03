## 本副本启停

在当前仓库根目录执行 `bash scripts/start.sh`、`bash scripts/stop.sh`；状态用 `bash scripts/start.sh --status`。默认启动本副本前后端、推流、分析和 ReID，配置自动读取 `deploy/config/deployment.local.env`。Agent 单独使用 `Agent/scripts/`。完整说明见 [部署说明](deploy/README.md)。

# HXJM 视频监控系统（v0.2）

稳定运行源码位于 `/data/nfs_storage/hxjm`，录像、图片、待投递成果和模型位于 `/data/nfs_storage/hxjm_datas`。
当前交付本机业务端：前端、Java 后端、MediaMTX、视频输入与录像、BoT-SORT 检测和 ReID 特征服务。
远端 Agent 源码位于 `Agent/`，由 Agent 服务器单独启动，不纳入本机业务端启动入口。

## 开发与部署

个人账号默认只启动前端，连接公共业务与模型服务，不重复加载 GPU 模型：

```bash
cp deploy/config/development.env.example deploy/config/development.local.env
bash scripts/start.sh --config deploy/config/development.local.env --check
bash scripts/start.sh --config deploy/config/development.local.env --build --frontend-port 3104
bash scripts/start.sh --config deploy/config/development.local.env --status
bash scripts/stop.sh --config deploy/config/development.local.env
```

`scripts` 仅有两个入口；环境、公共服务与个人联调由 Docker Compose 管理。
完整部署、GPU 选择、首次空库初始化、远程服务、迁移和回退见 [部署手册](deploy/README.md)。
稳定运行目录 `/data/nfs_storage/hxjm` 保持原部署，本仓库新部署使用独立端口和状态目录。
当前验收状态见 [部署验收记录](deploy/VERIFICATION.md)。

## 模块与设计文档

| 目录 | 内容 |
| --- | --- |
| `Agent` | 远端 Agent 稳定源码与模型；在 Agent 服务器单独启动，见 [Agent 部署说明](Agent/DEPLOYMENT.md) |
| `lanhu` | 监控前端 |
| `SmartMonitor-wangzj` | 管理与监控业务后端 |
| `mtx` | 媒体服务与 C++ 流处理 |
| `python/frame_hub`、`python/video_analysis` | 统一输入、录像、实时检测和可靠成果投递 |
| `python/reid_feature_service` | ReID 特征服务 |
| `deploy`、`scripts` | Compose、镜像、配置、数据初始化与两个启停入口 |
| `docs` | v0.2 需求、架构、数据和接口规格 |

开发规格见 [文档导航](docs/README.md)。其他算法、设备示例及大模型目录保留源码，本次入口不自动启动这些组件。
原 `/home/guest/hxjm-yh` 保留用于代码回退，当前业务端不再依赖其中的项目文件。
其他工作区使用的原公共媒体服务独立维护，本次不切换公共服务或修改其录像路径。
