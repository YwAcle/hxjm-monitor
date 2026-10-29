#!/usr/bin/env bash
# 在独立 Python 环境中启动 OpenAI 兼容的 vLLM 服务。
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
source "${ROOT_DIR}/scripts/load_env.sh"
export LLM_MODE=local LLM_BACKEND=vllm
load_env_defaults "${ROOT_DIR}/.env"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    printf '用法：./scripts/start_vllm.sh [vLLM 服务参数]\n'
    printf '模型与资源配置统一读取 .env 的 LLM_* 字段，Python 环境由 VLLM_ENV_ROOT 指定。\n'
    exit 0
fi

PYTHON_BIN="${VLLM_PYTHON_BIN:-${VLLM_ENV_ROOT:-${ROOT_DIR}/.venv-vllm}/bin/python}"
MODEL_PATH="${LLM_MODEL_PATH}"
MODEL_NAME="${LLM_MODEL_ID}"
SERVER_HOST="${LLM_SERVER_HOST}"
SERVER_PORT="${LLM_SERVER_PORT}"
CACHE_ROOT="${VLLM_CACHE_ROOT:-${ROOT_DIR}/.runtime-cache/vllm}"
MM_LIMIT='{"image":32}'
MM_LIMIT="${VLLM_LIMIT_MM_PER_PROMPT:-${MM_LIMIT}}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
    printf 'vLLM Python 不存在：%s\n请将 VLLM_PYTHON_BIN 或 VLLM_ENV_ROOT 设置为已安装 vllm 的环境。\n' "${PYTHON_BIN}" >&2
    exit 1
fi
if ! "${PYTHON_BIN}" -c 'import vllm' >/dev/null 2>&1; then
    printf '无法使用 %s 导入 vllm。\n' "${PYTHON_BIN}" >&2
    exit 1
fi

CHAT_TEMPLATE_ARGS=()
if [[ -n "${LLM_CHAT_TEMPLATE:-}" ]]; then
    CHAT_TEMPLATE_ARGS=(--chat-template "${LLM_CHAT_TEMPLATE}")
elif [[ -r "${MODEL_PATH}/chat_template.jinja" ]]; then
    CHAT_TEMPLATE_ARGS=(--chat-template "${MODEL_PATH}/chat_template.jinja")
fi

OPTIONAL_ARGS=()
if [[ -n "${VLLM_MAX_NUM_BATCHED_TOKENS:-}" ]]; then
    OPTIONAL_ARGS+=(--max-num-batched-tokens "${VLLM_MAX_NUM_BATCHED_TOKENS}")
fi
if [[ -n "${VLLM_ATTENTION_BACKEND:-}" ]]; then
    OPTIONAL_ARGS+=(--attention-backend "${VLLM_ATTENTION_BACKEND}")
fi
if [[ -n "${VLLM_REASONING_PARSER:-}" ]]; then
    OPTIONAL_ARGS+=(--reasoning-parser "${VLLM_REASONING_PARSER}")
fi
if [[ -n "${VLLM_DEFAULT_CHAT_TEMPLATE_KWARGS:-}" ]]; then
    OPTIONAL_ARGS+=(--default-chat-template-kwargs "${VLLM_DEFAULT_CHAT_TEMPLATE_KWARGS}")
elif [[ -n "${LLM_ENABLE_THINKING:-}" ]]; then
    case "${LLM_ENABLE_THINKING}" in
        false | 0) OPTIONAL_ARGS+=(--default-chat-template-kwargs '{"enable_thinking":false}') ;;
        true | 1) OPTIONAL_ARGS+=(--default-chat-template-kwargs '{"enable_thinking":true}') ;;
        *) printf 'LLM_ENABLE_THINKING 必须为 true 或 false。\n' >&2; exit 2 ;;
    esac
fi
case "${VLLM_ENFORCE_EAGER:-false}" in
    true | 1) OPTIONAL_ARGS+=(--enforce-eager) ;;
    false | 0) ;;
    *) printf 'VLLM_ENFORCE_EAGER 只接受 true、false、1、0。\n' >&2; exit 2 ;;
esac

export PYTHONNOUSERSITE=1
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
if ! "${PYTHON_BIN}" -c '
import sys
import torch
try:
    torch.cuda.init()
except Exception as exc:
    print(f"CUDA initialization failed: torch={torch.__version__}, CUDA={torch.version.cuda}: {exc}", file=sys.stderr)
    sys.exit(1)
'; then
    printf 'vLLM 需要兼容的 NVIDIA 驱动和 PyTorch/CUDA 构建，请在加载模型前检查 nvidia-smi 和 vLLM 依赖。\n' >&2
    exit 1
fi

mkdir -p "${CACHE_ROOT}/huggingface" "${CACHE_ROOT}/triton" "${CACHE_ROOT}/torch"
export HF_HOME="${HF_HOME:-${CACHE_ROOT}/huggingface}"
export TRITON_CACHE_DIR="${CACHE_ROOT}/triton"
export TORCH_EXTENSIONS_DIR="${CACHE_ROOT}/torch"

printf '正在启动 vLLM：模型=%s，GPU=%s，接口=http://%s:%s/v1\n' \
    "${MODEL_PATH}" "${CUDA_VISIBLE_DEVICES}" "${SERVER_HOST}" "${SERVER_PORT}"
exec "${PYTHON_BIN}" -m vllm.entrypoints.openai.api_server \
    --model "${MODEL_PATH}" \
    --served-model-name "${MODEL_NAME}" \
    --host "${SERVER_HOST}" \
    --port "${SERVER_PORT}" \
    --dtype "${LLM_DTYPE}" \
    --max-model-len "${LLM_CONTEXT_LENGTH}" \
    --gpu-memory-utilization "${LLM_GPU_MEMORY_UTILIZATION}" \
    --tensor-parallel-size "${LLM_TP_SIZE}" \
    --max-num-seqs "${VLLM_MAX_NUM_SEQS:-8}" \
    --limit-mm-per-prompt "${MM_LIMIT}" \
    --api-key "${LLM_API_KEY:-unused}" \
    --trust-remote-code \
    "${CHAT_TEMPLATE_ARGS[@]}" \
    "${OPTIONAL_ARGS[@]}" \
    "$@"
