#!/usr/bin/env bash
# Thin Compose entrypoint. No PID scanning, model fallback or custom supervisors.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
configure() {
    SCOPE=local CONFIG='' ONLY='' BUILD=false CHECK=false STATUS=false ACTION=''
    local -a overrides=()
    while (($#)); do
        case "$1" in
          --help|-h) printf '%s\n' 'start.sh [--scope local|dev|shared|isolated] [--config FILE] [--only frontend,backend,analysis,reid,mediamtx,stream]' '--build --check --status --render --init-db --register --infra new|external' '--frontend-port N --backend-port N --analysis-port N --reid-port N --analysis-gpu GPU-UUID --reid-gpu GPU-UUID'; exit 0;;
          --build-only) ACTION=build; shift;;
          --build) BUILD=true; shift;; --check) CHECK=true; shift;; --status) STATUS=true; shift;;
          --render) ACTION=render; shift;; --init-db) ACTION=initialize; shift;; --register) ACTION=register; shift;; --check-db) ACTION=check; shift;;
          --config|--scope|--only|--infra|--frontend-port|--backend-port|--analysis-port|--reid-port|--analysis-gpu|--reid-gpu)
            [[ $# -ge 2 && -n "$2" ]] || { echo "Missing value: $1" >&2; return 2; }
            case "$1" in
              --config) CONFIG=$2;; --scope) SCOPE=$2;; --only) ONLY=$2;;
              --infra) overrides+=("INFRA=$2");;
              --frontend-port) overrides+=("FRONTEND_PORT=$2");; --backend-port) overrides+=("BACKEND_PORT=$2");;
              --analysis-port) overrides+=("ANALYSIS_PORT=$2");; --reid-port) overrides+=("REID_PORT=$2");;
              --analysis-gpu) overrides+=("ANALYSIS_GPU_UUID=$2");; --reid-gpu) overrides+=("REID_GPU_UUID=$2");;
            esac; shift 2;;
          *) echo "Unknown option: $1" >&2; return 2;;
        esac
    done
    [[ "$SCOPE" != local || -n "$CONFIG" || ! -f "$ROOT/deploy/config/deployment.local.env" ]] || CONFIG="$ROOT/deploy/config/deployment.local.env"
    local line key value item
    if [[ -n "$CONFIG" ]]; then
        [[ -f "$CONFIG" ]] || { echo 'Missing config' >&2; return 2; }
        while IFS= read -r line || [[ -n "$line" ]]; do
            line=${line%$'\r'}
            [[ "$line" =~ ^[[:space:]]*(#.*)?$ ]] && continue
            [[ "$line" =~ ^([A-Z][A-Z0-9_]*)=(.*)$ ]] || { echo 'Config requires KEY=VALUE, no shell commands' >&2; return 2; }
            key=${BASH_REMATCH[1]}; value=${BASH_REMATCH[2]}
            case "$key" in HOME|PATH|BASH_ENV|ENV|SHELLOPTS|LD_PRELOAD|DOCKER_HOST|DOCKER_CONTEXT|COMPOSE_FILE|COMPOSE_PROJECT_NAME|SOURCE_ROOT|LOCAL_UID|LOCAL_GID|REVISION|ROOT|SCOPE|CONFIG|ONLY|BUILD|CHECK|STATUS|ACTION|SERVICES|COMPOSE) echo "Reserved key: $key" >&2; return 2;; esac
            if [[ "$value" == \"*\" || "$value" == \'*\' ]]; then value=${value:1:${#value}-2}; fi
            export "$key=$value"
        done < "$CONFIG"
    fi
    for item in "${overrides[@]}"; do export "$item"; done
    [[ "$SCOPE" =~ ^(local|dev|shared|isolated)$ ]] || { echo 'Invalid scope' >&2; return 2; }
    if [[ "$SCOPE" == local || "$SCOPE" == isolated ]]; then export INFRA=${INFRA:-new}; else export INFRA=${INFRA:-external}; fi
    [[ "$INFRA" == new || "$INFRA" == external ]] || return 2
    [[ "$SCOPE" != dev || "$INFRA" == external ]] || { echo 'Use isolated scope for private infrastructure' >&2; return 2; }
    [[ "$SCOPE" != isolated || "$INFRA" == new ]] || { echo 'isolated requires --infra new' >&2; return 2; }
    export SOURCE_ROOT="$ROOT" LOCAL_UID="$(id -u)" LOCAL_GID="$(id -g)"
    local identity
    identity="$(printf '%s' "$ROOT" | sha256sum | cut -c1-10)"
    export COMPOSE_PROJECT_NAME="hxjm-$LOCAL_UID-$identity-$SCOPE"
    [[ "$SCOPE" != shared ]] || export COMPOSE_PROJECT_NAME=hxjm-shared
    export REVISION="$(git -C "$ROOT" rev-parse --short HEAD)"
    git -C "$ROOT" diff --quiet HEAD -- || export REVISION="$REVISION-dirty-$(git -C "$ROOT" diff --binary HEAD -- | sha256sum | cut -c1-8)"
    export RUNTIME_ROOT="${RUNTIME_ROOT:-$ROOT/../.runtime/$COMPOSE_PROJECT_NAME}"
    [[ "$RUNTIME_ROOT" == /* ]] || { echo 'RUNTIME_ROOT requires an absolute path' >&2; return 2; }
    export DATA_ROOT="${DATA_ROOT:-$RUNTIME_ROOT/data}" MODEL_ROOT="${MODEL_ROOT:-$ROOT/../models}"
    if [[ "$SCOPE" != shared && "$DATA_ROOT" == /data/nfs_storage/hxjm_datas ]]; then
        echo 'Personal outputs cannot use the stable data root' >&2; return 2
    fi
    export CAMERAS_FILE="${CAMERAS_FILE:-$ROOT/deploy/config/cameras.example.json}"
    export COMPOSE_PARALLEL_LIMIT=1
    export IMAGE_TAG="${IMAGE_TAG:-v0.2-compose1}" INSTANCE_NAMESPACE="${INSTANCE_NAMESPACE:-$COMPOSE_PROJECT_NAME}"
    export FRONTEND_PORT=${FRONTEND_PORT:-3104} BACKEND_PORT=${BACKEND_PORT:-18580} ANALYSIS_PORT=${ANALYSIS_PORT:-28114} REID_PORT=${REID_PORT:-28124}
    for item in FRONTEND_PORT BACKEND_PORT ANALYSIS_PORT REID_PORT; do
        value=${!item}
        [[ "$value" =~ ^[1-9][0-9]{0,4}$ && "$value" -le 65535 ]] || { echo "$item must be 1..65535" >&2; return 2; }
    done
    if [[ "$SCOPE" == dev ]]; then
        export BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:18480}" ANALYSIS_URL="${ANALYSIS_URL:-http://127.0.0.1:28014}" REID_URL="${REID_URL:-http://127.0.0.1:28024}" MEDIA_HTTP_URL="${MEDIA_HTTP_URL:-http://127.0.0.1:19289}"
    fi
    [[ -n "$ONLY" ]] || { if [[ "$SCOPE" == dev ]]; then ONLY=frontend; else ONLY=frontend,backend,mediamtx,stream,analysis,reid; fi; }
    IFS=, read -r -a SERVICES <<< "$ONLY"
    for item in "${SERVICES[@]}"; do
        [[ "$item" =~ ^(frontend|backend|mediamtx|stream|analysis|reid)$ ]] || { echo "Unknown service: $item" >&2; return 2; }
        
    done
    COMPOSE=(docker compose --project-name "$COMPOSE_PROJECT_NAME" --project-directory "$ROOT/deploy" -f "$ROOT/deploy/compose.yml")
    [[ "$SCOPE" != dev ]] || COMPOSE+=(-f "$ROOT/deploy/development.yml")
    if [[ ",$ONLY," == *,analysis,* || ",$ONLY," == *,reid,* ]]; then COMPOSE+=(-f "$ROOT/deploy/gpu.yml"); fi
    if [[ -f "$RUNTIME_ROOT/config/analysis.env" ]]; then
        while IFS='=' read -r key value; do case "$key" in ANALYSIS_CAMERAS|SOURCE_IDS) export "$key=$value";; CAMERA_CODES) export CAMERA_CODES="${CAMERA_CODES:-$value}";; esac; done < "$RUNTIME_ROOT/config/analysis.env"
    fi
}
# Only algorithm listeners are reusable. Compose-owned running services stay managed.
reuse_algorithms() {
    local running name port remaining=() url
    running=$("${COMPOSE[@]}" ps --status running --services)
    for name in "${SERVICES[@]}"; do
        if [[ "$name" == analysis || "$name" == reid ]] && ! grep -qx "$name" <<< "$running"; then
            if [[ "$name" == analysis ]]; then port=$ANALYSIS_PORT; else port=$REID_PORT; fi
            if python3 - "$port" <<'PORT'
import socket,sys
try:
    with socket.create_connection(('127.0.0.1',int(sys.argv[1])),timeout=2):pass
except OSError:sys.exit(1)
PORT
            then
                url="http://127.0.0.1:$port"
                [[ "$SCOPE" == dev ]] || url="http://host.docker.internal:$port"
                if [[ "$name" == analysis ]]; then export ANALYSIS_URL="$url";
                else export REID_URL="$url" PIPELINE_REID_URL="$url"; fi
                echo "Reuse $name: port $port already listening; will not start or stop it."
                continue
            fi
        fi
        remaining+=("$name")
    done
    SERVICES=("${remaining[@]}")
    ONLY=$(IFS=,; echo "${SERVICES[*]}")
}

main() {
    configure "$@"
    docker compose version >/dev/null
    if [[ -z "$ACTION" ]] && ! "$STATUS"; then
        reuse_algorithms
        ((${#SERVICES[@]})) || { echo "All selected algorithms are reused; no local service to start."; return; }
    fi
    "${COMPOSE[@]}" config --quiet
    if "$STATUS"; then "${COMPOSE[@]}" ps --all; return; fi
    if [[ "$ACTION" == build ]]; then "${COMPOSE[@]}" build "${SERVICES[@]}"; return; fi
    if [[ -n "$ACTION" ]]; then
        [[ "$ACTION" != initialize || "$SCOPE" != dev && "$INFRA" == new ]] || { echo 'Initialization requires shared or isolated new infrastructure' >&2; return 2; }
        "$CHECK" && return
        mkdir -p "$RUNTIME_ROOT/config"
        if "$BUILD" || ! docker image inspect "hxjm/init:$IMAGE_TAG" >/dev/null 2>&1; then "${COMPOSE[@]}" build init; fi
        if [[ "$ACTION" == initialize ]]; then "${COMPOSE[@]}" up -d --wait --wait-timeout 180 mysql postgres redis; fi
        "${COMPOSE[@]}" run --rm --no-deps init python /opt/init/bootstrap.py "$ACTION"
        return
    fi
    local n uuid running
    running=$("${COMPOSE[@]}" ps --status running --services)
    for n in analysis reid; do
        [[ ",$ONLY," == *,$n,* ]] || continue
        grep -qx "$n" <<< "$running" && continue
        if [[ "$n" == analysis ]]; then uuid=${ANALYSIS_GPU_UUID:-}; else uuid=${REID_GPU_UUID:-}; fi
        [[ "$uuid" == GPU-* ]] || { echo "$n requires explicit GPU UUID" >&2; return 2; }
        nvidia-smi --query-gpu=uuid --format=csv,noheader | rg -Fx "$uuid" >/dev/null || { echo 'GPU unavailable' >&2; return 2; }
        [[ "$n" != analysis || -f "$MODEL_ROOT/botsort/pretrained/bytetrack_x_mot17.pth.tar" && -f "$MODEL_ROOT/botsort/pretrained/mot17_sbs_S50.pth" ]] || { echo 'Missing BoT-SORT weights' >&2; return 2; }
        [[ "$n" != reid || -f "$MODEL_ROOT/reid/MSMT17_clipreid_RN50_120.pth" && -f "$MODEL_ROOT/reid/yolov8n.pt" ]] || { echo 'Missing ReID weights' >&2; return 2; }
        local available
        available=$(nvidia-smi -i "$uuid" --query-gpu=memory.free --format=csv,noheader,nounits)
        [[ "$available" -ge "${MIN_GPU_FREE_MIB:-4096}" ]] || { echo "$n: insufficient free GPU memory" >&2; return 2; }
        echo "$n GPU $uuid; free memory snapshot, not a reservation:"
        nvidia-smi -i "$uuid" --query-gpu=memory.free --format=csv,noheader
    done
    if [[ "$SCOPE" == dev && ",$ONLY," == *,frontend,* ]]; then
        export ONLY
        python3 - <<'PY'
import os,socket
from urllib.parse import urlsplit
for name,var in [('backend','BACKEND_URL'),('analysis','ANALYSIS_URL')]:
 if name in os.environ['ONLY'].split(','):continue
 if name=='analysis' and os.environ.get('ANALYSIS_ENABLED','true').lower()=='false':continue
 try:
  address=urlsplit(os.environ[var])
  with socket.create_connection((address.hostname,address.port or (443 if address.scheme=='https' else 80)),timeout=3):pass
  print('Reuse',name,os.environ[var])
 except (OSError,ValueError) as e:raise SystemExit('Dependency unavailable: '+name+' ('+type(e).__name__+')')
PY
    fi
    # Fail before starting any selected service if a requested port is occupied.
    export ONLY
    running=$("${COMPOSE[@]}" ps --status running --services)
    RUNNING_SERVICES="$running" python3 - <<'PORTCHECK'
import os,socket
selected=os.environ['ONLY'].split(','); running=os.environ['RUNNING_SERVICES'].split()
ports={'frontend':[('FRONTEND_PORT',3104,1)],'backend':[('BACKEND_PORT',18580,1)],'analysis':[('ANALYSIS_PORT',28114,1)],'reid':[('REID_PORT',28124,1)],'mediamtx':[('RTSP_PORT',19554,1),('MEDIA_HTTP_PORT',19389,1),('MEDIA_API_PORT',10497,1),('MEDIA_ICE_PORT',19390,2)],'stream':[('STREAM_PORT',19590,1)]}
seen=set();probes=[]
try:
 for name in selected:
  for key,default,kind in ports[name]:
   raw=os.environ.get(key,str(default))
   if not raw.isdecimal() or not 1<=int(raw)<=65535:raise ValueError(key+' must be 1..65535')
   port=int(raw)
   if (kind,port) in seen:raise ValueError('Selected service ports overlap: '+str(port))
   seen.add((kind,port))
   if name in running:continue
   s=socket.socket(socket.AF_INET,socket.SOCK_STREAM if kind==1 else socket.SOCK_DGRAM)
   if kind==1:s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
   probes.append(s)
   try:s.bind(('0.0.0.0',port))
   except OSError:raise ValueError(key+' is occupied: '+str(port))
except ValueError as e:raise SystemExit(str(e))
finally:
 for s in probes:s.close()
PORTCHECK
    "$CHECK" && { echo "Validated $COMPOSE_PROJECT_NAME: $ONLY ($REVISION)"; return; }
    mkdir -p "$RUNTIME_ROOT/config" "$RUNTIME_ROOT/frontend/node_modules" "$RUNTIME_ROOT/backend" "$RUNTIME_ROOT/analysis" "$RUNTIME_ROOT/reid" "$DATA_ROOT"/{uploads,images,recordings,result-spool,mysql,postgres,redis}
    if [[ ",$ONLY," == *,backend,* || ",$ONLY," == *,analysis,* || ",$ONLY," == *,mediamtx,* || ",$ONLY," == *,stream,* ]]; then
        [[ -f "$RUNTIME_ROOT/config/backend.yml" ]] || { echo 'Render/provide config first; see deploy/README.md' >&2; return 2; }
    fi
    if [[ ",$ONLY," == *,analysis,* ]]; then
        [[ -f "$RUNTIME_ROOT/config/business.json" && -n "${ANALYSIS_CAMERAS:-}" && -n "${SOURCE_IDS:-}" ]] || { echo 'Register pipeline first' >&2; return 2; }
    fi
    "$BUILD" && "${COMPOSE[@]}" build "${SERVICES[@]}"
    if [[ "$INFRA" == new ]]; then
        [[ -n "${MYSQL_PASSWORD:-}" && -n "${POSTGRES_PASSWORD:-}" ]] || { echo 'Database passwords required' >&2; return 2; }
        "${COMPOSE[@]}" up -d --wait --wait-timeout 180 mysql postgres redis
    fi
    if [[ ",$ONLY," == *,backend,* || "$INFRA" == new ]]; then
        docker image inspect "hxjm/init:$IMAGE_TAG" >/dev/null 2>&1 || "${COMPOSE[@]}" build init
        "${COMPOSE[@]}" run --rm --no-deps init python /opt/init/bootstrap.py check
    fi
    if [[ "$SCOPE" == dev && ",$ONLY," == *,frontend,* ]]; then
        "${COMPOSE[@]}" run --rm --no-deps frontend npm ci --no-audit --no-fund --cache /tmp/npm-cache
    fi
    "${COMPOSE[@]}" up -d --no-deps --wait --wait-timeout 180 "${SERVICES[@]}"
    "${COMPOSE[@]}" ps
    echo "Started $COMPOSE_PROJECT_NAME ($ONLY), revision $REVISION; public services independently managed."
}
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then main "$@"; fi
