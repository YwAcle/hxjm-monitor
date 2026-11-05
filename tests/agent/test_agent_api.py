"""Agent API uses only the request directory and local helpers, without a DB."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx

from llm_agent_service.app import create_app
from llm_agent_service.config import ServiceConfig
from llm_agent_service.tools.capability_bridge import CapabilityBridge


class AgentToolsApiTests(unittest.TestCase):
    def make_app(self, handler):
        bridge = CapabilityBridge('http://business', 'svc', 'secret',
                                  transport=httpx.MockTransport(handler), wait_s=0)
        model = MagicMock()
        model.invoke.return_value = SimpleNamespace(content='{"action":"final","answer":"你好"}')
        with patch('llm_agent_service.app.CapabilityBridge.from_env', return_value=bridge):
            return create_app(svc_cfg=ServiceConfig(), llm=model)

    def test_tools_endpoint_refreshes_public_directory(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={'items': [{
                'tool_name': 'business_query', 'description': 'query', 'input_schema': {'type': 'object'},
                'read_only': True, 'capability_code': 'business.query',
                'instance_id': 'instance', 'output_types': ['page']}]})
        client = self.make_app(handler).test_client()
        for _ in range(2):
            response = client.get('/tools')
            self.assertEqual(response.status_code, 200)
            tools = response.get_json()['tools']
            self.assertEqual({t['name'] for t in tools},
                             {'parse_time', 'super_resolve_image', 'get_capability_task', 'business_query'})
            self.assertTrue(all('handler' not in t for t in tools))
        self.assertEqual(len(calls), 2)

    def test_directory_failure_never_falls_back_to_legacy_tools(self):
        client = self.make_app(lambda r: httpx.Response(503)).test_client()
        self.assertEqual(client.get('/tools').status_code, 503)
        self.assertEqual(client.post('/chat', json={'prompt': '查人员'}).status_code, 503)
        response = client.post('/chat/stream', json={'prompt': '查人员'})
        self.assertIn('CAPABILITY_DIRECTORY_UNAVAILABLE', response.get_data(as_text=True))

    def test_chat_and_memory_remain_local(self):
        client = self.make_app(lambda r: httpx.Response(200, json={'items': []})).test_client()
        self.assertEqual(client.post('/chat', json={'prompt': '你好', 'session_id': 's'}).status_code, 200)
        self.assertTrue(client.delete('/sessions/s/memory').get_json()['cleared'])
        self.assertFalse(client.delete('/sessions/s/memory').get_json()['cleared'])

    def test_readiness_checks_directory_not_database(self):
        client = self.make_app(lambda r: httpx.Response(200, json={'items': []})).test_client()
        result = client.get('/ready')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.get_json()['capability_directory'], 'ok')
        self.assertNotIn('database', result.get_json())

    def test_retired_person_cache_routes_are_not_exposed(self):
        client = self.make_app(lambda r: httpx.Response(200, json={'items': []})).test_client()
        self.assertEqual(client.get('/persons').status_code, 404)
        self.assertEqual(client.post('/reload_persons').status_code, 404)


if __name__ == '__main__':
    unittest.main()
