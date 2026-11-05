"""Explicit empty-database initialization, version check and configuration rendering."""
import json
import os
from pathlib import Path
import re
import sys
import uuid
import schema

BASE = Path(__file__).parent
OUT = Path('/config')

def connections():
    import pymysql
    from pymysql.constants import CLIENT
    import psycopg
    m = pymysql.connect(host=os.environ['MYSQL_HOST'], port=int(os.getenv('MYSQL_PORT',3306)),
        user=os.getenv('MYSQL_USER','root'), password=os.environ['MYSQL_PASSWORD'],
        database=os.environ['MYSQL_DATABASE'], charset='utf8mb4', client_flag=CLIENT.MULTI_STATEMENTS)
    try:
        p = psycopg.connect(host=os.environ['POSTGRES_HOST'], port=int(os.getenv('POSTGRES_PORT',5432)),
            user=os.getenv('POSTGRES_USER','root'), password=os.environ['POSTGRES_PASSWORD'],
            dbname=os.environ['POSTGRES_DATABASE'], autocommit=True)
    except Exception:
        m.close()
        raise
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
    import yaml
    token=os.environ['PIPELINE_TOKEN']
    if len(token)<24 or len(os.environ.get('STREAM_TOKEN',''))<24:raise ValueError('Provide independent PIPELINE_TOKEN and STREAM_TOKEN, each at least 24 characters')
    ops='activities.close activities.query assets.process assets.query assets.register assets.upload capabilities.describe capabilities.register events.query events.register feature_spaces.register features.register identities.associate identities.query identities.register instances.configure instances.query media.resolve queries.candidates queries.create queries.get queries.process queries.select reports.query reports.register result_types.register result_types.query results.query results.register samples.process samples.query samples.register search.execute sources.query sources.register streams.close streams.open tasks.get tasks.start tasks.finish tasks.submit tasks.complete tasks.fail tasks.heartbeat tracklets.query tracking.close'.split()
    backend={'hxjm':{'business':{'enabled':True,'storage-root':'/data','security':{'services':{'hxjm-pipeline':{'token':token,'operations':ops,'source-ids':[c['source_id'] for c in cameras]}}}}},'ruoyi':{'profile':'/data/uploads'},'smartmonitor':{'ai':{'public-host':os.getenv('PUBLIC_HOST','127.0.0.1'),'live-port':int(os.getenv('MEDIA_HTTP_PORT','19389'))}}}
    backend['hxjm']['business']['execution']={
        'enabled':os.getenv('CAPABILITY_EXECUTOR_ENABLED','false').lower()=='true',
        'namespace':os.environ['INSTANCE_NAMESPACE'],
        'services':{'business':{
            name:{'url':'http://backend:8080/api/v1/business/'+path,'required-operation':permission,'credential-ref':'hxjm-pipeline'}
            for name,path,permission in [('events','events/query','events.query'),('reports','reports/search','reports.query'),('identities','identities/query','identities.query'),('tracklets','tracklets/query','tracklets.query')]}}
    }
    mode=os.getenv('CLEANUP_MODE','disabled')
    if mode not in ('disabled','simulation','m20'):raise ValueError('CLEANUP_MODE must be disabled, simulation or m20')
    routes=json.loads(os.getenv('CLEANUP_SOURCE_ROUTES','{}'))
    if not isinstance(routes,dict) or any(k not in {c['source_id'] for c in cameras} or v not in ('route1','route2','route3','route4') for k,v in routes.items()):raise ValueError('Provide explicit configured source UUID -> route mapping')
    backend['hxjm']['business']['cleanup']={'enabled':mode!='disabled','routes':routes}
    if mode!='disabled':
        endpoint='mock://local' if mode=='simulation' else os.environ['M20_CONTROL_URL']
        backend['hxjm']['business']['execution']['services']['robot-dog']={'cleanup':{'url':endpoint,'adapter':'m20_mock' if mode=='simulation' else 'm20_route','required-operation':'cleanup.execute','credential-ref':'hxjm-pipeline'}}
    ops.extend(['cleanup.execute','cleanup.submit'])
    gallery_url = os.getenv('GALLERY_BUSINESS_URL', '').rstrip('/')
    if gallery_url:
        backend['hxjm']['business']['execution']['services']['gallery-business'] = {
            name: {'url': gallery_url + '/api/v1/business/gallery/' + name,
                   'required-operation': 'identities.query', 'credential-ref': 'hxjm-pipeline',
                   'response-timeout-ms': 30000, 'max-response-bytes': 10485760}
            for name in ('image', 'screenshot', 'description', 'select')}
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
    schema.check({'mysql':m,'postgres':p})

