import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from flask import Flask
from business_api.routes import install_gallery_api
from tests.agent.gallery_capability_fixture import GalleryCapabilityFixture
from tests.agent.test_gallery_search import image_data


@patch.dict(os.environ, {'CAPABILITY_SERVICE_ID': 'svc', 'CAPABILITY_SERVICE_TOKEN': 'secret'})
class GalleryBusinessTests(unittest.TestCase):
    headers = {'X-HXJM-Service-Id': 'svc', 'X-HXJM-Service-Token': 'secret'}

    def test_boundary_auth_schema_lazy_init_failure_and_close(self):
        app = Flask(__name__)
        factory = MagicMock()
        install_gallery_api(app, service_factory=factory)
        client = app.test_client()
        self.assertEqual(client.post('/api/v1/business/gallery/image', json={}).status_code, 403)
        self.assertEqual(client.post('/api/v1/business/gallery/image', json={}, headers=self.headers).status_code, 400)
        factory.assert_not_called()
        factory.side_effect = RuntimeError('missing model')
        with self.assertLogs('business_api.routes', level='ERROR'):
            response = client.post('/api/v1/business/gallery/image', json={'image_base64': image_data()}, headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('missing model', response.get_data(as_text=True))
        factory.side_effect = None
        gallery = factory.return_value
        gallery.search_image.return_value = {'type': 'pedestrian_search', 'status': 'ok'}
        self.assertEqual(client.post('/api/v1/business/gallery/image', json={'image_base64': image_data()}, headers=self.headers).status_code, 200)
        app.extensions['gallery_business_close']()
        gallery.engine.dispose.assert_called_once()

    def test_screenshot_two_turns_through_task_bridge_and_memory(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming):
                asset = 'a' * 32
                gallery = MagicMock()
                gallery.search_screenshot.return_value = dict(type='pedestrian_selection', status='selection_required',
                    source_asset_id=asset, top_k=3, candidates=[{'candidate_id': '2', 'bbox': [8, 0, 16, 32]}])
                gallery.search_selected.return_value = dict(type='pedestrian_search', status='ok', candidates=[
                    {'person_id': 'A', 'similarity': 0.9, 'image_base64': image_data()}])
                llm = MagicMock()
                llm.invoke.side_effect = [SimpleNamespace(content=json.dumps(dict(action='tool',
                    tool_name='search_pedestrians_in_screenshot', arguments={'top_k': 3}))),
                    SimpleNamespace(content=json.dumps(dict(action='tool', tool_name='select_gallery_candidate',
                        arguments={'source_asset_id': asset, 'candidate_id': '2'}))),
                    SimpleNamespace(content='{"action":"final","answer":"找到相似候选"}')]
                llm.stream.return_value = iter([SimpleNamespace(content='找到相似候选')])
                fixture = GalleryCapabilityFixture(gallery)
                client = fixture.app(llm).test_client()
                endpoint = '/chat/stream' if streaming else '/chat'
                response = client.post(endpoint, json={'session_id': 's', 'prompt': '截图找人', 'image': image_data()})
                self.assertIn('selection_required', response.get_data(as_text=True))
                response = client.post(endpoint, json={'session_id': 's', 'prompt': '选择2'})
                body = response.get_data(as_text=True)
                self.assertIn('pedestrian_search', body)
                self.assertIn('capability_task', body)
                gallery.search_selected.assert_called_once_with(image_data(), [8, 0, 16, 32], 3)
                messages = llm.invoke.call_args_list[1].args[0]
                self.assertTrue(any(asset in str(m.content) for m in messages))
                self.assertEqual(client.delete('/sessions/s/memory').status_code, 200)
                # The server consumes selection once; a repeated selection cannot replay the image.
                expired = fixture.client.post('/api/v1/business/gallery/select', headers=self.headers,
                    json={'source_asset_id': asset, 'candidate_id': '2'})
                self.assertEqual(expired.get_json()['status'], 'selection_expired')
                forged = fixture.client.post('/api/v1/business/gallery/select', headers=self.headers,
                    json={'source_asset_id': asset, 'candidate_id': '2', 'bbox': [0, 0, 1, 1]})
                self.assertEqual(forged.status_code, 400)
