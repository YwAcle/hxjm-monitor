# HXJM v0.2 设备持久化增量（005）

005在既有PostgreSQL业务库中增加四张设备表、三处可空关联字段及七用途约束，登记behavior.assessment/1和garbage.detection/1。不创建虚构设备、模型实例或任务，不改变原有主键或数据；设备接口和运行期适配仍需另行实现。

2026-10-29已完成隔离验证和当前业务库应用。详见共享docs数据库说明文档12.9、deploy/database-reports/005-verify.json和005-apply.json；同目录保留应用前纯结构备份。备份不包含业务行数据，迁移事务对原有数据摘要进行核对。

## 执行环境与命令

需要PyYAML、psycopg2，以及现有PostgreSQL容器内的pg_dump/psql。当前可用解释器为/home/guest/anaconda3/envs/reid/bin/python。脚本从本项目application-druid.yml读取连接且不打印凭据；要求其仍指向localhost:5432/postgres。不会启动、重启或停止服务，不连接MySQL。

在/data/nfs_storage/hxjm运行：

```bash
/home/guest/anaconda3/envs/reid/bin/python -B python/base/postgresql/stage3/validate.py inspect
```

inspect只读库结构。下列两条是首次应用的顺序，当前业务库已经完成，不必再次执行：

```bash
/home/guest/anaconda3/envs/reid/bin/python -B python/base/postgresql/stage3/validate.py verify
/home/guest/anaconda3/envs/reid/bin/python -B python/base/postgresql/stage3/validate.py apply
```

verify通过Docker读取现有容器纯结构，在同一PostgreSQL实例创建唯一命名的临时隔离库，验证后删除；不复制业务数据。验证全部字段／类型／可空性、约束和索引，并覆盖唯一键、引用保护、旧约束异名、七用途、四类行为判断、任务到产物关系及事务回滚。verify仅适用于005尚未应用的业务库结构。

apply要求同一SQL的隔离验证报告，在迁移事务锁内对比原表记录摘要，全部通过后一次提交，失败回滚。原SQL不做忽略错误的重复建表；脚本发现四表完整存在时检查结构和结果定义并返回already_applied，部分存在则停止，不自动覆盖或补猜缺失设计。

## 实施边界

数据库约束不会代替设备权限、JSON业务关联、乱序反馈状态机、精确七天期限或文件读取服务。当前未验证真实设备、Agent或新增HTTP接口；后续开发必须按共享docs接口契约接入。跨文件系统的文件写入与数据库登记仍按已定分步确认规则执行。
