FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

# ---------- 1) APT 国内源 + 基础依赖 ----------
RUN sed -i 's@http://archive.ubuntu.com/ubuntu/@https://mirrors.tuna.tsinghua.edu.cn/ubuntu/@g' /etc/apt/sources.list && \
    sed -i 's@http://security.ubuntu.com/ubuntu/@https://mirrors.tuna.tsinghua.edu.cn/ubuntu/@g' /etc/apt/sources.list && \
    apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip \
      libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3 /usr/bin/python && \
    ln -sf /usr/bin/pip3 /usr/bin/pip

# ---------- 2) pip 国内源 ----------
RUN mkdir -p /root/.pip && \
    printf "[global]\nindex-url = https://pypi.tuna.tsinghua.edu.cn/simple\ntrusted-host = pypi.tuna.tsinghua.edu.cn\n" > /root/.pip/pip.conf

WORKDIR /app

# ---------- 3) 安装依赖 ----------
RUN pip install --no-cache-dir ultralytics pyzmq ftfy regex iopath modelscope

# ---------- 4) 下载 SAM3 模型 ----------
RUN mkdir -p /app/model && \
    pip install modelscope && \
    modelscope download --model facebook/sam3 --local_dir /app/model

# ---------- 5) 拷贝代码 ----------
COPY python/base/ /app/base/
COPY python/sam3/server.py /app/server.py
COPY python/sam3/assets/ /app/assets/

# ---------- 6) 运行 ----------
ENV PYTHONUNBUFFERED=1
ENV SAM3_MODEL_PATH=/app/model/sam3/sam3.pt
CMD ["python3", "/app/server.py"]