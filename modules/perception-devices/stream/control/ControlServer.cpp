#include "ControlServer.h"
#include "../utils/Logger.h"
#include "../utils/picojson.h"

#include <arpa/inet.h>
#include <cerrno>
#include <cstring>
#include <netinet/in.h>
#include <sstream>
#include <sys/socket.h>
#include <unistd.h>

namespace test {
namespace {

bool parseRoute(const std::string& path, long& cameraId, std::string& task, bool& collection,
                bool& cameraStatus) {
    const std::string prefix = "/internal/v1/cameras/";
    if (path.rfind(prefix, 0) != 0) return false;
    const std::string rest = path.substr(prefix.size());
    const size_t slash = rest.find('/');
    try { cameraId = std::stol(rest.substr(0, slash)); } catch (...) { return false; }
    if (slash == std::string::npos) {
        collection = false;
        cameraStatus = true;
        return true;
    }
    const std::string marker = "/tasks";
    if (rest.compare(slash, marker.size(), marker) != 0) return false;
    const std::string after = rest.substr(slash + marker.size());
    collection = after.empty();
    cameraStatus = false;
    if (!collection) {
        if (after.size() < 2 || after[0] != '/') return false;
        task = after.substr(1);
    }
    return true;
}

std::string jsonString(const picojson::object& object, const char* name) {
    auto it = object.find(name);
    if (it == object.end() || !it->second.is<std::string>()) return "";
    return it->second.get<std::string>();
}

} // namespace

ControlServer::ControlServer(StreamManager& manager, const GlobalConfig::ControlConfig& config)
    : _manager(manager), _config(config) {}

ControlServer::~ControlServer() { stop(); }

bool ControlServer::start() {
    if (_running.exchange(true)) return true;
    _listenFd = socket(AF_INET, SOCK_STREAM, 0);
    if (_listenFd < 0) { _running = false; return false; }
    int reuse = 1;
    setsockopt(_listenFd, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_port = htons(static_cast<uint16_t>(_config.listenPort));
    if (inet_pton(AF_INET, _config.listenHost.c_str(), &address.sin_addr) != 1 ||
        bind(_listenFd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) != 0 ||
        listen(_listenFd, 32) != 0) {
        close(_listenFd);
        _listenFd = -1;
        _running = false;
        return false;
    }
    _thread = std::thread(&ControlServer::serve, this);
    InfoL << "ai-stream control listening on " << _config.listenHost << ':' << _config.listenPort;
    return true;
}

void ControlServer::stop() {
    if (!_running.exchange(false)) return;
    if (_listenFd >= 0) {
        shutdown(_listenFd, SHUT_RDWR);
        close(_listenFd);
        _listenFd = -1;
    }
    if (_thread.joinable()) _thread.join();
}

void ControlServer::serve() {
    while (_running) {
        const int client = accept(_listenFd, nullptr, nullptr);
        if (client < 0) {
            if (_running && errno != EINTR) WarnL << "ai-stream control accept failed";
            continue;
        }
        handleClient(client);
        close(client);
    }
}

void ControlServer::handleClient(int fd) {
    std::string request;
    char buffer[4096];
    while (request.size() < 65536) {
        const ssize_t n = recv(fd, buffer, sizeof(buffer), 0);
        if (n <= 0) return;
        request.append(buffer, static_cast<size_t>(n));
        const size_t headerEnd = request.find("\r\n\r\n");
        if (headerEnd == std::string::npos) continue;
        size_t contentLength = 0;
        const std::string lengthKey = "Content-Length:";
        const size_t lengthPos = request.find(lengthKey);
        if (lengthPos != std::string::npos) {
            try { contentLength = static_cast<size_t>(std::stoul(request.substr(lengthPos + lengthKey.size()))); } catch (...) { }
        }
        if (request.size() >= headerEnd + 4 + contentLength) break;
    }

    const size_t lineEnd = request.find("\r\n");
    if (lineEnd == std::string::npos) { respond(fd, 400, "{\"error\":\"bad request\"}"); return; }
    std::istringstream line(request.substr(0, lineEnd));
    std::string method, path;
    line >> method >> path;
    if (!authorized(request)) { respond(fd, 401, "{\"error\":\"unauthorized\"}"); return; }

    long cameraId = 0;
    std::string task;
    bool collection = false;
    bool cameraStatus = false;
    if (!parseRoute(path, cameraId, task, collection, cameraStatus)) { respond(fd, 404, "{\"error\":\"not found\"}"); return; }
    if (method == "GET" && cameraStatus) { respond(fd, 200, _manager.status(cameraId)); return; }

    if (method == "POST" && collection) {
        const size_t bodyStart = request.find("\r\n\r\n");
        picojson::value value;
        const std::string parseError = picojson::parse(value, request.substr(bodyStart + 4));
        if (!parseError.empty() || !value.is<picojson::object>()) { respond(fd, 400, "{\"error\":\"invalid json\"}"); return; }
        const picojson::object& body = value.get<picojson::object>();
        task = jsonString(body, "task");
        const std::string inputUrl = jsonString(body, "inputUrl");
        const std::string outputUrl = jsonString(body, "outputUrl");
        std::string error;
        if (task.empty() || inputUrl.empty() || outputUrl.empty() || !_manager.startTask(cameraId, task, inputUrl, outputUrl, error)) {
            respond(fd, 400, "{\"error\":\"" + error + "\"}"); return;
        }
        respond(fd, 200, _manager.status(cameraId)); return;
    }
    if (method == "DELETE" && !collection) {
        std::string error;
        if (!_manager.stopTask(cameraId, task, error)) { respond(fd, 400, "{\"error\":\"" + error + "\"}"); return; }
        respond(fd, 200, _manager.status(cameraId)); return;
    }
    respond(fd, 405, "{\"error\":\"method not allowed\"}");
}

bool ControlServer::authorized(const std::string& request) const {
    if (_config.token.empty()) return true;
    const size_t headersEnd = request.find("\r\n\r\n");
    const std::string headers = request.substr(0, headersEnd);
    const std::string key = "X-Ai-Stream-Token:";
    const size_t keyPos = headers.find(key);
    if (keyPos == std::string::npos) return false;
    const size_t valueStart = keyPos + key.size();
    const size_t valueEnd = headers.find("\r\n", valueStart);
    std::string value = headers.substr(valueStart, valueEnd - valueStart);
    const size_t first = value.find_first_not_of(" \t");
    const size_t last = value.find_last_not_of(" \t");
    if (first == std::string::npos) return false;
    return value.substr(first, last - first + 1) == _config.token;
}

void ControlServer::respond(int fd, int status, const std::string& body) const {
    const char* text = status == 200 ? "OK" : status == 400 ? "Bad Request" : status == 401 ? "Unauthorized" : status == 404 ? "Not Found" : "Method Not Allowed";
    std::ostringstream response;
    response << "HTTP/1.1 " << status << ' ' << text << "\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "
             << body.size() << "\r\n\r\n" << body;
    const std::string payload = response.str();
    send(fd, payload.data(), payload.size(), 0);
}

} // namespace test
