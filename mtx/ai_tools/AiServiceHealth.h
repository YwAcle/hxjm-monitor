#pragma once

#include <algorithm>
#include <chrono>
#include <iterator>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>

namespace test {

class AiServiceHealth {
public:
    struct Update {
        bool changed;
        int retryDelaySeconds;
    };

    bool isOnline() const {
        std::lock_guard<std::mutex> lock(_mutex);
        return _status == Status::ONLINE;
    }

    // Only one AI thread may probe a given IPC endpoint at a time.
    bool tryAcquireProbe() {
        std::lock_guard<std::mutex> lock(_mutex);
        if (_status == Status::ONLINE || _probeInProgress) return false;
        if (std::chrono::steady_clock::now() < _nextProbeAt) return false;
        _probeInProgress = true;
        return true;
    }

    Update reportOnline() {
        std::lock_guard<std::mutex> lock(_mutex);
        const bool changed = _status != Status::ONLINE;
        _status = Status::ONLINE;
        _probeInProgress = false;
        _backoffIndex = 0;
        _nextProbeAt = std::chrono::steady_clock::time_point{};
        return {changed, 0};
    }

    Update reportOffline() {
        static constexpr int DELAYS[] = {1, 2, 5, 10};
        std::lock_guard<std::mutex> lock(_mutex);
        const bool changed = _status != Status::OFFLINE;
        const size_t index = std::min(_backoffIndex, std::size(DELAYS) - 1);
        const int delay = DELAYS[index];
        if (_backoffIndex + 1 < std::size(DELAYS)) ++_backoffIndex;
        _status = Status::OFFLINE;
        _probeInProgress = false;
        _nextProbeAt = std::chrono::steady_clock::now() + std::chrono::seconds(delay);
        return {changed, delay};
    }

private:
    enum class Status { UNKNOWN, ONLINE, OFFLINE };

    mutable std::mutex _mutex;
    Status _status{Status::UNKNOWN};
    bool _probeInProgress{false};
    size_t _backoffIndex{0};
    std::chrono::steady_clock::time_point _nextProbeAt{};
};

inline std::shared_ptr<AiServiceHealth> getAiServiceHealth(const std::string& endpoint) {
    static std::mutex registryMutex;
    static std::unordered_map<std::string, std::weak_ptr<AiServiceHealth>> registry;

    std::lock_guard<std::mutex> lock(registryMutex);
    auto& weak = registry[endpoint];
    auto health = weak.lock();
    if (!health) {
        health = std::make_shared<AiServiceHealth>();
        weak = health;
    }
    return health;
}

} // namespace test
