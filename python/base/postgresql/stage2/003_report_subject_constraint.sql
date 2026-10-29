-- v0.2 reports use ck_report_subject for activity, event and query relations.
-- No report contents, identifiers or other constraints are changed.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='90s';
ALTER TABLE public.llm_report DROP CONSTRAINT IF EXISTS ck_llm_report_source_exclusive;
COMMIT;
