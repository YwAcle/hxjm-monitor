import concurrent.futures
import json
from pathlib import Path
import unittest
import httpx
from llm_agent_service.tools.capability_bridge import CapabilityBridge, JsonSchemaTool, check_schema, CapabilityDirectoryError
from llm_agent_service.tools.registry import ToolRegistry


class CapabilityBridgeTests(unittest.TestCase):
    def test_shared_contract_cases(self):
        cases=json.loads((Path(__file__).parents[2]/'contracts/capability-v1/schema-cases.json').read_text())
        for case in cases:
            tool=JsonSchemaTool('test','test',case['schema'],lambda args:args)
            for valid in case['valid']: self.assertTrue(tool.invoke(valid).ok)
            for invalid in case['invalid']: self.assertFalse(tool.invoke(invalid).ok)
        with self.assertRaises(ValueError):check_schema({'$ref':'https://example.com/schema'})

    def test_request_snapshots_are_isolated_and_next_request_refreshes(self):
        def build(name):
            def response(request):
                return httpx.Response(200,json={'items':[{'tool_name':name,'description':'query','input_schema':{'type':'object'},'read_only':True,'capability_code':name,'instance_id':'instance','output_types':['page']}]})
            return CapabilityBridge('http://business','svc','secret',transport=httpx.MockTransport(response)).snapshot(ToolRegistry())
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            a,b=list(pool.map(build,['one','two']))
        self.assertEqual({t.name for t in a.list()},{'one','get_capability_task'})
        self.assertEqual({t.name for t in b.list()},{'two','get_capability_task'})
        self.assertIn('three',{t.name for t in build('three').list()})

    def test_task_roundtrip_uses_standard_submit_and_outputs(self):
        def response(request):
            if request.method=='POST':
                body=json.loads(request.content)
                self.assertEqual(body['input'],{'kind':'capability_call','payload':{'mode':'latest'}})
                return httpx.Response(200,json={'task_id':'task','state':'pending'})
            return httpx.Response(200,json={'task_id':'task','state':'succeeded','outputs':[{'payload':{'items':[{'event_id':'real-shape'}]}}]})
        bridge=CapabilityBridge('http://business','svc','secret',transport=httpx.MockTransport(response))
        result=bridge.call({'capability_code':'events','instance_id':'instance','output_types':['page']},{'mode':'latest'})
        self.assertEqual(result['state'],'succeeded')
        self.assertEqual(result['outputs'][0]['payload']['items'][0]['event_id'],'real-shape')

    def test_wait_timeout_returns_task_without_cancel(self):
        requests=[]
        def response(request):
            requests.append(request)
            return httpx.Response(200,json={'task_id':'task','state':'pending'})
        bridge=CapabilityBridge('http://business','svc','secret',transport=httpx.MockTransport(response),wait_s=0)
        self.assertEqual(bridge.call({'capability_code':'events','instance_id':'instance','output_types':['page']},{})['task_id'],'task')
        self.assertEqual(len(requests),1)

    def test_catalog_failure_and_collision_do_not_fallback(self):
        bridge=CapabilityBridge('http://business','svc','secret',transport=httpx.MockTransport(lambda req:httpx.Response(503)))
        with self.assertRaises(CapabilityDirectoryError):bridge.snapshot(ToolRegistry())
        static=ToolRegistry();static.register(JsonSchemaTool('get_capability_task','collision',{},lambda a:a))
        bridge=CapabilityBridge('http://business','svc','secret',transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'items':[]})))
        with self.assertRaises(ValueError):bridge.snapshot(static)

    def test_executor_uses_explicit_registry_without_mutating_default(self):
        from types import SimpleNamespace
        from llm_agent_service.agent.executor import AgentExecutor
        class Model:
            def __init__(self):self.step=0
            def invoke(self,messages,**kwargs):
                self.step+=1
                return SimpleNamespace(content='{"action":"tool","tool_name":"dynamic","arguments":{}}' if self.step==1 else '{"action":"final","answer":"done"}')
        default=ToolRegistry();snapshot=ToolRegistry()
        snapshot.register(JsonSchemaTool('dynamic','request tool',{},lambda args:{'request':'one'}))
        executor=AgentExecutor(llm=Model(),registry=default)
        result=executor.run('query',registry=snapshot)
        self.assertEqual(result.data,{'request':'one'})
        self.assertIs(executor.registry,default)
        self.assertEqual(default.list(),[])
