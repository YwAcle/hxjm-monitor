"""Checks for the migration's executable module boundaries, without services."""
import ast
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
NS = {'m': 'http://maven.apache.org/POM/4.0.0'}


class ModuleLayoutTests(unittest.TestCase):
    def test_reactor_modules_and_parent_paths_resolve(self):
        parent = ROOT / 'apps/backend/pom.xml'
        reactor = ET.parse(parent)
        paths = [(parent.parent / m.text).resolve() for m in reactor.findall('m:modules/m:module', NS)]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertTrue(any('/modules/capability/' in str(p) for p in paths))
        for path in paths:
            child = ET.parse(path / 'pom.xml')
            rel = child.find('m:parent/m:relativePath', NS)
            self.assertEqual((path / (rel.text if rel is not None else '../pom.xml')).resolve(), parent)

    def test_agent_and_ai_infra_do_not_import_business_implementation(self):
        for module in ['agent', 'ai-infra']:
            for p in (ROOT / 'modules' / module / 'python').rglob('*.py'):
                for node in ast.walk(ast.parse(p.read_text())):
                    imports = [node.module or ''] if isinstance(node, ast.ImportFrom) else (
                        [a.name for a in node.names] if isinstance(node, ast.Import) else [])
                    self.assertFalse(any(name.split('.')[0] in {'business_api', 'llm_report_service', 'sqlalchemy'}
                                         for name in imports), str(p))

    def test_algorithm_factories_resolve_the_single_source(self):
        from video_analysis.algorithms import ALGORITHMS
        from video_analysis.botsort_adapter import BOT_ROOT
        from reid_feature_service.server import REID_ROOT
        import importlib.util
        for spec in ALGORITHMS.values():
            self.assertIsNotNone(importlib.util.find_spec(spec.factory.split(':')[0]))
        self.assertEqual(BOT_ROOT, ROOT / 'modules/perception-devices/vendor/botsort')
        self.assertTrue((BOT_ROOT / 'tracker/bot_sort.py').is_file())
        self.assertTrue((REID_ROOT / 'CLIP-ReID/model/make_model.py').is_file())
        self.assertFalse((ROOT / 'modules/perception-devices/stream/python').exists())

    def test_business_schema_source_and_access_assets_exist(self):
        from flask import Flask
        from business_api.routes import install_gallery_api
        app = Flask(__name__)
        install_gallery_api(app)  # Parses authority schemas but never creates a DB client.
        self.assertTrue(any(str(r) == '/api/v1/business/gallery/<operation>' for r in app.url_map.iter_rules()))
        self.assertTrue((ROOT / 'modules/access/garbage-web/open.html').is_file())
        self.assertTrue((ROOT / 'modules/access/garbage-web/index.html').is_file())

    def test_runtime_images_copy_current_module_sources(self):
        for filename in ['backend', 'frontend', 'python', 'stream', 'init']:
            for line in (ROOT / 'deploy/containers' / (filename + '.Dockerfile')).read_text().splitlines():
                if not line.startswith('COPY ') or '--from=' in line or '${' in line:
                    continue
                source = line.split()[1]
                self.assertTrue(any(ROOT.glob(source)), source)
