-- HXJM v0.2 stage 2: identity, samples, features, activities, events, reports and queries.
-- Apply after stage 1 with psql -X -v ON_ERROR_STOP=1 -f 002_identity_business.sql.
-- New columns on retained tables remain nullable for old writers; new API validates them.
-- No legacy row is rewritten, imported, removed or implicitly enrolled.
-- Repeated/partial application is rejected. The whole migration is one transaction.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
SET LOCAL search_path = pg_catalog, public;

DO $required_tables$
DECLARE name text;
BEGIN
  FOREACH name IN ARRAY ARRAY['camera','media_asset','tracklet','stream_session',
    'task_attempt','business_task','input_frame','algorithm_result','asset_reference',
    'episode','episode_tracklet_link','llm_report','vad'] LOOP
    IF NOT EXISTS (SELECT FROM pg_class WHERE oid=to_regclass('public.' || name)
      AND relkind IN ('r','p')) THEN
      RAISE EXCEPTION 'stage2: required table public.% is missing',name;
    END IF;
  END LOOP;
END
$required_tables$;

LOCK TABLE public.media_asset, public.asset_reference, public.episode,
  public.episode_tracklet_link, public.llm_report IN ACCESS EXCLUSIVE MODE;

DO $preflight$
DECLARE item record; found_new text; actual_type oid;
BEGIN
  SELECT string_agg(name, ', ' ORDER BY name) INTO found_new FROM unnest(ARRAY[
    'identity','identity_link','track_identity_assignment','legacy_identity_map','sample',
    'feature_space','feature','feature_contribution','business_event','event_object_link',
    'evidence_reference','report_evidence_link','query_request','query_candidate','search_hit',
    'identity_display_no_seq']) names(name)
  WHERE to_regclass('public.' || name) IS NOT NULL;
  IF found_new IS NOT NULL THEN
    RAISE EXCEPTION 'stage2: already applied or partial/conflicting objects: %; no changes made',found_new;
  END IF;
  FOR item IN SELECT * FROM (VALUES
    ('episode','identity_id'),('episode','activity_type'),('episode','state'),
    ('episode','end_reason'),('episode','coverage_json'),('episode','revision'),('episode','expires_at'),
    ('episode_tracklet_link','ordinal'),
    ('llm_report','subject_kind'),('llm_report','subject_id'),('llm_report','event_id'),
    ('llm_report','query_id'),('llm_report','report_type'),('llm_report','completeness'),
    ('llm_report','coverage_json'),('llm_report','task_id'),('llm_report','run_id'),
    ('llm_report','model_version'),('llm_report','processed_at'),('llm_report','revision'),
    ('llm_report','expires_at')) expected(table_name,column_name) LOOP
    IF EXISTS (SELECT FROM pg_attribute WHERE attrelid=to_regclass('public.' || item.table_name)
      AND attname=item.column_name AND attnum>0 AND NOT attisdropped) THEN
      RAISE EXCEPTION 'stage2: already applied or partial/conflicting column %.%; no changes made',
        item.table_name,item.column_name;
    END IF;
  END LOOP;
  FOR item IN SELECT * FROM (VALUES
    ('media_asset','id','uuid'),('media_asset','state','character varying'),
    ('media_asset','expires_at','timestamp with time zone'),
    ('asset_reference','id','uuid'),('asset_reference','retain_until','timestamp with time zone'),
    ('episode','id','uuid'),('episode','start_ts','timestamp with time zone'),
    ('episode','end_ts','timestamp with time zone'),
    ('episode_tracklet_link','episode_id','uuid'),('episode_tracklet_link','tracklet_id','uuid'),
    ('llm_report','id','uuid'),('llm_report','episode_id','uuid'),
    ('llm_report','report_json','jsonb'),('llm_report','created_at','timestamp with time zone'),
    ('vad','id','integer')) expected(table_name,column_name,type_name) LOOP
    SELECT atttypid INTO actual_type FROM pg_attribute
      WHERE attrelid=to_regclass('public.' || item.table_name) AND attname=item.column_name
        AND attnum>0 AND NOT attisdropped;
    IF NOT FOUND OR actual_type<>to_regtype(item.type_name) THEN
      RAISE EXCEPTION 'stage2: incompatible column %.%; expected %',
        item.table_name,item.column_name,item.type_name;
    END IF;
  END LOOP;
  SELECT atttypid INTO actual_type FROM pg_attribute WHERE attrelid='public.media_asset'::regclass
    AND attname='stream_id' AND attnum>0 AND NOT attisdropped;
  IF NOT FOUND OR actual_type NOT IN ('uuid'::regtype,'character varying'::regtype) THEN
    RAISE EXCEPTION 'stage2: media_asset.stream_id must retain its uuid/varchar legacy type';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_constraint WHERE conrelid='public.asset_reference'::regclass
    AND conname='ck_asset_ref_stage1_owner' AND contype='c') THEN
    RAISE EXCEPTION 'stage2: expected stage1 asset-reference owner constraint is missing';
  END IF;
  IF EXISTS (SELECT FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace
    WHERE e.extname='vector' AND n.nspname<>'public') THEN
    RAISE EXCEPTION 'stage2: vector extension is outside public; review placement first';
  END IF;
