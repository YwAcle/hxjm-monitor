#pragma once
#include "../utils/Logger.h"
#include <sys/fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <cerrno>
#include <cstring>
#include <string>
#include <stdexcept>
#include <chrono>

namespace test {

struct ShmBuffer {
    int fd;
    size_t size;
    void* data;
    std::string name;

    ShmBuffer(std::string shmName, size_t sz)
        : size(sz), name(std::move(shmName)) {
        if (name.empty() || name.front() != '/') {
            name = "/" + name;
        }
        bool existed = false;
        fd = shm_open(name.c_str(), O_CREAT | O_EXCL | O_RDWR, 0666);
        if (fd < 0 && errno == EEXIST) {
            fd = shm_open(name.c_str(), O_RDWR, 0666);
            existed = true;
        }
        if (fd < 0) {
            ErrorL << "shm_open failed: " << strerror(errno);
            throw std::runtime_error("shm_open failed");
        }
        if (fchmod(fd, 0666) != 0) {
            ErrorL << "fchmod failed: " << strerror(errno);
        }
        if (size == 0) {
            ErrorL << "ftruncate invalid size 0";
            throw std::runtime_error("ftruncate invalid size 0");
        }
        long pagesize = sysconf(_SC_PAGESIZE);
        if (pagesize <= 0) pagesize = 4096;
        size_t aligned = ((size + (size_t)pagesize - 1) / (size_t)pagesize) * (size_t)pagesize;
        size_t map_len = aligned;
        if (!existed) {
            if (ftruncate(fd, static_cast<off_t>(aligned)) != 0) {
                ErrorL << "ftruncate failed: " << strerror(errno);
                close(fd);
                shm_unlink(name.c_str());
                fd = shm_open(name.c_str(), O_CREAT | O_EXCL | O_RDWR, 0666);
                if (fd < 0) {
                    ErrorL << "shm_open retry failed: " << strerror(errno);
                    throw std::runtime_error("shm_open retry failed");
                }
                if (ftruncate(fd, static_cast<off_t>(aligned)) != 0) {
                    ErrorL << "ftruncate retry failed: " << strerror(errno);
                    throw std::runtime_error("ftruncate failed");
                }
            }
            if (fchmod(fd, 0666) != 0) {
                ErrorL << "fchmod failed: " << strerror(errno);
            }
        } else {
            struct stat st{};
            if (fstat(fd, &st) == 0 && st.st_size > 0) {
                map_len = (size_t)st.st_size;
            }
        }
        data = mmap(nullptr, map_len, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
        if (data == MAP_FAILED) {
            ErrorL << "mmap failed: " << strerror(errno);
            throw std::runtime_error("mmap failed");
        }
        size = map_len;
    }

    void write(const void* in, size_t len) {
        auto t_start = std::chrono::steady_clock::now();
        memcpy(data, in, len);
        auto t_end = std::chrono::steady_clock::now();
        auto duration = std::chrono::duration_cast<std::chrono::microseconds>(t_end - t_start).count() / 1000.0;
        if (duration > 10.0) {
            InfoL << "[SHM-WRITE-MEMCPY] took " << duration << "ms (size=" << len << " name=" << name << ")";
        }
    }

    void read(void* out, size_t len) {
        auto t_start = std::chrono::steady_clock::now();
        memcpy(out, data, len);
        auto t_end = std::chrono::steady_clock::now();
        auto duration = std::chrono::duration_cast<std::chrono::microseconds>(t_end - t_start).count() / 1000.0;
        if (duration > 10.0) {
            InfoL << "[SHM-READ-MEMCPY] took " << duration << "ms (size=" << len << " name=" << name << ")";
        }
    }

    ~ShmBuffer() {
        munmap(data, size);
        close(fd);
        // 不删除共享内存，让对端能继续使用
    }
};

} // namespace test
