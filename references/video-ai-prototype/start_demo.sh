#!/usr/bin/env bash
set -euo pipefail

DEMO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
HXJM_ROOT="$(cd -- "$DEMO_ROOT/.." && pwd -P)"
PYTHON_BIN='/home/guest/anaconda3/envs/deepsort/bin/python'
NODE_BIN='/home/guest/.nvm/versions/node/v18.20.8/bin/node'
VITE_CLI="$DEMO_ROOT/frontend/node_modules/vite/bin/vite.js"
MODEL_PATH="$HXJM_ROOT/python/deep_sort-master/detection/yolov5mu.pt"
PYTHON_DEPS="$DEMO_ROOT/.runtime/python_deps"
CONTROL_PYTHON='/usr/bin/python3'
CAMERA_CONFIG="$DEMO_ROOT/demo.env"
MEDIAMTX_API='http://127.0.0.1:9997'
WEBSOCKET_URL='ws://192.168.109.191:8010/ws/detections'

declare -A SERVICE_PORTS=([frontend]=3010 [backend]=8010)
declare -A SERVICE_DIRS=([frontend]="$DEMO_ROOT/frontend" [backend]="$DEMO_ROOT")
declare -A SERVICE_PIDS=([frontend]="$DEMO_ROOT/frontend/.run/vite.pid" [backend]="$DEMO_ROOT/.runtime/backend.pid")
declare -A SERVICE_LOGS=([frontend]="$DEMO_ROOT/frontend/.run/vite.log" [backend]="$DEMO_ROOT/.runtime/backend.log")
declare -A SERVICE_LOCKS=([frontend]="$DEMO_ROOT/frontend/.run/vite.lock" [backend]="$DEMO_ROOT/.runtime/backend.lock")

error() {
  printf '[错误] %s\n' "$*" >&2
  return 1
}

load_camera_config() {
  CAMERA_ID="$($CONTROL_PYTHON -B - "$CAMERA_CONFIG" <<'PY'
from pathlib import Path
import re
import sys

try:
    entries = [line.strip() for line in Path(sys.argv[1]).read_text().splitlines()
               if line.strip() and not line.lstrip().startswith('#')]
    if len(entries) != 1:
        raise ValueError('文件只能配置一项 DEMO_CAMERA_ID')
    match = re.fullmatch(r'DEMO_CAMERA_ID\s*=\s*(camera_[1-9][0-9]*)', entries[0])
    if not match:
        raise ValueError('格式应为 DEMO_CAMERA_ID=camera_1（正整数编号）')
    print(match.group(1))
except (OSError, ValueError) as error:
    raise SystemExit(f'demo.env 配置错误：{error}')
PY
  )" || return 1
  ORIGINAL_VIDEO_URL="http://192.168.109.191:18889/live/$CAMERA_ID/"
  RTSP_URL="rtsp://127.0.0.1:18554/live/$CAMERA_ID"
}

config_matches() {
  local service="$1" pid="$2"
  "$CONTROL_PYTHON" -B - "$service" "$pid" "$CAMERA_ID" "$ORIGINAL_VIDEO_URL" "$RTSP_URL" "$WEBSOCKET_URL" <<'PY'
from pathlib import Path
import sys

service, pid, camera, video_url, rtsp_url, websocket_url = sys.argv[1:]
try:
    environment = dict(entry.split('=', 1) for entry in
                       (Path('/proc') / pid / 'environ').read_bytes().decode().split('\0') if '=' in entry)
except (OSError, UnicodeError) as error:
    print(f'无法核对 demo 进程环境：{error}', file=sys.stderr)
    raise SystemExit(2)
if service == 'frontend':
    matches = environment.get('VITE_ORIGINAL_VIDEO_URL') == video_url
    matches = matches and environment.get('VITE_DETECTIONS_WS_URL', websocket_url) == websocket_url
else:
    matches = environment.get('DEMO_CAMERA_ID') == camera and environment.get('DEMO_RTSP_URL') == rtsp_url
raise SystemExit(0 if matches else 1)
PY
}

