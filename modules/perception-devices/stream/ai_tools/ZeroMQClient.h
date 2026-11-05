#pragma once
#include <zmq.hpp>
#include <string>
#include <utility>
#include <chrono>
#include "../utils/Logger.h"

namespace test {

class ZeroMQClient {
public:
    ZeroMQClient(std::string pyIpcAddress, int timeOut = 5000)
        : _ctx(1)
        , _socket(_ctx, ZMQ_REQ)
        , _timeOut(timeOut)
        , _pyIpcAddress(std::move(pyIpcAddress))
    {
        // 设置 linger 为 0，确保 close 时立即释放资源，避免文件描述符泄漏
        _socket.set(zmq::sockopt::linger, 0);
        _socket.connect(_pyIpcAddress);
        if (_timeOut > 0) {
            _socket.set(zmq::sockopt::rcvtimeo, _timeOut);
        }
    }

    ~ZeroMQClient() {
        try {
            _socket.set(zmq::sockopt::linger, 0);
            try {
                _socket.disconnect(_pyIpcAddress);
            } catch (...) {}
            _socket.close();
        } catch (...) {}
        // context 会在析构时自动关闭
    }

    void send(const std::string& msg) {
        auto t_start = std::chrono::steady_clock::now();
        zmq::message_t request(msg.size());
        memcpy(request.data(), msg.data(), msg.size());
        _socket.send(request, zmq::send_flags::none);
        auto t_end = std::chrono::steady_clock::now();
        auto duration = std::chrono::duration_cast<std::chrono::microseconds>(t_end - t_start).count() / 1000.0;
        if (duration > 10.0) {
            InfoL << "[ZMQ-SEND] took " << duration << "ms (msg_size=" << msg.size() << ")";
        }
    }

    std::string recv() {
        auto t_start = std::chrono::steady_clock::now();
        zmq::message_t reply;
        auto ok = _socket.recv(reply, zmq::recv_flags::none);
        auto t_end = std::chrono::steady_clock::now();
        auto duration = std::chrono::duration_cast<std::chrono::microseconds>(t_end - t_start).count() / 1000.0;
        
        if (!ok) {
            InfoL << "[ZMQ-RECV] TIMEOUT after " << duration << "ms (timeout=" << _timeOut << "ms)";
            reconnect();
            return "TIMEOUT";
        }
        
        // if (duration > 10.0) {
        //     InfoL << "[ZMQ-RECV] took " << duration << "ms (reply_size=" << reply.size() << ")";
        // }
        
        return {static_cast<char*>(reply.data()), reply.size()};
    }

private:
    void reconnect() {
        try {
            // 设置 linger 为 0，确保 close 时立即释放，不阻塞等待
            _socket.set(zmq::sockopt::linger, 0);
            // 先断开连接，再关闭 socket
            try {
                _socket.disconnect(_pyIpcAddress);
            } catch (...) {}
            _socket.close();
        } catch (...) {}
        
        _socket = zmq::socket_t(_ctx, ZMQ_REQ);
        // 新 socket 也要设置 linger
        _socket.set(zmq::sockopt::linger, 0);
        _socket.connect(_pyIpcAddress);
        if (_timeOut > 0) {
            _socket.set(zmq::sockopt::rcvtimeo, _timeOut);
        }
    }

private:
    zmq::context_t _ctx;
    zmq::socket_t _socket;
    int _timeOut;
    std::string _pyIpcAddress;
};

} // namespace test
