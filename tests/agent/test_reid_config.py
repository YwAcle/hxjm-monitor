"""Agent assembly no longer accepts database or algorithm-client configuration."""
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest.mock import MagicMock, patch

from llm_agent_service.app import create_app
from llm_agent_service.config import ServiceConfig
from apps.llm.agent import main


class AgentAssemblyTests(unittest.TestCase):
    def test_image_asset_configuration_is_preserved(self):
        config = ServiceConfig()
        with patch('llm_agent_service.app.CapabilityBridge.from_env'), \
             patch('llm_agent_service.app.SessionImageAssets') as assets, \
             patch('llm_agent_service.app.AgentExecutor') as executor:
            create_app(svc_cfg=config, llm=MagicMock())
        assets.assert_called_once_with(ttl_s=config.image_asset_ttl_s,
            max_per_session=config.image_asset_max_per_session,
            max_bytes_per_session=config.image_asset_max_bytes_per_session,
            max_total_bytes=config.image_asset_max_total_bytes)
        self.assertIs(executor.call_args.kwargs['image_assets'], assets.return_value)

    def test_cli_exposes_local_options_without_business_database_or_reid(self):
        output = StringIO()
        with patch('sys.argv', ['agent', '--help']), redirect_stdout(output):
            with self.assertRaises(SystemExit) as result:
                main()
        self.assertEqual(result.exception.code, 0)
        self.assertIn('--image-asset-ttl-s', output.getvalue())
        self.assertNotIn('--db-host', output.getvalue())
        self.assertNotIn('--reid-feature-base-url', output.getvalue())

    def test_cli_rejects_invalid_image_limits(self):
        with patch('sys.argv', ['agent', '--image-asset-ttl-s', '0']), redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as result:
                main()
        self.assertEqual(result.exception.code, 2)

    def test_model_client_is_closed_if_app_initialization_fails(self):
        with patch('sys.argv', ['agent']), patch('apps.llm.agent.build_llm') as build, \
             patch('apps.llm.agent.create_app', side_effect=ValueError('missing Business configuration')):
            with self.assertRaisesRegex(ValueError, 'missing Business'):
                main()
        build.return_value.close.assert_called_once_with()
