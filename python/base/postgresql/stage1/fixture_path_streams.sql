-- Isolated-test fixture: four legacy tables only; no historical/production records.
-- Requires an explicitly selected disposable database; refuses existing legacy tables.
BEGIN;
DO $fixture$
BEGIN
  IF EXISTS (SELECT FROM pg_class WHERE oid IN
    (to_regclass('public.camera'),to_regclass('public.camera_stream'),
     to_regclass('public.media_asset'),to_regclass('public.tracklet'))) THEN
    RAISE EXCEPTION 'stage1 fixture requires a fresh database without legacy tables';
  END IF;
END
$fixture$;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
CREATE TABLE "public"."camera" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "camera_code" text COLLATE "pg_catalog"."default" NOT NULL,
  "name" text COLLATE "pg_catalog"."default" NOT NULL,
  "location" text COLLATE "pg_catalog"."default",
  "vendor" text COLLATE "pg_catalog"."default",
  "model" text COLLATE "pg_catalog"."default",
  "stream_uri" text COLLATE "pg_catalog"."default",
  "timezone" text COLLATE "pg_catalog"."default",
  "calibration" jsonb,
  "meta" jsonb,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now()
);

CREATE TABLE "public"."camera_stream" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "camera_id" uuid NOT NULL,
  "stream_name" text COLLATE "pg_catalog"."default" NOT NULL,
  "task_type" text COLLATE "pg_catalog"."default" NOT NULL,
  "shm_name" text COLLATE "pg_catalog"."default",
  "zmq_addr" text COLLATE "pg_catalog"."default",
  "is_active" bool NOT NULL DEFAULT true,
  "meta" jsonb,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now()
);

CREATE TABLE "public"."media_asset" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "stream_id" varchar COLLATE "pg_catalog"."default" NOT NULL,
  "asset_type" text COLLATE "pg_catalog"."default" NOT NULL,
  "start_ts" timestamptz(6) NOT NULL,
  "duration_ms" int8 NOT NULL,
  "play_url" text COLLATE "pg_catalog"."default" NOT NULL,
  "oss_bucket" text COLLATE "pg_catalog"."default",
  "oss_key" text COLLATE "pg_catalog"."default",
  "content_type" text COLLATE "pg_catalog"."default",
  "meta" jsonb,
  "created_at" timestamptz(6) NOT NULL DEFAULT now()
);

CREATE TABLE "public"."tracklet" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "stream_id" varchar COLLATE "pg_catalog"."default" NOT NULL,
  "start_ts" timestamptz(6) NOT NULL,
  "end_ts" timestamptz(6),
  "cls_name" text COLLATE "pg_catalog"."default" NOT NULL,
  "color_rgb" int2[],
  "query_asset_base64" text COLLATE "pg_catalog"."default",
  "frame_asset_base64" text COLLATE "pg_catalog"."default",
  "frame_end_base64" text COLLATE "pg_catalog"."default",
  "gallery_target_id" uuid,
  "gallery_similarity" float8,
  "stranger_target_id" uuid,
  "repr_embedding" "public"."vector",
  "embedding_model" text COLLATE "pg_catalog"."default",
  "trajectory_points" jsonb,
  "meta" jsonb,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now()
);
ALTER TABLE public.camera ADD CONSTRAINT camera_pkey PRIMARY KEY (id);
ALTER TABLE public.camera ADD CONSTRAINT camera_camera_code_key UNIQUE (camera_code);
ALTER TABLE public.camera_stream ADD CONSTRAINT camera_stream_pkey PRIMARY KEY (id);
ALTER TABLE public.camera_stream ADD CONSTRAINT camera_stream_stream_name_key UNIQUE (stream_name);
ALTER TABLE public.camera_stream ADD CONSTRAINT camera_stream_shm_name_key UNIQUE (shm_name);
ALTER TABLE public.camera_stream ADD CONSTRAINT chk_camera_stream_task_type CHECK
  (task_type IN ('reid','yolo','sam','pose','track','other'));
ALTER TABLE public.camera_stream ADD CONSTRAINT camera_stream_camera_id_fkey
  FOREIGN KEY (camera_id) REFERENCES public.camera(id) ON DELETE CASCADE;
ALTER TABLE public.media_asset ADD CONSTRAINT media_asset_pkey PRIMARY KEY (id);
ALTER TABLE public.media_asset ADD CONSTRAINT media_asset_duration_ms_check CHECK (duration_ms>=0);
ALTER TABLE public.media_asset ADD CONSTRAINT chk_media_asset_type CHECK
  (asset_type IN ('segment','clip','snapshot'));
ALTER TABLE public.tracklet ADD CONSTRAINT tracklet_pkey PRIMARY KEY (id);
ALTER TABLE public.tracklet ADD CONSTRAINT chk_tracklet_identity_oneof CHECK
  (NOT (gallery_target_id IS NOT NULL AND stranger_target_id IS NOT NULL));
CREATE INDEX idx_media_asset_stream_start ON public.media_asset(stream_id,start_ts);
CREATE INDEX idx_tracklet_stream_start ON public.tracklet(stream_id,start_ts);

-- Synthetic legacy records deliberately omit every stage-one column.
INSERT INTO public.camera(id,camera_code,name,timezone) VALUES
  ('10000000-0000-4000-8000-000000000001','camera_1','fixture camera 1','Asia/Shanghai');
INSERT INTO public.camera_stream(id,camera_id,stream_name,task_type) VALUES
  ('20000000-0000-4000-8000-000000000001','10000000-0000-4000-8000-000000000001',
   'live/camera_1','track');
INSERT INTO public.media_asset(id,stream_id,asset_type,start_ts,duration_ms,play_url,oss_key,content_type) VALUES
  ('30000000-0000-4000-8000-000000000001','live/camera_1','segment',
   '2026-10-26T00:00:00Z',60000,'https://media.example.invalid/legacy/recording',
   'recordings/fixture/legacy.mp4','video/mp4');
INSERT INTO public.tracklet(id,stream_id,start_ts,end_ts,cls_name,embedding_model,repr_embedding) VALUES
  ('40000000-0000-4000-8000-000000000001','live/camera_1',
   '2026-10-26T00:00:01Z','2026-10-26T00:00:02Z','person','fixture-legacy','[1,0,0]'::public.vector);
COMMIT;
