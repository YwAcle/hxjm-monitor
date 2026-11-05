#!/usr/bin/env bash
set -euo pipefail
HXJM_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${HXJM_ROOT}/modules/agent/python:${HXJM_ROOT}/modules/business/python:${HXJM_ROOT}/modules/ai-infra/python:${HXJM_ROOT}/modules/perception-devices/python:${HXJM_ROOT}/modules/infrastructure/python:${HXJM_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
exec "${HXJM_PYTHON:-python3}" "$@"
