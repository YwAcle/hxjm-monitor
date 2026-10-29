"""Register durable recording manifests on a worker independent of recording."""
from copy import deepcopy
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import threading

from .business_client import BusinessRequestError
from .business_runtime import _uuid


logger = logging.getLogger(__name__)

_ASSET_FIELDS = (
    'request_id', 'trace_id', 'asset_id', 'producer_key', 'asset_type', 'source_id',
    'stream_session_id', 'storage_key', 'state', 'start_at', 'end_at', 'content_type',
    'byte_size', 'checksum_sha256', 'write_attempt_id', 'expected_revision',
    'frame_locations', 'recording_alignment', 'expires_at',
)


class RecordingDelivery:
    """Replay recorder-owned manifests; the recording callback only wakes a worker.

    The same BusinessRuntime is shared with analysis so both consumers open one
    immutable input session. A matching ACK sidecar skips already registered
    manifests without re-reading or hashing their MP4 contents.
    """

    def __init__(self, client, runtime, *, storage_root, source_ids, retry_interval=1.0):
        self.storage_root = Path(storage_root)
        if not self.storage_root.is_absolute():
            raise ValueError('Recording storage root must be an absolute path')
        self.source_ids = frozenset(_uuid(source) for source in source_ids)
        if not self.source_ids:
            raise ValueError('Recording delivery requires explicit source IDs')
        if (isinstance(retry_interval, bool) or not isinstance(retry_interval, (int, float))
                or not math.isfinite(retry_interval) or retry_interval <= 0):
            raise ValueError('Recording retry interval must be positive')
        self.client, self.runtime = client, runtime
        self.retry_interval = retry_interval
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._state = 'idle'
        self._error = None
        self._pending = 0
        self._confirmed = 0
        self._blocked = {}

    def start(self):
        with self._lock:
            if self._thread is not None or self._stop.is_set():
                raise RuntimeError('Create a new recording delivery for another lifecycle')
            self._state = 'running'
            self._thread = threading.Thread(target=self._run, name='recording-delivery', daemon=False)
            self._thread.start()

    def __call__(self, manifest):
        """No file, database or network work runs on the recording callback."""
        self._wake.set()

    def stop(self, timeout=5):
        """Call after recording has sealed its final segment; unconfirmed files stay."""
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        return thread is None or not thread.is_alive()

    def status(self):
        with self._lock:
            return {'state': self._state, 'last_error': self._error,
                    'pending_manifests': self._pending, 'confirmed_manifests': self._confirmed,
                    'blocked_manifests': len(self._blocked),
                    'thread_alive': self._thread is not None and self._thread.is_alive()}

    def _failure(self, error):
        with self._lock:
            self._state = 'retrying'
            self._error = type(error).__name__ + ': ' + str(error)
        logger.error('Recording registration failed: %s', error)

    def _load(self, path):
        manifest = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(manifest, dict):
            raise ValueError('Recording manifest must be an object')
        digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':'),
                                           allow_nan=False).encode('utf-8')).hexdigest()
        return manifest, digest

    def _validate(self, path, manifest):
        source = _uuid(manifest.get('source_id'))
        session = _uuid(manifest.get('stream_session_id'))
        asset = _uuid(manifest.get('asset_id'))
        if source not in self.source_ids:
            raise ValueError('Recording source is not configured')
        expected_key = f'recordings/{source}/{session}/{asset}.mp4'
        if (manifest.get('storage_key') != expected_key
                or path != self.storage_root / (expected_key + '.manifest.json')
                or not path.resolve().is_relative_to(self.storage_root.resolve())):
            raise ValueError('Recording manifest does not match its storage location')
        if manifest.get('asset_type') != 'recording' or manifest.get('state') != 'available':
            raise ValueError('Only sealed, available recordings can be delivered')
        metadata = manifest.get('stream_session')
        if not isinstance(metadata, dict) or metadata.get('stream_session_id') != session:
            raise ValueError('Recording manifest requires its original input session metadata')
        if not isinstance(manifest.get('recording_alignment'), dict):
            raise ValueError('Recording manifest requires precise media alignment')
        return source, metadata

    @staticmethod
    def _ack_matches(path, digest):
        try:
            ack = json.loads(path.read_text(encoding='utf-8'))
        except (FileNotFoundError, ValueError, UnicodeError):
            return False
        return isinstance(ack, dict) and ack.get('manifest_sha256') == digest

    @staticmethod
    def _acknowledge(path, digest, response):
        temporary = path.with_suffix(path.suffix + '.tmp')
        ack = {'manifest_sha256': digest, 'asset_id': response['asset_id'],
               'producer_key': response['producer_key'], 'revision': response.get('revision')}
        with temporary.open('w', encoding='utf-8') as handle:
            json.dump(ack, handle, sort_keys=True, separators=(',', ':'))
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)

    def _scan(self):
        pending = 0
        seen = set()
        for source in sorted(self.source_ids):
            for path in sorted((self.storage_root / 'recordings' / source).rglob('*.mp4.manifest.json')):
                seen.add(path)
                pending += 1
                digest = None
                try:
                    manifest, digest = self._load(path)
                    source_id, metadata = self._validate(path, manifest)
                    ack = path.with_suffix(path.suffix + '.ack')
                    if self._ack_matches(ack, digest):
                        self._blocked.pop(path, None)
                        pending -= 1
                        continue
                    if digest == self._blocked.get(path):
                        continue
                    self.runtime.open_input(source_id, deepcopy(metadata))
                    payload = {field: manifest[field] for field in _ASSET_FIELDS if field in manifest}
                    response = self.client.register_asset(payload)
                    if (not isinstance(response, dict) or response.get('asset_id') != manifest['asset_id']
                            or response.get('producer_key') != manifest.get('producer_key')
                            or response.get('state') != 'available'):
                        raise BusinessRequestError('ASSET_RESPONSE_MISMATCH')
                    self._acknowledge(ack, digest, response)
                    self._blocked.pop(path, None)
                    pending -= 1
                    with self._lock:
                        self._confirmed += 1
                except (ValueError, KeyError, TypeError) as error:
                    self._blocked[path] = digest
                    self._failure(error)
                except Exception as error:
                    self._failure(error)
        with self._lock:
            self._blocked = {path: digest for path, digest in self._blocked.items() if path in seen}
            self._pending = pending
            if pending == 0:
                self._state, self._error = 'running', None

    def _run(self):
        try:
            while not self._stop.is_set():
                self._wake.clear()
                try:
                    self._scan()
                except Exception as error:
                    self._failure(error)
                self._wake.wait(self.retry_interval)
            try:
                self._scan()
            except Exception as error:
                self._failure(error)
        finally:
            with self._lock:
                self._state = 'stopped'
