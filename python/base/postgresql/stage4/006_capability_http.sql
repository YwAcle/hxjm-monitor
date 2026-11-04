\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '5s';
SELECT pg_advisory_xact_lock(hashtextextended('hxjm:capability-http-v1:migration',0));
CREATE TABLE IF NOT EXISTS public.capability_schema_migration(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());
SELECT NOT EXISTS(SELECT 1 FROM public.capability_schema_migration WHERE version='006_capability_http') AS apply \gset
\if :apply
ALTER TABLE public.capability_definition ADD COLUMN agent_json jsonb NOT NULL DEFAULT '{}';
ALTER TABLE public.capability_instance ADD COLUMN resource_scope jsonb, ADD COLUMN dispatch_mode text NOT NULL DEFAULT 'runtime_managed' CHECK(dispatch_mode IN ('runtime_managed','platform_managed')), ADD COLUMN execution_json jsonb NOT NULL DEFAULT '{}';
UPDATE public.capability_instance SET resource_scope=jsonb_build_object('scope_type','camera','resource_ids',to_jsonb(source_ids));
CREATE FUNCTION public.capability_legacy_scope() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.resource_scope IS NULL THEN NEW.resource_scope=jsonb_build_object('scope_type','camera','resource_ids',to_jsonb(NEW.source_ids)); END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER capability_legacy_scope BEFORE INSERT ON public.capability_instance FOR EACH ROW EXECUTE FUNCTION public.capability_legacy_scope();
ALTER TABLE public.capability_instance ALTER COLUMN resource_scope SET NOT NULL;
ALTER TABLE public.business_task ADD COLUMN execution_snapshot jsonb, ADD COLUMN dispatch_mode text NOT NULL DEFAULT 'runtime_managed', ADD COLUMN execution_namespace text NOT NULL DEFAULT 'legacy';
ALTER TABLE public.task_attempt ADD COLUMN executor_id text, ADD COLUMN execution_token uuid, ADD COLUMN send_phase text NOT NULL DEFAULT 'not_sent' CHECK(send_phase IN ('not_sent','sending'));
ALTER TABLE public.business_task DROP CONSTRAINT business_task_task_kind_business_key_key;
CREATE UNIQUE INDEX uk_task_business_namespace ON public.business_task(task_kind,business_key,execution_namespace);
CREATE INDEX ix_platform_pending ON public.business_task(execution_namespace,created_at) WHERE dispatch_mode='platform_managed' AND state='pending';
CREATE TABLE public.task_output(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), task_id uuid NOT NULL REFERENCES public.business_task(task_id), run_id uuid NOT NULL REFERENCES public.task_attempt(run_id),
 result_type varchar(64) NOT NULL, schema_version varchar(32) NOT NULL, payload_json jsonb NOT NULL, asset_id uuid REFERENCES public.media_asset(id),
 producer_result_key varchar(128) NOT NULL, payload_digest char(64) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(run_id,producer_result_key), FOREIGN KEY(result_type,schema_version) REFERENCES public.result_type(type_code,schema_version)
);
CREATE INDEX ix_task_output_page ON public.task_output(task_id,id);
INSERT INTO public.capability_schema_migration(version) VALUES('006_capability_http');
\endif
COMMIT;
