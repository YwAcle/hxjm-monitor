-- Only synthetic fixtures; validation data and temporary helpers are rolled back.
BEGIN;
SET LOCAL search_path = pg_catalog, public;
SET LOCAL statement_timeout = '30s';
CREATE FUNCTION pg_temp.assert_true(ok boolean, message text) RETURNS void
LANGUAGE plpgsql AS $assert$
BEGIN
  IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'stage2 verification failed: %',message; END IF;
END
$assert$;
CREATE FUNCTION pg_temp.expect_sqlstate(command text, expected text) RETURNS void
LANGUAGE plpgsql AS $expect$
BEGIN
  BEGIN EXECUTE command;
  EXCEPTION WHEN OTHERS THEN
    IF SQLSTATE<>expected THEN RAISE; END IF;
    RETURN;
  END;
  RAISE EXCEPTION 'stage2 verification expected SQLSTATE % for: %',expected,command;
END
$expect$;
SELECT pg_temp.assert_true((SELECT count(*)=15 FROM unnest(ARRAY[
 'identity','identity_link','track_identity_assignment','legacy_identity_map','sample',
 'feature_space','feature','feature_contribution','business_event','event_object_link',
 'evidence_reference','report_evidence_link','query_request','query_candidate','search_hit']) names(name)
 WHERE to_regclass('public.'||name) IS NOT NULL),'all fifteen new tables exist');
SELECT pg_temp.assert_true((SELECT NOT attnotnull FROM pg_attribute
 WHERE attrelid='public.media_asset'::regclass AND attname='stream_id'),'images can omit a stream');
SELECT pg_temp.assert_true((SELECT NOT attnotnull FROM pg_attribute
 WHERE attrelid='public.asset_reference'::regclass AND attname='retain_until'),'enrollment retention can be permanent');
SELECT pg_temp.assert_true((SELECT bool_and(NOT attnotnull AND NOT atthasdef) FROM pg_attribute
 WHERE attrelid='public.llm_report'::regclass AND attname IN
 ('subject_kind','subject_id','event_id','query_id','report_type','completeness','coverage_json',
  'task_id','run_id','model_version','processed_at','revision','expires_at')),'old report writer remains compatible');
SELECT pg_temp.assert_true((SELECT convalidated FROM pg_constraint
 WHERE conrelid='public.llm_report'::regclass AND conname='ck_report_subject' AND contype='c'),
 'typed report subject check remains validated');
SELECT pg_temp.assert_true(NOT EXISTS(SELECT 1 FROM pg_constraint
 WHERE conrelid='public.llm_report'::regclass AND conname='ck_llm_report_source_exclusive'),
 'legacy exclusive source check no longer blocks event and query reports');
DO $normal_chain$
DECLARE
 temporary_id uuid; registered_id uuid; second_registered uuid; link_id uuid; assignment_id uuid;
 image_id uuid; history_sample uuid; enrollment_sample uuid; feature_id uuid; task_id uuid; run_id uuid;
 query_id uuid; query2_id uuid; event_id uuid; evidence_id uuid; activity_id uuid; v_report_id uuid;
 v vector := array_fill(1::real,ARRAY[3072])::vector;
 expiry timestamptz := now()+interval '7 days';
 track uuid := '40000000-0000-4000-8000-000000000001';
