# 本轮实施记录（2026-10-30）

这是开发分支的实施记录，不表示已经切换公共部署或完成生产验收。
按用户最新要求收缩验证范围，不继续完整业务、真实 GPU、浏览器及跨服务器验收。

## 已完成的必要检查

| 内容 | 结果 |
|---|---|
| 启停入口行为测试 | 8 项通过：字面量配置、参数覆盖、默认无 GPU、显式 GPU、端口错误及冲突、依赖断开、停止范围 |
| Compose | 公共、个人、隔离组合均可解析；未向个人前端隐式添加模型依赖 |
| 前端 | Node 18 镜像构建、全部 101 项前端测试及 Vite 构建通过；页面及后端代理 HTTP 200 |
| Java、C++、初始化镜像 | 从仓库构建成功；Java 8 后端、C++ 控制服务均实际启动 |
| 非 root 运行 | 前端和 Java 使用数字 UID 运行；修复 Java 日志路径与 Vite 临时配置写入权限问题 |
| 新空库 | 独立 MySQL/PostgreSQL 初始化与表列基线检查通过；重复初始化被拒绝 |
| 能力登记 | 独立后端中跟踪、特征及一台测试摄像头实例登记成功，重复登记成功 |
| 停止隔离 | 两个不同 UID 的前端容器同时运行，停止个人 Compose 前端后，另一前端和原公共分析仍返回 200；这是 UID 模拟，不是真实双账号验收 |
| Python 行为回归 | ReID API 21 项通过，分析业务生命周期 7 项通过；这部分使用只读既有 Python 环境，不替代容器 GPU 验收 |
| ReID 容器依赖 | 干净镜像安装完成，pip check 通过；将解析出的额外 13 项依赖补入锁文件 |
| BoT-SORT 容器依赖 | 已进入 CUDA/Python 依赖安装；按收缩验证范围停止耗时构建，尚未获得完整镜像及 pip check 结果 |

最终收尾还统一了生成的 business.json 与 Compose 的 `HXJM_PIPELINE_TOKEN` 命名，避免分析服务读取不到投递凭据；收尾配置调整仅做语法与静态检查，未重跑整套验收。

## 本机限制与部署状态

- Docker 缺少 `/usr/sbin/iptables`，默认 bridge 网络创建失败。个人开发 host 网络已可运行；新服务器/公共 bridge 部署需要先修复宿主机依赖。本轮未改系统防火墙或重启 Docker。
- 隔离数据库和服务的运行检查采用临时 host 网络容器，不能据此宣称 bridge 部署通过。
- 未启动新的 GPU 模型实例，没有真实推理、显存峰值或模型加载次数测量结果。
- 没有目标迁移服务器，跨服务器部署未验收。
- 当前非 Agent 链路不要求 LLM 配置，本轮没有部署或启动 LLM。
- `/data/nfs_storage/hxjm` 和原有稳定服务未修改、未切换；`apps/llm/scripts` 未修改。
- 本轮创建的临时验收容器、数据库卷与浏览器会话已清理；个人测试前端通过 stop.sh 停止。

## 构建与交付

镜像记录见 [IMAGE_MANIFEST.json](IMAGE_MANIFEST.json)。本机 `v0.2-compose1` 是开发构建标签，部分镜像 revision 标签为 unknown；不是已验收的正式发布。
正式交付请从确定的源码提交使用新的 IMAGE_TAG 重新构建并记录摘要，不能用本轮镜像状态冒充最终发布验证。
BoT-SORT 可通过 `start.sh --scope shared --config <配置> --only analysis --build-only` 继续构建，不启动模型。

本轮日志保存在当前服务器 `/tmp/hxjm-build-*.log`、`/tmp/hxjm-entrypoints-tests.log`、`/tmp/hxjm-analysis-tests.log`、`/tmp/hxjm-reid-tests.log`，不是迁移时必须携带的资源。
私有测试配置仍在仅当前账号可读的 `/tmp/hxjm-compose-validation`，未纳入仓库。
