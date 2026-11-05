#!/usr/bin/env bash
# 复用现有 Agent、报告 Worker 和模型进程管理。
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
action=${1:---help}
if (($#)); then shift; fi
case "$action" in
    start|stop)
        (($# == 0)) || { echo "无需模式参数，请使用：bash scripts/agent.sh $action" >&2; exit 2; }
        export LLM_MODE=local LLM_BACKEND=vllm
        exec bash "$ROOT/apps/llm/scripts/$action.sh" ;;
    --help|-h) echo '用法：bash scripts/agent.sh start | stop' ;;
    *) echo "未知操作：$action" >&2; exit 2 ;;
esac
