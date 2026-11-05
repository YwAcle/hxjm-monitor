#pragma once

#include "../stream/StreamManager.h"
#include "../utils/Config.h"
#include <atomic>
#include <thread>

namespace test {

class ControlServer {
public:
    ControlServer(StreamManager& manager, const GlobalConfig::ControlConfig& config);
    ~ControlServer();

    bool start();
    void stop();

private:
    void serve();
    void handleClient(int fd);
    bool authorized(const std::string& request) const;
    void respond(int fd, int status, const std::string& body) const;

    StreamManager& _manager;
    GlobalConfig::ControlConfig _config;
    std::atomic<bool> _running{false};
    int _listenFd{-1};
    std::thread _thread;
};

} // namespace test
