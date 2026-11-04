"""Explicit empty-database initialization, version check and configuration rendering."""
import json
import os
from pathlib import Path
import re
import sys
import uuid
import bcrypt
import pymysql
from pymysql.constants import CLIENT
import psycopg
import yaml

VERSION = 'hxjm-v0.2-compose1'
BASE = Path(__file__).parent
OUT = Path('/config')

def connections():
    m = pymysql.connect(host=os.environ['MYSQL_HOST'], port=int(os.getenv('MYSQL_PORT',3306)),
        user=os.getenv('MYSQL_USER','root'), password=os.environ['MYSQL_PASSWORD'],
        database=os.getenv('MYSQL_DATABASE','hxjm_sm'), client_flag=CLIENT.MULTI_STATEMENTS)
    p = psycopg.connect(host=os.environ['POSTGRES_HOST'], port=int(os.getenv('POSTGRES_PORT',5432)),
        user=os.getenv('POSTGRES_USER','root'), password=os.environ['POSTGRES_PASSWORD'],
        dbname=os.getenv('POSTGRES_DATABASE','hxjm'), autocommit=True)
    return m,p

def private(name, text):
    OUT.mkdir(parents=True,exist_ok=True)
    path=OUT/name
    with open(path,'w',opener=lambda p,f: os.open(p,f,0o600)) as f:f.write(text)
    path.chmod(0o600)

def camera_configuration():
    cameras=json.loads(Path('/input/cameras.json').read_text())
    if not isinstance(cameras,list) or not 1 <= len(cameras) <= 16:raise ValueError('Provide 1..16 cameras')
    namespace=uuid.uuid5(uuid.NAMESPACE_URL,os.environ['INSTANCE_NAMESPACE'])
    codes=set()
    for c in cameras:
        if not re.fullmatch('camera_[1-9][0-9]*',c['code']) or not c['url'].startswith('rtsp://') or c['code'] in codes:raise ValueError('Invalid/duplicate camera code or RTSP URL')
        codes.add(c['code']);c['source_id']=str(uuid.uuid5(namespace,c['code']));c['stream_id']=str(uuid.uuid5(namespace,c['code']+':raw'))
    return cameras

def render(cameras):
    token=os.environ['PIPELINE_TOKEN']
    if len(token)<24 or len(os.environ.get('STREAM_TOKEN',''))<24:raise ValueError('Provide independent PIPELINE_TOKEN and STREAM_TOKEN, each at least 24 characters')
    ops='activities.close activities.query assets.process assets.query assets.register assets.upload capabilities.describe capabilities.register events.query events.register feature_spaces.register features.register identities.associate identities.query identities.register instances.configure instances.query media.resolve queries.candidates queries.create queries.get queries.process queries.select reports.query reports.register result_types.register result_types.query results.query results.register samples.process samples.query samples.register search.execute sources.query sources.register streams.close streams.open tasks.get tasks.start tasks.finish tasks.submit tasks.complete tasks.fail tasks.heartbeat tracking.close'.split()
    backend={'hxjm':{'business':{'enabled':True,'storage-root':'/data','security':{'services':{'hxjm-pipeline':{'token':token,'operations':ops,'source-ids':[c['source_id'] for c in cameras]}}}}},'ruoyi':{'profile':'/data/uploads'},'smartmonitor':{'ai':{'launch-mode':'external','public-host':os.getenv('PUBLIC_HOST','127.0.0.1'),'live-port':int(os.getenv('MEDIA_HTTP_PORT','19389'))}}}
    backend['hxjm']['business']['execution']={
        'enabled':os.getenv('CAPABILITY_EXECUTOR_ENABLED','false').lower()=='true',
        'namespace':os.environ['INSTANCE_NAMESPACE'],
        'services':{'business':{
            name:{'url':'http://backend:8080/api/v1/business/'+path,'required-operation':permission,'credential-ref':'hxjm-pipeline'}
            for name,path,permission in [('events','events/query','events.query'),('reports','reports/search','reports.query')]}}
    }
    private('backend.yml',yaml.safe_dump(backend,sort_keys=False))
    # RTSP source credentials are private deployment configuration, never printed.
    media={'logDestinations':['stdout'],'api':True,'apiAddress':':'+os.getenv('MEDIA_API_PORT','10497'),'rtspAddress':':'+os.getenv('RTSP_PORT','19554'),'webrtcAddress':':'+os.getenv('MEDIA_HTTP_PORT','19389'),'authInternalUsers':[{'user':'any','pass':'','ips':[],'permissions':[{'action':'read'},{'action':'publish'},{'action':'api'}]}],'rtspTransports':['tcp'],'rtmp':False,'hls':False,'srt':False,'playback':False,'webrtcLocalUDPAddress':':'+os.getenv('MEDIA_ICE_PORT','19390'),'webrtcAdditionalHosts':[os.getenv('PUBLIC_HOST','127.0.0.1')],'pathDefaults':{'record':False},'paths':{'live/'+c['code']:{'source':c['url'],'rtspTransport':'tcp','sourceOnDemand':True} for c in cameras}}
    if os.getenv('MEDIA_RECORD_ENABLED','false').lower()=='true':
        media['pathDefaults'].update(record=True,recordPath='/recordings/%path/%Y-%m-%d/%H-%M-%S-%f',recordFormat='fmp4',recordSegmentDuration='1h',recordDeleteAfter='168h')
        for path in media['paths'].values():path['sourceOnDemand']=False
    if any(c['url'].rstrip('/').endswith('/test-input') for c in cameras):
        media['paths']['test-input']={'source':'publisher'}
    private('mediamtx.yml',yaml.safe_dump(media,sort_keys=False))
    private('ai-stream.yml',yaml.safe_dump({'mediamtx_url':os.getenv('MEDIA_RTSP_URL','rtsp://mediamtx:8554/live'),'control':{'enabled':True,'listen_host':'0.0.0.0','listen_port':int(os.getenv('STREAM_PORT','19590')),'token':os.environ['STREAM_TOKEN']},'streams':[],'ai_tasks_ipc':{},'task_templates':{}},sort_keys=False))
    private('sources.json',json.dumps(cameras,indent=2)+'\n')
    private('analysis.env','CAMERA_CODES='+','.join(c['code'] for c in cameras)+'\nANALYSIS_CAMERAS='+json.dumps({c['code']:os.getenv('MEDIA_RTSP_URL','rtsp://mediamtx:8554/live').rstrip('/')+'/'+c['code'] for c in cameras},separators=(',',':'))+'\nSOURCE_IDS='+json.dumps({c['code']:c['source_id'] for c in cameras},separators=(',',':'))+'\n')
    # Only this deployment's input identities; registration persists request IDs separately.
    private('bootstrap-input.json',json.dumps({'source_ids':{c['code']:c['source_id'] for c in cameras}}))

