#!/usr/bin/env bash
# 兼容旧路径：转发到根目录 scripts/start_sglang.sh。
set -euo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${ROOT_DIR}/scripts/start_sglang.sh" "$@"
