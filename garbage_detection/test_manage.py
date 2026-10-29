import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import manage


class ManageTests(unittest.TestCase):
    def test_stale_or_foreign_pid_is_not_managed(self):
        manage.RUNTIME.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=manage.RUNTIME) as directory:
            pid_file = Path(directory) / "service.json"
            record = {"pid": 123, "start_ticks": "100"}
            pid_file.write_text(json.dumps(record))
            with patch.object(manage, "PID_FILE", pid_file), patch.object(manage, "recover_process", return_value=None):
                with patch.object(manage, "identity", return_value=None):
                    self.assertIsNone(manage.managed_process())
                with patch.object(manage, "identity", return_value={"pid": 123, "start_ticks": "200"}):
                    self.assertIsNone(manage.managed_process())
                with patch.object(manage, "identity", return_value=record):
                    self.assertEqual(manage.managed_process(), record)

    def test_missing_or_stale_record_recovers_verified_service(self):
        with tempfile.TemporaryDirectory(dir=manage.RUNTIME) as directory:
            pid_file = Path(directory) / "service.json"
            record = {"pid": 123, "start_ticks": "200"}
            with patch.object(manage, "PID_FILE", pid_file), \
                    patch.object(manage, "recover_process", return_value=record):
                self.assertEqual(manage.managed_process(), record)
                self.assertEqual(json.loads(pid_file.read_text()), record)
                pid_file.write_text('{"pid":123,"start_ticks":"100"}')
                with patch.object(manage, "identity", return_value=record):
                    self.assertEqual(manage.managed_process(), record)
                self.assertEqual(json.loads(pid_file.read_text()), record)

    def test_recovery_checks_owner_and_process_identity(self):
        own, foreign, unrelated = [Mock(name=name) for name in ("own", "foreign", "unrelated")]
        for proc, pid, uid in [(own, "123", 1000), (foreign, "456", 2000), (unrelated, "789", 1000)]:
            proc.name = pid
            proc.stat.return_value.st_uid = uid
        root = Mock()
        root.iterdir.return_value = [own, foreign, unrelated]
        record = {"pid": 123, "start_ticks": "200"}
        with patch.object(manage, "Path", return_value=root), \
                patch.object(manage.os, "getuid", return_value=1000), \
                patch.object(manage, "identity", side_effect=lambda pid: record if pid == 123 else None) as identity:
            self.assertEqual(manage.recover_process(), record)
            self.assertEqual([call.args[0] for call in identity.call_args_list], [123, 789])

    def test_multiple_verified_services_are_not_adopted(self):
        proc = Mock()
        proc.name = "123"
        proc.stat.return_value.st_uid = 1000
        root = Mock()
        root.iterdir.return_value = [proc, proc]
        with patch.object(manage, "Path", return_value=root), \
                patch.object(manage.os, "getuid", return_value=1000), \
                patch.object(manage, "identity", return_value={"pid": 123, "start_ticks": "200"}):
            with self.assertRaisesRegex(RuntimeError, "多个"):
                manage.recover_process()

    def test_pid_reuse_does_not_signal_replacement_process(self):
        with patch.object(manage.os, "pidfd_open", return_value=42, create=True), \
                patch.object(manage.os, "close") as close, \
                patch.object(manage, "identity", return_value={"pid": 123, "start_ticks": "200"}), \
                patch.object(manage.signal, "pidfd_send_signal", create=True) as send:
            manage.stop_process({"pid": 123, "start_ticks": "100"})
            send.assert_not_called()
            close.assert_called_once_with(42)


if __name__ == "__main__":
    unittest.main()
