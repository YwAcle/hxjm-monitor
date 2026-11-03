#!/usr/bin/env python3
"""Generate per-worktree runtime configuration without editing source YAML/XML."""
import hashlib
import os
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


def render(root, state):
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit('PyYAML is required by local-config.py; install PyYAML for python3.') from exc
    env = os.environ
    ipc_dir = state / 'ipc'
    ipc_dir.mkdir(parents=True, exist_ok=True)
    if len(os.fsencode(str(ipc_dir / 'savereid.ipc'))) >= 104:
        raise SystemExit('Worktree path is too long for a Unix IPC socket.')
    config = yaml.safe_load((root / 'mtx/config.yaml').read_text())
    config['mediamtx_url'] = f"rtsp://127.0.0.1:{env['MTX_RTSP_PORT']}/live"
    tasks = set(config.get('ai_tasks_ipc', {})) | {'boxmot', 'reid', 'vad', 'deepsort'}
    tasks |= set(config.get('task_templates', {}))
    for stream in config.get('streams', []):
        tasks.update(task['type'] for task in stream.get('ai_tasks', []))
    for task in tasks:
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', task):
            raise ValueError(f'Invalid task name: {task}')
    config['ai_tasks_ipc'] = {task: f'ipc://{ipc_dir}/{"boxmot" if task == "reid" else task}.ipc'
                              for task in sorted(tasks)}
    config.setdefault('control', {}).update(enabled=True, listen_host='127.0.0.1',
        listen_port=int(env['AI_STREAM_PORT']), token=env['SMARTMONITOR_AI_CONTROL_TOKEN'])
    for task, template in config.get('task_templates', {}).items():
        template['ipc_addr'] = config['ai_tasks_ipc'][task]
    for stream in config.get('streams', []):
        for task in stream.get('ai_tasks', []):
            task['ipc_addr'] = config['ai_tasks_ipc'][task['type']]
    (state / 'ai-stream.yaml').write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False))

    try:
        media = yaml.safe_load((root / 'mtx/mediamtx/mediamtx.yml').read_text())
    except yaml.YAMLError:
        raise ValueError('Invalid media YAML; configuration contents were not printed') from None
    if not isinstance(media, dict):
        raise ValueError('Media configuration must be a YAML object')
    defaults = media.get('pathDefaults')
    record_path = defaults.get('recordPath') if isinstance(defaults, dict) else None
    if not isinstance(record_path, str) or not record_path.strip() or not Path(record_path).is_absolute():
        raise ValueError('pathDefaults.recordPath must be a nonempty absolute path')
    listeners = {'rtmpAddress': 'MTX_RTMP_PORT', 'rtspAddress': 'MTX_RTSP_PORT',
        'rtpAddress': 'MTX_RTP_PORT', 'rtcpAddress': 'MTX_RTCP_PORT', 'hlsAddress': 'MTX_HLS_PORT',
        'webrtcAddress': 'MTX_WEBRTC_PORT', 'webrtcLocalUDPAddress': 'MTX_WEBRTC_ICE_PORT',
        'srtAddress': 'MTX_SRT_PORT', 'playbackAddress': 'MTX_PLAYBACK_PORT', 'apiAddress': 'MTX_API_PORT'}
    media.update({name: ':' + env[key] for name, key in listeners.items()})
    media.update(api=True, logDestinations=['stdout'], rtspTransports=['udp', 'tcp'])
    if env.get('VIDEO_ANALYSIS_MODE') == 'shared':
        defaults['record'] = False
        for path in (media.get('paths') or {}).values():
            if isinstance(path, dict):
                path['record'] = False
    for path in [defaults, *(media.get('paths') or {}).values()]:
        if not isinstance(path, dict):
            continue
        hook = path.get('runOnRecordSegmentComplete')
        if isinstance(hook, str):
            path['runOnRecordSegmentComplete'] = re.sub(r'http://[^\s"\x27]+(?=/media-assets)',
                f"http://127.0.0.1:{env['BACKEND_PORT']}", hook)
        if 'recordPath' in path:
            path['recordPath'] = defaults['recordPath']
    if env.get('LOCAL_MEDIA_ENABLED', 'true') != 'false':
        (state / 'mediamtx.yml').write_text(yaml.safe_dump(media, allow_unicode=True, sort_keys=False))

    logging = ET.parse(root / 'SmartMonitor-wangzj/hxjm-admin/src/main/resources/logback.xml')
    for prop in logging.getroot().findall('property'):
        if prop.get('name') == 'log.path':
            prop.set('value', str(root / 'log/backend'))
    logging.write(state / 'logback.xml', encoding='unicode')
    (root / 'log/backend').mkdir(parents=True, exist_ok=True)
    return config


if __name__ == '__main__':
    render(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
