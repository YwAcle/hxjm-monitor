-- HXJM v0.2 stage 1: four retained tables and seventeen new tables.
-- Apply with psql -X -v ON_ERROR_STOP=1 -f 001_video_results.sql.
-- No database creation, data import, data backfill, or migration ledger.
-- A repeated/partial application is rejected; every change below is one transaction.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
SET LOCAL search_path = pg_catalog, public;

DO $required_tables$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['camera','camera_stream','media_asset','tracklet'] LOOP
    IF NOT EXISTS (SELECT FROM pg_class WHERE oid=to_regclass('public.' || table_name)
      AND relkind IN ('r','p')) THEN
      RAISE EXCEPTION 'stage1: required legacy table public.% is missing',table_name;
    END IF;
  END LOOP;
END
$required_tables$;

LOCK TABLE public.camera, public.camera_stream, public.media_asset, public.tracklet
  IN ACCESS EXCLUSIVE MODE;

DO $preflight$
DECLARE
  item record;
  actual_type oid;
  actual_not_null boolean;
  relation_oid regclass;
  found_new text;
BEGIN
  SELECT string_agg(name, ', ' ORDER BY name) INTO found_new
  FROM unnest(ARRAY['stream_session','capability_definition','capability_instance','result_type',
    'business_task','task_attempt','request_deduplication','outbox_event','tracking_context',
    'result_set','result_selection','input_frame','analysis_frame','detection_observation',
    'algorithm_result','processing_coverage','asset_reference']) AS names(name)
  WHERE to_regclass('public.' || name) IS NOT NULL;
  IF found_new IS NOT NULL THEN
    RAISE EXCEPTION 'stage1: already applied or partial/conflicting new tables: %; no changes made',found_new;
  END IF;

  FOR item IN SELECT * FROM (VALUES
    ('camera','management_device_id'), ('camera','channel_code'),
    ('camera','source_kind'), ('camera','enabled'),
    ('media_asset','source_id'), ('media_asset','stream_session_id'),
    ('media_asset','producer_key'), ('media_asset','storage_key'),
    ('media_asset','byte_size'), ('media_asset','checksum_sha256'),
    ('media_asset','write_attempt_id'), ('media_asset','write_lease_until'),
    ('media_asset','state'), ('media_asset','delete_attempts'),
    ('media_asset','last_error_code'), ('media_asset','revision'), ('media_asset','expires_at'),
    ('tracklet','source_id'), ('tracklet','stream_session_id'),
    ('tracklet','tracking_context_id'), ('tracklet','local_track_id'),
    ('tracklet','origin_result_set_id'), ('tracklet','canonical_tracklet_id'),
    ('tracklet','first_observed_at'), ('tracklet','last_observed_at'),
    ('tracklet','end_reason'), ('tracklet','revision'), ('tracklet','expires_at')
  ) AS expected(table_name,column_name) LOOP
    IF EXISTS (SELECT FROM pg_attribute
      WHERE attrelid=to_regclass('public.' || item.table_name) AND attname=item.column_name
        AND attnum>0 AND NOT attisdropped) THEN
      RAISE EXCEPTION 'stage1: already applied or partial/conflicting column %.%; no changes made',
        item.table_name,item.column_name;
    END IF;
  END LOOP;

  FOR item IN SELECT * FROM (VALUES
    ('camera','id','uuid',true), ('camera','camera_code','text',true), ('camera','name','text',true),
    ('camera_stream','id','uuid',true), ('camera_stream','camera_id','uuid',true),
    ('camera_stream','stream_name','text',true), ('camera_stream','task_type','text',true),
    ('camera_stream','is_active','boolean',true),
    ('media_asset','id','uuid',true), ('media_asset','asset_type','text',true),
    ('media_asset','start_ts','timestamp with time zone',true),
    ('media_asset','duration_ms','bigint',true), ('media_asset','play_url','text',false),
    ('media_asset','oss_key','text',false), ('media_asset','content_type','text',false),
    ('tracklet','id','uuid',true), ('tracklet','start_ts','timestamp with time zone',true),
    ('tracklet','end_ts','timestamp with time zone',false), ('tracklet','cls_name','text',true)
  ) AS expected(table_name,column_name,type_name,required_not_null) LOOP
    SELECT atttypid,attnotnull INTO actual_type,actual_not_null FROM pg_attribute
      WHERE attrelid=to_regclass('public.' || item.table_name) AND attname=item.column_name
        AND attnum>0 AND NOT attisdropped;
    IF NOT FOUND OR actual_type<>to_regtype(item.type_name)
      OR (item.required_not_null AND NOT actual_not_null) THEN
      RAISE EXCEPTION 'stage1: incompatible legacy column %.%; expected % (required NOT NULL=%)',
        item.table_name,item.column_name,item.type_name,item.required_not_null;
    END IF;
  END LOOP;

  FOR item IN SELECT unnest(ARRAY['camera','camera_stream','media_asset','tracklet']) AS table_name LOOP
    relation_oid := to_regclass('public.' || item.table_name);
    IF NOT EXISTS (SELECT FROM pg_constraint WHERE conrelid=relation_oid AND contype='p'
      AND conkey=ARRAY[(SELECT attnum FROM pg_attribute
        WHERE attrelid=relation_oid AND attname='id')]::smallint[]) THEN
      RAISE EXCEPTION 'stage1: public.% requires its existing primary key (id)',item.table_name;
    END IF;
  END LOOP;

  FOR item IN SELECT unnest(ARRAY['media_asset','tracklet']) AS table_name LOOP
    SELECT atttypid,attnotnull INTO actual_type,actual_not_null FROM pg_attribute
      WHERE attrelid=to_regclass('public.' || item.table_name) AND attname='stream_id'
        AND attnum>0 AND NOT attisdropped;
    IF NOT FOUND OR actual_type NOT IN ('uuid'::regtype,'character varying'::regtype)
      OR NOT actual_not_null THEN
      RAISE EXCEPTION 'stage1: %.stream_id must retain a NOT NULL uuid or varchar legacy type',item.table_name;
    END IF;
  END LOOP;

  -- Replace only the known three-value asset-type check; preserve unrelated checks.
  FOR item IN SELECT c.conname,pg_get_expr(c.conbin,c.conrelid) AS expression
    FROM pg_constraint c JOIN pg_attribute a ON a.attrelid=c.conrelid
    WHERE c.conrelid='public.media_asset'::regclass AND c.contype='c'
      AND a.attname='asset_type' AND a.attnum=ANY(c.conkey)
  LOOP
    IF item.conname<>'chk_media_asset_type' OR regexp_replace(item.expression,'[[:space:]]','','g')<>
      '(asset_type=ANY(ARRAY[''segment''::text,''clip''::text,''snapshot''::text]))' THEN
      RAISE EXCEPTION 'stage1: unsupported legacy asset_type constraint %; review its definition first',item.conname;
    END IF;
  END LOOP;

  IF to_regclass('public.ai_task_run') IS NOT NULL THEN
    IF NOT EXISTS (SELECT FROM pg_attribute WHERE attrelid=to_regclass('public.ai_task_run')
      AND attname='run_id' AND atttypid='character varying'::regtype AND atttypmod=68
      AND attnotnull AND NOT attisdropped) OR NOT EXISTS (
      SELECT FROM pg_constraint WHERE conrelid=to_regclass('public.ai_task_run') AND contype IN ('p','u')
        AND conkey=ARRAY[(SELECT attnum FROM pg_attribute
          WHERE attrelid=to_regclass('public.ai_task_run') AND attname='run_id')]::smallint[]
    ) THEN
      RAISE EXCEPTION 'stage1: existing ai_task_run.run_id must be unique NOT NULL varchar(64)';
    END IF;
  END IF;
  IF EXISTS (SELECT FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace
    WHERE e.extname='btree_gist' AND n.nspname<>'public') THEN
    RAISE EXCEPTION 'stage1: existing btree_gist is outside public; review extension placement first';
  END IF;
