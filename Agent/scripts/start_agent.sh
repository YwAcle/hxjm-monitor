#!/usr/bin/env bash
# 等待共享的模型接口就绪，然后启动 Agent HTTP 服务。

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
source "${ROOT_DIR}/scripts/load_env.sh"
load_env_defaults "${ROOT_DIR}/.env"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    printf '用法：./scripts/start_agent.sh [Agent 参数]\n'
    printf '等待 LLM_BASE_URL 上的模型接口就绪，然后启动 Agent HTTP 服务。\n'
    exit 0
fi

LLM_BACKEND="${LLM_BACKEND:-sglang}"
LOG_PROFILE="${LLM_BACKEND}"
if [[ "${LLM_MODE}" == api ]]; then LOG_PROFILE=api; fi
export AGENT_JSONL_LOG="${AGENT_JSONL_LOG:-${SERVICE_STACK_RUNTIME_DIR:-${ROOT_DIR}/.runtime-cache/service-stack/${LOG_PROFILE}}/agent.jsonl}"
PYTHON_BIN="${AGENT_PYTHON_BIN:-/data1/userhome/va/miniconda3/envs/monitor/bin/python}"
AGENT_HOST="${AGENT_HOST:-0.0.0.0}"
AGENT_PORT="${AGENT_PORT:-8002}"

LLM_BASE_URL="${LLM_BASE_URL:-http://127.0.0.1:8000/v1}"
LLM_MODEL_ID="${LLM_MODEL_ID:-internvl3.5-8b}"
LLM_API_KEY="${LLM_API_KEY:-unused}"
LLM_CONNECT_TIMEOUT_S="${LLM_CONNECT_TIMEOUT_S:-5}"
LLM_REQUEST_TIMEOUT_S="${LLM_REQUEST_TIMEOUT_S:-180}"
LLM_MAX_RETRIES="${LLM_MAX_RETRIES:-2}"
LLM_MAX_NEW_TOKENS="${LLM_MAX_NEW_TOKENS:-512}"
AGENT_REQUEST_TIMEOUT_S="${AGENT_REQUEST_TIMEOUT_S:-180}"
AGENT_ANSWER_MAX_NEW_TOKENS="${AGENT_ANSWER_MAX_NEW_TOKENS:-2048}"
LLM_STARTUP_TIMEOUT_S="${LLM_STARTUP_TIMEOUT_S:-300}"

DB_HOST="${DB_HOST:-100.127.237.7}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-root}"
DB_PASSWORD="${DB_PASSWORD:-123456}"
DB_NAME="${DB_NAME:-postgres}"
DB_SCHEMA="${DB_SCHEMA:-public}"
DB_CONNECT_TIMEOUT_S="${DB_CONNECT_TIMEOUT_S:-5}"

TZ_NAME="${TZ_NAME:-Asia/Shanghai}"
PLAYBACK_BASE_URL="${PLAYBACK_BASE_URL:-}"
MEMORY_MAX_SESSIONS="${MEMORY_MAX_SESSIONS:-1000}"
MEMORY_MAX_MESSAGES="${MEMORY_MAX_MESSAGES:-20}"
MAX_REQUEST_BYTES="${MAX_REQUEST_BYTES:-20971520}"
MAX_PROMPT_CHARS="${MAX_PROMPT_CHARS:-8000}"
MAX_IMAGE_BYTES="${MAX_IMAGE_BYTES:-10485760}"
MAX_IMAGE_PIXELS="${MAX_IMAGE_PIXELS:-25000000}"
MAX_IMAGE_SIDE="${MAX_IMAGE_SIDE:-8192}"

healthcheck() {
    model_endpoint_ready
}

if [[ ! -x "${PYTHON_BIN}" ]]; then
    printf 'Agent 使用的 Python 不存在或不可执行：%s\n' "${PYTHON_BIN}" >&2
    exit 1
fi

printf '模型模式：%s（本地后端配置：%s）\n' "${LLM_MODE}" "${LLM_BACKEND}"
printf '正在等待模型接口：%s\n' "${LLM_BASE_URL}"
deadline=$((SECONDS + LLM_STARTUP_TIMEOUT_S))
until healthcheck; do
    if ((SECONDS >= deadline)); then
        printf "等待 ${LLM_BACKEND} 超时（已等待 %s 秒）。\n" \
            "${LLM_STARTUP_TIMEOUT_S}" >&2
        exit 1
    fi
    sleep 2
done
printf '模型连接配置已就绪：模型=%s，接口=%s\n' "${LLM_MODEL_ID}" "${LLM_BASE_URL}"

exec "${PYTHON_BIN}" "${ROOT_DIR}/llm_agent_service/main.py" \
    --host "${AGENT_HOST}" \
    --port "${AGENT_PORT}" \
    --llm-backend "${LLM_BACKEND}" \
    --llm-base-url "${LLM_BASE_URL}" \
    --llm-model "${LLM_MODEL_ID}" \
    --llm-api-key "${LLM_API_KEY}" \
    --llm-connect-timeout-s "${LLM_CONNECT_TIMEOUT_S}" \
    --llm-request-timeout-s "${LLM_REQUEST_TIMEOUT_S}" \
    --llm-max-retries "${LLM_MAX_RETRIES}" \
    --max-new-tokens "${LLM_MAX_NEW_TOKENS}" \
    --agent-request-timeout-s "${AGENT_REQUEST_TIMEOUT_S}" \
    --agent-answer-max-new-tokens "${AGENT_ANSWER_MAX_NEW_TOKENS}" \
    --db-host "${DB_HOST}" \
    --db-port "${DB_PORT}" \
    --db-user "${DB_USER}" \
    --db-password "${DB_PASSWORD}" \
    --db-name "${DB_NAME}" \
    --db-schema "${DB_SCHEMA}" \
    --db-connect-timeout-s "${DB_CONNECT_TIMEOUT_S}" \
    --tz "${TZ_NAME}" \
    --playback-base-url "${PLAYBACK_BASE_URL}" \
    --memory-max-sessions "${MEMORY_MAX_SESSIONS}" \
    --memory-max-messages "${MEMORY_MAX_MESSAGES}" \
    --max-request-bytes "${MAX_REQUEST_BYTES}" \
    --max-prompt-chars "${MAX_PROMPT_CHARS}" \
    --max-image-bytes "${MAX_IMAGE_BYTES}" \
    --max-image-pixels "${MAX_IMAGE_PIXELS}" \
    --max-image-side "${MAX_IMAGE_SIDE}" \
    "$@"
