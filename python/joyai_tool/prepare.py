"""Create private config and scoped backend grants for this clone only."""
import argparse
import json
import os
from pathlib import Path
import secrets
import uuid
from urllib.request import urlopen
import yaml
from .contracts import OPERATIONS


def prepare(root):
    state = root / '.run/joyai'
    state.mkdir(parents=True, exist_ok=True)
    path = state / 'config.json'
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
            raw = next(stream for stream in source['streams'] if stream['stream_name'] == name and stream['task_type'] == 'raw')
            label = name.replace('camera_', '') + '号摄像头'
            cameras[name] = {'source_id': source['source_id'], 'camera_stream_id': raw['stream_id'],
                             'name': label, 'location': label,
                             'rtsp_url': f"rtsp://127.0.0.1:{os.environ['MTX_RTSP_PORT']}/live/{name}"}
        config = {'token': secrets.token_urlsafe(32), 'instance_id': str(uuid.uuid4()),
                  'business_url': f"http://127.0.0.1:{os.environ['BACKEND_PORT']}/api/v1/business",
                  'model_url': f"http://127.0.0.1:{os.environ['JOYAI_MODEL_PORT']}/v1",
                  'observer_url': f"http://127.0.0.1:{os.environ['JOYAI_OBSERVER_PORT']}/v1",
                  'review_url': f"http://127.0.0.1:{os.environ['JOYAI_REVIEW_PORT']}/v1",
                  'tool_url': f"http://127.0.0.1:{os.environ['JOYAI_TOOL_PORT']}",
                  'review_model': 'Qwen/Qwen3.8-27B-AWQ-INT4',
                  'storage_root': '/data/nfs_storage/hxjm_datas', 'cameras': cameras}
        if len(cameras) != 4:
            raise ValueError('Four public camera/stream mappings are required')
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n')
        path.chmod(0o600)
    grant = {'token': config['token'], 'operations': OPERATIONS,
             'source-ids': [camera['source_id'] for camera in config['cameras'].values()]}
    profile = state / 'backend.yml'
    profile.write_text(yaml.safe_dump({'hxjm': {'business': {'storage-root': config['storage_root'],
        'security': {'services': {'joyai-producer': grant}}}}}, allow_unicode=True))
    profile.chmod(0o600)
    print('JoyAI private config and four-source backend grant prepared; credentials were not printed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    prepare(parser.parse_args().root.resolve())
