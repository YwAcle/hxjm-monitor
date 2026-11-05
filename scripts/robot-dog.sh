#!/usr/bin/env bash
# 设备 Adapter 在共享后端运行；此入口只管理独立垃圾检测实例。
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
action=${1:---help}
if (($#)); then shift; fi
case "$action" in
    --help|-h)
        echo '用法：bash scripts/robot-dog.sh start|stop|status [--config FILE] [--scope local|isolated|shared] [--build]'
        echo '先启动公共后端和媒体服务，并完成垃圾能力登记；不会启动机器人控制程序或下发动作。'
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
case "$action" in
    start) exec bash "$ROOT/scripts/start.sh" "${args[@]}" --only garbage-analysis ;;
    stop) exec bash "$ROOT/scripts/stop.sh" "${args[@]}" --only garbage-analysis ;;
    status) exec bash "$ROOT/scripts/start.sh" "${args[@]}" --only garbage-analysis --status ;;
esac
