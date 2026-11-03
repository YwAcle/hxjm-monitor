ARG RUNTIME=analysis
FROM python:3.9.23-slim-bookworm AS analysis-base
FROM python:3.10.16-slim-bookworm AS reid-base
FROM ${RUNTIME:-analysis}-base AS environment
ARG RUNTIME=analysis
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 build-essential && rm -rf /var/lib/apt/lists/*
COPY deploy/containers/${RUNTIME}.lock /opt/hxjm/requirements.lock
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN python -m pip install --no-cache-dir --timeout 60 --retries 5 pip==25.2 setuptools==80.9.0 wheel==0.45.1
RUN python -m pip install --no-cache-dir --timeout 60 --retries 5 numpy==1.23.5 Cython==0.29.37
RUN python -m pip install --no-cache-dir --timeout 60 --retries 5 --no-build-isolation -r /opt/hxjm/requirements.lock && python -m pip check
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/python HOME=/tmp MPLBACKEND=Agg MPLCONFIGDIR=/runtime/matplotlib YOLO_CONFIG_DIR=/runtime/yolo VIDEO_ANALYSIS_CACHE_DIR=/runtime/analysis OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
WORKDIR /app/python
FROM environment AS development
CMD ["python", "-m", "uvicorn", "video_analysis.app:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1"]
FROM environment AS runtime
COPY python /app/python
ARG REVISION=unknown
ENV HXJM_REVISION=$REVISION
LABEL org.opencontainers.image.revision=$REVISION
CMD ["python", "-m", "uvicorn", "video_analysis.app:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1"]
