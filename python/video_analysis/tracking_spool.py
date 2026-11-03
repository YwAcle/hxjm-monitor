"""Bounded, exclusively owned JSON journal on a persistent local filesystem."""
import fcntl
import json
import os
from pathlib import Path
import threading
import time
import uuid
from collections import defaultdict, deque


def canonical_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


class SpoolFull(OSError):
    pass


class ResultSpool:
    def __init__(self, root, max_bytes=512 * 1024 ** 2, reserve_bytes=4 * 1024 ** 2):
        self.root = Path(root)
        if self.root.is_symlink():
            raise ValueError('Spool directory must not be a symlink')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._lockfile = (self.root / 'owner.lock').open('a+b')
        try:
            fcntl.flock(self._lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._lockfile.close()
            raise RuntimeError('Another result publisher owns this spool') from None
        self.mutex = threading.RLock()
        self.max_bytes, self.reserve_bytes = max_bytes, reserve_bytes
        self.jobs = self.root / 'pending'
        self.states = self.root / 'state'
        for directory in (self.jobs, self.states):
            directory.mkdir(exist_ok=True, mode=0o700)
        self.sequence = time.time_ns()
        # An unpublished temporary file is never a confirmed enqueue. Keep it as evidence.
        self.recovery_temporaries = sum(len(list(d.glob('*.tmp'))) for d in (self.jobs, self.states))
        self._sizes = {p: p.stat().st_size for d in (self.jobs, self.states) for p in d.iterdir() if p.is_file()}
        self._bytes = sum(self._sizes.values())
        self._lanes = defaultdict(deque)
        for path in sorted(self.jobs.glob('*.json')):
            self._lanes[json.loads(path.read_text())['lane']].append(path)
        self._sync_directory(self.root)

    @staticmethod
    def _sync_directory(directory):
        descriptor = os.open(str(directory), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _write(self, path, value, control=False):
        encoded = canonical_bytes(value)
        old = self._sizes.get(path, 0)
        limit = self.max_bytes if control else self.max_bytes - self.reserve_bytes
        if self.size() - old + len(encoded) > limit:
            raise SpoolFull('Result spool capacity exhausted')
        temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            with os.fdopen(os.open(str(temporary), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'wb') as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            self._bytes += len(encoded) - old
            self._sizes[path] = len(encoded)
            self._sync_directory(path.parent)
        finally:
            temporary.unlink(missing_ok=True)

    def size(self):
        return self._bytes

    def can_accept(self):
        with self.mutex:
            # Leave room for an entire maximum-sized result and its frozen request.
            return self.size() < self.max_bytes - self.reserve_bytes - 2 * 1024 ** 2

    def save_state(self, key, value):
        with self.mutex:
            self._write(self.states / (str(uuid.UUID(key)) + '.json'), value, control=True)

    def load_state(self, key):
        with self.mutex:
            return json.loads((self.states / (str(uuid.UUID(key)) + '.json')).read_text())

    def merge_state(self, key, changes):
        with self.mutex:
            value = self.load_state(key)
            value.update(changes)
            self.save_state(key, value)
            return value

    def all_states(self):
        with self.mutex:
            return [json.loads(p.read_text()) for p in sorted(self.states.glob('*.json'))]

    def enqueue(self, lane, kind, payload, key=None):
        with self.mutex:
            explicit = key is not None
            key = str(uuid.UUID(key)) if explicit else str(uuid.uuid4())
            existing = [p for p in self._lanes[lane] if p.name.endswith('-' + key + '.json')] if explicit else []
            if existing:
                return existing[0]
            self.sequence = max(self.sequence + 1, time.time_ns())
            path = self.jobs / ('%020d-%s.json' % (self.sequence, key))
            self._write(path, {'lane': lane, 'kind': kind, 'payload': payload,
                               'queued_at': time.time()}, control=kind != 'frame')
            self._lanes[lane].append(path)
            return path

    def entries(self):
        with self.mutex:
            return [(p, json.loads(p.read_text())) for p in sorted(self.jobs.glob('*.json'))]

    def lane_entries(self, lane, limit=100):
        with self.mutex:
            from itertools import islice
            return [(p, json.loads(p.read_text())) for p in islice(self._lanes[lane], limit)]

    def snapshot(self):
        with self.mutex:
            heads = [json.loads(lane[0].read_text()) for lane in self._lanes.values() if lane]
            oldest = min((h['queued_at'] for h in heads), default=time.time())
            return dict(pending_jobs=sum(len(lane) for lane in self._lanes.values()), pending_bytes=self.size(),
                        oldest_pending_seconds=max(0, time.time() - oldest))

    def update(self, path, value):
        with self.mutex:
            self._write(path, value, control=True)

    def remove(self, path):
        with self.mutex:
            if path in self._sizes:
                lane = json.loads(path.read_text())['lane']
                self._lanes[lane].remove(path)
            path.unlink(missing_ok=True)
            self._bytes -= self._sizes.pop(path, 0)
            self._sync_directory(self.jobs)

    def delete_state(self, key):
        with self.mutex:
            path = self.states / (str(uuid.UUID(key)) + '.json')
            path.unlink(missing_ok=True)
            self._bytes -= self._sizes.pop(path, 0)
            self._sync_directory(self.states)

    def close(self):
        self._lockfile.close()
