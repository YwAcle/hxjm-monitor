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
PRIMARY_ROOT="${HXJM_PRIMARY_ROOT:-$ROOT_DIR}"
if [[ -z "${HXJM_PRIMARY_ROOT:-}" && -f "$ROOT_DIR/.git" ]]; then
    IFS= read -r git_pointer < "$ROOT_DIR/.git"
    if [[ "$git_pointer" == 'gitdir: '* ]]; then
        git_directory="${git_pointer#gitdir: }"
        [[ "$git_directory" == /* ]] || git_directory="$ROOT_DIR/$git_directory"
        if [[ -f "$git_directory/commondir" ]]; then
            IFS= read -r common_directory < "$git_directory/commondir"
            [[ "$common_directory" == /* ]] || common_directory="$git_directory/$common_directory"
            PRIMARY_ROOT="$(cd -- "$common_directory/.." && pwd -P)"
        fi
    fi
fi
PRIMARY_ROOT="$(cd -- "$PRIMARY_ROOT" && pwd -P)"
RUN_DIR="$ROOT_DIR/.run/local-runtime"
LOG_DIR="$ROOT_DIR/log/local"
PORT_CONFIG="$ROOT_DIR/local-ports.env"
SERVICE_TOOL="$SCRIPT_DIR/local-runtime.py"
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
    export VIDEO_ANALYSIS_MODE="${VIDEO_ANALYSIS_MODE:-shared}"
    case "$VIDEO_ANALYSIS_MODE" in
        local)
            if [[ -f "$ROOT_DIR/.run/video-analysis.env" ]]; then
                source "$ROOT_DIR/.run/video-analysis.env"
            fi
            # Bootstrap-generated source/session mappings are deployment state,
            # kept separate from hand-maintained video settings and safe to
            # regenerate after the backend assigns stable UUIDs.
            if [[ -f "$ROOT_DIR/.run/yh-business-runtime.env" ]]; then
                source "$ROOT_DIR/.run/yh-business-runtime.env"
            fi
            # The business configuration names a token environment variable.
            # Load the deployment-local secret alongside the generated runtime
            # mapping so result/recording delivery can actually authenticate.
            if [[ -f "$ROOT_DIR/.run/yh-business-secrets.env" ]]; then
                source "$ROOT_DIR/.run/yh-business-secrets.env"
                export HXJM_YH_BUSINESS_TOKEN
            fi
            export LOCAL_MEDIA_ENABLED=true
            ;;
        shared)
            local shared_ports rtsp_port media_port api_port
            shared_ports="$(PORT_CONFIG="$PRIMARY_ROOT/local-ports.env"; load_port_config; printf '%s %s %s' "$MTX_RTSP_PORT" "$MTX_WEBRTC_PORT" "$MTX_API_PORT")" || return 1
            read -r rtsp_port media_port api_port <<< "$shared_ports"
            export VIDEO_ANALYSIS_SHARED_ORIGIN="${VIDEO_ANALYSIS_SHARED_ORIGIN:-http://127.0.0.1:28010}"
            export SHARED_MEDIA_ORIGIN="${SHARED_MEDIA_ORIGIN:-http://127.0.0.1:$media_port}"
            export SHARED_MEDIA_RTSP_BASE="rtsp://127.0.0.1:$rtsp_port/live"
            export SHARED_MEDIA_API_ORIGIN="http://127.0.0.1:$api_port"
            export LOCAL_MEDIA_ENABLED=true
            [[ "$ROOT_DIR" != "$PRIMARY_ROOT" ]] || export LOCAL_MEDIA_ENABLED=false
            ;;
        *) echo 'VIDEO_ANALYSIS_MODE must be shared or local.' >&2; return 1 ;;
    esac
}
runtime() { python3 "$SERVICE_TOOL" --state "$RUN_DIR" --root "$ROOT_DIR" "$@"; }
lock_runtime() {
    mkdir -p "$RUN_DIR" "$LOG_DIR"
    exec 9>"$RUN_DIR/operation.lock"
    flock -n 9 || { echo "Another start/stop is running in $ROOT_DIR; retry when it finishes." >&2; exit 1; }
}
