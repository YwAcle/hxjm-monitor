#!/usr/bin/env bash
# Source paths and runtime ownership are local to the selected worktree.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"
CHECK_ONLY=false
while (($#)); do
    case "$1" in
        --worktree) [[ $# -ge 2 ]] || { echo '--worktree requires a directory' >&2; exit 2; }; ROOT_DIR="$(cd -- "$2" && pwd -P)"; shift 2 ;;
        --check) CHECK_ONLY=true; shift ;;
        *) echo "Usage: $0 [--worktree DIRECTORY] [--check]" >&2; exit 2 ;;
    esac
done
COMMON_GIT_DIR="$(git -C "$ROOT_DIR" rev-parse --path-format=absolute --git-common-dir)"
PRIMARY_ROOT="$(dirname "$COMMON_GIT_DIR")"
# A copied Git repository is not automatically an algorithm owner.
if [[ -f "$ROOT_DIR/local-video.env" ]]; then source "$ROOT_DIR/local-video.env"; fi
ANALYSIS_ROOT="${HXJM_ANALYSIS_ROOT:-$PRIMARY_ROOT}"
[[ "$ANALYSIS_ROOT" == /* ]] || { echo 'HXJM_ANALYSIS_ROOT must be an absolute path.' >&2; exit 1; }
ANALYSIS_ROOT="$(realpath -m -- "$ANALYSIS_ROOT")"
RUN_DIR="$ROOT_DIR/.run/local-runtime"
LOG_DIR="$ROOT_DIR/log/local"
PORT_CONFIG="$ROOT_DIR/local-ports.env"
SERVICE_TOOL="$SCRIPT_DIR/local-runtime.py"
is_primary_worktree() { [[ "$ROOT_DIR" == "$PRIMARY_ROOT" ]]; }
is_analysis_owner() { [[ "$ROOT_DIR" == "$ANALYSIS_ROOT" ]]; }
stop_shared_service() {
    # Stop only this directory's supervisor, including copies left by older launchers.
    if [[ -d "$ROOT_DIR/.run/shared-botsort" ]]; then
        python3 "$ROOT_DIR/deploy/botsort/shared_service.py" stop --root "$ROOT_DIR"
    fi
}
PORT_KEYS=(FRONTEND_PORT BACKEND_PORT MTX_RTMP_PORT MTX_RTSP_PORT MTX_RTP_PORT
    MTX_RTCP_PORT MTX_HLS_PORT MTX_WEBRTC_PORT MTX_WEBRTC_ICE_PORT MTX_SRT_PORT
    MTX_PLAYBACK_PORT MTX_API_PORT AI_STREAM_PORT REDIS_DATABASE)
OPTIONAL_PORT_KEYS=(VIDEO_ANALYSIS_PORT VAD_PORT VAD_QWEN_PORT VAD_JOY_MODEL_PORT VAD_JOY_PORT VAD_DEEP_PORT)
load_port_config() {
    [[ -f "$PORT_CONFIG" ]] || { echo "Missing $PORT_CONFIG; run the launcher installer to create it." >&2; exit 1; }
    local line key value valid candidate
    local -A seen=()
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%$'\r'}"
        [[ "$line" =~ ^[[:space:]]*(#.*)?$ ]] && continue
        if [[ ! "$line" =~ ^[[:space:]]*([A-Z_]+)=(0|[1-9][0-9]*)[[:space:]]*(#.*)?$ ]]; then
            echo "Invalid line in $PORT_CONFIG: $line (expected KEY=NUMBER)" >&2; exit 1
        fi
        key=${BASH_REMATCH[1]}; value=${BASH_REMATCH[2]}; valid=false
        for candidate in "${PORT_KEYS[@]}" "${OPTIONAL_PORT_KEYS[@]}"; do [[ "$key" != "$candidate" ]] || valid=true; done
        "$valid" || { echo "Unknown setting in $PORT_CONFIG: $key" >&2; exit 1; }
        [[ ! -v "seen[$key]" ]] || { echo "Duplicate setting: $key" >&2; exit 1; }
        if [[ "$key" == REDIS_DATABASE ]]; then
            [[ ${#value} -le 2 && "$value" -le 15 ]] || { echo 'REDIS_DATABASE must be 0..15' >&2; exit 1; }
        else
            [[ ${#value} -le 5 && "$value" -ge 1 && "$value" -le 65535 ]] || { echo "Invalid port: $key=$value" >&2; exit 1; }
        fi
        seen[$key]=1
        export "$key=$value"
    done < "$PORT_CONFIG"
    for key in "${PORT_KEYS[@]}"; do
        [[ -v "seen[$key]" ]] || { echo "Missing $key in $PORT_CONFIG" >&2; exit 1; }
    done
}
load_video_config() {
    if is_analysis_owner; then
        if [[ -f "$ROOT_DIR/local-results.env" ]]; then source "$ROOT_DIR/local-results.env"; fi
    else
        # Personal applications never inherit permission to publish production results.
        export VIDEO_RESULTS_PERSIST_ENABLED=false
    fi
    export VIDEO_ANALYSIS_MODE="${VIDEO_ANALYSIS_MODE:-shared}"
    if ! is_analysis_owner && [[ "$VIDEO_ANALYSIS_MODE" != shared ]]; then
        echo 'This project only subscribes to shared analysis; local model startup is disabled.' >&2
        return 1
    fi
    export LOCAL_MEDIA_ORIGIN="http://127.0.0.1:$MTX_WEBRTC_PORT"
    case "$VIDEO_ANALYSIS_MODE" in
        local)
            if [[ -f "$ROOT_DIR/.run/video-analysis.env" ]]; then
                source "$ROOT_DIR/.run/video-analysis.env"
            fi
            export LOCAL_MEDIA_ENABLED=true
            ;;
        shared)
            export VIDEO_ANALYSIS_SHARED_ORIGIN="${VIDEO_ANALYSIS_SHARED_ORIGIN:-http://127.0.0.1:28010}"
            export SHARED_MEDIA_ORIGIN="$LOCAL_MEDIA_ORIGIN"
            export SHARED_MEDIA_RTSP_BASE="rtsp://127.0.0.1:$MTX_RTSP_PORT/live"
            export SHARED_MEDIA_API_ORIGIN="http://127.0.0.1:$MTX_API_PORT"
            export LOCAL_MEDIA_ENABLED=true
            if is_analysis_owner; then export LOCAL_MEDIA_ENABLED=false; fi
            ;;
        *) echo 'VIDEO_ANALYSIS_MODE must be shared or local.' >&2; return 1 ;;
    esac
}
runtime() { python3 "$SERVICE_TOOL" --state "$RUN_DIR" --root "$ROOT_DIR" "$@"; }
check_worktree_ports() {
    local key settings=()
    for key in "${PORT_KEYS[@]}" "${OPTIONAL_PORT_KEYS[@]}"; do
        [[ ! -v "$key" ]] || settings+=("$key=${!key}")
    done
    HXJM_ANALYSIS_ROOT="$ANALYSIS_ROOT" runtime check-ports "${settings[@]}"
}
start_infrastructure() {
    local healthy=true container status
    for container in smartmonitor-mysql smartmonitor-postgres smartmonitor-redis; do
        status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)"
        [[ "$status" == healthy ]] || healthy=false
    done
    if "$healthy"; then
        echo '[start-local] reusing healthy MySQL, PostgreSQL, and Redis.'
        return 0
    fi
    if ! is_analysis_owner; then
        echo '[start-local] error: Shared databases are not healthy; ask the primary project owner to start them. No shared containers were changed.' >&2
        return 1
    fi
    mkdir -p "$ANALYSIS_ROOT/.run"
    (
        exec 8>"$ANALYSIS_ROOT/.run/local-infrastructure.lock"
        flock -w 180 8 || { echo 'Timed out waiting for shared infrastructure.' >&2; exit 1; }
        docker compose -p "$INFRA_PROJECT" -f "$INFRA_COMPOSE_FILE" up -d \
            --no-recreate --wait --wait-timeout 180 mysql postgres redis
    )
}
ensure_service_group() {
    local group relaunch
    group="$(runtime service-group)" || return 1
    [[ -n "$group" ]] || return 0
    if command -v sg >/dev/null 2>&1 && [[ " $(id -nG "$(id -un)") " == *" $group "* ]]; then
        relaunch="$(python3 -c 'import shlex,sys; print(" ".join(map(shlex.quote, sys.argv[1:])))' bash "$@")" || return 1
        printf '[local-runtime] using existing %s group to manage this project.\n' "$group"
        exec sg "$group" -c "exec $relaunch"
    fi
    printf '[local-runtime] error: Cannot inspect this project; run with its service group: %s\n' "$group" >&2
    return 1
}
verify_local_ports_stopped() {
    [[ -f "$PORT_CONFIG" ]] || return 0
    local key value port listeners filter=''
    while IFS='=' read -r key value; do
        case "$key" in
            FRONTEND_PORT|BACKEND_PORT|AI_STREAM_PORT|MTX_RTMP_PORT|MTX_RTSP_PORT|MTX_HLS_PORT|MTX_WEBRTC_PORT|MTX_PLAYBACK_PORT|MTX_API_PORT)
                [[ "$value" =~ ^([1-9][0-9]{0,4})[[:space:]]*(#.*)?$ ]] || { echo "Invalid port: $key" >&2; return 1; }
                port=${BASH_REMATCH[1]}
                [[ "$port" -le 65535 ]] || return 1
                filter+="${filter:+ or }sport = :$port"
                ;;
        esac
    done < "$PORT_CONFIG"
    if is_analysis_owner; then
        [[ "${SHARED_BOTSORT_ANALYSIS_PORT:-28010}" =~ ^[1-9][0-9]{0,4}$ ]] || return 1
        filter+="${filter:+ or }sport = :${SHARED_BOTSORT_ANALYSIS_PORT:-28010}"
    fi
    [[ -n "$filter" ]] || return 0
    listeners="$(ss -H -ltn "( $filter )")" || return 1
    if [[ -n "$listeners" ]]; then
        printf '[stop-local] error: Application ports are still listening; stop is incomplete:\n%s\n' "$listeners" >&2
        return 1
    fi
}
ensure_docker_access() {
    command -v docker >/dev/null 2>&1 || { echo '[start-local] error: Docker is required.' >&2; return 1; }
    local error relaunch
    if error="$(docker info --format '{{.ServerVersion}}' 2>&1)"; then return 0; fi

    # Account membership can be newer than the groups inherited by an old terminal.
    if [[ "$error" == *'permission denied'* &&
          ( "$error" == *'unix:///var/run/docker.sock'* || "$error" == *'unix:///run/docker.sock'* ) ]] &&
       command -v sg >/dev/null 2>&1 &&
       [[ " $(id -nG "$(id -un)") " == *' docker '* && " $(id -nG) " != *' docker '* ]]; then
        relaunch="$(python3 -c 'import shlex,sys; print(" ".join(map(shlex.quote, sys.argv[1:])))' bash "$@")" || return 1
        echo '[start-local] activating existing docker group membership for this startup.'
        exec sg docker -c "exec $relaunch"
    fi

    printf '[start-local] error: Cannot access Docker; check daemon status and user/group permissions.\n%s\n' "$error" >&2
    return 1
}
lock_runtime() {
    mkdir -p "$RUN_DIR" "$LOG_DIR"
    exec 9>"$RUN_DIR/operation.lock"
    flock -n 9 || { echo "Another start/stop is running in $ROOT_DIR; retry when it finishes." >&2; exit 1; }
}
