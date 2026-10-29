-- Run only after one of this directory's synthetic fixtures and the migration.
-- All validation writes and temporary helper functions are rolled back.
BEGIN;
SET LOCAL search_path = pg_catalog, public;
SET LOCAL statement_timeout = '30s';

CREATE FUNCTION pg_temp.assert_true(ok boolean, message text) RETURNS void
LANGUAGE plpgsql AS $assert$
BEGIN
  IF ok IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'stage1 verification failed: %',message;
  END IF;
END
$assert$;

CREATE FUNCTION pg_temp.expect_sqlstate(command text, expected text) RETURNS void
LANGUAGE plpgsql AS $expect$
BEGIN
  BEGIN
    EXECUTE command;
  EXCEPTION WHEN OTHERS THEN
    IF SQLSTATE<>expected THEN
      RAISE;
    END IF;
    RETURN;
  END;
  RAISE EXCEPTION 'stage1 verification expected SQLSTATE % for: %',expected,command;
END
$expect$;

SELECT pg_temp.assert_true((SELECT count(*)=17
  FROM unnest(ARRAY['stream_session','capability_definition','capability_instance','result_type',
    'business_task','task_attempt','request_deduplication','outbox_event','tracking_context',
    'result_set','result_selection','input_frame','analysis_frame','detection_observation',
    'algorithm_result','processing_coverage','asset_reference']) AS names(name)
  WHERE to_regclass('public.' || name) IS NOT NULL),'all seventeen tables exist');
SELECT pg_temp.assert_true((SELECT NOT attnotnull FROM pg_attribute
  WHERE attrelid='public.media_asset'::regclass AND attname='play_url'),'play_url is nullable');
SELECT pg_temp.assert_true((SELECT NOT attnotnull AND NOT atthasdef FROM pg_attribute
  WHERE attrelid='public.media_asset'::regclass AND attname='state'),'legacy asset state has no default');
SELECT pg_temp.assert_true((SELECT NOT attnotnull FROM pg_attribute
  WHERE attrelid='public.tracklet'::regclass AND attname='expires_at'),'legacy track expiry is nullable');
SELECT pg_temp.assert_true((SELECT count(*)=2 FROM pg_attribute
  WHERE attrelid IN ('public.media_asset'::regclass,'public.tracklet'::regclass)
    AND attname='stream_id' AND attnotnull),'legacy stream fields remain NOT NULL');
SELECT pg_temp.assert_true((SELECT confdeltype='c' FROM pg_constraint
  WHERE conrelid='public.camera_stream'::regclass AND conname='camera_stream_camera_id_fkey'),
  'legacy camera_stream deletion behavior is preserved');
SELECT pg_temp.assert_true((SELECT count(*)=2 FROM pg_constraint
  WHERE conrelid='public.asset_reference'::regclass AND contype='f'),
  'asset references only depend on assets and algorithm results at this stage');
SELECT pg_temp.assert_true((SELECT state IS NULL AND source_id IS NULL
  AND oss_key='recordings/fixture/legacy.mp4' FROM public.media_asset
  WHERE id='30000000-0000-4000-8000-000000000001'),'legacy asset values survive');
SELECT pg_temp.assert_true((SELECT expires_at IS NULL AND source_id IS NULL
  AND repr_embedding='[1,0,0]'::public.vector FROM public.tracklet
  WHERE id='40000000-0000-4000-8000-000000000001'),'legacy track values survive');

-- The same pre-migration column lists still work for both real legacy stream types.
DO $legacy_writers$
DECLARE
  stream_value text;
BEGIN
  SELECT stream_id::text INTO STRICT stream_value FROM public.media_asset
    WHERE id='30000000-0000-4000-8000-000000000001';
  EXECUTE format('INSERT INTO public.media_asset
    (id,stream_id,asset_type,start_ts,duration_ms,play_url,oss_key,content_type)
    VALUES (%L,%L,%L,%L,60000,%L,%L,%L)',
    '30000000-0000-4000-8000-000000000009',stream_value,'segment','2026-10-26T00:01:00Z',
    'https://media.example.invalid/legacy/new','recordings/fixture/legacy-new.mp4','video/mp4');
  EXECUTE format('INSERT INTO public.tracklet(id,stream_id,start_ts,cls_name)
    VALUES (%L,%L,%L,%L)',
    '40000000-0000-4000-8000-000000000009',stream_value,'2026-10-26T00:01:00Z','person');
