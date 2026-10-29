#!/usr/bin/env bash
# Start the locally developed SmartMonitor services in dependency order.
set -euo pipefail

source "$(dirname -- "${BASH_SOURCE[0]}")/local-common.sh"
load_port_config
load_video_config
MTX_DIR="$ROOT_DIR/mtx"
# Persistent volumes/bind mounts always come from the primary worktree.
INFRA_COMPOSE_FILE="${INFRA_COMPOSE_FILE:-$PRIMARY_ROOT/scripts/local-infra.compose.yml}"
INFRA_PROJECT="${INFRA_PROJECT:-hxjm}"
MEDIAMTX_BIN="${MEDIAMTX_BIN:-$MTX_DIR/mediamtx/mediamtx}"
if [[ ! -x "$MEDIAMTX_BIN" ]]; then MEDIAMTX_BIN="$PRIMARY_ROOT/mtx/mediamtx/mediamtx"; fi
CONDA_BIN="${CONDA_BIN:-/home/guest/anaconda3/bin/conda}"
JAVA_BIN="${JAVA_BIN:-/usr/lib/jvm/java-8-openjdk-amd64/bin/java}"
VAD_PYTHON="${VAD_PYTHON:-/home/guest/anaconda3/envs/vad/bin/python}"
DEEPSORT_PYTHON="${DEEPSORT_PYTHON:-/home/guest/anaconda3/envs/deepsort/bin/python}"
VIDEO_ANALYSIS_PYTHON="${VIDEO_ANALYSIS_PYTHON:-/home/guest/anaconda3/envs/botsort39/bin/python}"
VIDEO_ANALYSIS_PORT="${VIDEO_ANALYSIS_PORT:-$((25010 + FRONTEND_PORT))}"
START_VIDEO_ANALYSIS="${START_VIDEO_ANALYSIS:-yes}"
START_REID_FEATURE="${START_REID_FEATURE:-no}"
REID_FEATURE_PYTHON="${REID_FEATURE_PYTHON:-/home/guest/anaconda3/envs/reid/bin/python}"
REID_FEATURE_PORT="${REID_FEATURE_PORT:-28024}"
[[ "$VIDEO_ANALYSIS_MODE" != shared ]] || START_VIDEO_ANALYSIS=no
export VIDEO_ANALYSIS_ALGORITHM="${VIDEO_ANALYSIS_ALGORITHM:-botsort}"
MAVEN_BIN="${MAVEN_BIN:-mvn}"
# Interactive startup asks which algorithm services to run. Set
# START_ALGORITHMS=no for non-algorithm raw-camera-only startup.
START_ALGORITHMS="${START_ALGORITHMS:-no}"
START_REID="${START_REID:-}"
START_VAD="${START_VAD:-}"
START_DEEPSORT="${START_DEEPSORT:-}"
export REID_ZMQ_ADDR="ipc://$RUN_DIR/ipc/boxmot.ipc"
export VAD_ZMQ_ADDR="ipc://$RUN_DIR/ipc/vad.ipc"
export DEEPSORT_ZMQ_ADDR="ipc://$RUN_DIR/ipc/deepsort.ipc"
export SMARTMONITOR_AI_CONTROL_TOKEN="${SMARTMONITOR_AI_CONTROL_TOKEN:-change-me-before-production}"
export AI_STREAM_SHM_NAMESPACE="$(printf '%s' "$ROOT_DIR" | sha256sum | cut -c 1-12)"
AI_STREAM_CONTROL_TOKEN="${SMARTMONITOR_AI_CONTROL_TOKEN:-change-me-before-production}"
export CAMERA_IDS="${CAMERA_IDS:-1 2 3 4}"
CAMERA_TASK="${CAMERA_TASK:-boxmot}"
PUBLIC_HOST="${PUBLIC_HOST:-192.168.109.191}"


info() { printf '[start-local] %s\n' "$*"; }
warn() { printf '[start-local] warning: %s\n' "$*" >&2; }
fail() { printf '[start-local] error: %s\n' "$*" >&2; exit 1; }

prompt_algorithm() {
    local name=$1
    local env_name=$2
    local answer=${!env_name:-}

    if [[ -n "$answer" ]]; then
        answer=${answer,,}
    elif [[ -t 0 ]]; then
        while true; do
            read -r -p "[start-local] start $name algorithm? [yes/no]: " answer
            answer=${answer,,}
            case "$answer" in
                yes|no) break ;;
                *) warn "please enter yes or no." ;;
            esac
        done
    else
        warn "non-interactive input: $env_name is not set; $name will not start."
        return 1
    fi

    case "$answer" in
        yes) return 0 ;;
        no) return 1 ;;
        *) fail "$env_name must be yes or no." ;;
    esac
}

pid_is_running() {
    local name
    name="$(basename "$1" .pid)"
    runtime status "$name"
}

