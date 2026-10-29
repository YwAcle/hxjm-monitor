"""Bounded multi-camera analysis configuration; URLs are deployment settings."""
import json
import math
import os
import re
import uuid
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
ALGORITHM = os.getenv("VIDEO_ANALYSIS_ALGORITHM", "botsort").lower()
if ALGORITHM not in {"botsort", "deepsort"}:
    raise ValueError("VIDEO_ANALYSIS_ALGORITHM must be botsort or deepsort")
CACHE_ROOT = Path(os.getenv("VIDEO_ANALYSIS_CACHE_DIR", str(Path(__file__).parent / ".runtime")))
CAMERA_ID = os.getenv("VIDEO_ANALYSIS_CAMERA_ID", "camera_1")
if not re.fullmatch(r"camera_[1-9][0-9]*", CAMERA_ID):
    raise ValueError("VIDEO_ANALYSIS_CAMERA_ID must be camera_<positive integer>")
RTSP_URL = os.getenv("VIDEO_ANALYSIS_RTSP_URL", f"rtsp://127.0.0.1:18554/live/{CAMERA_ID}")
RTSP_TRANSPORT = os.getenv("VIDEO_ANALYSIS_RTSP_TRANSPORT", "tcp").lower()
if RTSP_TRANSPORT not in {"udp", "tcp"}:
    raise ValueError("VIDEO_ANALYSIS_RTSP_TRANSPORT must be udp or tcp")
OPEN_TIMEOUT_MS = 5000
READ_TIMEOUT_MS = 5000
DECODE_THREADS = int(os.getenv('VIDEO_ANALYSIS_DECODE_THREADS', '1'))
if not 1 <= DECODE_THREADS <= 8:
    raise ValueError('VIDEO_ANALYSIS_DECODE_THREADS must be between 1 and 8')
OPENCV_THREADS = int(os.getenv('VIDEO_ANALYSIS_OPENCV_THREADS', '4'))
if not 1 <= OPENCV_THREADS <= 8:
    raise ValueError('VIDEO_ANALYSIS_OPENCV_THREADS must be between 1 and 8')


def positive_seconds(name, default):
    value = float(os.getenv(name, default))
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value


def boolean_env(name, default=False):
    value = os.getenv(name, "yes" if default else "no").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


INFERENCE_INTERVAL_SECONDS = positive_seconds("VIDEO_ANALYSIS_INTERVAL_SECONDS", "0.05" if ALGORITHM == "botsort" else "1")
# Synchronized JPEG frames share the inference workers with all cameras. Keep
# the default sustainable for multi-camera playback; deployments can raise it
# explicitly after measuring their available inference and network capacity.
SYNC_FPS = positive_seconds("VIDEO_ANALYSIS_SYNC_FPS", "8")
if SYNC_FPS > 60:
    raise ValueError("VIDEO_ANALYSIS_SYNC_FPS must be at most 60")
SYNC_FRAME_WIDTH = 1280
SYNC_FRAME_HEIGHT = 720
SYNC_JPEG_QUALITY = 80
SYNC_MAX_JPEG_BYTES = 2 * 1024 * 1024
RECONNECT_DELAY_SECONDS = positive_seconds("VIDEO_ANALYSIS_RECONNECT_SECONDS", "2")
WS_SEND_TIMEOUT_SECONDS = positive_seconds("VIDEO_ANALYSIS_WS_SEND_TIMEOUT_SECONDS", "5")
RESULT_TTL_MS = int(positive_seconds("VIDEO_ANALYSIS_RESULT_TTL_SECONDS", "3") * 1000)

# Recording is an explicit opt-in so existing deployments keep their current
# capture behavior until the NFS path has been prepared and reviewed.
RECORDING_ENABLED = boolean_env("VIDEO_ANALYSIS_RECORDING_ENABLED")
RECORDING_ROOT = os.getenv("VIDEO_ANALYSIS_RECORDING_ROOT", "/data/nfs_storage/hxjm_datas")
if not RECORDING_ROOT.strip() or not Path(RECORDING_ROOT).is_absolute():
    raise ValueError("VIDEO_ANALYSIS_RECORDING_ROOT must be an absolute path")
RECORDING_SEGMENT_SECONDS = positive_seconds(
    "VIDEO_ANALYSIS_RECORDING_SEGMENT_SECONDS", "3600"
)
RECORDING_QUEUE_SIZE = int(os.getenv("VIDEO_ANALYSIS_RECORDING_QUEUE_SIZE", "256"))
if RECORDING_QUEUE_SIZE <= 0:
    raise ValueError("VIDEO_ANALYSIS_RECORDING_QUEUE_SIZE must be positive")
RECORDING_RETENTION_SECONDS = int(
    positive_seconds("VIDEO_ANALYSIS_RECORDING_RETENTION_SECONDS", "604800")
)


