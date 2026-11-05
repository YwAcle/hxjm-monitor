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

SERVICE_NAMES = ('joyai_tool', 'joyai_observer', 'joyai_model', 'joyai_qwen')


def process(pid, strict=False):
    try:
        base = Path('/proc') / str(pid)
        stat = (base / 'stat').read_text().rsplit(')', 1)[1].split()
        if stat[0] == 'Z' or base.stat().st_uid != os.getuid():
            return None
        return dict(pid=int(pid), start=stat[19], pgid=int(stat[2]),
                    cwd=str((base / 'cwd').resolve(strict=True)),
                    args=(base / 'cmdline').read_bytes().decode(errors='replace').split('\0')[:-1],
                    env=(base / 'environ').read_bytes().split(b'\0'))
    except PermissionError as error:
        if strict:
            raise RuntimeError(f'Cannot inspect PID {pid}; run stop with the same user and group as startup. State was retained.') from error
        return None
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
        result = []
        for item in items:
            try:
                base = Path('/proc') / str(item['pid'])
                fields = (base / 'stat').read_text().rsplit(')', 1)[1].split()
                if fields[0] != 'Z' and fields[19] == item['start'] and base.stat().st_uid == os.getuid():
                    result.append(item)
            except FileNotFoundError:
                pass
        return result
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
        if record.get('pid'):
            process(record['pid'], strict=True)
        # The inherited token identifies workers even after their parent exits.
        members = owned(record)
        if members:
            print(f"[local-runtime] stopping {path.stem} ({record['root']})", flush=True)
            terminate(members)
        if owned(record):
            terminate(owned(record))
    path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('action', choices=('start', 'status', 'stop'))
    parser.add_argument('args', nargs=argparse.REMAINDER)
    ns = parser.parse_args()
    state, root = ns.state, ns.root.resolve()
    name = ns.args[0]
    if name not in SERVICE_NAMES:
        parser.error('Unknown service')
    path = state / f'{name}.json'
    record = read_json(path)
    if ns.action == 'status':
        return 0 if record and record.get('root') == str(root) and matches(process(record['pid']), record) else 1
    if ns.action == 'stop':
        stop_record(path, root)
        return 0
    _, cwd, log, *command = ns.args
    if Path(cwd).resolve() != root:
        raise ValueError("JoyAI processes must run in this repository")
    stop_record(path, root)
    state.mkdir(parents=True, exist_ok=True)
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