start_service() {
    local name=$1 workdir=$2
    shift 2
    runtime start "$name" "$workdir" "$LOG_DIR/$name.log" "$@"
}

check_port_available() {
    local port=$1
    local service=$2
    local listener

    listener="$(ss -H -ltnp "sport = :$port")" || fail "Cannot inspect TCP ports with ss."
    [[ -z "$listener" ]] && return 0

    warn "$service cannot start because TCP port $port is already in use:"
    printf '%s\n' "$listener" >&2
    return 1
}

check_udp_port_available() {
    local port=$1
    local service=$2
    local listener

    listener="$(ss -H -lunp "sport = :$port")" || fail "Cannot inspect UDP ports with ss."
    [[ -z "$listener" ]] && return 0

    warn "$service cannot start because UDP port $port is already in use:"
    printf '%s\n' "$listener" >&2
    return 1
}

ensure_local_ports_available() {
    local conflict=false

    # MediaMTX aborts completely when any enabled listener cannot bind.
    if "$LOCAL_MEDIA_ENABLED" && ! pid_is_running "$RUN_DIR/mediamtx.pid"; then
        local port
        for port in "$MTX_RTMP_PORT" "$MTX_RTSP_PORT" "$MTX_HLS_PORT" \
            "$MTX_WEBRTC_PORT" "$MTX_PLAYBACK_PORT" "$MTX_API_PORT"; do
            check_port_available "$port" mediamtx || conflict=true
        done
        for port in "$MTX_RTP_PORT" "$MTX_RTCP_PORT" "$MTX_WEBRTC_ICE_PORT" "$MTX_SRT_PORT"; do
            check_udp_port_available "$port" mediamtx || conflict=true
        done
    fi
    if ! pid_is_running "$RUN_DIR/ai_stream.pid"; then
        check_port_available "$AI_STREAM_PORT" ai_stream || conflict=true
    fi
    if ! pid_is_running "$RUN_DIR/backend.pid"; then
        check_port_available "$BACKEND_PORT" backend || conflict=true
    fi
    if ! pid_is_running "$RUN_DIR/frontend.pid"; then
        check_port_available "$FRONTEND_PORT" frontend || conflict=true
    fi
    if [[ "$START_VIDEO_ANALYSIS" == yes ]] && ! runtime status video_analysis; then
        check_port_available "$VIDEO_ANALYSIS_PORT" video_analysis || conflict=true
    fi
    if [[ "$START_REID_FEATURE" == yes ]] && ! runtime status reid_feature; then
        check_port_available "$REID_FEATURE_PORT" reid_feature || conflict=true
    fi

    if "$conflict"; then
        fail "stop the conflicting services and run start-local.sh again."
    fi
}

wait_for_port() {
    local port=$1
    local name=$2
    local attempts=${3:-30}

    for ((i = 1; i <= attempts; i++)); do
        if ! pid_is_running "$RUN_DIR/$name.pid"; then
            warn "$name exited before listening on port $port; inspect $LOG_DIR/$name.log."
            return 1
        fi
        if [[ -n "$(ss -H -ltn "sport = :$port")" ]]; then
            info "$name is listening on port $port."
            return 0
        fi
        sleep 1
    done

    warn "$name did not listen on port $port within $attempts seconds; inspect $LOG_DIR/$name.log."
    return 1
}

wait_for_backend() {
    local attempts=${1:-60} attempt status
    for ((attempt=1; attempt<=attempts; attempt++)); do
        pid_is_running "$RUN_DIR/backend.pid" || return 1
        status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
            --connect-timeout 1 --max-time 2 "http://127.0.0.1:$BACKEND_PORT/captchaImage" || true)"
        if [[ "$status" == 200 ]]; then
            info "backend is healthy (captchaImage HTTP 200)."
            return 0
        fi
        sleep 1
    done
    return 1
}

