#!/usr/bin/env python3
"""Own the shared camera relay and one BoT-SORT worker, separately from apps."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import selectors
import signal
import socket
import subprocess
import sys
import time
import uuid


CODE_ROOT = Path(__file__).resolve().parents[2]
LISTENERS = {
    'rtmpAddress': ('MTX_RTMP_PORT', socket.SOCK_STREAM),
    'rtspAddress': ('MTX_RTSP_PORT', socket.SOCK_STREAM),
    'rtpAddress': ('MTX_RTP_PORT', socket.SOCK_DGRAM),
    'rtcpAddress': ('MTX_RTCP_PORT', socket.SOCK_DGRAM),
    'hlsAddress': ('MTX_HLS_PORT', socket.SOCK_STREAM),
    'webrtcAddress': ('MTX_WEBRTC_PORT', socket.SOCK_STREAM),
    'webrtcLocalUDPAddress': ('MTX_WEBRTC_ICE_PORT', socket.SOCK_DGRAM),
    'srtAddress': ('MTX_SRT_PORT', socket.SOCK_DGRAM),
    'playbackAddress': ('MTX_PLAYBACK_PORT', socket.SOCK_STREAM),
    'apiAddress': ('MTX_API_PORT', socket.SOCK_STREAM),
}


def positive_integer(value, name, minimum=1, maximum=65535):
    if not str(value).isdigit() or not minimum <= int(value) <= maximum:
        raise ValueError(f'Invalid {name}')
    return int(value)


class Settings:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.state = self.root / '.run/shared-botsort'
        self.ports = {}
        for line in (self.root / 'local-ports.env').read_text().splitlines():
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            match = re.fullmatch(r'([A-Z_]+)=([0-9]+)\s*(?:#.*)?', line.strip())
            if not match or match[1] in self.ports:
                raise ValueError('Invalid or duplicate entry in local-ports.env')
            self.ports[match[1]] = positive_integer(match[2], match[1], minimum=0 if match[1] == 'REDIS_DATABASE' else 1)
        for key in [value[0] for value in LISTENERS.values()] + ['BACKEND_PORT']:
            if key not in self.ports:
                raise ValueError(f'Missing {key} in local-ports.env')
        self.analysis_port = positive_integer(os.getenv('SHARED_BOTSORT_ANALYSIS_PORT', '28010'), 'analysis port')
        self.gpu = positive_integer(os.getenv('SHARED_BOTSORT_GPU', '0'), 'GPU', minimum=0, maximum=255)
        self.python = Path(os.getenv('SHARED_BOTSORT_PYTHON', '/home/guest/anaconda3/envs/botsort39/bin/python'))
        self.media = self.root / 'mtx/mediamtx/mediamtx'
        self.model_root = self.root / 'python/tracker/BoT-SORT'
        self.log_bytes = positive_integer(os.getenv('SHARED_BOTSORT_LOG_MIB', '8'), 'log size', maximum=64) * 1024 ** 2
        record = os.getenv('SHARED_BOTSORT_RECORD', 'yes').lower()
        if record not in {'yes', 'no'}:
            raise ValueError('SHARED_BOTSORT_RECORD must be yes or no')
        self.record = record == 'yes'

    def validate(self):
        import yaml  # Fail before starting any subprocess if the renderer is unavailable.
        for path in (self.python, self.media):
            if not path.is_file() or not os.access(path, os.X_OK):
                raise ValueError(f'Required executable unavailable: {path}')
        for path in (self.model_root / 'pretrained/bytetrack_x_mot17.pth.tar',
                     self.model_root / 'pretrained/mot17_sbs_S50.pth',
                     CODE_ROOT / 'python/tracker/BoT-SORT/fast_reid/configs/MOT17/sbs_S50.yml',
                     CODE_ROOT / 'python/video_analysis/app.py'):
            if not path.is_file():
                raise ValueError(f'Required shared-service asset missing: {path}')
        configured = [(kind, self.ports[key]) for key, kind in LISTENERS.values()]
        configured.append((socket.SOCK_STREAM, self.analysis_port))
        if len(set(configured)) != len(configured):
            raise ValueError('Shared service ports overlap in local-ports.env')


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def private_write(path, text):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with os.fdopen(os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
            stream.write(text)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def process(pid):
    try:
        base = Path('/proc') / str(int(pid))
        if base.stat().st_uid != os.getuid():
            return None
        fields = (base / 'stat').read_text().rsplit(')', 1)[1].split()
        if fields[0] == 'Z':
            return None
        env = dict(part.split(b'=', 1) for part in (base / 'environ').read_bytes().split(b'\0') if b'=' in part)
        return {'pid': int(pid), 'start': fields[19], 'token': env.get(b'HXJM_SHARED_TOKEN', b'').decode(),
                'role': env.get(b'HXJM_SHARED_ROLE', b'').decode(),
                'shared': env.get(b'HXJM_SHARED_SERVICE') == b'1'}
    except (OSError, ValueError):
        return None


def same_process(record, role=None):
    current = process(record.get('pid', -1))
    return bool(current and current['shared'] and current['start'] == record.get('start')
                and current['token'] == record.get('token') and current['token']
                and (role is None or current['role'] == role))


def owned_children(token, role=None):
    if not token:
        return []
    return [item for path in Path('/proc').iterdir() if path.name.isdigit()
            for item in [process(path.name)] if item and item['shared'] and item['token'] == token
            and item['role'] in ({role} if role else {'media', 'analysis', 'setup'})]


def stop_children(token, role=None):
    # A token inherited only by our children also identifies orphaned model workers.
    for sig, timeout in ((signal.SIGTERM, 3), (signal.SIGKILL, 2)):
        for item in owned_children(token, role):
            if same_process(item, item['role']):
                try:
                    os.kill(item['pid'], sig)
                except ProcessLookupError:
                    pass
        deadline = time.monotonic() + timeout
        while owned_children(token, role) and time.monotonic() < deadline:
            time.sleep(.05)
    if owned_children(token, role):
        raise RuntimeError('Some owned shared-service children did not exit')


def base_environment(token, role):
    # Never inherit a caller's worktree ownership, media ports or camera settings.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('HXJM_LOCAL_', 'MTX_', 'VIDEO_ANALYSIS_'))}
    env.update(HXJM_SHARED_SERVICE='1', HXJM_SHARED_TOKEN=token, HXJM_SHARED_ROLE=role)
    return env


def read_sources():
    query = ('SELECT machine_id, video_url FROM ba_machine '
             'WHERE isvalid=1 AND status=1 AND machine_id IN (1,2,3,4) ORDER BY machine_id')
    env = dict(os.environ, MYSQL_PWD=os.getenv('SHARED_BOTSORT_MYSQL_PASSWORD', '123456'), HXJM_SHARED_ROLE='setup')
    command = ['docker', 'exec', '-e', 'MYSQL_PWD', 'smartmonitor-mysql', 'mysql',
               '-u' + os.getenv('SHARED_BOTSORT_MYSQL_USER', 'root'), '--batch', '--skip-column-names',
               '--raw', 'hxjm_sm', '-e', query]
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise RuntimeError('Cannot read camera sources from smartmonitor-mysql; check MySQL access')
    sources = {}
    for line in result.stdout.splitlines():
        parts = line.split('\t', 1)
        if len(parts) != 2 or parts[0] not in {'1', '2', '3', '4'} or not parts[1].startswith('rtsp://'):
            raise ValueError('Invalid camera source record; no source credentials were logged')
        sources['live/camera_' + parts[0]] = parts[1]
    if len(sources) != 4:
        raise ValueError('Four enabled camera records (machine_id 1 to 4) are required')
    return sources


def render_media(settings, sources):
    import yaml
    template = settings.root / '.run/local-runtime/mediamtx.yml'
    if not template.is_file():
        template = settings.root / 'mtx/mediamtx/mediamtx.yml'
    try:
        media = yaml.safe_load(template.read_text())
    except yaml.YAMLError:
        raise ValueError('Invalid media YAML; source credentials were not printed') from None
    if not isinstance(media, dict):
        raise ValueError('Media configuration must be a YAML object')
    media.update({name: ':' + str(settings.ports[key]) for name, (key, _) in LISTENERS.items()})
    media.update(api=True, apiAddress='127.0.0.1:' + str(settings.ports['MTX_API_PORT']),
                 logDestinations=['stdout'], rtspTransports=['udp', 'tcp'])
    defaults = media.setdefault('pathDefaults', {})
    defaults['record'] = settings.record and defaults.get('record', True)
    defaults['recordPath'] = str(settings.root / '.run/recordings/%path/%Y-%m-%d_%H-%M-%S-%f')
    # Keep the existing retention/segment policy and send the single recording hook to main.
    for config in [defaults, *(media.get('paths') or {}).values()]:
        if isinstance(config, dict) and isinstance(config.get('runOnRecordSegmentComplete'), str):
            config['runOnRecordSegmentComplete'] = re.sub(
                r'http://[^\s"\x27]+(?=/media-assets)',
                'http://127.0.0.1:' + str(settings.ports['BACKEND_PORT']), config['runOnRecordSegmentComplete'])
    previous = media.get('paths') or {}
    paths = {name: dict(config or {}) for name, config in previous.items()
             if (config or {}).get('source', 'publisher') == 'publisher' and name not in sources}
    if not settings.record:
        for config in paths.values():
            config['record'] = False
    override = os.getenv('SHARED_BOTSORT_SOURCE_TRANSPORT')
    if override and override not in {'udp', 'tcp'}:
        raise ValueError('SHARED_BOTSORT_SOURCE_TRANSPORT must be udp or tcp')
    for name, source in sources.items():
        config = dict(previous.get(name) or {})
        transport = override or config.get('rtspTransport', defaults.get('rtspTransport'))
        config.update(source=source, rtspTransport=transport if transport in {'udp', 'tcp'} else 'udp',
                      sourceOnDemand=config.get('sourceOnDemand', True), sourceOnDemandStartTimeout='10s',
                      sourceOnDemandCloseAfter='10s', record=settings.record and config.get('record', defaults['record']))
        config.pop('recordPath', None)
        paths[name] = config
    media['paths'] = paths
    return yaml.safe_dump(media, allow_unicode=True, sort_keys=False)


def analysis_environment(settings, token):
    env = base_environment(token, 'analysis')
    cameras = {f'camera_{i}': f"rtsp://127.0.0.1:{settings.ports['MTX_RTSP_PORT']}/live/camera_{i}" for i in range(1, 5)}
    env.update(PYTHONPATH=str(CODE_ROOT / 'python'), PYTHONDONTWRITEBYTECODE='1',
               BOTSORT_ROOT=str(settings.model_root), MPLCONFIGDIR=str(settings.state / 'matplotlib'),
               VIDEO_ANALYSIS_ALGORITHM='botsort', VIDEO_ANALYSIS_WORKERS='1',
               VIDEO_ANALYSIS_GPU=str(settings.gpu), VIDEO_ANALYSIS_CAMERAS=json.dumps(cameras),
               VIDEO_ANALYSIS_RTSP_TRANSPORT='tcp', VIDEO_ANALYSIS_DECODE_THREADS='1',
               VIDEO_ANALYSIS_OPENCV_THREADS='8', VIDEO_ANALYSIS_MEMORY_RESERVE_GIB='4',
               VIDEO_ANALYSIS_MODEL_HEADROOM_GIB='1',
               VIDEO_ANALYSIS_CUDA_GRAPH=os.getenv('SHARED_BOTSORT_CUDA_GRAPH', '1'))
    env.update(MALLOC_ARENA_MAX='2', MALLOC_TRIM_THRESHOLD_='131072')
    for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS',
                 'VECLIB_MAXIMUM_THREADS', 'BLIS_NUM_THREADS'):
        env[name] = '1'
    return env


def check_ports(settings, role=None):
    ports = [(key, settings.ports[key], kind) for key, kind in LISTENERS.values()] if role != 'analysis' else []
    if role != 'media':
        ports.append(('SHARED_BOTSORT_ANALYSIS_PORT', settings.analysis_port, socket.SOCK_STREAM))
    for name, port, kind in ports:
        with socket.socket(socket.AF_INET, kind) as probe:
            if kind == socket.SOCK_STREAM:
                # Match Uvicorn/MediaMTX's reuse of recently closed TCP sessions.
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(('0.0.0.0', port))
            except OSError:
                raise RuntimeError(f'{name} port {port} is occupied; stop or reconfigure its owner explicitly. Nothing was stopped.') from None


class BoundedLog:
    def __init__(self, path, limit):
        self.path, self.limit = path, limit

    def write(self, data):
        if self.path.exists() and self.path.stat().st_size + len(data) > self.limit:
            for index in (2, 1):
                source = self.path.with_name(self.path.name + '.' + str(index))
                if source.exists():
                    source.replace(self.path.with_name(self.path.name + '.' + str(index + 1)))
            self.path.replace(self.path.with_name(self.path.name + '.1'))
        with os.fdopen(os.open(str(self.path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), 'ab') as stream:
            stream.write(data[-self.limit:])


def listening(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=.15):
            return True
    except OSError:
        return False


def run(settings):
    settings.state.mkdir(parents=True, exist_ok=True, mode=0o700)
    if settings.state.is_symlink() or settings.state.stat().st_uid != os.getuid():
        raise RuntimeError('Shared-service state directory must belong to the current user')
    settings.state.chmod(0o700)
    identity = process(os.getpid())
    if identity is None:
        raise RuntimeError('Cannot verify supervisor identity through /proc')
    if not identity['shared'] or identity['role'] != 'manager' or not identity['token']:
        env = base_environment(uuid.uuid4().hex, 'manager')
        os.execve(sys.executable, [sys.executable, str(Path(__file__).resolve()), 'run', '--root', str(settings.root)], env)
    with open(settings.state / 'service.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('The shared-service supervisor is already running') from None
        previous = read_json(settings.state / 'service.json')
        if previous.get('root') == str(settings.root) and not same_process(previous, 'manager'):
            stop_children(previous.get('token'))
        token = identity['token']
        record = dict(identity, root=str(settings.root), code_root=str(CODE_ROOT), phase='starting', children={})
        # Record ownership before the bounded database query, so stop works during setup too.
        private_write(settings.state / 'service.json', json.dumps(record, indent=2) + '\n')
        settings.validate()
        check_ports(settings)
        private_write(settings.state / 'mediamtx.yml', render_media(settings, read_sources()))
        selector = selectors.DefaultSelector()
        event_log = BoundedLog(settings.state / 'supervisor.log', settings.log_bytes)
        children = {role: {'process': None, 'delay': 2., 'next': 0., 'started': 0.} for role in ('media', 'analysis')}
        stopping = False

        def stop(signum, frame):
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        last_write = 0.
        try:
            while not stopping:
                now = time.monotonic()
                for role, child in children.items():
                    proc = child['process']
                    if proc is not None and proc.poll() is not None:
                        selector.unregister(proc.stdout)
                        stop_children(token, role)
                        os.set_blocking(proc.stdout.fileno(), False)
                        remaining = proc.stdout.read()
                        if remaining:
                            child['log'].write(remaining)
                        proc.stdout.close()
                        event_log.write(f'{role} exited ({proc.returncode}); retry in {child["delay"]:.0f}s\n'.encode())
                        child.update(process=None, next=now + child['delay'], delay=min(120., child['delay'] * 2))
                        proc = None
                    if proc is not None and now - child['started'] > 60:
                        child['delay'] = 2.
                    if proc is None and now >= child['next']:
                        if role == 'analysis' and children['media']['process'] is None:
                            continue
                        try:
                            check_ports(settings, role)
                            command = ([str(settings.media), str(settings.state / 'mediamtx.yml')] if role == 'media' else
                                       [str(settings.python), '-B', '-m', 'uvicorn', 'video_analysis.app:app',
                                        '--host', '127.0.0.1', '--port', str(settings.analysis_port), '--workers', '1'])
                            env = base_environment(token, role) if role == 'media' else analysis_environment(settings, token)
                            proc = subprocess.Popen(command, cwd=settings.root, env=env, stdin=subprocess.DEVNULL,
                                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
                            child.update(process=proc, started=now, log=BoundedLog(settings.state / (role + '.log'), settings.log_bytes))
                            selector.register(proc.stdout, selectors.EVENT_READ, child['log'])
                            event_log.write(f'{role} started (PID {proc.pid})\n'.encode())
                        except (OSError, RuntimeError) as exc:
                            event_log.write(f'{role}: {exc}; retry in {child["delay"]:.0f}s\n'.encode())
                            child.update(next=now + child['delay'], delay=min(120., child['delay'] * 2))
                for key, _ in selector.select(timeout=.25):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if chunk:
                        key.data.write(chunk)
                if now - last_write >= 1:
                    record['children'] = {role: process(child['process'].pid) if child['process'] else None for role, child in children.items()}
                    ports = (settings.ports['MTX_RTSP_PORT'], settings.ports['MTX_API_PORT'], settings.analysis_port)
                    record['phase'] = 'running' if all(record['children'].values()) and all(listening(port) for port in ports) else 'starting'
                    private_write(settings.state / 'service.json', json.dumps(record, indent=2) + '\n')
                    last_write = now
        finally:
            stop_children(token)
            for child in children.values():
                if child['process'] is not None:
                    child['process'].wait(timeout=2)
                    child['process'].stdout.close()
            selector.close()
            record.update(phase='stopped', children={})
            private_write(settings.state / 'service.json', json.dumps(record, indent=2) + '\n')


def summary(settings, record):
    alive = record.get('root') == str(settings.root) and same_process(record, 'manager')
    return {'running': alive, 'phase': record.get('phase', 'stopped') if alive else 'stopped',
            'pid': record.get('pid') if alive else None, 'root': str(settings.root),
            'analysis_origin': f'http://127.0.0.1:{settings.analysis_port}',
            'rtsp_port': settings.ports['MTX_RTSP_PORT'], 'webrtc_port': settings.ports['MTX_WEBRTC_PORT'],
            'media_api_port': settings.ports['MTX_API_PORT'], 'gpu': settings.gpu,
            'logs': str(settings.state), 'children': record.get('children', {}) if alive else {}}


def start(settings):
    settings.state.mkdir(parents=True, exist_ok=True, mode=0o700)
    if settings.state.is_symlink() or settings.state.stat().st_uid != os.getuid():
        raise RuntimeError('Shared-service state directory must belong to the current user')
    settings.state.chmod(0o700)
    # Serialize bootstrap callers too: one app starting must not make another fail.
    with open(settings.state / 'start.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        record_path = settings.state / 'service.json'
        record = read_json(record_path)
        current = summary(settings, record)
        log_path = settings.state / 'bootstrap.log'
        child = None
        if not current['running']:
            if record.get('root') != str(settings.root) or not owned_children(record.get('token')):
                check_ports(settings)
            with os.fdopen(os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'wb') as log:
                child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'run', '--root', str(settings.root)],
                                         env=base_environment(uuid.uuid4().hex, 'manager'), stdin=subprocess.DEVNULL,
                                         stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            current = summary(settings, read_json(record_path))
            if current['running'] and current['phase'] == 'running':
                print(json.dumps(current, ensure_ascii=False))
                return 0
            if child is not None and child.poll() is not None:
                raise RuntimeError(f'Shared service did not start; see {log_path} (camera credentials are not printed)')
            time.sleep(.2)
        raise RuntimeError(f'Shared service is still starting; inspect {settings.state} with the status command')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('start', 'stop', 'status', 'check', 'run'))
    parser.add_argument('--root', default='/data/nfs_storage/hxjm')
    args = parser.parse_args(argv)
    settings = Settings(args.root)
    record_path = settings.state / 'service.json'
    record = read_json(record_path)
    current = summary(settings, record)
    if args.command == 'status':
        print(json.dumps(current, ensure_ascii=False))
        return 0 if current['running'] else 1
    if args.command == 'stop':
        if current['running'] and same_process(record, 'manager'):
            os.kill(record['pid'], signal.SIGTERM)
            deadline = time.monotonic() + 12
            while same_process(record, 'manager') and time.monotonic() < deadline:
                time.sleep(.1)
            if same_process(record, 'manager'):
                os.kill(record['pid'], signal.SIGKILL)
        if record.get('root') == str(settings.root):
            stop_children(record.get('token'))
        print('Shared BoT-SORT services stopped; developer applications were not stopped.')
        return 0
    settings.validate()
    if args.command == 'check':
        if not current['running']:
            check_ports(settings)
        print(json.dumps(dict(current, checked=True), ensure_ascii=False))
        return 0
    if args.command == 'run':
        run(settings)
        return 0
    return start(settings)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f'[shared-botsort] {error}', file=sys.stderr)
        raise SystemExit(1)