END
$legacy_writers$;
SELECT pg_temp.assert_true((SELECT state IS NULL FROM public.media_asset
  WHERE id='30000000-0000-4000-8000-000000000009'),'legacy writer does not invent a new asset state');

INSERT INTO public.capability_definition(capability_code,display_name,object_types,input_kinds)
VALUES ('tracking','fixture tracking',ARRAY['person'],ARRAY['live_video']);
INSERT INTO public.capability_instance
  (id,capability_code,instance_key,implementation_code,implementation_version,source_ids,service_ref)
VALUES ('50000000-0000-4000-8000-000000000002','tracking','fixture-primary','botsort','fixture-v1',
  ARRAY['10000000-0000-4000-8000-000000000001'::uuid],'algorithms/fixture-primary');
INSERT INTO public.result_type(type_code,schema_version,json_schema)
VALUES ('detection.frame','1','{"type":"object"}'),('fixture.output','1','{"type":"object"}');
INSERT INTO public.stream_session
  (id,source_id,camera_stream_id,session_key,started_at,time_origin_at,time_basis,
   source_timezone,source_width,source_height,expires_at)
VALUES ('50000000-0000-4000-8000-000000000001','10000000-0000-4000-8000-000000000001',
  '20000000-0000-4000-8000-000000000001','fixture-session','2026-10-26T00:00:00Z',
  '2026-10-26T00:00:00Z','ingest_clock','Asia/Shanghai',1920,1080,'2026-11-02T00:01:00Z');
INSERT INTO public.business_task
  (task_id,task_kind,business_key,task_mode,last_input_at,actor_key,capability_code,state,
   input_json,input_digest,generation,expires_at)
VALUES ('60000000-0000-4000-8000-000000000001','tracking','fixture-session:tracking','continuous',
  '2026-10-26T00:00:03Z','service:fixture','tracking','running',
  '{"schema_version":"1","source_id":"10000000-0000-4000-8000-000000000001"}',repeat('a',64),1,
  '2026-11-02T00:00:03Z');
INSERT INTO public.task_attempt
  (run_id,task_id,generation,state,implementation_code,implementation_version,parameters_json,expires_at)
VALUES ('60000000-0000-4000-8000-000000000002','60000000-0000-4000-8000-000000000001',1,
  'running','botsort','fixture-v1',
  '{"schema_version":"1","instance_id":"50000000-0000-4000-8000-000000000002","instance_revision":1,"service_ref":"algorithms/fixture-primary","implementation_code":"botsort","implementation_version":"fixture-v1","parameters":{}}',
  '2026-11-02T00:00:03Z');
UPDATE public.business_task SET current_run_id='60000000-0000-4000-8000-000000000002'
  WHERE task_id='60000000-0000-4000-8000-000000000001';
INSERT INTO public.request_deduplication
  (actor_key,operation,request_id,request_digest,state,task_id,response_json,expires_at)
VALUES ('service:fixture','results.register','fixture-request',repeat('b',64),'completed',
  '60000000-0000-4000-8000-000000000001','{"accepted":true}','2026-11-02T00:00:03Z');
INSERT INTO public.tracking_context
  (id,stream_session_id,run_id,context_key,source_width,source_height,started_at,expires_at)
VALUES ('60000000-0000-4000-8000-000000000003','50000000-0000-4000-8000-000000000001',
  '60000000-0000-4000-8000-000000000002','fixture-context',1920,1080,
  '2026-10-26T00:00:00Z','2026-11-02T00:00:03Z');
INSERT INTO public.result_set
  (id,run_id,source_id,stream_session_id,capability_code,set_key,generation,state,expires_at)
VALUES ('60000000-0000-4000-8000-000000000004','60000000-0000-4000-8000-000000000002',
  '10000000-0000-4000-8000-000000000001','50000000-0000-4000-8000-000000000001',
  'tracking','fixture-result-set',1,'ready','2026-11-02T00:00:03Z');

-- Create new video and large-output assets without altering the legacy stream representation.
INSERT INTO public.media_asset
  (id,stream_id,asset_type,start_ts,duration_ms,play_url,source_id,stream_session_id,
   producer_key,storage_key,byte_size,checksum_sha256,state,expires_at)
