#!/usr/bin/env python3
"""Register the same immutable contracts repeatedly; conflicts never overwrite."""
import argparse
import json
import os
from pathlib import Path
import urllib.request
from uuid import uuid4


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default=os.getenv('CAPABILITY_BUSINESS_URL'))
    parser.add_argument('--namespace',required=True)
    parser.add_argument('configs',nargs='+',type=Path)
    args=parser.parse_args()
    service=os.environ['CAPABILITY_SERVICE_ID'];token=os.environ['CAPABILITY_SERVICE_TOKEN']
    if not args.base_url:parser.error('--base-url is required')
    def request(path,body=None):
        encoded=None if body is None else json.dumps(dict(body,request_id=str(uuid4()))).encode()
        req=urllib.request.Request(args.base_url.rstrip('/')+path,data=encoded,headers={'Content-Type':'application/json','X-HXJM-Service-Id':service,'X-HXJM-Service-Token':token})
        with urllib.request.urlopen(req,timeout=15) as response:return json.load(response)
    for path in args.configs:
        config=json.loads(path.read_text())
        for endpoint,definition,query,key in [('/result-types',config['result_type'],'?type_code='+config['result_type']['type_code']+'&schema_version='+config['result_type']['schema_version'],'type_code'),('/capabilities',config['capability'],'?capability_code='+config['capability']['capability_code'],'capability_code')]:
            existing=request(endpoint+query)['items']
            if existing:
                old=existing[0]
                for field,value in definition.items():
                    if old.get(field)!=value:raise ValueError('Existing contract differs: '+definition[key]+'/'+field)
            else:request(endpoint,definition)
        instance=dict(config['instance'],capability_code=config['capability']['capability_code'],instance_key=args.namespace)
        existing=request('/instances?capability_code='+instance['capability_code'])['items']
        matches=[i for i in existing if i['instance_key']==args.namespace]
        if matches:
            old=matches[0]
            for field,value in instance.items():
                if old.get(field)!=value:raise ValueError('Existing instance differs: '+field)
            instance_id=old['id']
        else:
            instance_id=str(uuid4());request('/instances',dict(instance,instance_id=instance_id))
        print(json.dumps({'capability_code':instance['capability_code'],'instance_id':instance_id}))

if __name__=='__main__':main()