END
$preflight$;

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
CREATE SEQUENCE public.identity_display_no_seq AS bigint START WITH 1 INCREMENT BY 1 NO CYCLE;

ALTER TABLE public.media_asset ALTER COLUMN stream_id DROP NOT NULL;
ALTER TABLE public.asset_reference
  DROP CONSTRAINT ck_asset_ref_stage1_owner,
  ALTER COLUMN retain_until DROP NOT NULL,
  ADD CONSTRAINT ck_asset_ref_stage2_owner CHECK (message_id IS NULL),
  ADD CONSTRAINT ck_asset_ref_retention CHECK
    (retain_until IS NOT NULL OR identity_id IS NOT NULL OR sample_id IS NOT NULL);
-- NULL retention is accepted only after the API verifies a registered identity or enrollment sample.
ALTER TABLE public.episode
  ADD COLUMN identity_id uuid,
  ADD COLUMN activity_type varchar(64),
  ADD COLUMN state varchar(16),
  ADD COLUMN end_reason varchar(32),
  ADD COLUMN coverage_json jsonb,
  ADD COLUMN revision bigint,
  ADD COLUMN expires_at timestamptz(6),
  ADD CONSTRAINT ck_episode_state CHECK (state IN ('open','closed','interrupted')),
  ADD CONSTRAINT ck_episode_revision CHECK (revision IS NULL OR revision>0),
  ADD CONSTRAINT ck_episode_end_reason CHECK (state IS NULL OR
    (state='open' AND end_reason IS NULL) OR
    (state IN ('closed','interrupted') AND end_reason IS NOT NULL AND
      end_reason IN ('normal','observation_interrupted','cancelled')));
ALTER TABLE public.episode_tracklet_link
  ADD COLUMN ordinal integer,
  ADD CONSTRAINT ck_episode_track_ordinal CHECK (ordinal IS NULL OR ordinal>=0);
ALTER TABLE public.llm_report
  ADD COLUMN subject_kind varchar(16),
  ADD COLUMN subject_id uuid,
  ADD COLUMN event_id uuid,
  ADD COLUMN query_id uuid,
  ADD COLUMN report_type varchar(64),
  ADD COLUMN completeness varchar(16),
  ADD COLUMN coverage_json jsonb,
  ADD COLUMN task_id uuid,
  ADD COLUMN run_id uuid,
  ADD COLUMN model_version varchar(128),
  ADD COLUMN processed_at timestamptz(6),
  ADD COLUMN revision bigint,
  ADD COLUMN expires_at timestamptz(6),
  ADD CONSTRAINT uk_report_business_subject UNIQUE (subject_kind,subject_id,report_type),
  ADD CONSTRAINT ck_report_revision CHECK (revision IS NULL OR revision>0),
  ADD CONSTRAINT ck_report_completeness CHECK (completeness IN ('partial','complete')),
  ADD CONSTRAINT ck_report_subject CHECK (
    (subject_kind IS NULL AND subject_id IS NULL AND report_type IS NULL AND event_id IS NULL AND query_id IS NULL) OR
    (subject_kind IS NOT NULL AND subject_id IS NOT NULL AND report_type IS NOT NULL AND (
      (subject_kind='activity' AND episode_id IS NOT NULL AND episode_id=subject_id AND event_id IS NULL AND query_id IS NULL) OR
      (subject_kind='event' AND event_id IS NOT NULL AND event_id=subject_id AND episode_id IS NULL AND query_id IS NULL) OR
      (subject_kind='query' AND query_id IS NOT NULL AND query_id=subject_id AND episode_id IS NULL AND event_id IS NULL) OR
      (subject_kind='legacy' AND subject_id=id AND episode_id IS NULL AND event_id IS NULL AND query_id IS NULL))));