wait_for_vad_health() {
    local addr=${1:-ipc:///tmp/py_ai_vad.ipc}
    local attempts=${2:-30}

    for ((i = 1; i <= attempts; i++)); do
        if "$VAD_PYTHON" -c '
import sys
import zmq

socket = zmq.Context.instance().socket(zmq.REQ)
socket.setsockopt(zmq.LINGER, 0)
socket.setsockopt(zmq.RCVTIMEO, 1000)
socket.setsockopt(zmq.SNDTIMEO, 1000)
socket.connect(sys.argv[1])
try:
    socket.send_json({"task": "__health__"})
    if socket.recv_string() != "OK":
        raise SystemExit(1)
except zmq.ZMQError:
    raise SystemExit(1)
' "$addr"; then
            info "vad is healthy at $addr."
            return 0
        fi
        sleep 1
    done

    warn "vad did not pass its health check within $attempts seconds; inspect $LOG_DIR/vad.log."
    return 1
}

start_algorithm_camera_tasks() {
    local task_name=$1 camera_id response status body
    info "starting $task_name through this worktree's ai_stream (port $AI_STREAM_PORT)."
    for camera_id in $CAMERA_IDS; do
        [[ "$camera_id" =~ ^[0-9]+$ ]] || fail "CAMERA_IDS contains an invalid camera id: $camera_id"
        response="$(curl --silent --show-error --connect-timeout 5 --max-time 60 \
            -w $'\n%{http_code}' \
            -X POST "http://127.0.0.1:$AI_STREAM_PORT/internal/v1/cameras/$camera_id/tasks" \
            -H 'Content-Type: application/json' \
            -H "X-Ai-Stream-Token: $AI_STREAM_CONTROL_TOKEN" \
            -d "{\"task\":\"$task_name\",\"inputUrl\":\"rtsp://127.0.0.1:$MTX_RTSP_PORT/live/camera_${camera_id}\",\"outputUrl\":\"rtsp://127.0.0.1:$MTX_RTSP_PORT/live/camera_${camera_id}_${task_name}\"}")" \
            || fail "Could not start $task_name for camera $camera_id; inspect $LOG_DIR/ai_stream.log."
        status="${response##*$'\n'}"
        body="${response%$'\n'*}"
        [[ "$status" == 200 ]] || { printf '%s\n' "$body" >&2; fail "ai_stream rejected $task_name for camera $camera_id."; }
        info "camera $camera_id $task_name task accepted."
    done
}

start_original_camera_sources() {
    if ! "$LOCAL_MEDIA_ENABLED"; then
        info 'using camera sources owned by the shared MediaMTX service.'
        return 0
    fi
    command -v curl >/dev/null 2>&1 || fail "curl is required to create camera sources."
    command -v python3 >/dev/null 2>&1 || fail "python3 is required to encode camera source configuration."

    local camera_id source payload status cameras
    if [[ "$VIDEO_ANALYSIS_MODE" == shared ]]; then
        cameras="$(for camera_id in $CAMERA_IDS; do
            [[ "$camera_id" =~ ^[0-9]+$ ]] || exit 1
            printf '%s\t%s/camera_%s\n' "$camera_id" "$SHARED_MEDIA_RTSP_BASE" "$camera_id"
        done)" || fail 'CAMERA_IDS must contain numeric camera IDs.'
        info 'relaying shared camera sources; cameras are opened only by the public service.'
    else
        cameras="$(docker exec smartmonitor-mysql mysql -uroot -p123456 -N -B hxjm_sm \
            -e "SELECT machine_id, video_url FROM ba_machine WHERE isvalid=1 AND status=1 ORDER BY machine_id;" 2>/dev/null)" \
            || fail "Could not query camera sources from MySQL."
        info "starting original camera sources from ba_machine."
    fi
    while IFS=$'\t' read -r camera_id source; do
        [[ "$camera_id" =~ ^[0-9]+$ && -n "$source" ]] || continue
        payload="$(python3 -c 'import json,sys; shared = sys.argv[2] == "shared"; data = {"source": sys.argv[1], "rtspTransport": "tcp" if shared else "udp", "sourceOnDemand": True, "sourceOnDemandStartTimeout": "10s", "sourceOnDemandCloseAfter": "10s"}; data.update({"record": False} if shared else {}); print(json.dumps(data))' "$source" "$VIDEO_ANALYSIS_MODE")"
        status="$(curl --silent --show-error --connect-timeout 5 --max-time 15 \
            -o /dev/null -w '%{http_code}' \
            -X POST "http://127.0.0.1:$MTX_API_PORT/v3/config/paths/add/live/camera_${camera_id}" \
            -H 'Content-Type: application/json' -d "$payload")" \
            || fail "could not create original source for camera $camera_id."
        case "$status" in
            200|201) info "camera $camera_id original source configured." ;;
            400|409)
                # Existing paths must follow the authoritative device configuration.
                if curl --fail --silent --show-error --connect-timeout 5 --max-time 10 \
                    "http://127.0.0.1:$MTX_API_PORT/v3/config/paths/get/live/camera_${camera_id}" \
                    >/dev/null; then
                    status="$(curl --silent --show-error --connect-timeout 5 --max-time 15 \
                        -o /dev/null -w '%{http_code}' \
                        -X PATCH "http://127.0.0.1:$MTX_API_PORT/v3/config/paths/patch/live/camera_${camera_id}" \
                        -H 'Content-Type: application/json' -d "$payload")" \
                        || fail "could not update original source for camera $camera_id."
                    [[ "$status" == 200 ]] || fail "MediaMTX rejected original source update for camera $camera_id (HTTP $status)."
                    info "camera $camera_id original source synchronized."
                else
                    fail "MediaMTX rejected original source for camera $camera_id (HTTP $status)."
                fi
                ;;
            *) fail "MediaMTX rejected original source for camera $camera_id (HTTP $status)." ;;
        esac
    done <<< "$cameras"
}

