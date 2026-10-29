#include "utils/Logger.h"
#include "utils/Config.h"
#include "stream/StreamProcessor.h"
#include "stream/StreamManager.h"
#include "control/ControlServer.h"
#include <csignal>
#include <vector>
#include <memory>
#include <thread>
#include <filesystem>
#include <cstdlib>

using namespace test;
namespace fs = std::filesystem;

static std::atomic<bool> g_running{true};

void signalHandler(int sig) {
    InfoL << "Received signal " << sig << ", stopping...";
    g_running = false;
}

// 获取配置文件路径 (优先级: 命令行参数 > 项目根目录 > 当前目录)
std::string getConfigPath(int argc, char* argv[]) {
    // 1. 命令行参数
    if (argc > 1) {
        return argv[1];
    }
    
    // 2. 项目根目录 (编译时注入)
#ifdef PROJECT_SOURCE_DIR
    fs::path projectPath = fs::path(PROJECT_SOURCE_DIR) / "config.yaml";
    if (fs::exists(projectPath)) {
        return projectPath.string();
    }
#endif
    
    // 3. 当前目录
    return "config.yaml";
}

int main(int argc, char* argv[]) {
    // 初始化日志文件（优先使用环境变量，否则使用默认路径）
    const char* logPathEnv = std::getenv("AI_STREAM_LOG_PATH");
    std::string logPath;
    if (logPathEnv && strlen(logPathEnv) > 0) {
        logPath = logPathEnv;
        initLogFile(logPath);
    } else {
        // 默认日志路径：./logs/ai_stream_YYYYMMDD_HHMMSS.log
        initLogFile();
        logPath = "logs/ai_stream_*.log (auto-generated)";
    }
    
    InfoL << "=== AI Stream Processor ===";
    InfoL << "Usage: " << argv[0] << " [config.yaml]";
    InfoL << "Press Ctrl+C to stop";
    InfoL << "Log file: " << logPath;

    // 注册信号处理
    signal(SIGINT, signalHandler);
    signal(SIGTERM, signalHandler);

    // 配置文件路径
    std::string configPath = getConfigPath(argc, argv);
    InfoL << "Config path: " << configPath;

    // 加载配置
    GlobalConfig globalConfig;
    if (!loadConfigFromYaml(configPath, globalConfig)) {
        ErrorL << "Failed to load config from: " << configPath;
        ErrorL << "Refusing to start without a valid dynamic-control configuration";
        return 1;
    }

    // 获取最终的 MediaMTX URL (优先级: 环境变量 > 配置文件 > 默认值)
    std::string mediamtxUrl = getMediaMtxUrl(globalConfig.mediamtxUrl);
    
    // 更新所有摄像头的推流地址
    for (auto& cam : globalConfig.cameras) {
        cam.originalPushUrl = mediamtxUrl + "/" + cam.streamName;
        for (auto& task : cam.aiTasks) {
            // 如果 pushUrl 为空，使用默认格式
            if (task.pushUrl.empty()) {
                task.pushUrl = mediamtxUrl + "/" + cam.streamName + "_" + task.taskName;
            }
        }
    }

    InfoL << "MediaMTX URL: " << mediamtxUrl;
    InfoL << "AI Tasks IPC:";
    for (const auto& ipc : globalConfig.aiTasksIpc) {
        InfoL << "  " << ipc.first << " -> " << ipc.second;
    }
    InfoL << "AI Frame Skip: " << globalConfig.aiConfig.frameSkip;
    InfoL << "AI Thread Num: " << globalConfig.aiConfig.aiThreadNum;
    InfoL << "Cameras loaded: " << globalConfig.cameras.size();

    StreamManager streamManager(globalConfig);
    std::unique_ptr<ControlServer> controlServer;
    if (globalConfig.control.enabled) {
        controlServer = std::make_unique<ControlServer>(streamManager, globalConfig.control);
        if (!controlServer->start()) {
            ErrorL << "Failed to start ai-stream control server";
            return 1;
        }
        InfoL << "Dynamic control enabled; configured cameras are templates and will not be started eagerly";
    }

    // Legacy static processor mode. Dynamic control uses StreamManager instead.
    std::vector<std::unique_ptr<StreamProcessor>> processors;
    for (const auto& cam : globalConfig.cameras) {
        if (globalConfig.control.enabled) break;
        InfoL << "Adding camera: " << cam.streamName;
        InfoL << "  RTSP: " << cam.rtspUrl;
        InfoL << "  Keep Original: " << (cam.keepOriginal ? "yes" : "no");
        if (cam.keepOriginal) {
            InfoL << "  Original Push: " << cam.originalPushUrl;
        }
        for (const auto& task : cam.aiTasks) {
            InfoL << "  AI Task: " << task.taskName << " -> " << task.pushUrl;
        }

        auto processor = std::make_unique<StreamProcessor>(
            cam, globalConfig.aiConfig, globalConfig.aiTasksIpc);
        if (!processor->start()) {
            ErrorL << "Failed to start processor for " << cam.streamName;
            continue;
        }
        processors.push_back(std::move(processor));
    }

    if (processors.empty() && !globalConfig.control.enabled) {
        ErrorL << "No processors started, exiting";
        return 1;
    }

    InfoL << "Started " << processors.size() << " static stream processors";
    InfoL << "Waiting for streams...";

    // 主循环
    while (g_running) {
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }

    InfoL << "Stopping all processors...";
    if (controlServer) controlServer->stop();
    streamManager.stopAll();
    processors.clear();

    InfoL << "=== Shutdown complete ===";
    return 0;
}