CREATE TABLE public.identity (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  identity_kind varchar(16) NOT NULL,
  object_type varchar(64) NOT NULL,
  display_no bigint NOT NULL DEFAULT nextval('public.identity_display_no_seq'),
  display_name varchar(200),
  employee_id varchar(64),
  registered_at timestamptz(6),
  first_seen_at timestamptz(6),
  last_seen_at timestamptz(6),
  enabled boolean NOT NULL DEFAULT true,
  revision bigint NOT NULL DEFAULT 1,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  updated_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6),
  PRIMARY KEY (id),
  UNIQUE (display_no),
  CHECK (identity_kind IN ('temporary','registered')),
  CHECK ((identity_kind='temporary' AND registered_at IS NULL AND first_seen_at IS NOT NULL AND last_seen_at IS NOT NULL AND expires_at IS NOT NULL) OR (identity_kind='registered' AND registered_at IS NOT NULL)),
  CHECK ((first_seen_at IS NULL AND last_seen_at IS NULL) OR (first_seen_at IS NOT NULL AND last_seen_at IS NOT NULL AND last_seen_at>=first_seen_at)),
  CHECK (revision>0)
);
CREATE INDEX ix_identity_kind_expiry ON public.identity (identity_kind, expires_at);
CREATE INDEX ix_identity_name ON public.identity (display_name);

CREATE TABLE public.identity_link (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  temporary_identity_id uuid NOT NULL,
  registered_identity_id uuid NOT NULL,
  valid_from timestamptz(6) NOT NULL,
  valid_to timestamptz(6),
  basis_type varchar(32) NOT NULL,
  score double precision,
  run_id uuid,
  reason text,
  revision bigint NOT NULL DEFAULT 1,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6) NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT ck_identity_link_revision CHECK (revision>0),
  CHECK (temporary_identity_id<>registered_identity_id),
  CHECK (valid_to IS NULL OR valid_to>=valid_from)
);
CREATE UNIQUE INDEX uk_identity_link_current ON public.identity_link (temporary_identity_id) WHERE valid_to IS NULL;
CREATE INDEX ix_identity_link_registered ON public.identity_link (registered_identity_id);

CREATE TABLE public.track_identity_assignment (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  tracklet_id uuid NOT NULL,
  identity_id uuid NOT NULL,
  valid_from timestamptz(6) NOT NULL,
  valid_to timestamptz(6),
  basis_type varchar(32) NOT NULL,
  score double precision,
  run_id uuid,
  reason text,
  revision bigint NOT NULL DEFAULT 1,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6) NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT ck_track_identity_assignment_revision CHECK (revision>0),
  CHECK (valid_to IS NULL OR valid_to>=valid_from)
);
CREATE UNIQUE INDEX uk_assignment_current ON public.track_identity_assignment (tracklet_id) WHERE valid_to IS NULL;
CREATE INDEX ix_assignment_identity ON public.track_identity_assignment (identity_id, tracklet_id);

CREATE TABLE public.legacy_identity_map (
  legacy_namespace varchar(64) NOT NULL,
  legacy_id varchar(128) NOT NULL,
  identity_id uuid NOT NULL,
  sample_id uuid,
  feature_space_id varchar(128),
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  PRIMARY KEY (legacy_namespace, legacy_id)
);
CREATE INDEX ix_legacy_identity ON public.legacy_identity_map (identity_id);

CREATE TABLE public.sample (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  purpose varchar(16) NOT NULL,
  asset_id uuid NOT NULL,
  input_frame_id uuid,
  tracklet_id uuid,
  identity_id uuid,
  query_id uuid,
  occurred_at timestamptz(6) NOT NULL,
  bbox_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  quality_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  available boolean NOT NULL DEFAULT true,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6),
  PRIMARY KEY (id),
  CHECK (purpose IN ('history','enrollment','query','evidence')),
  CHECK (purpose='enrollment' OR expires_at IS NOT NULL)
);
CREATE INDEX ix_sample_track_time ON public.sample (tracklet_id, occurred_at);
CREATE INDEX ix_sample_identity ON public.sample (identity_id, purpose);
CREATE INDEX ix_sample_expiry ON public.sample (expires_at);
CREATE INDEX ix_sample_asset ON public.sample (asset_id);
CREATE INDEX ix_sample_frame ON public.sample (input_frame_id) WHERE input_frame_id IS NOT NULL;