def initialize(m,p,cameras):
    import bcrypt
    if len(os.getenv('INIT_ADMIN_PASSWORD',''))<12:raise ValueError('INIT_ADMIN_PASSWORD must be at least 12 characters')
    # Check BOTH targets before any schema write. Never adopt or erase an existing schema.
    with m.cursor() as c:
        c.execute('SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()')
        if c.fetchone()[0]:raise ValueError('MySQL is not empty; initialization refused')
    if p.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'").fetchone()[0]:raise ValueError('PostgreSQL is not empty; initialization refused')
    schema.apply_pending(m,'mysql',fresh=True)
    schema.apply_pending(p,'postgres',fresh=True)
    with m.cursor() as c:
        c.execute('INSERT INTO sys_user(user_id,user_name,nick_name,password,status,del_flag) VALUES (1,%s,%s,%s,%s,%s)',('admin','Deployment administrator',bcrypt.hashpw(os.environ['INIT_ADMIN_PASSWORD'].encode(),bcrypt.gensalt()).decode(),'0','0'))
        for cam in cameras:
            c.execute('INSERT INTO ba_machine(machine_id,machine_code,machine_name,video_url,status,isvalid) VALUES (%s,%s,%s,%s,1,1)',(int(cam['code'].split('_')[1]),cam['code'],cam.get('name',cam['code']),cam['url']))
    m.commit()
    with p.transaction():
        for cam in cameras:
            p.execute('INSERT INTO public.camera(id,camera_code,name,stream_uri,timezone,management_device_id,channel_code) VALUES (%s,%s,%s,%s,%s,%s,%s)',(cam['source_id'],cam['code'],cam.get('name',cam['code']),cam['url'],'Asia/Shanghai',int(cam['code'].split('_')[1]),'raw'))
            p.execute("INSERT INTO public.camera_stream(id,camera_id,stream_name,task_type,is_active) VALUES (%s,%s,%s,'raw',true)",(cam['stream_id'],cam['source_id'],'live/'+cam['code']))
    check(m,p)

def rebuild(m,p,cameras,confirmation):
    # The caller must verify container ownership/mounts before supplying this explicit opt-in.
    if os.getenv('HXJM_DATABASE_ENV') != 'isolated-local':
        raise ValueError('Rebuild requires HXJM_DATABASE_ENV=isolated-local')
    names = [os.environ['MYSQL_DATABASE'], os.environ['POSTGRES_DATABASE']]
    hosts = [os.environ['MYSQL_HOST'], os.environ['POSTGRES_HOST']]
    if any(not re.fullmatch(r'hxjm_[a-zA-Z0-9_]+', name) for name in names):
        raise ValueError('Rebuild only accepts explicitly named hxjm_* development databases')
    if hosts != ['mysql','postgres'] and hosts != ['127.0.0.1','127.0.0.1']:
        raise ValueError('Rebuild refuses external endpoints')
    expected = 'mysql@%s:%s/%s;postgres@%s:%s/%s' % (
        hosts[0],os.getenv('MYSQL_PORT','3306'),names[0],
        hosts[1],os.getenv('POSTGRES_PORT','5432'),names[1])
    if confirmation != expected:
        raise ValueError('Supply --confirm with both exact targets: ' + expected)
    if len(os.getenv('INIT_ADMIN_PASSWORD','')) < 12:
        raise ValueError('INIT_ADMIN_PASSWORD must be at least 12 characters')
    with m.cursor() as c:
        c.execute('SELECT DATABASE()')
        if c.fetchone()[0] != names[0]:raise ValueError('MySQL connected database differs')
    if p.execute('SELECT current_database()').fetchone()[0] != names[1]:
        raise ValueError('PostgreSQL connected database differs')
    extra=p.execute("SELECT nspname FROM pg_namespace WHERE nspname NOT IN ('public','information_schema') AND nspname NOT LIKE 'pg_%'").fetchall()
    if extra:raise ValueError('PostgreSQL has additional schemas; rebuild refused')
    print('Rebuilding verified explicit development targets:', expected)
    with m.cursor() as c:
        c.execute('DROP DATABASE `'+names[0]+'`')
        c.execute('CREATE DATABASE `'+names[0]+'` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci')
        c.execute('USE `'+names[0]+'`')
    with p.transaction():
        p.execute('DROP SCHEMA public CASCADE')
        p.execute('CREATE SCHEMA public')
    initialize(m,p,cameras)

