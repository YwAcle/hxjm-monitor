"""Regression checks for cross-worktree ownership and orphan cleanup."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
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

    def test_active_record_does_not_require_repository_metadata(self):
        self.call('mark-active')
        record = json.loads((self.state / 'active.json').read_text())
        self.assertEqual(record['root'], str(self.root))
        self.assertIsNone(record['revision'])
        self.assertIn('started', record)

    def test_feature_service_is_owned_and_stopped(self):
        self.call('start', 'reid_feature', str(self.root), str(self.root / 'feature.log'),
                  sys.executable, '-c', 'import time; time.sleep(120)')
        record = json.loads((self.state / 'reid_feature.json').read_text())
        self.call('status', 'reid_feature')
        self.call('stop-all')
        self.assertIsNone(runtime.process(record['pid']))
        self.assertIsNone(self.peer.poll())

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


class PortConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / 'local-ports.env'
        self.config.write_bytes(TOOL.parent.parent.joinpath('local-ports.env').read_bytes())

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

    def test_primary_root_uses_directory_or_explicit_shared_assets(self):
        command = ['bash', '-c', 'set -euo pipefail; source "$1" --worktree "$2"; printf "%s" "$PRIMARY_ROOT"',
                   'bash', str(TOOL.with_name('local-common.sh')), str(self.root)]
        environment = {key: value for key, value in os.environ.items() if key != 'HXJM_PRIMARY_ROOT'}
        own = subprocess.run(command, env=environment, capture_output=True, text=True, check=True)
        self.assertEqual(own.stdout, str(self.root))
        primary = self.root / 'shared'
        primary.mkdir()
        explicit = subprocess.run(command, env=dict(environment, HXJM_PRIMARY_ROOT=str(primary)),
                                  capture_output=True, text=True, check=True)
        self.assertEqual(explicit.stdout, str(primary))

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
                  'PRIMARY_ROOT="$3"; load_video_config; python3 -c ' + shlex.quote(payload))
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

    def test_shared_worktree_reads_primary_ports_without_overwriting_its_own(self):
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
        self.assertEqual('rtsp://127.0.0.1:28554/live', settings['SHARED_MEDIA_RTSP_BASE'])
        self.assertEqual('http://127.0.0.1:28889', settings['SHARED_MEDIA_ORIGIN'])
        self.assertEqual(ports['MTX_RTSP_PORT'], settings['MTX_RTSP_PORT'])

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
        content = self.config.read_text()
        self.config.write_text('\n'.join(line for line in content.splitlines()
                                          if not line.startswith('VIDEO_ANALYSIS_PORT=')) + '\n')
        with self.config.open('a') as stream:
            stream.write('\nVIDEO_ANALYSIS_PORT=28014\nVAD_PORT=18181\n')
        self.assertEqual(0, self.shell().returncode)

    def test_generated_media_and_algorithm_config_use_local_endpoints(self):
        import yaml
        spec = importlib.util.spec_from_file_location('local_config', TOOL.with_name('local-config.py'))
        config_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config_module)
        for name in ('mtx/config.yaml', 'mtx/mediamtx/mediamtx.yml',
                     'SmartMonitor-wangzj/hxjm-admin/src/main/resources/logback.xml'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((TOOL.parent.parent / name).read_bytes())
        settings = dict(line.split('=', 1) for line in self.config.read_text().splitlines() if line and not line.startswith('#'))
        settings.update(MTX_RTSP_PORT='28654', MTX_WEBRTC_PORT='28989', MTX_API_PORT='20097',
                        AI_STREAM_PORT='29190', BACKEND_PORT='28180', SMARTMONITOR_AI_CONTROL_TOKEN='test',
                        VIDEO_ANALYSIS_MODE='local', LOCAL_MEDIA_ENABLED='true')
        state = self.root / '.run/local-runtime'
        with patch.dict(os.environ, settings):
            config = config_module.render(self.root, state)
        self.assertEqual('rtsp://127.0.0.1:28654/live', config['mediamtx_url'])
        self.assertEqual(29190, config['control']['listen_port'])
        self.assertEqual(f'ipc://{state}/ipc/boxmot.ipc', config['task_templates']['boxmot']['ipc_addr'])
        self.assertEqual(f'ipc://{state}/ipc/vad.ipc', config['ai_tasks_ipc']['vad'])
        media = yaml.safe_load((state / 'mediamtx.yml').read_text())
        self.assertEqual(':28989', media['webrtcAddress'])
        self.assertEqual(':20097', media['apiAddress'])
        self.assertIn('127.0.0.1:28180/media-assets', media['pathDefaults']['runOnRecordSegmentComplete'])
        self.assertTrue(media['pathDefaults']['recordPath'].startswith(str(self.root)))

        settings['VIDEO_ANALYSIS_RECORDING_ENABLED'] = 'yes'
        with patch.dict(os.environ, settings):
            config_module.render(self.root, state)
        media = yaml.safe_load((state / 'mediamtx.yml').read_text())
        self.assertFalse(media['pathDefaults']['record'])
        self.assertTrue(all(not path.get('record') for path in media['paths'].values()
                            if isinstance(path, dict)))

        settings.update(VIDEO_ANALYSIS_MODE='shared', SHARED_MEDIA_RTSP_BASE='rtsp://127.0.0.1:18554/live')
        with patch.dict(os.environ, settings):
            config_module.render(self.root, state)
        media = yaml.safe_load((state / 'mediamtx.yml').read_text())
        self.assertFalse(media['pathDefaults']['record'])
        for camera_id in range(1, 5):
            relay = media['paths'][f'live/camera_{camera_id}']
            self.assertEqual(f'rtsp://127.0.0.1:18554/live/camera_{camera_id}', relay['source'])
            self.assertFalse(relay['record'])
            self.assertEqual('tcp', relay['rtspTransport'])
        sentinel = b'public media configuration belongs to another service'
        (state / 'mediamtx.yml').write_bytes(sentinel)
        settings['LOCAL_MEDIA_ENABLED'] = 'false'
        with patch.dict(os.environ, settings):
            config_module.render(self.root, state)
        self.assertEqual(sentinel, (state / 'mediamtx.yml').read_bytes())


class CameraSourceConfigurationTest(unittest.TestCase):
    def configure(self, add_status, get_exit=0, patch_status=200):
        source = TOOL.with_name('start-local.sh').read_text()
        function = source[source.index('start_original_camera_sources() {'):
                          source.index('\nwait_for_camera_outputs()')]
        mocks = r'''
docker() { printf '1\trtsp://camera.fixture/stream\n'; }
info() { :; }
fail() { printf '%s\n' "$*" >&2; exit 1; }
curl() {
    local argument operation=unknown
    for argument in "$@"; do
        case "$argument" in
            */v3/config/paths/add/*) operation=add ;;
            */v3/config/paths/get/*) operation=get ;;
            */v3/config/paths/patch/*) operation=patch ;;
        esac
    done
    printf '%s\t%s\n' "$operation" "${!#}" >> "$TEST_CALLS"
    case "$operation" in
        add) printf '%s' "$TEST_ADD_STATUS" ;;
        get) return "$TEST_GET_EXIT" ;;
        patch) printf '%s' "$TEST_PATCH_STATUS" ;;
        *) return 99 ;;
    esac
}
'''
        with tempfile.TemporaryDirectory() as directory:
            calls = Path(directory) / 'calls'
            environment = dict(os.environ, LOCAL_MEDIA_ENABLED='true', VIDEO_ANALYSIS_MODE='local',
                               MTX_API_PORT='19997', TEST_CALLS=str(calls),
                               TEST_ADD_STATUS=str(add_status), TEST_GET_EXIT=str(get_exit),
                               TEST_PATCH_STATUS=str(patch_status))
            result = subprocess.run(['bash', '-c', 'set -euo pipefail\n' + mocks + function +
                                     '\nstart_original_camera_sources'],
                                    env=environment, capture_output=True, text=True)
            return result, [line.split('\t', 1) for line in calls.read_text().splitlines()]

    def test_new_path_is_created_without_update(self):
        result, calls = self.configure(201)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(['add'], [call[0] for call in calls])

    def test_existing_path_is_updated_from_device_configuration(self):
        for status in (400, 409):
            with self.subTest(status=status):
                result, calls = self.configure(status)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(['add', 'get', 'patch'], [call[0] for call in calls])
                payload = json.loads(calls[-1][1])
                self.assertEqual('rtsp://camera.fixture/stream', payload['source'])
                self.assertEqual('udp', payload['rtspTransport'])

    def test_unrelated_add_error_is_not_ignored(self):
        result, calls = self.configure(400, get_exit=22)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(['add', 'get'], [call[0] for call in calls])

    def test_invalid_source_update_is_not_ignored(self):
        result, calls = self.configure(400, patch_status=400)
        self.assertNotEqual(0, result.returncode)
        self.assertIn('HTTP 400', result.stderr)
        self.assertEqual(['add', 'get', 'patch'], [call[0] for call in calls])


if __name__ == '__main__':
    unittest.main()
