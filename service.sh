#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
[[ "${1:-}" != business ]] || shift
case "${1:-}" in
 start) shift; exec bash "$ROOT/scripts/start.sh" "$@";;
 stop) shift; exec bash "$ROOT/scripts/stop.sh" "$@";;
 status) shift; exec bash "$ROOT/scripts/start.sh" --status "$@";;
 prepare) shift; exec bash "$ROOT/scripts/start.sh" --build-only "$@";;
 restart) shift; bash "$ROOT/scripts/stop.sh" "$@"; exec bash "$ROOT/scripts/start.sh" "$@";;
 *) exec bash "$ROOT/scripts/start.sh" "$@";;
esac
