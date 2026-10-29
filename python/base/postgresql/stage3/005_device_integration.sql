-- HXJM v0.2 / 005: reviewed device persistence and typed near-term algorithm results.
-- Dependencies: existing stage1 + stage2 public tables. Preserve all old rows/IDs.
-- Re-running raw SQL intentionally fails and rolls back; inspect the schema before retrying.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='90s';
SET LOCAL search_path=pg_catalog,public;
SELECT pg_advisory_xact_lock(48584,5);
LOCK TABLE public.camera,public.result_set,public.asset_reference,public.result_type IN ACCESS EXCLUSIVE MODE;
CREATE TABLE public.device_registry (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  adapter_code varchar(64) NOT NULL,
  external_device_id varchar(128) NOT NULL,
  device_type varchar(32) NOT NULL,
  display_name varchar(128) NOT NULL,
  parent_device_id uuid,
  management_device_id bigint,
  config_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  enabled boolean NOT NULL DEFAULT true,
  revision bigint NOT NULL DEFAULT 1,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  updated_at timestamptz(6) NOT NULL DEFAULT now(),
  CONSTRAINT pk_device_registry PRIMARY KEY (id),
  CONSTRAINT uk_device_registry_external UNIQUE (adapter_code, external_device_id),
  CONSTRAINT fk_device_registry_parent FOREIGN KEY (parent_device_id) REFERENCES public.device_registry(id) ON DELETE RESTRICT,
  CHECK (parent_device_id IS NULL OR parent_device_id<>id),
  CHECK (management_device_id IS NULL OR management_device_id>0),
  CHECK (revision>0 AND btrim(adapter_code)<>'' AND btrim(external_device_id)<>'' AND btrim(device_type)<>'' AND btrim(display_name)<>''),
  CHECK (jsonb_typeof(config_json)='object')
);
CREATE INDEX ix_device_registry_parent ON public.device_registry(parent_device_id,id);

CREATE TABLE public.device_state_observation (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  device_id uuid NOT NULL,
  producer_session_key varchar(128) NOT NULL,
  producer_message_key varchar(128) NOT NULL,
  observed_at timestamptz(6) NOT NULL,
  received_at timestamptz(6) NOT NULL,
  time_quality varchar(24) NOT NULL,
  record_kind varchar(8) NOT NULL,
  state_code varchar(40) NOT NULL,
  schema_version varchar(32) NOT NULL DEFAULT '1',
  payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  payload_digest char(64) NOT NULL,
  task_id uuid,
  run_id uuid,
  expires_at timestamptz(6) NOT NULL,
  CONSTRAINT pk_device_state_observation PRIMARY KEY (id),
  CONSTRAINT uk_device_state_producer UNIQUE (device_id,producer_session_key,producer_message_key),
  CONSTRAINT fk_device_state_device FOREIGN KEY (device_id) REFERENCES public.device_registry(id) ON DELETE RESTRICT,
  CONSTRAINT fk_device_state_attempt FOREIGN KEY (task_id,run_id) REFERENCES public.task_attempt(task_id,run_id) ON DELETE RESTRICT,
  CHECK ((task_id IS NULL)=(run_id IS NULL)),
  CHECK (time_quality IN ('device_reported','received_estimated')),
  CHECK (record_kind IN ('change','sample')),
  CHECK (btrim(producer_session_key)<>'' AND btrim(producer_message_key)<>'' AND btrim(state_code)<>'' AND btrim(schema_version)<>''),
  CHECK (jsonb_typeof(payload_json)='object'),
  CHECK (payload_digest ~ '^[0-9a-f]{64}$'),
  CHECK (expires_at>observed_at)
);
CREATE INDEX ix_device_state_history ON public.device_state_observation(device_id,observed_at DESC,received_at DESC,id DESC);
CREATE INDEX ix_device_state_latest ON public.device_state_observation(device_id,received_at DESC,id DESC);
CREATE INDEX ix_device_state_expiry ON public.device_state_observation(expires_at,id);

