"""Explicit real-data acceptance. No mock service, model, or synthesized business rows.

Set CAPABILITY_* service credentials and PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE.
Run with --model-base-url to additionally exercise the local Agent Flask chat route.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from time import monotonic
from uuid import uuid4

from llm_agent_service.tools.capability_bridge import CapabilityBridge
from llm_agent_service.tools.registry import ToolRegistry


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-base-url')
    parser.add_argument('--evidence',type=Path,required=True)
    args=parser.parse_args()
    bridge=CapabilityBridge.from_env()
    if bridge is None:raise ValueError('Enable CAPABILITY_BRIDGE_ENABLED')
    registry=bridge.snapshot(ToolRegistry())
    evidence={'checked_at':datetime.now(timezone.utc).isoformat(),'business':[]}
    for name,payload,path in [('query_business_events',{'mode':'latest','limit':3},'/events/query'),('query_business_reports',{'start_at':'2026-10-01T00:00:00Z','end_at':'2026-11-05T00:00:00Z','limit':3},'/reports/search')]:
        direct=bridge.request('POST',path,json=payload)
        tool=registry.invoke(name,payload)
        if not tool.ok:raise RuntimeError(tool.error_message)
        task=tool.data
        deadline=monotonic()+20
        while task['state'] in ('pending','running') and monotonic()<deadline:
            from time import sleep
            sleep(.2);task=bridge.task(task['task_id'])
        if task['state']!='succeeded':raise RuntimeError(str(task.get('failure')))
        stored=task['outputs'][0]
        assert direct['items']==stored['payload']['items'], 'Direct business rows differ from persisted outputs'
        evidence['business'].append({'tool':name,'task_id':task['task_id'],'run_id':task['run_id'],'state':task['state'],'direct_count':len(direct['items']),'stored_count':len(stored['payload']['items']),'nonempty_verified':bool(stored['payload']['items'])})
    if args.model_base_url:
        from llm_agent_service.app import create_app
        from llm_agent_service.config import DbConfig, ServiceConfig, ModelConfig
        from llm_agent_service.db.session import create_pg_engine
        from llm_agent_service.llm import build_llm
        db=DbConfig(host=os.environ['PGHOST'],port=int(os.environ['PGPORT']),user=os.environ['PGUSER'],password=os.environ['PGPASSWORD'],database=os.environ['PGDATABASE'])
        cfg=ModelConfig(base_url=args.model_base_url,max_retries=0,enable_thinking=False)
        llm=build_llm(cfg);engine=create_pg_engine(db)
        app=create_app(engine=engine,db_cfg=db,svc_cfg=ServiceConfig(),llm=llm)
        started=monotonic()
        with app.test_client() as client:
            tools=client.get('/tools');assert tools.status_code==200
            names=[item['name'] for item in tools.get_json()['tools']]
            print('request tool names:', names, flush=True)
            assert 'query_business_events' in names, 'Dynamic tools not exposed by current app' 
            response=client.post('/chat',json={'prompt':'请查询业务事件目录里最新的3条事件记录，不是视频异常检测记录。如果没有记录，请如实说明。','session_id':'capv1-live-'+uuid4().hex})
            assert response.status_code==200, response.status_code
            result=response.get_json();task=result.get('data') or {}
            assert task.get('task_id') and task.get('state')=='succeeded', 'Model did not complete the capability tool call'
            assert result['text'] and result['agent']['finish_reason']=='final'
            evidence['agent']={'http_status':response.status_code,'task_id':task['task_id'],'run_id':task['run_id'],'finish_reason':result['agent']['finish_reason'],'answer':result['text'],'elapsed_s':round(monotonic()-started,2),'source':'current repository Flask /chat + remote HTTP model'}
        engine.dispose()
    args.evidence.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(evidence,ensure_ascii=False))

if __name__=='__main__':main()
