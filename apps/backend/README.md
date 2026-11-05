# HXJM 后端装配

本目录保留 hxjm Maven reactor 与唯一 Spring Boot 应用 hxjm-admin。库源码按职责位于 modules/business/java、modules/capability/java 和 modules/infrastructure/java，artifactId 与原业务 API 保持不变。

在仓库根目录构建：

```bash
mvn -f apps/backend/pom.xml -pl hxjm-admin -am package -DskipTests
```

项目使用原有 Java 8 目标字节码；本地检查可用 JDK 11。原 Lombok 与系统 JDK 21 不兼容，本阶段未升级依赖。通过 deploy/containers/backend.Dockerfile 构建统一后端镜像；正式启停使用仓库 scripts/start.sh、scripts/stop.sh。

Capability 模块仍被同一应用扫描并装配，不独立部署。数据库基线和迁移位于 modules/infrastructure/database；历史 SQL 快照只保存在 references/database-snapshots，不自动执行。目录及验证见 ../../docs/refactor/stage-2.md。
