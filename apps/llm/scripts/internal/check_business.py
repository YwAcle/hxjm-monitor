"""Fail before loading a model when the configured business chain is unavailable."""
import json
import os
from pathlib import Path
from urllib.request import urlopen

from sqlalchemy import text
from business_api.routes import build_gallery
from video_analysis.business_client import BusinessClient


def check():
    client = BusinessClient(os.environ['CAPABILITY_BUSINESS_URL'],
        service_id=os.environ['CAPABILITY_SERVICE_ID'],
        token_provider=lambda: os.environ['CAPABILITY_SERVICE_TOKEN'], timeout=10)
    if client.get('/execution/status')['enabled'] is not True:
        raise RuntimeError('后端实际加载的 Capability 执行器未开启；请生成配置并重新加载后端')
    catalog = client.get('/capabilities/tools')['items']
    available = {item['capability_code'] for item in catalog}
    contracts = Path(__file__).resolve().parents[4] / 'contracts/capability-v1'
    required = {json.loads((contracts / (name + '.json')).read_text())['capability']['capability_code']
                for name in ('events', 'reports', 'identities', 'tracklets',
                             'gallery-image', 'gallery-screenshot', 'gallery-description', 'gallery-select')}
    if required - available:
        raise RuntimeError('缺少已启用的能力实例：' + ', '.join(sorted(required - available)))
    instances = client.get('/instances', {'capability_code': 'business.report.generate'})['items']
    if not any(item.get('enabled') and item.get('implementation_code') == 'llm-report' for item in instances):
        raise RuntimeError('报告生成能力尚未登记，请运行部署入口 --register')
    gallery = build_gallery()
    try:
        with gallery.engine.connect() as connection:
            connection.execute(text('SELECT id FROM public.reid_target LIMIT 1'))
        with urlopen(os.environ['REID_FEATURE_BASE_URL'].rstrip('/') + '/health', timeout=10) as response:
            if response.status != 200:
                raise RuntimeError('ReID 服务尚未就绪')
    finally:
        gallery.engine.dispose()
    print('业务启动检查通过：执行器、能力目录、图库数据库及 ReID 健康接口；不代表真实任务验收通过。')


if __name__ == '__main__':
    check()
