"""Write private shared files with explicit numeric POSIX ACL identities."""
import os
from pathlib import Path
import struct
import tempfile


def write_text(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    uids = sorted({int(value) for value in os.getenv('HXJM_SHARED_UIDS', '').split(',') if value})
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            if uids:
                entries = [(1, 6, 0xffffffff)]
                entries += [(2, 6, uid) for uid in uids]
                entries += [(4, 0, 0xffffffff), (16, 6, 0xffffffff), (32, 0, 0xffffffff)]
                acl = struct.pack('<I', 2) + b''.join(struct.pack('<HHI', *entry) for entry in entries)
                os.setxattr(stream.fileno(), 'system.posix_acl_access', acl)
            else:
                # Keep inherited named-user ACLs writable; chmod(0600) masks them.
                os.fchmod(stream.fileno(), 0o660)
            stream.write(content)
            stream.flush()
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