SELECT '30000000-0000-4000-8000-000000000002',stream_id,'segment','2026-10-26T00:00:00Z',
  60000,NULL,'10000000-0000-4000-8000-000000000001','50000000-0000-4000-8000-000000000001',
  'fixture:recording','recordings/fixture/new.mp4',100,repeat('c',64),'available','2026-11-02T00:01:00Z'
FROM public.media_asset WHERE id='30000000-0000-4000-8000-000000000001';
INSERT INTO public.media_asset
  (id,stream_id,asset_type,start_ts,duration_ms,play_url,source_id,stream_session_id,
   producer_key,storage_key,byte_size,checksum_sha256,state,expires_at)
SELECT '30000000-0000-4000-8000-000000000003',stream_id,'algorithm_output','2026-10-26T00:00:01Z',
  0,NULL,'10000000-0000-4000-8000-000000000001','50000000-0000-4000-8000-000000000001',
  'fixture:output','outputs/fixture/one.json',2,repeat('d',64),'available','2026-11-02T00:00:01Z'
FROM public.media_asset WHERE id='30000000-0000-4000-8000-000000000001';
INSERT INTO public.tracklet
  (id,stream_id,start_ts,cls_name,source_id,stream_session_id,tracking_context_id,local_track_id,
   origin_result_set_id,first_observed_at,last_observed_at,expires_at)
SELECT '40000000-0000-4000-8000-000000000002',stream_id,'2026-10-26T00:00:01Z','person',
  '10000000-0000-4000-8000-000000000001','50000000-0000-4000-8000-000000000001',
  '60000000-0000-4000-8000-000000000003',7,'60000000-0000-4000-8000-000000000004',
  '2026-10-26T00:00:01Z','2026-10-26T00:00:01Z','2026-11-02T00:00:01Z'
FROM public.tracklet WHERE id='40000000-0000-4000-8000-000000000001';

INSERT INTO public.input_frame
  (id,stream_session_id,frame_seq,occurred_at,stream_pts_ms,media_asset_id,media_pts_ms,
   time_quality,width,height,expires_at)
SELECT ('70000000-0000-4000-8000-' || lpad(n::text,12,'0'))::uuid,
  '50000000-0000-4000-8000-000000000001',n,'2026-10-26T00:00:00Z'::timestamptz+n*interval '1s',
  n*1000,'30000000-0000-4000-8000-000000000002',n*1000,'ingest_estimated',1920,1080,
  '2026-11-02T00:00:00Z'::timestamptz+n*interval '1s' FROM generate_series(1,3) AS series(n);
INSERT INTO public.analysis_frame
  (id,result_set_id,input_frame_id,producer_result_key,target_count,payload_digest,expires_at)
SELECT ('71000000-0000-4000-8000-' || lpad(n::text,12,'0'))::uuid,
  '60000000-0000-4000-8000-000000000004',('70000000-0000-4000-8000-' || lpad(n::text,12,'0'))::uuid,
  'fixture-result-' || n,CASE WHEN n=3 THEN 0 ELSE 1 END,repeat('e',64),
  '2026-11-02T00:00:00Z'::timestamptz+n*interval '1s' FROM generate_series(1,3) AS series(n);
INSERT INTO public.detection_observation
  (analysis_frame_id,target_index,tracklet_id,object_type,class_code,confidence,observation_kind,
   bbox_left,bbox_top,bbox_right,bbox_bottom,expires_at)
VALUES ('71000000-0000-4000-8000-000000000001',0,'40000000-0000-4000-8000-000000000002',
  'person','person',0.95,'observed',0.1,0.2,0.3,0.8,'2026-11-02T00:00:01Z'),
 ('71000000-0000-4000-8000-000000000002',0,'40000000-0000-4000-8000-000000000002',
  'person','person',NULL,'predicted',0.1,0.2,0.3,0.8,'2026-11-02T00:00:02Z');
INSERT INTO public.algorithm_result
  (id,result_set_id,producer_result_key,result_type,schema_version,input_frame_id,tracklet_id,
   start_at,payload_asset_id,payload_digest,expires_at)
VALUES ('80000000-0000-4000-8000-000000000001','60000000-0000-4000-8000-000000000004',
  'fixture-large-output','fixture.output','1','70000000-0000-4000-8000-000000000001',
  '40000000-0000-4000-8000-000000000002','2026-10-26T00:00:01Z',
  '30000000-0000-4000-8000-000000000003',repeat('d',64),'2026-11-02T00:00:01Z');
