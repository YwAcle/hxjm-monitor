#pragma once
#include "ShmBuffer.h"
#include "ZeroMQClient.h"
#include "AiFrame.h"
#include "../utils/Logger.h"
#include "../utils/base64.h"
#include <memory>
#include <sstream>
#include <atomic>
#include <chrono>

namespace test {

// 传输模式枚举（与 Config.h 中定义一致）
enum class TransportMode {
    SHM,      // 共享内存模式
    BASE64    // Base64 模式
};

/**
 * AI 引擎 - 统一接口
 * 通过字符串任务名调用，新增任务无需修改 C++ 代码
 */
class AiEngine {
public:
    AiEngine(const std::string& shmName, size_t shmSize,
             const std::string& ipcAddress,
             int timeout = 5000) {
        _shmBuffer = std::make_unique<ShmBuffer>(shmName, shmSize);
        _zeroMqClient = std::make_unique<ZeroMQClient>(ipcAddress, timeout);
    }

    ~AiEngine() = default;

    /**
     * 统一的 AI 处理接口
     * @param taskName 任务名称
     * @param aiFrame 帧数据
     * @param mode 传输模式 (SHM 或 BASE64)
     * @param streamName 流名称 (如 camera_1)
     * @param path 推流路径 (如 live/camera_1_reid)
     * @return 是否成功
     */
    bool process(const std::string& taskName, const AiFramePtr& aiFrame, TransportMode mode, const std::string& streamName = "", const std::string& path = "") {
        if (mode == TransportMode::BASE64) {
            return processBase64(taskName, aiFrame, streamName, path);
        } else {
            return processShm(taskName, aiFrame, streamName, path);
        }
    }

    /**
     * 共享内存模式：发送帧到共享内存，处理后回读结果用于渲染
     */
    bool processShm(const std::string& taskName, const AiFramePtr& aiFrame, const std::string& streamName = "", const std::string& path = "") {
        auto t_total_start = std::chrono::steady_clock::now();
        
        size_t stride = aiFrame->stride ? aiFrame->stride : aiFrame->width * 3;
        size_t len = aiFrame->height * stride;

        // 构建 JSON 消息
        auto t_json_start = std::chrono::steady_clock::now();
        std::ostringstream oss;
        oss << "{\"task\":\"" << taskName << "\","
            << "\"shmName\":\"" << _shmBuffer->name << "\","
            << "\"shmLen\":" << len << ","
            << "\"width\":" << aiFrame->width << ","
            << "\"height\":" << aiFrame->height << ","
            << "\"stride\":" << stride << ","
            << "\"pts\":" << aiFrame->pts << ","
            << "\"frameIndex\":" << aiFrame->frameIndex << ","
            << "\"timestamp\":" << std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::system_clock::now().time_since_epoch()).count();
        if (!streamName.empty()) {
            oss << ",\"streamName\":\"" << streamName << "\"";
        }
        if (!path.empty()) {
            oss << ",\"path\":\"" << path << "\"";
        }
        oss << "}";
        std::string msg = oss.str();
        auto t_json_end = std::chrono::steady_clock::now();
        auto json_duration = std::chrono::duration_cast<std::chrono::microseconds>(t_json_end - t_json_start).count() / 1000.0;

        // 写入共享内存并发送请求
        auto t_sync_start = std::chrono::steady_clock::now();
        if (!syncSendRecvShmData(aiFrame->data.get(), len, msg)) {
            ErrorL << taskName << " processShm failed";
            return false;
        }
        auto t_sync_end = std::chrono::steady_clock::now();
        auto sync_duration = std::chrono::duration_cast<std::chrono::microseconds>(t_sync_end - t_sync_start).count() / 1000.0;
        
        // 回读处理结果
        auto t_read_start = std::chrono::steady_clock::now();
        _shmBuffer->read(aiFrame->data.get(), len);
        auto t_read_end = std::chrono::steady_clock::now();
        auto read_duration = std::chrono::duration_cast<std::chrono::microseconds>(t_read_end - t_read_start).count() / 1000.0;
        
