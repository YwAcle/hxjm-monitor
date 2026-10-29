#!/usr/bin/env python3
"""Linux service ownership, isolated to one worktree (stdlib only)."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid


def process(pid):
    try:
        base = Path('/proc') / str(pid)
        stat = (base / 'stat').read_text().rsplit(')', 1)[1].split()
        if stat[0] == 'Z' or base.stat().st_uid != os.getuid():
            return None
        return dict(pid=int(pid), start=stat[19], pgid=int(stat[2]),
                    cwd=str((base / 'cwd').resolve(strict=True)),
                    args=(base / 'cmdline').read_bytes().decode(errors='replace').split('\0')[:-1],
                    env=(base / 'environ').read_bytes().split(b'\0'))
    except (OSError, ValueError):
        return None


def processes():
    for path in Path('/proc').iterdir():
        if path.name.isdigit():
            item = process(path.name)
            if item:
                yield item


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def write_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.replace(path)


def matches(item, record):
    return bool(item and item['start'] == record.get('start')
                and item['cwd'] == record.get('cwd'))


def owned(record):
    marker = ('HXJM_LOCAL_SERVICE_ID=' + record['token']).encode()
    return [p for p in processes() if marker in p['env'] and b'HXJM_SHARED_SERVICE=1' not in p['env']]


def terminate(items):
    # Recheck PID/start time immediately before every signal; never trust a PID file.
    def alive():
        return [p for p in items if matches(process(p['pid']), p)]
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for item in alive():
            try:
                os.kill(item['pid'], sig)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + (5 if sig == signal.SIGTERM else 2)
        while alive() and time.monotonic() < deadline:
            time.sleep(.1)
    if alive():
        raise RuntimeError('Could not stop owned processes: ' + str([p['pid'] for p in alive()]))


def stop_record(path, root):
    record = read_json(path)
    if record and record.get("root") != str(root):
        raise RuntimeError(f"Refusing to stop another worktree via {path}; record belongs to {record.get('root')}")
    if record.get('token'):
        # The inherited token identifies workers even after their parent exits.
        members = owned(record)
        if members:
            print(f"[local-runtime] stopping {path.stem} ({record['root']})", flush=True)
            terminate(members)
        if owned(record):
            terminate(owned(record))
    path.unlink(missing_ok=True)


def legacy_service(item, roots):
    """Migrate old launchers by exact cwd + executable, not global name matching."""
    if b'HXJM_SHARED_SERVICE=1' in item.get('env', []):
        return False
    cwd, args = item['cwd'], item['args']
    if not args:
        return False
    exe = Path(args[0]).name
    for root in roots:
        if cwd == str(root / 'mtx/mediamtx') and exe == 'mediamtx':
            return True
        if cwd == str(root / 'mtx/build') and exe == 'ai_stream':
            return True
        if cwd == str(root / 'SmartMonitor-wangzj') and exe == 'java' and any(
                a in ('hxjm-admin/target/hxjm-admin.jar', str(root / 'SmartMonitor-wangzj/hxjm-admin/target/hxjm-admin.jar')) for a in args):
            return True
        if cwd == str(root / 'lanhu') and (exe in ('npm', 'npm run dev', 'vite') or
                (exe == 'node' and any('node_modules/vite/' in a for a in args)) or
                (exe in ('sh', 'bash') and len(args) > 2 and args[1] == '-c' and args[2].startswith('vite'))):
            return True
        if cwd in [str(root / 'python' / name) for name in ('reid', 'vad', 'deepsort')] and exe.startswith('python'):
            return 'server.py' in args or any('multiprocessing.' in a for a in args)
    return False


def stop_all(state, root):
    for name in ('frontend', 'video_analysis', 'reid_feature', 'backend', 'ai_stream', 'deepsort', 'vad', 'reid', 'mediamtx'):
        stop_record(state / f'{name}.json', root)
    roots = [root]
    old = [p for p in processes() if legacy_service(p, roots)]
    if old:
        print('[local-runtime] stopping legacy application processes: ' + str([p['pid'] for p in old]), flush=True)
        terminate(old)
    for tree in roots:
        for name in ('frontend', 'backend', 'ai_stream', 'deepsort', 'vad', 'reid', 'mediamtx'):
            (tree / '.run' / f'{name}.pid').unlink(missing_ok=True)
    (state / 'active.json').unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('action', choices=('start', 'status', 'stop-all', 'mark-active', 'prepare-assets'))
    parser.add_argument('args', nargs=argparse.REMAINDER)
    ns = parser.parse_args()
    state, root = ns.state, ns.root.resolve()
    if ns.action == 'prepare-assets':
        primary = Path(ns.args[0]).resolve()
        if primary == root or ns.args[1:] == ['false', 'false', 'false']:
            return 0
        folders = ('python/models', 'python/reid/weights', 'python/reid/models',
                   'python/vad/model', 'python/fire', 'python/deep_sort-master/detection')
        count = 0
        for folder in folders:
            for source in (primary / folder).rglob('*'):
                if source.is_file() and source.suffix in ('.pt', '.pth', '.onnx', '.t7', '.safetensors'):
                    destination = root / source.relative_to(primary)
                    if not destination.exists() and not destination.is_symlink():
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.symlink_to(source)
                        count += 1
        print(f'[local-runtime] linked {count} missing model assets from {primary}')
        return 0
    if ns.action == 'stop-all':
        stop_all(state, root)
        return 0
    if ns.action == 'mark-active':
        write_json(state / 'active.json', dict(root=str(root), revision=None, branch=None, dirty=None,
                                             started=time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                                             ports={k: int(v) for k, v in os.environ.items()
                                                    if (k.endswith('_PORT') or k == 'REDIS_DATABASE') and v.isdigit()}))
        return 0
    name = ns.args[0]
    if name not in ('frontend', 'video_analysis', 'reid_feature', 'backend', 'ai_stream', 'deepsort', 'vad', 'reid', 'mediamtx'):
        parser.error('Unknown service')
    path = state / f'{name}.json'
    record = read_json(path)
    if ns.action == 'status':
        return 0 if record and record.get('root') == str(root) and matches(process(record['pid']), record) else 1
    _, cwd, log, *command = ns.args
    stop_record(path, root)
    token = uuid.uuid4().hex
    env = dict(os.environ, HXJM_LOCAL_SERVICE_ID=token, HXJM_LOCAL_WORKTREE=str(root))
    # Close Bash's flock descriptor so daemons never hold the operation lock.
    with open(log, 'ab', buffering=0) as output:
        child = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                 stdout=output, stderr=output, start_new_session=True, close_fds=True)
    item = process(child.pid)
    if not item:
        raise RuntimeError(f'{name} exited immediately; see {log}')
    write_json(path, {key: item[key] for key in ('pid', 'start', 'cwd')} |
               dict(token=token, root=str(root)))
    print(f'[local-runtime] started {name} (PID {child.pid}); log: {log}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
