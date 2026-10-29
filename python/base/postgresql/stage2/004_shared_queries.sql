-- v0.2: NULL owner denotes the shared business query scope; private owners remain unchanged.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '90s';
ALTER TABLE public.query_request ALTER COLUMN owner_user_id DROP NOT NULL;
COMMENT ON COLUMN public.query_request.owner_user_id IS 'NULL: shared business query; non-NULL: existing user-owned query';
COMMIT;
