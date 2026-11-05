"""Runtime/config boundaries only; no inference, external service or robot calls."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[2]


class MonitorIntegrationTest(unittest.TestCase):
    def test_main_and_garbage_cannot_replace_each_other(self):
        result = subprocess.run(['bash', '-c',
            'source scripts/start.sh; configure --scope local --only analysis,garbage-analysis; '
            '"${COMPOSE[@]}" --profile analysis --profile garbage config --format json'],
            cwd=ROOT, capture_output=True, text=True,
            env=dict(os.environ, VIDEO_ANALYSIS_ALGORITHM='garbage'))
        self.assertEqual(0, result.returncode, result.stderr)
        services = json.loads(result.stdout)['services']
        main, garbage = services['analysis'], services['garbage-analysis']
        self.assertEqual('botsort', main['environment']['VIDEO_ANALYSIS_ALGORITHM'])
        self.assertEqual('garbage', garbage['environment']['VIDEO_ANALYSIS_ALGORITHM'])
        for key in ['VIDEO_RESULTS_SOURCE_MAP_FILE', 'VIDEO_RESULTS_SPOOL_DIR', 'VIDEO_RESULTS_CAPABILITY_CODE']:
            self.assertNotEqual(main['environment'][key], garbage['environment'][key])
        self.assertNotEqual(main['ports'], garbage['ports'])
        self.assertNotEqual(main['build']['args']['RUNTIME'], garbage['build']['args']['RUNTIME'])

    def test_behavior_prepare_only_adds_scoped_grants_and_server_coordination(self):
        from joyai_tool.prepare import prepare
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root/'private/settings.json'
            path.parent.mkdir()
            config = dict(token='fixture-only', tool_url='http://127.0.0.1:34204',
                          storage_root='/host-data', cameras={
                              f'camera_{i}': {'source_id': str(i)} for i in range(1, 5)})
            path.write_text(json.dumps(config))
            with patch.dict(os.environ, dict(JOYAI_CONFIG=str(path), RUNTIME_ROOT=str(root/'runtime'),
                JOYAI_BACKEND_TOOL_URL='http://host.docker.internal:34204')):
                prepare(root)
            profile = yaml.safe_load((root/'runtime/config/joyai-backend.yml').read_text())['hxjm']['business']
            self.assertNotIn('storage-root', profile)
            self.assertEqual('http://host.docker.internal:34204', profile['behavior']['url'])
            grant = profile['security']['services']['joyai-producer']
            self.assertIn('tasks.end', grant['operations'])
            self.assertNotIn('tasks.complete', grant['operations'])
            self.assertEqual(['1', '2', '3', '4'], grant['source-ids'])
            self.assertEqual(config, json.loads(path.read_text()))

    def test_launcher_only_controls_its_recorded_dummy_process(self):
        import sys
        script = ROOT/'apps/joyai/runtime.py'
        with tempfile.TemporaryDirectory(dir=ROOT/'.run') as folder:
            state = Path(folder)/'state'
            command = [sys.executable, str(script), '--root', str(ROOT), '--state', str(state)]
            started = subprocess.run(command+['start', 'joyai_tool', str(ROOT), str(Path(folder)/'test.log'),
                sys.executable, '-c', 'import time; time.sleep(60)'], capture_output=True, text=True)
            self.assertEqual(0, started.returncode, started.stderr)
            try:
                self.assertEqual(0, subprocess.run(command+['status', 'joyai_tool'], capture_output=True).returncode)
            finally:
                stopped = subprocess.run(command+['stop', 'joyai_tool'], capture_output=True, text=True)
                self.assertEqual(0, stopped.returncode, stopped.stderr)
            self.assertNotEqual(0, subprocess.run(command+['status', 'joyai_tool'], capture_output=True).returncode)
