-- One durable observation of an external attempt; the existing task/attempt remains authoritative.
ALTER TABLE public.task_attempt ADD COLUMN external_execution jsonb;
CREATE INDEX ix_cleanup_event ON public.business_task((input_json->'input'->'payload'->>'event_id'))
 WHERE task_kind='garbage.cleanup';
