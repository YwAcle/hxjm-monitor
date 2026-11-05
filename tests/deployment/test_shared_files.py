import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from shared_files import write_text


class SharedFilesTest(unittest.TestCase):
    def test_acl_failure_does_not_truncate_existing_configuration(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, HXJM_SHARED_UIDS='1006,1021'):
            path = Path(directory) / 'private.json'
            path.write_text('original')
            with patch('shared_files.os.setxattr', side_effect=PermissionError('ACL denied')):
                with self.assertRaises(PermissionError):
                    write_text(path, 'replacement')
            self.assertEqual(path.read_text(), 'original')

    def test_named_users_keep_read_write_after_rewrite(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, HXJM_SHARED_UIDS='1006,1021'):
            path = Path(directory) / 'private.json'
            write_text(path, 'first')
            write_text(path, 'second')
            acl = os.getxattr(path, 'system.posix_acl_access')
            entries = [struct.unpack('<HHI', acl[i:i+8]) for i in range(4, len(acl), 8)]
            self.assertIn((2, 6, 1006), entries)
            self.assertIn((2, 6, 1021), entries)
            self.assertIn((16, 6, 0xffffffff), entries)
            self.assertEqual(path.stat().st_mode & 7, 0)
            self.assertEqual(path.read_text(), 'second')


if __name__ == '__main__':
    unittest.main()
