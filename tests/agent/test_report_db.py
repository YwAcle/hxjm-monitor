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
    def test_report_uses_public_registration_and_runtime_outputs(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            client = MagicMock()
            client.post.side_effect = [
                {'task_id': 'task', 'revision': 1},
                {'task_id': 'task', 'run_id': 'run', 'revision': 2},
                {'report_id': 'report'}, {'state': 'succeeded'}]
            publisher = report_repo.ReportPublisher(client, directory, 'local-model')
            report_id = publisher.publish('activity', 'subject', {'summary': '真实模型结果'}, '正文', ['evidence'])
            calls = client.post.call_args_list
            self.assertEqual([c.args[0] for c in calls], ['/tasks', '/tasks/start', '/reports/register', '/tasks/end'])
            report = calls[2].args[1]
            self.assertEqual(report['subject_kind'], 'activity')
            self.assertEqual(report['subject_id'], 'subject')
            self.assertEqual(report['model_version'], 'local-model')
            self.assertEqual(report['evidence_ids'], ['evidence'])
            self.assertNotIn('expires_at', report)  # Business derives it from the subject.
            self.assertEqual(calls[3].args[1]['state'], 'succeeded')
            self.assertEqual(calls[3].args[1]['outputs'][0]['payload']['report_id'], report_id)
            publisher.publish('activity', 'subject', None, None, [])
            self.assertEqual(client.post.call_count, 4)

    def test_lost_completion_acknowledgement_retries_identical_request(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            client = MagicMock()
            client.post.side_effect = [
                {'task_id': 'task', 'revision': 1},
                {'task_id': 'task', 'run_id': 'run', 'revision': 2},
                {}, TimeoutError('lost acknowledgement')]
            publisher = report_repo.ReportPublisher(client, directory, 'original-model')
            with self.assertRaises(TimeoutError):
                publisher.publish('event', 'subject', {'summary': '原结果'}, '正文', [])
            sent = client.post.call_args.args[1]
            self.assertFalse(publisher.load('event', 'subject').get('done', False))
            client.post.side_effect = None
            client.post.return_value = {'state': 'succeeded'}
            restarted = report_repo.ReportPublisher(client, directory, 'different-model')
            restarted.publish('event', 'subject', None, None, [])
            self.assertEqual(client.post.call_args.args[1], sent)
            self.assertEqual(client.post.call_count, 5)


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
