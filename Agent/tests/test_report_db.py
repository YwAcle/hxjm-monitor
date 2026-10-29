from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy.exc import ProgrammingError

from llm_report_service.config import DbConfig
from llm_report_service.db import episode_repo, media_repo, report_repo, session, stranger_repo, vad_repo


NOW = datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc)


class FakeResult:
    def __init__(self, *, rows=None, scalar=None):
        self.rows = list(rows or [])
        self.scalar_value = scalar

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows

    def scalar(self):
        return self.scalar_value


class FakeConnection:
    def __init__(self, engine):
        self.engine = engine

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, statement, params=None):
        self.engine.calls.append((str(statement), params or {}))
        outcome = self.engine.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeEngine:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.connect_count = 0
        self.begin_count = 0

    def connect(self):
        self.connect_count += 1
        return FakeConnection(self)

    def begin(self):
        self.begin_count += 1
        return FakeConnection(self)


def undefined_column_error(message='column m.play_url does not exist'):
    return ProgrammingError('select', {}, Exception({'C': '42703', 'M': message}))


def episode_row(**overrides):
    row = {'id': 12, 'start_ts': NOW, 'end_ts': NOW, 'meta': {'kind': 'entry'}}
    row.update(overrides)
    return row


def tracklet_row(**overrides):
    row = {
        'id': 21,
        'stream_id': 4,
        'start_ts': NOW,
        'end_ts': None,
        'color_rgb': [1, 2, 3],
        'trajectory_points': [{'x': 10, 'y': 20}],
        'query_asset_base64': 'image-data',
        'stranger_target_id': 'stranger-1',
    }
    row.update(overrides)
    return row


def media_row(**overrides):
    row = {
        'id': 31,
        'stream_id': 4,
        'asset_type': 'clip',
        'start_ts': NOW,
        'duration_ms': '2500',
        'path': '/media/clip.mp4',
        'content_type': None,
    }
    row.update(overrides)
    return row


def vad_row(**overrides):
    row = {
        'id': '41',
        'created_at': NOW,
        'media_asset_id': 31,
        'stream_id': None,
        'frame_vad_base64': None,
        'anomaly_name': 'fall',
        'anomaly_level': '2',
    }
    row.update(overrides)
    return row


class EpisodeRepoTests(unittest.TestCase):
    def test_count_episodes_handles_value_and_empty_result(self):
        self.assertEqual(episode_repo.count_episodes(FakeEngine(FakeResult(rows=[{'cnt': '3'}])), 'public'), 3)
        self.assertEqual(episode_repo.count_episodes(FakeEngine(FakeResult()), 'public'), 0)

    def test_fetch_episode_batch_converts_rows_and_parameters(self):
        engine = FakeEngine(FakeResult(rows=[episode_row()]))
        rows = episode_repo.fetch_episode_batch(engine, 'tenant', '2', '5')

        self.assertEqual(rows, [episode_repo.EpisodeRow('12', NOW, NOW, {'kind': 'entry'})])
        sql, params = engine.calls[0]
        self.assertIn('from tenant.episode', sql)
        self.assertEqual(params, {'offset': 2, 'limit': 5})

    def test_fetch_pending_episodes_adds_optional_since_filter(self):
        engine = FakeEngine(FakeResult(rows=[episode_row()]))
        rows = episode_repo.fetch_pending_episodes(engine, 'public', 'security', 7, NOW)

        self.assertEqual(rows[0].id, '12')
        sql, params = engine.calls[0]
        self.assertIn('not exists', sql)
        self.assertIn('e.start_ts >= :since_ts', sql)
        self.assertEqual(params, {'prompt_type': 'security', 'limit': 7, 'since_ts': NOW})

    def test_fetch_primary_tracklet_handles_row_and_missing_row(self):
        found_engine = FakeEngine(FakeResult(rows=[tracklet_row()]))
        row = episode_repo.fetch_primary_tracklet(found_engine, 'public', 'episode-1')

        self.assertEqual(row.id, '21')
        self.assertEqual(row.stream_id, '4')
        self.assertEqual(row.color_rgb, [1, 2, 3])
        self.assertEqual(found_engine.calls[0][1], {'episode_id': 'episode-1'})
        self.assertIsNone(episode_repo.fetch_primary_tracklet(FakeEngine(FakeResult()), 'public', 'missing'))


