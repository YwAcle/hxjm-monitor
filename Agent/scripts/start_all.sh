#!/usr/bin/env bash
# 启动共享的模型服务、报告 Worker 和 Agent HTTP 服务。

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
case "${1:-}" in
    api | local)
        export LLM_MODE="$1"
        shift
        ;;
    vllm | sglang)
        export LLM_MODE=local LLM_BACKEND="$1"
        shift
        ;;
esac
# 所有启动实现集中在 scripts 目录，服务代码保留在各自 Python 包中。
source "${ROOT_DIR}/scripts/load_env.sh"
load_env_defaults "${ROOT_DIR}/.env"
source "${ROOT_DIR}/scripts/logging.sh"
validate_log_write_mode "${LOG_WRITE_MODE:-append}"
MODEL_LOG_WRITE_MODE="${MODEL_LOG_WRITE_MODE:-${LOG_WRITE_MODE:-overwrite}}"
AGENT_LOG_WRITE_MODE="${AGENT_LOG_WRITE_MODE:-${LOG_WRITE_MODE:-overwrite}}"
REPORT_LOG_WRITE_MODE="${REPORT_LOG_WRITE_MODE:-${LOG_WRITE_MODE:-overwrite}}"
validate_log_write_mode "${MODEL_LOG_WRITE_MODE}"
validate_log_write_mode "${AGENT_LOG_WRITE_MODE}"
validate_log_write_mode "${REPORT_LOG_WRITE_MODE}"
export LLM_BACKEND="${LLM_BACKEND:-sglang}"
case "${LLM_BACKEND}" in
    sglang)
        MODEL_START_SCRIPT="${SGLANG_START_SCRIPT:-${SCRIPT_DIR}/start_sglang.sh}"
        MODEL_LOG="${SGLANG_LOG:-${REPORT_RUNTIME_DIR:-${ROOT_DIR}/.runtime-cache/llm-report-service}/sglang.log}"
        START_MODEL="${START_SGLANG:-auto}"
        MODEL_STARTUP_TIMEOUT_S="${SGLANG_STARTUP_TIMEOUT_S:-300}"
        ;;
    vllm)
        MODEL_START_SCRIPT="${VLLM_START_SCRIPT:-${SCRIPT_DIR}/start_vllm.sh}"
        MODEL_LOG="${VLLM_LOG:-${REPORT_RUNTIME_DIR:-${ROOT_DIR}/.runtime-cache/llm-report-service}/vllm.log}"
        START_MODEL="${START_VLLM:-auto}"
        MODEL_STARTUP_TIMEOUT_S="${VLLM_STARTUP_TIMEOUT_S:-300}"
        ;;
    *) printf '不支持的 LLM_BACKEND：%s\n' "${LLM_BACKEND}" >&2; exit 2 ;;
esac
if [[ "${LLM_MODE}" == api ]]; then
    # 无论地址是否为 localhost、START_* 是否为 1，API 模式都不启动本地引擎。
    START_MODEL=0
fi
MODEL_LABEL="${LLM_BACKEND}"
if [[ "${LLM_MODE}" == api ]]; then MODEL_LABEL=API; fi
LLM_BASE_URL="${LLM_BASE_URL:-http://127.0.0.1:8000/v1}"
LLM_MODEL_ID="${LLM_MODEL_ID:-internvl3.5-8b}"
LLM_API_KEY="${LLM_API_KEY:-unused}"
LLM_CONNECT_TIMEOUT_S="${LLM_CONNECT_TIMEOUT_S:-5}"
REPORT_START_SCRIPT="${REPORT_START_SCRIPT:-${SCRIPT_DIR}/start_report.sh}"
AGENT_START_SCRIPT="${AGENT_START_SCRIPT:-${SCRIPT_DIR}/start_agent.sh}"
RUNTIME_DIR="${SERVICE_STACK_RUNTIME_DIR:-${ROOT_DIR}/.runtime-cache/service-stack/${MODEL_LABEL,,}}"
REPORT_LOG="${REPORT_STACK_LOG:-${RUNTIME_DIR}/report.log}"
AGENT_LOG="${AGENT_STACK_LOG:-${RUNTIME_DIR}/agent.log}"
export AGENT_JSONL_LOG="${AGENT_JSONL_LOG:-${RUNTIME_DIR}/agent.jsonl}"

