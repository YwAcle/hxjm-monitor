#!/usr/bin/env python3
"""Validate stage two only in a fresh, named disposable PostgreSQL database."""
import argparse
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('stage1_validate', ROOT.parent / 'stage1/validate.py')
stage1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage1)
run_sql = stage1.run_sql
LEGACY = ('camera', 'camera_stream', 'media_asset', 'tracklet', 'asset_reference',
          'episode', 'episode_tracklet_link', 'llm_report', 'vad')


def snapshot(args):
    result = {}
    for name in LEGACY:
        sql = f"""SELECT jsonb_build_object(
          'columns', (SELECT jsonb_object_agg(a.attname,jsonb_build_object(
            'type',format_type(a.atttypid,a.atttypmod),'not_null',a.attnotnull,
            'default',pg_get_expr(d.adbin,d.adrelid)))
            FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
            WHERE a.attrelid='public.{name}'::regclass AND a.attnum>0 AND NOT a.attisdropped),
          'constraints', (SELECT jsonb_object_agg(conname,pg_get_constraintdef(oid))
            FROM pg_constraint WHERE conrelid='public.{name}'::regclass),
          'rows', (SELECT jsonb_agg(to_jsonb(t) ORDER BY id) FROM public.{name} t));"""
        result[name] = json.loads(run_sql(args, sql).stdout)
    return result


def check_legacy(before, after, report_patch=False):
    for table, old in before.items():
        new = after[table]
        for name, definition in old['columns'].items():
            expected = dict(definition)
            if (table, name) in (('media_asset', 'stream_id'), ('asset_reference', 'retain_until')):
                expected['not_null'] = False
            if new['columns'].get(name) != expected:
                raise AssertionError(f'Unexpected retained field change: {table}.{name}')
        for name, definition in (old['constraints'] or {}).items():
            if table == 'asset_reference' and name == 'ck_asset_ref_stage1_owner':
                continue
            if report_patch and table == 'llm_report' and name == 'ck_llm_report_source_exclusive':
                continue
            if (new['constraints'] or {}).get(name) != definition:
                raise AssertionError(f'Unexpected retained constraint change: {table}.{name}')
        rows = [{k: v for k, v in row.items() if k in old['columns']}
                for row in new['rows'] or []]
        if rows != (old['rows'] or []):
            raise AssertionError(f'Legacy values were changed: {table}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container', required=True)
    parser.add_argument('--database', required=True)
    parser.add_argument('--user', default='hxjm_stage1_test')
    parser.add_argument('--fixture', choices=('path', 'uuid'), required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'hxjm_stage2_(?:path|uuid)_[a-z0-9_]+', args.database):
        raise SystemExit('Only a named disposable hxjm_stage2 database is accepted')
    run_sql(args, (ROOT.parent / f'stage1/fixture_{args.fixture}_streams.sql').read_text())
    run_sql(args, (ROOT.parent / 'stage1/001_video_results.sql').read_text())
    run_sql(args, (ROOT / 'fixture_business.sql').read_text())
    before = snapshot(args)
    migration = (ROOT / '002_identity_business.sql').read_text()
    run_sql(args, migration)
    check_legacy(before, snapshot(args))
    report_patch = (ROOT / '003_report_subject_constraint.sql').read_text()
    run_sql(args, report_patch)
    check_legacy(before, snapshot(args), report_patch=True)
    validation = run_sql(args, (ROOT / 'verify.sql').read_text())
    print('\n'.join(line for line in validation.stdout.splitlines() if line.strip()))
    expected = stage1.schema_snapshot(args)
    repeated = run_sql(args, migration, expect_success=False)
    if not repeated.returncode or 'already applied or partial/conflicting' not in repeated.stderr:
        raise AssertionError('Repeated stage-two migration was not rejected by preflight')
    if stage1.schema_snapshot(args) != expected:
        raise AssertionError('Rejected repeated migration changed the database schema')
    run_sql(args, report_patch)
    if stage1.schema_snapshot(args) != expected:
        raise AssertionError('Repeated report patch changed the database schema')
    print(f'{args.fixture}: retained values/types unchanged; only approved legacy report constraint removed; stage-two checks passed; '
          'repeat rejected without changes', flush=True)


if __name__ == '__main__':
    main()
