"""CLIP-ReID 单后端的默认组装与命令行配置回归。"""

import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest.mock import MagicMock, patch

from llm_agent_service.app import create_app
from llm_agent_service.config import DbConfig, ServiceConfig
from llm_agent_service.main import main


class ReIDConfigTests(unittest.TestCase):
    def test_default_app_always_builds_clipreid_and_text_clients(self):
        config = ServiceConfig()
        with patch("llm_agent_service.app.ReidService"), \
             patch("llm_agent_service.app.ClipReIDClient") as client, \
             patch("llm_agent_service.app.TextReIDClient") as text_client, \
             patch("llm_agent_service.app.GallerySearchService") as gallery:
            create_app(engine=MagicMock(), db_cfg=DbConfig("localhost", 5432, "u", "p", "db"),
                       svc_cfg=config, llm=MagicMock())
        client.assert_called_once_with(config.reid_feature_base_url, config.reid_timeout_s,
                                       config.reid_feature_space_id)
        text_client.assert_called_once_with(
            config.reid_feature_base_url, config.reid_timeout_s,
            config.reid_text_feature_space_id, config.reid_text_contract_id,
            config.reid_text_max_chars,
        )
        self.assertIs(gallery.call_args.kwargs["feature_client"], client.return_value)
        self.assertIs(gallery.call_args.kwargs["text_feature_client"], text_client.return_value)
        self.assertEqual(gallery.call_args.kwargs["text_max_chars"], config.reid_text_max_chars)
        self.assertNotIn("llm", gallery.call_args.kwargs)
        self.assertNotIn("local_encoder", gallery.call_args.kwargs)

    def test_app_builds_image_asset_store_from_config(self):
        config = ServiceConfig()
        with patch("llm_agent_service.app.ReidService"), \
             patch("llm_agent_service.app.SessionImageAssets") as assets, \
             patch("llm_agent_service.app.AgentExecutor") as executor:
            create_app(engine=MagicMock(), db_cfg=DbConfig("localhost", 5432, "u", "p", "db"),
                       svc_cfg=config, llm=MagicMock())
        assets.assert_called_once_with(
            ttl_s=config.image_asset_ttl_s,
            max_per_session=config.image_asset_max_per_session,
            max_bytes_per_session=config.image_asset_max_bytes_per_session,
            max_total_bytes=config.image_asset_max_total_bytes,
        )
        self.assertIs(executor.call_args.kwargs["image_assets"], assets.return_value)

    def test_cli_exposes_image_asset_options_and_rejects_zero(self):
        output = StringIO()
        with patch("sys.argv", ["agent", "--help"]), redirect_stdout(output):
            with self.assertRaises(SystemExit) as exit_result:
                main()
        self.assertEqual(exit_result.exception.code, 0)
        for option in ("--image-asset-ttl-s", "--image-asset-max-per-session",
                       "--image-asset-max-bytes-per-session", "--image-asset-max-total-bytes"):
            self.assertIn(option, output.getvalue())
            with self.subTest(option=option), patch("sys.argv", ["agent", option, "0"]), \
                 redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as exit_result:
                    main()
                self.assertEqual(exit_result.exception.code, 2)

    def test_cli_passes_image_asset_config(self):
        with patch("sys.argv", ["agent", "--image-asset-ttl-s", "600",
                                "--image-asset-max-per-session", "2",
                                "--image-asset-max-bytes-per-session", "1048576",
                                "--image-asset-max-total-bytes", "4194304"]), \
             patch("llm_agent_service.main.create_pg_engine"), \
             patch("llm_agent_service.main.build_llm"), \
             patch("llm_agent_service.main.create_app") as create:
            main()
        config = create.call_args.kwargs["svc_cfg"]
        self.assertEqual(config.image_asset_ttl_s, 600)
        self.assertEqual(config.image_asset_max_per_session, 2)
        self.assertEqual(config.image_asset_max_bytes_per_session, 1048576)
        self.assertEqual(config.image_asset_max_total_bytes, 4194304)

    def test_cli_exposes_clipreid_and_text_options(self):
        output = StringIO()
        with patch("sys.argv", ["agent", "--help"]), redirect_stdout(output):
            with self.assertRaises(SystemExit) as exit_result:
                main()
        self.assertEqual(exit_result.exception.code, 0)
        help_text = output.getvalue()
        for option in ("--reid-feature-base-url", "--reid-timeout-s", "--reid-feature-space-id",
                       "--reid-text-feature-space-id", "--reid-text-contract-id",
                       "--reid-text-max-chars"):
            self.assertIn(option, help_text)
        for option in ("--reid-backend", "--reid-model-path", "--reid-embedding-url", "--reid-embedding-model"):
            self.assertNotIn(option, help_text)

    def test_cli_passes_clipreid_config_and_ignores_obsolete_backend_env(self):
        with patch("sys.argv", ["agent", "--reid-feature-base-url", "http://reid.test:28024",
                                "--reid-feature-space-id", "pinned-space", "--reid-timeout-s", "25",
                                "--reid-text-feature-space-id", "text-space",
                                "--reid-text-contract-id", "text-v1",
                                "--reid-text-max-chars", "80"]), \
             patch.dict("os.environ", {"REID_BACKEND": "local", "REID_MODEL_PATH": "/unused"}), \
             patch("llm_agent_service.main.create_pg_engine"), \
             patch("llm_agent_service.main.build_llm"), \
             patch("llm_agent_service.main.create_app") as create:
            main()
        config = create.call_args.kwargs["svc_cfg"]
        self.assertEqual(config.reid_feature_base_url, "http://reid.test:28024")
        self.assertEqual(config.reid_feature_space_id, "pinned-space")
        self.assertEqual(config.reid_timeout_s, 25)
        self.assertEqual(config.reid_text_feature_space_id, "text-space")
        self.assertEqual(config.reid_text_contract_id, "text-v1")
        self.assertEqual(config.reid_text_max_chars, 80)
        self.assertFalse(hasattr(config, "reid_backend"))
        self.assertFalse(hasattr(config, "reid_model_path"))
        create.return_value.run.assert_called_once()

    def test_obsolete_flags_are_rejected_before_loading_services(self):
        for flag in ("--reid-backend", "--reid-model-path", "--reid-embedding-url", "--reid-embedding-model"):
            with self.subTest(flag=flag), patch("sys.argv", ["agent", flag, "unused"]), \
                 redirect_stderr(StringIO()), \
                 patch("llm_agent_service.main.create_pg_engine") as engine:
                with self.assertRaises(SystemExit) as exit_result:
                    main()
                self.assertEqual(exit_result.exception.code, 2)
                engine.assert_not_called()

    def test_nonpositive_timeout_is_rejected(self):
        with patch("sys.argv", ["agent", "--reid-timeout-s", "0"]), redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as exit_result:
                main()
        self.assertEqual(exit_result.exception.code, 2)

    def test_nonpositive_text_max_chars_is_rejected(self):
        with patch("sys.argv", ["agent", "--reid-text-max-chars", "0"]), redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as exit_result:
                main()
        self.assertEqual(exit_result.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