END
$preflight$;

CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;

ALTER TABLE public.camera
  ADD COLUMN management_device_id bigint,
  ADD COLUMN channel_code varchar(64),
  ADD COLUMN source_kind varchar(24) NOT NULL DEFAULT 'camera',
  ADD COLUMN enabled boolean NOT NULL DEFAULT true;
ALTER TABLE public.media_asset
  ADD COLUMN source_id uuid,
  ADD COLUMN stream_session_id uuid,
  ADD COLUMN producer_key varchar(128),
  ADD COLUMN storage_key text,
  ADD COLUMN byte_size bigint,
  ADD COLUMN checksum_sha256 char(64),
  ADD COLUMN write_attempt_id uuid,
  ADD COLUMN write_lease_until timestamptz(6),
  ADD COLUMN state varchar(24),
  ADD COLUMN delete_attempts integer NOT NULL DEFAULT 0,
  ADD COLUMN last_error_code varchar(64),
  ADD COLUMN revision bigint NOT NULL DEFAULT 1,
  ADD COLUMN expires_at timestamptz(6),
  ALTER COLUMN play_url DROP NOT NULL;
-- NULL state leaves legacy registrations outside new-chain availability queries.
-- stream_id retains its type, NOT NULL, default, and existing foreign key behavior.
ALTER TABLE public.tracklet
  ADD COLUMN source_id uuid,
  ADD COLUMN stream_session_id uuid,
  ADD COLUMN tracking_context_id uuid,
  ADD COLUMN local_track_id bigint,
  ADD COLUMN origin_result_set_id uuid,
  ADD COLUMN canonical_tracklet_id uuid,
  ADD COLUMN first_observed_at timestamptz(6),
  ADD COLUMN last_observed_at timestamptz(6),
  ADD COLUMN end_reason varchar(32),
  ADD COLUMN revision bigint NOT NULL DEFAULT 1,
  ADD COLUMN expires_at timestamptz(6);
