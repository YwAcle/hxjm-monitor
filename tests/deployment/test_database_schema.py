"""Authority checks; opt-in live regressions run only in an isolated test database."""
import json
import os
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
DATABASE = ROOT / 'modules/infrastructure/database'
sys.path.insert(0, str(DATABASE / 'bootstrap'))
import schema


class DatabaseContractTests(unittest.TestCase):
    def test_every_current_table_has_one_owner(self):
        owners = json.loads((DATABASE / 'table-ownership.json').read_text())
        for db in ('mysql', 'postgres'):
            sql = '\n'.join(item[2] for item in schema.migrations(db))
            names = re.findall(r'CREATE TABLE (?:public\.)?`?(\w+)', sql)
            self.assertEqual(len(names), len(set(names)))
            self.assertEqual(set(names) | {schema.HISTORY}, set(owners[db]))
            self.assertTrue(all(t['owner'] in {'Business', 'Capability', 'Infrastructure'} for t in owners[db].values()))

    def test_formal_sql_references_have_tables(self):
        owners = json.loads((DATABASE / 'table-ownership.json').read_text())
        for part in ['business', 'capability']:
            for p in (ROOT / 'modules' / part).rglob('*'):
                if p.suffix not in {'.java', '.py', '.xml'} or set(p.parts) & {'target', 'test', 'tests', '__pycache__'}:
                    continue
                names = re.findall(r'\b(?:FROM|JOIN|INTO|UPDATE)\s+public\.(\w+)', p.read_text(), re.I)
                self.assertFalse(set(names) - set(owners['postgres']), str(p))

    def test_mapper_tables_are_in_the_current_model(self):
        owners = json.loads((DATABASE / 'table-ownership.json').read_text())
        expected = set(owners['mysql']) | set(owners['postgres'])
        for base in ['modules/business/java', 'modules/infrastructure/java']:
            for p in (ROOT/base).rglob('*.xml'):
                if 'target' in p.parts or p.parent.name not in {'algdeployment','basedata','system','quartz'}:
                    continue
                text = re.sub(r'<!--.*?-->', '', p.read_text(), flags=re.S)
                names = re.findall(r'\b(?:FROM|JOIN|INTO)\s+(?!public\.)([a-zA-Z_][a-zA-Z0-9_]*)(?![a-zA-Z0-9_.])', text, re.I)
                self.assertFalse({name for name in names if name.lower() != 'lateral'} - expected, str(p))

    def test_retired_structures_are_absent(self):
        sql = '\n'.join(s for db in ('mysql', 'postgres') for _, _, s in schema.migrations(db))
        for name in ['ai_task_run', 'legacy_run_id', 'legacy_identity_map', 'unified_event',
                     'reid_target_vit', 'face_recognition_events_copy', 'tbl_cameras', 'tbl_floors', 'tbl_testTexts', 'tbl_videos']:
            self.assertNotRegex(sql, r'\b' + name + r'\b')
        self.assertFalse((DATABASE / 'postgresql').exists())
        self.assertFalse((DATABASE / 'bootstrap/schema-manifest.json').exists())

    def test_http_capability_is_in_the_baseline(self):
        sql = schema.migrations('postgres')[0][2]
        for field in ['task_output', 'execution_snapshot', 'execution_namespace', 'executor_id',
                      'execution_token', 'send_phase', 'resource_scope', 'dispatch_mode', 'agent_json']:
            self.assertRegex(sql, r'\b' + field + r'\b')
        self.assertNotIn('capability_legacy_scope', sql)

    def test_upgrade_validates_both_targets_before_writing(self):
        with patch.object(schema, 'history', side_effect=[[], ValueError('postgres drift')]), patch.object(schema, 'apply_pending') as apply:
            with self.assertRaisesRegex(ValueError, 'postgres drift'):
                schema.upgrade({'mysql': object(), 'postgres': object()})
            apply.assert_not_called()

    def test_rebuild_requires_exact_local_opt_in_before_sql(self):
        import bootstrap
        from unittest.mock import Mock
        m, p = Mock(), Mock()
        env = {'HXJM_DATABASE_ENV':'isolated-local', 'MYSQL_HOST':'mysql', 'POSTGRES_HOST':'postgres',
               'MYSQL_DATABASE':'hxjm_test', 'POSTGRES_DATABASE':'hxjm_test'}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(ValueError, 'both exact targets'):
                bootstrap.rebuild(m, p, [], 'wrong')
        with patch.dict(os.environ, dict(env, MYSQL_HOST='external.invalid'), clear=True):
            with self.assertRaisesRegex(ValueError, 'external endpoints'):
                bootstrap.rebuild(m, p, [], 'wrong')
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'isolated-local'):
                bootstrap.rebuild(m, p, [], 'wrong')
        m.cursor.assert_not_called()
        p.execute.assert_not_called()


