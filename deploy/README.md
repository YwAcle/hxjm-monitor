# 本机非 Agent 服务启停

在仓库根目录使用现有入口：

```bash
bash scripts/start.sh
bash scripts/start.sh --status
bash scripts/stop.sh
```

默认 local 范围启动前端、Java 后端、MediaMTX、C++ 推流控制、视频分析、ReID，以及本副本的 MySQL、PostgreSQL、Redis。Agent 与报告服务由 `apps/llm/scripts/` 单独管理，不由这两个入口启动。

## 当前副本

自动读取 `deploy/config/deployment.local.env`（不提交凭据）。本机页面地址及端口见该配置。运行配置位于 `hxjm-yh/.runtime/business`，数据位于 `hxjm-yh/business-data`，权重位于 `hxjm-yh/models`。这些路径均不引用其他项目；Docker 镜像和驱动由本机提供，摄像头是业务输入。

视频分析、ReID 的配置端口已有监听且不属于本 Compose 项目时直接复用，否则启动本项目容器；普通服务冲突报错。停止只停止本项目选中的应用容器，保留数据库及数据，复用的服务不受影响。当前副本使用独立算法端口，不复用其他项目算法。

## 首次准备和更新

新环境参考 `deploy/config/deployment.env.example` 填写数据库凭据、摄像头路径、权重目录和 GPU UUID。配置是字面量 KEY=VALUE，不执行 shell。摄像头、密码、token 和生成配置不要提交。

```bash
bash scripts/start.sh --render
bash scripts/start.sh --init-db   # 仅用于本副本的全新空库，已有数据拒绝初始化
bash scripts/start.sh --only frontend,backend,stream --build-only
bash scripts/start.sh --only backend,mediamtx,stream,frontend
bash scripts/start.sh --register
bash scripts/start.sh
```

构建默认串行，容器有内存、CPU 和进程数限制。分析、ReID 端口空闲需要本地启动时，必须提供其权重、CUDA 依赖和可用 GPU；不会静默改用其他项目环境或假装已运行。标准算法镜像构建使用 `deploy/containers/python.Dockerfile` 与锁文件，配置中的 ANALYSIS_IMAGE、REID_IMAGE 可指定本机已准备的依赖镜像；当前源码在容器内挂载使用。

源码更新后按需 `--only frontend,backend,stream --build-only`，再通过 stop/start 重启对应服务。`--only` 可选 frontend,backend,mediamtx,stream,analysis,reid,garbage-analysis；`--check` 只检查，不启动。dev 是可选前端开发范围；isolated/shared 为显式部署范围，不是默认入口。

端口和容器健康不证明实际算法功能，须另验视频输入、模型推理和成果登记。大模型运行在另一台服务器，非 Agent 启动无需任何模型 API Key。

## 模块目录迁移

源码已切换为 modules/access/web、apps/backend 与 modules/*/java、modules/perception-devices/python/vendor/stream。Compose 开发挂载与 Docker COPY 已同步调整，统一入口仍是 scripts/start.sh、scripts/stop.sh。首次使用迁移后的源码需要重建对应镜像；仅运行旧镜像不会加载新 Java 模块。

init 镜像的源码维护位置是 modules/infrastructure/database/bootstrap，容器入口仍为 /opt/init/bootstrap.py。Agent/报告的独立入口为 apps/llm/scripts。历史 mtx/docker、Java 内部 Docker/Conda 启动器和 service.sh 已退役。目录与本地检查范围见 ../docs/refactor/stage-2.md。


## 数据库唯一入口

当前正式 SQL 仅维护于 `modules/infrastructure/database/migrations/`；`bootstrap/bootstrap.py` 统一提供 plan、initialize、upgrade、check、rebuild。init 镜像同时复制 bootstrap 和 migrations；Compose 也只读挂载当前源码，避免缓存旧镜像执行旧基线。分发独立镜像时仍须重建。

已有 `hxjm_schema_history` 的库使用 `bash scripts/start.sh --upgrade-db` 升级，`--check-db` 核验，`--plan-db` 输出版本摘要。旧阶段快照库不自动接管；初始化只接受空库。显式重建需要独立本地环境标识及两个精确连接目标，操作方法与表归属见 [数据库规范](../docs/refactor/database.md)。第三阶段的独立本地开发库详情见 [阶段记录](../docs/refactor/stage-3.md)，它与本文件“当前副本”的原数据目录分开。

主 analysis 固定 BoT-SORT；垃圾检测使用独立 garbage-analysis。JoyAI/Qwen 通过 `scripts/joyai-tool.sh` 独立运行并进入同一主监控告警体系；四路来源、服务授权、模型准备与启动命令见 [整合说明](../docs/refactor/monitor-device-integration.md)。
