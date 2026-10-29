#!/usr/bin/env bash
# 兼容旧路径：转发到统一的 scripts/start_all.sh。
set -euo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export LLM_BACKEND=sglang
exec "${ROOT_DIR}/scripts/start_all.sh" "$@"
