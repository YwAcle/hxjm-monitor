FROM python:3.11-slim

ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# 安装依赖
RUN pip install --no-cache-dir pyzmq

# 复制 Python 模块
COPY python/ /app/python/

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 默认启动命令
CMD ["python3", "/app/python/reid/server.py"]