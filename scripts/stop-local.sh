#!/usr/bin/env bash
# Stop only this worktree's applications. Port configuration is not needed to stop.
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/local-common.sh"
if "$CHECK_ONLY"; then
    if [[ -f "$RUN_DIR/active.json" ]]; then cat "$RUN_DIR/active.json"; else echo 'No active application recorded in this worktree.'; fi
    exit 0
fi
ensure_service_group "$SCRIPT_DIR/stop-local.sh" --worktree "$ROOT_DIR"
lock_runtime
runtime stop-all
stop_shared_service
verify_local_ports_stopped
printf '[stop-local] this worktree stopped; MySQL, PostgreSQL and Redis remain running\n'
