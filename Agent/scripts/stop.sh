#!/usr/bin/env bash
# 唯一公开停止入口；不读取模型配置，不停止复用的外部模型。
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
    printf '用法：bash Agent/scripts/stop.sh\n停止本入口创建的 Agent、报告 Worker 和本地模型；保留复用的模型服务。\n'
    exit 0
fi
if (($#)); then printf '停止命令不接受参数。\n' >&2; exit 2; fi
exec "${CONFIG_PYTHON_BIN:-python3}" "${SCRIPT_DIR}/internal/manage.py" stop
