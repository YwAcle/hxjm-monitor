-- Synthetic legacy business tables supplement the stage-one path/UUID fixtures.
BEGIN;
CREATE TABLE public.episode (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), title text,
  start_ts timestamptz(6) NOT NULL, end_ts timestamptz(6) NOT NULL,
  target_id uuid, stranger_target_id uuid, meta jsonb
);
CREATE TABLE public.episode_tracklet_link (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), episode_id uuid NOT NULL,
  tracklet_id uuid NOT NULL, note text, created_at timestamptz(6) NOT NULL DEFAULT now(),
  UNIQUE (episode_id,tracklet_id),
  FOREIGN KEY (episode_id) REFERENCES public.episode(id) ON DELETE CASCADE,
  FOREIGN KEY (tracklet_id) REFERENCES public.tracklet(id) ON DELETE CASCADE
);
CREATE TABLE public.vad (
  id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  media_asset_id uuid NOT NULL REFERENCES public.media_asset(id), stream_id varchar,
  frame_vad_base64 text, anomaly_name varchar, anomaly_level integer
);
CREATE TABLE public.llm_report (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), episode_id uuid REFERENCES public.episode(id),
  vad_id integer REFERENCES public.vad(id), prompt_type text, prompt_version text,
  report_json jsonb NOT NULL, report_text text, created_at timestamptz(6) NOT NULL DEFAULT now(),
  CONSTRAINT ck_llm_report_source_exclusive CHECK ((episode_id IS NOT NULL) <> (vad_id IS NOT NULL))
);
INSERT INTO public.episode(id,title,start_ts,end_ts,meta) VALUES
 ('81000000-0000-4000-8000-000000000001','legacy synthetic activity',
  '2026-10-26T00:00:01Z','2026-10-26T00:00:02Z','{"legacy":true}');
INSERT INTO public.episode_tracklet_link(episode_id,tracklet_id) VALUES
 ('81000000-0000-4000-8000-000000000001','40000000-0000-4000-8000-000000000001');
INSERT INTO public.vad(media_asset_id,stream_id,anomaly_name,anomaly_level) VALUES
 ('30000000-0000-4000-8000-000000000001','live/camera_1','synthetic',1);
INSERT INTO public.llm_report(id,episode_id,prompt_type,report_json,report_text) VALUES
 ('82000000-0000-4000-8000-000000000001','81000000-0000-4000-8000-000000000001',
  'legacy','{"summary":"legacy fixture"}','legacy fixture');
COMMIT;