-- New registration validates required new-chain fields; legacy writers may omit them.
-- camera_stream, its task_type check, and deletion behavior remain unchanged.


CREATE TABLE public.stream_session (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  source_id uuid NOT NULL,
  camera_stream_id uuid,
  session_key varchar(128) NOT NULL,
  started_at timestamptz(6) NOT NULL,
  ended_at timestamptz(6),
  time_origin_at timestamptz(6) NOT NULL,
  time_basis varchar(24) NOT NULL,
  source_timezone varchar(64) NOT NULL,
  source_width integer NOT NULL,
  source_height integer NOT NULL,
  state varchar(16) NOT NULL DEFAULT 'open',
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE (source_id, session_key),
  CHECK (state IN ('open','closed','interrupted')),
  CHECK (time_basis IN ('source_clock','ingest_clock')),
  CHECK (source_width>0 AND source_height>0),
  CHECK (ended_at IS NULL OR ended_at>=started_at),
  CHECK ((state='open' AND ended_at IS NULL) OR (state IN ('closed','interrupted') AND ended_at IS NOT NULL))
);
CREATE INDEX ix_stream_session_source_time ON public.stream_session (source_id, started_at);

CREATE TABLE public.capability_definition (
  capability_code varchar(64) NOT NULL,
  display_name varchar(128) NOT NULL,
  object_types text[] NOT NULL,
  input_kinds text[] NOT NULL,
  contract_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  enabled boolean NOT NULL DEFAULT true,
  revision bigint NOT NULL DEFAULT 1,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  updated_at timestamptz(6) NOT NULL DEFAULT now(),
  PRIMARY KEY (capability_code),
  CHECK (cardinality(object_types)>0 AND cardinality(input_kinds)>0),
  CHECK (revision>0)
);

CREATE TABLE public.capability_instance (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  capability_code varchar(64) NOT NULL,
  instance_key varchar(128) NOT NULL,
  implementation_code varchar(64) NOT NULL,
  implementation_version varchar(128) NOT NULL,
  source_ids uuid[] NOT NULL DEFAULT '{}'::uuid[],
  service_ref varchar(256) NOT NULL,
  enabled boolean NOT NULL DEFAULT true,
  revision bigint NOT NULL DEFAULT 1,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  updated_at timestamptz(6) NOT NULL DEFAULT now(),
  CONSTRAINT pk_capability_instance PRIMARY KEY (id),
  CONSTRAINT uk_capability_instance_key UNIQUE (capability_code, instance_key),
  CONSTRAINT ck_instance_revision CHECK (revision>0),
  CONSTRAINT ck_instance_keys CHECK (char_length(btrim(instance_key))>0 AND char_length(btrim(implementation_code))>0 AND char_length(btrim(implementation_version))>0 AND char_length(btrim(service_ref))>0),
  CONSTRAINT ck_instance_sources CHECK (array_position(source_ids,NULL::uuid) IS NULL)
);
CREATE INDEX ix_instance_selection ON public.capability_instance (capability_code, enabled, id);

CREATE TABLE public.result_type (
  type_code varchar(64) NOT NULL,
  schema_version varchar(32) NOT NULL,
  json_schema jsonb NOT NULL DEFAULT '{}'::jsonb,
  max_inline_bytes integer NOT NULL DEFAULT 1048576,
  enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  PRIMARY KEY (type_code, schema_version),
  CHECK (max_inline_bytes>0),
  CHECK (jsonb_typeof(json_schema)='object')
);

