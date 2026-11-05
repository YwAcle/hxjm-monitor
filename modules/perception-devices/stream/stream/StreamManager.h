#pragma once

#include "StreamProcessor.h"
#include <map>
#include <memory>
#include <mutex>
#include <string>

namespace test {

// Owns one decoding session per camera and fans its decoded frames to active tasks.
class StreamManager {
public:
    explicit StreamManager(const GlobalConfig& config);
    ~StreamManager();

    bool startTask(long cameraId, const std::string& taskName, const std::string& inputUrl,
                   const std::string& outputUrl, std::string& error);
    bool stopTask(long cameraId, const std::string& taskName, std::string& error);
    std::string status(long cameraId) const;
    void stopAll();

private:
    struct CameraSession {
        CameraConfig camera;
        std::map<std::string, StreamAiTask> tasks;
        std::unique_ptr<StreamProcessor> processor;
    };

    bool rebuild(CameraSession& session, std::string& error);
    static std::string escapeJson(const std::string& value);

    GlobalConfig _config;
    mutable std::mutex _mutex;
    std::map<long, std::unique_ptr<CameraSession>> _sessions;
};

} // namespace test