CREATE TABLE public.feature_space (
  id varchar(128) NOT NULL,
  definition_sha256 char(64) NOT NULL,
  definition_version varchar(32) NOT NULL,
  definition_text text NOT NULL,
  definition_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  object_type varchar(64) NOT NULL,
  feature_kind varchar(32) NOT NULL,
  dimensions integer NOT NULL,
  dtype varchar(16) NOT NULL DEFAULT 'float32',
  normalization varchar(16) NOT NULL,
  metric varchar(16) NOT NULL,
  enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  PRIMARY KEY (id),
  UNIQUE (definition_sha256),
  UNIQUE (id, dimensions),
  CHECK (dimensions>0),
  CHECK (dtype='float32'),
  CHECK (normalization IN ('l2','none')),
  CHECK (metric IN ('cosine','l2','inner_product'))
);


CREATE TABLE public.feature (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  feature_space_id varchar(128) NOT NULL,
  dimensions integer NOT NULL,
  embedding vector NOT NULL,
  sample_id uuid,
  tracklet_id uuid,
  identity_id uuid,
  run_id uuid NOT NULL,
  producer_feature_key varchar(128) NOT NULL,
  aggregation_method varchar(32) NOT NULL,
  input_count integer NOT NULL,
  used_count integer NOT NULL,
  state varchar(16) NOT NULL DEFAULT 'ready',
  processed_at timestamptz(6) NOT NULL,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6),
  PRIMARY KEY (id),
  UNIQUE (run_id, producer_feature_key),
  CHECK (dimensions>0 AND vector_dims(embedding)=dimensions),
  CHECK (input_count>=used_count AND used_count>0),
  CHECK (aggregation_method IN ('single','mean_l2_v1')),
  CHECK ((aggregation_method='single' AND sample_id IS NOT NULL AND used_count=1) OR (aggregation_method='mean_l2_v1' AND sample_id IS NULL)),
  CHECK (state IN ('ready','invalid'))
);
CREATE INDEX ix_feature_space_state_expiry ON public.feature (feature_space_id, state, expires_at);
CREATE INDEX ix_feature_identity ON public.feature (identity_id, feature_space_id);
CREATE INDEX ix_feature_track ON public.feature (tracklet_id, feature_space_id);
CREATE INDEX ix_feature_sample ON public.feature (sample_id) WHERE sample_id IS NOT NULL;

CREATE TABLE public.feature_contribution (
  feature_id uuid NOT NULL,
  ordinal integer NOT NULL,
  sample_id uuid NOT NULL,
  source_feature_id uuid,
  weight double precision NOT NULL DEFAULT 1,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  PRIMARY KEY (feature_id, ordinal),
  UNIQUE (feature_id, sample_id),
  CHECK (ordinal>=0 AND weight=1)
);
CREATE INDEX ix_contribution_sample ON public.feature_contribution (sample_id, feature_id);
CREATE INDEX ix_contribution_source_feature ON public.feature_contribution (source_feature_id) WHERE source_feature_id IS NOT NULL;

CREATE TABLE public.business_event (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  event_type varchar(64) NOT NULL,
  event_key varchar(128) NOT NULL,
  source_id uuid,
  start_at timestamptz(6) NOT NULL,
  end_at timestamptz(6),
  state varchar(16) NOT NULL DEFAULT 'open',
  end_reason varchar(32),
  conclusion_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  legacy_vad_id integer,
  run_id uuid,
  coverage_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  revision bigint NOT NULL DEFAULT 1,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  updated_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6) NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT ck_business_event_revision CHECK (revision>0),
  UNIQUE (event_type, event_key),
  UNIQUE (legacy_vad_id),
  CHECK (end_at IS NULL OR end_at>=start_at),
  CHECK (state IN ('open','closed','interrupted')),
  CHECK (end_reason IS NULL OR end_reason IN ('normal','observation_interrupted','cancelled')),
  CHECK ((state='open' AND end_reason IS NULL) OR (state IN ('closed','interrupted') AND end_at IS NOT NULL AND end_reason IS NOT NULL AND end_reason IN ('normal','observation_interrupted','cancelled')))
);
CREATE INDEX ix_event_type_time ON public.business_event (event_type, start_at, id);
CREATE INDEX ix_event_expiry ON public.business_event (expires_at);