check_target_stream() {
  local response
  response="$(curl --fail --silent --show-error --max-time 5 "$MEDIAMTX_API/v3/paths/get/live/$CAMERA_ID")" || {
    error "无法确认目标原始流 live/$CAMERA_ID 在线；保留当前 demo，不更新配置、不停止进程。"
    return 1
  }
  if ! "$CONTROL_PYTHON" -B -c '
import json
import sys
stream = json.load(sys.stdin)
assert stream["name"] == "live/" + sys.argv[1]
assert stream["ready"] is True and stream.get("tracks")
' "$CAMERA_ID" <<< "$response" 2>/dev/null; then
    error "目标原始流 live/$CAMERA_ID 未就绪；保留当前 demo，不更新配置、不停止进程。"
    return 1
  fi
  printf '[流在线] MediaMTX live/%s ready=true（仅只读查询）\n' "$CAMERA_ID"
}

prepare_frontend_env() {
  "$CONTROL_PYTHON" -B - "$DEMO_ROOT/frontend/.env.local" "$WEBSOCKET_URL" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
previous = path.read_text() if path.exists() else ''
lines = [line for line in previous.splitlines()
         if not re.match(r'\s*(?:export\s+)?VITE_(?:ORIGINAL_VIDEO_URL|DETECTIONS_WS_URL)\s*=', line)]
updated = '\n'.join([*lines, 'VITE_DETECTIONS_WS_URL=' + sys.argv[2]]) + '\n'
if updated != previous:
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(updated)
    temporary.replace(path)
PY
}

stop_service() {
  local service="$1" pid="$2"
  process_matches "$service" "$pid" || { error "$service 进程身份变化，拒绝停止 PID=$pid。"; return 1; }
  "$CONTROL_PYTHON" -B - "$service" "$pid" "${SERVICE_DIRS[$service]}" "$NODE_BIN" "$VITE_CLI" "$PYTHON_BIN" <<'PY'
import os
from pathlib import Path
import select
import signal
import sys

service, pid_text, directory, node, cli, python = sys.argv[1:]
pid = int(pid_text)
process = Path('/proc') / pid_text
descriptor = os.pidfd_open(pid)
try:
    arguments = process.joinpath('cmdline').read_bytes().decode().rstrip('\0').split('\0')
    assert process.joinpath('cwd').resolve() == Path(directory)
    if service == 'frontend':
        assert process.joinpath('exe').resolve() == Path(node).resolve()
        assert len(arguments) == 7
        assert (Path(directory) / arguments[1]).resolve() == Path(cli).resolve()
        assert arguments[2:] == ['--host', '0.0.0.0', '--port', '3010', '--strictPort']
    else:
        assert process.joinpath('exe').resolve() == Path(python).resolve()
        assert arguments == [python, '-B', '-m', 'uvicorn', 'backend.app:app', '--host', '0.0.0.0',
                             '--port', '8010', '--workers', '1', '--timeout-graceful-shutdown', '20']
    signal.pidfd_send_signal(descriptor, signal.SIGTERM)
    poller = select.poll()
    poller.register(descriptor, select.POLLIN)
    if not poller.poll(35000):
        raise SystemExit('35 秒内未退出；不发送强制信号、不重复启动，请检查 demo 日志。')
    print(f'[已停止] {service} PID={pid}（仅此已核对 demo 进程）')
finally:
    os.close(descriptor)
PY
}

listener_pid() {
  local port="$1" listeners remaining candidate owner=''
  listeners="$(ss -H -ltnp "sport = :$port")" || {
    error "无法检查端口 $port，未启动服务。"
    return 1
  }
  [[ -n "$listeners" ]] || return 0
  remaining="$listeners"
  while [[ "$remaining" =~ pid=([0-9]+) ]]; do
    candidate="${BASH_REMATCH[1]}"
    if [[ -n "$owner" && "$owner" != "$candidate" ]]; then
      error "端口 $port 被多个进程占用，未操作这些进程：$listeners"
      return 1
    fi
    owner="$candidate"
    remaining="${remaining#*"pid=$candidate"}"
  done
  if [[ -z "$owner" ]]; then
    error "端口 $port 已占用，但无法读取进程身份；未启动或终止任何进程：$listeners"
    return 1
  fi
  printf '%s\n' "$owner"
}