wait_for_camera_outputs() {
    local task_name=${1:-$CAMERA_TASK}
    local attempts=${2:-45}
    local camera_id path response all_ready

    info "waiting for MediaMTX $task_name outputs."
    for ((i = 1; i <= attempts; i++)); do
        all_ready=true
        for camera_id in $CAMERA_IDS; do
            path="live/camera_${camera_id}_${task_name}"
            response="$(curl --fail --silent --show-error --connect-timeout 2 --max-time 5 \
                "http://127.0.0.1:$MTX_API_PORT/v3/paths/get/$path" 2>/dev/null || true)"
            if [[ "$response" != *'"ready":true'* ]]; then
                all_ready=false
                break
            fi
        done
        if "$all_ready"; then
            info "all camera $task_name outputs are ready."
            return 0
        fi
        sleep 1
    done

    warn "camera outputs are not ready yet; the frontend will use original streams until the algorithm service recovers."
    return 0
}

start_infrastructure() {
    if [[ "${HXJM_EXISTING_INFRA_ONLY:-no}" == yes ]]; then
        local container status
        for container in smartmonitor-mysql smartmonitor-postgres smartmonitor-redis; do
            status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container")" || return 1
            [[ "$status" == healthy ]] || fail "Existing infrastructure is not healthy: $container"
        done
        info "reusing existing infrastructure; container creation is disabled."
        return 0
    fi
    command -v docker >/dev/null 2>&1 || fail "Docker is required to start MySQL, PostgreSQL, and Redis."
    docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is required."
    [[ -f "$INFRA_COMPOSE_FILE" ]] || fail "Infrastructure Compose file not found: $INFRA_COMPOSE_FILE"

    (
        exec 8>"$PRIMARY_ROOT/.run/local-infrastructure.lock"
        flock -w 180 8 || fail "Timed out waiting for shared infrastructure."
        local healthy=true container status
        for container in smartmonitor-mysql smartmonitor-postgres smartmonitor-redis; do
            status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)"
            [[ "$status" == healthy ]] || healthy=false
        done
        if "$healthy"; then
            info "reusing healthy MySQL, PostgreSQL, and Redis."
        else
            info "starting shared MySQL, PostgreSQL, and Redis."
            docker compose -p "$INFRA_PROJECT" -f "$INFRA_COMPOSE_FILE" up -d \
                --wait --wait-timeout 180 mysql postgres redis
        fi
    )
}

ensure_postgres_schema() {
    [[ "${HXJM_EXISTING_INFRA_ONLY:-no}" != yes ]] || return 0
    local schema_file="$ROOT_DIR/SmartMonitor-wangzj/sql/ai_task_run.sql"
    [[ -f "$schema_file" ]] || fail "PostgreSQL schema file is missing: $schema_file"
    info "ensuring PostgreSQL task-run schema."
    docker exec -i smartmonitor-postgres psql -v ON_ERROR_STOP=1 -U root -d postgres < "$schema_file" \
        || fail "Could not initialize PostgreSQL task-run schema."
}

build_ai_stream() {
    command -v cmake >/dev/null 2>&1 || fail "CMake is required to build ai_stream."
    [[ -f "$MTX_DIR/CMakeLists.txt" ]] || fail "ai_stream source tree is missing: $MTX_DIR"

    info "building ai_stream (incremental)."
    cmake -S "$MTX_DIR" -B "$MTX_DIR/build" -DCMAKE_BUILD_TYPE=Release \
        || return 1
    cmake --build "$MTX_DIR/build" --target ai_stream --parallel "${BUILD_JOBS:-4}" \
        || return 1
}

build_backend() {
    command -v "$MAVEN_BIN" >/dev/null 2>&1 || fail "Maven is required to build the backend."
    info "building backend."
    (
        cd "$ROOT_DIR/SmartMonitor-wangzj"
        JAVA_HOME="$(dirname "$(dirname "$JAVA_BIN")")" \
            PATH="$(dirname "$JAVA_BIN"):$PATH" \
            "$MAVEN_BIN" -pl hxjm-admin -am clean package -DskipTests -q
    ) || return 1
}

[[ -x "$MEDIAMTX_BIN" ]] || fail "MediaMTX executable missing; set MEDIAMTX_BIN to an installed executable."
[[ -x "$JAVA_BIN" ]] || fail "Java 8 not found: $JAVA_BIN (set JAVA_BIN to a Java 8 executable)."
[[ -f "$ROOT_DIR/SmartMonitor-wangzj/pom.xml" ]] || fail "Backend source tree is missing."
command -v npm >/dev/null 2>&1 || fail "npm is not available in PATH."

