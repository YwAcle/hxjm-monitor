#!/usr/bin/env python3
"""Run current-copy acceptance using private configuration without printing credentials."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import yaml

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--backend-config',type=Path,required=True)
parser.add_argument('--postgres-container',required=True)
parser.add_argument('--model-base-url',required=True)
parser.add_argument('--python',required=True)
parser.add_argument('--evidence',required=True)
parser.add_argument('--business-url',default='http://127.0.0.1:18580/api/v1/business')
args=parser.parse_args()
c=yaml.safe_load(args.backend_config.read_text())['hxjm']['business']
container=json.loads(subprocess.check_output(['docker','inspect',args.postgres_container]))[0]
pg=dict(x.split('=',1) for x in container['Config']['Env'])
port=container['NetworkSettings']['Ports']['5432/tcp'][0]['HostPort']
env=dict(os.environ,CAPABILITY_BRIDGE_ENABLED='true',CAPABILITY_BUSINESS_URL=args.business_url,CAPABILITY_SERVICE_ID='hxjm-pipeline',CAPABILITY_SERVICE_TOKEN=c['security']['services']['hxjm-pipeline']['token'],PGHOST='127.0.0.1',PGPORT=port,PGUSER=pg['POSTGRES_USER'],PGPASSWORD=pg['POSTGRES_PASSWORD'],PGDATABASE=pg['POSTGRES_DB'])
subprocess.run([args.python,'Agent/tests/live_capability_v1.py','--model-base-url',args.model_base_url,'--evidence',args.evidence],env=env,check=True)