class VadRepoTests(unittest.TestCase):
    def test_count_vads_handles_value_and_empty_result(self):
        self.assertEqual(vad_repo.count_vads(FakeEngine(FakeResult(rows=[{'cnt': 8}])), 'public'), 8)
        self.assertEqual(vad_repo.count_vads(FakeEngine(FakeResult()), 'public'), 0)

    def test_fetch_vad_batch_converts_nullable_fields(self):
        engine = FakeEngine(FakeResult(rows=[vad_row()]))
        rows = vad_repo.fetch_vad_batch(engine, 'public', '3', '4')

        self.assertEqual(rows, [vad_repo.VadRow(41, NOW, '31', None, None, 'fall', 2)])
        self.assertEqual(engine.calls[0][1], {'offset': 3, 'limit': 4})

    def test_fetch_pending_vads_without_since_filter(self):
        engine = FakeEngine(FakeResult(rows=[vad_row(stream_id=9, frame_vad_base64='frame')]))
        rows = vad_repo.fetch_pending_vads(engine, 'tenant', 'vad-analysis', limit=6)

        self.assertEqual(rows[0].stream_id, '9')
        self.assertEqual(rows[0].frame_vad_base64, 'frame')
        sql, params = engine.calls[0]
        self.assertIn('from tenant.vad', sql)
        self.assertNotIn('v.created_at >= :since_ts', sql)
        self.assertEqual(params, {'prompt_type': 'vad-analysis', 'limit': 6})

    def test_fetch_pending_vads_with_since_filter(self):
        engine = FakeEngine(FakeResult())
        vad_repo.fetch_pending_vads(engine, 'public', 'vad-analysis', since_ts=NOW)

        sql, params = engine.calls[0]
        self.assertIn('v.created_at >= :since_ts', sql)
        self.assertEqual(params['since_ts'], NOW)


class StrangerRepoTests(unittest.TestCase):
    def test_blank_id_short_circuits_without_database_access(self):
        engine = FakeEngine()
        self.assertIsNone(stranger_repo.get_stranger_code(engine, 'public', '  '))
        self.assertEqual(engine.calls, [])

    def test_get_stranger_code_handles_value_null_and_missing_rows(self):
        self.assertEqual(
            stranger_repo.get_stranger_code(FakeEngine(FakeResult(rows=[{'code': 123}])), 'public', ' id-1 '),
            '123',
        )
        self.assertIsNone(stranger_repo.get_stranger_code(FakeEngine(FakeResult(rows=[{'code': None}])), 'public', 'id-2'))
        self.assertIsNone(stranger_repo.get_stranger_code(FakeEngine(FakeResult()), 'public', 'id-3'))


class MediaRepoTests(unittest.TestCase):
    def test_undefined_column_detection_supports_sqlstate_and_message(self):
        self.assertTrue(media_repo._is_undefined_column_error(undefined_column_error()))
        message_error = ProgrammingError('select', {}, Exception('column m.play_url does not exist'))
        self.assertTrue(media_repo._is_undefined_column_error(message_error))
        self.assertFalse(media_repo._is_undefined_column_error(ProgrammingError('select', {}, Exception('timeout'))))

    def test_get_media_asset_uses_play_url_schema(self):
        engine = FakeEngine(FakeResult(rows=[media_row(content_type='video/mp4')]))
        row = media_repo.get_media_asset_by_id(engine, 'public', 'asset-1')

        self.assertEqual(row, media_repo.MediaAssetRow('31', '4', 'clip', NOW, 2500, '/media/clip.mp4', 'video/mp4'))
        self.assertIn('m.play_url as path', engine.calls[0][0])
        self.assertEqual(engine.calls[0][1], {'id': 'asset-1'})

    def test_get_media_asset_falls_back_to_legacy_path_column(self):
        engine = FakeEngine(undefined_column_error(), FakeResult(rows=[media_row()]))
        row = media_repo.get_media_asset_by_id(engine, 'public', 'asset-1')

        self.assertEqual(row.path, '/media/clip.mp4')
        self.assertEqual(len(engine.calls), 2)
        self.assertIn('m.path', engine.calls[1][0])

    def test_get_media_asset_reraises_unrelated_programming_error(self):
        error = ProgrammingError('select', {}, Exception('permission denied'))
        with self.assertRaises(ProgrammingError):
            media_repo.get_media_asset_by_id(FakeEngine(error), 'public', 'asset-1')

    def test_get_media_asset_returns_none_when_missing(self):
        self.assertIsNone(media_repo.get_media_asset_by_id(FakeEngine(FakeResult()), 'public', 'missing'))

    def test_select_episode_media_prefers_explicit_links(self):
        engine = FakeEngine(FakeResult(rows=[media_row()]))
        rows = media_repo.select_episode_media(engine, 'public', 'episode-1', 'stream-1', NOW, NOW, limit='3')

        self.assertEqual(len(rows), 1)
        self.assertEqual(engine.connect_count, 1)
        self.assertIn('episode_media_link', engine.calls[0][0])
        self.assertEqual(engine.calls[0][1]['limit'], 3)

    def test_select_episode_media_falls_back_to_overlapping_stream_assets(self):
        engine = FakeEngine(FakeResult(), FakeResult(rows=[media_row(asset_type='segment')]))
        rows = media_repo.select_episode_media(engine, 'public', 'episode-1', 'stream-1', NOW, NOW)

        self.assertEqual(rows[0].asset_type, 'segment')
        self.assertEqual(engine.connect_count, 2)
        self.assertNotIn('episode_media_link', engine.calls[1][0])
        self.assertEqual(engine.calls[1][1]['stream_id'], 'stream-1')

    def test_select_episode_media_does_not_fallback_without_stream(self):
        engine = FakeEngine(FakeResult())
        self.assertEqual(media_repo.select_episode_media(engine, 'public', 'episode-1', None, NOW, NOW), [])
        self.assertEqual(engine.connect_count, 1)

    def test_select_episode_media_supports_legacy_path_in_both_queries(self):
        engine = FakeEngine(
            undefined_column_error(),
            FakeResult(),
            undefined_column_error(),
            FakeResult(rows=[media_row()]),
        )
        rows = media_repo.select_episode_media(engine, 'public', 'episode-1', 'stream-1', NOW, NOW)

        self.assertEqual(rows[0].id, '31')
        self.assertIn('m.path', engine.calls[1][0])
        self.assertIn('m.path', engine.calls[3][0])


