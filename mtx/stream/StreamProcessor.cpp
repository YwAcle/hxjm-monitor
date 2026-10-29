#include <cstdlib>
#include "StreamProcessor.h"
#include <chrono>
#include <cstdlib>

namespace test {

// 静默 FFmpeg 日志回调
static void ffmpegLogCallback(void* ptr, int level, const char* fmt, va_list vl) {
    // 只输出错误级别以上的日志，忽略警告和信息
    // 如果要完全静默，可以把 AV_LOG_ERROR 改成 AV_LOG_QUIET
    if (level > AV_LOG_ERROR) {
        return;  // 忽略 warning/info/debug
    }
    // 错误级别的日志也不输出到控制台，而是用我们自己的日志系统
    // 如果想完全静默，直接 return
}

// 设置 FFmpeg 日志级别
static bool g_ffmpegLogInitialized = false;
static void initFFmpegLog() {
    if (!g_ffmpegLogInitialized) {
        av_log_set_callback(ffmpegLogCallback);
        av_log_set_level(AV_LOG_ERROR);  // 只处理错误级别
        g_ffmpegLogInitialized = true;
    }
}

bool StreamProcessor::start() {
    if (_running) {
        WarnL << "StreamProcessor already running";
        return true;
    }

    _running = true;
    InfoL << "Starting StreamProcessor for " << _config.streamName;

    // 创建 AI 任务处理器
    for (const auto& task : _config.aiTasks) {
        auto processor = std::make_unique<AiTaskProcessor>(task, task.aiConfig.queueSize);
        _aiProcessors.push_back(std::move(processor));
        InfoL << "  AI Task: " << task.taskName << " -> " << task.pushUrl;
    }

    // 创建原始流处理器
    if (_config.keepOriginal) {
        _originalProcessor = std::make_unique<OriginalStreamProcessor>(
            _config.originalPushUrl, _aiConfig.queueSize);
        InfoL << "  Original stream -> " << _config.originalPushUrl;
    }

    // 启动拉流+解码线程
    _pullThread = std::thread(&StreamProcessor::pullAndDecodeThread, this);

    // 为每个 AI 任务启动处理线程
    for (size_t i = 0; i < _aiProcessors.size(); ++i) {
        // AI 处理线程 - 使用任务自己的线程数配置
        for (int t = 0; t < _aiProcessors[i]->task.aiConfig.aiThreadNum; ++t) {
            _aiProcessors[i]->aiThreads.emplace_back(
                &StreamProcessor::aiProcessThread, this, t, i);
        }
        // 推流线程
        _aiProcessors[i]->pushThread = std::thread(
            &StreamProcessor::encodeAndPushThread, this, i);
    }

    // 启动原始流推流线程
    if (_originalProcessor) {
        _originalProcessor->pushThread = std::thread(
            &StreamProcessor::originalPushThread, this);
    }

    InfoL << "StreamProcessor started for " << _config.streamName;
    return true;
}

void StreamProcessor::stop() {
    if (!_running) return;

    InfoL << "Stopping StreamProcessor for " << _config.streamName;
    _running = false;

    if (_pullThread.joinable()) _pullThread.join();

    // 停止所有 AI 任务处理器
    for (auto& processor : _aiProcessors) {
        for (auto& t : processor->aiThreads) {
            if (t.joinable()) t.join();
        }
        if (processor->pushThread.joinable()) processor->pushThread.join();
    }
    _aiProcessors.clear();

    // 停止原始流处理器
    if (_originalProcessor) {
        if (_originalProcessor->pushThread.joinable()) {
            _originalProcessor->pushThread.join();
        }
        _originalProcessor.reset();
    }

    InfoL << "StreamProcessor stopped for " << _config.streamName;
}

bool StreamProcessor::initDecoder(AVCodecContext*& decCtx, AVBufferRef*& hwCtx, int codecId) {
    /// -----------------------------
    /// ① 查找解码器
    /// -----------------------------
    const AVCodec* dec = avcodec_find_decoder((AVCodecID)codecId);
    if (!dec) {
        ErrorL << "Decoder not found for codec: " << codecId;
        return false;
    }

    decCtx = avcodec_alloc_context3(dec);
    if (!decCtx) {
        ErrorL << "alloc dec ctx failed";
        return false;
    }

    /// -----------------------------
    /// ② 尝试硬件解码（跨平台）
    /// -----------------------------
    AVHWDeviceType try_hw[] = {
#if defined(__APPLE__)
        AV_HWDEVICE_TYPE_VIDEOTOOLBOX,   // macOS
#endif
#if defined(__linux__)
        AV_HWDEVICE_TYPE_CUDA,           // NVIDIA
        AV_HWDEVICE_TYPE_VAAPI,          // Intel/AMD
#endif
#if defined(_WIN32)
        AV_HWDEVICE_TYPE_DXVA2,          // Windows
#endif
        AV_HWDEVICE_TYPE_NONE
    };

    AVHWDeviceType selected_hw = AV_HWDEVICE_TYPE_NONE;

    for (int i = 0; try_hw[i] != AV_HWDEVICE_TYPE_NONE; ++i) {
        if (av_hwdevice_ctx_create(&hwCtx, try_hw[i], NULL, NULL, 0) == 0) {
            selected_hw = try_hw[i];
            decCtx->hw_device_ctx = av_buffer_ref(hwCtx);
            InfoL << "Using hardware decoder: " << av_hwdevice_get_type_name(selected_hw);
            break;
        }
    }

    if (selected_hw == AV_HWDEVICE_TYPE_NONE) {
        WarnL << "Hardware decode unavailable, fallback to software decode";
    }

    /// -----------------------------
    /// ③ 打开解码器
    /// -----------------------------
    if (avcodec_open2(decCtx, dec, nullptr) < 0) {
        ErrorL << "open decoder failed";
        avcodec_free_context(&decCtx);
        return false;
    }

    InfoL << "Decoder OK: " << (selected_hw != AV_HWDEVICE_TYPE_NONE 
              ? av_hwdevice_get_type_name(selected_hw) : "software");
    return true;
}

bool StreamProcessor::initEncoder(AVCodecContext*& encCtx, int width, int height) {
    /// -----------------------------
    /// 编码器候选列表（硬件优先）
    /// -----------------------------
    const char* enc_candidates[] = {
#if defined(__APPLE__)
        "h264_videotoolbox",   // macOS
#endif
        "h264_nvenc",          // NVIDIA GPU
        "h264_vaapi",          // Intel/AMD (Linux VAAPI)
        "h264_qsv",            // Intel Quick Sync
        "libx264",             // 软件编码 (x264)
        "libopenh264",         // 软件编码 (OpenH264)
        nullptr                // 哨兵值，后续尝试通用 H264
    };

    const AVCodec* enc = nullptr;

    /// -----------------------------
    /// 循环尝试每个编码器
    /// -----------------------------
    for (int i = 0; enc_candidates[i] || !enc; ++i) {
        // 先尝试候选列表，然后尝试通用 H264
        if (enc_candidates[i]) {
            enc = avcodec_find_encoder_by_name(enc_candidates[i]);
        } else {
            enc = avcodec_find_encoder(AV_CODEC_ID_H264);
        }
        if (!enc) continue;

        std::string name = enc->name;
        InfoL << "Trying encoder: " << name;

        AVCodecContext* ctx = avcodec_alloc_context3(enc);
        if (!ctx) continue;

        /// -----------------------------
        /// 基础参数
        /// -----------------------------
        ctx->width        = width;
        ctx->height       = height;
        ctx->time_base    = AVRational{1, 90000};
        ctx->framerate    = {25, 1};
        ctx->gop_size     = 25;           // 1秒一个I帧
        ctx->max_b_frames = 0;            // 禁用B帧
        ctx->bit_rate     = 5000000;      // 5Mbps

        /// -----------------------------
        /// 像素格式（NV12优先）
        /// -----------------------------
        AVPixelFormat target_fmt = AV_PIX_FMT_YUV420P;
        if (enc->pix_fmts) {
            for (const AVPixelFormat* p = enc->pix_fmts; *p != AV_PIX_FMT_NONE; ++p) {
                if (*p == AV_PIX_FMT_NV12) {
                    target_fmt = AV_PIX_FMT_NV12;
                    break;
                }
            }
        }
        ctx->pix_fmt = target_fmt;

        /// -----------------------------
        /// 颜色参数
        /// -----------------------------
        ctx->color_range     = AVCOL_RANGE_JPEG;    // FULL RANGE
        ctx->color_primaries = AVCOL_PRI_BT709;
        ctx->color_trc       = AVCOL_TRC_BT709;
        ctx->colorspace      = AVCOL_SPC_BT709;

        /// -----------------------------
        /// 针对不同编码器的低延迟优化
        /// -----------------------------
        if (name.find("libx264") != std::string::npos) {
            av_opt_set(ctx->priv_data, "preset", "ultrafast", 0);
            av_opt_set(ctx->priv_data, "tune", "zerolatency", 0);
            av_opt_set(ctx->priv_data, "scenecut", "0", 0);
            av_opt_set(ctx->priv_data, "rc-lookahead", "0", 0);
            ctx->profile = FF_PROFILE_H264_HIGH;
        }

        if (name.find("nvenc") != std::string::npos) {
            av_opt_set(ctx->priv_data, "preset", "p1", 0);        // p1最快
            av_opt_set(ctx->priv_data, "tune", "ll", 0);          // low-latency
            av_opt_set(ctx->priv_data, "rc-lookahead", "0", 0);
            av_opt_set(ctx->priv_data, "delay", "0", 0);
            av_opt_set(ctx->priv_data, "rc", "cbr", 0);
            ctx->profile = FF_PROFILE_H264_HIGH;
        }

#if defined(__APPLE__)
        if (name.find("videotoolbox") != std::string::npos) {
            av_opt_set(ctx->priv_data, "realtime", "1", 0);
            av_opt_set(ctx->priv_data, "allow_sw", "0", 0);
            ctx->profile = FF_PROFILE_H264_HIGH;
        }
#endif

        if (name.find("vaapi") != std::string::npos) {
            ctx->profile = FF_PROFILE_H264_HIGH;
        }

        /// -----------------------------
        /// 设置全局头标志 (RTSP 推流必需)
        /// -----------------------------
        ctx->flags |= AV_CODEC_FLAG_GLOBAL_HEADER;

        /// -----------------------------
        /// 尝试打开编码器
        /// -----------------------------
        if (avcodec_open2(ctx, enc, nullptr) == 0) {
            encCtx = ctx;
            InfoL << "Encoder OK: " << name 
                  << " fmt=" << av_get_pix_fmt_name(ctx->pix_fmt)
                  << " " << width << "x" << height;
            return true;
        }

        // 打开失败，释放并尝试下一个
        WarnL << "Encoder " << name << " found but failed to open, trying next...";
        avcodec_free_context(&ctx);
    }

    ErrorL << "No working H264 encoder found";
    return false;
}

bool StreamProcessor::initPusher(AVFormatContext*& fmtCtx, AVStream*& stream, AVCodecContext* encCtx, const std::string& pushUrl) {
    char errBuf[256];
    int ret = avformat_alloc_output_context2(&fmtCtx, nullptr, "rtsp", pushUrl.c_str());
    if (ret < 0 || !fmtCtx) {
        av_strerror(ret, errBuf, sizeof(errBuf));
        ErrorL << "alloc output context failed: " << errBuf;
        return false;
    }

    stream = avformat_new_stream(fmtCtx, nullptr);
    if (!stream) {
        ErrorL << "alloc output stream failed";
        avformat_free_context(fmtCtx);
        fmtCtx = nullptr;
        return false;
    }

    avcodec_parameters_from_context(stream->codecpar, encCtx);
    stream->time_base = encCtx->time_base;

    // 设置 RTSP 选项
    AVDictionary* opts = nullptr;
    av_dict_set(&opts, "rtsp_transport", "udp", 0);
    av_dict_set(&opts, "timeout", "5000000", 0);  // 5s timeout

    // 打开输出
    InfoL << "Connecting to RTSP server: " << pushUrl;
    if (!(fmtCtx->oformat->flags & AVFMT_NOFILE)) {
        ret = avio_open2(&fmtCtx->pb, pushUrl.c_str(), AVIO_FLAG_WRITE, nullptr, &opts);
        if (ret < 0) {
            av_strerror(ret, errBuf, sizeof(errBuf));
            ErrorL << "avio_open failed for " << pushUrl << ": " << errBuf;
            av_dict_free(&opts);
            avformat_free_context(fmtCtx);
            fmtCtx = nullptr;
            return false;
        }
    }

    ret = avformat_write_header(fmtCtx, &opts);
    av_dict_free(&opts);
    if (ret < 0) {
        av_strerror(ret, errBuf, sizeof(errBuf));
        ErrorL << "write header failed for " << pushUrl << ": " << errBuf;
        if (fmtCtx->pb) avio_closep(&fmtCtx->pb);
        avformat_free_context(fmtCtx);
        fmtCtx = nullptr;
        return false;
    }

    InfoL << "Pusher initialized: " << pushUrl;
    return true;
}

void StreamProcessor::pullAndDecodeThread() {
    // 初始化 FFmpeg 日志（静默警告）
    initFFmpegLog();
    
    InfoL << "Pull thread started for " << _config.rtspUrl;

    // 重连策略配置
    const int RECONNECT_INTERVAL = 30;     // 重连间隔 30 秒
    const int MAX_RETRY_COUNT = 20;        // 最大重试次数 (30s * 20 = 10分钟)
    int retryCount = 0;

    while (_running) {
        AVFormatContext* fmtCtx = nullptr;
        AVCodecContext* decCtx = nullptr;
        AVBufferRef* hwCtx = nullptr;
        SwsContext* swsCtx = nullptr;
        AVPacket* pkt = nullptr;
        AVFrame* frame = nullptr;
        AVFrame* swFrame = nullptr;
        int videoStreamIdx = -1;
        bool needReconnect = false;

        // 打开输入流
        AVDictionary* opts = nullptr;
        av_dict_set(&opts, "rtsp_transport", "udp", 0);
        av_dict_set(&opts, "stimeout", "5000000", 0);  // 5s timeout
        av_dict_set(&opts, "reconnect", "1", 0);
        av_dict_set(&opts, "reconnect_streamed", "1", 0);
        av_dict_set(&opts, "reconnect_delay_max", "5", 0);

        int ret = avformat_open_input(&fmtCtx, _config.rtspUrl.c_str(), nullptr, &opts);
        av_dict_free(&opts);
        if (ret < 0) {
            retryCount++;
            char errBuf[256];
            av_strerror(ret, errBuf, sizeof(errBuf));
            WarnL << "[" << _config.streamName << "] Failed to open stream (" 
                  << retryCount << "/" << MAX_RETRY_COUNT << "): " << errBuf;
            goto reconnect;
        }

        if (avformat_find_stream_info(fmtCtx, nullptr) < 0) {
            retryCount++;
            WarnL << "[" << _config.streamName << "] Failed to find stream info (" 
                  << retryCount << "/" << MAX_RETRY_COUNT << ")";
            goto cleanup;
        }

        // 找视频流
        for (unsigned i = 0; i < fmtCtx->nb_streams; ++i) {
            if (fmtCtx->streams[i]->codecpar->codec_type == AVMEDIA_TYPE_VIDEO) {
                videoStreamIdx = i;
                break;
            }
        }
        if (videoStreamIdx < 0) {
            retryCount++;
            WarnL << "[" << _config.streamName << "] No video stream found (" 
                  << retryCount << "/" << MAX_RETRY_COUNT << ")";
            goto cleanup;
        }

        {
            AVCodecParameters* codecpar = fmtCtx->streams[videoStreamIdx]->codecpar;
            _width = codecpar->width;
            _height = codecpar->height;
            _inputTimeBase = fmtCtx->streams[videoStreamIdx]->time_base;  // 保存输入时间基

            if (!initDecoder(decCtx, hwCtx, codecpar->codec_id)) {
                retryCount++;
                goto cleanup;
            }
        }

        // 连接成功
        if (retryCount > 0) {
            InfoL << "[" << _config.streamName << "] Reconnected successfully after " 
                  << retryCount << " retries";
        }
        InfoL << "[" << _config.streamName << "] Stream opened: " << _width << "x" << _height;
        retryCount = 0;  // 重置重试计数
        _globalFrameIndex = 0;  // 重置帧序号，避免旧帧干扰

        pkt = av_packet_alloc();
        frame = av_frame_alloc();
        swFrame = av_frame_alloc();

        // 读帧循环
        while (_running) {
            // ① 网络读取
            auto t_read_start = std::chrono::steady_clock::now();
            ret = av_read_frame(fmtCtx, pkt);
            auto t_read_end = std::chrono::steady_clock::now();
            auto read_duration = std::chrono::duration_cast<std::chrono::milliseconds>(
                t_read_end - t_read_start).count();
            
            if (read_duration > 100) {
                WarnL << "[PULL] av_read_frame took " << read_duration << "ms (NETWORK SLOW!)";
            }
            
            if (ret < 0) {
                if (ret == AVERROR(EAGAIN)) {
                    std::this_thread::sleep_for(std::chrono::milliseconds(10));
                    continue;
                }
                // 流断开，需要重连
                WarnL << "[" << _config.streamName << "] Stream disconnected, will reconnect";
                needReconnect = true;
                break;
            }

            if (pkt->stream_index != videoStreamIdx) {
                av_packet_unref(pkt);
                continue;
            }

            // ② 发送到解码器
            auto t_send_start = std::chrono::steady_clock::now();
            ret = avcodec_send_packet(decCtx, pkt);
            auto t_send_end = std::chrono::steady_clock::now();
            auto send_duration = std::chrono::duration_cast<std::chrono::milliseconds>(
                t_send_end - t_send_start).count();
            
            av_packet_unref(pkt);
            
            if (send_duration > 50) {
                WarnL << "[PULL] avcodec_send_packet took " << send_duration << "ms (DECODER SLOW!)";
            }
            
            if (ret < 0) {
                if (ret == AVERROR(EAGAIN)) continue;
                needReconnect = true;
                break;
            }

            while (ret >= 0) {
                // ③ 从解码器接收
                auto t_recv_start = std::chrono::steady_clock::now();
                ret = avcodec_receive_frame(decCtx, frame);
                auto t_recv_end = std::chrono::steady_clock::now();
                auto recv_duration = std::chrono::duration_cast<std::chrono::milliseconds>(
                    t_recv_end - t_recv_start).count();
                
                if (recv_duration > 50) {
                    WarnL << "[PULL] avcodec_receive_frame took " << recv_duration << "ms";
                }
                
                if (ret == AVERROR(EAGAIN) || ret == AVERROR_EOF) break;
                if (ret < 0) {
                    needReconnect = true;
                    break;
                }

                // ④ 硬件帧转 CPU
                AVFrame* srcFrame = frame;
                const AVPixFmtDescriptor* desc = av_pix_fmt_desc_get((AVPixelFormat)frame->format);
                if (desc && (desc->flags & AV_PIX_FMT_FLAG_HWACCEL) && frame->hw_frames_ctx) {
                    auto t_hw_start = std::chrono::steady_clock::now();
                    if (av_hwframe_transfer_data(swFrame, frame, 0) == 0) {
                        srcFrame = swFrame;
                    }
                    auto t_hw_end = std::chrono::steady_clock::now();
                    auto hw_duration = std::chrono::duration_cast<std::chrono::milliseconds>(
                        t_hw_end - t_hw_start).count();
                    if (hw_duration > 20) {
                        WarnL << "[PULL] av_hwframe_transfer_data took " << hw_duration << "ms (HW2CPU SLOW!)";
                    }
                }

                // ⑤ 转换为 RGB
                int rgbStride = _width * 3;
                if (!swsCtx) {
                    AVPixelFormat srcFmt = (AVPixelFormat)srcFrame->format;
                    if (srcFmt == AV_PIX_FMT_YUVJ420P) srcFmt = AV_PIX_FMT_YUV420P;
                    swsCtx = sws_getContext(
                        srcFrame->width, srcFrame->height, srcFmt,
                        _width, _height, AV_PIX_FMT_RGB24,
                        SWS_FAST_BILINEAR, nullptr, nullptr, nullptr);
                }

                auto aiFrame = std::make_shared<AiFrame>();
                aiFrame->width = _width;
                aiFrame->height = _height;
                aiFrame->stride = rgbStride;
                aiFrame->pts = frame->pts;
                aiFrame->frameIndex = _globalFrameIndex.fetch_add(1);  // 分配递增帧序号
                aiFrame->rgbFormat = AV_PIX_FMT_RGB24;
                aiFrame->data = std::shared_ptr<uint8_t>(
                    new uint8_t[rgbStride * _height], std::default_delete<uint8_t[]>());

                uint8_t* dstPlanes[4] = {aiFrame->data.get(), nullptr, nullptr, nullptr};
                int dstStrides[4] = {rgbStride, 0, 0, 0};
                
                auto t_sws_start = std::chrono::steady_clock::now();
                sws_scale(swsCtx, srcFrame->data, srcFrame->linesize,
                          0, srcFrame->height, dstPlanes, dstStrides);
                auto t_sws_end = std::chrono::steady_clock::now();
                auto sws_duration = std::chrono::duration_cast<std::chrono::milliseconds>(
                    t_sws_end - t_sws_start).count();
                if (sws_duration > 20) {
                    WarnL << "[PULL] sws_scale took " << sws_duration << "ms (RGB CONVERT SLOW!)";
                }

                // ⑥ 分发到每个 AI 任务的独立队列
                auto t_dispatch_start = std::chrono::steady_clock::now();
                for (auto& processor : _aiProcessors) {
                    auto taskFrame = std::make_shared<AiFrame>();
                    taskFrame->width = aiFrame->width;
                    taskFrame->height = aiFrame->height;
                    taskFrame->stride = aiFrame->stride;
                    taskFrame->pts = aiFrame->pts;
                    taskFrame->frameIndex = aiFrame->frameIndex;  // 复制帧序号
                    taskFrame->rgbFormat = aiFrame->rgbFormat;
                    taskFrame->data = std::shared_ptr<uint8_t>(
                        new uint8_t[rgbStride * _height], std::default_delete<uint8_t[]>());
                    
                    auto t_memcpy_start = std::chrono::steady_clock::now();
                    memcpy(taskFrame->data.get(), aiFrame->data.get(), rgbStride * _height);
                    auto t_memcpy_end = std::chrono::steady_clock::now();
                    auto memcpy_duration = std::chrono::duration_cast<std::chrono::milliseconds>(
                        t_memcpy_end - t_memcpy_start).count();
                    if (memcpy_duration > 10) {
                        WarnL << "[PULL] memcpy took " << memcpy_duration << "ms (size=" << (rgbStride * _height) << ")";
                    }
                    
                    auto t_push_start = std::chrono::steady_clock::now();
                    processor->inputQueue.push(taskFrame);
                    auto t_push_end = std::chrono::steady_clock::now();
                    auto push_duration = std::chrono::duration_cast<std::chrono::milliseconds>(
                        t_push_end - t_push_start).count();
                    if (push_duration > 10) {
                        WarnL << "[PULL] inputQueue.push took " << push_duration << "ms (QUEUE FULL?)";
                    }
                }
                auto t_dispatch_end = std::chrono::steady_clock::now();
                auto dispatch_duration = std::chrono::duration_cast<std::chrono::milliseconds>(
                    t_dispatch_end - t_dispatch_start).count();
                if (dispatch_duration > 50) {
                    InfoL << "[PULL] Frame dispatch took " << dispatch_duration << "ms (total for all AI tasks)";
                }
                
                // ⑦ 分发到原始流队列
                if (_originalProcessor) {
                    auto t_orig_start = std::chrono::steady_clock::now();
                    auto originalFrame = std::make_shared<AiFrame>();
                    originalFrame->width = aiFrame->width;
                    originalFrame->height = aiFrame->height;
                    originalFrame->stride = aiFrame->stride;
                    originalFrame->pts = aiFrame->pts;
                    originalFrame->frameIndex = aiFrame->frameIndex;  // 复制帧序号
                    originalFrame->rgbFormat = aiFrame->rgbFormat;
                    originalFrame->data = std::shared_ptr<uint8_t>(
                        new uint8_t[rgbStride * _height], std::default_delete<uint8_t[]>());
                    memcpy(originalFrame->data.get(), aiFrame->data.get(), rgbStride * _height);
                    _originalProcessor->encodeQueue.push(originalFrame);
                    auto t_orig_end = std::chrono::steady_clock::now();
                    auto orig_duration = std::chrono::duration_cast<std::chrono::milliseconds>(
                        t_orig_end - t_orig_start).count();
                    if (orig_duration > 20) {
                        InfoL << "[PULL] Original stream dispatch took " << orig_duration << "ms";
                    }
                }
            }
            
            if (needReconnect) break;
        }

    cleanup:
        // 释放资源
        if (pkt) av_packet_free(&pkt);
        if (frame) av_frame_free(&frame);
        if (swFrame) av_frame_free(&swFrame);
        if (swsCtx) { sws_freeContext(swsCtx); swsCtx = nullptr; }
        if (decCtx) { avcodec_free_context(&decCtx); decCtx = nullptr; }
        if (hwCtx) { av_buffer_unref(&hwCtx); hwCtx = nullptr; }
        if (fmtCtx) { avformat_close_input(&fmtCtx); fmtCtx = nullptr; }

    reconnect:
        if (!_running) break;
        
        // 检查是否超过最大重试次数
        if (retryCount >= MAX_RETRY_COUNT) {
            WarnL << "[" << _config.streamName << "] Max retry count (" << MAX_RETRY_COUNT 
                  << ") reached, continue retrying every " << RECONNECT_INTERVAL << "s...";
            // 超过 10 分钟后继续重试，但不再增加计数
        }
        
        // 等待 30 秒后重试
        InfoL << "[" << _config.streamName << "] Retrying in " << RECONNECT_INTERVAL << "s...";
        for (int i = 0; i < RECONNECT_INTERVAL * 10 && _running; ++i) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
    }

    InfoL << "Pull thread stopped for " << _config.streamName;
}

void StreamProcessor::aiProcessThread(int threadId, size_t taskIdx) {
    if (taskIdx >= _aiProcessors.size()) {
        ErrorL << "Invalid task index: " << taskIdx;
        return;
    }
    
    auto& processor = _aiProcessors[taskIdx];
    const std::string& taskName = processor->task.taskName;
    InfoL << "AI thread " << threadId << " started for task: " << taskName;

    // 初始化 AI 引擎
    std::string shmName = "/ai_stream_" + _config.streamName + "_" + taskName + "_" + std::to_string(threadId);
    // Linked worktrees can process the same camera and task concurrently.
    if (const char* instance = std::getenv("AI_STREAM_SHM_NAMESPACE")) {
        if (*instance) shmName += "_" + std::string(instance);
    }
    // size_t shmSize = 1280 * 720 * 3;  // 假设最大分辨率
    std::unique_ptr<AiEngine> engine;
    
    // 使用任务自己的 IPC 地址和配置
    const auto& taskConfig = processor->task.aiConfig;
    std::string zmqAddr = processor->task.ipcAddr;
    
    // 日志输出跳帧模式
    std::string modeStr = (taskConfig.frameSkipMode == FrameSkipMode::CONTINUOUS) 
        ? "continuous(" + std::to_string(taskConfig.frameSkipAi) + ":" + std::to_string(taskConfig.frameSkipTotal) + ")"
        : "interleaved(" + std::to_string(taskConfig.frameSkip) + ")";
    InfoL << "AI thread " << threadId << " for " << taskName << " using IPC: " << zmqAddr
          << " (mode=" << modeStr << ", timeout=" << taskConfig.zmqTimeout << "ms)";

    while (_running) {
        auto t_frame_start = std::chrono::steady_clock::now();
        
        AiFramePtr frame;
        auto t_pop_start = std::chrono::steady_clock::now();
        if (!processor->inputQueue.pop(frame, 100)) continue;
        auto t_pop_end = std::chrono::steady_clock::now();
        auto pop_duration = std::chrono::duration_cast<std::chrono::microseconds>(
            t_pop_end - t_pop_start).count() / 1000.0;

        // 跳帧处理 - 使用任务自己的配置
        int count = processor->frameCounter.fetch_add(1);
        bool doAi = taskConfig.shouldDoAi(count);

        // 帧已经是独立副本，直接使用
        if (doAi) {
            // 延迟初始化 AI 引擎
            if (!engine && _width > 0 && _height > 0) {
                size_t shmSize = _width * _height * 3 * 2;
                try {
                    engine = std::make_unique<AiEngine>(shmName, shmSize,
                        zmqAddr, taskConfig.zmqTimeout);
                    InfoL << "AI engine " << threadId << " initialized for " << taskName << " with shmSize: " << shmSize;
                } catch (const std::exception& e) {
                    ErrorL << "AI engine init failed: " << e.what();
                }
            }

            // 统一的 AI 处理接口 - 根据配置的传输模式调用
            if (engine) {
                auto t_ai_start = std::chrono::steady_clock::now();
                // 转换 AiTransportMode -> TransportMode
                TransportMode mode = (processor->task.transport == AiTransportMode::BASE64)
                    ? TransportMode::BASE64 : TransportMode::SHM;
                
                // 从 pushUrl 中提取 path (例如: rtsp://127.0.0.1:8554/live/camera_1_reid -> live/camera_1_reid)
                std::string path;
                const std::string& pushUrl = processor->task.pushUrl;
                size_t pos = pushUrl.find("://");
                if (pos != std::string::npos) {
                    size_t pathStart = pushUrl.find('/', pos + 3);
                    if (pathStart != std::string::npos) {
                        path = pushUrl.substr(pathStart + 1);  // 跳过开头的 '/'
                    }
                }
                
                bool success = engine->process(taskName, frame, mode, _config.streamName, path);
                auto t_ai_end = std::chrono::steady_clock::now();
                auto ai_duration = std::chrono::duration_cast<std::chrono::microseconds>(
                    t_ai_end - t_ai_start).count() / 1000.0;
                
                if (!success) {
                    WarnL << "[AI-THREAD] " << taskName << " thread=" << threadId 
                          << " frame=" << count << " AI FAILED/TIMEOUT after " << ai_duration << "ms";
                } else if (ai_duration > 50.0) {
                    InfoL << "[AI-THREAD] " << taskName << " thread=" << threadId 
                          << " frame=" << count << " AI took " << ai_duration << "ms";
                }
            }
        }

        processor->encodeQueue.push(frame);
        
        auto t_frame_end = std::chrono::steady_clock::now();
        auto frame_duration = std::chrono::duration_cast<std::chrono::microseconds>(
            t_frame_end - t_frame_start).count() / 1000.0;
        
        // 如果整个帧处理时间超过阈值，输出详细日志
        if (frame_duration > 100.0) {
            InfoL << "[FRAME-PROC] " << taskName << " thread=" << threadId 
                  << " frame=" << count << " total=" << frame_duration << "ms "
                  << "pop=" << pop_duration << "ms";
        }
    }

    InfoL << "AI thread " << threadId << " stopped for task: " << taskName;
}

void StreamProcessor::encodeAndPushThread(size_t taskIdx) {
    if (taskIdx >= _aiProcessors.size()) {
        ErrorL << "Invalid task index: " << taskIdx;
        return;
    }
    
    auto& processor = _aiProcessors[taskIdx];
    const std::string& taskName = processor->task.taskName;
    InfoL << "Push thread started for task: " << taskName;

    while (_running) {
        // 等待获取分辨率
        while (_running && (_width == 0 || _height == 0)) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
        if (!_running) break;

        AVCodecContext* encCtx = nullptr;
        AVFormatContext* fmtCtx = nullptr;
        AVStream* stream = nullptr;
        SwsContext* swsCtx = nullptr;
        AVFrame* yuvFrame = nullptr;
        AVPacket* pkt = nullptr;
        bool needReconnect = false;

        if (!initEncoder(encCtx, _width, _height)) {
            ErrorL << "[" << _config.streamName << "/" << taskName << "] Init encoder failed, retrying...";
            std::this_thread::sleep_for(std::chrono::seconds(5));
            continue;
        }

        if (!initPusher(fmtCtx, stream, encCtx, processor->task.pushUrl)) {
            ErrorL << "[" << _config.streamName << "/" << taskName << "] Init pusher failed, retrying...";
            avcodec_free_context(&encCtx);
            std::this_thread::sleep_for(std::chrono::seconds(5));
            continue;
        }

        yuvFrame = av_frame_alloc();
        yuvFrame->format = encCtx->pix_fmt;
        yuvFrame->width = _width;
        yuvFrame->height = _height;
        av_frame_get_buffer(yuvFrame, 0);

        pkt = av_packet_alloc();
        int64_t lastPts = AV_NOPTS_VALUE;  // 用于检测 PTS 异常
        uint64_t nextExpectedIndex = UINT64_MAX;  // 下一个期望的帧序号
        int emptyCount = 0;
        const int MAX_EMPTY_COUNT = 100;  // 10秒没有数据则重连
        
        // 按帧序号排序的缓冲区
        std::map<uint64_t, AiFramePtr> reorderBuffer;
        const size_t MAX_REORDER_SIZE = 10;  // 最大缓冲 60 帧

        while (_running && !needReconnect) {
            AiFramePtr frame;
            bool forceFlush = false;
            
            if (!processor->encodeQueue.pop(frame, 100)) {
                emptyCount++;
                if (emptyCount >= MAX_EMPTY_COUNT) {
                    WarnL << "[" << _config.streamName << "/" << taskName << "] No data for 10s, reconnecting pusher...";
                    needReconnect = true;
                }
                // 超时时也尝试输出缓冲区中的帧（强制输出）
                if (!reorderBuffer.empty() && emptyCount >= 5) {
                    forceFlush = true;
                } else {
                    continue;
                }
            } else {
                emptyCount = 0;
                
                // 将帧放入重排序缓冲区
                reorderBuffer[frame->frameIndex] = frame;
                
                // 初始化期望序号
                if (nextExpectedIndex == UINT64_MAX && !reorderBuffer.empty()) {
                    nextExpectedIndex = reorderBuffer.begin()->first;
                }
            }
            
            // 输出连续的帧（严格按序号顺序）
            while (!reorderBuffer.empty()) {
                auto it = reorderBuffer.find(nextExpectedIndex);
                
                if (it != reorderBuffer.end()) {
                    // 找到期望的帧，输出
                    frame = it->second;
                    reorderBuffer.erase(it);
                    nextExpectedIndex++;
                } else if (forceFlush || reorderBuffer.size() >= MAX_REORDER_SIZE) {
                    // 缓冲区太大或超时，强制输出最早的帧
                    auto earliest = reorderBuffer.begin();
                    frame = earliest->second;
                    WarnL << "[" << taskName << "] Force output frame " << earliest->first 
                          << ", expected " << nextExpectedIndex;
                    nextExpectedIndex = earliest->first + 1;  // 跳过缺失的帧
                    reorderBuffer.erase(earliest);
                    forceFlush = false;  // 只强制输出一帧
                } else {
                    // 等待期望的帧到达
                    break;
                }

                // RGB -> YUV
                if (!swsCtx) {
                    swsCtx = sws_getContext(
                        _width, _height, AV_PIX_FMT_RGB24,
                        _width, _height, encCtx->pix_fmt,
                        SWS_FAST_BILINEAR, nullptr, nullptr, nullptr);
                }

                int rgbStride = _width * 3;
                uint8_t* srcPlanes[4] = {frame->data.get(), nullptr, nullptr, nullptr};
                int srcStrides[4] = {rgbStride, 0, 0, 0};
                sws_scale(swsCtx, srcPlanes, srcStrides, 0, _height,
                          yuvFrame->data, yuvFrame->linesize);

                // 使用原始帧的 PTS，转换到编码器的时间基
                int64_t pts = av_rescale_q(frame->pts, _inputTimeBase, encCtx->time_base);
                // 确保 PTS 单调递增
                if (lastPts != AV_NOPTS_VALUE && pts <= lastPts) {
                    pts = lastPts + 1;
                }
                lastPts = pts;
                yuvFrame->pts = pts;

                int ret = avcodec_send_frame(encCtx, yuvFrame);
                if (ret < 0) {
                    if (ret != AVERROR(EAGAIN)) {
                        needReconnect = true;
                    }
                    continue;
                }

                while (ret >= 0) {
                    ret = avcodec_receive_packet(encCtx, pkt);
                    if (ret == AVERROR(EAGAIN) || ret == AVERROR_EOF) break;
                    if (ret < 0) {
                        needReconnect = true;
                        break;
                    }

                    av_packet_rescale_ts(pkt, encCtx->time_base, stream->time_base);
                    pkt->stream_index = stream->index;

                    ret = av_interleaved_write_frame(fmtCtx, pkt);
                    av_packet_unref(pkt);
                    if (ret < 0) {
                        WarnL << "[" << _config.streamName << "/" << taskName << "] Write frame failed, reconnecting...";
                        needReconnect = true;
                        break;
                    }
                }
                
                if (needReconnect) break;
            }
        }

        // 释放资源
        if (pkt) av_packet_free(&pkt);
        if (yuvFrame) av_frame_free(&yuvFrame);
        if (swsCtx) sws_freeContext(swsCtx);
        if (encCtx) avcodec_free_context(&encCtx);
        if (fmtCtx) {
            av_write_trailer(fmtCtx);
            if (fmtCtx->pb) avio_closep(&fmtCtx->pb);
            avformat_free_context(fmtCtx);
        }

        if (_running && needReconnect) {
            InfoL << "[" << _config.streamName << "/" << taskName << "] Pusher will reconnect in 2s...";
            // 清空队列中的旧帧
            AiFramePtr discardFrame;
            while (processor->encodeQueue.pop(discardFrame, 0)) {}
            std::this_thread::sleep_for(std::chrono::seconds(2));
        }
    }

    InfoL << "Push thread stopped for task: " << taskName;
}

void StreamProcessor::originalPushThread() {
    if (!_originalProcessor) return;
    
    InfoL << "Original push thread started";

    while (_running) {
        // 等待获取分辨率
        while (_running && (_width == 0 || _height == 0)) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
        if (!_running) break;

        AVCodecContext* encCtx = nullptr;
        AVFormatContext* fmtCtx = nullptr;
        AVStream* stream = nullptr;
        SwsContext* swsCtx = nullptr;
        AVFrame* yuvFrame = nullptr;
        AVPacket* pkt = nullptr;
        bool needReconnect = false;

        if (!initEncoder(encCtx, _width, _height)) {
            ErrorL << "[" << _config.streamName << "] Init encoder failed for original, retrying...";
            std::this_thread::sleep_for(std::chrono::seconds(5));
            continue;
        }

        if (!initPusher(fmtCtx, stream, encCtx, _originalProcessor->pushUrl)) {
            ErrorL << "[" << _config.streamName << "] Init pusher failed for original, retrying...";
            avcodec_free_context(&encCtx);
            std::this_thread::sleep_for(std::chrono::seconds(5));
            continue;
        }

        yuvFrame = av_frame_alloc();
        yuvFrame->format = encCtx->pix_fmt;
        yuvFrame->width = _width;
        yuvFrame->height = _height;
        av_frame_get_buffer(yuvFrame, 0);

        pkt = av_packet_alloc();
        int64_t lastPts = AV_NOPTS_VALUE;  // 用于检测 PTS 异常
        int emptyCount = 0;
        const int MAX_EMPTY_COUNT = 100;  // 10秒没有数据则重连

        while (_running && !needReconnect) {
            AiFramePtr frame;
            if (!_originalProcessor->encodeQueue.pop(frame, 100)) {
                emptyCount++;
                if (emptyCount >= MAX_EMPTY_COUNT) {
                    WarnL << "[" << _config.streamName << "] Original: No data for 10s, reconnecting pusher...";
                    needReconnect = true;
                }
                continue;
            }
            emptyCount = 0;

            // RGB -> YUV
            if (!swsCtx) {
                swsCtx = sws_getContext(
                    _width, _height, AV_PIX_FMT_RGB24,
                    _width, _height, encCtx->pix_fmt,
                    SWS_FAST_BILINEAR, nullptr, nullptr, nullptr);
            }

            int rgbStride = _width * 3;
            uint8_t* srcPlanes[4] = {frame->data.get(), nullptr, nullptr, nullptr};
            int srcStrides[4] = {rgbStride, 0, 0, 0};
            sws_scale(swsCtx, srcPlanes, srcStrides, 0, _height,
                      yuvFrame->data, yuvFrame->linesize);

            // 使用原始帧的 PTS，转换到编码器的时间基
            int64_t pts = av_rescale_q(frame->pts, _inputTimeBase, encCtx->time_base);
            // 确保 PTS 单调递增
            if (lastPts != AV_NOPTS_VALUE && pts <= lastPts) {
                pts = lastPts + 1;
            }
            lastPts = pts;
            yuvFrame->pts = pts;

            int ret = avcodec_send_frame(encCtx, yuvFrame);
            if (ret < 0) {
                if (ret != AVERROR(EAGAIN)) {
                    needReconnect = true;
                }
                continue;
            }

            while (ret >= 0) {
                ret = avcodec_receive_packet(encCtx, pkt);
                if (ret == AVERROR(EAGAIN) || ret == AVERROR_EOF) break;
                if (ret < 0) {
                    needReconnect = true;
                    break;
                }

                av_packet_rescale_ts(pkt, encCtx->time_base, stream->time_base);
                pkt->stream_index = stream->index;

                ret = av_interleaved_write_frame(fmtCtx, pkt);
                av_packet_unref(pkt);
                if (ret < 0) {
                    WarnL << "[" << _config.streamName << "] Original: Write frame failed, reconnecting...";
                    needReconnect = true;
                    break;
                }
            }
        }

        // 释放资源
        if (pkt) av_packet_free(&pkt);
        if (yuvFrame) av_frame_free(&yuvFrame);
        if (swsCtx) sws_freeContext(swsCtx);
        if (encCtx) avcodec_free_context(&encCtx);
        if (fmtCtx) {
            av_write_trailer(fmtCtx);
            if (fmtCtx->pb) avio_closep(&fmtCtx->pb);
            avformat_free_context(fmtCtx);
        }

        if (_running && needReconnect) {
            InfoL << "[" << _config.streamName << "] Original pusher will reconnect in 2s...";
            std::this_thread::sleep_for(std::chrono::seconds(2));
        }
    }

    InfoL << "Original push thread stopped";
}

} // namespace test