CREATE TABLE public.event_object_link (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  event_id uuid NOT NULL,
  identity_id uuid,
  tracklet_id uuid,
  sample_id uuid,
  object_role varchar(32) NOT NULL DEFAULT 'subject',
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6) NOT NULL,
  PRIMARY KEY (id),
  CHECK (num_nonnulls(identity_id,tracklet_id,sample_id)=1)
);
CREATE UNIQUE INDEX uk_event_object_identity ON public.event_object_link (event_id, identity_id, object_role) WHERE identity_id IS NOT NULL;
CREATE UNIQUE INDEX uk_event_object_track ON public.event_object_link (event_id, tracklet_id, object_role) WHERE tracklet_id IS NOT NULL;
CREATE UNIQUE INDEX uk_event_object_sample ON public.event_object_link (event_id, sample_id, object_role) WHERE sample_id IS NOT NULL;
CREATE INDEX ix_event_object_identity ON public.event_object_link (identity_id, event_id) WHERE identity_id IS NOT NULL;
CREATE INDEX ix_event_object_track ON public.event_object_link (tracklet_id, event_id) WHERE tracklet_id IS NOT NULL;
CREATE INDEX ix_event_object_sample ON public.event_object_link (sample_id, event_id) WHERE sample_id IS NOT NULL;

CREATE TABLE public.evidence_reference (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  activity_id uuid,
  event_id uuid,
  source_id uuid,
  asset_id uuid,
  original_tracklet_id uuid,
  original_result_id uuid,
  start_at timestamptz(6) NOT NULL,
  end_at timestamptz(6),
  fact_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  provenance_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6) NOT NULL,
  PRIMARY KEY (id),
  CHECK (num_nonnulls(activity_id,event_id)=1),
  CHECK (end_at IS NULL OR end_at>=start_at),
  CHECK (asset_id IS NOT NULL OR fact_snapshot<>'{}'::jsonb)
);
CREATE INDEX ix_evidence_activity ON public.evidence_reference (activity_id);
CREATE INDEX ix_evidence_event ON public.evidence_reference (event_id);

CREATE TABLE public.report_evidence_link (
  report_id uuid NOT NULL,
  evidence_id uuid NOT NULL,
  report_revision bigint NOT NULL,
  ordinal integer NOT NULL,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  PRIMARY KEY (report_id, evidence_id),
  UNIQUE (report_id, ordinal),
  CHECK (report_revision>0 AND ordinal>=0)
);
CREATE INDEX ix_report_evidence_reverse ON public.report_evidence_link (evidence_id);

CREATE TABLE public.query_request (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  owner_user_id bigint NOT NULL,
  session_id uuid,
  query_kind varchar(32) NOT NULL,
  object_type varchar(64) NOT NULL DEFAULT 'person',
  input_asset_id uuid,
  input_sample_id uuid,
  selected_candidate_id varchar(32),
  identity_id uuid,
  feature_space_id varchar(128),
  start_at timestamptz(6),
  end_at timestamptz(6),
  scope_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  state varchar(24) NOT NULL DEFAULT 'pending',
  coverage_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  task_id uuid,
  revision bigint NOT NULL DEFAULT 1,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  updated_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6) NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT ck_query_stage2_session CHECK (session_id IS NULL),
  CONSTRAINT ck_query_request_revision CHECK (revision>0),
  CHECK (end_at IS NULL OR start_at IS NULL OR end_at>start_at),
  CHECK (state IN ('pending','running','waiting_input','succeeded','partial','failed','cancelled','expired'))
);
CREATE INDEX ix_query_owner_time ON public.query_request (owner_user_id, created_at, id);

CREATE TABLE public.query_candidate (
  query_id uuid NOT NULL,
  candidate_id varchar(32) NOT NULL,
  sample_id uuid NOT NULL,
  object_type varchar(64) NOT NULL,
  bbox_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  confidence double precision NOT NULL,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6) NOT NULL,
  PRIMARY KEY (query_id, candidate_id),
  CHECK (confidence>=0 AND confidence<=1)
);
CREATE INDEX ix_query_candidate_sample ON public.query_candidate (sample_id);

CREATE TABLE public.search_hit (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  query_id uuid NOT NULL,
  rank_no integer NOT NULL,
  hit_kind varchar(16) NOT NULL,
  identity_id uuid,
  tracklet_id uuid,
  sample_id uuid NOT NULL,
  feature_id uuid,
  feature_space_id varchar(128),
  score double precision,
  score_metric varchar(32),
  basis_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE (query_id, rank_no),
  CHECK (rank_no>0),
  CHECK (hit_kind IN ('gallery','historical'))
);
CREATE INDEX ix_search_hit_identity ON public.search_hit (identity_id, query_id);
CREATE INDEX ix_search_hit_sample ON public.search_hit (sample_id);