CREATE TABLE public.business_task (
  task_id uuid NOT NULL DEFAULT gen_random_uuid(),
  task_kind varchar(64) NOT NULL,
  business_key varchar(256),
  task_mode varchar(16) NOT NULL DEFAULT 'once',
  last_input_at timestamptz(6),
  actor_key varchar(128) NOT NULL,
  owner_user_id bigint,
  capability_code varchar(64),
  state varchar(24) NOT NULL DEFAULT 'pending',
  input_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  input_digest char(64) NOT NULL,
  current_run_id uuid,
  generation bigint NOT NULL DEFAULT 0,
  progress numeric(5,2) NOT NULL DEFAULT 0,
  error_code varchar(64),
  error_message text,
  revision bigint NOT NULL DEFAULT 1,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  updated_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6) NOT NULL,
  PRIMARY KEY (task_id),
  UNIQUE (task_kind, business_key),
  CHECK (state IN ('pending','running','waiting_input','succeeded','partial','failed','cancelled','expired')),
  CHECK (generation>=0 AND progress>=0 AND progress<=100 AND revision>0),
  CHECK (task_mode IN ('once','continuous'))
);
CREATE INDEX ix_task_owner_state ON public.business_task (owner_user_id, state, created_at);
CREATE INDEX ix_task_expiry ON public.business_task (expires_at);

CREATE TABLE public.task_attempt (
  run_id uuid NOT NULL DEFAULT gen_random_uuid(),
  task_id uuid NOT NULL,
  generation bigint NOT NULL,
  legacy_run_id varchar(64),
  state varchar(24) NOT NULL DEFAULT 'pending',
  implementation_code varchar(128) NOT NULL,
  implementation_version varchar(128) NOT NULL,
  parameters_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  lease_owner varchar(128),
  lease_until timestamptz(6),
  started_at timestamptz(6),
  finished_at timestamptz(6),
  error_code varchar(64),
  error_message text,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  updated_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6) NOT NULL,
  PRIMARY KEY (run_id),
  UNIQUE (task_id, generation),
  UNIQUE (task_id, run_id),
  UNIQUE (legacy_run_id),
  CHECK (generation>0),
  CHECK (finished_at IS NULL OR started_at IS NULL OR finished_at>=started_at),
  CHECK (state IN ('pending','running','waiting_input','succeeded','partial','failed','cancelled','expired'))
);
CREATE INDEX ix_attempt_recovery ON public.task_attempt (state, lease_until);

CREATE TABLE public.request_deduplication (
  actor_key varchar(128) NOT NULL,
  operation varchar(128) NOT NULL,
  request_id varchar(128) NOT NULL,
  request_digest char(64) NOT NULL,
  state varchar(16) NOT NULL DEFAULT 'accepted',
  task_id uuid,
  response_json jsonb,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  updated_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6) NOT NULL,
  PRIMARY KEY (actor_key, operation, request_id),
  CHECK (state IN ('accepted','completed','failed'))
);
CREATE INDEX ix_dedup_expiry ON public.request_deduplication (expires_at);

CREATE TABLE public.outbox_event (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  event_type varchar(64) NOT NULL,
  aggregate_type varchar(64) NOT NULL,
  aggregate_id uuid NOT NULL,
  aggregate_revision bigint NOT NULL,
  payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  state varchar(16) NOT NULL DEFAULT 'pending',
  attempt_count integer NOT NULL DEFAULT 0,
  next_attempt_at timestamptz(6) NOT NULL DEFAULT now(),
  last_error_code varchar(64),
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6) NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uk_outbox_aggregate_revision UNIQUE (event_type, aggregate_type, aggregate_id, aggregate_revision),
  CHECK (state IN ('pending','sent','dead')),
  CHECK (aggregate_revision>0 AND attempt_count>=0)
);
CREATE INDEX ix_outbox_pending ON public.outbox_event (next_attempt_at, id) WHERE state='pending';

CREATE TABLE public.tracking_context (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  stream_session_id uuid NOT NULL,
  run_id uuid NOT NULL,
  context_key varchar(128) NOT NULL,
  source_width integer NOT NULL,
  source_height integer NOT NULL,
  started_at timestamptz(6) NOT NULL,
  ended_at timestamptz(6),
  reset_reason varchar(64),
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE (run_id, context_key),
  CHECK (source_width>0 AND source_height>0),
  CHECK (ended_at IS NULL OR ended_at>=started_at)
);
CREATE INDEX ix_context_session ON public.tracking_context (stream_session_id, started_at);

CREATE TABLE public.result_set (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  run_id uuid NOT NULL,
  source_id uuid,
  input_asset_id uuid,
  stream_session_id uuid,
  capability_code varchar(64) NOT NULL,
  set_key varchar(128) NOT NULL,
  generation bigint NOT NULL,
  state varchar(16) NOT NULL DEFAULT 'collecting',
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE (run_id, set_key),
  UNIQUE (id, source_id, capability_code),
  CHECK (generation>0),
  CHECK (state IN ('collecting','ready','partial','failed')),
  CHECK (source_id IS NOT NULL OR input_asset_id IS NOT NULL),
  CHECK (stream_session_id IS NULL OR source_id IS NOT NULL)
);
CREATE INDEX ix_result_set_run ON public.result_set (run_id);

