#pragma once
#include <iostream>
#include <sstream>
#include <chrono>
#include <iomanip>
#include <mutex>
#include <fstream>
#include <string>
#include <cstring>
#include <filesystem>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/types.h>

namespace test {

enum LogLevel { LOG_DEBUG, LOG_INFO, LOG_WARN, LOG_ERROR };

inline const char* levelStr(LogLevel level) {
    switch(level) {
        case LOG_DEBUG: return "D";
        case LOG_INFO:  return "I";
        case LOG_WARN:  return "W";
        case LOG_ERROR: return "E";
    }
    return "?";
}

inline std::string currentTime() {
    auto now = std::chrono::system_clock::now();
    auto t = std::chrono::system_clock::to_time_t(now);
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()) % 1000;
    std::stringstream ss;
    ss << std::put_time(std::localtime(&t), "%Y-%m-%d %H:%M:%S");
    ss << '.' << std::setfill('0') << std::setw(3) << ms.count();
    return ss.str();
}

// 日志文件管理器（单例）
class LogFileManager {
public:
    static LogFileManager& getInstance() {
        static LogFileManager instance;
        return instance;
    }
    
    void setLogFile(const std::string& logPath) {
        std::lock_guard<std::mutex> lock(_mtx);
        if (_logFile.is_open()) {
            _logFile.close();
        }
        
        // 创建目录（如果不存在）
        try {
            std::filesystem::path logFilePath(logPath);
            std::filesystem::path logDir = logFilePath.parent_path();
            if (!logDir.empty() && !std::filesystem::exists(logDir)) {
                std::filesystem::create_directories(logDir);
            }
        } catch (const std::exception& e) {
            std::cerr << "Failed to create log directory: " << e.what() << std::endl;
        }
        
        _logFile.open(logPath, std::ios::app);
        if (!_logFile.is_open()) {
            std::cerr << "Failed to open log file: " << logPath << std::endl;
        } else {
            _logPath = logPath;
            std::cout << "Log file opened: " << logPath << std::endl;
        }
    }
    
    void write(const std::string& msg) {
        std::lock_guard<std::mutex> lock(_mtx);
        if (_logFile.is_open()) {
            _logFile << msg << std::endl;
            _logFile.flush();  // 立即刷新，确保日志及时写入
        }
    }
    
    ~LogFileManager() {
        if (_logFile.is_open()) {
            _logFile.close();
        }
    }
    
private:
    LogFileManager() = default;
    LogFileManager(const LogFileManager&) = delete;
    LogFileManager& operator=(const LogFileManager&) = delete;
    
    std::ofstream _logFile;
    std::mutex _mtx;
    std::string _logPath;
};

// 初始化日志文件（在程序启动时调用）
inline void initLogFile(const std::string& logPath = "") {
    if (logPath.empty()) {
        // 默认日志路径：./logs/ai_stream_YYYYMMDD_HHMMSS.log
        auto now = std::chrono::system_clock::now();
        auto t = std::chrono::system_clock::to_time_t(now);
        std::stringstream ss;
        ss << std::put_time(std::localtime(&t), "logs/ai_stream_%Y%m%d_%H%M%S.log");
        LogFileManager::getInstance().setLogFile(ss.str());
    } else {
        LogFileManager::getInstance().setLogFile(logPath);
    }
}

class LogStream {
public:
    LogStream(LogLevel level, const char* file, int line)
        : _level(level) {
        // 只保留文件名，不包含路径
        const char* filename = strrchr(file, '/');
        filename = filename ? filename + 1 : file;
        _ss << currentTime() << " " << levelStr(level) << " [" << filename << ":" << line << "] ";
    }
    ~LogStream() {
        static std::mutex mtx;
        std::lock_guard<std::mutex> lock(mtx);
        std::string msg = _ss.str();
        
        // 同时输出到控制台和文件
        std::cout << msg << std::endl;
        LogFileManager::getInstance().write(msg);
    }
    template<typename T>
    LogStream& operator<<(const T& v) { _ss << v; return *this; }
private:
    LogLevel _level;
    std::stringstream _ss;
};

#define LOG_D test::LogStream(test::LOG_DEBUG, __FILE__, __LINE__)
#define LOG_I test::LogStream(test::LOG_INFO, __FILE__, __LINE__)
#define LOG_W test::LogStream(test::LOG_WARN, __FILE__, __LINE__)
#define LOG_E test::LogStream(test::LOG_ERROR, __FILE__, __LINE__)

// 兼容原有代码的宏
#define InfoL  LOG_I
#define WarnL  LOG_W
#define ErrorL LOG_E
#define DebugL LOG_D

} // namespace test