class ReportRepoTests(unittest.TestCase):
    def test_report_identity_requires_exactly_one_source(self):
        for kwargs in ({}, {'episode_id': 'e', 'vad_id': 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                report_repo.has_llm_report(FakeEngine(), 'public', prompt_type='p', **kwargs)
            with self.subTest(save_kwargs=kwargs), self.assertRaises(ValueError):
                report_repo.save_llm_report(
                    FakeEngine(), 'public', prompt_type='p', report_json={}, report_text=None, **kwargs
                )

    def test_has_llm_report_selects_episode_or_vad(self):
        episode_engine = FakeEngine(FakeResult(scalar=1))
        vad_engine = FakeEngine(FakeResult(scalar=None))

        self.assertTrue(report_repo.has_llm_report(episode_engine, 'public', prompt_type='p', episode_id='e'))
        self.assertFalse(report_repo.has_llm_report(vad_engine, 'public', prompt_type='p', vad_id=5))
        self.assertIn('episode_id = :episode_id', episode_engine.calls[0][0])
        self.assertEqual(episode_engine.calls[0][1], {'episode_id': 'e', 'prompt_type': 'p'})
        self.assertIn('vad_id = :vad_id', vad_engine.calls[0][0])

    def test_save_llm_report_returns_existing_id_without_insert(self):
        engine = FakeEngine(FakeResult(scalar=99))
        report_id = report_repo.save_llm_report(
            engine,
            'public',
            prompt_type='episode-summary',
            episode_id='e-1',
            report_json={'ok': True},
            report_text='summary',
        )

        self.assertEqual(report_id, '99')
        self.assertEqual(engine.begin_count, 0)

    @patch('llm_report_service.db.report_repo.uuid4', return_value='new-report-id')
    def test_save_llm_report_inserts_json_in_transaction(self, _uuid4):
        engine = FakeEngine(FakeResult(scalar=None), FakeResult())
        report_id = report_repo.save_llm_report(
            engine,
            'tenant',
            prompt_type='vad-analysis',
            vad_id=41,
            report_json={'message': '异常'},
            report_text=None,
        )

        self.assertEqual(report_id, 'new-report-id')
        self.assertEqual(engine.begin_count, 1)
        insert_sql, payload = engine.calls[1]
        self.assertIn('insert into tenant.llm_report', insert_sql)
        self.assertIsNone(payload['episode_id'])
        self.assertEqual(payload['vad_id'], 41)
        self.assertEqual(json.loads(payload['report_json']), {'message': '异常'})
        self.assertIsInstance(payload['created_at'], datetime)
        self.assertIsNotNone(payload['created_at'].tzinfo)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.cfg = DbConfig(
            host='db.internal', port=5433, user='reporter', password='secret', database='monitoring'
        )

    def test_build_pg_uri_uses_configured_or_default_driver(self):
        self.assertEqual(
            session.build_pg_uri(self.cfg),
            'postgresql+pg8000://reporter:secret@db.internal:5433/monitoring',
        )
        blank_driver = DbConfig(**{**self.cfg.__dict__, 'driver': '  '})
        self.assertIn('postgresql+pg8000://', session.build_pg_uri(blank_driver))

    @patch('llm_report_service.db.session.create_engine')
    def test_create_pg_engine_uses_available_preferred_driver(self, create_engine):
        expected = MagicMock()
        create_engine.return_value = expected
        with patch.dict(sys.modules, {'pg8000': SimpleNamespace()}):
            actual = session.create_pg_engine(self.cfg)

        self.assertIs(actual, expected)
        create_engine.assert_called_once_with(session.build_pg_uri(self.cfg), pool_pre_ping=True)

    @patch('llm_report_service.db.session.create_engine')
    def test_create_pg_engine_falls_back_to_an_available_driver(self, create_engine):
        cfg = DbConfig(**{**self.cfg.__dict__, 'driver': 'not-supported'})
        with patch.dict(sys.modules, {'pg8000': None, 'psycopg': SimpleNamespace()}):
            session.create_pg_engine(cfg)

        uri = create_engine.call_args.args[0]
        self.assertTrue(uri.startswith('postgresql+psycopg://'))

    def test_create_pg_engine_exits_when_no_driver_is_available(self):
        cfg = DbConfig(**{**self.cfg.__dict__, 'driver': 'not-supported'})
        with patch.dict(sys.modules, {'pg8000': None, 'psycopg': None, 'psycopg2': None}):
            with self.assertRaisesRegex(SystemExit, 'Missing PostgreSQL driver'):
                session.create_pg_engine(cfg)


if __name__ == '__main__':
    unittest.main()
