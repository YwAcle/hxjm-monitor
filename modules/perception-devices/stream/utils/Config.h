#pragma once
#include <vector>
#include <string>
#include <map>
#include <cstdlib>
#include <fstream>
#include <yaml-cpp/yaml.h>
#include "Logger.h"

namespace test {

// 帧跳过模式
enum class FrameSkipMode {
    INTERLEAVED,  // 交叉模式：每 N 帧处理一次 (ABABAB...)
    CONTINUOUS    // 连续模式：前 M 帧处理，后 N-M 帧不处理 (AABB...)
};

// AI 处理配置
struct AiConfig {
    FrameSkipMode frameSkipMode = FrameSkipMode::INTERLEAVED;  // 帧跳过模式
    int frameSkip = 5;           // 交叉模式：每 N 帧处理一次 AI
    int frameSkipAi = 1;         // 连续模式：周期内前 M 帧做 AI
    int frameSkipTotal = 2;      // 连续模式：周期总帧数 N（如 12:25 中 N=25）
    int aiThreadNum = 2;         // AI 处理线程数
    int queueSize = 25;          // 帧队列大小
    int zmqTimeout = 5000;       // ZeroMQ 超时 (ms)
    int maxFrameAgeMs = 700;     // 超过此时长的帧不再推送，0 表示禁用
    