AGENT_PORT="${AGENT_PORT:-8002}"
AGENT_STARTUP_TIMEOUT_S="${AGENT_STARTUP_TIMEOUT_S:-360}"
AGENT_HEALTH_URL="${AGENT_HEALTH_URL:-http://127.0.0.1:${AGENT_PORT}/health}"
AGENT_READY_URL="${AGENT_READY_URL:-http://127.0.0.1:${AGENT_PORT}/ready}"

MODEL_PID=""
REPORT_PID=""
AGENT_PID=""

usage() {
    cat <<EOF
用法：./scripts/start_all.sh [local|api|vllm|sglang] [--show-config]

启动内容：
  1. local 模式复用或启动本地模型；api 模式仅连接已配置的 API
  2. 通过 scripts/start_report.sh 启动报告 Worker
  3. 通过 scripts/start_agent.sh 启动 Agent 服务

常用覆盖配置：
  CUDA_VISIBLE_DEVICES=0,1
  LLM_MODE=local 或 api
  LLM_BACKEND=sglang 或 vllm（仅选择本地推理引擎）
  LLM_REMOTE_BASE_URL / LLM_REMOTE_MODEL_ID / LLM_REMOTE_API_KEY
  LLM_HEALTHCHECK=auto 或 models 或 none
  LLM_TP_SIZE=2
  LLM_GPU_MEMORY_UTILIZATION=0.70
  LLM_BASE_URL=http://127.0.0.1:8000/v1
  AGENT_PORT=8002
  DB_HOST=100.127.237.7
  SERVICE_STACK_RUNTIME_DIR=/path/to/logs
EOF
}

if [[ "${1:-}" == "--show-config" ]]; then
    "${CONFIG_PYTHON_BIN:-python3}" "${SCRIPT_DIR}/resolve_model_config.py"
    exit 0
fi
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
    exit 0
fi
if (($# > 0)); then
    printf '存在未识别的参数：%s\n' "$1" >&2
    usage >&2
    exit 2
fi

tail_log() {
    local label=$1
    local path=$2
    printf '%s 日志（%s）：\n' "${label}" "${path}" >&2
    tail -n 40 "${path}" >&2 2>/dev/null || true
}

model_healthcheck() {
    model_endpoint_ready
}

is_local_endpoint() {
    case "${LLM_BASE_URL}" in
        http://127.0.0.1:* | http://localhost:* | http://0.0.0.0:*) return 0 ;;
        *) return 1 ;;
    esac
}

stop_process() {
    local pid=$1
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
        kill "${pid}" 2>/dev/null || true
        wait "${pid}" 2>/dev/null || true
    fi
}

cleanup() {
    local exit_code=$?
    trap - EXIT INT TERM
    stop_process "${AGENT_PID}"
    stop_process "${REPORT_PID}"
    stop_process "${MODEL_PID}"
    exit "${exit_code}"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

for executable in "${REPORT_START_SCRIPT}" "${AGENT_START_SCRIPT}"; do
    if [[ ! -x "${executable}" ]]; then
        printf '找不到可执行的启动脚本：%s\n' "${executable}" >&2
        exit 1
    fi
done

mkdir -p "${RUNTIME_DIR}"

if model_healthcheck; then
    printf '模型接口已配置：模式=%s，接口=%s\n' "${MODEL_LABEL}" "${LLM_BASE_URL}"
else
    should_start=0
    case "${START_MODEL}" in
        1 | true | yes) should_start=1 ;;
        0 | false | no) ;;
        auto) if is_local_endpoint; then should_start=1; fi ;;
        *) printf 'START_MODEL 的值无效：%s\n' "${START_MODEL}" >&2; exit 2 ;;
    esac
    if [[ "${should_start}" != "1" ]]; then
        printf '%s 接口不可用：%s。请检查 API 配置或先启动模型服务。\n' "${MODEL_LABEL}" "${LLM_BASE_URL}" >&2
        exit 1
    fi
    if [[ ! -x "${MODEL_START_SCRIPT}" ]]; then
        printf '%s 启动脚本不存在或不可执行：%s\n' "${LLM_BACKEND}" "${MODEL_START_SCRIPT}" >&2
        exit 1
    fi
    printf '正在启动 %s，日志文件：%s\n' "${LLM_BACKEND}" "${MODEL_LOG}"
    prepare_log_file "${MODEL_LOG}" "${MODEL_LOG_WRITE_MODE}"
    "${MODEL_START_SCRIPT}" \
        >>"${MODEL_LOG}" 2>&1 &
    MODEL_PID=$!
    deadline=$((SECONDS + MODEL_STARTUP_TIMEOUT_S))
    until model_healthcheck; do
        if ! kill -0 "${MODEL_PID}" 2>/dev/null; then
            printf '%s 在启动过程中退出。\n' "${LLM_BACKEND}" >&2
            tail_log "Model" "${MODEL_LOG}"
            exit 1
        fi
        if ((SECONDS >= deadline)); then
            printf '等待 %s 超时（已等待 %s 秒）。\n' "${LLM_BACKEND}" "${MODEL_STARTUP_TIMEOUT_S}" >&2
            tail_log "Model" "${MODEL_LOG}"
            exit 1
        fi
        sleep 2
    done
    printf '%s 启动成功：%s\n' "${LLM_BACKEND}" "${LLM_BASE_URL}"
