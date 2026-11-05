#!/usr/bin/env bash
# Explicit model deployment, isolated to this clone's recorded processes.
set -euo pipefail
action=${1:-status}
if (($#)); then shift; fi
source "$(dirname -- "${BASH_SOURCE[0]}")/local-common.sh" "$@"
load_port_config
JOY_DIR="$ROOT_DIR/.run/joyai"
JOY_PYTHON="$JOY_DIR/venv/bin/python"
JOY_MODEL_DIR="$JOY_DIR/models/JoyAI-VL-Interaction-INT4"
export JOYAI_CONFIG="$JOY_DIR/config.json"
export PYTHONPATH="$ROOT_DIR/python"
export HF_HOME="$JOY_DIR/cache/huggingface" UV_CACHE_DIR="$JOY_DIR/cache/uv"
export XDG_CACHE_HOME="$JOY_DIR/cache" VLLM_CACHE_ROOT="$JOY_DIR/cache/vllm"
export CUDA_CACHE_PATH="$JOY_DIR/cache/cuda" TRITON_CACHE_DIR="$JOY_DIR/cache/triton"
export TMPDIR="$JOY_DIR/tmp" HF_HUB_DISABLE_XET=1 VLLM_WORKER_MULTIPROC_METHOD=spawn
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export VLLM_USE_FLASHINFER_SAMPLER=0
mkdir -p "$TMPDIR" "$LOG_DIR"

wait_health() {
    local name=$1 port=$2 attempt
    for ((attempt=0; attempt<1200; attempt++)); do
        runtime status "$name" || { echo "查看 $LOG_DIR/$name.log" >&2; return 1; }
        if curl --fail --silent --max-time 2 "http://127.0.0.1:$port/health" >/dev/null; then return 0; fi
        sleep 1
    done
    echo "$name 未就绪，查看 $LOG_DIR/$name.log" >&2
    return 1
}

check_port() {
    [[ -z "$(ss -Hltn "sport = :$1")" ]] || { echo "端口 $1 已占用，不会停止其拥有者。" >&2; return 1; }
}

weights() {
    "$JOY_PYTHON" - "$JOY_MODEL_DIR" "$JOY_DIR/models/Qwen3.8-27B-AWQ-INT4" <<'PY'
import json,sys
from pathlib import Path
for i,name in enumerate(sys.argv[1:]):
    root=Path(name); config=json.loads((root/'config.json').read_text())
    if i==0:
        quant=config.get('quantization_config',{})
        if quant.get('quant_method')!='compressed-tensors' or not any(
            group.get('weights',{}).get('num_bits')==4 for group in quant.get('config_groups',{}).values()):
            raise SystemExit('JoyAI 必须为官方同参数规模的 INT4 权重')
        text=config.get('text_config',{})
        if text.get('num_hidden_layers')!=36 or text.get('hidden_size')!=4096:
            raise SystemExit('JoyAI 参数结构与原 8B 模型不一致')
    if not config.get('vision_config'):
        raise SystemExit('模型缺少视觉模块')
    index=root/'model.safetensors.index.json'
    shards=set(json.loads(index.read_text())['weight_map'].values()) if index.exists() else {'model.safetensors'}
    if any(not (root/shard).is_file() for shard in shards):
        raise SystemExit(f'模型权重尚未下载完整：{root}')
print('JoyAI 官方同参数规模 INT4 与 Qwen 视觉权重检查通过。')
PY
}

control() {
    "$JOY_PYTHON" - "$1" <<'PY'
import json,os,urllib.request
config=json.load(open(os.environ['JOYAI_CONFIG']))
request=urllib.request.Request(config['tool_url']+'/monitoring/'+__import__('sys').argv[1],
    data=b'{}',headers={'Content-Type':'application/json','X-JoyAI-Token':config['token']})
with urllib.request.urlopen(request,timeout=60) as r: print(r.read().decode())
PY
}

case "$action" in
    setup)
        command -v uv >/dev/null || { echo '需要 uv'; exit 1; }
        if [[ ! -d "$JOY_DIR/source" ]]; then
            git clone --no-checkout https://github.com/jd-opensource/JoyAI-VL-Interaction.git "$JOY_DIR/source"
            git -C "$JOY_DIR/source" checkout --detach 12e817ef64d6e8065a3cf69572bb074b0e1fcff8
        fi
        [[ -x "$JOY_PYTHON" ]] || uv venv --python 3.12 "$JOY_DIR/venv"
        uv pip install --python "$JOY_PYTHON" -c "$JOY_DIR/source/install/constraints.txt" \
            'vllm==0.22.0' aiohttp huggingface_hub ninja opencv-python-headless pyyaml
        "$JOY_PYTHON" - "$JOY_MODEL_DIR" <<'PY'
import sys
from huggingface_hub import snapshot_download
snapshot_download('jdopensource/JoyAI-VL-Interaction-INT4',revision='1bfadbd2b41c11864cd7c359c7ea961aa6fd835c',local_dir=sys.argv[1],max_workers=2)
PY
        ;;
    prepare)
        python3 -m joyai_tool.prepare "$ROOT_DIR"
        ;;
    check)
        check_worktree_ports
        weights
        "$JOY_PYTHON" -c 'from joyai_tool.config import load; c=load(); print("四路配置、10 秒证据窗口已核对。")'
        nvidia-smi --query-gpu=index,name,memory.free --format=csv,noheader
        ;;
    start)
        lock_runtime
        check_worktree_ports
        weights
        [[ -f "$JOY_DIR/backend.yml" ]] || { echo '请先运行 prepare 并重新启动本目录后端。'; exit 1; }
        if ! runtime status joyai_model; then
            check_port "$JOYAI_MODEL_PORT"
            runtime start joyai_model "$ROOT_DIR" "$LOG_DIR/joyai_model.log" env CUDA_VISIBLE_DEVICES="${JOYAI_GPU:-0}" \
                "$JOY_PYTHON" -m vllm.entrypoints.openai.api_server --host 127.0.0.1 --port "$JOYAI_MODEL_PORT" \
                --model "$JOY_MODEL_DIR" --served-model-name jdopensource/JoyAI-VL-Interaction \
                --dtype bfloat16 --max-model-len 4096 --max-num-seqs 1 --max-num-batched-tokens 1024 \
                --gpu-memory-utilization "${JOYAI_GPU_MEMORY_UTILIZATION:-0.40}" --enforce-eager \
                --limit-mm-per-prompt '{"image":8,"video":0}' --mm-processor-kwargs '{"max_pixels":262144}'
        fi
        wait_health joyai_model "$JOYAI_MODEL_PORT"
        if ! runtime status joyai_observer; then
            check_port "$JOYAI_OBSERVER_PORT"
            runtime start joyai_observer "$ROOT_DIR" "$LOG_DIR/joyai_observer.log" \
                "$JOY_PYTHON" "$JOY_DIR/source/services/webinfer/live_adapter.py" \
                --host 127.0.0.1 --port "$JOYAI_OBSERVER_PORT" --main-api-base "http://127.0.0.1:$JOYAI_MODEL_PORT/v1" \
                --main-model jdopensource/JoyAI-VL-Interaction --disable-summarizer --chunk 8 --no-live-save \
                --no-save-model-inputs --no-summarizer-debug --no-force-silence-before-query --no-normalize-output \
                --no-qa-history --main-max-tokens 512 --main-temperature 0 \
                --frame-save-dir "$JOY_DIR/frames" --save-root "$JOY_DIR/results"
        fi
        wait_health joyai_observer "$JOYAI_OBSERVER_PORT"
        if ! runtime status joyai_tool; then
            # Retire an orphan from an earlier run; the tool owns subsequent demand loads.
            runtime stop joyai_qwen
            check_port "$JOYAI_TOOL_PORT"
            runtime start joyai_tool "$ROOT_DIR/python" "$LOG_DIR/joyai_tool.log" \
                "$JOY_PYTHON" -m uvicorn joyai_tool.app:app --host 127.0.0.1 --port "$JOYAI_TOOL_PORT"
        fi
        wait_health joyai_tool "$JOYAI_TOOL_PORT"
        control start
        ;;
    review-start)
        lock_runtime
        weights
        if ! runtime status joyai_tool; then
            echo '复核模型仅由正在运行的本目录工具按需启动。' >&2; exit 1
        fi
        if ! runtime status joyai_qwen; then
            check_port "$JOYAI_REVIEW_PORT"
            runtime start joyai_qwen "$ROOT_DIR" "$LOG_DIR/joyai_qwen.log" env CUDA_VISIBLE_DEVICES="${JOYAI_REVIEW_GPU:-1}" \
                "$JOY_PYTHON" -m vllm.entrypoints.openai.api_server --host 127.0.0.1 --port "$JOYAI_REVIEW_PORT" \
                --model "$JOY_DIR/models/Qwen3.8-27B-AWQ-INT4" --served-model-name Qwen/Qwen3.8-27B-AWQ-INT4 \
                --dtype bfloat16 --max-model-len 8192 --max-num-seqs 1 --max-num-batched-tokens 1024 \
                --gpu-memory-utilization "${JOYAI_REVIEW_GPU_MEMORY_UTILIZATION:-0.92}" --enforce-eager \
                --limit-mm-per-prompt '{"image":8,"video":0}' --mm-processor-kwargs '{"max_pixels":262144}'
        fi
        # The monitoring worker waits for health with cancellation support.
        ;;
    review-stop)
        lock_runtime
        runtime stop joyai_qwen
        ;;
    stop)
        if runtime status joyai_tool; then control stop || true; fi
        lock_runtime
        for name in joyai_tool joyai_observer joyai_model joyai_qwen; do runtime stop "$name"; done
        ;;
    status)
        for name in joyai_model joyai_observer joyai_qwen joyai_tool; do
            if runtime status "$name"; then echo "$name: running"; else echo "$name: stopped"; fi
        done
        if runtime status joyai_tool; then curl --fail --silent --max-time 5 "http://127.0.0.1:$JOYAI_TOOL_PORT/status"; fi
        ;;
    *) echo 'Usage: bash scripts/joyai-tool.sh setup|prepare|check|start|stop|status'; exit 2 ;;
esac
