#!/usr/bin/env python3
"""Register HXJM deployment's configured video capability and source instances.

The script is deliberately stateful: UUIDs and request IDs are kept in the
JSON output so rerunning after a restart repeats the same idempotent requests.
It reads the service token from the environment and never writes credentials.
"""
from __future__ import annotations
import argparse, json, os, sys, uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

STATE = Path("/config/business.json")
BASE = "http://backend:8080/api/v1/business"
SERVICE_ID = "hxjm-pipeline"
CAPABILITY = "person.tracking"
RESULT_TYPE = "detection.frame"
SCHEMA_VERSION = "1"
FEATURE_CAPABILITY = "person.reidentification"
FEATURE_RESULT = "feature.embedding"

def save(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
    os.chmod(temporary, 0o600)
    temporary.replace(path)

def declared(path, payload, fields):
    """Read before registering; never overwrite another deployment's contract."""
    status, response = req('GET', path)
    items = ensure_ok('read ' + path, status, response).get('items', [])
    if not items:
        return False
    if len(items) != 1 or any(items[0].get(name) != payload[name] for name in fields):
        raise SystemExit('registered contract/configuration differs: ' + path)
    if items[0].get('enabled') is not True:
        raise SystemExit('registered contract/configuration is disabled: ' + path)
    return True

def load_token():
    name = os.environ.get("HXJM_PIPELINE_TOKEN")
    if name: return name
    raise SystemExit("HXJM_PIPELINE_TOKEN is not available")

def req(method, path, body=None, token=None):
    headers={"Accept":"application/json", "X-HXJM-Service-Id":SERVICE_ID,
             "X-HXJM-Service-Token":token or load_token()}
    data=None
    if body is not None:
        headers["Content-Type"]="application/json"; data=json.dumps(body,separators=(",",":"),ensure_ascii=False).encode()
    try:
        with urlopen(Request(BASE+path,data=data,method=method,headers=headers),timeout=10) as response:
            return response.status,json.loads(response.read())
    except HTTPError as e:
        try: detail=json.loads(e.read())
        except Exception: detail={}
        return e.code,detail
    except URLError as e: raise SystemExit(f"business API unavailable: {e.reason}")

def rid(name, state):
    return state.setdefault("request_ids",{}).setdefault(name,str(uuid.uuid4()))

def ensure_ok(label,status,data):
    if status >= 400:
        code=(data.get("error") or {}).get("code") if isinstance(data,dict) else None
        message=(data.get("error") or {}).get("message") if isinstance(data,dict) else None
        raise SystemExit(f"{label} failed HTTP {status} ({code or 'unknown'}: {message or 'no message'}); existing records are not silently treated as success")
    return data

def main():
    global BASE, CAPABILITY, RESULT_TYPE
    ap=argparse.ArgumentParser(); ap.add_argument("--state",default=str(STATE)); ap.add_argument("--base-url",default=BASE)
    ap.add_argument("--adopt-existing",action="store_true",help="explicitly accept an already registered type/instance after manual review")
    ap.add_argument('--algorithm', choices=['botsort','garbage'], default='botsort')
    ap.add_argument('--feature-url', default='http://reid:8020')
    ns=ap.parse_args(); BASE=ns.base_url.rstrip("/")
    algorithm=ns.algorithm
    if algorithm=='garbage':CAPABILITY='garbage.detection';RESULT_TYPE='garbage.detection'
    path=Path(ns.state)
    state_path=path.with_name("bootstrap-state.json" if algorithm=="botsort" else "garbage-bootstrap-state.json")
    if state_path.exists(): state=json.loads(state_path.read_text())
    elif path.exists() and algorithm=="botsort":
        legacy=json.loads(path.read_text()); state={"request_ids":legacy.get("request_ids",{}),"instances":legacy.get("instances",[])}
    else: state={}
    sources_status,sources=req("GET","/sources?page_size=200")
    sources=ensure_ok("sources",sources_status,sources).get("items",[])
    by_camera={item.get("camera_code"):item for item in sources if item.get("enabled")}
    configured=json.loads(Path("/config/bootstrap-input.json").read_text())["source_ids"]
    cameras={code:by_camera.get(code) for code in configured}
    if any(not item for item in cameras.values()): raise SystemExit("all configured camera sources are required")
    source_ids={cid:item["source_id"] for cid,item in cameras.items()}
    source_streams={}
    for cid,item in cameras.items():
        raw=[s for s in item.get("streams",[]) if s.get("task_type")=="raw" and s.get("is_active")]
        if len(raw)!=1: raise SystemExit(f"{cid} requires exactly one active raw stream")
        source_streams[item["source_id"]]=raw[0]["stream_id"]
    state["source_ids"]=source_ids; state["source_streams"]=source_streams
    # Allocate stable identities before the first side effect, including failed runs.
    saved_instances={item.get('source_id'):item for item in state.get('instances',[]) if isinstance(item,dict) and item.get('algorithm', 'botsort')==algorithm}
    instance_list=[{'source_id':source,'algorithm':algorithm,
                    'instance_id':saved_instances.get(source,{}).get('instance_id') or str(uuid.uuid4()),
                    'capability_code':CAPABILITY} for source in source_ids.values()]
    state['instances']=instance_list
    state.setdefault('feature_instance_id', str(uuid.uuid4()))
    for name in ['capability','result_type','feature_capability','feature_result_type','feature_instance'] + [
            'instance:' + camera for camera in source_ids]:
        rid(name, state)
    save(state_path, state)
    contract={
      "input_schema":{"type":"object","required":["kind","source_id","stream_session_id"],"properties":{"kind":{"type":"string","enum":["live_video"]},"source_id":{"type":"string"},"stream_session_id":{"type":"string"}}},
      "parameters_schema":{"type":"object","additionalProperties":True},
      "output_types":[RESULT_TYPE],
    }
    cap={"request_id":rid("capability",state),"trace_id":str(uuid.uuid4()),"capability_code":CAPABILITY,
         "display_name":"垃圾检测" if algorithm=="garbage" else "人员目标跟踪","object_types":["garbage" if algorithm=="garbage" else "person"],"input_kinds":["live_video"],"contract":contract}
    # Capabilities have a read endpoint; an existing contract is acceptable only
    # when it is byte-for-byte compatible with this deployment declaration.
    if not declared('/capabilities?' + urlencode({'capability_code':CAPABILITY}), cap,
                    ('capability_code','object_types','input_kinds','contract')):
        ensure_ok("capability registration",*req("POST","/capabilities",cap))
    result={"request_id":rid("result_type",state),"trace_id":str(uuid.uuid4()),"type_code":RESULT_TYPE,
            "schema_version":SCHEMA_VERSION,"max_inline_bytes":1048576,
            "json_schema":{"type":"object","required":["result_id","frame_id","occurred_at","targets"],"properties":{"result_id":{"type":"string"},"frame_id":{"type":"string"},"occurred_at":{"type":"string"},"targets":{"type":"array"}}}}
    if algorithm=='garbage':
        if not ensure_ok('garbage result schema',*req('GET','/result-types?type_code=garbage.detection&schema_version=1')).get('items'):
            raise SystemExit('garbage.detection/1 must be initialized before registration')
    else:
        if not declared('/result-types?' + urlencode({'type_code':RESULT_TYPE,'schema_version':SCHEMA_VERSION}),
                        result, ('type_code','schema_version','json_schema','max_inline_bytes')):
            ensure_ok('result type registration', *req('POST','/result-types',result))
    instances={}
    saved_instances={item['source_id']:item for item in instance_list}
    for cid,source in source_ids.items():
        instance_id=saved_instances.get(source,{}).get("instance_id") or str(uuid.uuid4())
        payload={"request_id":rid("instance:"+cid,state),"trace_id":str(uuid.uuid4()),"instance_id":instance_id,
          "capability_code":CAPABILITY,"instance_key":algorithm+":"+cid,"implementation_code":algorithm,
          "implementation_version":"configured","source_ids":[source],"service_ref":"local://hxjm/video-analysis","enabled":True}
        if not declared('/instances?' + urlencode({'instance_id':instance_id}), payload,
                        ('capability_code','instance_key','implementation_code','implementation_version',
                         'source_ids','service_ref')):
            ensure_ok('instance ' + cid, *req('POST','/instances',payload))
        instances[(source,algorithm)]={"instance_id":instance_id,"capability_code":CAPABILITY}
    if algorithm=='garbage':
        source_map={camera:dict(source_id=source,camera_stream_id=source_streams[source],instance_id=instances[(source,algorithm)]['instance_id'],timezone='Asia/Shanghai') for camera,source in source_ids.items()}
        save(state_path.with_name('garbage-sources.json'),source_map)
        state['instances']=instance_list
        save(state_path,state)
        print('Registered garbage runtime instances; source map: garbage-sources.json')
        return
    feature_contract={'input_schema':{'type':'object','required':['kind','asset_ids'],
        'properties':{'kind':{'type':'string','enum':['image']},'asset_ids':{'type':'array'}}},
        'parameters_schema':{'type':'object','additionalProperties':True},'output_types':[FEATURE_RESULT]}
    feature_cap={'request_id':rid('feature_capability',state),'capability_code':FEATURE_CAPABILITY,
        'display_name':'行人重识别特征','object_types':['person'],'input_kinds':['image'],'contract':feature_contract}
    if not declared('/capabilities?' + urlencode({'capability_code':FEATURE_CAPABILITY}), feature_cap,
                    ('capability_code','object_types','input_kinds','contract')):
        ensure_ok('feature capability',*req('POST','/capabilities',feature_cap))
    feature_result={'request_id':rid('feature_result_type',state),'type_code':FEATURE_RESULT,'schema_version':'1',
        'max_inline_bytes':1048576,'json_schema':{'type':'object','required':['feature_id','feature_space_id','embedding'],
        'properties':{'feature_id':{'type':'string'},'feature_space_id':{'type':'string'},'embedding':{'type':'array'}}}}
    if not declared('/result-types?' + urlencode({'type_code':FEATURE_RESULT,'schema_version':'1'}), feature_result,
                    ('type_code','schema_version','json_schema','max_inline_bytes')):
        ensure_ok('feature result type',*req('POST','/result-types',feature_result))
    feature_instance={'request_id':rid('feature_instance',state),'instance_id':state['feature_instance_id'],
        'capability_code':FEATURE_CAPABILITY,'instance_key':'clipreid:local','implementation_code':'clipreid',
        'implementation_version':'RN50-MSMT17-120','source_ids':list(source_ids.values()),
        'service_ref':ns.feature_url.rstrip('/'),'enabled':True}
    if not declared('/instances?' + urlencode({'instance_id':feature_instance['instance_id']}), feature_instance,
                    ('capability_code','instance_key','implementation_code','implementation_version','source_ids','service_ref')):
        ensure_ok('feature instance',*req('POST','/instances',feature_instance))
    state.update({"api_url":BASE,"service_id":SERVICE_ID,"token_env":"HXJM_PIPELINE_TOKEN","source_streams":source_streams,"capability_code":CAPABILITY,"result_type":RESULT_TYPE,"schema_version":SCHEMA_VERSION})
    instance_list=[{"source_id":source,"algorithm":"botsort","instance_id":instances[(source,algorithm)]["instance_id"],"capability_code":CAPABILITY}
                   for source in source_ids.values()]
    serial={"api_url":BASE,"service_id":SERVICE_ID,"token_env":"HXJM_PIPELINE_TOKEN",
            "source_streams":source_streams,"instances":instance_list,
            'spool_dir':'/data/result-spool',
            'sample_pipeline':{'feature_url':ns.feature_url.rstrip('/'),
                               'instance_id':state['feature_instance_id'],'threshold':0.88}}
    save(path, serial)
    state["source_ids"]=source_ids; state["source_streams"]=source_streams; state["instances"]=instance_list
    source_map = {camera: dict(source_id=source, camera_stream_id=source_streams[source],
                              instance_id=instances[(source, "botsort")]["instance_id"], timezone="Asia/Shanghai")
                  for camera, source in source_ids.items()}
    save(state_path.with_name("tracking-sources.json"), source_map)
    save(state_path,state)
    print(f"Registered tracking/feature contracts, {len(instances)} camera instances and feature instance; state: {path}")
if __name__=="__main__": main()