BEGIN
 INSERT INTO public.identity(identity_kind,object_type,first_seen_at,last_seen_at,expires_at)
 VALUES ('temporary','person',now(),now(),expiry) RETURNING id INTO temporary_id;
 INSERT INTO public.identity(identity_kind,object_type,display_name,registered_at)
 VALUES ('registered','person','same display name',now()) RETURNING id INTO registered_id;
 INSERT INTO public.identity(identity_kind,object_type,display_name,registered_at)
 VALUES ('registered','person','same display name',now()) RETURNING id INTO second_registered;
 PERFORM pg_temp.assert_true((SELECT count(DISTINCT display_no)=3 FROM public.identity),
   'atomic display allocation and duplicate names coexist');
 PERFORM pg_temp.expect_sqlstate($q$INSERT INTO public.identity(identity_kind,object_type)
   VALUES ('temporary','person')$q$,'23514');
 INSERT INTO public.identity_link(temporary_identity_id,registered_identity_id,valid_from,basis_type,expires_at)
 VALUES (temporary_id,registered_id,now(),'manual_confirm',expiry) RETURNING id INTO link_id;
 PERFORM pg_temp.expect_sqlstate(format('INSERT INTO public.identity_link
   (temporary_identity_id,registered_identity_id,valid_from,basis_type,expires_at)
   VALUES (%L,%L,now(),''manual_confirm'',%L)',temporary_id,second_registered,expiry),'23505');
 UPDATE public.identity_link SET valid_to=now(),revision=revision+1 WHERE id=link_id;
 INSERT INTO public.identity_link(temporary_identity_id,registered_identity_id,valid_from,basis_type,expires_at)
 VALUES (temporary_id,second_registered,now(),'manual_confirm',expiry);
 INSERT INTO public.track_identity_assignment(tracklet_id,identity_id,valid_from,basis_type,expires_at)
 VALUES (track,temporary_id,now(),'cross_camera_match',expiry) RETURNING id INTO assignment_id;
 PERFORM pg_temp.expect_sqlstate(format('INSERT INTO public.track_identity_assignment
   (tracklet_id,identity_id,valid_from,basis_type,expires_at) VALUES (%L,%L,now(),''manual_correction'',%L)',
   track,registered_id,expiry),'23505');
 UPDATE public.track_identity_assignment SET valid_to=now(),revision=revision+1 WHERE id=assignment_id;
 INSERT INTO public.track_identity_assignment(tracklet_id,identity_id,valid_from,basis_type,expires_at)
 VALUES (track,registered_id,now(),'manual_correction',expiry);
 INSERT INTO public.media_asset(asset_type,start_ts,duration_ms,content_type,state,producer_key)
 VALUES ('query_image',now(),0,'image/jpeg','preparing','stage2.fixture.image') RETURNING id INTO image_id;
 INSERT INTO public.sample(purpose,asset_id,tracklet_id,identity_id,occurred_at,expires_at)
 VALUES ('history',image_id,track,temporary_id,now(),expiry) RETURNING id INTO history_sample;
 INSERT INTO public.sample(purpose,asset_id,identity_id,occurred_at)
 VALUES ('enrollment',image_id,registered_id,now()) RETURNING id INTO enrollment_sample;
 PERFORM pg_temp.expect_sqlstate(format('INSERT INTO public.sample(purpose,asset_id,occurred_at)
   VALUES (''query'',%L,now())',image_id),'23514');
 PERFORM pg_temp.expect_sqlstate(format('DELETE FROM public.media_asset WHERE id=%L',image_id),'23503');
 INSERT INTO public.feature_space(id,definition_sha256,definition_version,definition_text,object_type,
   feature_kind,dimensions,normalization,metric)
 VALUES ('fs-stage2-fixture',repeat('a',64),'canonical_json_v1','{}','person','body_appearance',3072,'l2','cosine');
 INSERT INTO public.business_task(task_kind,actor_key,input_digest,expires_at)
 VALUES ('feature.extract','stage2-test',repeat('b',64),expiry) RETURNING business_task.task_id INTO task_id;
 INSERT INTO public.task_attempt(task_id,generation,implementation_code,implementation_version,expires_at)
 VALUES (task_id,1,'fixture','1',expiry) RETURNING task_attempt.run_id INTO run_id;
 INSERT INTO public.feature(feature_space_id,dimensions,embedding,sample_id,tracklet_id,identity_id,
   run_id,producer_feature_key,aggregation_method,input_count,used_count,processed_at,expires_at)
 VALUES ('fs-stage2-fixture',3072,v,history_sample,track,temporary_id,
   run_id,'sample-1','single',1,1,now(),expiry) RETURNING id INTO feature_id;
 INSERT INTO public.feature_contribution(feature_id,ordinal,sample_id) VALUES (feature_id,0,history_sample);
 PERFORM pg_temp.assert_true((SELECT vector_dims(embedding)=3072 AND abs(embedding<=>v)<0.000001
   FROM public.feature WHERE id=feature_id),'3072-dimensional exact cosine is usable without ANN');
 PERFORM pg_temp.expect_sqlstate(format('UPDATE public.feature SET dimensions=3 WHERE id=%L',feature_id),'23514');
 PERFORM pg_temp.expect_sqlstate(format('UPDATE public.feature SET dimensions=3,embedding=''[1,0,0]'' WHERE id=%L',feature_id),'23503');
 PERFORM pg_temp.expect_sqlstate(format('INSERT INTO public.feature_contribution(feature_id,ordinal,sample_id)
   VALUES (%L,1,%L)',feature_id,history_sample),'23505');
 INSERT INTO public.legacy_identity_map(legacy_namespace,legacy_id,identity_id,sample_id)
 VALUES ('public.reid_target','synthetic-legacy-id',registered_id,enrollment_sample);
 PERFORM pg_temp.expect_sqlstate(format('INSERT INTO public.legacy_identity_map(legacy_namespace,legacy_id,identity_id)
   VALUES (''public.reid_target'',''synthetic-legacy-id'',%L)',temporary_id),'23505');
 INSERT INTO public.query_request(owner_user_id,query_kind,input_asset_id,feature_space_id,expires_at)
 VALUES (7,'image',image_id,'fs-stage2-fixture',expiry) RETURNING id INTO query_id;
 INSERT INTO public.query_request(owner_user_id,query_kind,expires_at)
 VALUES (7,'image',expiry) RETURNING id INTO query2_id;
 INSERT INTO public.query_candidate(query_id,candidate_id,sample_id,object_type,confidence,expires_at)
 VALUES (query_id,'1',history_sample,'person',0.9,expiry);
 UPDATE public.query_request SET selected_candidate_id='1',input_sample_id=history_sample WHERE id=query_id;
 PERFORM pg_temp.expect_sqlstate(format('UPDATE public.query_request SET selected_candidate_id=''1'' WHERE id=%L',query2_id),'23503');
 PERFORM pg_temp.expect_sqlstate(format('UPDATE public.query_request SET session_id=gen_random_uuid() WHERE id=%L',query_id),'23514');
 INSERT INTO public.search_hit(query_id,rank_no,hit_kind,identity_id,tracklet_id,sample_id,feature_id,feature_space_id,
   score,score_metric,expires_at)
 VALUES (query_id,1,'historical',temporary_id,track,history_sample,feature_id,'fs-stage2-fixture',0.99,'cosine_similarity',expiry);
 PERFORM pg_temp.expect_sqlstate(format('INSERT INTO public.search_hit(query_id,rank_no,hit_kind,sample_id,expires_at)
   VALUES (%L,1,''gallery'',%L,%L)',query_id,enrollment_sample,expiry),'23505');
 INSERT INTO public.business_event(event_type,event_key,source_id,start_at,end_at,state,end_reason,expires_at)
 VALUES ('fixture.event','fixture-1','10000000-0000-4000-8000-000000000001',now(),now(),'closed','normal',expiry)
 RETURNING id INTO event_id;
 INSERT INTO public.event_object_link(event_id,identity_id,expires_at) VALUES (event_id,temporary_id,expiry);
 PERFORM pg_temp.expect_sqlstate(format('INSERT INTO public.event_object_link(event_id,identity_id,tracklet_id,expires_at)
   VALUES (%L,%L,%L,%L)',event_id,temporary_id,track,expiry),'23514');
 PERFORM pg_temp.expect_sqlstate(format('INSERT INTO public.event_object_link(event_id,identity_id,expires_at)
   VALUES (%L,%L,%L)',event_id,temporary_id,expiry),'23505');
 INSERT INTO public.episode(start_ts,end_ts,identity_id,activity_type,state,coverage_json,revision,expires_at)
 VALUES (now(),now(),temporary_id,'person_activity','open','{}',1,expiry) RETURNING id INTO activity_id;
 PERFORM pg_temp.expect_sqlstate(format('INSERT INTO public.episode(start_ts,end_ts,identity_id,activity_type,state)
   VALUES (now(),now(),%L,''person_activity'',''open'')',temporary_id),'23505');
 INSERT INTO public.evidence_reference(event_id,start_at,fact_snapshot,expires_at)
 VALUES (event_id,now(),'{"schema_version":"1","label":"fixture"}',expiry) RETURNING id INTO evidence_id;
 PERFORM pg_temp.expect_sqlstate(format('INSERT INTO public.evidence_reference(event_id,activity_id,start_at,fact_snapshot,expires_at)
   VALUES (%L,%L,now(),''{"label":"fixture"}'',%L)',event_id,activity_id,expiry),'23514');
 INSERT INTO public.llm_report(event_id,subject_kind,subject_id,report_type,completeness,coverage_json,
   report_json,report_text,processed_at,revision,expires_at)
 VALUES (event_id,'event',event_id,'summary','partial','{}','{"summary":"first"}','first',now(),1,expiry)
 RETURNING id INTO v_report_id;
 INSERT INTO public.report_evidence_link(report_id,evidence_id,report_revision,ordinal)
 VALUES (v_report_id,evidence_id,1,0);
 UPDATE public.llm_report SET report_text='updated',completeness='complete',revision=2,processed_at=now()
 WHERE id=v_report_id;
 UPDATE public.report_evidence_link rel SET report_revision=2 WHERE rel.report_id=v_report_id;
 PERFORM pg_temp.assert_true((SELECT count(*)=1 FROM public.llm_report WHERE id=v_report_id AND revision=2),
   'report update keeps stable ID');
 PERFORM pg_temp.expect_sqlstate(format('INSERT INTO public.llm_report(event_id,subject_kind,subject_id,report_type,report_json)
   VALUES (%L,''event'',%L,''summary'',''{}'')',event_id,event_id),'23505');
 PERFORM pg_temp.expect_sqlstate(format('INSERT INTO public.llm_report(subject_kind,subject_id,report_type,report_json)
   VALUES (''event'',%L,''other'',''{}'')',event_id),'23514');
 INSERT INTO public.llm_report(query_id,subject_kind,subject_id,report_type,completeness,coverage_json,
   report_json,processed_at,revision,expires_at)
 VALUES (query_id,'query',query_id,'query_summary','partial','{}','{"summary":"query"}',now(),1,expiry);
 PERFORM pg_temp.expect_sqlstate(format('INSERT INTO public.llm_report(query_id,subject_kind,subject_id,report_type,report_json)
   VALUES (%L,''query'',%L,''wrong_query'',''{}'')',query_id,query2_id),'23514');
 INSERT INTO public.asset_reference(asset_id,sample_id) VALUES (image_id,enrollment_sample);
 INSERT INTO public.asset_reference(asset_id,identity_id) VALUES (image_id,registered_id);
 INSERT INTO public.asset_reference(asset_id,query_id,retain_until) VALUES (image_id,query_id,expiry);
 INSERT INTO public.asset_reference(asset_id,evidence_id,retain_until) VALUES (image_id,evidence_id,expiry);
 PERFORM pg_temp.expect_sqlstate(format('INSERT INTO public.asset_reference(asset_id,sample_id)
   VALUES (%L,%L)',image_id,enrollment_sample),'23505');
 PERFORM pg_temp.expect_sqlstate(format('INSERT INTO public.asset_reference(asset_id,query_id)
   VALUES (%L,%L)',image_id,query2_id),'23514');
 PERFORM pg_temp.expect_sqlstate(format('INSERT INTO public.asset_reference(asset_id,message_id,retain_until)
   VALUES (%L,gen_random_uuid(),%L)',image_id,expiry),'23514');
 -- Existing callers continue using named legacy columns after the migration.
 INSERT INTO public.episode(title,start_ts,end_ts) VALUES ('old writer still valid',now(),now());
 INSERT INTO public.llm_report(episode_id,prompt_type,report_json)
 VALUES ('81000000-0000-4000-8000-000000000001','old-writer','{}');
END
$normal_chain$;
SELECT 'Stage 2 normal chain, 3072-vector search, ownership, uniqueness, FK and compatibility checks passed.';
ROLLBACK;
