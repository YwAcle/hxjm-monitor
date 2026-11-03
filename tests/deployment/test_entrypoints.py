"""Behavioral tests: parsing is literal, ports/projects isolated, GPU opt-in."""
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
START=ROOT/'scripts/start.sh'
class Entrypoints(unittest.TestCase):
    def configure(self,*args,env=None):
        script='source "$1"; shift; configure --scope dev "$@"; "${COMPOSE[@]}" config --format json'
        return subprocess.run(['bash','-c',script,'bash',str(START),*args],env=dict(os.environ,**(env or {})),capture_output=True,text=True)
    def test_default_personal_has_no_gpu_or_model_dependency(self):
        r=self.configure();self.assertEqual(r.returncode,0,r.stderr)
        # Profiles deliberately remain disabled: no implicit model depends_on.
        d=json.loads(r.stdout)['services'];self.assertNotIn('depends_on',d.get('frontend',{}))
        # Ask Compose to materialize the selected profile for detailed assertions.
        r=subprocess.run(['bash','-c','source "$1"; configure --scope dev; "${COMPOSE[@]}" --profile frontend config --format json','bash',str(START)],capture_output=True,text=True)
        s=json.loads(r.stdout)['services']['frontend']
        self.assertEqual(s['network_mode'],'host');self.assertNotIn('deploy',s)
        self.assertNotIn('LLM_REMOTE_API_KEY',s['environment'])
    def test_cli_overrides_literal_config(self):
        with tempfile.TemporaryDirectory() as t:
            f=Path(t)/'env';f.write_text('FRONTEND_PORT=3198\nAGENT_URL=$(touch /tmp/hxjm-must-not-execute)\n')
            r=subprocess.run(['bash','-c','source "$1"; shift; configure --scope dev "$@"; printf "%s|%s" "$FRONTEND_PORT" "$AGENT_URL"','bash',str(START),'--config',str(f),'--frontend-port','3199'],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout,'3199|$(touch /tmp/hxjm-must-not-execute)')
            self.assertFalse(Path('/tmp/hxjm-must-not-execute').exists())
    def test_reserved_key_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            f=Path(t)/'env';f.write_text('ROOT=/tmp\n')
            r=self.configure('--config',str(f));self.assertNotEqual(r.returncode,0)
    def test_isolated_requires_private_infrastructure(self):
        self.assertNotEqual(self.configure('--scope','isolated','--infra','external').returncode,0)
    def test_gpu_not_implicitly_selected(self):
        r=subprocess.run(['bash',str(START),'--config',str(ROOT/'deploy/config/development.env.example'),'--scope','dev','--only','reid','--reid-port','28991','--check'],capture_output=True,text=True)
        self.assertNotEqual(r.returncode,0);self.assertIn('explicit GPU UUID',r.stderr)
    def test_invalid_port_and_conflict(self):
        for p in ['0','70000','bad']:
            r=subprocess.run(['bash',str(START),'--scope','dev','--only','backend','--backend-port',p,'--check'],capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0);self.assertIn('must be',r.stderr)
        with socket.socket() as s:
            s.bind(('0.0.0.0',0));s.listen();port=s.getsockname()[1]
            r=subprocess.run(['bash',str(START),'--scope','dev','--only','backend','--backend-port',str(port),'--check'],capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0);self.assertIn('occupied',r.stderr)
    def test_unreachable_dependency_does_not_spawn(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));port=s.getsockname()[1]
            r=subprocess.run(['bash',str(START),'--scope','dev','--check'],env=dict(os.environ,ANALYSIS_ENABLED='false',BACKEND_URL=f'http://127.0.0.1:{port}'),capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0);self.assertIn('Dependency unavailable',r.stderr)
    def test_stopping_does_not_start_check_or_remove_volumes(self):
        with tempfile.TemporaryDirectory() as t:
            command=Path(t)/'docker';log=Path(t)/'calls'
            command.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_DOCKER_LOG"\n')
            command.chmod(0o755)
            result=subprocess.run(['bash',str(ROOT/'scripts/stop.sh'),'--only','frontend'],
                env=dict(os.environ,PATH=t+':'+os.environ['PATH'],TEST_DOCKER_LOG=str(log)),capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            calls=log.read_text().splitlines()
            self.assertEqual(len(calls),1)
            self.assertTrue(calls[0].endswith(' stop frontend'),calls)
        self.assertEqual(sorted(p.name for p in (ROOT/'scripts').iterdir()),['start.sh','stop.sh'])
    def test_occupied_algorithm_port_is_reused_without_gpu_or_start(self):
        with tempfile.TemporaryDirectory() as t, socket.socket() as listener:
            listener.bind(('127.0.0.1',0));listener.listen()
            docker=Path(t)/'docker';log=Path(t)/'calls'
            docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_DOCKER_LOG"\n')
            docker.chmod(0o755)
            result=subprocess.run(['bash',str(START),'--only','reid','--reid-port',str(listener.getsockname()[1]),'--check'],
                env=dict(os.environ,PATH=t+':'+os.environ['PATH'],TEST_DOCKER_LOG=str(log)),capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('Reuse reid:',result.stdout)
            calls=log.read_text()
            self.assertNotIn(' up ',calls);self.assertNotIn(' run ',calls)
            self.assertNotIn(' build ',calls)

if __name__=='__main__':unittest.main()