CREATE TABLE public.device_task_binding (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  task_id uuid NOT NULL,
  run_id uuid NOT NULL,
  device_id uuid NOT NULL,
  dispatch_key varchar(128) NOT NULL,
  external_task_id varchar(128),
  dispatch_state varchar(16) NOT NULL DEFAULT 'pending',
  last_feedback_seq bigint NOT NULL DEFAULT 0,
  dispatched_at timestamptz(6),
  acknowledged_at timestamptz(6),
  revision bigint NOT NULL DEFAULT 1,
  created_at timestamptz(6) NOT NULL DEFAULT now(),
  updated_at timestamptz(6) NOT NULL DEFAULT now(),
  expires_at timestamptz(6) NOT NULL,
  CONSTRAINT pk_device_task_binding PRIMARY KEY (id),
  CONSTRAINT uk_device_task_run UNIQUE (run_id),
  CONSTRAINT uk_device_task_dispatch UNIQUE (device_id,dispatch_key),
  CONSTRAINT fk_device_task_attempt FOREIGN KEY (task_id,run_id) REFERENCES public.task_attempt(task_id,run_id) ON DELETE RESTRICT,
  CONSTRAINT fk_device_task_device FOREIGN KEY (device_id) REFERENCES public.device_registry(id) ON DELETE RESTRICT,
  CHECK (btrim(dispatch_key)<>'' AND (external_task_id IS NULL OR btrim(external_task_id)<>'')),
  CHECK (dispatch_state IN ('pending','sent','acknowledged','rejected')),
  CHECK (last_feedback_seq>=0 AND revision>0),
  CHECK (acknowledged_at IS NULL OR dispatched_at IS NULL OR acknowledged_at>=dispatched_at),
  CHECK (dispatch_state<>'acknowledged' OR (dispatched_at IS NOT NULL AND acknowledged_at IS NOT NULL))
);
CREATE INDEX ix_device_task_device_time ON public.device_task_binding(device_id,created_at DESC,id DESC);
CREATE INDEX ix_device_task_expiry ON public.device_task_binding(expires_at,id);

CREATE TABLE public.device_task_feedback (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  binding_id uuid NOT NULL,
  feedback_key varchar(128) NOT NULL,
  feedback_seq bigint NOT NULL,
  occurred_at timestamptz(6) NOT NULL,
  received_at timestamptz(6) NOT NULL,
  feedback_type varchar(16) NOT NULL,
  execution_state varchar(24),
  progress numeric(5,2),
  error_code varchar(64),
  error_message text,
  schema_version varchar(32) NOT NULL DEFAULT '1',
  payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  payload_digest char(64) NOT NULL,
  expires_at timestamptz(6) NOT NULL,
  CONSTRAINT pk_device_task_feedback PRIMARY KEY (id),
  CONSTRAINT uk_device_feedback_key UNIQUE (binding_id,feedback_key),
  CONSTRAINT uk_device_feedback_seq UNIQUE (binding_id,feedback_seq),
  CONSTRAINT fk_device_feedback_binding FOREIGN KEY (binding_id) REFERENCES public.device_task_binding(id) ON DELETE RESTRICT,
  CHECK (feedback_seq>0 AND btrim(feedback_key)<>'' AND btrim(schema_version)<>''),
  CHECK (feedback_type IN ('accepted','started','progress','artifact','completed','failed','cancelled','rejected')),
  CHECK ((feedback_type IN ('accepted','artifact') AND execution_state IS NULL)
    OR (feedback_type IN ('started','progress') AND execution_state='running')
    OR (feedback_type='completed' AND execution_state IN ('succeeded','partial'))
    OR (feedback_type IN ('failed','rejected') AND execution_state='failed')
    OR (feedback_type='cancelled' AND execution_state='cancelled')),
  CHECK (progress IS NULL OR (progress>=0 AND progress<=100)),
  CHECK (jsonb_typeof(payload_json)='object'),
  CHECK (payload_digest ~ '^[0-9a-f]{64}$')
);
CREATE INDEX ix_device_feedback_order ON public.device_task_feedback(binding_id,feedback_seq,id);
CREATE INDEX ix_device_feedback_expiry ON public.device_task_feedback(expires_at,id);
ALTER TABLE public.device_task_feedback ADD CONSTRAINT ck_device_feedback_state_required
  CHECK (feedback_type IN ('accepted','artifact') OR execution_state IS NOT NULL);