process_matches() {
  local service="$1" pid="$2" cwd executable cli
  local -a process_args=()
  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
  cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null)" || return 1
  [[ "$cwd" == "${SERVICE_DIRS[$service]}" ]] || return 1
  executable="$(readlink -f "/proc/$pid/exe" 2>/dev/null)" || return 1
  mapfile -d '' -t process_args < "/proc/$pid/cmdline" || return 1
  if [[ "$service" == 'frontend' ]]; then
    [[ "$executable" == "$(readlink -f "$NODE_BIN")" && ${#process_args[@]} -eq 7 ]] || return 1
    cli="${process_args[1]}"
    [[ "$cli" == /* ]] || cli="$cwd/$cli"
    [[ "$(readlink -f "$cli")" == "$(readlink -f "$VITE_CLI")" ]] || return 1
    [[ "${process_args[*]:2}" == '--host 0.0.0.0 --port 3010 --strictPort' ]]
  else
    [[ "$executable" == "$(readlink -f "$PYTHON_BIN")" ]] || return 1
    [[ "${process_args[*]:1}" == '-B -m uvicorn backend.app:app --host 0.0.0.0 --port 8010 --workers 1 --timeout-graceful-shutdown 20' ]]
  fi
}

running_pid() {
  local service="$1" pid cached_pid
  pid="$(listener_pid "${SERVICE_PORTS[$service]}")" || return 1
  if [[ -n "$pid" ]]; then
    if ! process_matches "$service" "$pid"; then
      error "端口 ${SERVICE_PORTS[$service]} 被非本 demo 的已核对进程占用（PID=$pid），未操作该进程。"
      return 1
    fi
    printf '%s\n' "$pid"
    return 0
  fi
  if [[ -f "${SERVICE_PIDS[$service]}" ]]; then
    cached_pid="$(cat "${SERVICE_PIDS[$service]}")"
    if [[ "$cached_pid" =~ ^[1-9][0-9]*$ ]] && kill -0 "$cached_pid" 2>/dev/null && process_matches "$service" "$cached_pid"; then
      printf '%s\n' "$cached_pid"
    fi
  fi
}

check_prerequisites() {
  local service="$1"
  if [[ "$service" == 'frontend' ]]; then
    [[ -x "$NODE_BIN" ]] || { error "缺少已验证的 Node：$NODE_BIN"; return 1; }
    [[ -f "$VITE_CLI" ]] || { error "缺少现有 Vite 依赖：$VITE_CLI；不会自动安装。"; return 1; }
  else
    [[ -x "$PYTHON_BIN" ]] || { error "缺少已有算法 Python：$PYTHON_BIN"; return 1; }
    [[ -s "$MODEL_PATH" ]] || { error "缺少或为空的本地模型：$MODEL_PATH；不会下载权重。"; return 1; }
    env -u PYTHONHOME PYTHONPATH="$PYTHON_DEPS:$DEMO_ROOT" "$PYTHON_BIN" -B -c 'import fastapi, uvicorn, websockets' || {
      error "API 依赖检查失败，保留现有算法环境；请检查 $PYTHON_DEPS。"
      return 1
    }
  fi
}

spawn_detached() {
  local working_directory="$1" port="$2" pid_file="$3" log_file="$4" lock_file="$5"
  shift 5
  setsid --fork /bin/bash -c '
    set -euo pipefail
    working_directory="$1"; port="$2"; pid_file="$3"; lock_file="$4"
    shift 4
    cd -- "$working_directory"
    exec 9>"$lock_file"
    flock -n 9 || { echo "另一个 demo 进程持有启动锁，未重复启动。" >&2; exit 1; }
    listeners="$(ss -H -ltn "sport = :$port")"
    [[ -z "$listeners" ]] || { echo "端口 $port 已占用，未启动或终止任何进程。" >&2; exit 1; }
    printf "%s\n" "$$" > "$pid_file.tmp.$$"
    mv -- "$pid_file.tmp.$$" "$pid_file"
    printf "[start_demo] detached start PID=%s directory=%s\n" "$$" "$working_directory"
    exec nohup "$@"
  ' demo-service "$working_directory" "$port" "$pid_file" "$lock_file" "$@" \
    8>&- </dev/null >>"$log_file" 2>&1
}

start_service() {
  local service="$1"
  local -a command_args
  if [[ "$service" == 'frontend' ]]; then
    command_args=(env "VITE_ORIGINAL_VIDEO_URL=$ORIGINAL_VIDEO_URL" "VITE_DETECTIONS_WS_URL=$WEBSOCKET_URL" NODE_ENV=development
      "$NODE_BIN" "$VITE_CLI" --host 0.0.0.0 --port 3010 --strictPort)
  else
    command_args=(env -u PYTHONHOME
      "PYTHONPATH=$PYTHON_DEPS:$DEMO_ROOT" PYTHONUNBUFFERED=1
      "DEMO_RTSP_URL=$RTSP_URL" DEMO_RTSP_TRANSPORT=udp
      'OPENCV_FFMPEG_CAPTURE_OPTIONS=rtsp_transport;udp' "DEMO_CAMERA_ID=$CAMERA_ID"
      DEMO_INFERENCE_INTERVAL_SECONDS=1 DEMO_RECONNECT_DELAY_SECONDS=2 DEMO_WS_SEND_TIMEOUT_SECONDS=5
      "DEEPSORT_MODEL=$MODEL_PATH" "$PYTHON_BIN" -B -m uvicorn backend.app:app
      --host 0.0.0.0 --port 8010 --workers 1 --timeout-graceful-shutdown 20)
  fi
  spawn_detached "${SERVICE_DIRS[$service]}" "${SERVICE_PORTS[$service]}" \
    "${SERVICE_PIDS[$service]}" "${SERVICE_LOGS[$service]}" "${SERVICE_LOCKS[$service]}" "${command_args[@]}"
}

http_ready() {
  local service="$1" response
  if [[ "$service" == 'frontend' ]]; then
    response="$(curl --fail --silent --max-time 3 http://127.0.0.1:3010/src/App.jsx)" || return 1
    "$CONTROL_PYTHON" -B -c '
import json
import re
import sys
source = sys.stdin.read()
match = re.search(r"import\.meta\.env\s*=\s*(\{[^\n]*?\});", source)
environment = json.loads(match.group(1))
assert environment["VITE_ORIGINAL_VIDEO_URL"] == sys.argv[1]
assert environment["VITE_DETECTIONS_WS_URL"] == sys.argv[2]
' "$ORIGINAL_VIDEO_URL" "$WEBSOCKET_URL" <<< "$response" 2>/dev/null
  else
    response="$(curl --fail --silent --max-time 3 http://127.0.0.1:8010/health)" || return 1
    env -u PYTHONHOME -u PYTHONPATH "$PYTHON_BIN" -B -c '
import json
import sys
health = json.load(sys.stdin)
assert health["status"] == "ok" and health["model_initializations"] == 1
assert health["analysis_task_alive"] and health["published_count"] > 0
assert health["camera_id"] == sys.argv[1]
' "$CAMERA_ID" <<< "$response" 2>/dev/null
  fi
}

wait_ready() {
  local service="$1" timeout=30 deadline pid
  [[ "$service" != 'backend' ]] || timeout=90
  deadline=$((SECONDS + timeout))
  while (( SECONDS < deadline )); do
    pid="$(running_pid "$service")" || return 1
    if [[ -n "$pid" ]] && http_ready "$service"; then
      printf '%s\n' "$pid" > "${SERVICE_PIDS[$service]}"
      printf '[就绪] %s PID=%s，端口 %s，摄像头 %s\n' "$service" "$pid" "${SERVICE_PORTS[$service]}" "$CAMERA_ID"
      return 0
    fi
    sleep 1
  done
  error "$service 在 ${timeout}s 内未就绪，未杀进程或重复启动。日志：${SERVICE_LOGS[$service]}"
  tail -n 15 "${SERVICE_LOGS[$service]}" >&2 || true
  return 1
}

main() {
  local tool service failures=0 changes=0 match_status current_pid
  local -A existing_pids=() actions=()
  [[ $# -eq 0 ]] || { error '用法：直接执行 start_demo.sh，无需参数。'; return 1; }
  for tool in setsid flock ss readlink curl nohup; do
    command -v "$tool" >/dev/null || { error "缺少系统命令：$tool"; return 1; }
  done
  [[ -x "$CONTROL_PYTHON" ]] || { error "缺少进程核对工具：$CONTROL_PYTHON"; return 1; }
  mkdir -p "$DEMO_ROOT/.runtime" "$DEMO_ROOT/frontend/.run"
  exec 8>"$DEMO_ROOT/.runtime/start_demo.lock"
  flock -n 8 || { error '另一个 start_demo.sh 正在检查或启动，请稍后重试。'; return 1; }
  load_camera_config || return 1
  printf '[配置] %s：%s\n' "$CAMERA_CONFIG" "$CAMERA_ID"
  for service in frontend backend; do
    existing_pids[$service]="$(running_pid "$service")" || failures=1
  done
  (( failures == 0 )) || return 1
  for service in frontend backend; do
    if [[ -z "${existing_pids[$service]}" ]]; then
      actions[$service]='start'
    elif config_matches "$service" "${existing_pids[$service]}"; then
      actions[$service]='skip'
    else
      match_status=$?
      (( match_status == 1 )) || return 1
      actions[$service]='restart'
    fi
    if [[ "${actions[$service]}" != 'skip' ]]; then
      changes=1
    fi
  done
  if (( changes )); then
    check_target_stream || return 1
    for service in frontend backend; do
      if [[ "${actions[$service]}" != 'skip' ]]; then
        check_prerequisites "$service" || return 1
      fi
    done
    for service in frontend backend; do
      current_pid="$(running_pid "$service")" || return 1
      [[ "$current_pid" == "${existing_pids[$service]}" ]] || { error "$service 进程已变化，保留当前 demo，请重新执行。"; return 1; }
    done
    check_target_stream || return 1
    for service in backend frontend; do
      if [[ "${actions[$service]}" == 'restart' ]]; then
        stop_service "$service" "${existing_pids[$service]}" || return 1
      fi
    done
  fi
  prepare_frontend_env || return 1
  for service in backend frontend; do
    if [[ "${actions[$service]}" == 'skip' ]]; then
      printf '[跳过启动] %s 摄像头配置一致，PID=%s\n' "$service" "${existing_pids[$service]}"
    else
      printf '[启动] %s，日志：%s\n' "$service" "${SERVICE_LOGS[$service]}"
      start_service "$service" || return 1
    fi
  done
  for service in frontend backend; do
    wait_ready "$service" || failures=1
  done
  (( failures == 0 )) || return 1
  printf '\nDemo 页面：http://192.168.109.191:3010/\n'
  printf '摄像头：%s\n原始视频：%s\n原始 RTSP：%s\n' "$CAMERA_ID" "$ORIGINAL_VIDEO_URL" "$RTSP_URL"
  printf '检测 WS：%s\n' "$WEBSOCKET_URL"
  printf 'PID / 日志：frontend/.run/vite.pid、vite.log；.runtime/backend.pid、backend.log\n'
  printf '只修改 demo.env 的 DEMO_CAMERA_ID 后重新执行本脚本；未操作原业务或 MediaMTX。\n'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
