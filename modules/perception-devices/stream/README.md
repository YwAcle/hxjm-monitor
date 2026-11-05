# C++ 视频推流组件

维护摄像头视频输入、推流、IPC 和现有控制接口。算法 Python 源码不在此目录复制；正式运行时及模型 Adapter 位于 modules/perception-devices/python，第三方实现位于同模块 vendor。

正式部署由仓库 deploy/compose.yml 的 stream 服务装配，镜像入口为 deploy/containers/stream.Dockerfile；配置仍由 /config/ai-stream.yml 提供。原 docker/docker-compose.yml 已退役，不能在旧目录另启一套算法容器。

从仓库根目录本地编译（需已有 FFmpeg、ZeroMQ、yaml-cpp 开发依赖）：

```bash
cmake -S modules/perception-devices/stream -B .run/stream-build -DBUILD_TESTING=ON
cmake --build .run/stream-build -j2
ctest --test-dir .run/stream-build --output-on-failure
```

此命令只编译与测试，不连接摄像头或启动推流。业务端启停继续使用 scripts/start.sh、scripts/stop.sh。