        auto t_total_end = std::chrono::steady_clock::now();
        auto total_duration = std::chrono::duration_cast<std::chrono::microseconds>(t_total_end - t_total_start).count() / 1000.0;
        
        // 如果总时间超过阈值，输出详细日志
        if (total_duration > 50.0 || sync_duration > 50.0) {
            InfoL << "[AI-ENGINE] " << taskName << " processShm: total=" << total_duration << "ms "
                  << "json=" << json_duration << "ms sync=" << sync_duration << "ms read=" << read_duration << "ms "
                  << "(size=" << len << " shm=" << _shmBuffer->name << ")";
        }
        
        return true;
    }

    /**
     * Base64 模式：发送 base64 编码的图像，不回读结果
     */
    bool processBase64(const std::string& taskName, const AiFramePtr& aiFrame, const std::string& streamName = "", const std::string& path = "") {
        size_t stride = aiFrame->stride ? aiFrame->stride : aiFrame->width * 3;
        size_t len = aiFrame->height * stride;

        // Base64 编码图像数据
        std::string img64 = base64::base64_encode(aiFrame->data.get(), len);

        // 构建 JSON 消息
        std::ostringstream oss;
        oss << "{\"task\":\"" << taskName << "\","
            << "\"width\":" << aiFrame->width << ","
            << "\"height\":" << aiFrame->height << ","
            << "\"stride\":" << stride << ","
            << "\"channels\":3,"
            << "\"pts\":" << aiFrame->pts << ","
            << "\"frameIndex\":" << aiFrame->frameIndex << ","
            << "\"timestamp\":" << std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::system_clock::now().time_since_epoch()).count();
        if (!streamName.empty()) {
            oss << ",\"streamName\":\"" << streamName << "\"";
        }
        if (!path.empty()) {
            oss << ",\"path\":\"" << path << "\"";
        }
        oss << ",\"base64\":\"" << img64 << "\"}";
        std::string msg = oss.str();

        // 发送 JSON，不回读结果
        if (!syncSendJsonData(msg)) {
            ErrorL << taskName << " processBase64 failed";
            return false;
        }
        return true;
    }

private:
    bool syncSendRecvShmData(uint8_t* data, size_t len, std::string& jsonMsg) {
        if (!_shmBuffer || !_zeroMqClient) {
            ErrorL << "AiEngine not initialized";
            return false;
        }
        if (len > _shmBuffer->size) {
            ErrorL << "Data size exceeds shared memory size";
            return false;
        }
        
        // 写入共享内存
        auto t_shm_write_start = std::chrono::steady_clock::now();
        _shmBuffer->write(data, len);
        auto t_shm_write_end = std::chrono::steady_clock::now();
        auto shm_write_duration = std::chrono::duration_cast<std::chrono::microseconds>(
            t_shm_write_end - t_shm_write_start).count() / 1000.0;
        
        if (shm_write_duration > 10.0) {
            InfoL << "[SHM-WRITE] took " << shm_write_duration << "ms (size=" << len << ")";
        }
        
        // 发送 JSON 并等待回复
        auto t_zmq_start = std::chrono::steady_clock::now();
        bool result = syncSendJsonData(jsonMsg);
        auto t_zmq_end = std::chrono::steady_clock::now();
        auto zmq_duration = std::chrono::duration_cast<std::chrono::microseconds>(
            t_zmq_end - t_zmq_start).count() / 1000.0;
        
        if (zmq_duration > 50.0) {
            InfoL << "[ZMQ-TOTAL] send+recv took " << zmq_duration << "ms";
        }
        
        return result;
    }

    bool syncSendJsonData(std::string& jsonMsg) {
        _zeroMqClient->send(jsonMsg);
        std::string reply = _zeroMqClient->recv();
        if (reply != "OK") {
            ErrorL << "ZeroMQ reply error: " << reply;
            return false;
        }
        return true;
    }

private:
    std::unique_ptr<ShmBuffer> _shmBuffer;
    std::unique_ptr<ZeroMQClient> _zeroMqClient;
};

} // namespace test
