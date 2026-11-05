# 第三阶段进展（2026-11-05）

## 已实施

仍在 `codex/compose-deployment`，沿用前两阶段未提交内容，没有创建分支、暂存、提交、合并或远端操作。

数据库规范与逐域核心表清单见 [database.md](database.md)；机器可读的表归属及源码引用清单位于 `modules/infrastructure/database/table-ownership.json`。

主要问题与改造：

1. 原初始化快照未包含已被 Capability Java 代码使用的 HTTP 后续结构。现在将 agent_json、resource_scope、execution_snapshot、执行 namespace、token/lease 字段与 task_output 直接纳入 0001_current；不再要求手工补跑 006 或创建旧 scope 兼容触发器。
2. 原手写 schema-manifest 只查部分列，且旧版本标记可缺省。改为 hxjm_schema_history：有序版本、SQL 摘要、真实结构指纹。initialize/upgrade/check 走同一迁移来源，既有无版本库拒绝自动收编，已改写迁移及结构漂移都会停止。
3. 新基线移除 9 张确认无正式引用的历史表及 task_attempt.legacy_run_id。历史迁移 SQL 仅存参考区；旧硬编码数据库连接和应用程序、旧全量快照退役。正式 modules 内仅剩两份当前基线 SQL，不再分散在阶段目录和 Java 菜单文件中。
4. 当前基线包括 MySQL 30 张、PostgreSQL 49 张表，均计入各库一张版本表。不同生命周期的任务/尝试、连续结果/按需成果、活动/事件/证据、幂等/投递保持分离。
5. task_output 增加任务/执行尝试的复合外键，阻止把其他任务的 run_id 登记为本任务成果。持续任务 namespace 由 legacy 明确为 runtime；平台任务仍使用已配置 namespace。
6. FaceDatabase 的 6 个 Controller/Service/Mapper/Domain/XML 文件从 Infrastructure 迁入 Business，公开路径及权限字符串保持不变；移除旧编译副本，防止重复装配。
7. 新种子写入管理员角色、用户关联、最小平台配置及已有行为/垃圾成果 Schema；摄像头初始化同步建立管理设备整数编号与分析来源 UUID 的明确映射。不复制历史业务数据，不创建真实设备任务。
8. Docker init 同时复制迁移目录，Compose 只读挂载当前源码；scripts/start.sh 增加 --plan-db、--upgrade-db，避免缓存旧 init 镜像继续执行旧快照。

## 本地数据库重建

原 deployment.local.env 的数据根目录在仓库外，原当前项目容器处于停止状态。本次没有清空、启动或改写该目录中的数据库，也未改该配置或接触稳定部署。

实际新建并重建的是本仓库 `.run/refactor-stage3/db-data/` 下的独立开发数据库：

- Docker 项目：`hxjm-refactor-stage3`。
- MySQL：`hxjm_sm_refactor`，服务端口 3306，仅私有容器网络命名空间可访问。
- PostgreSQL：`hxjm_refactor`，服务端口 5432，仅同一私有命名空间可访问。
- 初始化使用现有示例中的一个摄像头，未访问其 RTSP 地址；不代表真实视频已联通。
- 已逐项核实项目标签、配置文件路径、容器挂载路径和无端口发布，再传入两个完整目标执行 rebuild；没有以模糊通配符或数据库默认配置清理数据。
- 仅复用已有 MySQL、pgvector 与 init 镜像，无下载、全局依赖安装或其他服务启动。配置和随机凭据在忽略目录 `database.local.env`，权限 0600；不提交数据库内容、密码或连接配置。

Docker 默认桥接因宿主缺少 iptables 无法创建，改用 network_mode=none 的新 MySQL 容器私有网络命名空间，PostgreSQL/init 共享该命名空间；未更改宿主网络。NFS 下 Docker 的 root 自动建目录不能 chown，改为当前账号预建数据目录并按当前 UID/GID 运行；未改动仓库外权限。

## 针对性验证

- 实际执行 initialize、精确目标 rebuild、check、重复 upgrade；新库通过版本与结构校验。
- 数据库回归 14 项通过，其中 7 项连接上述真实开发库：结构/归属、种子关系、非空库拒绝初始化、摘要篡改拒绝、结构漂移拒绝、后续迁移及指纹更新、任务成果复合外键。动态探针使用回滚事务，不留下测试业务记录。
- Java 库在现有 JDK 11 下离线 test-compile 通过；主应用与集成检查 40 个源码直接编译、5 个检查通过，包含人脸 Business 新归属及原 HTTP 路径。
- 部署入口和模块布局回归 14 项通过；Compose 两套配置、Shell/Python 语法及 git diff --check 通过。
- 没有运行模型、GPU、真实摄像头、设备控制、全平台性能评估或完整应用启动；数据库通过不代表上述链路验收。

收尾已停止本阶段新建的两个数据库容器，开发库内容保留；未停止其他项目服务。检查日志及当前副本重启配置在忽略目录 `.run/refactor-stage3/`。已有本地开发库可用以下命令重新启动、校验，不会清空：

```bash
# 工作目录：仓库根目录；仅针对本阶段新建的项目。
docker compose --project-name hxjm-refactor-stage3 --env-file .run/refactor-stage3/database.local.env -f .run/refactor-stage3/compose.local.json up -d --wait mysql postgres
docker compose --project-name hxjm-refactor-stage3 --env-file .run/refactor-stage3/database.local.env -f .run/refactor-stage3/compose.local.json run --rm --no-deps init python /opt/init/bootstrap.py check
```

## 后续衔接与限制

原业务数据目录未重建，应用默认配置也未自动切换到本阶段开发库。正式联调前需要明确选择本阶段开发库或另一个经确认的隔离目标，再配置后端/图库/报告连接，并通过现有 API 登记能力与实例；禁止对共享库照搬本次清空命令。

现有图库/人脸 API、旧报告输入仍有正式调用，按实际使用保留，不能将它们描述为已全部迁到新 identity 模型。Capability 与 Business 的持续任务协作写入和业务投影 SQL 也未完全拆开，详见数据库规范的访问边界。设备表及公共协议保留，真实机器狗回报与清理业务由后续阶段实现。

MySQL DDL 和两库整体初始化不具有统一事务回滚能力，部分失败须显式重建已确认的独立开发库。完整后端打包仍受此前离线缺少 Spring Boot Maven 插件限制；本阶段验证的是库编译、应用源码与装配检查，没有宣称产出新的完整发布包。