CREATE TABLE public.result_selection (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  source_id uuid NOT NULL,
  capability_code varchar(64) NOT NULL,
  range_start timestamptz(6) NOT NULL,
  range_end timestamptz(6) NOT NULL,
  result_set_id uuid NOT NULL,
  generation bigint NOT NULL,
  revision bigint NOT NULL DEFAULT 1,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6) NOT NULL,
  PRIMARY KEY (id),
  CHECK (range_end>range_start AND generation>0 AND revision>0),
  EXCLUDE USING gist (source_id WITH =, capability_code WITH =, tstzrange(range_start, range_end, '[)') WITH &&)
);
CREATE INDEX ix_selection_set ON public.result_selection (result_set_id);

CREATE TABLE public.input_frame (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  stream_session_id uuid NOT NULL,
  frame_seq bigint NOT NULL,
  occurred_at timestamptz(6) NOT NULL,
  stream_pts_ms bigint,
  media_asset_id uuid,
  media_pts_ms bigint,
  time_quality varchar(24) NOT NULL,
  width integer NOT NULL,
  height integer NOT NULL,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE (stream_session_id, frame_seq),
  CHECK (frame_seq>=0 AND width>0 AND height>0),
  CHECK (stream_pts_ms IS NULL OR stream_pts_ms>=0),
  CHECK (media_pts_ms IS NULL OR media_pts_ms>=0),
  CHECK ((media_asset_id IS NULL)=(media_pts_ms IS NULL)),
  CHECK (time_quality IN ('source_clock','ingest_estimated','reconciled'))
);
CREATE INDEX ix_frame_session_time ON public.input_frame (stream_session_id, occurred_at, id);
CREATE INDEX ix_frame_expiry ON public.input_frame (expires_at);

CREATE TABLE public.analysis_frame (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  result_set_id uuid NOT NULL,
  input_frame_id uuid NOT NULL,
  producer_result_key varchar(128) NOT NULL,
  schema_version varchar(32) NOT NULL DEFAULT '1',
  target_count integer NOT NULL,
  payload_digest char(64) NOT NULL,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE (result_set_id, input_frame_id),
  UNIQUE (result_set_id, producer_result_key),
  CHECK (target_count>=0)
);
CREATE INDEX ix_analysis_frame_input ON public.analysis_frame (input_frame_id, result_set_id);

CREATE TABLE public.detection_observation (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  analysis_frame_id uuid NOT NULL,
  target_index integer NOT NULL,
  tracklet_id uuid,
  object_type varchar(64) NOT NULL,
  class_code varchar(64) NOT NULL,
  confidence double precision,
  observation_kind varchar(16) NOT NULL,
  bbox_left double precision NOT NULL,
  bbox_top double precision NOT NULL,
  bbox_right double precision NOT NULL,
  bbox_bottom double precision NOT NULL,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE (analysis_frame_id, target_index),
  CHECK (bbox_left>=0 AND bbox_top>=0 AND bbox_right<=1 AND bbox_bottom<=1 AND bbox_right>bbox_left AND bbox_bottom>bbox_top),
  CHECK (observation_kind IN ('observed','predicted')),
  CHECK (target_index>=0 AND (confidence IS NULL OR (confidence>=0 AND confidence<=1))),
  CHECK (observation_kind='predicted' OR confidence IS NOT NULL)
);
CREATE INDEX ix_observation_track_frame ON public.detection_observation (tracklet_id, analysis_frame_id);

CREATE TABLE public.algorithm_result (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  result_set_id uuid NOT NULL,
  producer_result_key varchar(128) NOT NULL,
  result_type varchar(64) NOT NULL,
  schema_version varchar(32) NOT NULL,
  input_frame_id uuid,
  tracklet_id uuid,
  start_at timestamptz(6) NOT NULL,
  end_at timestamptz(6),
  payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  payload_asset_id uuid,
  payload_digest char(64) NOT NULL,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE (result_set_id, producer_result_key),
  CHECK (end_at IS NULL OR end_at>=start_at)
);
CREATE INDEX ix_algorithm_result_type_time ON public.algorithm_result (result_type, start_at, id);

