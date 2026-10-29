#!/usr/bin/env python3
"""Apply synthetic fixtures and validate stage 1 in an explicit Docker test database.

The caller prepares the isolated container and an empty database. This script
does not create databases, start containers, or accept a host/production DSN.
Example: python -B validate.py --container TEST_CONTAINER --database TEST_DB --fixture path
"""
import argparse
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parent
LEGACY_TABLES = ('camera', 'camera_stream', 'media_asset', 'tracklet')


def run_sql(args, sql, *, expect_success=True):
    command = ['docker', 'exec', '-i', args.container, 'psql', '-X', '-q', '-A', '-t',
               '-v', 'ON_ERROR_STOP=1', '-h', '/var/run/postgresql',
               '-U', args.user, '-d', args.database]
    completed = subprocess.run(command, input=sql, text=True, capture_output=True, check=False)
    if expect_success and completed.returncode:
        raise RuntimeError(completed.stderr.strip() or 'isolated psql command failed')
    return completed


def snapshot(args, *, include_rows):
    parts = []
    for name in LEGACY_TABLES:
        rows = f"(SELECT jsonb_agg(to_jsonb(t) ORDER BY id) FROM public.{name} t)" if include_rows else "'null'::jsonb"
        parts.append(f"""'{name}', jsonb_build_object(
          'columns', (SELECT jsonb_object_agg(a.attname, jsonb_build_object(
            'type', format_type(a.atttypid,a.atttypmod), 'not_null', a.attnotnull,
            'default', pg_get_expr(d.adbin,d.adrelid)))
            FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
            WHERE a.attrelid='public.{name}'::regclass AND a.attnum>0 AND NOT a.attisdropped),
          'constraints', (SELECT jsonb_object_agg(conname,pg_get_constraintdef(oid))
            FROM pg_constraint WHERE conrelid='public.{name}'::regclass),
          'rows', {rows})""")
    sql = 'SELECT jsonb_build_object(' + ','.join(parts) + ');'
    return json.loads(run_sql(args, sql).stdout)


def check_legacy(before, after):
    for name in LEGACY_TABLES:
        original = before[name]
        current = after[name]
        for field, definition in original['columns'].items():
            expected = dict(definition)
            if name == 'media_asset' and field == 'play_url':
                expected['not_null'] = False
            if current['columns'].get(field) != expected:
                raise AssertionError(f'legacy column changed unexpectedly: {name}.{field}')
        for constraint, definition in (original['constraints'] or {}).items():
            if name == 'media_asset' and constraint == 'chk_media_asset_type':
                continue
            if (current['constraints'] or {}).get(constraint) != definition:
                raise AssertionError(f'legacy constraint changed unexpectedly: {name}.{constraint}')
        columns = original['columns']
        rows = [{key: value for key, value in row.items() if key in columns}
                for row in (current['rows'] or [])]
        if rows != (original['rows'] or []):
            raise AssertionError(f'legacy data changed during migration: {name}')
    if after['camera_stream'] != before['camera_stream']:
        raise AssertionError('camera_stream must remain unchanged')


def schema_snapshot(args):
    sql = """SELECT jsonb_build_object(
      'tables', (SELECT jsonb_agg(jsonb_build_array(c.relname,a.attname,a.attnum,
        format_type(a.atttypid,a.atttypmod),a.attnotnull,pg_get_expr(d.adbin,d.adrelid))
        ORDER BY c.relname,a.attnum)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid
        LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
        WHERE n.nspname='public' AND c.relkind IN ('r','p') AND a.attnum>0 AND NOT a.attisdropped),
      'constraints', (SELECT jsonb_agg(jsonb_build_array(c.relname,k.conname,pg_get_constraintdef(k.oid))
        ORDER BY c.relname,k.conname)
        FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'),
      'indexes', (SELECT jsonb_agg(jsonb_build_array(tablename,indexname,indexdef)
        ORDER BY tablename,indexname) FROM pg_indexes WHERE schemaname='public'));
    """
    return json.loads(run_sql(args, sql).stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container', required=True, help='explicit isolated PostgreSQL container')
    parser.add_argument('--database', required=True, help='existing empty disposable database')
    parser.add_argument('--user', default='postgres', help='container-local PostgreSQL role')
    parser.add_argument('--fixture', choices=('path', 'uuid'), required=True)
    args = parser.parse_args()

    fixture = ROOT / f'fixture_{args.fixture}_streams.sql'
    migration = (ROOT / '001_video_results.sql').read_text()
    run_sql(args, fixture.read_text())
    before = snapshot(args, include_rows=True)
    run_sql(args, migration)
    check_legacy(before, snapshot(args, include_rows=True))
    validation = run_sql(args, (ROOT / 'verify.sql').read_text())
    print('\n'.join(line for line in validation.stdout.splitlines() if line.strip()))

    expected = schema_snapshot(args)
    repeated = run_sql(args, migration, expect_success=False)
    if not repeated.returncode or 'already applied or partial/conflicting' not in repeated.stderr:
        raise AssertionError('a repeated migration must be explicitly rejected by preflight')
    if schema_snapshot(args) != expected:
        raise AssertionError('rejected repeated migration changed the schema')
    print(f'{args.fixture}: legacy values/types/constraints preserved; normal chain and '
          'constraint checks passed; repeated migration rejected without schema changes.')


if __name__ == '__main__':
    main()