fi

printf '正在启动报告 Worker，日志：%s\n' "${REPORT_LOG}"
prepare_log_file "${REPORT_LOG}" "${REPORT_LOG_WRITE_MODE}"
"${REPORT_START_SCRIPT}" >>"${REPORT_LOG}" 2>&1 &
REPORT_PID=$!

printf '正在启动 Agent 服务，日志：%s\n' "${AGENT_LOG}"
prepare_log_file "${AGENT_LOG}" "${AGENT_LOG_WRITE_MODE}"
"${AGENT_START_SCRIPT}" >>"${AGENT_LOG}" 2>&1 &
AGENT_PID=$!

deadline=$((SECONDS + AGENT_STARTUP_TIMEOUT_S))
until curl --fail --silent --connect-timeout 2 --max-time 5 \
    "${AGENT_READY_URL}" >/dev/null 2>&1; do
    if ! kill -0 "${REPORT_PID}" 2>/dev/null; then
        printf '报告服务在启动阶段退出。\n' >&2
        tail_log "Report" "${REPORT_LOG}"
        exit 1
    fi
    if ! kill -0 "${AGENT_PID}" 2>/dev/null; then
        printf 'Agent 服务在启动阶段退出。\n' >&2
        tail_log "Agent" "${AGENT_LOG}"
        exit 1
    fi
    if [[ -n "${MODEL_PID}" ]] && ! kill -0 "${MODEL_PID}" 2>/dev/null; then
        printf '%s 模型服务在启动阶段退出。\n' "${LLM_BACKEND}" >&2
        tail_log "Model" "${MODEL_LOG}"
        exit 1
    fi
    if ((SECONDS >= deadline)); then
        printf '等待 Agent 就绪超时，已等待 %s 秒。\n' \
            "${AGENT_STARTUP_TIMEOUT_S}" >&2
        tail_log "Report" "${REPORT_LOG}"
        tail_log "Agent" "${AGENT_LOG}"
        exit 1
    fi
    sleep 2
done

printf '%s 模式的业务服务全部启动成功。\n' "${MODEL_LABEL}"
printf 'Agent 健康检查：%s\n' "${AGENT_HEALTH_URL}"
printf 'Agent 就绪检查：%s\n' "${AGENT_READY_URL}"
printf '报告日志：%s\n' "${REPORT_LOG}"
printf 'Agent 日志：%s\n' "${AGENT_LOG}"
printf 'Agent JSONL 日志：%s\n' "${AGENT_JSONL_LOG}"
printf '按 Ctrl+C 停止本脚本启动的服务。\n'

child_pids=("${REPORT_PID}" "${AGENT_PID}")
if [[ -n "${MODEL_PID}" ]]; then
    child_pids+=("${MODEL_PID}")
fi
set +e
wait -n "${child_pids[@]}"
child_exit_code=$?
set -e

if [[ -n "${MODEL_PID}" ]] && ! kill -0 "${MODEL_PID}" 2>/dev/null; then
    printf '%s 模型服务意外停止。\n' "${LLM_BACKEND}" >&2
    tail_log "Model" "${MODEL_LOG}"
    exit 1
elif ! kill -0 "${REPORT_PID}" 2>/dev/null; then
    printf '报告服务意外停止。\n' >&2
    tail_log "Report" "${REPORT_LOG}"
else
    printf 'Agent 服务意外停止。\n' >&2
    tail_log "Agent" "${AGENT_LOG}"
fi
exit "${child_exit_code}"
