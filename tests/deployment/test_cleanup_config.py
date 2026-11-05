"""Render-only assertions; never connect to a robot, model or database."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'modules/infrastructure/database/bootstrap'))
import bootstrap

class CleanupConfigTests(unittest.TestCase):
    source = '10000000-0000-4000-8000-000000000001'
    def render(self, **env):
        with tempfile.TemporaryDirectory() as directory, patch.object(bootstrap, 'OUT', Path(directory)), patch.dict(os.environ, dict(PIPELINE_TOKEN='x'*32, STREAM_TOKEN='y'*32, INSTANCE_NAMESPACE='fixture', **env), clear=True):
            bootstrap.render([dict(code='camera_1',source_id=self.source,url='rtsp://fixture/live')])
            return yaml.safe_load((Path(directory)/'backend.yml').read_text())['hxjm']['business']
    def test_disabled_does_not_offer_device_operation(self):
        config=self.render()
        self.assertFalse(config['cleanup']['enabled'])
        self.assertNotIn('robot-dog', config['execution']['services'])
    def test_mock_and_real_require_explicit_distinct_configuration(self):
        routes=json.dumps({self.source:'route1'})
        for mode,adapter,url in [('simulation','m20_mock','mock://local'),('m20','m20_route','ws://robot.invalid:8765/control')]:
            config=self.render(CLEANUP_MODE=mode,CLEANUP_SOURCE_ROUTES=routes,M20_CONTROL_URL=url)
            op=config['execution']['services']['robot-dog']['cleanup']
            self.assertEqual((op['adapter'],op['url']),(adapter,url))
            self.assertFalse(config['execution']['enabled'])
            self.assertEqual(config['cleanup']['routes'],{self.source:'route1'})
    def test_source_or_pixel_mapping_cannot_be_invented(self):
        for routes in [{self.source:'pixel:100,100'},{'camera_1':'route1'}]:
            with self.assertRaisesRegex(ValueError,'mapping'):
                self.render(CLEANUP_MODE='simulation',CLEANUP_SOURCE_ROUTES=json.dumps(routes))
