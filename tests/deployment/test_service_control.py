"""Test group routing without Docker, models or device connections."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ServiceControl(unittest.TestCase):
    def test_group_routing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / 'scripts'
            scripts.mkdir()
            agent = root / 'apps/llm/scripts'
            agent.mkdir(parents=True)
            for name in ('main.sh', 'robot-dog.sh', 'agent.sh'):
                shutil.copy(ROOT / 'scripts' / name, scripts / name)
            log = root / 'calls'
            recorder = 'printf "%s %s\\n" "${0##*/}" "$*" >> "$CALL_LOG"\n'
            (scripts / 'start.sh').write_text(
                '#!/bin/bash\nconfigure() { SCOPE=local; ONLY=frontend,backend,mediamtx,stream,analysis,reid; export RUNTIME_ROOT=/test; }\n'
                'if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then\n' + recorder + 'fi\n')
            for path in (scripts / 'stop.sh', scripts / 'joyai-tool.sh', agent / 'start.sh', agent / 'stop.sh'):
                path.write_text('#!/bin/bash\n' + recorder)
            env = dict(os.environ, CALL_LOG=str(log))
            def run(name, *args):
                result = subprocess.run(['bash', str(scripts / name), *args], env=env,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            run('main.sh', 'start', '--config', 'private.env')
            self.assertEqual(log.read_text().splitlines(), [
                'joyai-tool.sh check',
                'start.sh --config private.env --only frontend,backend,mediamtx,stream,analysis,reid',
                'joyai-tool.sh start'])
            log.write_text('')
            run('robot-dog.sh', 'stop')
            run('agent.sh', 'start')
            self.assertEqual(log.read_text().splitlines(), [
                'stop.sh --only garbage-analysis', 'start.sh '])
            for name in ('main.sh', 'robot-dog.sh', 'agent.sh'):
                result = subprocess.run(['bash', str(scripts / name), 'start', '--only', 'analysis'],
                                        env=env, capture_output=True)
                self.assertEqual(result.returncode, 2)
            log.write_text('')
            (scripts / 'joyai-tool.sh').write_text('#!/bin/bash\n' + recorder + 'exit 1\n')
            result = subprocess.run(['bash', str(scripts / 'main.sh'), 'stop'], env=env)
            self.assertEqual(result.returncode, 1)
            self.assertIn('stop.sh --only frontend,backend,mediamtx,stream,analysis,reid', log.read_text())


if __name__ == '__main__':
    unittest.main()