def camera_configs():
    raw = os.getenv("VIDEO_ANALYSIS_CAMERAS")
    if raw:
        cameras = json.loads(raw)
    else:
        base = os.getenv("VIDEO_ANALYSIS_RTSP_BASE", "rtsp://127.0.0.1:18554/live").rstrip("/")
        # Keep the explicit stage-one single-camera deployment setting compatible.
        cameras = ({CAMERA_ID: RTSP_URL} if os.getenv("VIDEO_ANALYSIS_RTSP_URL") else
                   {f"camera_{i}": f"{base}/camera_{i}" for i in range(1, 5)})
    if not isinstance(cameras, dict) or not 1 <= len(cameras) <= 16:
        raise ValueError("VIDEO_ANALYSIS_CAMERAS must map 1 to 16 camera IDs to RTSP URLs")
    for camera_id, url in cameras.items():
        if not re.fullmatch(r"camera_[1-9][0-9]*", camera_id):
            raise ValueError("Camera IDs must be camera_<positive integer>")
        if not isinstance(url, str) or not url.startswith("rtsp://"):
            raise ValueError("Camera sources must be RTSP URLs")
    return cameras


CAMERAS = camera_configs()


def camera_source_ids(cameras, raw=None):
    raw = os.getenv('VIDEO_ANALYSIS_SOURCE_IDS') if raw is None else raw
    if raw is None:
        return {}
    mapping = json.loads(raw)
    if not isinstance(mapping, dict) or set(mapping) != set(cameras):
        raise ValueError('VIDEO_ANALYSIS_SOURCE_IDS must map every configured camera to its source UUID')
    for source_id in mapping.values():
        if (not isinstance(source_id, str) or str(uuid.UUID(source_id)) != source_id
                or uuid.UUID(source_id).int == 0):
            raise ValueError('Source IDs must be canonical nonzero UUIDs')
    if len(set(mapping.values())) != len(mapping):
        raise ValueError('Each configured camera must map to a distinct source')
    return mapping


SOURCE_IDS = camera_source_ids(CAMERAS)


