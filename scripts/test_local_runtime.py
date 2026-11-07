"""Regression checks for cross-worktree ownership and orphan cleanup."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

TOOL = Path(__file__).with_name('local-runtime.py')
spec = importlib.util.spec_from_file_location('local_runtime', TOOL)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = self.root / 'state'
        self.state.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        self.peer = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])

    def call(self, *args, check=True, root=None, state=None):
        result = subprocess.run([sys.executable, str(TOOL), '--state', str(state or self.state),
                               '--root', str(root or self.root), *args], check=False, capture_output=True, text=True)
        if check and result.returncode:
            self.fail(result.stdout + result.stderr)
        return result

    def tearDown(self):
        self.call('stop-all')
        self.peer.terminate()
        self.peer.wait()
        self.temp.cleanup()

    def test_stop_preserves_unrelated_process_and_stale_pid(self):
        self.call('start', 'backend', str(self.root), str(self.root / 'service.log'),
                  sys.executable, '-c', 'import time; time.sleep(120)')
        original = json.loads((self.state / 'backend.json').read_text())
        self.assertEqual(0, self.call('status', 'backend').returncode)
        self.call('stop-all')
        self.assertIsNone(runtime.process(original['pid']))
        # A stale record can point to a live unrelated process; it must survive.
        original['pid'] = self.peer.pid
        (self.state / 'backend.json').write_text(json.dumps(original))
        self.assertNotEqual(0, self.call('status', 'backend', check=False).returncode)
        self.call('stop-all')
        self.assertIsNone(self.peer.poll())
        self.call('stop-all')  # Idempotent.

    def test_orphan_worker_is_stopped_after_parent_exits(self):
        worker_pid = self.root / 'worker.pid'
        code = ('import subprocess,sys,time; from pathlib import Path; '
                'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(120)"]); '
                f'Path({str(worker_pid)!r}).write_text(str(p.pid)); time.sleep(.3)')
        self.call('start', 'reid', str(self.root), str(self.root / 'reid.log'), sys.executable, '-c', code)
        deadline = time.monotonic() + 5
        while not worker_pid.exists() and time.monotonic() < deadline:
            time.sleep(.05)
        pid = int(worker_pid.read_text())
        time.sleep(.4)
        self.call('stop-all')
        self.assertIsNone(runtime.process(pid))
        self.assertIsNone(self.peer.poll())

    def test_stopping_one_worktree_preserves_managed_and_legacy_peer(self):
        other = self.root / 'other'
        other_state = other / 'state'
        other_state.mkdir(parents=True)
        legacy_dir = other / 'python/reid'
        legacy_dir.mkdir(parents=True)
        (legacy_dir / 'server.py').write_text('import time; time.sleep(120)')
        legacy = subprocess.Popen([sys.executable, 'server.py'], cwd=legacy_dir)
        try:
            self.call('start', 'backend', str(other), str(other / 'backend.log'),
                      sys.executable, '-c', 'import time; time.sleep(120)', root=other, state=other_state)
            self.call('start', 'backend', str(self.root), str(self.root / 'backend.log'),
                      sys.executable, '-c', 'import time; time.sleep(120)')
            local_record = json.loads((self.state / 'backend.json').read_text())
            self.call('stop-all')
            self.assertIsNone(runtime.process(local_record['pid']))
            self.call('status', 'backend', root=other, state=other_state)
            self.assertIsNone(legacy.poll())
            # Even a misplaced record cannot grant permission to stop a peer.
            (self.state / 'backend.json').write_bytes((other_state / 'backend.json').read_bytes())
            self.assertNotEqual(0, self.call('stop-all', check=False).returncode)
            self.call('status', 'backend', root=other, state=other_state)
            (self.state / 'backend.json').unlink()
        finally:
            self.call('stop-all', root=other, state=other_state)
            legacy.terminate()
            legacy.wait()

    def test_stop_preserves_shared_media_in_same_primary_directory(self):
        directory = self.root / 'mtx/mediamtx'
        directory.mkdir(parents=True)
        executable = directory / 'mediamtx'
        executable.symlink_to(sys.executable)
        shared = subprocess.Popen([str(executable), '-c', 'import time; time.sleep(120)'],
                                  cwd=directory, env=dict(os.environ, HXJM_SHARED_SERVICE='1'))
        try:
            self.call('stop-all')
            self.assertIsNone(shared.poll())
            candidate = {'cwd': str(directory), 'args': [str(executable)],
                         'env': [b'HXJM_SHARED_SERVICE=1']}
            self.assertFalse(runtime.legacy_service(candidate, [self.root]))
            candidate['env'] = []
            self.assertTrue(runtime.legacy_service(candidate, [self.root]))
        finally:
            shared.terminate()
            shared.wait()

    def test_unrecorded_vite_bin_process_is_stopped_and_its_port_closes(self):
        self.check_unrecorded_vite()

    def test_stop_script_handles_orphan_vite_started_by_sg_docker(self):
        import grp
        try:
            docker = grp.getgrnam('docker')
        except KeyError:
            self.skipTest('No docker group on this host')
        if docker.gr_gid == os.getegid() or docker.gr_gid not in os.getgrouplist(
                __import__('pwd').getpwuid(os.getuid()).pw_name, os.getgid()):
            self.skipTest('Needs an authorized docker group different from the current group')
        self.check_unrecorded_vite(other_group=True)

    def check_unrecorded_vite(self, other_group=False):
        directory = self.root / 'lanhu'
        script = directory / 'node_modules/.bin/vite'
        script.parent.mkdir(parents=True)
        ready = self.root / 'port'
        script.write_text('import socket,time; from pathlib import Path; '
                          's=socket.socket(); s.bind(("127.0.0.1",0)); s.listen(); '
                          f'Path({str(ready)!r}).write_text(str(s.getsockname()[1])); time.sleep(120)')
        if other_group:
            command = shlex.join(['bash', '-c', 'exec -a node "$1" "$2"', 'bash', sys.executable, str(script)])
            child = subprocess.Popen(['sg', 'docker', '-c', command], cwd=directory)
        else:
            child = subprocess.Popen(['node', str(script)], executable=sys.executable, cwd=directory)
        try:
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertTrue(ready.exists())
            port = int(ready.read_text())
            with socket.create_connection(('127.0.0.1', port), timeout=1):
                pass
            if other_group:
                (self.root / 'local-ports.env').write_text(f'FRONTEND_PORT={port}\n')
                result = subprocess.run(['bash', str(TOOL.with_name('stop-local.sh')),
                                         '--worktree', str(self.root)],
                                        env=dict(os.environ, HXJM_ANALYSIS_ROOT=str(self.root / 'owner')),
                                        text=True, capture_output=True, timeout=15)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertIn('using existing docker group', result.stdout)
            else:
                self.call('stop-all')
            child.wait(timeout=5)
            with socket.socket() as probe:
                self.assertNotEqual(0, probe.connect_ex(('127.0.0.1', port)))
            self.assertIsNone(self.peer.poll())
        finally:
            if child.poll() is None:
                child.terminate()
            child.wait()

    def test_unreadable_recorded_process_does_not_erase_state(self):
        path = self.state / 'frontend.json'
        path.write_text(json.dumps(dict(root=str(self.root), token='test', pid=123)))
        with patch.object(runtime, 'process', side_effect=RuntimeError('Cannot inspect PID 123')):
            with self.assertRaisesRegex(RuntimeError, 'Cannot inspect PID'):
                runtime.stop_record(path, self.root)
        self.assertTrue(path.exists())
        path.unlink()

    def test_service_group_uses_live_record(self):
        self.call('start', 'frontend', str(self.root), str(self.root / 'frontend.log'),
                  sys.executable, '-c', 'import time; time.sleep(120)')
        with patch.object(runtime.os, 'getegid', return_value=-1):
            import grp
            self.assertEqual(grp.getgrgid(os.getgid()).gr_name, runtime.service_group(self.state, self.root))
        self.call('stop-all')

    def test_stop_script_reports_conflicting_port_without_killing_its_owner(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            (self.root / 'local-ports.env').write_text(f'FRONTEND_PORT={listener.getsockname()[1]}\n')
            result = subprocess.run(['bash', str(TOOL.with_name('stop-local.sh')),
                                     '--worktree', str(self.root)],
                                    env=dict(os.environ, HXJM_ANALYSIS_ROOT=str(self.root / 'owner')),
                                    capture_output=True, text=True, timeout=10)
            self.assertNotEqual(0, result.returncode)
            self.assertIn('stop is incomplete', result.stderr)
            self.assertNotIn('this worktree stopped', result.stdout)
            self.assertIsNone(self.peer.poll())


class PortConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / 'local-ports.env'
        self.config.write_bytes(TOOL.parent.parent.joinpath('local-ports.env').read_bytes())
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)

    def tearDown(self):
        self.temp.cleanup()

    def shell(self, check=True):
        result = subprocess.run(['bash', '-c', 'set -euo pipefail; source "$1" --worktree "$2"; load_port_config; printf "%s:%s" "$FRONTEND_PORT" "$RUN_DIR"',
                                 'bash', str(TOOL.with_name('local-common.sh')), str(self.root)],
                                env=dict(os.environ, FRONTEND_PORT='65500'), capture_output=True, text=True)
        if check and result.returncode:
            self.fail(result.stderr)
        return result

    def test_config_overrides_environment_and_state_is_local(self):
        result = self.shell()
        port = next(line.split('=', 1)[1] for line in self.config.read_text().splitlines()
                    if line.startswith('FRONTEND_PORT='))
        self.assertEqual(f'{port}:{self.root}/.run/local-runtime', result.stdout)

    def test_reserved_peer_ports_and_redis_are_rejected(self):
        peer = self.root / 'peer'
        peer.mkdir()
        config = peer / 'local-ports.env'
        settings = dict(FRONTEND_PORT='3006', BACKEND_PORT='18680', REDIS_DATABASE='6')
        with patch.object(runtime, 'worktrees', return_value=[self.root, peer]):
            for content in ('AI_STREAM_PORT=18680 # different service, same port\n', 'REDIS_DATABASE=6\n'):
                config.write_text(content)
                with self.assertRaisesRegex(ValueError, 'conflicts with'):
                    runtime.check_ports(self.root, settings)
            config.write_text('AI_STREAM_PORT=19490\nREDIS_DATABASE=4\n')
            runtime.check_ports(self.root, settings)

    def test_duplicate_local_ports_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate local port'):
            runtime.check_ports(self.root, dict(FRONTEND_PORT='3006', BACKEND_PORT='3006', REDIS_DATABASE='6'))

    def test_independent_sibling_clone_reservations_are_checked(self):
        root = self.root / 'hxjm-self/hxjm-monitor'
        peer = self.root / 'hxjm-peer/hxjm-monitor'
        for directory in (root, peer):
            directory.mkdir(parents=True)
            subprocess.run(['git', 'init', '-q', str(directory)], check=True)
        (peer / 'local-ports.env').write_text('FRONTEND_PORT=3011\nREDIS_DATABASE=11\n')
        with self.assertRaisesRegex(ValueError, 'conflicts with'):
            runtime.check_ports(root, dict(FRONTEND_PORT='3011', REDIS_DATABASE='10'))

    def test_subscriber_only_reuses_shared_databases(self):
        fake_bin = self.root / 'bin'
        fake_bin.mkdir()
        docker = fake_bin / 'docker'
        docker.write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$DOCKER_LOG"\n'
                          'if [[ "$1" == inspect ]]; then echo "$DOCKER_HEALTH"; else exit 99; fi\n')
        docker.chmod(0o755)
        log = self.root / 'docker.log'
        script = 'set -euo pipefail; source "$1" --worktree "$2"; start_infrastructure'
        env = dict(os.environ, PATH=f'{fake_bin}:{os.environ["PATH"]}', DOCKER_LOG=str(log),
                   HXJM_ANALYSIS_ROOT=str(self.root / 'owner'))
        for health, expected in [('healthy', 0), ('unhealthy', 1)]:
            with self.subTest(health=health):
                log.write_text('')
                result = subprocess.run(['bash', '-c', script, 'bash',
                                         str(TOOL.with_name('local-common.sh')), str(self.root)],
                                        env=dict(env, DOCKER_HEALTH=health), capture_output=True, text=True)
                self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
                self.assertEqual(3, len(log.read_text().splitlines()))
                self.assertNotIn('compose', log.read_text())
                self.assertFalse((self.root / 'owner/.run').exists())

    def test_primary_worktree_ownership(self):
        peer = self.root / 'peer'
        peer.mkdir()
        script = ('source "$1" --worktree "$2"; PRIMARY_ROOT="$3"; '
                  'is_primary_worktree && printf primary || printf worktree')
        command = ['bash', '-c', script, 'bash', str(TOOL.with_name('local-common.sh'))]
        primary_result = subprocess.run(command + [str(self.root), str(self.root)], capture_output=True, text=True)
        peer_result = subprocess.run(command + [str(peer), str(self.root)], capture_output=True, text=True)
        self.assertEqual('primary', primary_result.stdout)
        self.assertEqual('worktree', peer_result.stdout)

    def test_invalid_and_duplicate_ports_are_rejected(self):
        content = self.config.read_text()
        for bad in ('FRONTEND_PORT=70000', 'FRONTEND_PORT=03000', 'FRONTEND_PORT=$(touch /tmp/should-not-run)',
                    'UNEXPECTED=1', 'FRONTEND_PORT=3001'):
            self.config.write_text(content + '\n' + bad + '\n')
            self.assertNotEqual(0, self.shell(check=False).returncode, bad)

    def video_settings(self, primary=None, **overrides):
        payload = ('import json,os; print(json.dumps({key:os.getenv(key) for key in '
                   '["VIDEO_ANALYSIS_MODE","LOCAL_MEDIA_ENABLED","SHARED_MEDIA_RTSP_BASE",'
                   '"SHARED_MEDIA_ORIGIN","VIDEO_ANALYSIS_SHARED_ORIGIN","VIDEO_ANALYSIS_WORKERS",'
                   '"MTX_RTSP_PORT"]}))')
        script = ('set -euo pipefail; source "$1" --worktree "$2"; load_port_config; '
                  'PRIMARY_ROOT="$3"; ANALYSIS_ROOT="${HXJM_ANALYSIS_ROOT:-$PRIMARY_ROOT}"; '
                  'load_video_config; python3 -c ' + shlex.quote(payload))
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(('VIDEO_ANALYSIS_', 'SHARED_MEDIA_', 'LOCAL_MEDIA_'))}
        environment.update(overrides)
        result = subprocess.run(['bash', '-c', script, 'bash', str(TOOL.with_name('local-common.sh')),
                                 str(self.root), str(primary or self.root)],
                                env=environment, capture_output=True, text=True)
        return result

    def test_shared_is_default_and_ignores_old_private_model_config(self):
        (self.root / '.run').mkdir()
        (self.root / '.run/video-analysis.env').write_text('export VIDEO_ANALYSIS_WORKERS=4\n')
        result = self.video_settings()
        self.assertEqual(0, result.returncode, result.stderr)
        settings = json.loads(result.stdout)
        self.assertEqual('shared', settings['VIDEO_ANALYSIS_MODE'])
        self.assertEqual('false', settings['LOCAL_MEDIA_ENABLED'])
        self.assertIsNone(settings['VIDEO_ANALYSIS_WORKERS'])
        ports = dict(line.split('=', 1) for line in self.config.read_text().splitlines()
                     if line and not line.startswith('#'))
        self.assertEqual(f'rtsp://127.0.0.1:{ports["MTX_RTSP_PORT"]}/live', settings['SHARED_MEDIA_RTSP_BASE'])
        self.assertEqual(f'http://127.0.0.1:{ports["MTX_WEBRTC_PORT"]}', settings['SHARED_MEDIA_ORIGIN'])

    def test_shared_subscriber_keeps_its_own_media_ports(self):
        primary = self.root / 'primary'
        primary.mkdir()
        content = self.config.read_text()
        ports = dict(line.split('=', 1) for line in content.splitlines() if line and not line.startswith('#'))
        (primary / 'local-ports.env').write_text(
            content.replace(f'MTX_RTSP_PORT={ports["MTX_RTSP_PORT"]}', 'MTX_RTSP_PORT=28554')
                   .replace(f'MTX_WEBRTC_PORT={ports["MTX_WEBRTC_PORT"]}', 'MTX_WEBRTC_PORT=28889'))
        result = self.video_settings(primary=primary)
        self.assertEqual(0, result.returncode, result.stderr)
        settings = json.loads(result.stdout)
        self.assertEqual('true', settings['LOCAL_MEDIA_ENABLED'])
        self.assertEqual(f'rtsp://127.0.0.1:{ports["MTX_RTSP_PORT"]}/live', settings['SHARED_MEDIA_RTSP_BASE'])
        self.assertEqual(f'http://127.0.0.1:{ports["MTX_WEBRTC_PORT"]}', settings['SHARED_MEDIA_ORIGIN'])
        self.assertEqual(ports['MTX_RTSP_PORT'], settings['MTX_RTSP_PORT'])

    def test_independent_clone_uses_explicit_owner_and_own_media_without_models(self):
        owner = self.root / 'owner'
        (self.root / 'local-video.env').write_text(f'HXJM_ANALYSIS_ROOT="{owner}"\n')
        (self.root / '.run').mkdir()
        (self.root / '.run/video-analysis.env').write_text('export VIDEO_ANALYSIS_WORKERS=99\n')
        result = self.video_settings(SHARED_MEDIA_ORIGIN='http://main.invalid:18889')
        self.assertEqual(0, result.returncode, result.stderr)
        settings = json.loads(result.stdout)
        self.assertEqual('shared', settings['VIDEO_ANALYSIS_MODE'])
        self.assertEqual('true', settings['LOCAL_MEDIA_ENABLED'])
        self.assertNotIn('main.invalid', settings['SHARED_MEDIA_ORIGIN'])
        self.assertIsNone(settings['VIDEO_ANALYSIS_WORKERS'])
        self.assertFalse((self.root / 'python').exists())
        result = self.video_settings(VIDEO_ANALYSIS_MODE='local')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('local model startup is disabled', result.stderr)

    def test_copied_repository_is_not_the_configured_algorithm_owner(self):
        (self.root / 'local-video.env').write_text('HXJM_ANALYSIS_ROOT="/main/algorithm-owner"\n')
        script = 'set -eu; source "$1" --worktree "$2"; is_analysis_owner'
        result = subprocess.run(['bash', '-c', script, 'bash',
                                 str(TOOL.with_name('local-common.sh')), str(self.root)])
        self.assertNotEqual(0, result.returncode)

    def test_ignored_local_override_wins_over_the_shared_owner(self):
        (self.root / 'local-video.env').write_text('HXJM_ANALYSIS_ROOT="/main/algorithm-owner"\n')
        (self.root / 'local-video.local.env').write_text(f'HXJM_ANALYSIS_ROOT="{self.root}"\n')
        script = 'set -eu; source "$1" --worktree "$2"; is_analysis_owner'
        result = subprocess.run(['bash', '-c', script, 'bash',
                                 str(TOOL.with_name('local-common.sh')), str(self.root)],
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_local_mode_reuses_private_settings_and_rejects_unknown_mode(self):
        (self.root / '.run').mkdir()
        (self.root / '.run/video-analysis.env').write_text('export VIDEO_ANALYSIS_WORKERS=4\n')
        result = self.video_settings(VIDEO_ANALYSIS_MODE='local')
        self.assertEqual(0, result.returncode, result.stderr)
        settings = json.loads(result.stdout)
        self.assertEqual('true', settings['LOCAL_MEDIA_ENABLED'])
        self.assertEqual('4', settings['VIDEO_ANALYSIS_WORKERS'])
        result = self.video_settings(VIDEO_ANALYSIS_MODE='unknown')
        self.assertNotEqual(0, result.returncode)

    def test_optional_existing_worktree_ports_remain_valid(self):
        with self.config.open('a') as stream:
            stream.write('\nVIDEO_ANALYSIS_PORT=28014\nVAD_PORT=18181\n')
        self.assertEqual(0, self.shell().returncode)


class DockerAccessTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / "project ' $(touch should-not-run)"
        self.root.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        (self.root / 'local-ports.env').write_bytes(TOOL.parent.parent.joinpath('local-ports.env').read_bytes())
        self.bin = self.directory / 'bin'
        self.bin.mkdir()
        self.trace = self.directory / 'trace'
        self.result = self.directory / 'result.json'
        self.env = dict(os.environ, PATH=f'{self.bin}:{os.environ["PATH"]}',
                        TEST_DOCKER_MODE='stale', TEST_ACCOUNT_DOCKER='1', TEST_ACTIVE_DOCKER='0',
                        TEST_DOCKER_TRACE=str(self.trace), TEST_DOCKER_RESULT=str(self.result),
                        TEST_DOCKER_COMMON=str(TOOL.with_name('local-common.sh')),
                        HXJM_ANALYSIS_ROOT=str(self.root))
        self.executable('docker', '''#!/bin/bash
printf 'docker:%s\\n' "$*" >> "$TEST_DOCKER_TRACE"
[[ "$1" == info ]] || exit 91
if [[ "$TEST_DOCKER_MODE" == healthy || ( "$TEST_DOCKER_MODE" == stale && "$TEST_ACTIVE_DOCKER" == 1 ) ]]; then
    echo 27.0; exit 0
fi
if [[ "$TEST_DOCKER_MODE" == daemon ]]; then
    echo 'Cannot connect to the Docker daemon' >&2
elif [[ "$TEST_DOCKER_MODE" == remote ]]; then
    echo 'permission denied connecting to tcp://remote:2376' >&2
else
    echo 'permission denied connecting to unix:///var/run/docker.sock' >&2
fi
exit 1
''')
        self.executable('id', '''#!/bin/bash
if [[ "$1" == -nG ]]; then
    if [[ ( $# == 2 && "$TEST_ACCOUNT_DOCKER" == 1 ) || ( $# == 1 && "$TEST_ACTIVE_DOCKER" == 1 ) ]]; then
        echo 'user docker'
    else
        echo user
    fi
else
    exec /usr/bin/id "$@"
fi
''')
        self.executable('sg', '''#!/bin/bash
[[ $# == 3 && "$1" == docker && "$2" == -c ]] || exit 92
echo sg >> "$TEST_DOCKER_TRACE"
export TEST_ACTIVE_DOCKER=1
exec /bin/sh -c "$3"
''')
        self.launcher = self.executable('launcher', '''#!/bin/bash
set -euo pipefail
source "$TEST_DOCKER_COMMON" --worktree "$1"
ensure_docker_access "$0" "$ROOT_DIR" "argument with spaces and a single quote: '"
python3 -c 'import json,os,sys; from pathlib import Path; Path(os.environ["TEST_DOCKER_RESULT"]).write_text(json.dumps([sys.argv[1:], os.getcwd(), os.getuid()]))' "$ROOT_DIR" "argument with spaces and a single quote: '"
exit 37
''')

    def executable(self, name, content):
        path = self.bin / name
        path.write_text(content)
        path.chmod(0o755)
        return path

    def call(self, **overrides):
        script = ('set -euo pipefail; source "$1" --worktree "$2"; '
                  'ensure_docker_access "$3" "$2"; echo ready')
        return subprocess.run(['bash', '-c', script, 'bash', str(TOOL.with_name('local-common.sh')),
                               str(self.root), str(self.launcher)], cwd=self.directory,
                              env=dict(self.env, **overrides), text=True, capture_output=True, timeout=10)

    def test_healthy_docker_does_not_change_groups(self):
        result = self.call(TEST_DOCKER_MODE='healthy')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('ready\n', result.stdout)
        self.assertNotIn('sg', self.trace.read_text().splitlines())

    def test_stale_groups_relaunch_once_with_safe_arguments_and_exit_status(self):
        result = self.call()
        self.assertEqual(37, result.returncode, result.stderr)
        args, cwd, uid = json.loads(self.result.read_text())
        self.assertEqual([str(self.root), "argument with spaces and a single quote: '"], args)
        self.assertEqual(str(self.directory), cwd)
        self.assertEqual(os.getuid(), uid)
        self.assertFalse((self.directory / 'should-not-run').exists())
        self.assertEqual(1, self.trace.read_text().splitlines().count('sg'))
        self.assertEqual(2, self.trace.read_text().count('docker:info'))

    def test_unrelated_failures_and_missing_authorization_do_not_switch_groups(self):
        for overrides in ({'TEST_ACCOUNT_DOCKER': '0'}, {'TEST_ACTIVE_DOCKER': '1', 'TEST_DOCKER_MODE': 'denied'},
                          {'TEST_DOCKER_MODE': 'daemon'}, {'TEST_DOCKER_MODE': 'remote'}):
            with self.subTest(overrides=overrides):
                self.trace.write_text('')
                result = self.call(**overrides)
                self.assertNotEqual(0, result.returncode)
                self.assertIn('Cannot access Docker', result.stderr)
                self.assertNotIn('sg', self.trace.read_text().splitlines())
                self.assertFalse(self.result.exists())

    def test_startup_rejects_docker_before_building_or_stopping_services(self):
        result = subprocess.run(['bash', str(TOOL.with_name('start-local.sh')),
                                 '--worktree', str(self.root)],
                                env=dict(self.env, TEST_ACCOUNT_DOCKER='0'),
                                text=True, capture_output=True, timeout=10)
        self.assertNotEqual(0, result.returncode)
        self.assertIn('permission denied', result.stderr)
        self.assertNotIn('building', result.stdout)
        self.assertFalse((self.root / '.run').exists())
        self.assertEqual(1, self.trace.read_text().count('docker:info'))


class MediaConfigurationTest(unittest.TestCase):
    def setUp(self):
        import yaml
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.recording_root = self.root / 'external-storage/recordings'
        self.record_path = str(self.recording_root / '%path/%Y-%m-%d_%H-%M-%S-%f')
        self.config = self.root / 'local-ports.env'
        self.config.write_bytes(TOOL.parent.parent.joinpath('local-ports.env').read_bytes())
        self.settings = dict(line.split('=', 1) for line in self.config.read_text().splitlines()
                             if line and not line.startswith('#'))
        self.settings.update(MTX_RTSP_PORT='28654', MTX_WEBRTC_PORT='28989', MTX_API_PORT='20097',
                             AI_STREAM_PORT='29190', BACKEND_PORT='28180', SMARTMONITOR_AI_CONTROL_TOKEN='test',
                             VIDEO_ANALYSIS_MODE='local', LOCAL_MEDIA_ENABLED='true', CAMERA_IDS='1 2 3 4')
        self.state = self.root / '.run/local-runtime'
        spec = importlib.util.spec_from_file_location('local_config', TOOL.with_name('local-config.py'))
        self.config_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.config_module)
        algorithm = self.root / 'mtx/config.yaml'
        algorithm.parent.mkdir(parents=True)
        algorithm.write_text(yaml.safe_dump({
            'task_templates': {'boxmot': {'ipc_addr': 'ipc:///unused'}},
            'streams': [{'ai_tasks': [{'type': 'vad', 'ipc_addr': 'ipc:///unused'}]}],
        }))
        self.media_source = self.root / 'mtx/mediamtx/mediamtx.yml'
        self.media_source.parent.mkdir()
        hook = 'curl -X POST "http://example.invalid:8080/media-assets"'
        self.media_source.write_text(yaml.safe_dump({
            'pathDefaults': {'record': True, 'recordPath': self.record_path,
                             'recordDeleteAfter': '168h', 'runOnRecordSegmentComplete': hook},
            'paths': {'live/custom': {'source': 'publisher', 'record': True,
                                     'recordPath': str(self.root / '.run/recordings/old'),
                                     'runOnRecordSegmentComplete': hook}},
        }))
        logback = self.root / 'SmartMonitor-wangzj/hxjm-admin/src/main/resources/logback.xml'
        logback.parent.mkdir(parents=True)
        logback.write_text('<configuration><property name="log.path" value="./log"/></configuration>')

    def render(self):
        with patch.dict(os.environ, self.settings):
            return self.config_module.render(self.root, self.state)

    def test_generated_media_and_algorithm_config_use_local_endpoints(self):
        import yaml
        config = self.render()
        self.assertEqual('rtsp://127.0.0.1:28654/live', config['mediamtx_url'])
        self.assertEqual(29190, config['control']['listen_port'])
        self.assertEqual(f'ipc://{self.state}/ipc/boxmot.ipc', config['task_templates']['boxmot']['ipc_addr'])
        self.assertEqual(f'ipc://{self.state}/ipc/vad.ipc', config['ai_tasks_ipc']['vad'])
        media = yaml.safe_load((self.state / 'mediamtx.yml').read_text())
        self.assertEqual(':28989', media['webrtcAddress'])
        self.assertEqual(':20097', media['apiAddress'])
        self.assertIn('127.0.0.1:28180/media-assets', media['pathDefaults']['runOnRecordSegmentComplete'])
        self.assertEqual(self.record_path, media['pathDefaults']['recordPath'])
        self.assertEqual(self.record_path, media['paths']['live/custom']['recordPath'])
        self.assertEqual('168h', media['pathDefaults']['recordDeleteAfter'])
        self.assertIn('127.0.0.1:28180/media-assets', media['paths']['live/custom']['runOnRecordSegmentComplete'])
        self.assertFalse(self.recording_root.exists())

        self.settings.update(VIDEO_ANALYSIS_MODE='shared', SHARED_MEDIA_RTSP_BASE='rtsp://127.0.0.1:18554/live')
        self.render()
        media = yaml.safe_load((self.state / 'mediamtx.yml').read_text())
        self.assertFalse(media['pathDefaults']['record'])
        self.assertFalse(media['paths']['live/custom']['record'])
        self.assertEqual(self.record_path, media['paths']['live/custom']['recordPath'])
        self.assertNotIn('live/camera_1', media['paths'])
        self.assertNotIn('18554', str(media['paths']))
        sentinel = b'public media configuration belongs to another service'
        (self.state / 'mediamtx.yml').write_bytes(sentinel)
        self.settings['LOCAL_MEDIA_ENABLED'] = 'false'
        self.render()
        self.assertEqual(sentinel, (self.state / 'mediamtx.yml').read_bytes())
        self.assertFalse(self.recording_root.exists())

    def test_missing_recording_path_is_rejected(self):
        import yaml
        media = yaml.safe_load(self.media_source.read_text())
        for missing in ('recordPath', 'pathDefaults'):
            with self.subTest(missing=missing):
                invalid = dict(media)
                if missing == 'pathDefaults':
                    invalid.pop('pathDefaults')
                else:
                    invalid['pathDefaults'] = dict(media['pathDefaults'])
                    invalid['pathDefaults'].pop('recordPath')
                self.media_source.write_text(yaml.safe_dump(invalid))
                with self.assertRaisesRegex(ValueError, 'recordPath must be a nonempty absolute path'):
                    self.render()
                self.assertFalse((self.state / 'mediamtx.yml').exists())

    def test_empty_or_relative_recording_path_is_rejected(self):
        import yaml
        media = yaml.safe_load(self.media_source.read_text())
        for record_path in (None, '', '   ', './recordings/%path', 'recordings/%path', 123):
            with self.subTest(record_path=record_path):
                media['pathDefaults']['recordPath'] = record_path
                self.media_source.write_text(yaml.safe_dump(media))
                with self.assertRaisesRegex(ValueError, 'recordPath must be a nonempty absolute path'):
                    self.render()
                self.assertFalse((self.state / 'mediamtx.yml').exists())

    def test_invalid_media_yaml_does_not_expose_configuration(self):
        self.media_source.write_text('pathDefaults: [private-placeholder')
        with self.assertRaisesRegex(ValueError, '^Invalid media YAML; configuration contents were not printed$'):
            self.render()


if __name__ == '__main__':
    unittest.main()