@unittest.skipUnless(os.getenv('HXJM_ISOLATED_DATABASE_TEST') == '1', 'requires explicit isolated DB environment')
class LiveDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import bootstrap
        # These tests must never use the regular deployment DB or an external endpoint.
        if (os.environ['MYSQL_DATABASE'], os.environ['POSTGRES_DATABASE']) != ('hxjm_sm_refactor', 'hxjm_refactor'):
            raise ValueError('Wrong integration databases')
        if {os.environ['MYSQL_HOST'], os.environ['POSTGRES_HOST']} - {'127.0.0.1'}:
            raise ValueError('Use the private shared container namespace')
        cls.bootstrap = bootstrap
        cls.mysql, cls.postgres = bootstrap.connections()

    @classmethod
    def tearDownClass(cls):
        cls.mysql.close()
        cls.postgres.close()

    def test_initialized_structure_and_repeatable_upgrade(self):
        connections = {'mysql': self.mysql, 'postgres': self.postgres}
        schema.check(connections)
        schema.upgrade(connections)
        for db, c in connections.items():
            self.assertEqual(len(schema.history(c, db)), len(schema.migrations(db)))
            expected = json.loads((DATABASE / 'table-ownership.json').read_text())[db]
            self.assertEqual(set(schema.tables(c, db)), set(expected))

    def test_initialized_seed_relations(self):
        m = schema.rows(self.mysql, 'mysql', 'SELECT user_id,role_id FROM sys_user_role')
        self.assertIn((1, 1), m)
        self.assertEqual(self.postgres.execute('SELECT count(*) FROM public.camera_stream s JOIN public.camera c ON c.id=s.camera_id').fetchone()[0], 1)
        devices = {r[0] for r in schema.rows(self.mysql, 'mysql', 'SELECT machine_id FROM ba_machine')}
        sources = self.postgres.execute('SELECT management_device_id,channel_code FROM public.camera').fetchall()
        self.assertTrue(all(r[0] in devices and r[1] == 'raw' for r in sources))
        types = self.postgres.execute('SELECT type_code FROM public.result_type ORDER BY type_code').fetchall()
        self.assertEqual([r[0] for r in types], ['behavior.assessment', 'garbage.detection'])

    def test_existing_database_is_not_implicitly_erased(self):
        with self.assertRaisesRegex(ValueError, 'MySQL is not empty'):
            self.bootstrap.initialize(self.mysql, self.postgres, [])
        schema.check({'mysql': self.mysql, 'postgres': self.postgres})

    def test_changed_sql_checksum_is_rejected(self):
        original = schema.migrations('postgres')
        changed = [(original[0][0], '0' * 64, original[0][2])]
        with patch.object(schema, 'migrations', return_value=changed):
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                schema.history(self.postgres, 'postgres')

    def test_schema_drift_is_rejected_without_committing(self):
        with self.postgres.transaction(force_rollback=True):
            self.postgres.execute('CREATE TABLE public.refactor_drift_probe(id integer)')
            with self.assertRaisesRegex(ValueError, 'schema drift'):
                schema.history(self.postgres, 'postgres')
        schema.history(self.postgres, 'postgres')

    def test_postgres_pending_migration_and_fingerprint(self):
        import tempfile
        migrations = schema.migrations('postgres')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for version, _, sql in migrations:
                (root/version).mkdir()
                (root/version/'postgres.sql').write_text(sql)
            (root/'0003_probe').mkdir()
            (root/'0003_probe/postgres.sql').write_text('ALTER TABLE public.task_output ADD COLUMN upgrade_probe text;')
            with self.postgres.transaction(force_rollback=True), patch.object(schema, 'MIGRATIONS', root):
                schema.apply_pending(self.postgres, 'postgres')
                self.assertEqual(len(schema.history(self.postgres, 'postgres')), len(migrations)+1)
        self.assertEqual(len(schema.history(self.postgres, 'postgres')), len(migrations))

    def test_task_attempt_and_output_relations(self):
        from uuid import uuid4
        from psycopg.errors import ForeignKeyViolation
        task, run = str(uuid4()), str(uuid4())
        with self.postgres.transaction(force_rollback=True):
            self.postgres.execute("INSERT INTO public.business_task(task_id,task_kind,actor_key,input_digest,expires_at) VALUES(%s,'test','test',%s,now()+interval '1 hour')", (task, '0'*64))
            self.postgres.execute("INSERT INTO public.task_attempt(run_id,task_id,generation,implementation_code,implementation_version,expires_at) VALUES(%s,%s,1,'test','1',now()+interval '1 hour')", (run, task))
            self.postgres.execute("INSERT INTO public.task_output(task_id,run_id,result_type,schema_version,payload_json,producer_result_key,payload_digest) VALUES(%s,%s,'garbage.detection','1','{}','test',%s)", (task, run, '0'*64))
            self.assertEqual(self.postgres.execute('SELECT task_id::text FROM public.task_output WHERE run_id=%s', (run,)).fetchone()[0], task)
            other = str(uuid4())
            self.postgres.execute("INSERT INTO public.business_task(task_id,task_kind,actor_key,input_digest,expires_at) VALUES(%s,'other','test',%s,now()+interval '1 hour')", (other, '0'*64))
            with self.assertRaises(ForeignKeyViolation):
                with self.postgres.transaction():
                    self.postgres.execute("INSERT INTO public.task_output(task_id,run_id,result_type,schema_version,payload_json,producer_result_key,payload_digest) VALUES(%s,%s,'garbage.detection','1','{}','mismatch',%s)", (other, run, '0'*64))