def load_business_config(path=None, *, cameras=None, source_ids=None, algorithm=None):
    """Load explicit delivery configuration without creating directories or clients."""
    configured_path = os.getenv('VIDEO_ANALYSIS_BUSINESS_CONFIG') if path is None else path
    if configured_path is None:
        return None
    if not isinstance(configured_path, (str, Path)) or not str(configured_path).strip():
        raise ValueError('VIDEO_ANALYSIS_BUSINESS_CONFIG requires a JSON file path')
    try:
        configuration = json.loads(Path(configured_path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise ValueError('Cannot read a valid business configuration JSON object') from None
    required = {'api_url', 'service_id', 'token_env', 'source_streams', 'instances'}
    optional = {'spool_dir', 'timeout_seconds', 'batch_size', 'queue_size', 'flush_interval_seconds',
                'sample_pipeline'}
    if (not isinstance(configuration, dict) or not required.issubset(configuration)
            or not set(configuration).issubset(required | optional)):
        raise ValueError('Business configuration has missing or unsupported fields')
    for name in ('api_url', 'service_id', 'token_env'):
        if not isinstance(configuration[name], str) or not configuration[name].strip():
            raise ValueError('Business API URL, service ID and token environment name are required')
    token_env = configuration['token_env']
    if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', token_env) is None:
        raise ValueError('token_env must name an environment variable')
    token = os.getenv(token_env)
    if not isinstance(token, str) or not token.strip() or '\r' in token or '\n' in token:
        raise ValueError('The configured business service token environment variable is missing or invalid')

    cameras = CAMERAS if cameras is None else cameras
    source_ids = SOURCE_IDS if source_ids is None else source_ids
    algorithm = ALGORITHM if algorithm is None else algorithm
    if not source_ids:
        raise ValueError('Business delivery requires complete VIDEO_ANALYSIS_SOURCE_IDS')
    camera_source_ids(cameras, json.dumps(source_ids))
    sources = set(source_ids.values())
    streams = configuration['source_streams']
    if not isinstance(streams, dict) or set(streams) != sources:
        raise ValueError('source_streams must map every configured source to its camera_stream UUID')
    for stream in streams.values():
        if (not isinstance(stream, str) or str(uuid.UUID(stream)) != stream
                or uuid.UUID(stream).int == 0):
            raise ValueError('Camera stream references must be canonical nonzero UUIDs')
    if len(set(streams.values())) != len(streams):
        raise ValueError('Each configured source requires a distinct camera_stream')
    instances = configuration['instances']
    if not isinstance(instances, list) or not instances:
        raise ValueError('instances must list explicit source and algorithm bindings')
    bindings = {}
    for instance in instances:
        if (not isinstance(instance, dict)
                or set(instance) != {'source_id', 'algorithm', 'instance_id', 'capability_code'}
                or instance['source_id'] not in sources or instance['algorithm'] != algorithm):
            raise ValueError('Each instance must bind a configured source and the active algorithm')
        key = instance['source_id'], instance['algorithm']
        if key in bindings:
            raise ValueError('A source and algorithm cannot have repeated instance bindings')
        instance_id = instance['instance_id']
        if (not isinstance(instance_id, str) or str(uuid.UUID(instance_id)) != instance_id
                or uuid.UUID(instance_id).int == 0):
            raise ValueError('Instance references must be canonical nonzero UUIDs')
        code = instance['capability_code']
        if not isinstance(code, str) or not 1 <= len(code) <= 64 or code != code.strip():
            raise ValueError('Each instance requires its capability code')
        bindings[key] = {'instance_id': instance_id, 'capability_code': code}
    if set(bindings) != {(source, algorithm) for source in sources}:
        raise ValueError('instances must cover every configured source and the active algorithm')

    normalized = dict(configuration, instances=bindings)
    spool_dir = normalized.setdefault('spool_dir', '/data/nfs_storage/hxjm_datas/result-spool')
    if not isinstance(spool_dir, str) or not spool_dir.strip() or not Path(spool_dir).is_absolute():
        raise ValueError('spool_dir must be an explicit absolute directory')
    for name, default in (('batch_size', 32), ('queue_size', 256)):
        value = normalized.setdefault(name, default)
        if type(value) is not int or value <= 0:
            raise ValueError('Business batch_size and queue_size must be positive integers')
    for name, default in (('timeout_seconds', 5), ('flush_interval_seconds', 0.2)):
        value = normalized.setdefault(name, default)
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value <= 0):
            raise ValueError('Business timeout and flush interval must be finite and positive')
    sample = normalized.get('sample_pipeline')
    if sample is not None:
        from urllib.parse import urlsplit
        if (not isinstance(sample, dict)
                or not {'feature_url', 'instance_id'}.issubset(sample)
                or not set(sample).issubset({'feature_url', 'instance_id', 'capability_code',
                                            'threshold', 'queue_size'})):
            raise ValueError('sample_pipeline requires feature_url and instance_id')
        if not isinstance(sample['feature_url'], str):
            raise ValueError('Feature service URL must be an HTTP(S) origin')
        parts = urlsplit(sample['feature_url'])
        if (parts.scheme not in ('http', 'https') or not parts.hostname
                or parts.username is not None or parts.password is not None
                or parts.query or parts.fragment or parts.path not in ('', '/')):
            raise ValueError('Feature service URL must be an HTTP(S) origin without credentials')
        if (not isinstance(sample['instance_id'], str)
                or str(uuid.UUID(sample['instance_id'])) != sample['instance_id']
                or uuid.UUID(sample['instance_id']).int == 0):
            raise ValueError('Feature instance requires a canonical nonzero UUID')
        sample = dict(sample)
        sample.setdefault('capability_code', 'person.reidentification')
        if not isinstance(sample['capability_code'], str) or not 1 <= len(sample['capability_code']) <= 64:
            raise ValueError('Feature capability code is required')
        sample.setdefault('threshold', 0.88)
        value = sample['threshold']
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('ReID threshold must be finite and between 0 and 1')
        sample.setdefault('queue_size', 16)
        if type(sample['queue_size']) is not int or sample['queue_size'] <= 0:
            raise ValueError('Sample queue size must be a positive integer')
        normalized['sample_pipeline'] = sample
    return normalized


WORKER_COUNT = int(os.getenv("VIDEO_ANALYSIS_WORKERS", "1"))
if not 1 <= WORKER_COUNT <= 4:
    raise ValueError("VIDEO_ANALYSIS_WORKERS must be between 1 and 4")
INFERENCE_TIMEOUT_SECONDS = positive_seconds("VIDEO_ANALYSIS_INFERENCE_TIMEOUT_SECONDS", "10")
MODEL_TIMEOUT_SECONDS = positive_seconds("VIDEO_ANALYSIS_MODEL_TIMEOUT_SECONDS", "60")
WORKER_RETRY_SECONDS = positive_seconds("VIDEO_ANALYSIS_WORKER_RETRY_SECONDS", "5")
WORKER_RETRY_MAX_SECONDS = positive_seconds("VIDEO_ANALYSIS_WORKER_RETRY_MAX_SECONDS", "120")
WORKER_IDLE_SECONDS = positive_seconds("VIDEO_ANALYSIS_WORKER_IDLE_SECONDS", "60")
FRAME_FRESH_MS = int(positive_seconds("VIDEO_ANALYSIS_FRAME_FRESH_SECONDS", "2") * 1000)
MAX_FRAME_BYTES = int(os.getenv("VIDEO_ANALYSIS_MAX_FRAME_BYTES", str(3840 * 2160 * 3)))
if not 1 <= MAX_FRAME_BYTES <= 128 * 1024 * 1024:
    raise ValueError("VIDEO_ANALYSIS_MAX_FRAME_BYTES must be between 1 and 128 MiB")
MAX_CLIENTS = int(os.getenv("VIDEO_ANALYSIS_MAX_CLIENTS", "64"))
if not 1 <= MAX_CLIENTS <= 1024:
    raise ValueError("VIDEO_ANALYSIS_MAX_CLIENTS must be between 1 and 1024")
