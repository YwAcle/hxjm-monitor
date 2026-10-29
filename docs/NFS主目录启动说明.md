# NFS 主目录启动说明（v0.2）

稳定源码目录：`/data/nfs_storage/hxjm`。业务文件和模型目录：`/data/nfs_storage/hxjm_datas`。
原 `/home/guest/hxjm-yh` 保留用于代码回退，正常运行不再引用其中的项目文件。

## 本机启动

```bash
bash /data/nfs_storage/hxjm/service.sh business prepare
bash /data/nfs_storage/hxjm/service.sh business start
bash /data/nfs_storage/hxjm/service.sh business status
bash /data/nfs_storage/hxjm/service.sh business stop
```

首次部署及源码修改后，先停止本机业务端再执行 `prepare`；该步骤同步源码、编译并运行前端测试。
日常启停直接使用 `start` 和 `stop`。`restart` 执行与 `start` 相同的本机重启流程，不重新构建。
启动失败会停止本次启动的不完整业务实例，保留日志。数据库、Redis 和其他工作区服务不由此入口启停。

## 主机配置与运行状态

主机配置放在 `deploy/hosts/<machine-id>/`，目录仅供该部署账户访问。
`host.json` 声明本机启动的业务端角色及环境变量；配套文件保留摄像头、算法、来源映射和服务身份配置。
凭据文件不得提交公共仓库，复制配置时保持原有访问限制。

源码在共享目录维护。构建及实际运行副本位于本机 `~/.local/state/hxjm/<machine-id前12位>/release`，
日志、PID、锁、IPC、临时缓存均在该主机目录，避免多台服务器覆盖运行状态。
不要在运行副本内修改业务源码；修改共享源码后重新执行停止、准备、启动。
配置文件中的主目录引用会在准备时转换为本机运行目录；业务数据路径保持共享存储路径。

## 文件布局与数据

录像保存在 `hxjm_datas/recordings`，图片保存在 `hxjm_datas/images`，上传文件保存在 `hxjm_datas/uploads`，
待投递成果保存在 `hxjm_datas/result-spool`；模型权重保存在 `hxjm_datas/models`。
业务数据库继续使用原有容器与表结构，不初始化空库。历史测试数据不迁移，清理范围必须限定到本业务端。
其他工作区的公共 MediaMTX 继续独立管理，只将其录像根切换到 `hxjm_datas/recordings`。

现有本机 Conda、Java、Node、CMake 及 Maven 环境继续复用。新服务器需要提供自己的计算环境和主机配置。
本次入口只交付本机业务端，不启动远端 Agent，也未验证远端联合部署。

## 本次迁移验证记录

已完成目录切换及本机业务端启动，原代码目录保留。新业务文件写入 `hxjm_datas`，旧测试记录按本业务端范围事务清理；
旧文件在数据目录的 `.before-nfs-migration-*` 中隔离，不复制到新业务路径、不重新投递。
摄像头、流目录、算法实例、成果类型、特征空间及其他工作区的旧录像记录保留。

编译通过；前端 101 项、录像模块 33 项、视频分析 155 项、启停隔离 18 项测试通过。
视频分析模拟测试使用其固定期望的 `deepsort` 环境变量运行；实际部署算法仍是 BoT-SORT。
启动入口另外验证了共享数据路径不被源码路径替换、主机状态隔离及 IPC 路径长度。

四路来源均有新录像和可查询的历史检测结果，录像定位与 HTTP Range 读取、图片上传与读取、报告检索接口通过。
成果及录像投递没有保存错误。新入口停止并重启 6 个本机服务，检查到的其他工作区 18 个服务进程保持运行。

页面加载及免登录历史查询弹窗通过。安装的 Chromium 不支持摄像头 H.264 WebRTC 编码，
媒体服务返回客户端不支持编码，因此本次自动化未验证浏览器实时视频解码和实际叠框效果，不标为通过。
摄像头 2 持续接收视频，但现有时间过滤下检测结果更新稀少，该问题单独标记，未随迁移擅自调整算法逻辑。
观察窗口没有新生成的本地报告内容，报告检索可用不等于新报告生成已验收。
远端 Agent 未操作、未联合验证。

本机完整验收记录位于 `~/.local/state/hxjm/<machine-id前12位>/verification-result.json`，
页面截图位于同目录的 `migration-page.png`。
