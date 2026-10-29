#!/usr/bin/env python3
"""Inspect, isolate-test, or apply the reviewed HXJM v0.2 device migration.

Uses the current checkout's configured PostgreSQL connection; never logs credentials.
No application services are started. Isolation tests clone schema only, not business data.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
import hashlib,json,os,re,subprocess,sys,uuid
from pathlib import Path
from urllib.parse import urlsplit
import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json
import yaml

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
MIGRATION=HERE/'005_device_integration.sql'
REPORTS=ROOT/'deploy/database-reports'
NEW=('device_registry','device_state_observation','device_task_binding','device_task_feedback')
TOUCHED=('camera','result_set','asset_reference')
CONTAINER='smartmonitor-postgres'

def need(ok,message):
 if not ok:raise RuntimeError(message)

def credentials():
 d=yaml.safe_load((ROOT/'SmartMonitor-wangzj/hxjm-admin/src/main/resources/application-druid.yml').read_text())['spring']['datasource']['druid']['slave']
 u=urlsplit(d['url'].removeprefix('jdbc:'))
 need((u.hostname,u.port or 5432,u.path)==('localhost',5432,'/postgres'),'Configured endpoint differs from reviewed localhost:5432/postgres; no changes made')
 return dict(host=u.hostname,port=u.port or 5432,dbname=u.path[1:],user=d['username'],password=d['password'],connect_timeout=10,application_name='hxjm-v02-device-migration')

def connect(database=None,autocommit=False):
 cfg=credentials()
 if database:cfg['dbname']=database
 c=psycopg2.connect(**cfg);c.autocommit=autocommit
 return c

@contextmanager
def session(database=None):
 c=connect(database)
 try:
  with c:yield c
 finally:c.close()

def rows(c,query,params=()):
 with c.cursor() as q:q.execute(query,params or None);return q.fetchall()

def execute(c,query,params=()):
 with c.cursor() as q:q.execute(query,params or None)

def save(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w') as f:
  os.fchmod(f.fileno(),0o600);json.dump(value,f,ensure_ascii=False,indent=2,default=str);f.write('\n')

def dump_schema():
 result=subprocess.run(['docker','exec',CONTAINER,'pg_dump','--schema-only','--no-owner','--no-privileges','-U',credentials()['user'],'-d','postgres'],capture_output=True)
 need(result.returncode==0,'Schema backup failed; raw output suppressed')
 need(b'CREATE TABLE public.camera' in result.stdout,'Unexpected schema dump')
 return result.stdout

def status(c):
 return {n:rows(c,'SELECT to_regclass(%s) IS NOT NULL',('public.'+n,))[0][0] for n in NEW}

def snapshot(c):
 out={}
 for name,omit in zip(TOUCHED,('device_id','device_task_binding_id','device_task_feedback_id')):
  out[name]=rows(c,sql.SQL("SELECT count(*),md5(coalesce(string_agg(md5((to_jsonb(t)-%s)::text),',' ORDER BY id),'')) FROM public.{} t").format(sql.Identifier(name)),(omit,))[0]
 out['result_type_existing']=rows(c,"SELECT type_code,schema_version,json_schema,max_inline_bytes,enabled,created_at FROM public.result_type WHERE type_code NOT IN ('behavior.assessment','garbage.detection') ORDER BY 1,2")
 return out

def inner_sql():
 text=MIGRATION.read_text()
 need(len(re.findall(r'^BEGIN;$',text,re.M))==1 and len(re.findall(r'^COMMIT;$',text,re.M))==1,'Unexpected transaction wrapper')
 return re.sub(r'^(BEGIN|COMMIT);\s*$','',text,flags=re.M)

def check_shape(c):
 text=MIGRATION.read_text()
 expected={}
 for name,body in re.findall(r'CREATE TABLE public\.(\w+) \((.*?)\n\);',text,re.S):
  cols={}
  for line in body.splitlines():
   m=re.match(r'  (\w+) (uuid|varchar\(\d+\)|bigint|boolean|jsonb|timestamptz\(6\)|char\(64\)|numeric\(5,2\)|text)(.*)',line)
   if m:
    typ=m[2].replace('varchar','character varying').replace('timestamptz(6)','timestamp(6) with time zone').replace('char(64)','character(64)')
    cols[m[1]]=(typ,'NOT NULL' in m[3])
  actual={r[0]:(r[1],r[2]) for r in rows(c,"SELECT attname,format_type(atttypid,atttypmod),attnotnull FROM pg_attribute WHERE attrelid=%s::regclass AND attnum>0 AND NOT attisdropped",('public.'+name,))}
  need(actual==cols,'Field/type/nullability mismatch: '+name);expected[name]=len(cols)
 for name,col in zip(TOUCHED,('device_id','device_task_binding_id','device_task_feedback_id')):
  need(rows(c,"SELECT format_type(atttypid,atttypmod),attnotnull FROM pg_attribute WHERE attrelid=%s::regclass AND attname=%s",('public.'+name,col))==[('uuid',False)],'Missing nullable association: '+name+'.'+col)
 names=set(re.findall(r'(?:CONSTRAINT|INDEX) (\w+)',text))
 actual=set(r[0] for r in rows(c,"SELECT conname FROM pg_constraint WHERE connamespace='public'::regnamespace UNION SELECT indexname FROM pg_indexes WHERE schemaname='public'"))
 need(names<=actual,'Missing constraints or indexes: '+str(names-actual))
 need(not rows(c,"SELECT 1 FROM pg_constraint WHERE conrelid='public.asset_reference'::regclass AND contype='c' AND regexp_replace(pg_get_expr(conbin,conrelid),'[[:space:]()]','','g')='num_nonnullssample_id,evidence_id,query_id,identity_id,message_id,result_id=1'"),'Old six-owner check remains')
 need(not rows(c,"SELECT conname FROM pg_constraint WHERE conrelid=ANY(%s::regclass[]) AND NOT convalidated",(['public.'+n for n in (*NEW,*TOUCHED)],)),'Unvalidated new constraints')
 need(rows(c,"SELECT count(*) FROM public.result_type WHERE type_code IN ('behavior.assessment','garbage.detection') AND schema_version='1' AND enabled")[0][0]==2,'Missing result contracts')
 for name,value in re.findall(r"VALUES \('([^']+)','1','(.*?)'::jsonb,1048576,true\)",text):
  actual=rows(c,"SELECT json_schema,max_inline_bytes,enabled FROM public.result_type WHERE type_code=%s AND schema_version='1'",(name,))
  need(actual==[(json.loads(value.replace("''", "'")),1048576,True)],'Result contract differs: '+name)
 return expected

def apply_transaction(c,commit=False):
 execute(c,"SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='90s'; SELECT pg_advisory_xact_lock(48584,5); LOCK TABLE public.camera,public.result_set,public.asset_reference,public.result_type IN ACCESS EXCLUSIVE MODE")
 before=snapshot(c)
 try:
  execute(c,inner_sql())
  shape=check_shape(c)
  need(snapshot(c)==before,'Existing business records changed; rollback required')
  if commit:c.commit()
  else:c.rollback()
  return shape
 except Exception:
  c.rollback();raise

def insert(c,table,values):
 execute(c,sql.SQL('INSERT INTO public.{} ({}) VALUES ({})').format(sql.Identifier(table),sql.SQL(',').join(map(sql.Identifier,values)),sql.SQL(',').join(sql.Placeholder()*len(values))),tuple(values.values()))

def exercise(c):
 now=datetime.now(timezone.utc);expiry=now+timedelta(days=7);uid=lambda:str(uuid.uuid4());digest='0'*64
 device,task,run,binding,feedback,source,asset,identity,resultset=[uid() for _ in range(9)]
 insert(c,'device_registry',dict(id=device,adapter_code='test_adapter',external_device_id='test_dog',device_type='robot_dog',display_name='isolated test'))
 insert(c,'business_task',dict(task_id=task,task_kind='device.patrol',actor_key='isolated-test',input_digest=digest,expires_at=expiry))
 insert(c,'task_attempt',dict(run_id=run,task_id=task,generation=1,implementation_code='isolated',implementation_version='1',expires_at=expiry))
 insert(c,'device_task_binding',dict(id=binding,task_id=task,run_id=run,device_id=device,dispatch_key='dispatch1',expires_at=expiry))
 insert(c,'device_state_observation',dict(device_id=device,producer_session_key='connection1',producer_message_key='message1',observed_at=now,received_at=now,time_quality='received_estimated',record_kind='change',state_code='standing',payload_digest=digest,task_id=task,run_id=run,expires_at=expiry))
 insert(c,'device_task_feedback',dict(id=feedback,binding_id=binding,feedback_key='feedback1',feedback_seq=1,occurred_at=now,received_at=now,feedback_type='completed',execution_state='succeeded',payload_digest=digest,expires_at=expiry))
 insert(c,'camera',dict(id=source,camera_code='isolated_device_camera',name='isolated',device_id=device))
 insert(c,'camera_stream',dict(camera_id=source,stream_name='isolated_device_stream',task_type='raw'))
 stream_type=rows(c,"SELECT udt_name FROM information_schema.columns WHERE table_schema='public' AND table_name='media_asset' AND column_name='stream_id'")[0][0]
 stream=rows(c,"SELECT id FROM public.camera_stream WHERE stream_name='isolated_device_stream'")[0][0] if stream_type=='uuid' else 'isolated_device_stream'
 insert(c,'media_asset',dict(id=asset,stream_id=stream,asset_type='snapshot',start_ts=now,duration_ms=0,play_url='test://not-a-real-file'))
 insert(c,'identity',dict(id=identity,identity_kind='registered',object_type='person',registered_at=now))
 # Preserve all old usage categories while allowing a new device-feedback owner.
 insert(c,'asset_reference',dict(asset_id=asset,identity_id=identity))
 insert(c,'asset_reference',dict(asset_id=asset,device_task_feedback_id=feedback,retain_until=expiry))
 insert(c,'capability_definition',dict(capability_code='isolated.behavior',display_name='isolated',object_types=['person'],input_kinds=['video']))
 insert(c,'result_set',dict(id=resultset,run_id=run,source_id=source,capability_code='isolated.behavior',set_key='set1',generation=1,device_task_binding_id=binding,expires_at=expiry))
 for decision in ['suspected','confirmed','rejected','insufficient_evidence']:
  insert(c,'algorithm_result',dict(result_set_id=resultset,producer_result_key=decision,result_type='behavior.assessment',schema_version='1',start_at=now,payload_json=Json(dict(behavior_type='fight',decision=decision,description='isolated')),payload_digest=digest,expires_at=expiry))
 insert(c,'algorithm_result',dict(result_set_id=resultset,producer_result_key='garbage',result_type='garbage.detection',schema_version='1',start_at=now,payload_json=Json(dict(has_target=False,targets=[])),payload_digest=digest,expires_at=expiry))
 tests=[]
 def rejected(label,code,fn):
  execute(c,'SAVEPOINT rejection')
  try:fn()
  except psycopg2.Error as e:
   execute(c,'ROLLBACK TO SAVEPOINT rejection');need(e.pgcode==code,label+': wrong SQLSTATE '+str(e.pgcode))
  else:
   execute(c,'ROLLBACK TO SAVEPOINT rejection');raise RuntimeError(label+': invalid write was accepted')
  execute(c,'RELEASE SAVEPOINT rejection');tests.append(label)
 rejected('device external key unique','23505',lambda:insert(c,'device_registry',dict(adapter_code='test_adapter',external_device_id='test_dog',device_type='robot_dog',display_name='duplicate')))
 rejected('device self parent forbidden','23514',lambda:execute(c,'UPDATE public.device_registry SET parent_device_id=id WHERE id=%s',(device,)))
 rejected('state producer message unique','23505',lambda:execute(c,"INSERT INTO public.device_state_observation SELECT gen_random_uuid(),device_id,producer_session_key,producer_message_key,observed_at,received_at,time_quality,record_kind,state_code,schema_version,payload_json,payload_digest,task_id,run_id,expires_at FROM public.device_state_observation LIMIT 1"))
 rejected('state task and run paired','23514',lambda:execute(c,'UPDATE public.device_state_observation SET run_id=NULL WHERE device_id=%s',(device,)))
 rejected('feedback key unique','23505',lambda:insert(c,'device_task_feedback',dict(binding_id=binding,feedback_key='feedback1',feedback_seq=2,occurred_at=now,received_at=now,feedback_type='artifact',payload_digest=digest,expires_at=expiry)))
 rejected('feedback sequence unique','23505',lambda:insert(c,'device_task_feedback',dict(binding_id=binding,feedback_key='different-key',feedback_seq=1,occurred_at=now,received_at=now,feedback_type='artifact',payload_digest=digest,expires_at=expiry)))
 rejected('completion state required','23514',lambda:execute(c,'UPDATE public.device_task_feedback SET execution_state=NULL WHERE id=%s',(feedback,)))
 rejected('feedback progress bounds','23514',lambda:execute(c,'UPDATE public.device_task_feedback SET progress=101 WHERE id=%s',(feedback,)))
 rejected('single device per run','23505',lambda:insert(c,'device_task_binding',dict(task_id=task,run_id=run,device_id=device,dispatch_key='different-dispatch',expires_at=expiry)))
 rejected('feedback asset relation unique','23505',lambda:insert(c,'asset_reference',dict(asset_id=asset,device_task_feedback_id=feedback,retain_until=expiry)))
 rejected('exactly one asset owner','23514',lambda:insert(c,'asset_reference',dict(asset_id=asset,device_task_feedback_id=feedback,identity_id=identity,retain_until=expiry)))
 rejected('asset owner required','23514',lambda:insert(c,'asset_reference',dict(asset_id=asset,retain_until=expiry)))
 rejected('feedback asset retention required','23514',lambda:insert(c,'asset_reference',dict(asset_id=asset,device_task_feedback_id=feedback)))
 rejected('referenced feedback cannot be deleted','23503',lambda:execute(c,'DELETE FROM public.device_task_feedback WHERE id=%s',(feedback,)))
 rejected('referenced device cannot be deleted','23503',lambda:execute(c,'DELETE FROM public.device_registry WHERE id=%s',(device,)))
 rejected('camera device FK','23503',lambda:execute(c,'UPDATE public.camera SET device_id=%s WHERE id=%s',(uid(),source)))
 need(rows(c,'SELECT count(*) FROM public.device_task_binding b JOIN public.device_task_feedback f ON f.binding_id=b.id JOIN public.asset_reference a ON a.device_task_feedback_id=f.id JOIN public.result_set s ON s.device_task_binding_id=b.id JOIN public.algorithm_result r ON r.result_set_id=s.id WHERE b.task_id=%s',(task,))[0][0]==5,'Task to files and five algorithm results traversal failed')
 tests+=['task-to-device-feedback-asset-results traversal','four behavior decisions without person or skeleton','garbage zero-target result','legacy identity asset reference still accepted']
 # A failed unit of work leaves neither the new feedback nor its task mutation.
 execute(c,'SAVEPOINT atomic_unit')
 try:
  execute(c,"UPDATE public.business_task SET state='succeeded' WHERE task_id=%s",(task,))
  insert(c,'device_task_feedback',dict(binding_id=binding,feedback_key='atomic-new',feedback_seq=3,occurred_at=now,received_at=now,feedback_type='artifact',payload_digest=digest,expires_at=expiry))
  insert(c,'asset_reference',dict(asset_id=asset,device_task_feedback_id=uid(),retain_until=expiry))
 except psycopg2.Error as e:
  need(e.pgcode=='23503','Atomic failure was not expected FK rejection');execute(c,'ROLLBACK TO SAVEPOINT atomic_unit')
 else:raise RuntimeError('Atomic test unexpectedly accepted invalid asset relation')
 need(rows(c,'SELECT state FROM public.business_task WHERE task_id=%s',(task,))[0][0]=='pending','Task rollback failed')
 need(rows(c,"SELECT count(*) FROM public.device_task_feedback WHERE feedback_key='atomic-new'")[0][0]==0,'Feedback rollback failed')
 tests.append('feedback-asset-task transaction rollback')
 c.rollback();return tests

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['inspect','verify','apply']);args=p.parse_args()
 REPORTS.mkdir(parents=True,exist_ok=True)
 digest=hashlib.sha256(MIGRATION.read_bytes()).hexdigest()
 report={'migration_sha256':digest,'endpoint':'localhost:5432/postgres','time':datetime.now(timezone.utc).isoformat(),'mode':args.mode}
 with session() as c:
  report['tables_before']=status(c)
  if args.mode=='inspect':
   report['constraints']=rows(c,"SELECT conname,pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='public.asset_reference'::regclass ORDER BY conname")
   print(json.dumps(report,ensure_ascii=False,indent=2));return
  if args.mode=='apply' and all(report['tables_before'].values()):
   report['shape']=check_shape(c);report['status']='already_applied';save(REPORTS/'005-inspect.json',report);print(json.dumps(report,ensure_ascii=False));return
  need(not any(report['tables_before'].values()),'Device schema partially or already exists; inspect before migration')
 if args.mode=='verify':
  dump=dump_schema();backup=REPORTS/'005-before-schema.sql'
  with os.fdopen(os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'wb') as f:f.write(dump)
  name='hxjm_device_verify_'+uuid.uuid4().hex[:12]
  admin=connect(autocommit=True)
  created=False
  try:
   execute(admin,sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(name)));created=True
   restored=subprocess.run(['docker','exec','-i',CONTAINER,'psql','-X','-v','ON_ERROR_STOP=1','-U',credentials()['user'],'-d',name],input=dump,capture_output=True)
   need(restored.returncode==0,'Isolated schema restore failed: '+restored.stderr.decode(errors='replace')[-1200:])
   with session(name) as c:
    # Prove constraint discovery does not depend on the legacy-generated name.
    old=rows(c,"SELECT conname FROM pg_constraint WHERE conrelid='public.asset_reference'::regclass AND contype='c' AND regexp_replace(pg_get_expr(conbin,conrelid),'[[:space:]()]','','g')='num_nonnullssample_id,evidence_id,query_id,identity_id,message_id,result_id=1'")
    need(len(old)==1,'Unrecognized legacy owner check')
    execute(c,sql.SQL('ALTER TABLE public.asset_reference RENAME CONSTRAINT {} TO isolated_renamed_legacy_owner').format(sql.Identifier(old[0][0])));c.commit()
    # First prove all DDL can roll back together.
    report['shape']=apply_transaction(c,False)
    need(not any(status(c).values()),'DDL rollback failed');c.rollback()
    report['ddl_rollback']='passed'
    apply_transaction(c,True)
    report['tests']=exercise(c)
    need(all(status(c).values()),'Schema missing after fixture rollback')
   report['status']='verified';report['isolation_database']=name
  finally:
   if created:execute(admin,sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
   admin.close()
  report['isolation_database_removed']=True
  save(REPORTS/'005-verify.json',report)
 else:
  proof=json.loads((REPORTS/'005-verify.json').read_text())
  need(proof.get('status')=='verified' and proof.get('migration_sha256')==digest,'Isolation verification for this exact SQL is required')
  # A fresh schema backup is retained immediately before the real transaction.
  backup=REPORTS/('005-before-apply-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.sql')
  dump=dump_schema()
  with os.fdopen(os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'wb') as f:f.write(dump)
  with session() as c:report['shape']=apply_transaction(c,True)
  with session() as c:check_shape(c)
  report.update(status='applied',commit_outcome='committed',schema_backup=str(backup),existing_rows='unchanged')
  save(REPORTS/'005-apply.json',report)
 print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
 try:main()
 except Exception as e:
  # PostgreSQL detail may contain business data; only print safe status and class.
  if isinstance(e,psycopg2.Error):print('Database operation failed; SQLSTATE='+str(e.pgcode)+'; '+str(e.diag.message_primary),file=sys.stderr)
  elif isinstance(e,RuntimeError):print(str(e),file=sys.stderr)
  else:print('Migration tool failed: '+type(e).__name__,file=sys.stderr)
  sys.exit(1)