command -v python3 >/dev/null || fail "Python 3 is required."
command -v flock >/dev/null || fail "flock is required."
command -v ss >/dev/null || fail "ss (iproute2) is required."
command -v "$MAVEN_BIN" >/dev/null || fail "Maven is required."
command -v cmake >/dev/null || fail "CMake is required."
node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 18 ? 0 : 1)' \
    || fail "Node.js 18+ is required."
if "$CHECK_ONLY"; then
    info "source directory: $ROOT_DIR"
    info "port configuration: $PORT_CONFIG"
    info "worktree state: $RUN_DIR"
    info "MediaMTX executable: $MEDIAMTX_BIN; source configuration: $MTX_DIR/mediamtx/mediamtx.yml"
    info "frontend/backend: $FRONTEND_PORT/$BACKEND_PORT; RTSP/WebRTC: $MTX_RTSP_PORT/$MTX_WEBRTC_PORT"
    info "video analysis mode: $VIDEO_ANALYSIS_MODE; local MediaMTX: $LOCAL_MEDIA_ENABLED"
    if [[ "$VIDEO_ANALYSIS_MODE" == shared ]]; then
        info "shared analysis/media: $VIDEO_ANALYSIS_SHARED_ORIGIN / $SHARED_MEDIA_ORIGIN"
    else
        info "video analysis: $VIDEO_ANALYSIS_ALGORITHM on $VIDEO_ANALYSIS_PORT ($VIDEO_ANALYSIS_PYTHON)"
    fi
    info "media API/ai-stream: $MTX_API_PORT/$AI_STREAM_PORT; Redis database: $REDIS_DATABASE"
    info "IPC: $RUN_DIR/ipc/; shared-memory namespace: $AI_STREAM_SHM_NAMESPACE"
    exit 0
fi
if [[ "$VIDEO_ANALYSIS_MODE" == shared ]]; then
    [[ -f "$PRIMARY_ROOT/deploy/botsort/shared_service.py" ]] \
        || fail 'Update the primary checkout first: deploy/botsort/shared_service.py is missing.'
fi
[[ "${START_ALGORITHMS,,}" == yes || "${START_ALGORITHMS,,}" == no ]] || fail "START_ALGORITHMS must be yes or no."
[[ "$START_VIDEO_ANALYSIS" == yes || "$START_VIDEO_ANALYSIS" == no ]] || fail "START_VIDEO_ANALYSIS must be yes or no."
[[ "$START_REID_FEATURE" == yes || "$START_REID_FEATURE" == no ]] || fail "START_REID_FEATURE must be yes or no."
if [[ "$START_REID_FEATURE" == yes ]]; then
    [[ "$REID_FEATURE_PORT" =~ ^[0-9]+$ && "$REID_FEATURE_PORT" -ge 1 && "$REID_FEATURE_PORT" -le 65535 ]] || fail 'Invalid REID_FEATURE_PORT'
    PYTHONPATH="$ROOT_DIR/.run/reid-feature-deps${PYTHONPATH:+:$PYTHONPATH}" \
        "$REID_FEATURE_PYTHON" -B -c 'import torch, fastapi, uvicorn, multipart, PIL' || fail 'Missing ReID feature dependencies'
fi
if [[ "$START_VIDEO_ANALYSIS" == yes ]]; then
    [[ "$VIDEO_ANALYSIS_PORT" =~ ^[0-9]+$ && "$VIDEO_ANALYSIS_PORT" -ge 1 && "$VIDEO_ANALYSIS_PORT" -le 65535 ]] || fail 'Invalid VIDEO_ANALYSIS_PORT'
    PYTHONPATH="$ROOT_DIR/.run/media-deps${PYTHONPATH:+:$PYTHONPATH}" \
        "$VIDEO_ANALYSIS_PYTHON" -B -c 'import fastapi, uvicorn, websockets, cv2, numpy, av' || fail 'Missing analysis API dependencies in VIDEO_ANALYSIS_PYTHON'
fi
for port in "$BACKEND_PORT" "$FRONTEND_PORT" "$MTX_RTSP_PORT" "$AI_STREAM_PORT"; do
    [[ "$port" =~ ^[0-9]+$ && "$port" -ge 1 && "$port" -le 65535 ]] || fail "Invalid port: $port"
done
lock_runtime

start_reid=false
start_vad=false
start_deepsort=false
if [[ "${START_ALGORITHMS,,}" == "yes" ]]; then
    prompt_algorithm "ReID" START_REID && start_reid=true || true
    prompt_algorithm "VAD" START_VAD && start_vad=true || true
    prompt_algorithm "DeepSORT detection" START_DEEPSORT && start_deepsort=true || true
else
    info "algorithm services disabled (raw-camera-only mode)."
fi

if "$start_reid"; then
    [[ -x "$CONDA_BIN" ]] || fail "Conda not found: $CONDA_BIN (set CONDA_BIN to the conda executable)."
fi
if "$start_vad"; then
    [[ -x "$VAD_PYTHON" ]] || fail "VAD Python not found: $VAD_PYTHON (set VAD_PYTHON to the vad environment Python)."