-- All new objects exist before cyclic and cross-table references are installed.
ALTER TABLE public.identity_link ADD CONSTRAINT fk_il_temp FOREIGN KEY (temporary_identity_id) REFERENCES public.identity (id) ON DELETE RESTRICT;
ALTER TABLE public.identity_link ADD CONSTRAINT fk_il_reg FOREIGN KEY (registered_identity_id) REFERENCES public.identity (id) ON DELETE RESTRICT;
ALTER TABLE public.identity_link ADD CONSTRAINT fk_il_run FOREIGN KEY (run_id) REFERENCES public.task_attempt (run_id) ON DELETE SET NULL;
ALTER TABLE public.track_identity_assignment ADD CONSTRAINT fk_tia_track FOREIGN KEY (tracklet_id) REFERENCES public.tracklet (id) ON DELETE RESTRICT;
ALTER TABLE public.track_identity_assignment ADD CONSTRAINT fk_tia_identity FOREIGN KEY (identity_id) REFERENCES public.identity (id) ON DELETE RESTRICT;
ALTER TABLE public.track_identity_assignment ADD CONSTRAINT fk_tia_run FOREIGN KEY (run_id) REFERENCES public.task_attempt (run_id) ON DELETE SET NULL;
ALTER TABLE public.legacy_identity_map ADD CONSTRAINT fk_lim_identity FOREIGN KEY (identity_id) REFERENCES public.identity (id) ON DELETE RESTRICT;
ALTER TABLE public.legacy_identity_map ADD CONSTRAINT fk_lim_sample FOREIGN KEY (sample_id) REFERENCES public.sample (id) ON DELETE SET NULL;
ALTER TABLE public.legacy_identity_map ADD CONSTRAINT fk_lim_space FOREIGN KEY (feature_space_id) REFERENCES public.feature_space (id) ON DELETE RESTRICT;
ALTER TABLE public.sample ADD CONSTRAINT fk_sample_asset FOREIGN KEY (asset_id) REFERENCES public.media_asset (id) ON DELETE RESTRICT;
ALTER TABLE public.sample ADD CONSTRAINT fk_sample_frame FOREIGN KEY (input_frame_id) REFERENCES public.input_frame (id) ON DELETE SET NULL;
ALTER TABLE public.sample ADD CONSTRAINT fk_sample_track FOREIGN KEY (tracklet_id) REFERENCES public.tracklet (id) ON DELETE SET NULL;
ALTER TABLE public.sample ADD CONSTRAINT fk_sample_identity FOREIGN KEY (identity_id) REFERENCES public.identity (id) ON DELETE SET NULL;
ALTER TABLE public.sample ADD CONSTRAINT fk_sample_query FOREIGN KEY (query_id) REFERENCES public.query_request (id) ON DELETE SET NULL;
ALTER TABLE public.feature ADD CONSTRAINT fk_feature_space FOREIGN KEY (feature_space_id, dimensions) REFERENCES public.feature_space (id, dimensions) ON DELETE RESTRICT;
ALTER TABLE public.feature ADD CONSTRAINT fk_feature_sample FOREIGN KEY (sample_id) REFERENCES public.sample (id) ON DELETE RESTRICT;
ALTER TABLE public.feature ADD CONSTRAINT fk_feature_track FOREIGN KEY (tracklet_id) REFERENCES public.tracklet (id) ON DELETE SET NULL;
ALTER TABLE public.feature ADD CONSTRAINT fk_feature_identity FOREIGN KEY (identity_id) REFERENCES public.identity (id) ON DELETE SET NULL;
ALTER TABLE public.feature ADD CONSTRAINT fk_feature_run FOREIGN KEY (run_id) REFERENCES public.task_attempt (run_id) ON DELETE RESTRICT;
ALTER TABLE public.feature_contribution ADD CONSTRAINT fk_contrib_feature FOREIGN KEY (feature_id) REFERENCES public.feature (id) ON DELETE RESTRICT;
ALTER TABLE public.feature_contribution ADD CONSTRAINT fk_contrib_sample FOREIGN KEY (sample_id) REFERENCES public.sample (id) ON DELETE RESTRICT;
ALTER TABLE public.feature_contribution ADD CONSTRAINT fk_contrib_source_feature FOREIGN KEY (source_feature_id) REFERENCES public.feature (id) ON DELETE RESTRICT;
ALTER TABLE public.business_event ADD CONSTRAINT fk_event_source FOREIGN KEY (source_id) REFERENCES public.camera (id) ON DELETE RESTRICT;
ALTER TABLE public.business_event ADD CONSTRAINT fk_event_vad FOREIGN KEY (legacy_vad_id) REFERENCES public.vad (id) ON DELETE RESTRICT;
ALTER TABLE public.business_event ADD CONSTRAINT fk_event_run FOREIGN KEY (run_id) REFERENCES public.task_attempt (run_id) ON DELETE SET NULL;
ALTER TABLE public.evidence_reference ADD CONSTRAINT fk_evidence_activity FOREIGN KEY (activity_id) REFERENCES public.episode (id) ON DELETE RESTRICT;
ALTER TABLE public.evidence_reference ADD CONSTRAINT fk_evidence_event FOREIGN KEY (event_id) REFERENCES public.business_event (id) ON DELETE RESTRICT;
ALTER TABLE public.evidence_reference ADD CONSTRAINT fk_evidence_source FOREIGN KEY (source_id) REFERENCES public.camera (id) ON DELETE RESTRICT;
ALTER TABLE public.evidence_reference ADD CONSTRAINT fk_evidence_asset FOREIGN KEY (asset_id) REFERENCES public.media_asset (id) ON DELETE RESTRICT;
ALTER TABLE public.evidence_reference ADD CONSTRAINT fk_evidence_track FOREIGN KEY (original_tracklet_id) REFERENCES public.tracklet (id) ON DELETE SET NULL;
ALTER TABLE public.evidence_reference ADD CONSTRAINT fk_evidence_result FOREIGN KEY (original_result_id) REFERENCES public.algorithm_result (id) ON DELETE SET NULL;
ALTER TABLE public.asset_reference ADD CONSTRAINT fk_asset_ref_sample FOREIGN KEY (sample_id) REFERENCES public.sample (id) ON DELETE RESTRICT;
ALTER TABLE public.asset_reference ADD CONSTRAINT fk_asset_ref_evidence FOREIGN KEY (evidence_id) REFERENCES public.evidence_reference (id) ON DELETE RESTRICT;
ALTER TABLE public.asset_reference ADD CONSTRAINT fk_asset_ref_query FOREIGN KEY (query_id) REFERENCES public.query_request (id) ON DELETE RESTRICT;
ALTER TABLE public.asset_reference ADD CONSTRAINT fk_asset_ref_identity FOREIGN KEY (identity_id) REFERENCES public.identity (id) ON DELETE RESTRICT;
ALTER TABLE public.report_evidence_link ADD CONSTRAINT fk_report_evidence_report FOREIGN KEY (report_id) REFERENCES public.llm_report (id) ON DELETE RESTRICT;
ALTER TABLE public.report_evidence_link ADD CONSTRAINT fk_report_evidence_evidence FOREIGN KEY (evidence_id) REFERENCES public.evidence_reference (id) ON DELETE RESTRICT;
ALTER TABLE public.query_request ADD CONSTRAINT fk_query_asset FOREIGN KEY (input_asset_id) REFERENCES public.media_asset (id) ON DELETE RESTRICT;
ALTER TABLE public.query_request ADD CONSTRAINT fk_query_sample FOREIGN KEY (input_sample_id) REFERENCES public.sample (id) ON DELETE SET NULL;
ALTER TABLE public.query_request ADD CONSTRAINT fk_query_identity FOREIGN KEY (identity_id) REFERENCES public.identity (id) ON DELETE SET NULL;
ALTER TABLE public.query_request ADD CONSTRAINT fk_query_space FOREIGN KEY (feature_space_id) REFERENCES public.feature_space (id) ON DELETE RESTRICT;
ALTER TABLE public.query_request ADD CONSTRAINT fk_query_task FOREIGN KEY (task_id) REFERENCES public.business_task (task_id) ON DELETE SET NULL;
ALTER TABLE public.query_candidate ADD CONSTRAINT fk_candidate_query FOREIGN KEY (query_id) REFERENCES public.query_request (id) ON DELETE RESTRICT;
ALTER TABLE public.query_candidate ADD CONSTRAINT fk_candidate_sample FOREIGN KEY (sample_id) REFERENCES public.sample (id) ON DELETE RESTRICT;
ALTER TABLE public.search_hit ADD CONSTRAINT fk_hit_query FOREIGN KEY (query_id) REFERENCES public.query_request (id) ON DELETE RESTRICT;
ALTER TABLE public.search_hit ADD CONSTRAINT fk_hit_identity FOREIGN KEY (identity_id) REFERENCES public.identity (id) ON DELETE SET NULL;
ALTER TABLE public.search_hit ADD CONSTRAINT fk_hit_track FOREIGN KEY (tracklet_id) REFERENCES public.tracklet (id) ON DELETE SET NULL;
ALTER TABLE public.search_hit ADD CONSTRAINT fk_hit_sample FOREIGN KEY (sample_id) REFERENCES public.sample (id) ON DELETE RESTRICT;
ALTER TABLE public.search_hit ADD CONSTRAINT fk_hit_feature FOREIGN KEY (feature_id) REFERENCES public.feature (id) ON DELETE SET NULL;
ALTER TABLE public.search_hit ADD CONSTRAINT fk_hit_space FOREIGN KEY (feature_space_id) REFERENCES public.feature_space (id) ON DELETE RESTRICT;
ALTER TABLE public.episode ADD CONSTRAINT fk_episode_identity FOREIGN KEY (identity_id) REFERENCES public.identity (id) ON DELETE RESTRICT;
ALTER TABLE public.llm_report ADD CONSTRAINT fk_report_event FOREIGN KEY (event_id) REFERENCES public.business_event (id) ON DELETE RESTRICT;
ALTER TABLE public.llm_report ADD CONSTRAINT fk_report_query FOREIGN KEY (query_id) REFERENCES public.query_request (id) ON DELETE RESTRICT;
ALTER TABLE public.llm_report ADD CONSTRAINT fk_report_task FOREIGN KEY (task_id) REFERENCES public.business_task (task_id) ON DELETE SET NULL;
ALTER TABLE public.llm_report ADD CONSTRAINT fk_report_run FOREIGN KEY (run_id) REFERENCES public.task_attempt (run_id) ON DELETE SET NULL;
ALTER TABLE public.query_request ADD CONSTRAINT fk_query_selected_candidate FOREIGN KEY (id, selected_candidate_id) REFERENCES public.query_candidate (query_id, candidate_id) ON DELETE RESTRICT;
ALTER TABLE public.event_object_link ADD CONSTRAINT fk_event_object_event FOREIGN KEY (event_id) REFERENCES public.business_event (id) ON DELETE RESTRICT;
ALTER TABLE public.event_object_link ADD CONSTRAINT fk_event_object_identity FOREIGN KEY (identity_id) REFERENCES public.identity (id) ON DELETE RESTRICT;
ALTER TABLE public.event_object_link ADD CONSTRAINT fk_event_object_track FOREIGN KEY (tracklet_id) REFERENCES public.tracklet (id) ON DELETE RESTRICT;
ALTER TABLE public.event_object_link ADD CONSTRAINT fk_event_object_sample FOREIGN KEY (sample_id) REFERENCES public.sample (id) ON DELETE RESTRICT;

