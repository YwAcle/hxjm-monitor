#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi
mkdir -p .runtime/cache
export PYTHONDONTWRITEBYTECODE=1
export HF_HOME="$PWD/.runtime/cache/huggingface"
export XDG_CACHE_HOME="$PWD/.runtime/cache"
export TORCH_HOME="$PWD/.runtime/cache/torch"
export HF_HUB_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
# FFmpeg supports pthreads here; one stalled camera must not serialize all other opens.
export OPENCV_FFMPEG_IS_THREAD_SAFE=1
export GARBAGE_PYTHON="${GARBAGE_PYTHON:-/home/guest/anaconda3/envs/reid/bin/python}"
exec /usr/bin/python3 -B manage.py start