CREATE TABLE public.processing_coverage (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  source_id uuid NOT NULL,
  stream_session_id uuid,
  run_id uuid,
  result_set_id uuid,
  stage varchar(24) NOT NULL,
  coverage_key varchar(128) NOT NULL,
  closed boolean NOT NULL DEFAULT false,
  start_at timestamptz(6) NOT NULL,
  end_at timestamptz(6) NOT NULL,
  status varchar(16) NOT NULL,
  analyzed_frame_count bigint NOT NULL DEFAULT 0,
  saved_frame_count bigint NOT NULL DEFAULT 0,
  frame_manifest_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  reason_code varchar(64),
  revision bigint NOT NULL DEFAULT 1,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6) NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uk_coverage_key UNIQUE (source_id, stage, coverage_key),
  CONSTRAINT ck_coverage_revision CHECK (revision>0),
  CHECK (end_at>start_at AND analyzed_frame_count>=0 AND saved_frame_count>=0 AND saved_frame_count<=analyzed_frame_count),
  CHECK (stage IN ('input','recording','analysis','registration','features')),
  CHECK (status IN ('complete','partial','gap','unavailable'))
);
CREATE INDEX ix_coverage_source_stage_time ON public.processing_coverage (source_id, stage, start_at, end_at);

CREATE TABLE public.asset_reference (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  asset_id uuid NOT NULL,
  sample_id uuid,
  evidence_id uuid,
  query_id uuid,
  identity_id uuid,
  message_id uuid,
  result_id uuid,
  retain_until timestamptz(6) NOT NULL,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  PRIMARY KEY (id),
  CHECK (num_nonnulls(sample_id,evidence_id,query_id,identity_id,message_id,result_id)=1),
  CONSTRAINT ck_asset_ref_stage1_owner CHECK (result_id IS NOT NULL AND
    sample_id IS NULL AND evidence_id IS NULL AND query_id IS NULL AND identity_id IS NULL AND message_id IS NULL)
);
CREATE INDEX ix_asset_reference_retention ON public.asset_reference (asset_id, retain_until);
CREATE UNIQUE INDEX uk_asset_ref_result ON public.asset_reference (asset_id, result_id) WHERE result_id IS NOT NULL;
CREATE INDEX ix_asset_ref_result ON public.asset_reference (result_id) WHERE result_id IS NOT NULL;

