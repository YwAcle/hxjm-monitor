"""Opt-in persistence configuration, shared by the launcher and offline checks."""
import json
import math
import os
import re
from pathlib import Path
from urllib.parse import urlsplit
import uuid
from zoneinfo import ZoneInfo


def valid_uuid(value):
    parsed = uuid.UUID(value)
    if str(parsed) != value or parsed.int == 0:
        raise ValueError('Expected a canonical nonzero UUID')
    return value


class PersistenceConfig:
    def __init__(self, env=None, cameras=None):
        env = os.environ if env is None else env
        switch = env.get('VIDEO_RESULTS_PERSIST_ENABLED', 'false').lower()
        if switch not in ('true', 'false'):
            raise ValueError('VIDEO_RESULTS_PERSIST_ENABLED must be true or false')
        self.enabled = switch == 'true'
        self.samples = None
        if not self.enabled:
            samples_switch = env.get('VIDEO_SAMPLES_ENABLED', 'false').lower()
            if samples_switch not in ('true', 'false'):
                raise ValueError('VIDEO_SAMPLES_ENABLED must be true or false')
            if samples_switch == 'true':
                raise ValueError('Video samples require VIDEO_RESULTS_PERSIST_ENABLED=true')
            return
        required = ('BUSINESS_BASE_URL', 'SERVICE_ID', 'SERVICE_TOKEN', 'SPOOL_DIR', 'SOURCE_MAP_FILE',
                    'IMPLEMENTATION_CODE', 'IMPLEMENTATION_VERSION')
        for name in required:
            value = env.get('VIDEO_RESULTS_' + name, '')
            if not value.strip() or 'REPLACE_WITH_' in value or any(ord(c) < 32 for c in value):
                raise ValueError('Missing or invalid VIDEO_RESULTS_' + name)
            setattr(self, name.lower(), value)
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}', self.service_id):
            raise ValueError('Invalid VIDEO_RESULTS_SERVICE_ID')
        if not Path(self.spool_dir).is_absolute():
            raise ValueError('VIDEO_RESULTS_SPOOL_DIR must be absolute')
        try:
            self.sources = json.loads(Path(self.source_map_file).read_text())
        except (OSError, ValueError):
            raise ValueError('Cannot read result source mapping JSON') from None
        if not isinstance(self.sources, dict) or not self.sources:
            raise ValueError('Source mapping must be a nonempty camera object')
        streams = set()
        for camera, item in self.sources.items():
            if not re.fullmatch(r'camera_[1-9][0-9]*', camera):
                raise ValueError('Source mapping camera names must use camera_<positive integer>')
            if not isinstance(item, dict) or set(item) - {'source_id', 'camera_stream_id', 'instance_id', 'timezone'}:
                raise ValueError('Unsupported result source mapping fields')
            for key in ('source_id', 'camera_stream_id', 'instance_id'):
                valid_uuid(item[key])
            if item['camera_stream_id'] in streams:
                raise ValueError('Each analyzed camera must map to a distinct camera stream')
            streams.add(item['camera_stream_id'])
            ZoneInfo(item.get('timezone', 'Asia/Shanghai'))
        if cameras and set(cameras) - set(self.sources):
            raise ValueError('Every analyzed camera needs an explicit result source mapping')
        self.capability_code = env.get('VIDEO_RESULTS_CAPABILITY_CODE', 'tracking')
        for value in (self.capability_code, self.implementation_code, self.implementation_version):
            if not value.strip() or len(value) > 64 or any(ord(c) < 32 for c in value):
                raise ValueError('Invalid capability or implementation identifier')
        try:
            self.parameters = json.loads(env.get('VIDEO_RESULTS_PARAMETERS_JSON', '{}'))
        except ValueError:
            raise ValueError('VIDEO_RESULTS_PARAMETERS_JSON must be a JSON object') from None
        if not isinstance(self.parameters, dict):
            raise ValueError('VIDEO_RESULTS_PARAMETERS_JSON must be a JSON object')
        json.dumps(self.parameters, allow_nan=False)
        self.batch_frames = self._integer(env, 'BATCH_FRAMES', 10, 1, 100)
        self.batch_bytes = self._integer(env, 'BATCH_BYTES', 512 * 1024, 1024, 4 * 1024 ** 2)
        self.max_bytes = self._integer(env, 'SPOOL_MAX_MIB', 512, 16, 1024 * 1024) * 1024 ** 2
        self.flush_seconds = self._seconds(env, 'FLUSH_SECONDS', .5)
        self.timeout = self._seconds(env, 'TIMEOUT_SECONDS', 10)
        self.retry_max = self._seconds(env, 'RETRY_MAX_SECONDS', 60)
        self.samples = self._samples(env)

    @staticmethod
    def _samples(env):
        """Sample extraction is an explicit opt-in on top of reliable persistence."""
        switch = env.get('VIDEO_SAMPLES_ENABLED', 'false').lower()
        if switch not in ('true', 'false'):
            raise ValueError('VIDEO_SAMPLES_ENABLED must be true or false')
        if switch == 'false':
            return None
        text_switch = env.get('VIDEO_SAMPLES_TEXT_ENABLED', 'true').lower()
        if text_switch not in ('true', 'false'):
            raise ValueError('VIDEO_SAMPLES_TEXT_ENABLED must be true or false')
        feature_url = env.get('VIDEO_SAMPLES_FEATURE_URL', '')
        parts = urlsplit(feature_url)
        if (parts.scheme not in ('http', 'https') or not parts.hostname
                or parts.username is not None or parts.password is not None
                or parts.query or parts.fragment or parts.path not in ('', '/')):
            raise ValueError('VIDEO_SAMPLES_FEATURE_URL must be an HTTP(S) origin')
        instance_id = env.get('VIDEO_SAMPLES_INSTANCE_ID', '')
        try:
            valid_uuid(instance_id)
        except (TypeError, ValueError):
            raise ValueError('VIDEO_SAMPLES_INSTANCE_ID must be a canonical nonzero UUID') from None
        capability_code = env.get('VIDEO_SAMPLES_CAPABILITY_CODE', 'person.reidentification')
        if (not capability_code.strip() or len(capability_code) > 64
                or any(ord(c) < 32 for c in capability_code)):
            raise ValueError('Invalid VIDEO_SAMPLES_CAPABILITY_CODE')
        threshold = float(env.get('VIDEO_SAMPLES_THRESHOLD', '0.88'))
        if not math.isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError('VIDEO_SAMPLES_THRESHOLD must be between 0 and 1')
        queue_size = int(env.get('VIDEO_SAMPLES_QUEUE_SIZE', '16'))
        if queue_size <= 0:
            raise ValueError('VIDEO_SAMPLES_QUEUE_SIZE must be positive')
        poll_seconds = float(env.get('VIDEO_SAMPLES_POLL_SECONDS', '5'))
        if not math.isfinite(poll_seconds) or poll_seconds <= 0:
            raise ValueError('VIDEO_SAMPLES_POLL_SECONDS must be finite and positive')
        return dict(feature_url=feature_url, instance_id=instance_id,
                    capability_code=capability_code, threshold=threshold, queue_size=queue_size,
                    text_enabled=text_switch == 'true', poll_interval_seconds=poll_seconds)

    @staticmethod
    def _integer(env, key, default, minimum, maximum):
        value = int(env.get('VIDEO_RESULTS_' + key, default))
        if not minimum <= value <= maximum:
            raise ValueError('Invalid VIDEO_RESULTS_' + key)
        return value

    @staticmethod
    def _seconds(env, key, default):
        value = float(env.get('VIDEO_RESULTS_' + key, default))
        if not math.isfinite(value) or value <= 0:
            raise ValueError('Invalid VIDEO_RESULTS_' + key)
        return value