fi
if "$start_deepsort"; then
    [[ "$VIDEO_ANALYSIS_MODE" == local && "$START_VIDEO_ANALYSIS" == no ]] || fail 'Use VIDEO_ANALYSIS_MODE=local START_VIDEO_ANALYSIS=no before selecting legacy DeepSORT'
    [[ -x "$DEEPSORT_PYTHON" ]] || fail "DeepSORT Python not found: $DEEPSORT_PYTHON (set DEEPSORT_PYTHON to the reid environment Python)."
fi

python3 "$SCRIPT_DIR/local-config.py" "$ROOT_DIR" "$RUN_DIR"
runtime prepare-assets "$PRIMARY_ROOT" "$start_reid" "$start_vad" "$start_deepsort"

# Prepare artifacts before switching off the previous application.
if [[ "${HXJM_SKIP_BUILD:-no}" != yes ]]; then
info "building current C++ and backend sources; logs: $LOG_DIR/build-*.log"
build_ai_stream >"$LOG_DIR/build-ai-stream.log" 2>&1 || fail "C++ build failed; see $LOG_DIR/build-ai-stream.log"
build_backend >"$LOG_DIR/build-backend.log" 2>&1 || fail "Backend build failed; see $LOG_DIR/build-backend.log"
frontend_hash="$(sha256sum "$ROOT_DIR/lanhu/package.json" "$ROOT_DIR/lanhu/package-lock.json" | sha256sum | cut -d ' ' -f 1)"
if [[ ! -x "$ROOT_DIR/lanhu/node_modules/.bin/vite" || ! -f "$ROOT_DIR/lanhu/node_modules/.local-deps.sha256" || "$(cat "$ROOT_DIR/lanhu/node_modules/.local-deps.sha256")" != "$frontend_hash" ]]; then
    info "installing this worktree's frontend dependencies; log: $LOG_DIR/install-frontend.log"
    (cd "$ROOT_DIR/lanhu" && npm ci --no-audit --no-fund) >"$LOG_DIR/install-frontend.log" 2>&1 \
        || fail "npm ci failed; see $LOG_DIR/install-frontend.log"
    printf '%s\n' "$frontend_hash" > "$ROOT_DIR/lanhu/node_modules/.local-deps.sha256"
fi
else
    [[ -x "$MTX_DIR/build/ai_stream" && -f "$ROOT_DIR/SmartMonitor-wangzj/hxjm-admin/target/hxjm-admin.jar" && -x "$ROOT_DIR/lanhu/node_modules/.bin/vite" ]] || fail "Run service.sh business prepare first."
fi
start_infrastructure
ensure_postgres_schema
info "restarting services from $ROOT_DIR."
runtime stop-all
# Roll back every new service if readiness/startup fails.
startup_complete=false
cleanup_failed_start() {
    local result=$?
    if ! "$startup_complete"; then
        warn "startup failed; stopping the partial application (logs are retained)."
        runtime stop-all || true
    fi
    return "$result"
}
trap cleanup_failed_start EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
ensure_local_ports_available
if [[ "$VIDEO_ANALYSIS_MODE" == shared ]]; then
    if ! python3 "$PRIMARY_ROOT/deploy/botsort/shared_service.py" start --root "$PRIMARY_ROOT"; then
        if curl --fail --silent --show-error --connect-timeout 2 --max-time 5 \
            "$SHARED_MEDIA_API_ORIGIN/v3/paths/list" >/dev/null; then
            warn 'Shared analysis is unavailable; the ready shared media service will keep raw video playable.'
        else
            fail 'Shared media service did not start; inspect its output above.'
        fi
    fi
fi

# Override listener addresses and file-only logging for the local process.
if "$LOCAL_MEDIA_ENABLED"; then
start_service mediamtx "$MTX_DIR/mediamtx" env \
    MTX_LOGDESTINATIONS=stdout \
    MTX_RTMPADDRESS=":$MTX_RTMP_PORT" \
    MTX_RTSPADDRESS=":$MTX_RTSP_PORT" \
    MTX_RTPADDRESS=":$MTX_RTP_PORT" \
    MTX_RTCPADDRESS=":$MTX_RTCP_PORT" \
    MTX_HLSADDRESS=":$MTX_HLS_PORT" \
    MTX_WEBRTCADDRESS=":$MTX_WEBRTC_PORT" \
    MTX_WEBRTCLOCALUDPADDRESS=":$MTX_WEBRTC_ICE_PORT" \
    MTX_SRTADDRESS=":$MTX_SRT_PORT" \
    MTX_PLAYBACKADDRESS=":$MTX_PLAYBACK_PORT" \
    MTX_API=yes \
    MTX_APIADDRESS=":$MTX_API_PORT" \
    SMARTMONITOR_BACKEND_PORT="$BACKEND_PORT" \
    "$MEDIAMTX_BIN" "$RUN_DIR/mediamtx.yml"