-- Physical references within the stage-one boundary.
ALTER TABLE public.stream_session ADD CONSTRAINT fk_ss_source FOREIGN KEY (source_id) REFERENCES public.camera (id) ON DELETE RESTRICT;
ALTER TABLE public.stream_session ADD CONSTRAINT fk_ss_stream FOREIGN KEY (camera_stream_id) REFERENCES public.camera_stream (id) ON DELETE RESTRICT;
ALTER TABLE public.capability_instance ADD CONSTRAINT fk_instance_cap FOREIGN KEY (capability_code) REFERENCES public.capability_definition (capability_code) ON DELETE RESTRICT;
ALTER TABLE public.business_task ADD CONSTRAINT fk_task_cap FOREIGN KEY (capability_code) REFERENCES public.capability_definition (capability_code) ON DELETE RESTRICT;
ALTER TABLE public.task_attempt ADD CONSTRAINT fk_attempt_task FOREIGN KEY (task_id) REFERENCES public.business_task (task_id) ON DELETE RESTRICT;
ALTER TABLE public.request_deduplication ADD CONSTRAINT fk_dedup_task FOREIGN KEY (task_id) REFERENCES public.business_task (task_id) ON DELETE SET NULL;
ALTER TABLE public.tracking_context ADD CONSTRAINT fk_context_session FOREIGN KEY (stream_session_id) REFERENCES public.stream_session (id) ON DELETE RESTRICT;
ALTER TABLE public.tracking_context ADD CONSTRAINT fk_context_run FOREIGN KEY (run_id) REFERENCES public.task_attempt (run_id) ON DELETE RESTRICT;
ALTER TABLE public.result_set ADD CONSTRAINT fk_rs_run FOREIGN KEY (run_id) REFERENCES public.task_attempt (run_id) ON DELETE RESTRICT;
ALTER TABLE public.result_set ADD CONSTRAINT fk_rs_source FOREIGN KEY (source_id) REFERENCES public.camera (id) ON DELETE RESTRICT;
ALTER TABLE public.result_set ADD CONSTRAINT fk_rs_session FOREIGN KEY (stream_session_id) REFERENCES public.stream_session (id) ON DELETE RESTRICT;
ALTER TABLE public.result_set ADD CONSTRAINT fk_rs_cap FOREIGN KEY (capability_code) REFERENCES public.capability_definition (capability_code) ON DELETE RESTRICT;
ALTER TABLE public.result_set ADD CONSTRAINT fk_rs_input_asset FOREIGN KEY (input_asset_id) REFERENCES public.media_asset (id) ON DELETE RESTRICT;
ALTER TABLE public.result_selection ADD CONSTRAINT fk_selection_set FOREIGN KEY (result_set_id, source_id, capability_code) REFERENCES public.result_set (id, source_id, capability_code) ON DELETE RESTRICT;
ALTER TABLE public.input_frame ADD CONSTRAINT fk_frame_session FOREIGN KEY (stream_session_id) REFERENCES public.stream_session (id) ON DELETE RESTRICT;
ALTER TABLE public.input_frame ADD CONSTRAINT fk_frame_media FOREIGN KEY (media_asset_id) REFERENCES public.media_asset (id) ON DELETE RESTRICT;
ALTER TABLE public.analysis_frame ADD CONSTRAINT fk_af_set FOREIGN KEY (result_set_id) REFERENCES public.result_set (id) ON DELETE RESTRICT;
ALTER TABLE public.analysis_frame ADD CONSTRAINT fk_af_input FOREIGN KEY (input_frame_id) REFERENCES public.input_frame (id) ON DELETE RESTRICT;
ALTER TABLE public.detection_observation ADD CONSTRAINT fk_obs_frame FOREIGN KEY (analysis_frame_id) REFERENCES public.analysis_frame (id) ON DELETE RESTRICT;
ALTER TABLE public.detection_observation ADD CONSTRAINT fk_obs_track FOREIGN KEY (tracklet_id) REFERENCES public.tracklet (id) ON DELETE SET NULL;
ALTER TABLE public.algorithm_result ADD CONSTRAINT fk_ar_set FOREIGN KEY (result_set_id) REFERENCES public.result_set (id) ON DELETE RESTRICT;
ALTER TABLE public.algorithm_result ADD CONSTRAINT fk_ar_type FOREIGN KEY (result_type, schema_version) REFERENCES public.result_type (type_code, schema_version) ON DELETE RESTRICT;
ALTER TABLE public.algorithm_result ADD CONSTRAINT fk_ar_frame FOREIGN KEY (input_frame_id) REFERENCES public.input_frame (id) ON DELETE SET NULL;
ALTER TABLE public.algorithm_result ADD CONSTRAINT fk_ar_track FOREIGN KEY (tracklet_id) REFERENCES public.tracklet (id) ON DELETE SET NULL;
ALTER TABLE public.algorithm_result ADD CONSTRAINT fk_ar_asset FOREIGN KEY (payload_asset_id) REFERENCES public.media_asset (id) ON DELETE RESTRICT;
ALTER TABLE public.processing_coverage ADD CONSTRAINT fk_cov_source FOREIGN KEY (source_id) REFERENCES public.camera (id) ON DELETE RESTRICT;
ALTER TABLE public.processing_coverage ADD CONSTRAINT fk_cov_session FOREIGN KEY (stream_session_id) REFERENCES public.stream_session (id) ON DELETE SET NULL;
ALTER TABLE public.processing_coverage ADD CONSTRAINT fk_cov_run FOREIGN KEY (run_id) REFERENCES public.task_attempt (run_id) ON DELETE SET NULL;
ALTER TABLE public.processing_coverage ADD CONSTRAINT fk_cov_set FOREIGN KEY (result_set_id) REFERENCES public.result_set (id) ON DELETE SET NULL;
ALTER TABLE public.asset_reference ADD CONSTRAINT fk_asset_ref_asset FOREIGN KEY (asset_id) REFERENCES public.media_asset (id) ON DELETE RESTRICT;
ALTER TABLE public.asset_reference ADD CONSTRAINT fk_asset_ref_result FOREIGN KEY (result_id) REFERENCES public.algorithm_result (id) ON DELETE RESTRICT;
ALTER TABLE public.media_asset ADD CONSTRAINT fk_asset_source FOREIGN KEY (source_id) REFERENCES public.camera (id) ON DELETE RESTRICT;
ALTER TABLE public.media_asset ADD CONSTRAINT fk_asset_session FOREIGN KEY (stream_session_id) REFERENCES public.stream_session (id) ON DELETE RESTRICT;
ALTER TABLE public.tracklet ADD CONSTRAINT fk_track_source FOREIGN KEY (source_id) REFERENCES public.camera (id) ON DELETE RESTRICT;
ALTER TABLE public.tracklet ADD CONSTRAINT fk_track_session FOREIGN KEY (stream_session_id) REFERENCES public.stream_session (id) ON DELETE RESTRICT;
ALTER TABLE public.tracklet ADD CONSTRAINT fk_track_context FOREIGN KEY (tracking_context_id) REFERENCES public.tracking_context (id) ON DELETE RESTRICT;
ALTER TABLE public.tracklet ADD CONSTRAINT fk_track_result_set FOREIGN KEY (origin_result_set_id) REFERENCES public.result_set (id) ON DELETE SET NULL;
ALTER TABLE public.tracklet ADD CONSTRAINT fk_track_canonical FOREIGN KEY (canonical_tracklet_id) REFERENCES public.tracklet (id) ON DELETE RESTRICT;
ALTER TABLE public.business_task ADD CONSTRAINT fk_task_current_run FOREIGN KEY (task_id, current_run_id) REFERENCES public.task_attempt (task_id, run_id) ON DELETE RESTRICT;