ALTER SEQUENCE public.identity_display_no_seq OWNED BY public.identity.display_no;
CREATE UNIQUE INDEX uk_asset_ref_sample ON public.asset_reference (asset_id,sample_id) WHERE sample_id IS NOT NULL;
CREATE UNIQUE INDEX uk_asset_ref_evidence ON public.asset_reference (asset_id,evidence_id) WHERE evidence_id IS NOT NULL;
CREATE UNIQUE INDEX uk_asset_ref_query ON public.asset_reference (asset_id,query_id) WHERE query_id IS NOT NULL;
CREATE UNIQUE INDEX uk_asset_ref_identity ON public.asset_reference (asset_id,identity_id) WHERE identity_id IS NOT NULL;
CREATE INDEX ix_asset_ref_sample ON public.asset_reference (sample_id) WHERE sample_id IS NOT NULL;
CREATE INDEX ix_asset_ref_evidence ON public.asset_reference (evidence_id) WHERE evidence_id IS NOT NULL;
CREATE INDEX ix_asset_ref_query ON public.asset_reference (query_id) WHERE query_id IS NOT NULL;
CREATE INDEX ix_asset_ref_identity ON public.asset_reference (identity_id) WHERE identity_id IS NOT NULL;
CREATE UNIQUE INDEX uk_episode_open_identity ON public.episode (identity_id,activity_type)
  WHERE state='open' AND identity_id IS NOT NULL;
CREATE INDEX ix_episode_identity_time ON public.episode (identity_id,start_ts);
CREATE INDEX ix_report_expiry ON public.llm_report (expires_at);
COMMIT;