ALTER TABLE public.camera ADD COLUMN device_id uuid;
ALTER TABLE public.camera ADD CONSTRAINT fk_camera_device FOREIGN KEY (device_id) REFERENCES public.device_registry(id) ON DELETE RESTRICT;
CREATE INDEX ix_camera_device ON public.camera(device_id,id) WHERE device_id IS NOT NULL;
ALTER TABLE public.result_set ADD COLUMN device_task_binding_id uuid;
ALTER TABLE public.result_set ADD CONSTRAINT fk_result_set_device_task FOREIGN KEY (device_task_binding_id) REFERENCES public.device_task_binding(id) ON DELETE RESTRICT;
CREATE INDEX ix_result_set_device_task ON public.result_set(device_task_binding_id,id) WHERE device_task_binding_id IS NOT NULL;
ALTER TABLE public.asset_reference ADD COLUMN device_task_feedback_id uuid;
ALTER TABLE public.asset_reference ADD CONSTRAINT fk_asset_ref_device_feedback FOREIGN KEY (device_task_feedback_id) REFERENCES public.device_task_feedback(id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX uk_asset_ref_device_feedback ON public.asset_reference(asset_id,device_task_feedback_id) WHERE device_task_feedback_id IS NOT NULL;
CREATE INDEX ix_asset_ref_device_feedback ON public.asset_reference(device_task_feedback_id) WHERE device_task_feedback_id IS NOT NULL;
-- Locate the reviewed six-owner expression, rather than guessing its constraint name.
DO $migration$
DECLARE old_name text; matches integer;
BEGIN
  SELECT count(*),min(conname::text) INTO matches,old_name
  FROM pg_constraint
  WHERE conrelid='public.asset_reference'::regclass AND contype='c'
    AND regexp_replace(pg_get_expr(conbin,conrelid),'[[:space:]()]','','g') =
        'num_nonnullssample_id,evidence_id,query_id,identity_id,message_id,result_id=1';
  IF matches<>1 THEN
    RAISE EXCEPTION 'Expected exactly one reviewed six-owner CHECK; found %; migration rolled back',matches;
  END IF;
  EXECUTE format('ALTER TABLE public.asset_reference DROP CONSTRAINT %I',old_name);
END $migration$;
ALTER TABLE public.asset_reference ADD CONSTRAINT ck_asset_ref_owner_v02_device
  CHECK (num_nonnulls(sample_id,evidence_id,query_id,identity_id,message_id,result_id,device_task_feedback_id)=1);
ALTER TABLE public.asset_reference ADD CONSTRAINT ck_asset_ref_device_retention
  CHECK (device_task_feedback_id IS NULL OR retain_until IS NOT NULL);

-- Register payload contracts only; no unverified algorithm instances or devices.
DO $contract$
BEGIN
  IF EXISTS (SELECT 1 FROM public.result_type WHERE type_code='behavior.assessment' AND schema_version='1'
    AND (json_schema<>'{"type":"object","additionalProperties":false,"required":["behavior_type","decision","description"],"properties":{"behavior_type":{"type":"string","enum":["fight","fall"]},"decision":{"type":"string","enum":["suspected","confirmed","rejected","insufficient_evidence"]},"description":{"type":"string","maxLength":4000},"score":{"anyOf":[{"type":"number"},{"type":"null"}]},"score_semantics":{"anyOf":[{"type":"string","minLength":1,"maxLength":128},{"type":"null"}]},"targets":{"type":"array","items":{"type":"object","additionalProperties":false,"required":["target_index","bbox"],"properties":{"target_index":{"type":"integer","minimum":0},"bbox":{"type":"array","minItems":4,"maxItems":4,"items":{"type":"number","minimum":0,"maximum":1},"description":"Normalized source-image xyxy; right>left and bottom>top need business validation."},"tracklet_id":{"type":"string","pattern":"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"}}}}},"anyOf":[{"not":{"required":["score"]}},{"required":["score"],"properties":{"score":{"type":"null"}}},{"required":["score","score_semantics"],"properties":{"score":{"type":"number"},"score_semantics":{"type":"string","minLength":1,"maxLength":128}}}]}'::jsonb OR max_inline_bytes<>1048576 OR NOT enabled)) THEN
    RAISE EXCEPTION 'Existing result contract conflicts with behavior.assessment/1; no overwrite';
  END IF;
END $contract$;
INSERT INTO public.result_type(type_code,schema_version,json_schema,max_inline_bytes,enabled)
VALUES ('behavior.assessment','1','{"type":"object","additionalProperties":false,"required":["behavior_type","decision","description"],"properties":{"behavior_type":{"type":"string","enum":["fight","fall"]},"decision":{"type":"string","enum":["suspected","confirmed","rejected","insufficient_evidence"]},"description":{"type":"string","maxLength":4000},"score":{"anyOf":[{"type":"number"},{"type":"null"}]},"score_semantics":{"anyOf":[{"type":"string","minLength":1,"maxLength":128},{"type":"null"}]},"targets":{"type":"array","items":{"type":"object","additionalProperties":false,"required":["target_index","bbox"],"properties":{"target_index":{"type":"integer","minimum":0},"bbox":{"type":"array","minItems":4,"maxItems":4,"items":{"type":"number","minimum":0,"maximum":1},"description":"Normalized source-image xyxy; right>left and bottom>top need business validation."},"tracklet_id":{"type":"string","pattern":"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"}}}}},"anyOf":[{"not":{"required":["score"]}},{"required":["score"],"properties":{"score":{"type":"null"}}},{"required":["score","score_semantics"],"properties":{"score":{"type":"number"},"score_semantics":{"type":"string","minLength":1,"maxLength":128}}}]}'::jsonb,1048576,true)
ON CONFLICT(type_code,schema_version) DO NOTHING;
DO $contract$
BEGIN
  IF EXISTS (SELECT 1 FROM public.result_type WHERE type_code='garbage.detection' AND schema_version='1'
    AND (json_schema<>'{"type":"object","additionalProperties":false,"required":["has_target","targets"],"properties":{"has_target":{"type":"boolean"},"targets":{"type":"array","items":{"type":"object","additionalProperties":false,"required":["category","bbox"],"properties":{"category":{"type":"string","minLength":1,"maxLength":64},"bbox":{"type":"array","minItems":4,"maxItems":4,"items":{"type":"number","minimum":0,"maximum":1},"description":"Normalized source-image xyxy; right>left and bottom>top need business validation."},"confidence":{"type":"number","minimum":0,"maximum":1}}}},"scene_description":{"anyOf":[{"type":"string","maxLength":4000},{"type":"null"}]},"suggestion":{"anyOf":[{"type":"string","maxLength":4000},{"type":"null"}]}},"anyOf":[{"properties":{"has_target":{"enum":[false]},"targets":{"maxItems":0}}},{"properties":{"has_target":{"enum":[true]},"targets":{"minItems":1}}}]}'::jsonb OR max_inline_bytes<>1048576 OR NOT enabled)) THEN
    RAISE EXCEPTION 'Existing result contract conflicts with garbage.detection/1; no overwrite';
  END IF;
END $contract$;
INSERT INTO public.result_type(type_code,schema_version,json_schema,max_inline_bytes,enabled)
VALUES ('garbage.detection','1','{"type":"object","additionalProperties":false,"required":["has_target","targets"],"properties":{"has_target":{"type":"boolean"},"targets":{"type":"array","items":{"type":"object","additionalProperties":false,"required":["category","bbox"],"properties":{"category":{"type":"string","minLength":1,"maxLength":64},"bbox":{"type":"array","minItems":4,"maxItems":4,"items":{"type":"number","minimum":0,"maximum":1},"description":"Normalized source-image xyxy; right>left and bottom>top need business validation."},"confidence":{"type":"number","minimum":0,"maximum":1}}}},"scene_description":{"anyOf":[{"type":"string","maxLength":4000},{"type":"null"}]},"suggestion":{"anyOf":[{"type":"string","maxLength":4000},{"type":"null"}]}},"anyOf":[{"properties":{"has_target":{"enum":[false]},"targets":{"maxItems":0}}},{"properties":{"has_target":{"enum":[true]},"targets":{"minItems":1}}}]}'::jsonb,1048576,true)
ON CONFLICT(type_code,schema_version) DO NOTHING;

COMMENT ON TABLE public.device_registry IS 'HXJM v0.2；设备接入目录：一个实际设备或独立上报组件';
COMMENT ON COLUMN public.device_registry.id IS '设备稳定主键';
COMMENT ON COLUMN public.device_registry.adapter_code IS '已部署适配器命名空间，不是IP';
COMMENT ON COLUMN public.device_registry.external_device_id IS '该适配器中的设备稳定编号';
COMMENT ON COLUMN public.device_registry.device_type IS '已发布robot_dog、robot_arm等设备类型，不用每种设备新增主表';
COMMENT ON COLUMN public.device_registry.display_name IS '展示名称，不唯一';
COMMENT ON COLUMN public.device_registry.parent_device_id IS '父设备；不可指向自己，业务校验防循环';
COMMENT ON COLUMN public.device_registry.management_device_id IS '逻辑引用hxjm_sm.ba_machine.machine_id，正整数；对外十进制字符串';
COMMENT ON COLUMN public.device_registry.config_json IS 'v1配置对象，schema_version为字符串1；service_ref和credential_ref为可选1～128字符字符串，分别为已部署连接引用和凭据引用，state_sample_interval_seconds默认30，state_stale_after_seconds默认90；均为正整数且后者大于采样间隔';
COMMENT ON COLUMN public.device_registry.enabled IS '停用阻止新下发，不删除已执行任务／历史';
COMMENT ON COLUMN public.device_registry.revision IS '乐观锁，更新时expected_revision校验';
COMMENT ON COLUMN public.device_registry.created_at IS '首次登记时间';
COMMENT ON COLUMN public.device_registry.updated_at IS '有效修改时更新';
COMMENT ON TABLE public.device_state_observation IS 'HXJM v0.2；设备状态历史：一次保留的状态变化或周期采样';
COMMENT ON COLUMN public.device_state_observation.id IS '状态记录主键';
COMMENT ON COLUMN public.device_state_observation.device_id IS '设备或独立组件';
COMMENT ON COLUMN public.device_state_observation.producer_session_key IS '设备上报会话；适配器连接新编号空间时改变';
COMMENT ON COLUMN public.device_state_observation.producer_message_key IS '该会话内稳定消息键；同一上报重传不变';
COMMENT ON COLUMN public.device_state_observation.observed_at IS '设备真实观测时间；缺失时固定采用首次接收时间';
COMMENT ON COLUMN public.device_state_observation.received_at IS '主系统首次接收时间，重传不刷新';
COMMENT ON COLUMN public.device_state_observation.time_quality IS 'device_reported或received_estimated，不宣称时钟已精确同步';
COMMENT ON COLUMN public.device_state_observation.record_kind IS 'change或sample；同一上报同时命中时优先change';
COMMENT ON COLUMN public.device_state_observation.state_code IS '该设备类型已发布状态码；unknown表示设备确实上报未知';
COMMENT ON COLUMN public.device_state_observation.schema_version IS '设备状态载荷版本';
COMMENT ON COLUMN public.device_state_observation.payload_json IS '对象；可选battery_percent(0～100)、velocity_mps(有限数)、position({coordinate_system:非空字符串最多64字符,values:有限数数组})、joints_deg(有限数数组)、gripper；缺失不填零；位置无导航用途';
COMMENT ON COLUMN public.device_state_observation.payload_digest IS '设备、生产键、观测时间、状态及载荷等不可变业务内容摘要';
COMMENT ON COLUMN public.device_state_observation.task_id IS '实际明确的业务任务；与run_id同时提供或同时为空';
COMMENT ON COLUMN public.device_state_observation.run_id IS '实际执行；通过(task_id,run_id)校验归属，不凭接收时间猜测';
COMMENT ON COLUMN public.device_state_observation.expires_at IS 'observed_at+7天';
COMMENT ON TABLE public.device_task_binding IS 'HXJM v0.2；设备执行映射：一次公共执行对应一台执行设备';
COMMENT ON COLUMN public.device_task_binding.id IS '设备执行映射主键';
COMMENT ON COLUMN public.device_task_binding.task_id IS '公共巡检任务';
COMMENT ON COLUMN public.device_task_binding.run_id IS '该任务执行尝试；一次只绑定一台设备';
COMMENT ON COLUMN public.device_task_binding.device_id IS '实际执行设备';
COMMENT ON COLUMN public.device_task_binding.dispatch_key IS '设备命名空间内的下发幂等键，首次受理生成，重传不变';
COMMENT ON COLUMN public.device_task_binding.external_task_id IS '设备侧本次执行编号，首次下发可空，不是路线模板编号';
COMMENT ON COLUMN public.device_task_binding.dispatch_state IS 'pending/sent/acknowledged/rejected；只描述下发';
COMMENT ON COLUMN public.device_task_binding.last_feedback_seq IS '已用于更新执行状态的反馈序号水位，不是收到消息条数';
COMMENT ON COLUMN public.device_task_binding.dispatched_at IS '首次实际发送时刻';
COMMENT ON COLUMN public.device_task_binding.acknowledged_at IS '设备实际确认接收时刻';
COMMENT ON COLUMN public.device_task_binding.revision IS '状态更新CAS修订';
COMMENT ON COLUMN public.device_task_binding.created_at IS '首次创建';
COMMENT ON COLUMN public.device_task_binding.updated_at IS '有效更新时维护';
COMMENT ON COLUMN public.device_task_binding.expires_at IS '任务正常终态后按finished_at+7天固定；进行中维护控制目录期限';
COMMENT ON TABLE public.device_task_feedback IS 'HXJM v0.2；设备执行反馈：一次带稳定业务键及序号的反馈';
COMMENT ON COLUMN public.device_task_feedback.id IS '反馈主键';
COMMENT ON COLUMN public.device_task_feedback.binding_id IS '设备执行映射';
COMMENT ON COLUMN public.device_task_feedback.feedback_key IS '该绑定内稳定反馈键，重试不变';
COMMENT ON COLUMN public.device_task_feedback.feedback_seq IS '该绑定内从1递增序号，源版本或适配器稳定分配；不以HTTP到达时间替代已知源顺序';
COMMENT ON COLUMN public.device_task_feedback.occurred_at IS '设备执行发生时刻；缺失时采用首次接收估计，并在payload_json.time_quality声明';
COMMENT ON COLUMN public.device_task_feedback.received_at IS '首次接收时间';
COMMENT ON COLUMN public.device_task_feedback.feedback_type IS 'accepted/started/progress/artifact/completed/failed/cancelled/rejected';
COMMENT ON COLUMN public.device_task_feedback.execution_state IS '执行结论；accepted/artifact可空，其余按映射更新公共状态';
COMMENT ON COLUMN public.device_task_feedback.progress IS '0～100百分比，未提供为NULL';
COMMENT ON COLUMN public.device_task_feedback.error_code IS '明确设备错误码或适配器规范错误码';
COMMENT ON COLUMN public.device_task_feedback.error_message IS '脱敏说明，入口限4000字符';
COMMENT ON COLUMN public.device_task_feedback.schema_version IS '反馈结构版本';
COMMENT ON COLUMN public.device_task_feedback.payload_json IS 'v1对象：可选summary(string，最多4000字符)、stage(string，最多64字符)、time_quality(device_reported/received_estimated)(device_reported/received_estimated)；文件及结果ID通过公共关系读取，不藏私有路径';
COMMENT ON COLUMN public.device_task_feedback.payload_digest IS '绑定、反馈键／序号、原发生时间、状态、载荷和规范附件引用的摘要';
COMMENT ON COLUMN public.device_task_feedback.expires_at IS '终态按该执行finished_at+7天固定；进行中采用所属绑定控制期限';
COMMENT ON COLUMN public.camera.device_id IS '可空直接设备归属；保留原管理设备映射';
COMMENT ON COLUMN public.result_set.device_task_binding_id IS '可空巡检设备执行归属；不替代本成果的算法run_id';
COMMENT ON COLUMN public.asset_reference.device_task_feedback_id IS '可空设备反馈文件用途；七种用途恰好一个非空';
COMMIT;