-- Preserve the optional legacy mapping without creating a fifth legacy table.
DO $legacy_fk$
BEGIN
  IF to_regclass('public.ai_task_run') IS NOT NULL THEN
    ALTER TABLE public.task_attempt ADD CONSTRAINT fk_attempt_legacy
      FOREIGN KEY (legacy_run_id) REFERENCES public.ai_task_run (run_id) ON DELETE RESTRICT;
  END IF;
END
$legacy_fk$;

ALTER TABLE public.camera
  ADD CONSTRAINT ck_camera_device_channel CHECK ((management_device_id IS NULL)=(channel_code IS NULL)),
  ADD CONSTRAINT ck_camera_source_kind CHECK (source_kind IN ('camera','device_video','imported_video')),
  ADD CONSTRAINT uk_camera_device_channel UNIQUE (management_device_id, channel_code);

DO $asset_type$
BEGIN
  IF EXISTS (SELECT FROM pg_constraint WHERE conrelid='public.media_asset'::regclass
    AND conname='chk_media_asset_type') THEN
    ALTER TABLE public.media_asset DROP CONSTRAINT chk_media_asset_type;
  END IF;
END
$asset_type$;
ALTER TABLE public.media_asset ADD CONSTRAINT chk_media_asset_type CHECK (
  asset_type IN ('segment','clip','snapshot','recording','crop','evidence_clip',
    'algorithm_output','query_image','enrollment_image'));
ALTER TABLE public.media_asset
  ADD CONSTRAINT ck_asset_state CHECK (state IN ('preparing','available','unavailable','missing','delete_pending','deleted')),
  ADD CONSTRAINT ck_asset_size CHECK ((byte_size IS NULL OR byte_size>=0) AND delete_attempts>=0 AND revision>0),
  ADD CONSTRAINT ck_asset_hash CHECK (checksum_sha256 IS NULL OR checksum_sha256 ~ '^[0-9a-f]{64}$'),
  ADD CONSTRAINT ck_asset_available_content CHECK (state<>'available' OR storage_key IS NULL OR (byte_size IS NOT NULL AND checksum_sha256 IS NOT NULL));
ALTER TABLE public.tracklet
  ADD CONSTRAINT ck_tracklet_context_pair CHECK ((tracking_context_id IS NULL)=(local_track_id IS NULL)),
  ADD CONSTRAINT ck_tracklet_local_id CHECK (local_track_id IS NULL OR local_track_id>=0),
  ADD CONSTRAINT ck_tracklet_observed_time CHECK (
    (first_observed_at IS NULL AND last_observed_at IS NULL) OR
    (first_observed_at IS NOT NULL AND last_observed_at IS NOT NULL AND last_observed_at>=first_observed_at)),
  ADD CONSTRAINT ck_tracklet_canonical CHECK (canonical_tracklet_id IS NULL OR canonical_tracklet_id<>id),
  ADD CONSTRAINT ck_tracklet_end_reason CHECK (end_reason IS NULL OR end_reason IN ('normal','observation_interrupted','cancelled'));
CREATE UNIQUE INDEX uk_asset_producer_key ON public.media_asset (producer_key) WHERE producer_key IS NOT NULL;
CREATE UNIQUE INDEX uk_asset_storage_key ON public.media_asset (storage_key) WHERE storage_key IS NOT NULL;
CREATE INDEX ix_asset_source_time ON public.media_asset (source_id, start_ts, id);
CREATE INDEX ix_asset_expiry_state ON public.media_asset (expires_at, state);
CREATE UNIQUE INDEX uk_track_context_local ON public.tracklet (tracking_context_id, local_track_id) WHERE tracking_context_id IS NOT NULL;
CREATE INDEX ix_track_source_observed ON public.tracklet (source_id, first_observed_at, last_observed_at);

COMMIT;
