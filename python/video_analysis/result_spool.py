"""Immutable result batches awaiting explicit business-service confirmation."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading


class SpoolConflict(ValueError):
    """One request key was reused with a different payload."""


_DIRECTORY_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def _encode(value):
    # Local integrity encoding only; this is not the business API's JCS digest.
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def _sync_directory(directory):
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _request_key(actor_key, operation, request_id):
    return hashlib.sha256(_encode([actor_key, operation, request_id])).hexdigest()


def _result_ids(payload):
    if not isinstance(payload, dict):
        raise ValueError('Payload must be a JSON object')
    request_id = payload.get('request_id')
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
        raise ValueError('request_id must contain 1 to 128 characters')
    results = payload.get('results')
    if not isinstance(results, list) or not results:
        raise ValueError('results must be a nonempty array')
    identifiers = []
    for result in results:
        identifier = result.get('result_id') if isinstance(result, dict) else None
        if not isinstance(identifier, str) or not identifier:
            raise ValueError('Each result must have a nonempty result_id')
        identifiers.append(identifier)
    if len(set(identifiers)) != len(identifiers):
        raise ValueError('result_id must be unique within a batch')
    return set(identifiers)


class ResultSpool:
    """Single-process queue; callers supply its persistent directory.

    shortcut: processes must not share a directory; add cross-process ownership
    before deploying multiple writers against the same spool.
    """

    def __init__(self, directory):
        if not isinstance(directory, (str, os.PathLike)) or not str(directory).strip():
            raise ValueError('Spool path must be a nonempty directory path')
        if '\x00' in os.fspath(directory):
            raise ValueError('Spool path cannot contain NUL')
        # Resolving symlinks or probing an NFS path can block application startup.
        self.directory = Path(os.path.abspath(directory))
        with _LOCKS_GUARD:
            self._lock = _DIRECTORY_LOCKS.setdefault(self.directory, threading.RLock())

    def _prepare(self):
        missing = []
        current = self.directory
        while not current.exists():
            missing.append(current)
            current = current.parent
        for child in reversed(missing):
            child.mkdir(exist_ok=True)
            _sync_directory(child.parent)
        if not self.directory.is_dir():
            raise NotADirectoryError('Spool path is not an available directory')

    def _path(self, key):
        if not isinstance(key, str) or re.fullmatch(r'[0-9a-f]{64}', key) is None:
            raise ValueError('Invalid spool key')
        return self.directory / (key + '.json')

    def _read(self, key):
        record = json.loads(self._path(key).read_bytes())
        if not isinstance(record, dict) or record.get('format_version') != 1:
            raise ValueError('Unsupported or damaged spool record')
        body = {field: record[field] for field in ('actor_key', 'operation', 'payload')}
        if hashlib.sha256(_encode(body)).hexdigest() != record.get('sha256'):
            raise ValueError('Spool record integrity check failed')
        _result_ids(body['payload'])
        if _request_key(body['actor_key'], body['operation'],
                        body['payload']['request_id']) != key:
            raise ValueError('Spool record request key does not match its filename')
        return body

    def put(self, actor_key, operation, payload):
        """Durably store a batch; identical retries reuse its original key."""
        if not isinstance(actor_key, str) or not actor_key:
            raise ValueError('actor_key must be a nonempty string')
        if not isinstance(operation, str) or not operation:
            raise ValueError('operation must be a nonempty string')
        _result_ids(payload)
        body = {'actor_key': actor_key, 'operation': operation, 'payload': payload}
        encoded_body = _encode(body)
        body = json.loads(encoded_body)
        _result_ids(body['payload'])
        key = _request_key(actor_key, operation, body['payload']['request_id'])
        record = dict(body, format_version=1,
                      sha256=hashlib.sha256(encoded_body).hexdigest())
        content = _encode(record)
        with self._lock:
            self._prepare()
            target = self._path(key)
            if target.exists():
                if _encode(self._read(key)) != encoded_body:
                    raise SpoolConflict('Request key already has a different payload')
                _sync_directory(self.directory)
                return key
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=self.directory, prefix='.pending-',
                                                 suffix='.tmp', delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
                _sync_directory(self.directory)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        return key

    def pending(self):
        """Return registered keys; incomplete temporary files are not batches."""
        with self._lock:
            self._prepare()
            # Path.glob can silently hide directory read failures as an empty queue.
            return sorted(name[:-5] for name in os.listdir(self.directory) if name.endswith('.json'))

    def read(self, key):
        """Read a verified, independent copy of actor, operation and payload."""
        with self._lock:
            return self._read(key)

    def acknowledge(self, key, response):
        """Delete only after every original result is explicitly confirmed.

        Pass the results.register response data object. Partial confirmation
        returns False without rewriting the request or changing its request_id.
        """
        with self._lock:
            expected = _result_ids(self._read(key)['payload'])
            if not isinstance(response, dict):
                raise ValueError('Confirmation must be a response object')
            accepted = response.get('accepted_result_ids')
            duplicate = response.get('duplicate_result_ids')
            rejected = response.get('rejected_results')
            if any(not isinstance(value, list) for value in (accepted, duplicate, rejected)):
                raise ValueError('Confirmation must include all three result arrays')
            confirmed = accepted + duplicate
            rejected_ids = [item.get('result_id') if isinstance(item, dict) else None
                            for item in rejected]
            all_ids = confirmed + rejected_ids
            if (any(not isinstance(identifier, str) for identifier in all_ids)
                    or len(set(all_ids)) != len(all_ids)
                    or not set(all_ids).issubset(expected)):
                raise ValueError('Confirmation contains unknown, invalid or repeated result IDs')
            if rejected or set(confirmed) != expected:
                return False
            self._path(key).unlink()
            _sync_directory(self.directory)
            return True

    def replace_unconfirmed(self, key, response):
        """Persist a new logical request before removing a partially confirmed one.

        Original result identities and the complete analysis manifest remain
        unchanged. A repeat after interruption reuses the same replacement key.
        """
        with self._lock:
            record = self._read(key)
            if self.acknowledge(key, response):
                return None
            if any(item.get('retryable') is not True for item in response['rejected_results']):
                raise ValueError('Unconfirmed result was rejected without retry permission')
            confirmed = set(response['accepted_result_ids'] + response['duplicate_result_ids'])
            payload = record['payload']
            payload['results'] = [result for result in payload['results']
                                  if result['result_id'] not in confirmed]
            identity = _encode([key, [result['result_id'] for result in payload['results']]])
            payload['request_id'] = 'retry:' + hashlib.sha256(identity).hexdigest()
            replacement = self.put(record['actor_key'], record['operation'], payload)
            self._path(key).unlink()
            _sync_directory(self.directory)
            return replacement