INSERT INTO public.asset_reference(asset_id,result_id,retain_until)
VALUES ('30000000-0000-4000-8000-000000000003','80000000-0000-4000-8000-000000000001',
  '2026-11-02T00:00:01Z');
INSERT INTO public.processing_coverage
  (id,source_id,stream_session_id,run_id,result_set_id,stage,coverage_key,start_at,end_at,
   status,analyzed_frame_count,saved_frame_count,expires_at)
VALUES ('90000000-0000-4000-8000-000000000001','10000000-0000-4000-8000-000000000001',
  '50000000-0000-4000-8000-000000000001','60000000-0000-4000-8000-000000000002',
  '60000000-0000-4000-8000-000000000004','registration','fixture-coverage',
  '2026-10-26T00:00:00Z','2026-10-26T00:00:04Z','complete',3,3,'2026-11-02T00:00:03Z');
INSERT INTO public.result_selection
  (source_id,capability_code,range_start,range_end,result_set_id,generation,expires_at)
VALUES ('10000000-0000-4000-8000-000000000001','tracking','2026-10-26T00:00:00Z',
  '2026-10-26T00:00:04Z','60000000-0000-4000-8000-000000000004',1,'2026-11-02T00:00:03Z');
INSERT INTO public.outbox_event
  (event_type,aggregate_type,aggregate_id,aggregate_revision,payload_json,expires_at)
VALUES ('results.registered','result_set','60000000-0000-4000-8000-000000000004',1,
  '{"schema_version":"1","frame_count":3}','2026-11-02T00:00:03Z');

SELECT pg_temp.assert_true(NOT EXISTS (
  SELECT FROM public.analysis_frame f LEFT JOIN public.detection_observation o ON o.analysis_frame_id=f.id
  GROUP BY f.id HAVING f.target_count<>count(o.id)),'every frame has its complete target set, including zero targets');
SELECT pg_temp.assert_true((SELECT NOT closed FROM public.processing_coverage
  WHERE id='90000000-0000-4000-8000-000000000001'),'coverage starts open');
UPDATE public.processing_coverage SET closed=true,revision=revision+1
  WHERE id='90000000-0000-4000-8000-000000000001' AND revision=1;
SELECT pg_temp.assert_true((SELECT closed AND revision=2 FROM public.processing_coverage
  WHERE id='90000000-0000-4000-8000-000000000001'),'coverage can be closed with an explicit revision');

