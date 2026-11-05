"""In-memory task adapter for Agent → Capability → actual gallery HTTP facade tests."""
import json
from pathlib import Path
from unittest.mock import patch
import httpx
from flask import Flask
from business_api.routes import install_gallery_api
from llm_agent_service.app import create_app
from llm_agent_service.config import ServiceConfig
from llm_agent_service.tools.capability_bridge import CapabilityBridge
from llm_agent_service.tools.default_tools import build_default_registry


class GalleryCapabilityFixture:
    def __init__(self, gallery):
        self.gallery = gallery
        host = Flask(__name__)
        install_gallery_api(host, service_factory=lambda: gallery)
        self.client = host.test_client()
        self.tasks = {}
        self.artifacts = [json.loads(p.read_text()) for p in
            (Path(__file__).resolve().parents[2] / 'contracts/capability-v1').glob('gallery-*.json')]
        self.bridge = CapabilityBridge('http://business', 'svc', 'secret',
                                      transport=httpx.MockTransport(self.handle), wait_s=1)

    def handle(self, request):
        if request.url.path.endswith('/capabilities/tools'):
            return httpx.Response(200, json={'items': [dict(
                tool_name=a['capability']['agent']['tool_name'], description=a['capability']['agent']['description'],
                input_schema=a['capability']['contract']['input_schema']['properties']['payload'],
                context_inputs=a['capability']['agent'].get('context_inputs', {}), read_only=True,
                capability_code=a['capability']['capability_code'], instance_id=a['instance']['execution']['operation'],
                output_types=a['capability']['contract']['output_types']) for a in self.artifacts]})
        if request.method == 'POST':
            data = json.loads(request.content)
            response = self.client.post('/api/v1/business/gallery/' + data['instance_id'],
                json=data['input']['payload'], headers=dict(request.headers))
            task_id = '00000000-0000-0000-0000-' + str(len(self.tasks)+1).zfill(12)
            result = dict(task_id=task_id, run_id='run', state='succeeded', outputs=[{'payload': response.get_json()}])
            if response.status_code != 200:
                result.update(state='failed', failure=response.get_json()['error'], outputs=[])
            self.tasks[task_id] = result
            return httpx.Response(200, json={'task_id': task_id, 'state': 'pending'})
        return httpx.Response(200, json=self.tasks[request.url.params['task_id']])

    def app(self, llm):
        with patch('llm_agent_service.app.CapabilityBridge.from_env', return_value=self.bridge):
            return create_app(svc_cfg=ServiceConfig(), llm=llm)

    def registry(self):
        return self.bridge.snapshot(build_default_registry())
