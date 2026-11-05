"""Business-owned gallery facade; reuses the existing service identity and models.

Hosted by the existing Flask access process. Agent decision code only discovers
these operations through Capability, never calls this implementation directly.
"""
import hmac
import json
import logging
import os
from pathlib import Path
from threading import Lock

from flask import request
from jsonschema import Draft202012Validator, ValidationError

from .gallery_selection import ReIDSelections


ARTIFACTS = {
    'image': 'gallery-image.json', 'screenshot': 'gallery-screenshot.json',
    'description': 'gallery-description.json', 'select': 'gallery-select.json',
}


def build_gallery():
    from .config import DbConfig
    from .database import create_pg_engine
    from .gallery_search import GallerySearchService
    from .clipreid_client import ClipReIDClient
    from .text_reid_client import TextReIDClient
    cfg = DbConfig(host=os.environ['DB_HOST'], port=int(os.getenv('DB_PORT', '5432')),
                   user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'],
                   database=os.environ['DB_NAME'], schema=os.getenv('DB_SCHEMA', 'public'),
                   connect_timeout_s=float(os.getenv('DB_CONNECT_TIMEOUT_S', '5')))
    timeout = float(os.getenv('REID_TIMEOUT_S', '15'))
    url = os.environ['REID_FEATURE_BASE_URL']
    engine = create_pg_engine(cfg)
    try:
        return GallerySearchService(engine=engine, schema=cfg.schema,
            feature_client=ClipReIDClient(url, timeout, os.getenv('REID_FEATURE_SPACE_ID', '')),
            text_feature_client=TextReIDClient(url, timeout, os.getenv('REID_TEXT_FEATURE_SPACE_ID', ''),
                os.getenv('REID_TEXT_CONTRACT_ID', ''), int(os.getenv('REID_TEXT_MAX_CHARS', '200'))),
            text_max_chars=int(os.getenv('REID_TEXT_MAX_CHARS', '200')))
    except BaseException:
        engine.dispose()
        raise


def install_gallery_api(app, *, service_factory=build_gallery):
    root = Path(__file__).resolve().parents[4] / 'contracts/capability-v1'
    validators = {name: Draft202012Validator(json.loads((root / filename).read_text())[
        'capability']['contract']['input_schema']['properties']['payload'])
        for name, filename in ARTIFACTS.items()}
    lock = Lock()
    service = None
    selections = None

    def close():
        if service is not None:
            service.engine.dispose()

    app.extensions['gallery_business_close'] = close

    @app.post('/api/v1/business/gallery/<operation>')
    def gallery_operation(operation):
        nonlocal service, selections
        # Same configured service account as Capability; no new identities or user login.
        identity, token = os.getenv('CAPABILITY_SERVICE_ID', ''), os.getenv('CAPABILITY_SERVICE_TOKEN', '')
        if (not identity or not token or request.headers.get('X-HXJM-Service-Id') != identity
                or not hmac.compare_digest(request.headers.get('X-HXJM-Service-Token', ''), token)):
            return {'error': {'code': 'FORBIDDEN', 'message': '服务身份无权调用图库能力', 'retryable': False}}, 403
        if operation not in validators:
            return {'error': {'code': 'NOT_FOUND', 'message': '未知图库操作', 'retryable': False}}, 404
        payload = request.get_json(silent=True)
        try:
            validators[operation].validate(payload)
        except ValidationError:
            return {'error': {'code': 'INVALID_ARGUMENT', 'message': '参数不符合能力契约', 'retryable': False}}, 400
        try:
            with lock:
                if service is None:
                    service = service_factory()
                    selections = ReIDSelections(service)
            if operation == 'select':
                prompt = '取消' if payload['candidate_id'] == 'cancel' else '选择' + payload['candidate_id']
                result = selections.resume(payload['source_asset_id'], prompt)
                if result is None:
                    result = {'type': 'pedestrian_selection', 'status': 'selection_expired',
                              'message': '没有有效的待选择截图，请重新上传。'}
            elif operation == 'description':
                result = service.search_description(payload['description'], payload.get('top_k', 5))
            elif operation == 'image':
                result = service.search_image(payload['image_base64'], payload.get('top_k', 5))
            else:
                result = service.search_screenshot(payload['image_base64'], payload.get('top_k', 5))
                if result.get('status') == 'selection_required':
                    selections.remember(result['source_asset_id'], payload['image_base64'], result)
            return result
        except Exception:
            logging.getLogger(__name__).exception('Gallery capability failed: %s', operation)
            return {'error': {'code': 'GALLERY_UNAVAILABLE', 'message': '图库或特征服务不可用，未完成检索', 'retryable': False}}, 503