def check(m,p):
    manifest=json.loads((BASE/'schema-manifest.json').read_text())
    with m.cursor() as c:
        c.execute("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema=DATABASE()")
        mcols=set(c.fetchall())
    pcols=set(p.execute("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public'").fetchall())
    for database,actual in [('mysql',mcols),('postgres',pcols)]:
        missing=[t+'.'+col for t,cols in manifest[database].items() for col in cols if (t,col) not in actual]
        if missing:raise ValueError(database+' baseline mismatch: '+', '.join(missing[:8]))
    # Existing stable databases need not have our new deployment marker.
    if ('hxjm_deployment_version','version') in mcols:
        with m.cursor() as c:
            c.execute('SELECT version FROM hxjm_deployment_version');a=c.fetchone()[0]
        if a!=VERSION:raise ValueError('MySQL version mismatch')
    if ('hxjm_deployment_version','version') in pcols:
        if p.execute('SELECT version FROM public.hxjm_deployment_version').fetchone()[0]!=VERSION:raise ValueError('PostgreSQL version mismatch')
    print('Database schema baseline matches',VERSION)

def initialize(m,p,cameras):
    if len(os.getenv('INIT_ADMIN_PASSWORD',''))<12:raise ValueError('INIT_ADMIN_PASSWORD must be at least 12 characters')
    # Check BOTH targets before any schema write. Never adopt or erase an existing schema.
    with m.cursor() as c:
        c.execute('SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()')
        if c.fetchone()[0]:raise ValueError('MySQL is not empty; initialization refused')
    if p.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'").fetchone()[0]:raise ValueError('PostgreSQL is not empty; initialization refused')
    with m.cursor() as c:
        c.execute((BASE/'mysql-schema.sql').read_text())
        while c.nextset():pass
        c.execute('INSERT INTO sys_user(user_id,user_name,nick_name,password,status,del_flag) VALUES (1,%s,%s,%s,%s,%s)',('admin','Deployment administrator',bcrypt.hashpw(os.environ['INIT_ADMIN_PASSWORD'].encode(),bcrypt.gensalt()).decode(),'0','0'))
        c.execute('CREATE TABLE hxjm_deployment_version(version varchar(64) PRIMARY KEY)')
        c.execute('INSERT INTO hxjm_deployment_version VALUES (%s)',(VERSION,))
        for cam in cameras:
            c.execute('INSERT INTO ba_machine(machine_id,machine_code,machine_name,video_url,status,isvalid) VALUES (%s,%s,%s,%s,1,1)',(int(cam['code'].split('_')[1]),cam['code'],cam.get('name',cam['code']),cam['url']))
    m.commit()
    with p.transaction():
        p.execute((BASE/'postgres-schema.sql').read_text(),prepare=False)
        for cam in cameras:
            p.execute('INSERT INTO public.camera(id,camera_code,name,stream_uri,timezone) VALUES (%s,%s,%s,%s,%s)',(cam['source_id'],cam['code'],cam.get('name',cam['code']),cam['url'],'Asia/Shanghai'))
            p.execute("INSERT INTO public.camera_stream(id,camera_id,stream_name,task_type,is_active) VALUES (%s,%s,%s,'raw',true)",(cam['stream_id'],cam['source_id'],'live/'+cam['code']))
        p.execute('CREATE TABLE public.hxjm_deployment_version(version text PRIMARY KEY)')
        p.execute('INSERT INTO public.hxjm_deployment_version VALUES (%s)',(VERSION,))
    check(m,p)

if __name__=='__main__':
    try:
        action=sys.argv[1]
        if action=='render':render(camera_configuration())
        elif action in ['initialize','check']:
            m,p=connections()
            try:
                if action=='initialize':initialize(m,p,camera_configuration())
                else:check(m,p)
            finally:m.close();p.close()
        elif action=='register':
            import subprocess
            env=dict(os.environ,HXJM_PIPELINE_TOKEN=os.environ['PIPELINE_TOKEN'])
            subprocess.run([sys.executable,str(BASE/'register.py'),'--state','/config/business.json','--base-url',os.environ['PIPELINE_BACKEND_URL'].rstrip('/')+'/api/v1/business','--feature-url',os.environ['PIPELINE_REID_URL']],env=env,check=True)
        else:raise ValueError('Use render, initialize, check, or register')
    except Exception as e:
        # Do not include credentials/SQL/connection strings from driver exceptions.
        print('Deployment initialization failed:',str(e) if isinstance(e,ValueError) else type(e).__name__,file=sys.stderr)
        sys.exit(1)
