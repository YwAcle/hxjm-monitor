#pragma once
#include "../utils/Logger.h"
#include "../utils/Config.h"
#include "../ai_tools/AiFrame.h"
#include "../ai_tools/AiEngine.h"
#include <atomic>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <queue>
#include <memory>
#include <string>
#include <vector>
#include <functional>
#include <unordered_map>
#include <map>

extern "C" {
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/imgutils.h>
#include <libavutil/opt.h>
#include <libavutil/hwcontext.h>
#include <libavutil/pixdesc.h>
#include <libswscale/swscale.h>
}

// FFmpeg 7.0+ 将 profile 常量移到了 defs.h，这里做兼容
#ifndef FF_PROFILE_H264_HIGH
#define FF_PROFILE_H264_HIGH 100
#endif

namespace test {

// 线程安全队列
template<typename T>
class ThreadSafeQueue {
public:
    explicit ThreadSafeQueue(size_t maxSize = 25) : _maxSize(maxSize) {}

    bool push(T item) {
        std::unique_lock<std::mutex> lock(_mutex);
        if (_queue.size() >= _maxSize) {
            _queue.pop();  // 丢弃最旧的帧
        }
        _queue.push(std::move(item));
        _cond.notify_one();
        return true;
    }

    bool pop(T& item, int timeoutMs = 100) {
        std::unique_lock<std::mutex> lock(_mutex);
        if (_cond.wait_for(lock, std::chrono::milliseconds(timeoutMs),
                           [this] { return !_queue.empty(); })) {
            item = std::move(_queue.front());
            _queue.pop();
            return true;
        }
        return false;
    }

    size_t size() const {
        std::lock_guard<std::mutex> lock(_mutex);
        return _queue.size();
    }

private:
    std::queue<T> _queue;
    mutable std::mutex _mutex;
    std::condition_variable _cond;
    size_t _maxSize;
};

// 单个 AI 任务的推流处理器
struct AiTaskProcessor {
    StreamAiTask task;                               // AI 任务配置
    ThreadSafeQueue<AiFramePtr> inputQueue;          // 任务独立的输入队列
    ThreadSafeQueue<AiFramePtr> encodeQueue;         // 编码队列
    std::vector<std::thread> aiThreads;              // AI 处理线程
    std::thread pushThread;                          // 推流线程
    std::atomic<int> frameCounter{0};                // 帧计数器
    
    explicit AiTaskProcessor(const StreamAiTask& t, size_t queueSize = 25) 
        : task(t), inputQueue(queueSize), encodeQueue(queueSize) {}
};

// 原始流推流处理器
struct OriginalStreamProcessor {
    std::string pushUrl;                             // 推流地址
    ThreadSafeQueue<AiFramePtr> encodeQueue;         // 编码队列
    std::thread pushThread;                          // 推流线程
    
    explicit OriginalStreamProcessor(const std::string& url, size_t queueSize = 25)
        : pushUrl(url), encodeQueue(queueSize) {}
};

class StreamProcessor {
public:
    StreamProcessor(const CameraConfig& config, const AiConfig& aiConfig, 
                    const std::map<std::string, std::string>& aiTasksIpc = {})
        : _config(config)
        , _aiConfig(aiConfig)
        , _aiTasksIpc(aiTasksIpc)
        , _running(false)
        , _width(0)
        , _height(0)
        , _inputTimeBase{1, 90000}  // 默认时间基
    {}

    ~StreamProcessor() {
        stop();
    }

    bool start();
    void stop();

private:
    // 拉流 + 解码线程
    void pullAndDecodeThread();
    // AI 处理线程 (为每个 AI 任务)
    void aiProcessThread(int threadId, size_t taskIdx);
    // 编码 + 推流线程 (为每个 AI 任务)
    void encodeAndPushThread(size_t taskIdx);
    // 原始流推流线程
    void originalPushThread();

    // 初始化解码器
    bool initDecoder(AVCodecContext*& decCtx, AVBufferRef*& hwCtx, int codecId);
    // 初始化编码器
    bool initEncoder(AVCodecContext*& encCtx, int width, int height);
    // 初始化推流器
    bool initPusher(AVFormatContext*& fmtCtx, AVStream*& stream, AVCodecContext* encCtx, const std::string& pushUrl);

private:
    CameraConfig _config;
    AiConfig _aiConfig;
    std::map<std::string, std::string> _aiTasksIpc;  // 每个任务的独立 IPC 地址
    std::atomic<bool> _running;
    int _width;
    int _height;
    AVRational _inputTimeBase;  // 输入流的时间基
    std::atomic<uint64_t> _globalFrameIndex{0};  // 全局帧序号

    // 解码队列 (仅用于拉流线程和分发)
    // 每个 AI 任务有自己独立的 inputQueue

    // AI 任务处理器列表
    std::vector<std::unique_ptr<AiTaskProcessor>> _aiProcessors;
    
    // 原始流处理器
    std::unique_ptr<OriginalStreamProcessor> _originalProcessor;

    // 拉流线程
    std::thread _pullThread;
};

} // namespace test
