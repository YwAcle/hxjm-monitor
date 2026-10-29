# AI Stream Processor Dockerfile
FROM ubuntu:22.04 AS build

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 先用 HTTP 安装 ca-certificates，然后换 HTTPS 源
RUN sed -i 's@http://archive.ubuntu.com@http://mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list && \
    sed -i 's@http://security.ubuntu.com@http://mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list && \
    apt-get update && apt-get install -y ca-certificates && \
    sed -i 's@http://mirrors.tuna.tsinghua.edu.cn@https://mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list && \
    apt-get update

RUN apt-get install -y \
    build-essential \
    cmake \
    pkg-config \
    git \
    ca-certificates \
    libzmq3-dev \
    libyaml-cpp-dev \
    libx264-dev \
    libopenh264-dev \
    libavcodec-dev libavformat-dev libavutil-dev libswscale-dev \
    && rm -rf /var/lib/apt/lists/*

# Install cppzmq (header only)
COPY 3rd/cppzmq/*.hpp /usr/local/include/

WORKDIR /src
COPY . /src

WORKDIR /src/build
RUN cmake .. -DCMAKE_BUILD_TYPE=Release \
    && make -j$(nproc)

# Runtime stage
FROM ubuntu:22.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 先用 HTTP 安装 ca-certificates，然后换 HTTPS 源
RUN sed -i 's@http://archive.ubuntu.com@http://mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list && \
    sed -i 's@http://security.ubuntu.com@http://mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list && \
    apt-get update && apt-get install -y ca-certificates && \
    sed -i 's@http://mirrors.tuna.tsinghua.edu.cn@https://mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list && \
    apt-get update

RUN apt-get install -y --no-install-recommends \
    libzmq5 \
    libyaml-cpp0.7 \
    libx264-163 \
    libopenh264-6 \
    libavcodec58 libavformat58 libavutil56 libswscale5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=build /src/build/ai_stream /app/ai_stream
COPY config.yaml /app/config.yaml

# 默认环境变量
ENV REID_ZMQ_ADDR=tcp://ai-reid:5556
ENV GARDEN_ZMQ_ADDR=tcp://ai-garden:5557
ENV SAM3_ZMQ_ADDR=tcp://ai-sam3:5558
ENV PUSH_URL_PREFIX=rtsp://mediamtx:8554/live/

ENTRYPOINT ["/app/ai_stream", "/app/config.yaml"]