wait_for_port "$MTX_RTSP_PORT" mediamtx 15 || fail "mediamtx RTSP listener did not start."
wait_for_port "$MTX_API_PORT" mediamtx 15 || fail "mediamtx Control API did not start."
fi

# The local host currently reports CUDA as available but fails NVML/model
# allocation. CPU keeps the detector stream alive; set REID_DEVICE=cuda
# explicitly on a machine with a healthy GPU.
if "$start_reid"; then
    export REID_DEVICE="${REID_DEVICE:-cpu}"
    start_service reid "$ROOT_DIR/python/reid" bash -lc 'eval "$("$1" shell.bash hook)"; conda activate reid; exec python server.py' bash "$CONDA_BIN"
else
    info "ReID algorithm was not selected."
fi

if "$start_vad"; then
    start_service vad "$ROOT_DIR/python/vad" env VAD_STREAM_CONFIG="$RUN_DIR/ai-stream.yaml" "$VAD_PYTHON" server.py
    wait_for_vad_health "${VAD_ZMQ_ADDR:-ipc:///tmp/py_ai_vad.ipc}" 30 || fail "VAD failed its health check."
else
    info "VAD algorithm was not selected."
fi

if "$start_deepsort"; then
    start_service deepsort "$ROOT_DIR/python/deepsort" env PY_ZMQ_ADDR="$DEEPSORT_ZMQ_ADDR" "$DEEPSORT_PYTHON" server.py
else
    info "DeepSORT detection was not selected."
fi

# ai_stream also preserves original camera streams; unavailable algorithm tasks retry in the background.
start_service ai_stream "$MTX_DIR/build" env \
    AI_STREAM_CONTROL_PORT="$AI_STREAM_PORT" AI_STREAM_CONTROL_TOKEN="$AI_STREAM_CONTROL_TOKEN" \
    AI_STREAM_LOG_PATH="$LOG_DIR/ai-stream-internal.log" \
    PUSH_URL_PREFIX="rtsp://127.0.0.1:$MTX_RTSP_PORT/live/" \
    ./ai_stream "$RUN_DIR/ai-stream.yaml"
wait_for_port "$AI_STREAM_PORT" ai_stream 15 || fail "ai_stream did not start its control API; inspect $LOG_DIR/ai_stream.log."

# start-local runs MediaMTX and ai_stream directly on the host, unlike the Docker
# deployment. Override Docker-only service names unless the caller supplied them.
export SMARTMONITOR_AI_STREAM_MTX_URL="rtsp://127.0.0.1:$MTX_RTSP_PORT"
export SMARTMONITOR_AI_STREAM_MTX_CONTROL_URL="http://127.0.0.1:$MTX_API_PORT/v3"
export SMARTMONITOR_AI_LIVE_PORT="$MTX_WEBRTC_PORT"
export SPRING_REDIS_DATABASE="$REDIS_DATABASE"
export SMARTMONITOR_LOG_DIR="$ROOT_DIR/log/backend"
# Druid 1.2.23 cannot normalize PostgreSQL's FOR UPDATE OF syntax.
export SPRING_DATASOURCE_DRUID_FILTER_STAT_MERGE_SQL=false
if [[ -f "$ROOT_DIR/.run/yh-business.yml" ]]; then
    export SPRING_CONFIG_ADDITIONAL_LOCATION="${SPRING_CONFIG_ADDITIONAL_LOCATION:-file:$ROOT_DIR/.run/yh-business.yml}"
fi
start_service backend "$ROOT_DIR/SmartMonitor-wangzj" env SERVER_PORT="$BACKEND_PORT" \
    "$JAVA_BIN" -jar hxjm-admin/target/hxjm-admin.jar \
    "--logging.config=$RUN_DIR/logback.xml" "--spring.redis.database=$REDIS_DATABASE" \
    "--server.port=$BACKEND_PORT" "--ruoyi.profile=${HXJM_UPLOAD_ROOT:-$ROOT_DIR/.run/uploads}" \
    "--smartmonitor.ai.mtx-home=$MTX_DIR" \
    "--smartmonitor.ai.public-host=$PUBLIC_HOST" \
    "--smartmonitor.ai.live-port=$MTX_WEBRTC_PORT"
wait_for_backend 45 || fail "backend did not start; inspect $LOG_DIR/backend.log."
# All control requests go to this worktree's C++ service, without launching shared containers.
start_original_camera_sources
if "$start_deepsort"; then
    start_algorithm_camera_tasks deepsort
    wait_for_camera_outputs deepsort
fi
if "$start_reid"; then
    start_algorithm_camera_tasks "$CAMERA_TASK"
    wait_for_camera_outputs "$CAMERA_TASK"
