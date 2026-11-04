#!/usr/bin/env bash
# Explicit migration of an existing PostgreSQL container; normal startup never migrates.
set -euo pipefail
# Schema locks should fail quickly rather than blocking a live video writer.
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
if [[ $# != 1 ]]; then echo 'Usage: bash scripts/migrate-capabilities.sh POSTGRES_CONTAINER' >&2; exit 2; fi
docker exec -i "$1" sh -c 'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$ROOT/python/base/postgresql/stage4/006_capability_http.sql"
