#!/usr/bin/env bash

validate_log_write_mode() {
    case "$1" in
        append | overwrite) return 0 ;;
        *) printf '日志写入模式无效：%s（应为 append 或 overwrite）\n' "$1" >&2; return 2 ;;
    esac
}

prepare_log_file() {
    local path=$1
    local mode=$2
    validate_log_write_mode "${mode}" || return
    mkdir -p "$(dirname -- "${path}")"
    if [[ "${mode}" == "overwrite" ]]; then
        : >"${path}"
    else
        : >>"${path}"
    fi
}