fi
if "$start_vad"; then
    start_algorithm_camera_tasks vad
    wait_for_camera_outputs vad
fi
if ! "$start_reid" && ! "$start_vad" && ! "$start_deepsort"; then
    info "original sources are on demand; analysis or browser readers will activate them."
fi

export VITE_VIDEO_ANALYSIS_MODE="$VIDEO_ANALYSIS_MODE"
export VITE_VIDEO_ANALYSIS_ALGORITHM="$VIDEO_ANALYSIS_ALGORITHM"
if [[ "$START_REID_FEATURE" == yes ]]; then
    start_service reid_feature "$ROOT_DIR/python" env \
        PYTHONPATH="$ROOT_DIR/python:$ROOT_DIR/.run/reid-feature-deps" \
        REID_FEATURE_WEIGHTS="${REID_FEATURE_WEIGHTS:-$PRIMARY_ROOT/python/reid/weights/MSMT17_clipreid_RN50_120.pth}" \
        REID_FEATURE_CONFIG="${REID_FEATURE_CONFIG:-$ROOT_DIR/python/reid/config/cnn_base.yml}" \
        REID_FEATURE_YOLO_WEIGHTS="${REID_FEATURE_YOLO_WEIGHTS:-$PRIMARY_ROOT/python/reid/weights/yolov8n.pt}" \
        "$REID_FEATURE_PYTHON" -B -m uvicorn reid_feature_service.server:app \
        --host 127.0.0.1 --port "$REID_FEATURE_PORT" --workers 1
    wait_for_port "$REID_FEATURE_PORT" reid_feature 90 || fail 'ReID feature API did not start'
fi
if [[ "$VIDEO_ANALYSIS_MODE" == shared ]]; then
    export VITE_VIDEO_ANALYSIS_ENABLED=true
    export VITE_VIDEO_ANALYSIS_ORIGIN="$VIDEO_ANALYSIS_SHARED_ORIGIN"
    export VITE_VIDEO_ANALYSIS_CAMERAS=camera_1,camera_2,camera_3,camera_4
elif [[ "$START_VIDEO_ANALYSIS" == yes ]]; then
    start_service video_analysis "$ROOT_DIR/python" env \
        PYTHONPATH="$ROOT_DIR/python:$ROOT_DIR/.run/media-deps" MPLCONFIGDIR="$ROOT_DIR/.run/matplotlib" \
        VIDEO_ANALYSIS_RTSP_BASE="rtsp://127.0.0.1:$MTX_RTSP_PORT/live" \
        VIDEO_ANALYSIS_RTSP_TRANSPORT="${VIDEO_ANALYSIS_RTSP_TRANSPORT:-tcp}" \
        "$VIDEO_ANALYSIS_PYTHON" -B -m uvicorn video_analysis.app:app \
        --host 127.0.0.1 --port "$VIDEO_ANALYSIS_PORT" --workers 1
    wait_for_port "$VIDEO_ANALYSIS_PORT" video_analysis 20 || fail 'Video analysis API did not start'
    export VITE_VIDEO_ANALYSIS_ENABLED=true
    export VITE_VIDEO_ANALYSIS_ORIGIN="http://127.0.0.1:$VIDEO_ANALYSIS_PORT"
    export VITE_VIDEO_ANALYSIS_CAMERAS
    VITE_VIDEO_ANALYSIS_CAMERAS="$(PYTHONPATH="$ROOT_DIR/python" "$VIDEO_ANALYSIS_PYTHON" -B -c 'from video_analysis.config import CAMERAS; print(",".join(CAMERAS))')"
else
    export VITE_VIDEO_ANALYSIS_ENABLED=false
fi

if "$start_deepsort"; then
    export VITE_ENABLE_DEEPSORT=true
else
    export VITE_ENABLE_DEEPSORT=false
fi
export VITE_MEDIA_PORT="$MTX_WEBRTC_PORT"
export VITE_BACKEND_ORIGIN="http://127.0.0.1:$BACKEND_PORT"
export VITE_MEDIA_BASE_URL="http://$PUBLIC_HOST:$MTX_WEBRTC_PORT/live"
export BROWSER=none
start_service frontend "$ROOT_DIR/lanhu" npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" --strictPort
wait_for_port "$FRONTEND_PORT" frontend 20 || fail "frontend did not start; inspect $LOG_DIR/frontend.log."

runtime mark-active
startup_complete=true

cat <<EOF

SmartMonitor local services have been started.
  Frontend: http://$PUBLIC_HOST:$FRONTEND_PORT/
  Backend:  http://$PUBLIC_HOST:$BACKEND_PORT/
  Analysis: ${VITE_VIDEO_ANALYSIS_ORIGIN:-disabled}/health ($VIDEO_ANALYSIS_MODE)
  Logs:     $LOG_DIR
  Stop:     bash $ROOT_DIR/scripts/stop-local.sh
EOF
