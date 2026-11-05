"""Create private config and scoped backend grants for this clone only."""
import argparse
import json
import os
from pathlib import Path
import secrets
import uuid
from urllib.request import urlopen
import yaml
from shared_files import write_text
from .contracts import OPERATIONS


def prepare(root):
    path = Path(os.getenv('JOYAI_CONFIG', str(root / '.run/joyai/config.json'))).resolve()
    state = path.parent
    state.mkdir(parents=True, exist_ok=True)
    if path.exists():
        config = json.loads(path.read_text())
    else:
        with urlopen(f"http://127.0.0.1:{os.environ['BACKEND_PORT']}/api/v1/business/sources", timeout=10) as response:
            sources = json.load(response)['items']
        cameras = {}
        for source in sources:
            name = source['camera_code']
            if name not in {f'camera_{i}' for i in range(1, 5)}:
                continue
            streams = [stream for stream in source['streams']
                       if stream['task_type'] == 'raw' and stream['is_active']]
            if len(streams) != 1:
                raise ValueError(f'{name} requires exactly one active raw stream')
            raw = streams[0]
            label = name.replace('camera_', '') + '号摄像头'
            cameras[name] = {'source_id': source['source_id'], 'camera_stream_id': raw['stream_id'],
                             'name': label, 'location': label,
                             'rtsp_url': f"rtsp://127.0.0.1:{os.environ['RTSP_PORT']}/live/{name}"}
        config = {'token': secrets.token_urlsafe(32), 'instance_id': str(uuid.uuid4()),
                  'business_url': f"http://127.0.0.1:{os.environ['BACKEND_PORT']}/api/v1/business",
                  'model_url': f"http://127.0.0.1:{os.environ['JOYAI_MODEL_PORT']}/v1",
                  'observer_url': f"http://127.0.0.1:{os.environ['JOYAI_OBSERVER_PORT']}/v1",
                  'review_url': f"http://127.0.0.1:{os.environ['JOYAI_REVIEW_PORT']}/v1",
                  'tool_url': f"http://127.0.0.1:{os.environ['JOYAI_TOOL_PORT']}",
                  'review_model': 'Qwen/Qwen3.8-27B-AWQ-INT4',
                  'storage_root': os.environ['DATA_ROOT'], 'cameras': cameras}
        if len(cameras) != 4:
            raise ValueError('Four public camera/stream mappings are required')
        write_text(path, json.dumps(config, ensure_ascii=False, indent=2) + '\n')
    grant = {'token': config['token'], 'operations': OPERATIONS,
             'source-ids': [camera['source_id'] for camera in config['cameras'].values()]}
    profile = Path(os.environ['RUNTIME_ROOT']) / 'config/joyai-backend.yml'
    profile.parent.mkdir(parents=True, exist_ok=True)
    write_text(profile, yaml.safe_dump({'hxjm': {'business': {'behavior': {'url': os.environ['JOYAI_BACKEND_TOOL_URL'], 'token': config['token']},
        'security': {'services': {'joyai-producer': grant}}}}}, allow_unicode=True))
    print('JoyAI private config and four-source backend grant prepared; credentials were not printed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    prepare(parser.parse_args().root.resolve())
