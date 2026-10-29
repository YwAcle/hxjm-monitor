#!/usr/bin/env bash
# 启动 SGLang 大模型服务。

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
# 读取根目录的统一环境配置。
source "${ROOT_DIR}/scripts/load_env.sh"
export LLM_MODE=local LLM_BACKEND=sglang
load_env_defaults "${ROOT_DIR}/.env"
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    printf '用法：./scripts/start_sglang.sh [SGLang 服务参数]\n模型与资源配置统一读取 .env 的 LLM_* 字段。\n'
    exit 0
fi

SGLANG_ENV_ROOT="${SGLANG_ENV_ROOT:-/home/zwd/miniconda3/envs/sglang}"
SGLANG_BIN="${SGLANG_BIN:-${SGLANG_ENV_ROOT}/bin/sglang}"
SGLANG_PYTHON_BIN="${SGLANG_PYTHON_BIN:-${SGLANG_ENV_ROOT}/bin/python}"
MODEL_PATH="${LLM_MODEL_PATH}"
CUDA_TOOLKIT="${CUDA_TOOLKIT:-/usr/local/cuda-12.2}"
CACHE_ROOT="${SGLANG_CACHE_ROOT:-${ROOT_DIR}/.runtime-cache}"

SERVED_MODEL_NAME="${LLM_MODEL_ID}"
PROCESS_NAME="${SGLANG_PROCESS_NAME:-SGLang:${SERVED_MODEL_NAME}}"
SERVER_HOST="${LLM_SERVER_HOST}"
SERVER_PORT="${LLM_SERVER_PORT}"
# SGLang also reads SGLANG_PORT for internal sockets; keep it from claiming the HTTP port.
unset SGLANG_PORT
GPU_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
TP_SIZE="${LLM_TP_SIZE}"
CONTEXT_LENGTH="${LLM_CONTEXT_LENGTH}"
MEM_FRACTION_STATIC="${LLM_GPU_MEMORY_UTILIZATION}"

HOST_GCC="${SGLANG_ENV_ROOT}/bin/x86_64-conda-linux-gnu-gcc"
HOST_GXX="${SGLANG_ENV_ROOT}/bin/x86_64-conda-linux-gnu-g++"
NVCC="${CUDA_TOOLKIT}/bin/nvcc"

for executable in "${SGLANG_BIN}" "${SGLANG_PYTHON_BIN}" "${HOST_GCC}" "${HOST_GXX}" "${NVCC}"; do
    if [[ ! -x "${executable}" ]]; then
        printf '所需可执行文件不存在或不可执行：%s\n' "${executable}" >&2
        exit 1
    fi
done

if [[ ! -r "${MODEL_PATH}/config.json" ]]; then
    printf '模型配置文件不存在或不可读：%s/config.json\n' "${MODEL_PATH}" >&2
    exit 1
fi

CHAT_TEMPLATE_ARGS=()
if [[ -n "${LLM_CHAT_TEMPLATE:-}" ]]; then
    CHAT_TEMPLATE_ARGS=(--chat-template "${LLM_CHAT_TEMPLATE}")
elif [[ -r "${MODEL_PATH}/chat_template.jinja" ]]; then
    CHAT_TEMPLATE_ARGS=(--chat-template "${MODEL_PATH}/chat_template.jinja")
fi

mkdir -p \
    "${CACHE_ROOT}/huggingface/modules" \
    "${CACHE_ROOT}/triton-cuda122-gcc11" \
    "${CACHE_ROOT}/torch-cuda122-gcc11" \
    "${CACHE_ROOT}/tvm-ffi-cuda122-gcc11" \
    "${CACHE_ROOT}/flashinfer-cuda122-gcc11"

export PYTHONNOUSERSITE=1
export CUDA_HOME="${CUDA_TOOLKIT}"
export CUDA_PATH="${CUDA_TOOLKIT}"
export CUDACXX="${NVCC}"
export PYTORCH_NVCC="${NVCC}"
export NVCC_PREPEND_FLAGS="-ccbin=${HOST_GXX}"
export CC="${HOST_GCC}"
export CXX="${HOST_GXX}"
export PATH="${CUDA_TOOLKIT}/bin:${SGLANG_ENV_ROOT}/bin:${PATH}"
export TORCH_CUDA_ARCH_LIST="${TORCH_CUDA_ARCH_LIST:-8.6}"
export TVM_FFI_CUDA_ARCH_LIST="${TVM_FFI_CUDA_ARCH_LIST:-8.6}"
export SGLANG_IS_FLASHINFER_AVAILABLE=false
export HF_HOME="${CACHE_ROOT}/huggingface"
export HF_MODULES_CACHE="${CACHE_ROOT}/huggingface/modules"
export TRITON_CACHE_DIR="${CACHE_ROOT}/triton-cuda122-gcc11"
export TORCH_EXTENSIONS_DIR="${CACHE_ROOT}/torch-cuda122-gcc11"
export TVM_FFI_CACHE_DIR="${CACHE_ROOT}/tvm-ffi-cuda122-gcc11"
export FLASHINFER_WORKSPACE_BASE="${CACHE_ROOT}/flashinfer-cuda122-gcc11"
export CUDA_VISIBLE_DEVICES="${GPU_DEVICES}"
export SGLANG_PROCESS_NAME="${PROCESS_NAME}"

printf '正在启动 SGLang：模型=%s，进程名=%s，GPU=%s，TP=%s，接口=http://%s:%s\n' \
    "${MODEL_PATH}" "${PROCESS_NAME}" "${GPU_DEVICES}" "${TP_SIZE}" "${SERVER_HOST}" "${SERVER_PORT}"
if ((${#CHAT_TEMPLATE_ARGS[@]})); then
    printf '使用模型聊天模板：%s\n' "${CHAT_TEMPLATE_ARGS[1]}"
fi

exec "${SGLANG_PYTHON_BIN}" "${SCRIPT_DIR}/launch_sglang.py" "${SGLANG_BIN}" serve \
    --model-path "${MODEL_PATH}" \
    --tokenizer-path "${MODEL_PATH}" \
    --served-model-name "${SERVED_MODEL_NAME}" \
    --host "${SERVER_HOST}" \
    --port "${SERVER_PORT}" \
    --api-key "${LLM_API_KEY:-unused}" \
    --dtype "${LLM_DTYPE}" \
    --context-length "${CONTEXT_LENGTH}" \
    --mem-fraction-static "${MEM_FRACTION_STATIC}" \
    --tp-size "${TP_SIZE}" \
    --enable-multimodal \
    --attention-backend triton \
    --sampling-backend pytorch \
    --mm-attention-backend triton_attn \
    --trust-remote-code \
    "${CHAT_TEMPLATE_ARGS[@]}" \
    "$@"