    // 判断当前帧是否需要做 AI 处理
    bool shouldDoAi(int frameCount) const {
        if (frameSkipMode == FrameSkipMode::INTERLEAVED) {
            // 交叉模式：取余
            return (frameCount % frameSkip == 0);
        } else {
            // 连续模式：周期内前 M 帧做 AI
            int posInCycle = frameCount % frameSkipTotal;
            return (posInCycle < frameSkipAi);
        }
    }
};

// AI 任务传输模式
enum class AiTransportMode {
    SHM,      // 共享内存模式：发送帧到共享内存，处理后回读结果用于渲染
    BASE64    // Base64 模式：发送 base64 编码的图像，不回读结果
};

// 单个流的 AI 处理配置
struct StreamAiTask {
    std::string taskName;        // AI 任务名称（字符串，如 "reid", "sam3", "yolo" 等）
    std::string pushUrl;         // 该任务的推流地址
    std::string ipcAddr;         // 该任务的 IPC 地址（可覆盖全局）
    AiConfig aiConfig;           // 该任务的 AI 配置（可覆盖全局）
    AiTransportMode transport = AiTransportMode::SHM;  // 传输模式（默认共享内存）
};

// 摄像头配置
struct CameraConfig {
    std::string rtspUrl;                     // RTSP 拉流地址
    std::string streamName;                  // 流名称 (如 camera_1)
    std::vector<StreamAiTask> aiTasks;       // AI 任务列表
    bool keepOriginal = false;               // 是否保留原始流
    std::string originalPushUrl;             // 原始流推流地址
    bool enabled = true;                     // 是否启用
};

// 全局配置
struct GlobalConfig {
    std::string mediamtxUrl;                          // MediaMTX 服务器地址
    std::map<std::string, std::string> aiTasksIpc;    // 每个 AI 任务的独立 IPC 地址
    AiConfig aiConfig;                                // AI 配置
    std::map<std::string, StreamAiTask> taskTemplates;// 动态任务的默认配置
    std::vector<CameraConfig> cameras;                // 摄像头配置列表
    struct ControlConfig {
        bool enabled = false;
        std::string listenHost = "127.0.0.1";
        int listenPort = 19090;
        std::string token;
    } control;
};

// 从 YAML 文件加载配置
inline bool loadConfigFromYaml(const std::string& yamlPath, GlobalConfig& config) {
    // 辅助函数：解析 AiConfig
    auto parseAiConfig = [](const YAML::Node& node, AiConfig& cfg) {
        // frame_skip_mode: interleaved / continuous
        if (node["frame_skip_mode"]) {
            std::string mode = node["frame_skip_mode"].as<std::string>();
            if (mode == "continuous") {
                cfg.frameSkipMode = FrameSkipMode::CONTINUOUS;
            } else {
                cfg.frameSkipMode = FrameSkipMode::INTERLEAVED;
            }
        }
        // 交叉模式参数
        if (node["frame_skip"]) cfg.frameSkip = node["frame_skip"].as<int>();
        // 连续模式参数: frame_skip_ratio (如 "12:25")
        if (node["frame_skip_ratio"]) {
            std::string ratio = node["frame_skip_ratio"].as<std::string>();
            size_t colonPos = ratio.find(':');
            if (colonPos != std::string::npos) {
                cfg.frameSkipAi = std::stoi(ratio.substr(0, colonPos));
                cfg.frameSkipTotal = std::stoi(ratio.substr(colonPos + 1));
                // 如果指定了 ratio，自动切换到连续模式
                if (!node["frame_skip_mode"]) {
                    cfg.frameSkipMode = FrameSkipMode::CONTINUOUS;
                }
            }
        }
        // 其他参数
        if (node["ai_thread_num"]) cfg.aiThreadNum = node["ai_thread_num"].as<int>();
        if (node["queue_size"]) cfg.queueSize = node["queue_size"].as<int>();
        if (node["zmq_timeout"]) cfg.zmqTimeout = node["zmq_timeout"].as<int>();
        if (node["max_frame_age_ms"]) cfg.maxFrameAgeMs = node["max_frame_age_ms"].as<int>();
    };
    
    try {
        YAML::Node root = YAML::LoadFile(yamlPath);
        
        // mediamtx_url
        if (root["mediamtx_url"]) {
            config.mediamtxUrl = root["mediamtx_url"].as<std::string>();
        }
        
        // ai_tasks_ipc
        if (root["ai_tasks_ipc"]) {
            for (const auto& kv : root["ai_tasks_ipc"]) {
                config.aiTasksIpc[kv.first.as<std::string>()] = kv.second.as<std::string>();
            }
        }
        
        // ai_config
        if (root["ai_config"]) {
            parseAiConfig(root["ai_config"], config.aiConfig);
        }

        // Dynamic mode uses these templates instead of camera-specific YAML tasks.
        if (root["task_templates"]) {
            for (const auto& kv : root["task_templates"]) {
                const std::string taskName = kv.first.as<std::string>();
                const YAML::Node taskNode = kv.second;
                StreamAiTask aiTask;
                aiTask.taskName = taskName;
                aiTask.aiConfig = config.aiConfig;
                if (taskNode["ipc_addr"]) aiTask.ipcAddr = taskNode["ipc_addr"].as<std::string>();
                if (taskNode["push_url"]) aiTask.pushUrl = taskNode["push_url"].as<std::string>();
                parseAiConfig(taskNode, aiTask.aiConfig);
                if (taskNode["transport"]) {
                    aiTask.transport = taskNode["transport"].as<std::string>() == "base64"
                        ? AiTransportMode::BASE64 : AiTransportMode::SHM;
                }
                if (aiTask.ipcAddr.empty()) {
                    auto ipc = config.aiTasksIpc.find(taskName);
                    aiTask.ipcAddr = ipc == config.aiTasksIpc.end() ? "ipc:///tmp/py_ai_" + taskName + ".ipc" : ipc->second;
                }
                config.taskTemplates[taskName] = aiTask;
            }
        }

        if (root["control"]) {
            const YAML::Node node = root["control"];
            if (node["enabled"]) config.control.enabled = node["enabled"].as<bool>();
            if (node["listen_host"]) config.control.listenHost = node["listen_host"].as<std::string>();
            if (node["listen_port"]) config.control.listenPort = node["listen_port"].as<int>();
            if (node["token"]) config.control.token = node["token"].as<std::string>();
        }
        if (const char* host = std::getenv("AI_STREAM_CONTROL_HOST")) config.control.listenHost = host;
        if (const char* port = std::getenv("AI_STREAM_CONTROL_PORT")) config.control.listenPort = std::atoi(port);
        if (const char* token = std::getenv("AI_STREAM_CONTROL_TOKEN")) config.control.token = token;
        
        // streams
        if (root["streams"]) {
            for (const auto& streamNode : root["streams"]) {
                CameraConfig cam;
                
                if (streamNode["name"]) cam.streamName = streamNode["name"].as<std::string>();
                if (streamNode["rtsp_url"]) cam.rtspUrl = streamNode["rtsp_url"].as<std::string>();
                if (streamNode["enabled"]) cam.enabled = streamNode["enabled"].as<bool>();
                if (streamNode["keep_original"]) cam.keepOriginal = streamNode["keep_original"].as<bool>();
                
                cam.originalPushUrl = config.mediamtxUrl + "/" + cam.streamName;
                
                // ai_tasks
                if (streamNode["ai_tasks"]) {
                    for (const auto& taskNode : streamNode["ai_tasks"]) {
                        StreamAiTask aiTask;
                        aiTask.aiConfig = config.aiConfig;  // 默认用全局配置
                        
                        // type (必填)
                        if (!taskNode["type"]) {
                            WarnL << "AI task missing 'type', skipping";
                            continue;
                        }
                        std::string taskName = taskNode["type"].as<std::string>();
                        aiTask.taskName = taskName;
                        
                        // 可选配置
                        if (taskNode["ipc_addr"]) aiTask.ipcAddr = taskNode["ipc_addr"].as<std::string>();
                        if (taskNode["push_url"]) aiTask.pushUrl = taskNode["push_url"].as<std::string>();
                        
                        // 解析任务级别的 AI 配置
                        parseAiConfig(taskNode, aiTask.aiConfig);
                        
                        // transport
                        if (taskNode["transport"]) {
                            std::string t = taskNode["transport"].as<std::string>();
                            aiTask.transport = (t == "base64") ? AiTransportMode::BASE64 : AiTransportMode::SHM;
                        }
                        
                        // 默认推流地址
                        if (aiTask.pushUrl.empty()) {
                            aiTask.pushUrl = config.mediamtxUrl + "/" + cam.streamName + "_" + taskName;
                        }
                        
                        // 默认 IPC 地址
                        if (aiTask.ipcAddr.empty()) {
                            auto it = config.aiTasksIpc.find(taskName);
                            if (it != config.aiTasksIpc.end()) {
                                aiTask.ipcAddr = it->second;
                            } else {
                                aiTask.ipcAddr = "ipc:///tmp/py_ai_" + taskName + ".ipc";
                            }
                        }
                        
                        cam.aiTasks.push_back(aiTask);
                        if (config.taskTemplates.find(taskName) == config.taskTemplates.end()) {
                            config.taskTemplates[taskName] = aiTask;
                        }
                        
                        // 日志输出
                        std::string modeStr = (aiTask.aiConfig.frameSkipMode == FrameSkipMode::CONTINUOUS) 
                            ? "continuous(" + std::to_string(aiTask.aiConfig.frameSkipAi) + ":" + std::to_string(aiTask.aiConfig.frameSkipTotal) + ")"
                            : "interleaved(" + std::to_string(aiTask.aiConfig.frameSkip) + ")";
                        InfoL << "Added AI task: " << taskName 
                              << " -> " << aiTask.pushUrl
                              << " (ipc=" << aiTask.ipcAddr 
                              << ", mode=" << modeStr
                              << ", threads=" << aiTask.aiConfig.aiThreadNum
                              << ", max_frame_age_ms=" << aiTask.aiConfig.maxFrameAgeMs
                              << ", timeout=" << aiTask.aiConfig.zmqTimeout << ")";
                    }
                }
                
                if (!cam.enabled) {
                    InfoL << "Stream " << cam.streamName << " is disabled, skipping";
                    continue;
                }
                
                config.cameras.push_back(cam);
            }
        }
        
        return true;
    } catch (const YAML::Exception& e) {
        ErrorL << "YAML parse error: " << e.what();
        return false;
    }
}

// MediaMTX 推流地址 (优先用环境变量 PUSH_URL_PREFIX)
inline std::string getMediaMtxUrl(const std::string& configUrl = "") {
    const char* env = std::getenv("PUSH_URL_PREFIX");
    if (env && *env) {
        std::string url = env;
        while (!url.empty() && url.back() == '/') {
            url.pop_back();
        }
        return url;
    }
    if (!configUrl.empty()) {
        return configUrl;
    }
    return std::string("rtsp://127.0.0.1:18554/live");
}

} // namespace test
