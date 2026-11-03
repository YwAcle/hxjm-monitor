#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/start.sh"
configure "$@"
if "$STATUS" || "$CHECK"; then "${COMPOSE[@]}" ps --all; exit; fi
[[ "$SCOPE" != shared ]] || echo 'Explicitly stopping PUBLIC services; other developers may use them.'
"${COMPOSE[@]}" stop "${SERVICES[@]}"
echo "Stopped $COMPOSE_PROJECT_NAME: $ONLY; databases and volumes retained."
