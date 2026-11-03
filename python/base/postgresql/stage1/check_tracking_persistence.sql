-- Read-only deployment preflight. Does not apply a migration or repair data.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '10s';
DO $check$
DECLARE item record;
BEGIN
  FOR item IN SELECT * FROM (VALUES
    ('camera','id'),('camera','enabled'),('camera_stream','camera_id'),
    ('stream_session','expires_at'),('stream_session','time_origin_at'),
    ('capability_definition','contract_json'),('capability_instance','implementation_version'),
    ('result_type','max_inline_bytes'),('business_task','input_json'),('business_task','last_input_at'),
    ('task_attempt','parameters_json'),('request_deduplication','request_digest'),
    ('outbox_event','aggregate_revision'),('tracking_context','context_key'),
    ('result_set','set_key'),('result_selection','range_start'),('input_frame','stream_pts_ms'),
    ('analysis_frame','payload_digest'),('detection_observation','observation_kind'),
    ('tracklet','tracking_context_id'),('tracklet','local_track_id'),('tracklet','end_reason'),
    ('tracklet','first_observed_at'),('tracklet','last_observed_at'),('tracklet','expires_at'),
    ('processing_coverage','coverage_key'),('processing_coverage','closed')
  ) AS required(table_name,column_name) LOOP
    IF NOT EXISTS (SELECT FROM pg_attribute WHERE attrelid=to_regclass('public.'||item.table_name)
      AND attname=item.column_name AND attnum>0 AND NOT attisdropped) THEN
      RAISE EXCEPTION 'Tracking persistence requires %.%; inspect migration state first',item.table_name,item.column_name;
    END IF;
  END LOOP;
  IF NOT EXISTS (SELECT FROM pg_indexes WHERE schemaname='public' AND tablename='tracklet'
    AND indexdef ILIKE 'CREATE UNIQUE INDEX%'
    AND indexdef LIKE '%(tracking_context_id, local_track_id)%') THEN
    RAISE EXCEPTION 'Tracking context/local ID unique index is missing';
  END IF;
END
$check$;
SELECT 'tracking persistence schema preflight passed' AS result;
ROLLBACK;
