#!/usr/bin/env bash
# 主监控 = 公共服务、BoT-SORT/ReID 与独立 JoyAI/Qwen。
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
action=${1:---help}
if (($#)); then shift; fi
case "$action" in
    --help|-h)
        echo '用法：bash scripts/main.sh start|stop|status [--config FILE] [--scope local|isolated|shared] [--build]'
        echo '需提前完成数据库、能力登记和 JoyAI prepare；停止保留数据库、Agent 和垃圾检测。'
        exit 0 ;;
    start|stop|status) ;;
    *) echo "未知操作：$action" >&2; exit 2 ;;
esac
args=()
while (($#)); do
    case "$1" in
        --config|--scope) [[ $# -ge 2 ]] || exit 2; args+=("$1" "$2"); shift 2 ;;
        --build) [[ "$action" == start ]] || exit 2; args+=("$1"); shift ;;
        *) echo "不支持参数：$1" >&2; exit 2 ;;
    esac
done
source "$ROOT/scripts/start.sh"
configure "${args[@]}" --only frontend,backend,mediamtx,stream,analysis,reid
[[ "$SCOPE" != dev ]] || { echo '主服务不支持前端专用 dev scope。' >&2; exit 2; }
case "$action" in
    start)
        bash "$ROOT/scripts/joyai-tool.sh" check
        bash "$ROOT/scripts/start.sh" "${args[@]}" --only "$ONLY"
        bash "$ROOT/scripts/joyai-tool.sh" start ;;
    stop)
        result=0
        bash "$ROOT/scripts/joyai-tool.sh" stop || result=$?
        bash "$ROOT/scripts/stop.sh" "${args[@]}" --only "$ONLY" || result=$?
        exit "$result" ;;
    status)
        result=0
        bash "$ROOT/scripts/start.sh" "${args[@]}" --only "$ONLY" --status || result=$?
        bash "$ROOT/scripts/joyai-tool.sh" status || result=$?
        exit "$result" ;;
esac
