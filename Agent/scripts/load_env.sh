#!/usr/bin/env bash

load_env_defaults() {
    local env_file="$1"
    local entry key value

    if [[ -f "${env_file}" ]]; then
        while IFS= read -r entry || [[ -n "${entry}" ]]; do
            [[ -z "${entry}" || "${entry}" =~ ^[[:space:]]*# ]] && continue
            [[ "${entry}" == *=* ]] || continue
            key="${entry%%=*}"
            [[ "${key}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
            if [[ ! -v "${key}" ]]; then
                value="${entry#*=}"
                if [[ "${value}" == \"*\" || "${value}" == \'*\' ]]; then
                    value="${value:1:${#value}-2}"
                fi
                export "${key}=${value}"
            fi
        done < "${env_file}"
    fi
    # 共享 Python 配置解析，按 key=value 传递，无 eval、无 shell 展开。
    local resolver_dir resolved
    resolver_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
    resolved="$("${CONFIG_PYTHON_BIN:-python3}" "${resolver_dir}/resolve_model_config.py" --shell)" || return 1
    while IFS='=' read -r key value; do
        export "${key}=${value}"
    done <<< "${resolved}"
}

model_endpoint_ready() {
    local checker_dir model_check_status
    checker_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
    if "${CONFIG_PYTHON_BIN:-python3}" "${checker_dir}/check_model_endpoint.py"; then
        return 0
    else
        model_check_status=$?
        # 端口上有服务但模型不匹配时立即停止，不复用、不另起冲突服务。
        if [[ "${model_check_status}" == 2 ]]; then exit 2; fi
        return 1
    fi
}
