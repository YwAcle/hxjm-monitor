#pragma once
#include <memory>
#include <cstdint>
extern "C" {
#include <libavutil/pixfmt.h>
}

namespace test {

struct AiFrame {
    std::shared_ptr<uint8_t> data;  // RGB 数据
    size_t width;
    size_t height;
    size_t stride;                   // 每行字节数
    int64_t pts;                     // 时间戳
    uint64_t frameIndex;             // 帧序号（用于排序）
    AVPixelFormat rgbFormat;         // 像素格式
};

using AiFramePtr = std::shared_ptr<AiFrame>;

} // namespace test
