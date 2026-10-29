"""Shared-service configuration and real subprocess ownership, without cameras/CUDA."""
import importlib.util
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml


SCRIPT = Path(__file__).resolve().parents[1] / 'shared_service.py'
spec = importlib.util.spec_from_file_location('shared_service', SCRIPT)
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


class ConfigurationTests(unittest.TestCase):
    def test_environment_uses_shared_assets_and_drops_worktree_settings(self):
        settings = SimpleNamespace(ports={'MTX_RTSP_PORT': 18554}, model_root=Path('/main/models'),
                                   state=Path('/main/.run/shared-botsort'), gpu=1)
        with patch.dict(os.environ, {'HXJM_LOCAL_SERVICE_ID': 'other', 'HXJM_LOCAL_WORKTREE': '/other',
                                    'MTX_RTSPADDRESS': ':9999', 'VIDEO_ANALYSIS_WORKERS': '4',
                                    'VIDEO_ANALYSIS_CAMERAS': '{"wrong":"wrong"}', 'OPENBLAS_NUM_THREADS': '64'}):
            env = service.analysis_environment(settings, 'test-token')
        self.assertNotIn('HXJM_LOCAL_SERVICE_ID', env)
        self.assertNotIn('HXJM_LOCAL_WORKTREE', env)
        self.assertNotIn('MTX_RTSPADDRESS', env)
        self.assertEqual('1', env['HXJM_SHARED_SERVICE'])
        self.assertEqual('1', env['VIDEO_ANALYSIS_WORKERS'])
        self.assertEqual('1', env['OPENBLAS_NUM_THREADS'])
        self.assertEqual('1', env['VIDEO_ANALYSIS_DECODE_THREADS'])
        self.assertEqual('2', env['MALLOC_ARENA_MAX'])
        self.assertEqual('131072', env['MALLOC_TRIM_THRESHOLD_'])
        self.assertEqual('8', env['VIDEO_ANALYSIS_OPENCV_THREADS'])
        self.assertEqual('4', env['VIDEO_ANALYSIS_MEMORY_RESERVE_GIB'])
        self.assertEqual('3', env['VIDEO_ANALYSIS_MODEL_HEADROOM_GIB'])
        self.assertEqual(os.getenv('SHARED_BOTSORT_CUDA_GRAPH', '1'), env['VIDEO_ANALYSIS_CUDA_GRAPH'])
        self.assertEqual('/main/models', env['BOTSORT_ROOT'])
        cameras = json.loads(env['VIDEO_ANALYSIS_CAMERAS'])
        self.assertEqual(4, len(cameras))
        self.assertTrue(all(':18554/' in url for url in cameras.values()))

    def test_source_reader_never_exposes_credentials_on_failure(self):
        with patch.object(service.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stderr='secret', stdout='')):
            with self.assertRaisesRegex(RuntimeError, 'Cannot read camera sources') as error:
                service.read_sources()
        self.assertNotIn('secret', str(error.exception))
        sources = ''.join(f'{i}\trtsp://user:secret@camera-{i}/stream\n' for i in range(1, 5))
        with patch.object(service.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=sources)):
            self.assertEqual(4, len(service.read_sources()))

    def test_render_preserves_source_transport_and_single_recording_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'mtx/mediamtx/mediamtx.yml'
            source.parent.mkdir(parents=True)
            source.write_text(yaml.safe_dump({'pathDefaults': {'record': True, 'recordDeleteAfter': '168h',
                              'runOnRecordSegmentComplete': 'curl http://192.0.2.7:8080/media-assets'},
                              'paths': {'all_others': {}, 'live/camera_1': {'rtspTransport': 'tcp'}}}))
            settings = SimpleNamespace(root=root, ports={key: 19000 + i for i, (key, _) in enumerate(service.LISTENERS.values())}, record=True)
            settings.ports['BACKEND_PORT'] = 18080
            sources = {f'live/camera_{i}': f'rtsp://user:secret@host-{i}/stream' for i in range(1, 5)}
            with patch.dict(os.environ, {}, clear=True):
                rendered = yaml.safe_load(service.render_media(settings, sources))
            self.assertEqual('tcp', rendered['paths']['live/camera_1']['rtspTransport'])
            self.assertEqual('udp', rendered['paths']['live/camera_2']['rtspTransport'])
            self.assertEqual(sources['live/camera_1'], rendered['paths']['live/camera_1']['source'])
            self.assertEqual('168h', rendered['pathDefaults']['recordDeleteAfter'])
            self.assertIn('127.0.0.1:18080/media-assets', rendered['pathDefaults']['runOnRecordSegmentComplete'])
            settings.record = False
            rendered = yaml.safe_load(service.render_media(settings, sources))
            self.assertFalse(rendered['pathDefaults']['record'])
            self.assertTrue(all(not rendered['paths'][name]['record'] for name in sources))
            self.assertFalse(rendered['paths']['all_others']['record'])

    def test_logs_are_bounded_and_private(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'test.log'
            log = service.BoundedLog(path, 32)
            for _ in range(12):
                log.write(b'x' * 20)
            files = list(Path(temp).iterdir())
            self.assertLessEqual(len(files), 4)
            self.assertTrue(all(item.stat().st_size <= 32 for item in files))
            self.assertTrue(all(item.stat().st_mode & 0o777 == 0o600 for item in files))

    def test_occupied_port_is_reported_without_touching_owner(self):
        with socket.socket() as owner:
            owner.bind(('127.0.0.1', 0))
            owner.listen()
            settings = SimpleNamespace(analysis_port=owner.getsockname()[1])
            with self.assertRaisesRegex(RuntimeError, 'occupied.*Nothing was stopped'):
                service.check_ports(settings, 'analysis')
            self.assertTrue(service.listening(settings.analysis_port))

    def test_stale_pid_cannot_match_unrelated_process(self):
        current = service.process(os.getpid())
        self.assertFalse(service.same_process(dict(current, token='different'), 'manager'))
        self.assertFalse(service.same_process(dict(current, start='wrong-start'), 'manager'))

    def test_recently_closed_tcp_sessions_do_not_block_service_restart(self):
        with socket.socket() as owner:
            owner.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            owner.bind(('127.0.0.1', 0))
            owner.listen()
            port = owner.getsockname()[1]
            with socket.create_connection(('127.0.0.1', port)) as client:
                accepted, _ = owner.accept()
                accepted.close()
                self.assertEqual(b'', client.recv(1))
        service.check_ports(SimpleNamespace(analysis_port=port), 'analysis')


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = dict(os.environ)
        self.env.update(SHARED_BOTSORT_PYTHON=str(self.root / 'analysis'), PYTHONDONTWRITEBYTECODE='1')
        self.ports = {}
        used = set()
        for key, kind in service.LISTENERS.values():
            while True:
                with socket.socket(socket.AF_INET, kind) as probe:
                    probe.bind(('127.0.0.1', 0))
                    port = probe.getsockname()[1]
                if port not in used:
                    break
            used.add(port)
            self.ports[key] = port
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            self.env['SHARED_BOTSORT_ANALYSIS_PORT'] = str(probe.getsockname()[1])
        self.ports['BACKEND_PORT'] = 18080
        (self.root / 'local-ports.env').write_text(''.join(f'{key}={port}\n' for key, port in self.ports.items()))
        for relative in ('python/tracker/BoT-SORT/pretrained/bytetrack_x_mot17.pth.tar',
                         'python/tracker/BoT-SORT/pretrained/mot17_sbs_S50.pth',
                         'python/tracker/BoT-SORT/fast_reid/configs/MOT17/sbs_S50.yml'):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'test fixture only')
        media = self.root / 'mtx/mediamtx/mediamtx'
        media.parent.mkdir(parents=True)
        (media.parent / 'mediamtx.yml').write_text('pathDefaults: {record: true}\npaths: {}\n')
        fake_service = '''#!PYTHON
import os,signal,socket,subprocess,sys,time,yaml
if os.environ['HXJM_SHARED_ROLE'] == 'analysis':
    ports = [int(sys.argv[sys.argv.index('--port') + 1])]
    subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)'])
else:
    with open(sys.argv[1]) as stream:
        config = yaml.safe_load(stream)
    ports = [int(config[name].rsplit(':',1)[1]) for name in ['rtspAddress','apiAddress']]
sockets=[]
for port in ports:
    sock=socket.socket(); sock.bind(('0.0.0.0',port)); sock.listen(); sockets.append(sock)
print('test child ready',flush=True)
while True: time.sleep(.1)
'''.replace('PYTHON', sys.executable)
        for executable in (media, self.root / 'analysis'):
            executable.write_text(fake_service)
            executable.chmod(0o700)
        docker = self.root / 'bin/docker'
        docker.parent.mkdir()
        docker.write_text('#!' + sys.executable + '\nfor i in range(1,5): print(str(i) + "\\trtsp://user:secret@fixture-"+str(i)+"/stream")\n')
        docker.chmod(0o700)
        self.env['PATH'] = str(docker.parent) + os.pathsep + self.env.get('PATH', '')
        self.peer = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])

    def call(self, command, check=True):
        result = subprocess.run([sys.executable, str(SCRIPT), command, '--root', str(self.root)],
                                env=self.env, capture_output=True, text=True, timeout=35)
        if check:
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return result

    def tearDown(self):
        try:
            self.call('stop')
        finally:
            self.peer.terminate()
            self.peer.wait()
            self.temp.cleanup()

    def test_singleton_stop_and_orphan_recovery_preserve_unrelated_process(self):
        first = json.loads(self.call('start').stdout)
        second = json.loads(self.call('start').stdout)
        self.assertEqual(first['pid'], second['pid'])
        record = service.read_json(self.root / '.run/shared-botsort/service.json')
        token = record['token']
        self.assertIsNone(self.peer.poll())
        config = self.root / '.run/shared-botsort/mediamtx.yml'
        self.assertEqual(0o600, config.stat().st_mode & 0o777)
        self.assertNotIn('secret', self.call('status').stdout)
        os.kill(record['pid'], signal.SIGKILL)
        deadline = time.monotonic() + 3
        while service.same_process(record, 'manager') and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertTrue(service.owned_children(token))
        third = json.loads(self.call('start').stdout)
        self.assertNotEqual(first['pid'], third['pid'])
        self.assertFalse(service.owned_children(token))
        new_token = service.read_json(self.root / '.run/shared-botsort/service.json')['token']
        self.call('stop')
        self.assertFalse(service.owned_children(new_token))
        self.assertIsNone(self.peer.poll())
        self.call('stop')

    def test_concurrent_start_is_singleton_and_child_restart_has_backoff(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            starts = list(pool.map(lambda _: json.loads(self.call('start').stdout), range(2)))
        self.assertEqual(starts[0]['pid'], starts[1]['pid'])
        self.assertTrue(all(item['phase'] == 'running' for item in starts))
        old = starts[0]['children']['media']
        before = time.monotonic()
        os.kill(old['pid'], signal.SIGTERM)
        deadline = before + 8
        replacement = None
        while time.monotonic() < deadline:
            record = service.read_json(self.root / '.run/shared-botsort/service.json')
            media = record.get('children', {}).get('media')
            if media and media['pid'] != old['pid']:
                replacement = media
                break
            time.sleep(.1)
        self.assertIsNotNone(replacement)
        self.assertGreaterEqual(time.monotonic() - before, 2)
        self.assertIsNone(self.peer.poll())


if __name__ == '__main__':
    unittest.main()