SELECT pg_temp.expect_sqlstate($q$
  INSERT INTO public.input_frame(stream_session_id,frame_seq,occurred_at,time_quality,width,height,expires_at)
  VALUES ('50000000-0000-4000-8000-000000000001',1,'2026-10-26T00:00:01Z','ingest_estimated',1920,1080,'2026-11-02T00:00:01Z')
$q$,'23505');
SELECT pg_temp.expect_sqlstate($q$
  INSERT INTO public.tracklet(stream_id,start_ts,cls_name,tracking_context_id,local_track_id)
  SELECT stream_id,start_ts,cls_name,tracking_context_id,local_track_id FROM public.tracklet
  WHERE id='40000000-0000-4000-8000-000000000002'
$q$,'23505');
SELECT pg_temp.expect_sqlstate($q$
  UPDATE public.detection_observation SET confidence=NULL WHERE observation_kind='observed'
$q$,'23514');
SELECT pg_temp.expect_sqlstate($q$
  UPDATE public.detection_observation SET bbox_right=2
$q$,'23514');
SELECT pg_temp.expect_sqlstate($q$
  UPDATE public.processing_coverage SET saved_frame_count=4
$q$,'23514');
SELECT pg_temp.expect_sqlstate($q$
  UPDATE public.processing_coverage SET revision=0
$q$,'23514');
SELECT pg_temp.expect_sqlstate($q$
  INSERT INTO public.processing_coverage(source_id,stage,coverage_key,start_at,end_at,status,expires_at)
  SELECT source_id,stage,coverage_key,start_at,end_at,status,expires_at FROM public.processing_coverage
$q$,'23505');
SELECT pg_temp.expect_sqlstate($q$
  INSERT INTO public.request_deduplication(actor_key,operation,request_id,request_digest,expires_at)
  VALUES ('service:fixture','results.register','fixture-request',repeat('f',64),'2026-11-02T00:00:03Z')
$q$,'23505');
SELECT pg_temp.expect_sqlstate($q$
  UPDATE public.media_asset SET producer_key='fixture:recording'
  WHERE id='30000000-0000-4000-8000-000000000003'
$q$,'23505');
SELECT pg_temp.expect_sqlstate($q$
  UPDATE public.media_asset SET checksum_sha256=NULL
  WHERE id='30000000-0000-4000-8000-000000000003'
$q$,'23514');
SELECT pg_temp.expect_sqlstate($q$
  INSERT INTO public.asset_reference(asset_id,sample_id,retain_until)
  VALUES ('30000000-0000-4000-8000-000000000003','80000000-0000-4000-8000-000000000009','2026-11-02T00:00:01Z')
$q$,'23514');
SELECT pg_temp.expect_sqlstate($q$
  UPDATE public.asset_reference SET retain_until=NULL
$q$,'23502');
SELECT pg_temp.expect_sqlstate($q$
  UPDATE public.asset_reference SET result_id='80000000-0000-4000-8000-000000000009'
$q$,'23503');
SELECT pg_temp.expect_sqlstate($q$
  INSERT INTO public.result_selection(source_id,capability_code,range_start,range_end,result_set_id,generation,expires_at)
  VALUES ('10000000-0000-4000-8000-000000000001','tracking','2026-10-26T00:00:02Z',
    '2026-10-26T00:00:05Z','60000000-0000-4000-8000-000000000004',1,'2026-11-02T00:00:03Z')
$q$,'23P01');
-- Adjacent ranges do not overlap: the upper bound is exclusive.
INSERT INTO public.result_selection(source_id,capability_code,range_start,range_end,result_set_id,generation,expires_at)
VALUES ('10000000-0000-4000-8000-000000000001','tracking','2026-10-26T00:00:04Z',
  '2026-10-26T00:00:05Z','60000000-0000-4000-8000-000000000004',1,'2026-11-02T00:00:03Z');

-- An invalid target rolls its whole frame write back, without moving saved coverage.
SELECT pg_temp.expect_sqlstate($q$
  DO $failed_frame$
  BEGIN
    INSERT INTO public.input_frame(id,stream_session_id,frame_seq,occurred_at,time_quality,width,height,expires_at)
    VALUES ('70000000-0000-4000-8000-000000000004','50000000-0000-4000-8000-000000000001',4,
      '2026-10-26T00:00:04Z','ingest_estimated',1920,1080,'2026-11-02T00:00:04Z');
    INSERT INTO public.analysis_frame(id,result_set_id,input_frame_id,producer_result_key,target_count,payload_digest,expires_at)
    VALUES ('71000000-0000-4000-8000-000000000004','60000000-0000-4000-8000-000000000004',
      '70000000-0000-4000-8000-000000000004','fixture-result-4',1,repeat('f',64),'2026-11-02T00:00:04Z');
    UPDATE public.processing_coverage SET analyzed_frame_count=4,saved_frame_count=4;
    INSERT INTO public.detection_observation(analysis_frame_id,target_index,object_type,class_code,confidence,
      observation_kind,bbox_left,bbox_top,bbox_right,bbox_bottom,expires_at)
    VALUES ('71000000-0000-4000-8000-000000000004',0,'person','person',0.9,
      'observed',0.1,0.2,2,0.8,'2026-11-02T00:00:04Z');
  END
  $failed_frame$;
$q$,'23514');
SELECT pg_temp.assert_true(NOT EXISTS (SELECT FROM public.input_frame
  WHERE id='70000000-0000-4000-8000-000000000004'),'failed frame leaves no input row');
SELECT pg_temp.assert_true(NOT EXISTS (SELECT FROM public.analysis_frame
  WHERE id='71000000-0000-4000-8000-000000000004'),'failed frame leaves no registered result');
SELECT pg_temp.assert_true((SELECT saved_frame_count=3 AND analyzed_frame_count=3
  FROM public.processing_coverage WHERE id='90000000-0000-4000-8000-000000000001'),
  'failed frame does not advance saved coverage');

SELECT 'stage1 normal-chain and constraint verification passed; test writes will be rolled back' AS result;
ROLLBACK;
