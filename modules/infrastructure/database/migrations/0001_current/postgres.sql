-- HXJM current baseline. Apply only through bootstrap.py.

-- Dumped from database version 16.11 (Debian 16.11-1.pgdg12+1)
-- Dumped by pg_dump version 16.11 (Debian 16.11-1.pgdg12+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', 'public', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

-- *not* creating schema, since initdb creates it

COMMENT ON SCHEMA public IS '';

CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;

COMMENT ON EXTENSION btree_gist IS 'support for indexing common datatypes in GiST';

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';

SET default_tablespace = '';

SET default_table_access_method = heap;

CREATE TABLE public.algorithm_result (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    result_set_id uuid NOT NULL,
    producer_result_key character varying(128) NOT NULL,
    result_type character varying(64) NOT NULL,
    schema_version character varying(32) NOT NULL,
    input_frame_id uuid,
    tracklet_id uuid,
    start_at timestamp(6) with time zone NOT NULL,
    end_at timestamp(6) with time zone,
    payload_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    payload_asset_id uuid,
    payload_digest character(64) NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT algorithm_result_check CHECK (((end_at IS NULL) OR (end_at >= start_at)))
);

CREATE TABLE public.analysis_frame (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    result_set_id uuid NOT NULL,
    input_frame_id uuid NOT NULL,
    producer_result_key character varying(128) NOT NULL,
    schema_version character varying(32) DEFAULT '1'::character varying NOT NULL,
    target_count integer NOT NULL,
    payload_digest character(64) NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT analysis_frame_target_count_check CHECK ((target_count >= 0))
);

CREATE TABLE public.asset_reference (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    asset_id uuid NOT NULL,
    sample_id uuid,
    evidence_id uuid,
    query_id uuid,
    identity_id uuid,
    message_id uuid,
    result_id uuid,
    retain_until timestamp(6) with time zone,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    device_task_feedback_id uuid,
    CONSTRAINT ck_asset_ref_device_retention CHECK (((device_task_feedback_id IS NULL) OR (retain_until IS NOT NULL))),
    CONSTRAINT ck_asset_ref_owner_v02_device CHECK ((num_nonnulls(sample_id, evidence_id, query_id, identity_id, message_id, result_id, device_task_feedback_id) = 1)),
    CONSTRAINT ck_asset_ref_retention CHECK (((retain_until IS NOT NULL) OR (identity_id IS NOT NULL) OR (sample_id IS NOT NULL))),
    CONSTRAINT ck_asset_ref_stage2_owner CHECK ((message_id IS NULL))
);

COMMENT ON COLUMN public.asset_reference.device_task_feedback_id IS '可空设备反馈文件用途；七种用途恰好一个非空';

CREATE TABLE public.business_event (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    event_type character varying(64) NOT NULL,
    event_key character varying(128) NOT NULL,
    source_id uuid,
    start_at timestamp(6) with time zone NOT NULL,
    end_at timestamp(6) with time zone,
    state character varying(16) DEFAULT 'open'::character varying NOT NULL,
    end_reason character varying(32),
    conclusion_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    legacy_vad_id integer,
    run_id uuid,
    coverage_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    revision bigint DEFAULT 1 NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    updated_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT business_event_check CHECK (((end_at IS NULL) OR (end_at >= start_at))),
    CONSTRAINT business_event_check1 CHECK (((((state)::text = 'open'::text) AND (end_reason IS NULL)) OR (((state)::text = ANY ((ARRAY['closed'::character varying, 'interrupted'::character varying])::text[])) AND (end_at IS NOT NULL) AND (end_reason IS NOT NULL) AND ((end_reason)::text = ANY ((ARRAY['normal'::character varying, 'observation_interrupted'::character varying, 'cancelled'::character varying])::text[]))))),
    CONSTRAINT business_event_end_reason_check CHECK (((end_reason IS NULL) OR ((end_reason)::text = ANY ((ARRAY['normal'::character varying, 'observation_interrupted'::character varying, 'cancelled'::character varying])::text[])))),
    CONSTRAINT business_event_state_check CHECK (((state)::text = ANY ((ARRAY['open'::character varying, 'closed'::character varying, 'interrupted'::character varying])::text[]))),
    CONSTRAINT ck_business_event_revision CHECK ((revision > 0))
);

CREATE TABLE public.business_task (
    execution_snapshot jsonb,
    dispatch_mode text NOT NULL DEFAULT 'runtime_managed' CHECK(dispatch_mode IN ('runtime_managed','platform_managed')),
    execution_namespace text NOT NULL DEFAULT 'runtime',
    task_id uuid DEFAULT gen_random_uuid() NOT NULL,
    task_kind character varying(64) NOT NULL,
    business_key character varying(256),
    task_mode character varying(16) DEFAULT 'once'::character varying NOT NULL,
    last_input_at timestamp(6) with time zone,
    actor_key character varying(128) NOT NULL,
    owner_user_id bigint,
    capability_code character varying(64),
    state character varying(24) DEFAULT 'pending'::character varying NOT NULL,
    input_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    input_digest character(64) NOT NULL,
    current_run_id uuid,
    generation bigint DEFAULT 0 NOT NULL,
    progress numeric(5,2) DEFAULT 0 NOT NULL,
    error_code character varying(64),
    error_message text,
    revision bigint DEFAULT 1 NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    updated_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT business_task_check CHECK (((generation >= 0) AND (progress >= (0)::numeric) AND (progress <= (100)::numeric) AND (revision > 0))),
    CONSTRAINT business_task_state_check CHECK (((state)::text = ANY ((ARRAY['pending'::character varying, 'running'::character varying, 'waiting_input'::character varying, 'succeeded'::character varying, 'partial'::character varying, 'failed'::character varying, 'cancelled'::character varying, 'expired'::character varying])::text[]))),
    CONSTRAINT business_task_task_mode_check CHECK (((task_mode)::text = ANY ((ARRAY['once'::character varying, 'continuous'::character varying])::text[])))
);

CREATE TABLE public.camera (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    camera_code text NOT NULL,
    name text NOT NULL,
    location text,
    vendor text,
    model text,
    stream_uri text,
    timezone text,
    calibration jsonb,
    meta jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    management_device_id bigint,
    channel_code character varying(64),
    source_kind character varying(24) DEFAULT 'camera'::character varying NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    device_id uuid,
    CONSTRAINT ck_camera_device_channel CHECK (((management_device_id IS NULL) = (channel_code IS NULL))),
    CONSTRAINT ck_camera_source_kind CHECK (((source_kind)::text = ANY ((ARRAY['camera'::character varying, 'device_video'::character varying, 'imported_video'::character varying])::text[])))
);

COMMENT ON COLUMN public.camera.device_id IS '可空直接设备归属；保留原管理设备映射';

CREATE TABLE public.camera_stream (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    camera_id uuid NOT NULL,
    stream_name text NOT NULL,
    task_type text NOT NULL,
    shm_name text,
    zmq_addr text,
    is_active boolean DEFAULT true NOT NULL,
    meta jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.capability_definition (
    agent_json jsonb NOT NULL DEFAULT '{}',
    capability_code character varying(64) NOT NULL,
    display_name character varying(128) NOT NULL,
    object_types text[] NOT NULL,
    input_kinds text[] NOT NULL,
    contract_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    revision bigint DEFAULT 1 NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    updated_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    CONSTRAINT capability_definition_check CHECK (((cardinality(object_types) > 0) AND (cardinality(input_kinds) > 0))),
    CONSTRAINT capability_definition_revision_check CHECK ((revision > 0))
);

CREATE TABLE public.capability_instance (
    resource_scope jsonb NOT NULL,
    dispatch_mode text NOT NULL DEFAULT 'runtime_managed' CHECK(dispatch_mode IN ('runtime_managed','platform_managed')),
    execution_json jsonb NOT NULL DEFAULT '{}',
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    capability_code character varying(64) NOT NULL,
    instance_key character varying(128) NOT NULL,
    implementation_code character varying(64) NOT NULL,
    implementation_version character varying(128) NOT NULL,
    source_ids uuid[] DEFAULT '{}'::uuid[] NOT NULL,
    service_ref character varying(256) NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    revision bigint DEFAULT 1 NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    updated_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_instance_keys CHECK (((char_length(btrim((instance_key)::text)) > 0) AND (char_length(btrim((implementation_code)::text)) > 0) AND (char_length(btrim((implementation_version)::text)) > 0) AND (char_length(btrim((service_ref)::text)) > 0))),
    CONSTRAINT ck_instance_revision CHECK ((revision > 0)),
    CONSTRAINT ck_instance_sources CHECK ((array_position(source_ids, NULL::uuid) IS NULL))
);

CREATE TABLE public.detection_observation (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    analysis_frame_id uuid NOT NULL,
    target_index integer NOT NULL,
    tracklet_id uuid,
    object_type character varying(64) NOT NULL,
    class_code character varying(64) NOT NULL,
    confidence double precision,
    observation_kind character varying(16) NOT NULL,
    bbox_left double precision NOT NULL,
    bbox_top double precision NOT NULL,
    bbox_right double precision NOT NULL,
    bbox_bottom double precision NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT detection_observation_check CHECK (((bbox_left >= (0)::double precision) AND (bbox_top >= (0)::double precision) AND (bbox_right <= (1)::double precision) AND (bbox_bottom <= (1)::double precision) AND (bbox_right > bbox_left) AND (bbox_bottom > bbox_top))),
    CONSTRAINT detection_observation_check1 CHECK (((target_index >= 0) AND ((confidence IS NULL) OR ((confidence >= (0)::double precision) AND (confidence <= (1)::double precision))))),
    CONSTRAINT detection_observation_check2 CHECK ((((observation_kind)::text = 'predicted'::text) OR (confidence IS NOT NULL))),
    CONSTRAINT detection_observation_observation_kind_check CHECK (((observation_kind)::text = ANY ((ARRAY['observed'::character varying, 'predicted'::character varying])::text[])))
);

CREATE TABLE public.device_registry (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    adapter_code character varying(64) NOT NULL,
    external_device_id character varying(128) NOT NULL,
    device_type character varying(32) NOT NULL,
    display_name character varying(128) NOT NULL,
    parent_device_id uuid,
    management_device_id bigint,
    config_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    revision bigint DEFAULT 1 NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    updated_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    CONSTRAINT device_registry_check CHECK (((parent_device_id IS NULL) OR (parent_device_id <> id))),
    CONSTRAINT device_registry_check1 CHECK (((revision > 0) AND (btrim((adapter_code)::text) <> ''::text) AND (btrim((external_device_id)::text) <> ''::text) AND (btrim((device_type)::text) <> ''::text) AND (btrim((display_name)::text) <> ''::text))),
    CONSTRAINT device_registry_config_json_check CHECK ((jsonb_typeof(config_json) = 'object'::text)),
    CONSTRAINT device_registry_management_device_id_check CHECK (((management_device_id IS NULL) OR (management_device_id > 0)))
);

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

CREATE TABLE public.device_state_observation (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    device_id uuid NOT NULL,
    producer_session_key character varying(128) NOT NULL,
    producer_message_key character varying(128) NOT NULL,
    observed_at timestamp(6) with time zone NOT NULL,
    received_at timestamp(6) with time zone NOT NULL,
    time_quality character varying(24) NOT NULL,
    record_kind character varying(8) NOT NULL,
    state_code character varying(40) NOT NULL,
    schema_version character varying(32) DEFAULT '1'::character varying NOT NULL,
    payload_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    payload_digest character(64) NOT NULL,
    task_id uuid,
    run_id uuid,
    expires_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT device_state_observation_check CHECK (((task_id IS NULL) = (run_id IS NULL))),
    CONSTRAINT device_state_observation_check1 CHECK (((btrim((producer_session_key)::text) <> ''::text) AND (btrim((producer_message_key)::text) <> ''::text) AND (btrim((state_code)::text) <> ''::text) AND (btrim((schema_version)::text) <> ''::text))),
    CONSTRAINT device_state_observation_check2 CHECK ((expires_at > observed_at)),
    CONSTRAINT device_state_observation_payload_digest_check CHECK ((payload_digest ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT device_state_observation_payload_json_check CHECK ((jsonb_typeof(payload_json) = 'object'::text)),
    CONSTRAINT device_state_observation_record_kind_check CHECK (((record_kind)::text = ANY ((ARRAY['change'::character varying, 'sample'::character varying])::text[]))),
    CONSTRAINT device_state_observation_time_quality_check CHECK (((time_quality)::text = ANY ((ARRAY['device_reported'::character varying, 'received_estimated'::character varying])::text[])))
);

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

CREATE TABLE public.device_task_binding (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    task_id uuid NOT NULL,
    run_id uuid NOT NULL,
    device_id uuid NOT NULL,
    dispatch_key character varying(128) NOT NULL,
    external_task_id character varying(128),
    dispatch_state character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    last_feedback_seq bigint DEFAULT 0 NOT NULL,
    dispatched_at timestamp(6) with time zone,
    acknowledged_at timestamp(6) with time zone,
    revision bigint DEFAULT 1 NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    updated_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT device_task_binding_check CHECK (((btrim((dispatch_key)::text) <> ''::text) AND ((external_task_id IS NULL) OR (btrim((external_task_id)::text) <> ''::text)))),
    CONSTRAINT device_task_binding_check1 CHECK (((last_feedback_seq >= 0) AND (revision > 0))),
    CONSTRAINT device_task_binding_check2 CHECK (((acknowledged_at IS NULL) OR (dispatched_at IS NULL) OR (acknowledged_at >= dispatched_at))),
    CONSTRAINT device_task_binding_check3 CHECK ((((dispatch_state)::text <> 'acknowledged'::text) OR ((dispatched_at IS NOT NULL) AND (acknowledged_at IS NOT NULL)))),
    CONSTRAINT device_task_binding_dispatch_state_check CHECK (((dispatch_state)::text = ANY ((ARRAY['pending'::character varying, 'sent'::character varying, 'acknowledged'::character varying, 'rejected'::character varying])::text[])))
);

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

CREATE TABLE public.device_task_feedback (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    binding_id uuid NOT NULL,
    feedback_key character varying(128) NOT NULL,
    feedback_seq bigint NOT NULL,
    occurred_at timestamp(6) with time zone NOT NULL,
    received_at timestamp(6) with time zone NOT NULL,
    feedback_type character varying(16) NOT NULL,
    execution_state character varying(24),
    progress numeric(5,2),
    error_code character varying(64),
    error_message text,
    schema_version character varying(32) DEFAULT '1'::character varying NOT NULL,
    payload_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    payload_digest character(64) NOT NULL,
    expires_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT ck_device_feedback_state_required CHECK ((((feedback_type)::text = ANY ((ARRAY['accepted'::character varying, 'artifact'::character varying])::text[])) OR (execution_state IS NOT NULL))),
    CONSTRAINT device_task_feedback_check CHECK (((feedback_seq > 0) AND (btrim((feedback_key)::text) <> ''::text) AND (btrim((schema_version)::text) <> ''::text))),
    CONSTRAINT device_task_feedback_check1 CHECK (((((feedback_type)::text = ANY ((ARRAY['accepted'::character varying, 'artifact'::character varying])::text[])) AND (execution_state IS NULL)) OR (((feedback_type)::text = ANY ((ARRAY['started'::character varying, 'progress'::character varying])::text[])) AND ((execution_state)::text = 'running'::text)) OR (((feedback_type)::text = 'completed'::text) AND ((execution_state)::text = ANY ((ARRAY['succeeded'::character varying, 'partial'::character varying])::text[]))) OR (((feedback_type)::text = ANY ((ARRAY['failed'::character varying, 'rejected'::character varying])::text[])) AND ((execution_state)::text = 'failed'::text)) OR (((feedback_type)::text = 'cancelled'::text) AND ((execution_state)::text = 'cancelled'::text)))),
    CONSTRAINT device_task_feedback_feedback_type_check CHECK (((feedback_type)::text = ANY ((ARRAY['accepted'::character varying, 'started'::character varying, 'progress'::character varying, 'artifact'::character varying, 'completed'::character varying, 'failed'::character varying, 'cancelled'::character varying, 'rejected'::character varying])::text[]))),
    CONSTRAINT device_task_feedback_payload_digest_check CHECK ((payload_digest ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT device_task_feedback_payload_json_check CHECK ((jsonb_typeof(payload_json) = 'object'::text)),
    CONSTRAINT device_task_feedback_progress_check CHECK (((progress IS NULL) OR ((progress >= (0)::numeric) AND (progress <= (100)::numeric))))
);

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

CREATE TABLE public.episode (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    title text,
    start_ts timestamp with time zone NOT NULL,
    end_ts timestamp with time zone NOT NULL,
    target_id uuid,
    stranger_target_id uuid,
    meta jsonb,
    identity_id uuid,
    activity_type character varying(64),
    state character varying(16),
    end_reason character varying(32),
    coverage_json jsonb,
    revision bigint,
    expires_at timestamp(6) with time zone,
    CONSTRAINT ck_episode_end_reason CHECK (((state IS NULL) OR (((state)::text = 'open'::text) AND (end_reason IS NULL)) OR (((state)::text = ANY ((ARRAY['closed'::character varying, 'interrupted'::character varying])::text[])) AND (end_reason IS NOT NULL) AND ((end_reason)::text = ANY ((ARRAY['normal'::character varying, 'observation_interrupted'::character varying, 'cancelled'::character varying])::text[]))))),
    CONSTRAINT ck_episode_revision CHECK (((revision IS NULL) OR (revision > 0))),
    CONSTRAINT ck_episode_state CHECK (((state)::text = ANY ((ARRAY['open'::character varying, 'closed'::character varying, 'interrupted'::character varying])::text[]))),
    CONSTRAINT ck_episode_target_exclusive CHECK ((NOT ((target_id IS NOT NULL) AND (stranger_target_id IS NOT NULL))))
);

CREATE TABLE public.episode_media_link (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    episode_id uuid NOT NULL,
    media_asset_id uuid NOT NULL,
    note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.episode_tracklet_link (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    episode_id uuid NOT NULL,
    tracklet_id uuid NOT NULL,
    note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    ordinal integer,
    CONSTRAINT ck_episode_track_ordinal CHECK (((ordinal IS NULL) OR (ordinal >= 0)))
);

CREATE TABLE public.event_object_link (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    event_id uuid NOT NULL,
    identity_id uuid,
    tracklet_id uuid,
    sample_id uuid,
    object_role character varying(32) DEFAULT 'subject'::character varying NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT event_object_link_check CHECK ((num_nonnulls(identity_id, tracklet_id, sample_id) = 1))
);

CREATE TABLE public.evidence_reference (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    activity_id uuid,
    event_id uuid,
    source_id uuid,
    asset_id uuid,
    original_tracklet_id uuid,
    original_result_id uuid,
    start_at timestamp(6) with time zone NOT NULL,
    end_at timestamp(6) with time zone,
    fact_snapshot jsonb DEFAULT '{}'::jsonb NOT NULL,
    provenance_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT evidence_reference_check CHECK ((num_nonnulls(activity_id, event_id) = 1)),
    CONSTRAINT evidence_reference_check1 CHECK (((end_at IS NULL) OR (end_at >= start_at))),
    CONSTRAINT evidence_reference_check2 CHECK (((asset_id IS NOT NULL) OR (fact_snapshot <> '{}'::jsonb)))
);

CREATE TABLE public.feature (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    feature_space_id character varying(128) NOT NULL,
    dimensions integer NOT NULL,
    embedding public.vector NOT NULL,
    sample_id uuid,
    tracklet_id uuid,
    identity_id uuid,
    run_id uuid NOT NULL,
    producer_feature_key character varying(128) NOT NULL,
    aggregation_method character varying(32) NOT NULL,
    input_count integer NOT NULL,
    used_count integer NOT NULL,
    state character varying(16) DEFAULT 'ready'::character varying NOT NULL,
    processed_at timestamp(6) with time zone NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone,
    CONSTRAINT feature_aggregation_method_check CHECK (((aggregation_method)::text = ANY ((ARRAY['single'::character varying, 'mean_l2_v1'::character varying])::text[]))),
    CONSTRAINT feature_check CHECK (((dimensions > 0) AND (public.vector_dims(embedding) = dimensions))),
    CONSTRAINT feature_check1 CHECK (((input_count >= used_count) AND (used_count > 0))),
    CONSTRAINT feature_check2 CHECK (((((aggregation_method)::text = 'single'::text) AND (sample_id IS NOT NULL) AND (used_count = 1)) OR (((aggregation_method)::text = 'mean_l2_v1'::text) AND (sample_id IS NULL)))),
    CONSTRAINT feature_state_check CHECK (((state)::text = ANY ((ARRAY['ready'::character varying, 'invalid'::character varying])::text[])))
);

CREATE TABLE public.feature_contribution (
    feature_id uuid NOT NULL,
    ordinal integer NOT NULL,
    sample_id uuid NOT NULL,
    source_feature_id uuid,
    weight double precision DEFAULT 1 NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    CONSTRAINT feature_contribution_check CHECK (((ordinal >= 0) AND (weight = (1)::double precision)))
);

CREATE TABLE public.feature_space (
    id character varying(128) NOT NULL,
    definition_sha256 character(64) NOT NULL,
    definition_version character varying(32) NOT NULL,
    definition_text text NOT NULL,
    definition_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    object_type character varying(64) NOT NULL,
    feature_kind character varying(32) NOT NULL,
    dimensions integer NOT NULL,
    dtype character varying(16) DEFAULT 'float32'::character varying NOT NULL,
    normalization character varying(16) NOT NULL,
    metric character varying(16) NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    CONSTRAINT feature_space_dimensions_check CHECK ((dimensions > 0)),
    CONSTRAINT feature_space_dtype_check CHECK (((dtype)::text = 'float32'::text)),
    CONSTRAINT feature_space_metric_check CHECK (((metric)::text = ANY ((ARRAY['cosine'::character varying, 'l2'::character varying, 'inner_product'::character varying])::text[]))),
    CONSTRAINT feature_space_normalization_check CHECK (((normalization)::text = ANY ((ARRAY['l2'::character varying, 'none'::character varying])::text[])))
);

CREATE TABLE public.identity (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    identity_kind character varying(16) NOT NULL,
    object_type character varying(64) NOT NULL,
    display_no bigint NOT NULL,
    display_name character varying(200),
    employee_id character varying(64),
    registered_at timestamp(6) with time zone,
    first_seen_at timestamp(6) with time zone,
    last_seen_at timestamp(6) with time zone,
    enabled boolean DEFAULT true NOT NULL,
    revision bigint DEFAULT 1 NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    updated_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone,
    CONSTRAINT identity_check CHECK (((((identity_kind)::text = 'temporary'::text) AND (registered_at IS NULL) AND (first_seen_at IS NOT NULL) AND (last_seen_at IS NOT NULL) AND (expires_at IS NOT NULL)) OR (((identity_kind)::text = 'registered'::text) AND (registered_at IS NOT NULL)))),
    CONSTRAINT identity_check1 CHECK ((((first_seen_at IS NULL) AND (last_seen_at IS NULL)) OR ((first_seen_at IS NOT NULL) AND (last_seen_at IS NOT NULL) AND (last_seen_at >= first_seen_at)))),
    CONSTRAINT identity_identity_kind_check CHECK (((identity_kind)::text = ANY ((ARRAY['temporary'::character varying, 'registered'::character varying])::text[]))),
    CONSTRAINT identity_revision_check CHECK ((revision > 0))
);

CREATE SEQUENCE public.identity_display_no_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.identity_display_no_seq OWNED BY public.identity.display_no;

CREATE TABLE public.identity_link (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    temporary_identity_id uuid NOT NULL,
    registered_identity_id uuid NOT NULL,
    valid_from timestamp(6) with time zone NOT NULL,
    valid_to timestamp(6) with time zone,
    basis_type character varying(32) NOT NULL,
    score double precision,
    run_id uuid,
    reason text,
    revision bigint DEFAULT 1 NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT ck_identity_link_revision CHECK ((revision > 0)),
    CONSTRAINT identity_link_check CHECK ((temporary_identity_id <> registered_identity_id)),
    CONSTRAINT identity_link_check1 CHECK (((valid_to IS NULL) OR (valid_to >= valid_from)))
);

CREATE TABLE public.input_frame (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    stream_session_id uuid NOT NULL,
    frame_seq bigint NOT NULL,
    occurred_at timestamp(6) with time zone NOT NULL,
    stream_pts_ms bigint,
    media_asset_id uuid,
    media_pts_ms bigint,
    time_quality character varying(24) NOT NULL,
    width integer NOT NULL,
    height integer NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT input_frame_check CHECK (((frame_seq >= 0) AND (width > 0) AND (height > 0))),
    CONSTRAINT input_frame_check1 CHECK (((media_asset_id IS NULL) = (media_pts_ms IS NULL))),
    CONSTRAINT input_frame_media_pts_ms_check CHECK (((media_pts_ms IS NULL) OR (media_pts_ms >= 0))),
    CONSTRAINT input_frame_stream_pts_ms_check CHECK (((stream_pts_ms IS NULL) OR (stream_pts_ms >= 0))),
    CONSTRAINT input_frame_time_quality_check CHECK (((time_quality)::text = ANY ((ARRAY['source_clock'::character varying, 'ingest_estimated'::character varying, 'reconciled'::character varying])::text[])))
);

CREATE TABLE public.llm_report (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    episode_id uuid,
    vad_id integer,
    prompt_type text,
    prompt_version text,
    report_json jsonb NOT NULL,
    report_text text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    subject_kind character varying(16),
    subject_id uuid,
    event_id uuid,
    query_id uuid,
    report_type character varying(64),
    completeness character varying(16),
    coverage_json jsonb,
    task_id uuid,
    run_id uuid,
    model_version character varying(128),
    processed_at timestamp(6) with time zone,
    revision bigint,
    expires_at timestamp(6) with time zone,
    CONSTRAINT ck_report_completeness CHECK (((completeness)::text = ANY ((ARRAY['partial'::character varying, 'complete'::character varying])::text[]))),
    CONSTRAINT ck_report_revision CHECK (((revision IS NULL) OR (revision > 0))),
    CONSTRAINT ck_report_subject CHECK ((((subject_kind IS NULL) AND (subject_id IS NULL) AND (report_type IS NULL) AND (event_id IS NULL) AND (query_id IS NULL)) OR ((subject_kind IS NOT NULL) AND (subject_id IS NOT NULL) AND (report_type IS NOT NULL) AND ((((subject_kind)::text = 'activity'::text) AND (episode_id IS NOT NULL) AND (episode_id = subject_id) AND (event_id IS NULL) AND (query_id IS NULL)) OR (((subject_kind)::text = 'event'::text) AND (event_id IS NOT NULL) AND (event_id = subject_id) AND (episode_id IS NULL) AND (query_id IS NULL)) OR (((subject_kind)::text = 'query'::text) AND (query_id IS NOT NULL) AND (query_id = subject_id) AND (episode_id IS NULL) AND (event_id IS NULL)) OR (((subject_kind)::text = 'legacy'::text) AND (subject_id = id) AND (episode_id IS NULL) AND (event_id IS NULL) AND (query_id IS NULL))))))
);

CREATE TABLE public.media_asset (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    stream_id character varying,
    asset_type text NOT NULL,
    start_ts timestamp with time zone NOT NULL,
    duration_ms bigint NOT NULL,
    play_url text,
    oss_bucket text,
    oss_key text,
    content_type text,
    meta jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    source_id uuid,
    stream_session_id uuid,
    producer_key character varying(128),
    storage_key text,
    byte_size bigint,
    checksum_sha256 character(64),
    write_attempt_id uuid,
    write_lease_until timestamp(6) with time zone,
    state character varying(24),
    delete_attempts integer DEFAULT 0 NOT NULL,
    last_error_code character varying(64),
    revision bigint DEFAULT 1 NOT NULL,
    expires_at timestamp(6) with time zone,
    CONSTRAINT chk_media_asset_type CHECK ((asset_type = ANY (ARRAY['segment'::text, 'clip'::text, 'snapshot'::text, 'recording'::text, 'crop'::text, 'evidence_clip'::text, 'algorithm_output'::text, 'query_image'::text, 'enrollment_image'::text]))),
    CONSTRAINT ck_asset_available_content CHECK ((((state)::text <> 'available'::text) OR (storage_key IS NULL) OR ((byte_size IS NOT NULL) AND (checksum_sha256 IS NOT NULL)))),
    CONSTRAINT ck_asset_hash CHECK (((checksum_sha256 IS NULL) OR (checksum_sha256 ~ '^[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_asset_size CHECK ((((byte_size IS NULL) OR (byte_size >= 0)) AND (delete_attempts >= 0) AND (revision > 0))),
    CONSTRAINT ck_asset_state CHECK (((state)::text = ANY ((ARRAY['preparing'::character varying, 'available'::character varying, 'unavailable'::character varying, 'missing'::character varying, 'delete_pending'::character varying, 'deleted'::character varying])::text[])))
);

CREATE TABLE public.outbox_event (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    event_type character varying(64) NOT NULL,
    aggregate_type character varying(64) NOT NULL,
    aggregate_id uuid NOT NULL,
    aggregate_revision bigint NOT NULL,
    payload_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    state character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    attempt_count integer DEFAULT 0 NOT NULL,
    next_attempt_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    last_error_code character varying(64),
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT outbox_event_check CHECK (((aggregate_revision > 0) AND (attempt_count >= 0))),
    CONSTRAINT outbox_event_state_check CHECK (((state)::text = ANY ((ARRAY['pending'::character varying, 'sent'::character varying, 'dead'::character varying])::text[])))
);

CREATE TABLE public.processing_coverage (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    source_id uuid NOT NULL,
    stream_session_id uuid,
    run_id uuid,
    result_set_id uuid,
    stage character varying(24) NOT NULL,
    coverage_key character varying(128) NOT NULL,
    closed boolean DEFAULT false NOT NULL,
    start_at timestamp(6) with time zone NOT NULL,
    end_at timestamp(6) with time zone NOT NULL,
    status character varying(16) NOT NULL,
    analyzed_frame_count bigint DEFAULT 0 NOT NULL,
    saved_frame_count bigint DEFAULT 0 NOT NULL,
    frame_manifest_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    reason_code character varying(64),
    revision bigint DEFAULT 1 NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT ck_coverage_revision CHECK ((revision > 0)),
    CONSTRAINT processing_coverage_check CHECK (((end_at > start_at) AND (analyzed_frame_count >= 0) AND (saved_frame_count >= 0) AND (saved_frame_count <= analyzed_frame_count))),
    CONSTRAINT processing_coverage_stage_check CHECK (((stage)::text = ANY ((ARRAY['input'::character varying, 'recording'::character varying, 'analysis'::character varying, 'registration'::character varying, 'features'::character varying])::text[]))),
    CONSTRAINT processing_coverage_status_check CHECK (((status)::text = ANY ((ARRAY['complete'::character varying, 'partial'::character varying, 'gap'::character varying, 'unavailable'::character varying])::text[])))
);

CREATE TABLE public.query_candidate (
    query_id uuid NOT NULL,
    candidate_id character varying(32) NOT NULL,
    sample_id uuid NOT NULL,
    object_type character varying(64) NOT NULL,
    bbox_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    confidence double precision NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT query_candidate_confidence_check CHECK (((confidence >= (0)::double precision) AND (confidence <= (1)::double precision)))
);

CREATE TABLE public.query_request (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    owner_user_id bigint,
    session_id uuid,
    query_kind character varying(32) NOT NULL,
    object_type character varying(64) DEFAULT 'person'::character varying NOT NULL,
    input_asset_id uuid,
    input_sample_id uuid,
    selected_candidate_id character varying(32),
    identity_id uuid,
    feature_space_id character varying(128),
    start_at timestamp(6) with time zone,
    end_at timestamp(6) with time zone,
    scope_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    state character varying(24) DEFAULT 'pending'::character varying NOT NULL,
    coverage_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    task_id uuid,
    revision bigint DEFAULT 1 NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    updated_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT ck_query_request_revision CHECK ((revision > 0)),
    CONSTRAINT ck_query_stage2_session CHECK ((session_id IS NULL)),
    CONSTRAINT query_request_check CHECK (((end_at IS NULL) OR (start_at IS NULL) OR (end_at > start_at))),
    CONSTRAINT query_request_state_check CHECK (((state)::text = ANY ((ARRAY['pending'::character varying, 'running'::character varying, 'waiting_input'::character varying, 'succeeded'::character varying, 'partial'::character varying, 'failed'::character varying, 'cancelled'::character varying, 'expired'::character varying])::text[])))
);

COMMENT ON COLUMN public.query_request.owner_user_id IS 'NULL: shared business query; non-NULL: existing user-owned query';

CREATE TABLE public.reid_match (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tracklet_id uuid NOT NULL,
    ts timestamp with time zone NOT NULL,
    similarity double precision NOT NULL,
    threshold double precision NOT NULL,
    matched boolean NOT NULL,
    target_id uuid,
    stranger_target_id uuid,
    query_asset_base64 text,
    evidence_asset_base64 text,
    meta jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_reid_match_target_exclusive CHECK ((NOT ((target_id IS NOT NULL) AND (stranger_target_id IS NOT NULL))))
);

CREATE TABLE public.reid_target (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    employee_id text,
    name text NOT NULL,
    source_asset_id uuid,
    embedding public.vector(3072) NOT NULL,
    embedding_model text NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    image_base64 text NOT NULL
);

CREATE TABLE public.report_evidence_link (
    report_id uuid NOT NULL,
    evidence_id uuid NOT NULL,
    report_revision bigint NOT NULL,
    ordinal integer NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    CONSTRAINT report_evidence_link_check CHECK (((report_revision > 0) AND (ordinal >= 0)))
);

CREATE TABLE public.request_deduplication (
    actor_key character varying(128) NOT NULL,
    operation character varying(128) NOT NULL,
    request_id character varying(128) NOT NULL,
    request_digest character(64) NOT NULL,
    state character varying(16) DEFAULT 'accepted'::character varying NOT NULL,
    task_id uuid,
    response_json jsonb,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    updated_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT request_deduplication_state_check CHECK (((state)::text = ANY ((ARRAY['accepted'::character varying, 'completed'::character varying, 'failed'::character varying])::text[])))
);

CREATE TABLE public.result_selection (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    source_id uuid NOT NULL,
    capability_code character varying(64) NOT NULL,
    range_start timestamp(6) with time zone NOT NULL,
    range_end timestamp(6) with time zone NOT NULL,
    result_set_id uuid NOT NULL,
    generation bigint NOT NULL,
    revision bigint DEFAULT 1 NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT result_selection_check CHECK (((range_end > range_start) AND (generation > 0) AND (revision > 0)))
);

CREATE TABLE public.result_set (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    run_id uuid NOT NULL,
    source_id uuid,
    input_asset_id uuid,
    stream_session_id uuid,
    capability_code character varying(64) NOT NULL,
    set_key character varying(128) NOT NULL,
    generation bigint NOT NULL,
    state character varying(16) DEFAULT 'collecting'::character varying NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone NOT NULL,
    device_task_binding_id uuid,
    CONSTRAINT result_set_check CHECK (((source_id IS NOT NULL) OR (input_asset_id IS NOT NULL))),
    CONSTRAINT result_set_check1 CHECK (((stream_session_id IS NULL) OR (source_id IS NOT NULL))),
    CONSTRAINT result_set_generation_check CHECK ((generation > 0)),
    CONSTRAINT result_set_state_check CHECK (((state)::text = ANY ((ARRAY['collecting'::character varying, 'ready'::character varying, 'partial'::character varying, 'failed'::character varying])::text[])))
);

COMMENT ON COLUMN public.result_set.device_task_binding_id IS '可空巡检设备执行归属；不替代本成果的算法run_id';

CREATE TABLE public.result_type (
    type_code character varying(64) NOT NULL,
    schema_version character varying(32) NOT NULL,
    json_schema jsonb DEFAULT '{}'::jsonb NOT NULL,
    max_inline_bytes integer DEFAULT 1048576 NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    CONSTRAINT result_type_json_schema_check CHECK ((jsonb_typeof(json_schema) = 'object'::text)),
    CONSTRAINT result_type_max_inline_bytes_check CHECK ((max_inline_bytes > 0))
);

CREATE TABLE public.sample (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    purpose character varying(16) NOT NULL,
    asset_id uuid NOT NULL,
    input_frame_id uuid,
    tracklet_id uuid,
    identity_id uuid,
    query_id uuid,
    occurred_at timestamp(6) with time zone NOT NULL,
    bbox_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    quality_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    available boolean DEFAULT true NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone,
    CONSTRAINT sample_check CHECK ((((purpose)::text = 'enrollment'::text) OR (expires_at IS NOT NULL))),
    CONSTRAINT sample_purpose_check CHECK (((purpose)::text = ANY ((ARRAY['history'::character varying, 'enrollment'::character varying, 'query'::character varying, 'evidence'::character varying])::text[])))
);

CREATE TABLE public.search_hit (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    query_id uuid NOT NULL,
    rank_no integer NOT NULL,
    hit_kind character varying(16) NOT NULL,
    identity_id uuid,
    tracklet_id uuid,
    sample_id uuid NOT NULL,
    feature_id uuid,
    feature_space_id character varying(128),
    score double precision,
    score_metric character varying(32),
    basis_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT search_hit_hit_kind_check CHECK (((hit_kind)::text = ANY ((ARRAY['gallery'::character varying, 'historical'::character varying])::text[]))),
    CONSTRAINT search_hit_rank_no_check CHECK ((rank_no > 0))
);

CREATE TABLE public.stranger_target (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    code text NOT NULL,
    status text NOT NULL,
    embedding public.vector(3072),
    embedding_model text NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    promoted_target_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    image_base64 text
);

CREATE TABLE public.stream_session (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    source_id uuid NOT NULL,
    camera_stream_id uuid,
    session_key character varying(128) NOT NULL,
    started_at timestamp(6) with time zone NOT NULL,
    ended_at timestamp(6) with time zone,
    time_origin_at timestamp(6) with time zone NOT NULL,
    time_basis character varying(24) NOT NULL,
    source_timezone character varying(64) NOT NULL,
    source_width integer NOT NULL,
    source_height integer NOT NULL,
    state character varying(16) DEFAULT 'open'::character varying NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT stream_session_check CHECK (((source_width > 0) AND (source_height > 0))),
    CONSTRAINT stream_session_check1 CHECK (((ended_at IS NULL) OR (ended_at >= started_at))),
    CONSTRAINT stream_session_check2 CHECK (((((state)::text = 'open'::text) AND (ended_at IS NULL)) OR (((state)::text = ANY ((ARRAY['closed'::character varying, 'interrupted'::character varying])::text[])) AND (ended_at IS NOT NULL)))),
    CONSTRAINT stream_session_state_check CHECK (((state)::text = ANY ((ARRAY['open'::character varying, 'closed'::character varying, 'interrupted'::character varying])::text[]))),
    CONSTRAINT stream_session_time_basis_check CHECK (((time_basis)::text = ANY ((ARRAY['source_clock'::character varying, 'ingest_clock'::character varying])::text[])))
);

CREATE TABLE public.task_attempt (
    executor_id text,
    execution_token uuid,
    send_phase text NOT NULL DEFAULT 'not_sent' CHECK(send_phase IN ('not_sent','sending')),
    run_id uuid DEFAULT gen_random_uuid() NOT NULL,
    task_id uuid NOT NULL,
    generation bigint NOT NULL,
    state character varying(24) DEFAULT 'pending'::character varying NOT NULL,
    implementation_code character varying(128) NOT NULL,
    implementation_version character varying(128) NOT NULL,
    parameters_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    lease_owner character varying(128),
    lease_until timestamp(6) with time zone,
    started_at timestamp(6) with time zone,
    finished_at timestamp(6) with time zone,
    error_code character varying(64),
    error_message text,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    updated_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT task_attempt_check CHECK (((finished_at IS NULL) OR (started_at IS NULL) OR (finished_at >= started_at))),
    CONSTRAINT task_attempt_generation_check CHECK ((generation > 0)),
    CONSTRAINT task_attempt_state_check CHECK (((state)::text = ANY ((ARRAY['pending'::character varying, 'running'::character varying, 'waiting_input'::character varying, 'succeeded'::character varying, 'partial'::character varying, 'failed'::character varying, 'cancelled'::character varying, 'expired'::character varying])::text[])))
);

CREATE TABLE public.track_identity_assignment (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tracklet_id uuid NOT NULL,
    identity_id uuid NOT NULL,
    valid_from timestamp(6) with time zone NOT NULL,
    valid_to timestamp(6) with time zone,
    basis_type character varying(32) NOT NULL,
    score double precision,
    run_id uuid,
    reason text,
    revision bigint DEFAULT 1 NOT NULL,
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT ck_track_identity_assignment_revision CHECK ((revision > 0)),
    CONSTRAINT track_identity_assignment_check CHECK (((valid_to IS NULL) OR (valid_to >= valid_from)))
);

CREATE TABLE public.tracking_context (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    stream_session_id uuid NOT NULL,
    run_id uuid NOT NULL,
    context_key character varying(128) NOT NULL,
    source_width integer NOT NULL,
    source_height integer NOT NULL,
    started_at timestamp(6) with time zone NOT NULL,
    ended_at timestamp(6) with time zone,
    reset_reason character varying(64),
    created_at timestamp(6) with time zone DEFAULT now() NOT NULL,
    expires_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT tracking_context_check CHECK (((source_width > 0) AND (source_height > 0))),
    CONSTRAINT tracking_context_check1 CHECK (((ended_at IS NULL) OR (ended_at >= started_at)))
);

CREATE TABLE public.tracklet (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    stream_id character varying NOT NULL,
    start_ts timestamp with time zone NOT NULL,
    end_ts timestamp with time zone,
    cls_name text NOT NULL,
    color_rgb smallint[],
    query_asset_base64 text,
    frame_asset_base64 text,
    frame_end_base64 text,
    gallery_target_id uuid,
    gallery_similarity double precision,
    stranger_target_id uuid,
    repr_embedding public.vector(3072),
    embedding_model text,
    trajectory_points jsonb,
    meta jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    source_id uuid,
    stream_session_id uuid,
    tracking_context_id uuid,
    local_track_id bigint,
    origin_result_set_id uuid,
    canonical_tracklet_id uuid,
    first_observed_at timestamp(6) with time zone,
    last_observed_at timestamp(6) with time zone,
    end_reason character varying(32),
    revision bigint DEFAULT 1 NOT NULL,
    expires_at timestamp(6) with time zone,
    CONSTRAINT ck_tracklet_canonical CHECK (((canonical_tracklet_id IS NULL) OR (canonical_tracklet_id <> id))),
    CONSTRAINT ck_tracklet_context_pair CHECK (((tracking_context_id IS NULL) = (local_track_id IS NULL))),
    CONSTRAINT ck_tracklet_end_reason CHECK (((end_reason IS NULL) OR ((end_reason)::text = ANY ((ARRAY['normal'::character varying, 'observation_interrupted'::character varying, 'cancelled'::character varying])::text[])))),
    CONSTRAINT ck_tracklet_local_id CHECK (((local_track_id IS NULL) OR (local_track_id >= 0))),
    CONSTRAINT ck_tracklet_observed_time CHECK ((((first_observed_at IS NULL) AND (last_observed_at IS NULL)) OR ((first_observed_at IS NOT NULL) AND (last_observed_at IS NOT NULL) AND (last_observed_at >= first_observed_at)))),
    CONSTRAINT ck_tracklet_target_exclusive CHECK ((NOT ((gallery_target_id IS NOT NULL) AND (stranger_target_id IS NOT NULL))))
);

CREATE TABLE public.vad (
    id integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    media_asset_id uuid NOT NULL,
    stream_id character varying,
    frame_vad_base64 text,
    anomaly_name character varying,
    anomaly_level integer
);

ALTER TABLE public.vad ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.vad_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

ALTER TABLE ONLY public.identity ALTER COLUMN display_no SET DEFAULT nextval('public.identity_display_no_seq'::regclass);

ALTER TABLE ONLY public.algorithm_result
    ADD CONSTRAINT algorithm_result_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.algorithm_result
    ADD CONSTRAINT algorithm_result_result_set_id_producer_result_key_key UNIQUE (result_set_id, producer_result_key);

ALTER TABLE ONLY public.analysis_frame
    ADD CONSTRAINT analysis_frame_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.analysis_frame
    ADD CONSTRAINT analysis_frame_result_set_id_input_frame_id_key UNIQUE (result_set_id, input_frame_id);

ALTER TABLE ONLY public.analysis_frame
    ADD CONSTRAINT analysis_frame_result_set_id_producer_result_key_key UNIQUE (result_set_id, producer_result_key);

ALTER TABLE ONLY public.asset_reference
    ADD CONSTRAINT asset_reference_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.business_event
    ADD CONSTRAINT business_event_event_type_event_key_key UNIQUE (event_type, event_key);

ALTER TABLE ONLY public.business_event
    ADD CONSTRAINT business_event_legacy_vad_id_key UNIQUE (legacy_vad_id);

ALTER TABLE ONLY public.business_event
    ADD CONSTRAINT business_event_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.business_task
    ADD CONSTRAINT business_task_pkey PRIMARY KEY (task_id);

ALTER TABLE ONLY public.business_task
    ADD CONSTRAINT uk_task_business_namespace UNIQUE (task_kind, business_key, execution_namespace);

ALTER TABLE ONLY public.camera
    ADD CONSTRAINT camera_camera_code_key UNIQUE (camera_code);

ALTER TABLE ONLY public.camera
    ADD CONSTRAINT camera_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.camera_stream
    ADD CONSTRAINT camera_stream_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.camera_stream
    ADD CONSTRAINT camera_stream_shm_name_key UNIQUE (shm_name);

ALTER TABLE ONLY public.camera_stream
    ADD CONSTRAINT camera_stream_stream_name_key UNIQUE (stream_name);

ALTER TABLE ONLY public.capability_definition
    ADD CONSTRAINT capability_definition_pkey PRIMARY KEY (capability_code);

ALTER TABLE ONLY public.detection_observation
    ADD CONSTRAINT detection_observation_analysis_frame_id_target_index_key UNIQUE (analysis_frame_id, target_index);

ALTER TABLE ONLY public.detection_observation
    ADD CONSTRAINT detection_observation_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.episode_media_link
    ADD CONSTRAINT episode_media_link_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.episode
    ADD CONSTRAINT episode_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.episode_tracklet_link
    ADD CONSTRAINT episode_tracklet_link_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.event_object_link
    ADD CONSTRAINT event_object_link_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.evidence_reference
    ADD CONSTRAINT evidence_reference_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.feature_contribution
    ADD CONSTRAINT feature_contribution_feature_id_sample_id_key UNIQUE (feature_id, sample_id);

ALTER TABLE ONLY public.feature_contribution
    ADD CONSTRAINT feature_contribution_pkey PRIMARY KEY (feature_id, ordinal);

ALTER TABLE ONLY public.feature
    ADD CONSTRAINT feature_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.feature
    ADD CONSTRAINT feature_run_id_producer_feature_key_key UNIQUE (run_id, producer_feature_key);

ALTER TABLE ONLY public.feature_space
    ADD CONSTRAINT feature_space_definition_sha256_key UNIQUE (definition_sha256);

ALTER TABLE ONLY public.feature_space
    ADD CONSTRAINT feature_space_id_dimensions_key UNIQUE (id, dimensions);

ALTER TABLE ONLY public.feature_space
    ADD CONSTRAINT feature_space_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.identity
    ADD CONSTRAINT identity_display_no_key UNIQUE (display_no);

ALTER TABLE ONLY public.identity_link
    ADD CONSTRAINT identity_link_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.identity
    ADD CONSTRAINT identity_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.input_frame
    ADD CONSTRAINT input_frame_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.input_frame
    ADD CONSTRAINT input_frame_stream_session_id_frame_seq_key UNIQUE (stream_session_id, frame_seq);

ALTER TABLE ONLY public.llm_report
    ADD CONSTRAINT llm_report_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.media_asset
    ADD CONSTRAINT media_asset_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.outbox_event
    ADD CONSTRAINT outbox_event_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.capability_instance
    ADD CONSTRAINT pk_capability_instance PRIMARY KEY (id);

ALTER TABLE ONLY public.device_registry
    ADD CONSTRAINT pk_device_registry PRIMARY KEY (id);

ALTER TABLE ONLY public.device_state_observation
    ADD CONSTRAINT pk_device_state_observation PRIMARY KEY (id);

ALTER TABLE ONLY public.device_task_binding
    ADD CONSTRAINT pk_device_task_binding PRIMARY KEY (id);

ALTER TABLE ONLY public.device_task_feedback
    ADD CONSTRAINT pk_device_task_feedback PRIMARY KEY (id);

ALTER TABLE ONLY public.processing_coverage
    ADD CONSTRAINT processing_coverage_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.query_candidate
    ADD CONSTRAINT query_candidate_pkey PRIMARY KEY (query_id, candidate_id);

ALTER TABLE ONLY public.query_request
    ADD CONSTRAINT query_request_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.reid_match
    ADD CONSTRAINT reid_match_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.reid_target
    ADD CONSTRAINT reid_target_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.report_evidence_link
    ADD CONSTRAINT report_evidence_link_pkey PRIMARY KEY (report_id, evidence_id);

ALTER TABLE ONLY public.report_evidence_link
    ADD CONSTRAINT report_evidence_link_report_id_ordinal_key UNIQUE (report_id, ordinal);

ALTER TABLE ONLY public.request_deduplication
    ADD CONSTRAINT request_deduplication_pkey PRIMARY KEY (actor_key, operation, request_id);

ALTER TABLE ONLY public.result_selection
    ADD CONSTRAINT result_selection_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.result_selection
    ADD CONSTRAINT result_selection_source_id_capability_code_tstzrange_excl EXCLUDE USING gist (source_id WITH =, capability_code WITH =, tstzrange(range_start, range_end, '[)'::text) WITH &&);

ALTER TABLE ONLY public.result_set
    ADD CONSTRAINT result_set_id_source_id_capability_code_key UNIQUE (id, source_id, capability_code);

ALTER TABLE ONLY public.result_set
    ADD CONSTRAINT result_set_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.result_set
    ADD CONSTRAINT result_set_run_id_set_key_key UNIQUE (run_id, set_key);

ALTER TABLE ONLY public.result_type
    ADD CONSTRAINT result_type_pkey PRIMARY KEY (type_code, schema_version);

ALTER TABLE ONLY public.sample
    ADD CONSTRAINT sample_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.search_hit
    ADD CONSTRAINT search_hit_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.search_hit
    ADD CONSTRAINT search_hit_query_id_rank_no_key UNIQUE (query_id, rank_no);

ALTER TABLE ONLY public.stranger_target
    ADD CONSTRAINT stranger_target_code_key UNIQUE (code);

ALTER TABLE ONLY public.stranger_target
    ADD CONSTRAINT stranger_target_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.stream_session
    ADD CONSTRAINT stream_session_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.stream_session
    ADD CONSTRAINT stream_session_source_id_session_key_key UNIQUE (source_id, session_key);

ALTER TABLE ONLY public.task_attempt
    ADD CONSTRAINT task_attempt_pkey PRIMARY KEY (run_id);

ALTER TABLE ONLY public.task_attempt
    ADD CONSTRAINT task_attempt_task_id_generation_key UNIQUE (task_id, generation);

ALTER TABLE ONLY public.task_attempt
    ADD CONSTRAINT task_attempt_task_id_run_id_key UNIQUE (task_id, run_id);

ALTER TABLE ONLY public.track_identity_assignment
    ADD CONSTRAINT track_identity_assignment_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.tracking_context
    ADD CONSTRAINT tracking_context_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.tracking_context
    ADD CONSTRAINT tracking_context_run_id_context_key_key UNIQUE (run_id, context_key);

ALTER TABLE ONLY public.tracklet
    ADD CONSTRAINT tracklet_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.camera
    ADD CONSTRAINT uk_camera_device_channel UNIQUE (management_device_id, channel_code);

ALTER TABLE ONLY public.capability_instance
    ADD CONSTRAINT uk_capability_instance_key UNIQUE (capability_code, instance_key);

ALTER TABLE ONLY public.processing_coverage
    ADD CONSTRAINT uk_coverage_key UNIQUE (source_id, stage, coverage_key);

ALTER TABLE ONLY public.device_task_feedback
    ADD CONSTRAINT uk_device_feedback_key UNIQUE (binding_id, feedback_key);

ALTER TABLE ONLY public.device_task_feedback
    ADD CONSTRAINT uk_device_feedback_seq UNIQUE (binding_id, feedback_seq);

ALTER TABLE ONLY public.device_registry
    ADD CONSTRAINT uk_device_registry_external UNIQUE (adapter_code, external_device_id);

ALTER TABLE ONLY public.device_state_observation
    ADD CONSTRAINT uk_device_state_producer UNIQUE (device_id, producer_session_key, producer_message_key);

ALTER TABLE ONLY public.device_task_binding
    ADD CONSTRAINT uk_device_task_dispatch UNIQUE (device_id, dispatch_key);

ALTER TABLE ONLY public.device_task_binding
    ADD CONSTRAINT uk_device_task_run UNIQUE (run_id);

ALTER TABLE ONLY public.outbox_event
    ADD CONSTRAINT uk_outbox_aggregate_revision UNIQUE (event_type, aggregate_type, aggregate_id, aggregate_revision);

ALTER TABLE ONLY public.llm_report
    ADD CONSTRAINT uk_report_business_subject UNIQUE (subject_kind, subject_id, report_type);

ALTER TABLE ONLY public.vad
    ADD CONSTRAINT vad_pkey PRIMARY KEY (id);

CREATE INDEX idx_camera_stream_camera_id ON public.camera_stream USING btree (camera_id);

CREATE INDEX idx_camera_stream_task_type ON public.camera_stream USING btree (task_type);

CREATE INDEX idx_episode_media_link_episode_id ON public.episode_media_link USING btree (episode_id);

CREATE INDEX idx_episode_media_link_media_asset_id ON public.episode_media_link USING btree (media_asset_id);

CREATE INDEX idx_episode_start_ts ON public.episode USING btree (start_ts);

CREATE INDEX idx_episode_tracklet_link_episode_id ON public.episode_tracklet_link USING btree (episode_id);

CREATE INDEX idx_episode_tracklet_link_tracklet_id ON public.episode_tracklet_link USING btree (tracklet_id);

CREATE INDEX idx_llm_report_episode_id ON public.llm_report USING btree (episode_id);

CREATE INDEX idx_llm_report_prompt_type ON public.llm_report USING btree (prompt_type);

CREATE INDEX idx_llm_report_vad_id ON public.llm_report USING btree (vad_id);

CREATE INDEX idx_media_asset_asset_type ON public.media_asset USING btree (asset_type);

CREATE INDEX idx_media_asset_start_ts ON public.media_asset USING btree (start_ts);

CREATE INDEX idx_media_asset_stream_id ON public.media_asset USING btree (stream_id);

CREATE INDEX idx_reid_match_tracklet_id ON public.reid_match USING btree (tracklet_id);

CREATE INDEX idx_reid_match_ts ON public.reid_match USING btree (ts);

CREATE INDEX idx_reid_target_is_active ON public.reid_target USING btree (is_active);

CREATE INDEX idx_reid_target_name ON public.reid_target USING btree (name);

CREATE INDEX idx_stranger_target_is_active ON public.stranger_target USING btree (is_active);

CREATE INDEX idx_stranger_target_status ON public.stranger_target USING btree (status);

CREATE INDEX idx_tracklet_gallery_target_id ON public.tracklet USING btree (gallery_target_id);

CREATE INDEX idx_tracklet_start_ts ON public.tracklet USING btree (start_ts);

CREATE INDEX idx_tracklet_stranger_target_id ON public.tracklet USING btree (stranger_target_id);

CREATE INDEX idx_tracklet_stream_id ON public.tracklet USING btree (stream_id);

CREATE INDEX idx_vad_created_at ON public.vad USING btree (created_at);

CREATE INDEX idx_vad_media_asset_id ON public.vad USING btree (media_asset_id);

CREATE INDEX idx_vad_stream_id ON public.vad USING btree (stream_id);

CREATE INDEX ix_algorithm_result_type_time ON public.algorithm_result USING btree (result_type, start_at, id);

CREATE INDEX ix_analysis_frame_input ON public.analysis_frame USING btree (input_frame_id, result_set_id);

CREATE INDEX ix_asset_expiry_state ON public.media_asset USING btree (expires_at, state);

CREATE INDEX ix_asset_ref_device_feedback ON public.asset_reference USING btree (device_task_feedback_id) WHERE (device_task_feedback_id IS NOT NULL);

CREATE INDEX ix_asset_ref_evidence ON public.asset_reference USING btree (evidence_id) WHERE (evidence_id IS NOT NULL);

CREATE INDEX ix_asset_ref_identity ON public.asset_reference USING btree (identity_id) WHERE (identity_id IS NOT NULL);

CREATE INDEX ix_asset_ref_query ON public.asset_reference USING btree (query_id) WHERE (query_id IS NOT NULL);

CREATE INDEX ix_asset_ref_result ON public.asset_reference USING btree (result_id) WHERE (result_id IS NOT NULL);

CREATE INDEX ix_asset_ref_sample ON public.asset_reference USING btree (sample_id) WHERE (sample_id IS NOT NULL);

CREATE INDEX ix_asset_reference_retention ON public.asset_reference USING btree (asset_id, retain_until);

CREATE INDEX ix_asset_source_time ON public.media_asset USING btree (source_id, start_ts, id);

CREATE INDEX ix_assignment_identity ON public.track_identity_assignment USING btree (identity_id, tracklet_id);

CREATE INDEX ix_attempt_recovery ON public.task_attempt USING btree (state, lease_until);

CREATE INDEX ix_camera_device ON public.camera USING btree (device_id, id) WHERE (device_id IS NOT NULL);

CREATE INDEX ix_context_session ON public.tracking_context USING btree (stream_session_id, started_at);

CREATE INDEX ix_contribution_sample ON public.feature_contribution USING btree (sample_id, feature_id);

CREATE INDEX ix_contribution_source_feature ON public.feature_contribution USING btree (source_feature_id) WHERE (source_feature_id IS NOT NULL);

CREATE INDEX ix_coverage_source_stage_time ON public.processing_coverage USING btree (source_id, stage, start_at, end_at);

CREATE INDEX ix_dedup_expiry ON public.request_deduplication USING btree (expires_at);

CREATE INDEX ix_device_feedback_expiry ON public.device_task_feedback USING btree (expires_at, id);

CREATE INDEX ix_device_feedback_order ON public.device_task_feedback USING btree (binding_id, feedback_seq, id);

CREATE INDEX ix_device_registry_parent ON public.device_registry USING btree (parent_device_id, id);

CREATE INDEX ix_device_state_expiry ON public.device_state_observation USING btree (expires_at, id);

CREATE INDEX ix_device_state_history ON public.device_state_observation USING btree (device_id, observed_at DESC, received_at DESC, id DESC);

CREATE INDEX ix_device_state_latest ON public.device_state_observation USING btree (device_id, received_at DESC, id DESC);

CREATE INDEX ix_device_task_device_time ON public.device_task_binding USING btree (device_id, created_at DESC, id DESC);

CREATE INDEX ix_device_task_expiry ON public.device_task_binding USING btree (expires_at, id);

CREATE INDEX ix_episode_identity_time ON public.episode USING btree (identity_id, start_ts);

CREATE INDEX ix_event_expiry ON public.business_event USING btree (expires_at);

CREATE INDEX ix_event_object_identity ON public.event_object_link USING btree (identity_id, event_id) WHERE (identity_id IS NOT NULL);

CREATE INDEX ix_event_object_sample ON public.event_object_link USING btree (sample_id, event_id) WHERE (sample_id IS NOT NULL);

CREATE INDEX ix_event_object_track ON public.event_object_link USING btree (tracklet_id, event_id) WHERE (tracklet_id IS NOT NULL);

CREATE INDEX ix_event_type_time ON public.business_event USING btree (event_type, start_at, id);

CREATE INDEX ix_evidence_activity ON public.evidence_reference USING btree (activity_id);

CREATE INDEX ix_evidence_event ON public.evidence_reference USING btree (event_id);

CREATE INDEX ix_feature_identity ON public.feature USING btree (identity_id, feature_space_id);

CREATE INDEX ix_feature_sample ON public.feature USING btree (sample_id) WHERE (sample_id IS NOT NULL);

CREATE INDEX ix_feature_space_state_expiry ON public.feature USING btree (feature_space_id, state, expires_at);

CREATE INDEX ix_feature_track ON public.feature USING btree (tracklet_id, feature_space_id);

CREATE INDEX ix_frame_expiry ON public.input_frame USING btree (expires_at);

CREATE INDEX ix_frame_session_time ON public.input_frame USING btree (stream_session_id, occurred_at, id);

CREATE INDEX ix_identity_kind_expiry ON public.identity USING btree (identity_kind, expires_at);

CREATE INDEX ix_identity_link_registered ON public.identity_link USING btree (registered_identity_id);

CREATE INDEX ix_identity_name ON public.identity USING btree (display_name);

CREATE INDEX ix_instance_selection ON public.capability_instance USING btree (capability_code, enabled, id);

CREATE INDEX ix_observation_track_frame ON public.detection_observation USING btree (tracklet_id, analysis_frame_id);

CREATE INDEX ix_outbox_pending ON public.outbox_event USING btree (next_attempt_at, id) WHERE ((state)::text = 'pending'::text);

CREATE INDEX ix_query_candidate_sample ON public.query_candidate USING btree (sample_id);

CREATE INDEX ix_query_owner_time ON public.query_request USING btree (owner_user_id, created_at, id);

CREATE INDEX ix_report_evidence_reverse ON public.report_evidence_link USING btree (evidence_id);

CREATE INDEX ix_report_expiry ON public.llm_report USING btree (expires_at);

CREATE INDEX ix_result_set_device_task ON public.result_set USING btree (device_task_binding_id, id) WHERE (device_task_binding_id IS NOT NULL);

CREATE INDEX ix_result_set_run ON public.result_set USING btree (run_id);

CREATE INDEX ix_sample_asset ON public.sample USING btree (asset_id);

CREATE INDEX ix_sample_expiry ON public.sample USING btree (expires_at);

CREATE INDEX ix_sample_frame ON public.sample USING btree (input_frame_id) WHERE (input_frame_id IS NOT NULL);

CREATE INDEX ix_sample_identity ON public.sample USING btree (identity_id, purpose);

CREATE INDEX ix_sample_track_time ON public.sample USING btree (tracklet_id, occurred_at);

CREATE INDEX ix_search_hit_identity ON public.search_hit USING btree (identity_id, query_id);

CREATE INDEX ix_search_hit_sample ON public.search_hit USING btree (sample_id);

CREATE INDEX ix_selection_set ON public.result_selection USING btree (result_set_id);

CREATE INDEX ix_stream_session_source_time ON public.stream_session USING btree (source_id, started_at);

CREATE INDEX ix_task_expiry ON public.business_task USING btree (expires_at);

CREATE INDEX ix_task_owner_state ON public.business_task USING btree (owner_user_id, state, created_at);

CREATE INDEX ix_track_source_observed ON public.tracklet USING btree (source_id, first_observed_at, last_observed_at);

CREATE UNIQUE INDEX uk_asset_producer_key ON public.media_asset USING btree (producer_key) WHERE (producer_key IS NOT NULL);

CREATE UNIQUE INDEX uk_asset_ref_device_feedback ON public.asset_reference USING btree (asset_id, device_task_feedback_id) WHERE (device_task_feedback_id IS NOT NULL);

CREATE UNIQUE INDEX uk_asset_ref_evidence ON public.asset_reference USING btree (asset_id, evidence_id) WHERE (evidence_id IS NOT NULL);

CREATE UNIQUE INDEX uk_asset_ref_identity ON public.asset_reference USING btree (asset_id, identity_id) WHERE (identity_id IS NOT NULL);

CREATE UNIQUE INDEX uk_asset_ref_query ON public.asset_reference USING btree (asset_id, query_id) WHERE (query_id IS NOT NULL);

CREATE UNIQUE INDEX uk_asset_ref_result ON public.asset_reference USING btree (asset_id, result_id) WHERE (result_id IS NOT NULL);

CREATE UNIQUE INDEX uk_asset_ref_sample ON public.asset_reference USING btree (asset_id, sample_id) WHERE (sample_id IS NOT NULL);

CREATE UNIQUE INDEX uk_asset_storage_key ON public.media_asset USING btree (storage_key) WHERE (storage_key IS NOT NULL);

CREATE UNIQUE INDEX uk_assignment_current ON public.track_identity_assignment USING btree (tracklet_id) WHERE (valid_to IS NULL);

CREATE UNIQUE INDEX uk_episode_open_identity ON public.episode USING btree (identity_id, activity_type) WHERE (((state)::text = 'open'::text) AND (identity_id IS NOT NULL));

CREATE UNIQUE INDEX uk_event_object_identity ON public.event_object_link USING btree (event_id, identity_id, object_role) WHERE (identity_id IS NOT NULL);

CREATE UNIQUE INDEX uk_event_object_sample ON public.event_object_link USING btree (event_id, sample_id, object_role) WHERE (sample_id IS NOT NULL);

CREATE UNIQUE INDEX uk_event_object_track ON public.event_object_link USING btree (event_id, tracklet_id, object_role) WHERE (tracklet_id IS NOT NULL);

CREATE UNIQUE INDEX uk_identity_link_current ON public.identity_link USING btree (temporary_identity_id) WHERE (valid_to IS NULL);

CREATE UNIQUE INDEX uk_track_context_local ON public.tracklet USING btree (tracking_context_id, local_track_id) WHERE (tracking_context_id IS NOT NULL);

ALTER TABLE ONLY public.analysis_frame
    ADD CONSTRAINT fk_af_input FOREIGN KEY (input_frame_id) REFERENCES public.input_frame(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.analysis_frame
    ADD CONSTRAINT fk_af_set FOREIGN KEY (result_set_id) REFERENCES public.result_set(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.algorithm_result
    ADD CONSTRAINT fk_ar_asset FOREIGN KEY (payload_asset_id) REFERENCES public.media_asset(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.algorithm_result
    ADD CONSTRAINT fk_ar_frame FOREIGN KEY (input_frame_id) REFERENCES public.input_frame(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.algorithm_result
    ADD CONSTRAINT fk_ar_set FOREIGN KEY (result_set_id) REFERENCES public.result_set(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.algorithm_result
    ADD CONSTRAINT fk_ar_track FOREIGN KEY (tracklet_id) REFERENCES public.tracklet(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.algorithm_result
    ADD CONSTRAINT fk_ar_type FOREIGN KEY (result_type, schema_version) REFERENCES public.result_type(type_code, schema_version) ON DELETE RESTRICT;

ALTER TABLE ONLY public.asset_reference
    ADD CONSTRAINT fk_asset_ref_asset FOREIGN KEY (asset_id) REFERENCES public.media_asset(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.asset_reference
    ADD CONSTRAINT fk_asset_ref_device_feedback FOREIGN KEY (device_task_feedback_id) REFERENCES public.device_task_feedback(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.asset_reference
    ADD CONSTRAINT fk_asset_ref_evidence FOREIGN KEY (evidence_id) REFERENCES public.evidence_reference(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.asset_reference
    ADD CONSTRAINT fk_asset_ref_identity FOREIGN KEY (identity_id) REFERENCES public.identity(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.asset_reference
    ADD CONSTRAINT fk_asset_ref_query FOREIGN KEY (query_id) REFERENCES public.query_request(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.asset_reference
    ADD CONSTRAINT fk_asset_ref_result FOREIGN KEY (result_id) REFERENCES public.algorithm_result(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.asset_reference
    ADD CONSTRAINT fk_asset_ref_sample FOREIGN KEY (sample_id) REFERENCES public.sample(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.media_asset
    ADD CONSTRAINT fk_asset_session FOREIGN KEY (stream_session_id) REFERENCES public.stream_session(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.media_asset
    ADD CONSTRAINT fk_asset_source FOREIGN KEY (source_id) REFERENCES public.camera(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.task_attempt
    ADD CONSTRAINT fk_attempt_task FOREIGN KEY (task_id) REFERENCES public.business_task(task_id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.camera
    ADD CONSTRAINT fk_camera_device FOREIGN KEY (device_id) REFERENCES public.device_registry(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.query_candidate
    ADD CONSTRAINT fk_candidate_query FOREIGN KEY (query_id) REFERENCES public.query_request(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.query_candidate
    ADD CONSTRAINT fk_candidate_sample FOREIGN KEY (sample_id) REFERENCES public.sample(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.tracking_context
    ADD CONSTRAINT fk_context_run FOREIGN KEY (run_id) REFERENCES public.task_attempt(run_id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.tracking_context
    ADD CONSTRAINT fk_context_session FOREIGN KEY (stream_session_id) REFERENCES public.stream_session(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.feature_contribution
    ADD CONSTRAINT fk_contrib_feature FOREIGN KEY (feature_id) REFERENCES public.feature(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.feature_contribution
    ADD CONSTRAINT fk_contrib_sample FOREIGN KEY (sample_id) REFERENCES public.sample(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.feature_contribution
    ADD CONSTRAINT fk_contrib_source_feature FOREIGN KEY (source_feature_id) REFERENCES public.feature(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.processing_coverage
    ADD CONSTRAINT fk_cov_run FOREIGN KEY (run_id) REFERENCES public.task_attempt(run_id) ON DELETE SET NULL;

ALTER TABLE ONLY public.processing_coverage
    ADD CONSTRAINT fk_cov_session FOREIGN KEY (stream_session_id) REFERENCES public.stream_session(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.processing_coverage
    ADD CONSTRAINT fk_cov_set FOREIGN KEY (result_set_id) REFERENCES public.result_set(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.processing_coverage
    ADD CONSTRAINT fk_cov_source FOREIGN KEY (source_id) REFERENCES public.camera(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.request_deduplication
    ADD CONSTRAINT fk_dedup_task FOREIGN KEY (task_id) REFERENCES public.business_task(task_id) ON DELETE SET NULL;

ALTER TABLE ONLY public.device_task_feedback
    ADD CONSTRAINT fk_device_feedback_binding FOREIGN KEY (binding_id) REFERENCES public.device_task_binding(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.device_registry
    ADD CONSTRAINT fk_device_registry_parent FOREIGN KEY (parent_device_id) REFERENCES public.device_registry(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.device_state_observation
    ADD CONSTRAINT fk_device_state_attempt FOREIGN KEY (task_id, run_id) REFERENCES public.task_attempt(task_id, run_id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.device_state_observation
    ADD CONSTRAINT fk_device_state_device FOREIGN KEY (device_id) REFERENCES public.device_registry(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.device_task_binding
    ADD CONSTRAINT fk_device_task_attempt FOREIGN KEY (task_id, run_id) REFERENCES public.task_attempt(task_id, run_id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.device_task_binding
    ADD CONSTRAINT fk_device_task_device FOREIGN KEY (device_id) REFERENCES public.device_registry(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.episode
    ADD CONSTRAINT fk_episode_identity FOREIGN KEY (identity_id) REFERENCES public.identity(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.event_object_link
    ADD CONSTRAINT fk_event_object_event FOREIGN KEY (event_id) REFERENCES public.business_event(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.event_object_link
    ADD CONSTRAINT fk_event_object_identity FOREIGN KEY (identity_id) REFERENCES public.identity(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.event_object_link
    ADD CONSTRAINT fk_event_object_sample FOREIGN KEY (sample_id) REFERENCES public.sample(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.event_object_link
    ADD CONSTRAINT fk_event_object_track FOREIGN KEY (tracklet_id) REFERENCES public.tracklet(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.business_event
    ADD CONSTRAINT fk_event_run FOREIGN KEY (run_id) REFERENCES public.task_attempt(run_id) ON DELETE SET NULL;

ALTER TABLE ONLY public.business_event
    ADD CONSTRAINT fk_event_source FOREIGN KEY (source_id) REFERENCES public.camera(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.business_event
    ADD CONSTRAINT fk_event_vad FOREIGN KEY (legacy_vad_id) REFERENCES public.vad(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.evidence_reference
    ADD CONSTRAINT fk_evidence_activity FOREIGN KEY (activity_id) REFERENCES public.episode(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.evidence_reference
    ADD CONSTRAINT fk_evidence_asset FOREIGN KEY (asset_id) REFERENCES public.media_asset(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.evidence_reference
    ADD CONSTRAINT fk_evidence_event FOREIGN KEY (event_id) REFERENCES public.business_event(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.evidence_reference
    ADD CONSTRAINT fk_evidence_result FOREIGN KEY (original_result_id) REFERENCES public.algorithm_result(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.evidence_reference
    ADD CONSTRAINT fk_evidence_source FOREIGN KEY (source_id) REFERENCES public.camera(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.evidence_reference
    ADD CONSTRAINT fk_evidence_track FOREIGN KEY (original_tracklet_id) REFERENCES public.tracklet(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.feature
    ADD CONSTRAINT fk_feature_identity FOREIGN KEY (identity_id) REFERENCES public.identity(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.feature
    ADD CONSTRAINT fk_feature_run FOREIGN KEY (run_id) REFERENCES public.task_attempt(run_id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.feature
    ADD CONSTRAINT fk_feature_sample FOREIGN KEY (sample_id) REFERENCES public.sample(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.feature
    ADD CONSTRAINT fk_feature_space FOREIGN KEY (feature_space_id, dimensions) REFERENCES public.feature_space(id, dimensions) ON DELETE RESTRICT;

ALTER TABLE ONLY public.feature
    ADD CONSTRAINT fk_feature_track FOREIGN KEY (tracklet_id) REFERENCES public.tracklet(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.input_frame
    ADD CONSTRAINT fk_frame_media FOREIGN KEY (media_asset_id) REFERENCES public.media_asset(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.input_frame
    ADD CONSTRAINT fk_frame_session FOREIGN KEY (stream_session_id) REFERENCES public.stream_session(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.search_hit
    ADD CONSTRAINT fk_hit_feature FOREIGN KEY (feature_id) REFERENCES public.feature(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.search_hit
    ADD CONSTRAINT fk_hit_identity FOREIGN KEY (identity_id) REFERENCES public.identity(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.search_hit
    ADD CONSTRAINT fk_hit_query FOREIGN KEY (query_id) REFERENCES public.query_request(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.search_hit
    ADD CONSTRAINT fk_hit_sample FOREIGN KEY (sample_id) REFERENCES public.sample(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.search_hit
    ADD CONSTRAINT fk_hit_space FOREIGN KEY (feature_space_id) REFERENCES public.feature_space(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.search_hit
    ADD CONSTRAINT fk_hit_track FOREIGN KEY (tracklet_id) REFERENCES public.tracklet(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.identity_link
    ADD CONSTRAINT fk_il_reg FOREIGN KEY (registered_identity_id) REFERENCES public.identity(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.identity_link
    ADD CONSTRAINT fk_il_run FOREIGN KEY (run_id) REFERENCES public.task_attempt(run_id) ON DELETE SET NULL;

ALTER TABLE ONLY public.identity_link
    ADD CONSTRAINT fk_il_temp FOREIGN KEY (temporary_identity_id) REFERENCES public.identity(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.capability_instance
    ADD CONSTRAINT fk_instance_cap FOREIGN KEY (capability_code) REFERENCES public.capability_definition(capability_code) ON DELETE RESTRICT;

ALTER TABLE ONLY public.detection_observation
    ADD CONSTRAINT fk_obs_frame FOREIGN KEY (analysis_frame_id) REFERENCES public.analysis_frame(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.detection_observation
    ADD CONSTRAINT fk_obs_track FOREIGN KEY (tracklet_id) REFERENCES public.tracklet(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.query_request
    ADD CONSTRAINT fk_query_asset FOREIGN KEY (input_asset_id) REFERENCES public.media_asset(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.query_request
    ADD CONSTRAINT fk_query_identity FOREIGN KEY (identity_id) REFERENCES public.identity(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.query_request
    ADD CONSTRAINT fk_query_sample FOREIGN KEY (input_sample_id) REFERENCES public.sample(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.query_request
    ADD CONSTRAINT fk_query_selected_candidate FOREIGN KEY (id, selected_candidate_id) REFERENCES public.query_candidate(query_id, candidate_id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.query_request
    ADD CONSTRAINT fk_query_space FOREIGN KEY (feature_space_id) REFERENCES public.feature_space(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.query_request
    ADD CONSTRAINT fk_query_task FOREIGN KEY (task_id) REFERENCES public.business_task(task_id) ON DELETE SET NULL;

ALTER TABLE ONLY public.llm_report
    ADD CONSTRAINT fk_report_event FOREIGN KEY (event_id) REFERENCES public.business_event(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.report_evidence_link
    ADD CONSTRAINT fk_report_evidence_evidence FOREIGN KEY (evidence_id) REFERENCES public.evidence_reference(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.report_evidence_link
    ADD CONSTRAINT fk_report_evidence_report FOREIGN KEY (report_id) REFERENCES public.llm_report(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.llm_report
    ADD CONSTRAINT fk_report_query FOREIGN KEY (query_id) REFERENCES public.query_request(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.llm_report
    ADD CONSTRAINT fk_report_run FOREIGN KEY (run_id) REFERENCES public.task_attempt(run_id) ON DELETE SET NULL;

ALTER TABLE ONLY public.llm_report
    ADD CONSTRAINT fk_report_task FOREIGN KEY (task_id) REFERENCES public.business_task(task_id) ON DELETE SET NULL;

ALTER TABLE ONLY public.result_set
    ADD CONSTRAINT fk_result_set_device_task FOREIGN KEY (device_task_binding_id) REFERENCES public.device_task_binding(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.result_set
    ADD CONSTRAINT fk_rs_cap FOREIGN KEY (capability_code) REFERENCES public.capability_definition(capability_code) ON DELETE RESTRICT;

ALTER TABLE ONLY public.result_set
    ADD CONSTRAINT fk_rs_input_asset FOREIGN KEY (input_asset_id) REFERENCES public.media_asset(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.result_set
    ADD CONSTRAINT fk_rs_run FOREIGN KEY (run_id) REFERENCES public.task_attempt(run_id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.result_set
    ADD CONSTRAINT fk_rs_session FOREIGN KEY (stream_session_id) REFERENCES public.stream_session(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.result_set
    ADD CONSTRAINT fk_rs_source FOREIGN KEY (source_id) REFERENCES public.camera(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.sample
    ADD CONSTRAINT fk_sample_asset FOREIGN KEY (asset_id) REFERENCES public.media_asset(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.sample
    ADD CONSTRAINT fk_sample_frame FOREIGN KEY (input_frame_id) REFERENCES public.input_frame(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.sample
    ADD CONSTRAINT fk_sample_identity FOREIGN KEY (identity_id) REFERENCES public.identity(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.sample
    ADD CONSTRAINT fk_sample_query FOREIGN KEY (query_id) REFERENCES public.query_request(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.sample
    ADD CONSTRAINT fk_sample_track FOREIGN KEY (tracklet_id) REFERENCES public.tracklet(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.result_selection
    ADD CONSTRAINT fk_selection_set FOREIGN KEY (result_set_id, source_id, capability_code) REFERENCES public.result_set(id, source_id, capability_code) ON DELETE RESTRICT;

ALTER TABLE ONLY public.stream_session
    ADD CONSTRAINT fk_ss_source FOREIGN KEY (source_id) REFERENCES public.camera(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.stream_session
    ADD CONSTRAINT fk_ss_stream FOREIGN KEY (camera_stream_id) REFERENCES public.camera_stream(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.business_task
    ADD CONSTRAINT fk_task_cap FOREIGN KEY (capability_code) REFERENCES public.capability_definition(capability_code) ON DELETE RESTRICT;

ALTER TABLE ONLY public.business_task
    ADD CONSTRAINT fk_task_current_run FOREIGN KEY (task_id, current_run_id) REFERENCES public.task_attempt(task_id, run_id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.track_identity_assignment
    ADD CONSTRAINT fk_tia_identity FOREIGN KEY (identity_id) REFERENCES public.identity(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.track_identity_assignment
    ADD CONSTRAINT fk_tia_run FOREIGN KEY (run_id) REFERENCES public.task_attempt(run_id) ON DELETE SET NULL;

ALTER TABLE ONLY public.track_identity_assignment
    ADD CONSTRAINT fk_tia_track FOREIGN KEY (tracklet_id) REFERENCES public.tracklet(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.tracklet
    ADD CONSTRAINT fk_track_canonical FOREIGN KEY (canonical_tracklet_id) REFERENCES public.tracklet(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.tracklet
    ADD CONSTRAINT fk_track_context FOREIGN KEY (tracking_context_id) REFERENCES public.tracking_context(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.tracklet
    ADD CONSTRAINT fk_track_result_set FOREIGN KEY (origin_result_set_id) REFERENCES public.result_set(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.tracklet
    ADD CONSTRAINT fk_track_session FOREIGN KEY (stream_session_id) REFERENCES public.stream_session(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.tracklet
    ADD CONSTRAINT fk_track_source FOREIGN KEY (source_id) REFERENCES public.camera(id) ON DELETE RESTRICT;

CREATE INDEX ix_platform_pending ON public.business_task(execution_namespace,created_at)
 WHERE dispatch_mode='platform_managed' AND state='pending';
CREATE TABLE public.task_output (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 task_id uuid NOT NULL REFERENCES public.business_task(task_id),
 run_id uuid NOT NULL,
 result_type varchar(64) NOT NULL,
 schema_version varchar(32) NOT NULL,
 payload_json jsonb NOT NULL,
 asset_id uuid REFERENCES public.media_asset(id),
 producer_result_key varchar(128) NOT NULL,
 payload_digest char(64) NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(run_id,producer_result_key),
 FOREIGN KEY(task_id,run_id) REFERENCES public.task_attempt(task_id,run_id),
 FOREIGN KEY(result_type,schema_version) REFERENCES public.result_type(type_code,schema_version)
);
CREATE INDEX ix_task_output_page ON public.task_output(task_id,id);

INSERT INTO public.result_type(type_code,schema_version,json_schema,max_inline_bytes,enabled)
VALUES ('behavior.assessment','1','{"type":"object","additionalProperties":false,"required":["behavior_type","decision","description"],"properties":{"behavior_type":{"type":"string","enum":["fight","fall"]},"decision":{"type":"string","enum":["suspected","confirmed","rejected","insufficient_evidence"]},"description":{"type":"string","maxLength":4000},"score":{"anyOf":[{"type":"number"},{"type":"null"}]},"score_semantics":{"anyOf":[{"type":"string","minLength":1,"maxLength":128},{"type":"null"}]},"targets":{"type":"array","items":{"type":"object","additionalProperties":false,"required":["target_index","bbox"],"properties":{"target_index":{"type":"integer","minimum":0},"bbox":{"type":"array","minItems":4,"maxItems":4,"items":{"type":"number","minimum":0,"maximum":1},"description":"Normalized source-image xyxy; right>left and bottom>top need business validation."},"tracklet_id":{"type":"string","pattern":"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"}}}}},"anyOf":[{"not":{"required":["score"]}},{"required":["score"],"properties":{"score":{"type":"null"}}},{"required":["score","score_semantics"],"properties":{"score":{"type":"number"},"score_semantics":{"type":"string","minLength":1,"maxLength":128}}}]}'::jsonb,1048576,true)
ON CONFLICT(type_code,schema_version) DO NOTHING;
INSERT INTO public.result_type(type_code,schema_version,json_schema,max_inline_bytes,enabled)
VALUES ('garbage.detection','1','{"type":"object","additionalProperties":false,"required":["has_target","targets"],"properties":{"has_target":{"type":"boolean"},"targets":{"type":"array","items":{"type":"object","additionalProperties":false,"required":["category","bbox"],"properties":{"category":{"type":"string","minLength":1,"maxLength":64},"bbox":{"type":"array","minItems":4,"maxItems":4,"items":{"type":"number","minimum":0,"maximum":1},"description":"Normalized source-image xyxy; right>left and bottom>top need business validation."},"confidence":{"type":"number","minimum":0,"maximum":1}}}},"scene_description":{"anyOf":[{"type":"string","maxLength":4000},{"type":"null"}]},"suggestion":{"anyOf":[{"type":"string","maxLength":4000},{"type":"null"}]}},"anyOf":[{"properties":{"has_target":{"enum":[false]},"targets":{"maxItems":0}}},{"properties":{"has_target":{"enum":[true]},"targets":{"minItems":1}}}]}'::jsonb,1048576,true)
ON CONFLICT(type_code,schema_version) DO NOTHING;
