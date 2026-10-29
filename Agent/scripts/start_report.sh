#!/usr/bin/env bash
# 等待模型接口就绪，然后启动报告 Worker。

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
# 报告 Worker 代码仍位于 llm_report_service，启动入口统一位于 scripts。
source "${ROOT_DIR}/scripts/load_env.sh"
load_env_defaults "${ROOT_DIR}/.env"
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    printf '用法：./scripts/start_report.sh [报告 Worker 参数]\n'
    printf '等待 LLM_BASE_URL 上的模型接口就绪，然后启动报告 Worker。\n'
    exit 0
fi

LLM_BACKEND="${LLM_BACKEND:-sglang}"
case "${LLM_BACKEND}" in
    sglang | vllm) ;;
    *) printf '不支持的 LLM_BACKEND：%s\n' "${LLM_BACKEND}" >&2; exit 2 ;;
esac

PYTHON_BIN="${REPORT_PYTHON_BIN:-/data1/userhome/va/miniconda3/envs/monitor/bin/python}"

LLM_BASE_URL="${LLM_BASE_URL:-http://127.0.0.1:8000/v1}"
LLM_MODEL_ID="${LLM_MODEL_ID:-internvl3.5-8b}"
LLM_API_KEY="${LLM_API_KEY:-unused}"
LLM_CONNECT_TIMEOUT_S="${LLM_CONNECT_TIMEOUT_S:-5}"
LLM_REQUEST_TIMEOUT_S="${LLM_REQUEST_TIMEOUT_S:-180}"
LLM_MAX_RETRIES="${LLM_MAX_RETRIES:-2}"
LLM_MAX_NEW_TOKENS="${LLM_MAX_NEW_TOKENS:-1024}"
LLM_STARTUP_TIMEOUT_S="${LLM_STARTUP_TIMEOUT_S:-300}"

DB_HOST="${DB_HOST:-100.127.237.7}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-root}"
DB_PASSWORD="${DB_PASSWORD:-123456}"
DB_NAME="${DB_NAME:-postgres}"
DB_SCHEMA="${DB_SCHEMA:-public}"

SCAN_INTERVAL_S="${SCAN_INTERVAL_S:-60}"
BATCH_SIZE="${BATCH_SIZE:-8}"
MEDIA_LIMIT="${MEDIA_LIMIT:-2}"
MAX_VIDEO_FRAMES="${MAX_VIDEO_FRAMES:-8}"
MEDIA_BASE_DIR="${MEDIA_BASE_DIR:-/home/guest/Documents/lkh/mtx/mediamtx}"
RECENT_PENDING_HOURS="${RECENT_PENDING_HOURS:-1}"

healthcheck() {
    model_endpoint_ready
}

if [[ ! -x "${PYTHON_BIN}" ]]; then
    printf '报告 Worker 使用的 Python 不存在或不可执行：%s\n' "${PYTHON_BIN}" >&2
    exit 1
fi

printf '模型模式：%s（本地后端配置：%s）\n' "${LLM_MODE}" "${LLM_BACKEND}"
printf '正在等待模型接口：%s\n' "${LLM_BASE_URL}"
deadline=$((SECONDS + LLM_STARTUP_TIMEOUT_S))
until healthcheck; do
    if ((SECONDS >= deadline)); then
        printf '等待 %s 超时（已等待 %s 秒）。\n' "${LLM_BACKEND}" "${LLM_STARTUP_TIMEOUT_S}" >&2
        exit 1
    fi
    sleep 2
done
printf '模型连接配置已就绪：模型=%s，接口=%s\n' "${LLM_MODEL_ID}" "${LLM_BASE_URL}"

worker_command=(
    "${PYTHON_BIN}"
    "${ROOT_DIR}/llm_report_service/main.py"
    --llm-backend "${LLM_BACKEND}"
    --llm-base-url "${LLM_BASE_URL}"
    --llm-model "${LLM_MODEL_ID}"
    --llm-api-key "${LLM_API_KEY}"
    --llm-connect-timeout-s "${LLM_CONNECT_TIMEOUT_S}"
    --llm-request-timeout-s "${LLM_REQUEST_TIMEOUT_S}"
    --llm-max-retries "${LLM_MAX_RETRIES}"
    --max-new-tokens "${LLM_MAX_NEW_TOKENS}"
    --db-host "${DB_HOST}"
    --db-port "${DB_PORT}"
    --db-user "${DB_USER}"
    --db-password "${DB_PASSWORD}"
    --db-name "${DB_NAME}"
    --db-schema "${DB_SCHEMA}"
    --scan-interval-s "${SCAN_INTERVAL_S}"
    --batch-size "${BATCH_SIZE}"
    --media-limit "${MEDIA_LIMIT}"
    --max-video-frames "${MAX_VIDEO_FRAMES}"
    --media-base-dir "${MEDIA_BASE_DIR}"
    --recent-pending-hours "${RECENT_PENDING_HOURS}"
    "$@"
)

printf '正在启动报告 Worker：模型=%s，接口=%s\n' \
    "${LLM_MODEL_ID}" "${LLM_BASE_URL}"
export PYTHONUNBUFFERED=1
exec "${worker_command[@]}"
