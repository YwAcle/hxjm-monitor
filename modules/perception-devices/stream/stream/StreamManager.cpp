#include "StreamManager.h"

#include <sstream>

namespace test {

StreamManager::StreamManager(const GlobalConfig& config) : _config(config) {}

StreamManager::~StreamManager() {
    stopAll();
}

bool StreamManager::startTask(long cameraId, const std::string& taskName, const std::string& inputUrl,
                              const std::string& outputUrl, std::string& error) {
    std::lock_guard<std::mutex> lock(_mutex);
    auto templateIt = _config.taskTemplates.find(taskName);
    if (templateIt == _config.taskTemplates.end()) {
        error = "unknown task template: " + taskName;
        return false;
    }

    auto& session = _sessions[cameraId];
    if (!session) {
        session = std::make_unique<CameraSession>();
        session->camera.streamName = "camera_" + std::to_string(cameraId);
        session->camera.rtspUrl = inputUrl;
        // MediaMTX itself owns the original source path. ai-stream must not republish it.
        session->camera.keepOriginal = false;
    }
    if (session->camera.rtspUrl != inputUrl) {
        error = "camera already has a different input URL";
        return false;
    }

    auto existing = session->tasks.find(taskName);
    if (existing != session->tasks.end()) {
        if (existing->second.pushUrl == outputUrl) return true;
        error = "task already exists with a different output URL";
        return false;
    }

    StreamAiTask task = templateIt->second;
    task.taskName = taskName;
    task.pushUrl = outputUrl;
    session->tasks.emplace(taskName, task);
    if (rebuild(*session, error)) return true;
    session->tasks.erase(taskName);
    if (session->tasks.empty()) _sessions.erase(cameraId);
    return false;
}

bool StreamManager::stopTask(long cameraId, const std::string& taskName, std::string& error) {
    std::lock_guard<std::mutex> lock(_mutex);
    auto sessionIt = _sessions.find(cameraId);
    if (sessionIt == _sessions.end()) return true;
    CameraSession& session = *sessionIt->second;
    auto taskIt = session.tasks.find(taskName);
    if (taskIt == session.tasks.end()) return true;
    session.tasks.erase(taskIt);
    if (session.tasks.empty()) {
        if (session.processor) session.processor->stop();
        _sessions.erase(sessionIt);
        return true;
    }
    return rebuild(session, error);
}

std::string StreamManager::status(long cameraId) const {
    std::lock_guard<std::mutex> lock(_mutex);
    auto it = _sessions.find(cameraId);
    if (it == _sessions.end()) return "{\"cameraId\":" + std::to_string(cameraId) + ",\"active\":false,\"tasks\":[]}";
    std::ostringstream out;
    out << "{\"cameraId\":" << cameraId << ",\"active\":true,\"tasks\":[";
    bool first = true;
    for (const auto& entry : it->second->tasks) {
        if (!first) out << ',';
        first = false;
        out << "\"" << escapeJson(entry.first) << "\"";
    }
    return out.str() + "]}";
}

void StreamManager::stopAll() {
    std::lock_guard<std::mutex> lock(_mutex);
    for (auto& entry : _sessions) {
        if (entry.second->processor) entry.second->processor->stop();
    }
    _sessions.clear();
}

bool StreamManager::rebuild(CameraSession& session, std::string& error) {
    if (session.processor) session.processor->stop();
    session.camera.aiTasks.clear();
    for (const auto& entry : session.tasks) session.camera.aiTasks.push_back(entry.second);
    session.processor = std::make_unique<StreamProcessor>(session.camera, _config.aiConfig, _config.aiTasksIpc);
    if (!session.processor->start()) {
        session.processor.reset();
        error = "failed to start stream processor";
        return false;
    }
    return true;
}

std::string StreamManager::escapeJson(const std::string& value) {
    std::string escaped;
    for (char c : value) {
        if (c == '\\' || c == '\"') escaped += '\\';
        escaped += c;
    }
    return escaped;
}

} // namespace test