if __name__=='__main__':
    try:
        action=sys.argv[1]
        if action=='plan':
            print(json.dumps({db:[{'version':v,'checksum':c} for v,c,_ in schema.migrations(db)] for db in ('mysql','postgres')},indent=2))
        elif action=='render':render(camera_configuration())
        elif action in ['initialize','check','upgrade','rebuild']:
            m,p=connections()
            try:
                if action=='initialize':initialize(m,p,camera_configuration())
                elif action=='rebuild':
                    import argparse
                    parser=argparse.ArgumentParser()
                    parser.add_argument('--confirm',required=True)
                    rebuild(m,p,camera_configuration(),parser.parse_args(sys.argv[2:]).confirm)
                elif action=='upgrade':schema.upgrade({'mysql':m,'postgres':p})
                else:check(m,p)
            finally:m.close();p.close()
        elif action=='register':
            import subprocess
            env=dict(os.environ,HXJM_PIPELINE_TOKEN=os.environ['PIPELINE_TOKEN'])
            contract_root=Path('/opt/contracts')
            configs=[contract_root/(name+'.json') for name in ('events','reports','identities','tracklets')]
            if os.getenv('GALLERY_BUSINESS_URL'):
                configs.extend(contract_root/('gallery-'+name+'.json') for name in ('image','screenshot','description','select'))
            if os.getenv('CLEANUP_MODE','disabled')!='disabled':configs.append(contract_root/'garbage-cleanup.json')
            command=[sys.executable,str(contract_root/'tools/register.py'),'--base-url',os.environ['PIPELINE_BACKEND_URL'].rstrip('/')+'/api/v1/business','--namespace',os.environ['INSTANCE_NAMESPACE']]
            if os.getenv('CLEANUP_MODE')=='simulation':command.append('--simulate-device')
            subprocess.run(command+[str(path) for path in configs],env=dict(env,CAPABILITY_SERVICE_ID='hxjm-pipeline',CAPABILITY_SERVICE_TOKEN=os.environ['PIPELINE_TOKEN']),check=True)
            subprocess.run([sys.executable,str(BASE/'register.py'),'--state','/config/business.json','--base-url',os.environ['PIPELINE_BACKEND_URL'].rstrip('/')+'/api/v1/business','--feature-url',os.environ['PIPELINE_REID_URL'],'--algorithm',os.getenv('VIDEO_ANALYSIS_ALGORITHM','botsort')],env=env,check=True)
        else:raise ValueError('Use plan, render, initialize, rebuild --confirm TARGETS, upgrade, check, or register')
    except Exception as e:
        # Do not include credentials/SQL/connection strings from driver exceptions.
        print('Deployment initialization failed:',str(e) if isinstance(e,ValueError) else type(e).__name__,file=sys.stderr)
        sys.exit(1)
