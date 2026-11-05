#!/usr/bin/env bash
# 唯一公开启动入口；配置预览不创建后台服务。
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
case "${1:-}" in
    api|local) export LLM_MODE="$1"; shift ;;
    vllm|sglang) export LLM_MODE=local LLM_BACKEND="$1"; shift ;;
esac
if (($# > 1)); then printf '启动参数过多。\n' >&2; exit 2; fi
case "${1:-}" in
    -h|--help)
        printf '用法：bash apps/llm/scripts/start.sh [local|api|vllm|sglang] [--show-config]\n后台启动 Agent 和报告 Worker；模型端口已占用时复用兼容服务，否则按配置启动本地模型。\n'
        exit 0 ;;
    --show-config) exec bash "${SCRIPT_DIR}/internal/run_stack.sh" --show-config ;;
    '') ;;
    *) printf '无法识别参数：%s\n' "$1" >&2; exit 2 ;;
esac
source "${SCRIPT_DIR}/internal/load_env.sh"
load_env_defaults "${ROOT_DIR}/.env"
exec "${CONFIG_PYTHON_BIN:-python3}" "${SCRIPT_DIR}/internal/manage.py" start
