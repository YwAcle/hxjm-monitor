"""Host-local configuration. No model or cache path points at the old worktree."""
import json
import math
import os
from pathlib import Path
import uuid


def load(path=None):
    path = Path(path or os.environ['JOYAI_CONFIG']).resolve()
    config = json.loads(path.read_text())
    for name in ('token', 'business_url', 'observer_url', 'review_url', 'review_model', 'instance_id', 'storage_root'):
        if not isinstance(config.get(name), str) or not config[name].strip():
            raise ValueError('Missing JoyAI setting: ' + name)
    uuid.UUID(config['instance_id'])
    if not Path(config['storage_root']).is_absolute():
        raise ValueError('JoyAI storage_root must be absolute')
    if not isinstance(config.get('cameras'), dict) or set(config['cameras']) != {f'camera_{i}' for i in range(1, 5)}:
        raise ValueError('Configure exactly the four camera sources explicitly')
    for name, camera in config['cameras'].items():
        for key in ('source_id', 'camera_stream_id'):
            uuid.UUID(camera[key])
        if not camera['rtsp_url'].startswith('rtsp://127.0.0.1:'):
            raise ValueError('JoyAI reads this project\'s local media distributor')
    for name, default in [('clip_seconds', 10), ('pre_seconds', 5), ('sample_fps', 4),
                          ('observe_interval', 1), ('cooldown_seconds', 30), ('review_start_timeout', 1200)]:
        value = config.setdefault(name, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError('Invalid JoyAI setting: ' + name)
    if config['pre_seconds'] >= config['clip_seconds'] or config['clip_seconds'] > 30 or config['sample_fps'] > 10:
        raise ValueError('JoyAI clip window must be bounded and include post-trigger frames')
    config['state_dir'] = str(path.parent)
    return config
