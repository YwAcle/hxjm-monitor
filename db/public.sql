/*
 Navicat Premium Dump SQL

 Source Server         : hxjm
 Source Server Type    : PostgreSQL
 Source Server Version : 160011 (160011)
 Source Host           : 100.127.237.7:5432
 Source Catalog        : postgres
 Source Schema         : public

 Target Server Type    : PostgreSQL
 Target Server Version : 160011 (160011)
 File Encoding         : 65001

 Date: 03/11/2026 19:19:34
*/


-- ----------------------------
-- Type structure for gbtreekey16
-- ----------------------------
DROP TYPE IF EXISTS "public"."gbtreekey16";
CREATE TYPE "public"."gbtreekey16" (
  INPUT = "public"."gbtreekey16_in",
  OUTPUT = "public"."gbtreekey16_out",
  INTERNALLENGTH = 16,
  CATEGORY = U,
  DELIMITER = ','
);

-- ----------------------------
-- Type structure for gbtreekey2
-- ----------------------------
DROP TYPE IF EXISTS "public"."gbtreekey2";
CREATE TYPE "public"."gbtreekey2" (
  INPUT = "public"."gbtreekey2_in",
  OUTPUT = "public"."gbtreekey2_out",
  INTERNALLENGTH = 2,
  CATEGORY = U,
  DELIMITER = ','
);

-- ----------------------------
-- Type structure for gbtreekey32
-- ----------------------------
DROP TYPE IF EXISTS "public"."gbtreekey32";
CREATE TYPE "public"."gbtreekey32" (
  INPUT = "public"."gbtreekey32_in",
  OUTPUT = "public"."gbtreekey32_out",
  INTERNALLENGTH = 32,
  CATEGORY = U,
  DELIMITER = ','
);

-- ----------------------------
-- Type structure for gbtreekey4
-- ----------------------------
DROP TYPE IF EXISTS "public"."gbtreekey4";
CREATE TYPE "public"."gbtreekey4" (
  INPUT = "public"."gbtreekey4_in",
  OUTPUT = "public"."gbtreekey4_out",
  INTERNALLENGTH = 4,
  CATEGORY = U,
  DELIMITER = ','
);

-- ----------------------------
-- Type structure for gbtreekey8
-- ----------------------------
DROP TYPE IF EXISTS "public"."gbtreekey8";
CREATE TYPE "public"."gbtreekey8" (
  INPUT = "public"."gbtreekey8_in",
  OUTPUT = "public"."gbtreekey8_out",
  INTERNALLENGTH = 8,
  CATEGORY = U,
  DELIMITER = ','
);

-- ----------------------------
-- Type structure for gbtreekey_var
-- ----------------------------
DROP TYPE IF EXISTS "public"."gbtreekey_var";
CREATE TYPE "public"."gbtreekey_var" (
  INPUT = "public"."gbtreekey_var_in",
  OUTPUT = "public"."gbtreekey_var_out",
  INTERNALLENGTH = VARIABLE,
  STORAGE = extended,
  CATEGORY = U,
  DELIMITER = ','
);

-- ----------------------------
-- Type structure for halfvec
-- ----------------------------
DROP TYPE IF EXISTS "public"."halfvec";
CREATE TYPE "public"."halfvec" (
  INPUT = "public"."halfvec_in",
  OUTPUT = "public"."halfvec_out",
  RECEIVE = "public"."halfvec_recv",
  SEND = "public"."halfvec_send",
  TYPMOD_IN = "public"."halfvec_typmod_in",
  INTERNALLENGTH = VARIABLE,
  STORAGE = external,
  CATEGORY = U,
  DELIMITER = ','
);

-- ----------------------------
-- Type structure for sparsevec
-- ----------------------------
DROP TYPE IF EXISTS "public"."sparsevec";
CREATE TYPE "public"."sparsevec" (
  INPUT = "public"."sparsevec_in",
  OUTPUT = "public"."sparsevec_out",
  RECEIVE = "public"."sparsevec_recv",
  SEND = "public"."sparsevec_send",
  TYPMOD_IN = "public"."sparsevec_typmod_in",
  INTERNALLENGTH = VARIABLE,
  STORAGE = external,
  CATEGORY = U,
  DELIMITER = ','
);

-- ----------------------------
-- Type structure for vector
-- ----------------------------
DROP TYPE IF EXISTS "public"."vector";
CREATE TYPE "public"."vector" (
  INPUT = "public"."vector_in",
  OUTPUT = "public"."vector_out",
  RECEIVE = "public"."vector_recv",
  SEND = "public"."vector_send",
  TYPMOD_IN = "public"."vector_typmod_in",
  INTERNALLENGTH = VARIABLE,
  STORAGE = external,
  CATEGORY = U,
  DELIMITER = ','
);

-- ----------------------------
-- Sequence structure for identity_display_no_seq
-- ----------------------------
DROP SEQUENCE IF EXISTS "public"."identity_display_no_seq";
CREATE SEQUENCE "public"."identity_display_no_seq" 
INCREMENT 1
MINVALUE  1
MAXVALUE 9223372036854775807
START 1
CACHE 1;

-- ----------------------------
-- Sequence structure for vad_id_seq
-- ----------------------------
DROP SEQUENCE IF EXISTS "public"."vad_id_seq";
CREATE SEQUENCE "public"."vad_id_seq" 
INCREMENT 1
MINVALUE  1
MAXVALUE 2147483647
START 1
CACHE 1;

-- ----------------------------
-- Table structure for ai_task_run
-- ----------------------------
DROP TABLE IF EXISTS "public"."ai_task_run";
CREATE TABLE "public"."ai_task_run" (
  "run_id" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,
  "camera_id" int8 NOT NULL,
  "task_code" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,
  "status" varchar(16) COLLATE "pg_catalog"."default" NOT NULL,
  "input_path" varchar(255) COLLATE "pg_catalog"."default" NOT NULL,
  "output_path" varchar(255) COLLATE "pg_catalog"."default" NOT NULL,
  "output_url" text COLLATE "pg_catalog"."default" NOT NULL,
  "failure_reason" text COLLATE "pg_catalog"."default",
  "started_at" timestamptz(6),
  "stopped_at" timestamptz(6),
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now()
)
;

-- ----------------------------
-- Table structure for algorithm_result
-- ----------------------------
DROP TABLE IF EXISTS "public"."algorithm_result";
CREATE TABLE "public"."algorithm_result" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "result_set_id" uuid NOT NULL,
  "producer_result_key" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "result_type" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,
  "schema_version" varchar(32) COLLATE "pg_catalog"."default" NOT NULL,
  "input_frame_id" uuid,
  "tracklet_id" uuid,
  "start_at" timestamptz(6) NOT NULL,
  "end_at" timestamptz(6),
  "payload_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "payload_asset_id" uuid,
  "payload_digest" char(64) COLLATE "pg_catalog"."default" NOT NULL,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6) NOT NULL
)
;

-- ----------------------------
-- Table structure for analysis_frame
-- ----------------------------
DROP TABLE IF EXISTS "public"."analysis_frame";
CREATE TABLE "public"."analysis_frame" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "result_set_id" uuid NOT NULL,
  "input_frame_id" uuid NOT NULL,
  "producer_result_key" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "schema_version" varchar(32) COLLATE "pg_catalog"."default" NOT NULL DEFAULT '1'::character varying,
  "target_count" int4 NOT NULL,
  "payload_digest" char(64) COLLATE "pg_catalog"."default" NOT NULL,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6) NOT NULL
)
;

-- ----------------------------
-- Table structure for asset_reference
-- ----------------------------
DROP TABLE IF EXISTS "public"."asset_reference";
CREATE TABLE "public"."asset_reference" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "asset_id" uuid NOT NULL,
  "sample_id" uuid,
  "evidence_id" uuid,
  "query_id" uuid,
  "identity_id" uuid,
  "message_id" uuid,
  "result_id" uuid,
  "retain_until" timestamptz(6),
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "device_task_feedback_id" uuid
)
;
COMMENT ON COLUMN "public"."asset_reference"."device_task_feedback_id" IS '可空设备反馈文件用途；七种用途恰好一个非空';

-- ----------------------------
-- Table structure for business_event
-- ----------------------------
DROP TABLE IF EXISTS "public"."business_event";
CREATE TABLE "public"."business_event" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "event_type" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,
  "event_key" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "source_id" uuid,
  "start_at" timestamptz(6) NOT NULL,
  "end_at" timestamptz(6),
  "state" varchar(16) COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'open'::character varying,
  "end_reason" varchar(32) COLLATE "pg_catalog"."default",
  "conclusion_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "legacy_vad_id" int4,
  "run_id" uuid,
  "coverage_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "revision" int8 NOT NULL DEFAULT 1,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6) NOT NULL
)
;

-- ----------------------------
-- Table structure for business_task
-- ----------------------------
DROP TABLE IF EXISTS "public"."business_task";
CREATE TABLE "public"."business_task" (
  "task_id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "task_kind" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,
  "business_key" varchar(256) COLLATE "pg_catalog"."default",
  "task_mode" varchar(16) COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'once'::character varying,
  "last_input_at" timestamptz(6),
  "actor_key" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "owner_user_id" int8,
  "capability_code" varchar(64) COLLATE "pg_catalog"."default",
  "state" varchar(24) COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'pending'::character varying,
  "input_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "input_digest" char(64) COLLATE "pg_catalog"."default" NOT NULL,
  "current_run_id" uuid,
  "generation" int8 NOT NULL DEFAULT 0,
  "progress" numeric(5,2) NOT NULL DEFAULT 0,
  "error_code" varchar(64) COLLATE "pg_catalog"."default",
  "error_message" text COLLATE "pg_catalog"."default",
  "revision" int8 NOT NULL DEFAULT 1,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6) NOT NULL,
  "dispatch_mode" varchar(32) COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'runtime_managed'::character varying,
  "execution_snapshot" jsonb,
  "execution_namespace" varchar(96) COLLATE "pg_catalog"."default" NOT NULL DEFAULT ''::character varying
)
;

-- ----------------------------
-- Table structure for camera
-- ----------------------------
DROP TABLE IF EXISTS "public"."camera";
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
  "updated_at" timestamptz(6) NOT NULL DEFAULT now(),
  "management_device_id" int8,
  "channel_code" varchar(64) COLLATE "pg_catalog"."default",
  "source_kind" varchar(24) COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'camera'::character varying,
  "enabled" bool NOT NULL DEFAULT true,
  "device_id" uuid
)
;
COMMENT ON COLUMN "public"."camera"."device_id" IS '可空直接设备归属；保留原管理设备映射';

-- ----------------------------
-- Table structure for camera_stream
-- ----------------------------
DROP TABLE IF EXISTS "public"."camera_stream";
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
)
;

-- ----------------------------
-- Table structure for capability_definition
-- ----------------------------
DROP TABLE IF EXISTS "public"."capability_definition";
CREATE TABLE "public"."capability_definition" (
  "capability_code" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,
  "display_name" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "object_types" text[] COLLATE "pg_catalog"."default" NOT NULL,
  "input_kinds" text[] COLLATE "pg_catalog"."default" NOT NULL,
  "contract_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "enabled" bool NOT NULL DEFAULT true,
  "revision" int8 NOT NULL DEFAULT 1,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now(),
  "agent_json" jsonb NOT NULL DEFAULT '{}'::jsonb
)
;

-- ----------------------------
-- Table structure for capability_instance
-- ----------------------------
DROP TABLE IF EXISTS "public"."capability_instance";
CREATE TABLE "public"."capability_instance" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "capability_code" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,
  "instance_key" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "implementation_code" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,
  "implementation_version" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "source_ids" uuid[] NOT NULL DEFAULT '{}'::uuid[],
  "service_ref" varchar(256) COLLATE "pg_catalog"."default" NOT NULL,
  "enabled" bool NOT NULL DEFAULT true,
  "revision" int8 NOT NULL DEFAULT 1,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now(),
  "resource_scope" jsonb NOT NULL,
  "dispatch_mode" varchar(32) COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'runtime_managed'::character varying,
  "execution_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "execution_namespace" varchar(96) COLLATE "pg_catalog"."default" NOT NULL DEFAULT ''::character varying
)
;

-- ----------------------------
-- Table structure for detection_observation
-- ----------------------------
DROP TABLE IF EXISTS "public"."detection_observation";
CREATE TABLE "public"."detection_observation" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "analysis_frame_id" uuid NOT NULL,
  "target_index" int4 NOT NULL,
  "tracklet_id" uuid,
  "object_type" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,
  "class_code" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,
  "confidence" float8,
  "observation_kind" varchar(16) COLLATE "pg_catalog"."default" NOT NULL,
  "bbox_left" float8 NOT NULL,
  "bbox_top" float8 NOT NULL,
  "bbox_right" float8 NOT NULL,
  "bbox_bottom" float8 NOT NULL,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6) NOT NULL
)
;

-- ----------------------------
-- Table structure for device_registry
-- ----------------------------
DROP TABLE IF EXISTS "public"."device_registry";
CREATE TABLE "public"."device_registry" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "adapter_code" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,
  "external_device_id" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "device_type" varchar(32) COLLATE "pg_catalog"."default" NOT NULL,
  "display_name" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "parent_device_id" uuid,
  "management_device_id" int8,
  "config_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "enabled" bool NOT NULL DEFAULT true,
  "revision" int8 NOT NULL DEFAULT 1,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now()
)
;
COMMENT ON COLUMN "public"."device_registry"."id" IS '设备稳定主键';
COMMENT ON COLUMN "public"."device_registry"."adapter_code" IS '已部署适配器命名空间，不是IP';
COMMENT ON COLUMN "public"."device_registry"."external_device_id" IS '该适配器中的设备稳定编号';
COMMENT ON COLUMN "public"."device_registry"."device_type" IS '已发布robot_dog、robot_arm等设备类型，不用每种设备新增主表';
COMMENT ON COLUMN "public"."device_registry"."display_name" IS '展示名称，不唯一';
COMMENT ON COLUMN "public"."device_registry"."parent_device_id" IS '父设备；不可指向自己，业务校验防循环';
COMMENT ON COLUMN "public"."device_registry"."management_device_id" IS '逻辑引用hxjm_sm.ba_machine.machine_id，正整数；对外十进制字符串';
COMMENT ON COLUMN "public"."device_registry"."config_json" IS 'v1配置对象，schema_version为字符串1；service_ref和credential_ref为可选1～128字符字符串，分别为已部署连接引用和凭据引用，state_sample_interval_seconds默认30，state_stale_after_seconds默认90；均为正整数且后者大于采样间隔';
COMMENT ON COLUMN "public"."device_registry"."enabled" IS '停用阻止新下发，不删除已执行任务／历史';
COMMENT ON COLUMN "public"."device_registry"."revision" IS '乐观锁，更新时expected_revision校验';
COMMENT ON COLUMN "public"."device_registry"."created_at" IS '首次登记时间';
COMMENT ON COLUMN "public"."device_registry"."updated_at" IS '有效修改时更新';
COMMENT ON TABLE "public"."device_registry" IS 'HXJM v0.2；设备接入目录：一个实际设备或独立上报组件';

-- ----------------------------
-- Table structure for device_state_observation
-- ----------------------------
DROP TABLE IF EXISTS "public"."device_state_observation";
CREATE TABLE "public"."device_state_observation" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "device_id" uuid NOT NULL,
  "producer_session_key" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "producer_message_key" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "observed_at" timestamptz(6) NOT NULL,
  "received_at" timestamptz(6) NOT NULL,
  "time_quality" varchar(24) COLLATE "pg_catalog"."default" NOT NULL,
  "record_kind" varchar(8) COLLATE "pg_catalog"."default" NOT NULL,
  "state_code" varchar(40) COLLATE "pg_catalog"."default" NOT NULL,
  "schema_version" varchar(32) COLLATE "pg_catalog"."default" NOT NULL DEFAULT '1'::character varying,
  "payload_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "payload_digest" char(64) COLLATE "pg_catalog"."default" NOT NULL,
  "task_id" uuid,
  "run_id" uuid,
  "expires_at" timestamptz(6) NOT NULL
)
;
COMMENT ON COLUMN "public"."device_state_observation"."id" IS '状态记录主键';
COMMENT ON COLUMN "public"."device_state_observation"."device_id" IS '设备或独立组件';
COMMENT ON COLUMN "public"."device_state_observation"."producer_session_key" IS '设备上报会话；适配器连接新编号空间时改变';
COMMENT ON COLUMN "public"."device_state_observation"."producer_message_key" IS '该会话内稳定消息键；同一上报重传不变';
COMMENT ON COLUMN "public"."device_state_observation"."observed_at" IS '设备真实观测时间；缺失时固定采用首次接收时间';
COMMENT ON COLUMN "public"."device_state_observation"."received_at" IS '主系统首次接收时间，重传不刷新';
COMMENT ON COLUMN "public"."device_state_observation"."time_quality" IS 'device_reported或received_estimated，不宣称时钟已精确同步';
COMMENT ON COLUMN "public"."device_state_observation"."record_kind" IS 'change或sample；同一上报同时命中时优先change';
COMMENT ON COLUMN "public"."device_state_observation"."state_code" IS '该设备类型已发布状态码；unknown表示设备确实上报未知';
COMMENT ON COLUMN "public"."device_state_observation"."schema_version" IS '设备状态载荷版本';
COMMENT ON COLUMN "public"."device_state_observation"."payload_json" IS '对象；可选battery_percent(0～100)、velocity_mps(有限数)、position({coordinate_system:非空字符串最多64字符,values:有限数数组})、joints_deg(有限数数组)、gripper；缺失不填零；位置无导航用途';
COMMENT ON COLUMN "public"."device_state_observation"."payload_digest" IS '设备、生产键、观测时间、状态及载荷等不可变业务内容摘要';
COMMENT ON COLUMN "public"."device_state_observation"."task_id" IS '实际明确的业务任务；与run_id同时提供或同时为空';
COMMENT ON COLUMN "public"."device_state_observation"."run_id" IS '实际执行；通过(task_id,run_id)校验归属，不凭接收时间猜测';
COMMENT ON COLUMN "public"."device_state_observation"."expires_at" IS 'observed_at+7天';
COMMENT ON TABLE "public"."device_state_observation" IS 'HXJM v0.2；设备状态历史：一次保留的状态变化或周期采样';

-- ----------------------------
-- Table structure for device_task_binding
-- ----------------------------
DROP TABLE IF EXISTS "public"."device_task_binding";
CREATE TABLE "public"."device_task_binding" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "task_id" uuid NOT NULL,
  "run_id" uuid NOT NULL,
  "device_id" uuid NOT NULL,
  "dispatch_key" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "external_task_id" varchar(128) COLLATE "pg_catalog"."default",
  "dispatch_state" varchar(16) COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'pending'::character varying,
  "last_feedback_seq" int8 NOT NULL DEFAULT 0,
  "dispatched_at" timestamptz(6),
  "acknowledged_at" timestamptz(6),
  "revision" int8 NOT NULL DEFAULT 1,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6) NOT NULL
)
;
COMMENT ON COLUMN "public"."device_task_binding"."id" IS '设备执行映射主键';
COMMENT ON COLUMN "public"."device_task_binding"."task_id" IS '公共巡检任务';
COMMENT ON COLUMN "public"."device_task_binding"."run_id" IS '该任务执行尝试；一次只绑定一台设备';
COMMENT ON COLUMN "public"."device_task_binding"."device_id" IS '实际执行设备';
COMMENT ON COLUMN "public"."device_task_binding"."dispatch_key" IS '设备命名空间内的下发幂等键，首次受理生成，重传不变';
COMMENT ON COLUMN "public"."device_task_binding"."external_task_id" IS '设备侧本次执行编号，首次下发可空，不是路线模板编号';
COMMENT ON COLUMN "public"."device_task_binding"."dispatch_state" IS 'pending/sent/acknowledged/rejected；只描述下发';
COMMENT ON COLUMN "public"."device_task_binding"."last_feedback_seq" IS '已用于更新执行状态的反馈序号水位，不是收到消息条数';
COMMENT ON COLUMN "public"."device_task_binding"."dispatched_at" IS '首次实际发送时刻';
COMMENT ON COLUMN "public"."device_task_binding"."acknowledged_at" IS '设备实际确认接收时刻';
COMMENT ON COLUMN "public"."device_task_binding"."revision" IS '状态更新CAS修订';
COMMENT ON COLUMN "public"."device_task_binding"."created_at" IS '首次创建';
COMMENT ON COLUMN "public"."device_task_binding"."updated_at" IS '有效更新时维护';
COMMENT ON COLUMN "public"."device_task_binding"."expires_at" IS '任务正常终态后按finished_at+7天固定；进行中维护控制目录期限';
COMMENT ON TABLE "public"."device_task_binding" IS 'HXJM v0.2；设备执行映射：一次公共执行对应一台执行设备';

-- ----------------------------
-- Table structure for device_task_feedback
-- ----------------------------
DROP TABLE IF EXISTS "public"."device_task_feedback";
CREATE TABLE "public"."device_task_feedback" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "binding_id" uuid NOT NULL,
  "feedback_key" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "feedback_seq" int8 NOT NULL,
  "occurred_at" timestamptz(6) NOT NULL,
  "received_at" timestamptz(6) NOT NULL,
  "feedback_type" varchar(16) COLLATE "pg_catalog"."default" NOT NULL,
  "execution_state" varchar(24) COLLATE "pg_catalog"."default",
  "progress" numeric(5,2),
  "error_code" varchar(64) COLLATE "pg_catalog"."default",
  "error_message" text COLLATE "pg_catalog"."default",
  "schema_version" varchar(32) COLLATE "pg_catalog"."default" NOT NULL DEFAULT '1'::character varying,
  "payload_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "payload_digest" char(64) COLLATE "pg_catalog"."default" NOT NULL,
  "expires_at" timestamptz(6) NOT NULL
)
;
COMMENT ON COLUMN "public"."device_task_feedback"."id" IS '反馈主键';
COMMENT ON COLUMN "public"."device_task_feedback"."binding_id" IS '设备执行映射';
COMMENT ON COLUMN "public"."device_task_feedback"."feedback_key" IS '该绑定内稳定反馈键，重试不变';
COMMENT ON COLUMN "public"."device_task_feedback"."feedback_seq" IS '该绑定内从1递增序号，源版本或适配器稳定分配；不以HTTP到达时间替代已知源顺序';
COMMENT ON COLUMN "public"."device_task_feedback"."occurred_at" IS '设备执行发生时刻；缺失时采用首次接收估计，并在payload_json.time_quality声明';
COMMENT ON COLUMN "public"."device_task_feedback"."received_at" IS '首次接收时间';
COMMENT ON COLUMN "public"."device_task_feedback"."feedback_type" IS 'accepted/started/progress/artifact/completed/failed/cancelled/rejected';
COMMENT ON COLUMN "public"."device_task_feedback"."execution_state" IS '执行结论；accepted/artifact可空，其余按映射更新公共状态';
COMMENT ON COLUMN "public"."device_task_feedback"."progress" IS '0～100百分比，未提供为NULL';
COMMENT ON COLUMN "public"."device_task_feedback"."error_code" IS '明确设备错误码或适配器规范错误码';
COMMENT ON COLUMN "public"."device_task_feedback"."error_message" IS '脱敏说明，入口限4000字符';
COMMENT ON COLUMN "public"."device_task_feedback"."schema_version" IS '反馈结构版本';
COMMENT ON COLUMN "public"."device_task_feedback"."payload_json" IS 'v1对象：可选summary(string，最多4000字符)、stage(string，最多64字符)、time_quality(device_reported/received_estimated)(device_reported/received_estimated)；文件及结果ID通过公共关系读取，不藏私有路径';
COMMENT ON COLUMN "public"."device_task_feedback"."payload_digest" IS '绑定、反馈键／序号、原发生时间、状态、载荷和规范附件引用的摘要';
COMMENT ON COLUMN "public"."device_task_feedback"."expires_at" IS '终态按该执行finished_at+7天固定；进行中采用所属绑定控制期限';
COMMENT ON TABLE "public"."device_task_feedback" IS 'HXJM v0.2；设备执行反馈：一次带稳定业务键及序号的反馈';

-- ----------------------------
-- Table structure for episode
-- ----------------------------
DROP TABLE IF EXISTS "public"."episode";
CREATE TABLE "public"."episode" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "title" text COLLATE "pg_catalog"."default",
  "start_ts" timestamptz(6) NOT NULL,
  "end_ts" timestamptz(6) NOT NULL,
  "target_id" uuid,
  "stranger_target_id" uuid,
  "meta" jsonb,
  "identity_id" uuid,
  "activity_type" varchar(64) COLLATE "pg_catalog"."default",
  "state" varchar(16) COLLATE "pg_catalog"."default",
  "end_reason" varchar(32) COLLATE "pg_catalog"."default",
  "coverage_json" jsonb,
  "revision" int8,
  "expires_at" timestamptz(6)
)
;

-- ----------------------------
-- Table structure for episode_media_link
-- ----------------------------
DROP TABLE IF EXISTS "public"."episode_media_link";
CREATE TABLE "public"."episode_media_link" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "episode_id" uuid NOT NULL,
  "media_asset_id" uuid NOT NULL,
  "note" text COLLATE "pg_catalog"."default",
  "created_at" timestamptz(6) NOT NULL DEFAULT now()
)
;

-- ----------------------------
-- Table structure for episode_tracklet_link
-- ----------------------------
DROP TABLE IF EXISTS "public"."episode_tracklet_link";
CREATE TABLE "public"."episode_tracklet_link" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "episode_id" uuid NOT NULL,
  "tracklet_id" uuid NOT NULL,
  "note" text COLLATE "pg_catalog"."default",
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "ordinal" int4
)
;

-- ----------------------------
-- Table structure for event_object_link
-- ----------------------------
DROP TABLE IF EXISTS "public"."event_object_link";
CREATE TABLE "public"."event_object_link" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "event_id" uuid NOT NULL,
  "identity_id" uuid,
  "tracklet_id" uuid,
  "sample_id" uuid,
  "object_role" varchar(32) COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'subject'::character varying,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6) NOT NULL
)
;

-- ----------------------------
-- Table structure for evidence_reference
-- ----------------------------
DROP TABLE IF EXISTS "public"."evidence_reference";
CREATE TABLE "public"."evidence_reference" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "activity_id" uuid,
  "event_id" uuid,
  "source_id" uuid,
  "asset_id" uuid,
  "original_tracklet_id" uuid,
  "original_result_id" uuid,
  "start_at" timestamptz(6) NOT NULL,
  "end_at" timestamptz(6),
  "fact_snapshot" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "provenance_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6) NOT NULL
)
;

-- ----------------------------
-- Table structure for feature
-- ----------------------------
DROP TABLE IF EXISTS "public"."feature";
CREATE TABLE "public"."feature" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "feature_space_id" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "dimensions" int4 NOT NULL,
  "embedding" vector NOT NULL,
  "sample_id" uuid,
  "tracklet_id" uuid,
  "identity_id" uuid,
  "run_id" uuid NOT NULL,
  "producer_feature_key" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "aggregation_method" varchar(32) COLLATE "pg_catalog"."default" NOT NULL,
  "input_count" int4 NOT NULL,
  "used_count" int4 NOT NULL,
  "state" varchar(16) COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'ready'::character varying,
  "processed_at" timestamptz(6) NOT NULL,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6)
)
;

-- ----------------------------
-- Table structure for feature_contribution
-- ----------------------------
DROP TABLE IF EXISTS "public"."feature_contribution";
CREATE TABLE "public"."feature_contribution" (
  "feature_id" uuid NOT NULL,
  "ordinal" int4 NOT NULL,
  "sample_id" uuid NOT NULL,
  "source_feature_id" uuid,
  "weight" float8 NOT NULL DEFAULT 1,
  "created_at" timestamptz(6) NOT NULL DEFAULT now()
)
;

-- ----------------------------
-- Table structure for feature_space
-- ----------------------------
DROP TABLE IF EXISTS "public"."feature_space";
CREATE TABLE "public"."feature_space" (
  "id" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "definition_sha256" char(64) COLLATE "pg_catalog"."default" NOT NULL,
  "definition_version" varchar(32) COLLATE "pg_catalog"."default" NOT NULL,
  "definition_text" text COLLATE "pg_catalog"."default" NOT NULL,
  "definition_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "object_type" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,
  "feature_kind" varchar(32) COLLATE "pg_catalog"."default" NOT NULL,
  "dimensions" int4 NOT NULL,
  "dtype" varchar(16) COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'float32'::character varying,
  "normalization" varchar(16) COLLATE "pg_catalog"."default" NOT NULL,
  "metric" varchar(16) COLLATE "pg_catalog"."default" NOT NULL,
  "enabled" bool NOT NULL DEFAULT true,
  "created_at" timestamptz(6) NOT NULL DEFAULT now()
)
;

-- ----------------------------
-- Table structure for hxjm_schema_migration
-- ----------------------------
DROP TABLE IF EXISTS "public"."hxjm_schema_migration";
CREATE TABLE "public"."hxjm_schema_migration" (
  "version" int4 NOT NULL,
  "digest" text COLLATE "pg_catalog"."default" NOT NULL,
  "applied_at" timestamptz(6) NOT NULL DEFAULT now()
)
;

-- ----------------------------
-- Table structure for identity
-- ----------------------------
DROP TABLE IF EXISTS "public"."identity";
CREATE TABLE "public"."identity" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "identity_kind" varchar(16) COLLATE "pg_catalog"."default" NOT NULL,
  "object_type" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,
  "display_no" int8 NOT NULL DEFAULT nextval('identity_display_no_seq'::regclass),
  "display_name" varchar(200) COLLATE "pg_catalog"."default",
  "employee_id" varchar(64) COLLATE "pg_catalog"."default",
  "registered_at" timestamptz(6),
  "first_seen_at" timestamptz(6),
  "last_seen_at" timestamptz(6),
  "enabled" bool NOT NULL DEFAULT true,
  "revision" int8 NOT NULL DEFAULT 1,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6)
)
;

-- ----------------------------
-- Table structure for identity_link
-- ----------------------------
DROP TABLE IF EXISTS "public"."identity_link";
CREATE TABLE "public"."identity_link" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "temporary_identity_id" uuid NOT NULL,
  "registered_identity_id" uuid NOT NULL,
  "valid_from" timestamptz(6) NOT NULL,
  "valid_to" timestamptz(6),
  "basis_type" varchar(32) COLLATE "pg_catalog"."default" NOT NULL,
  "score" float8,
  "run_id" uuid,
  "reason" text COLLATE "pg_catalog"."default",
  "revision" int8 NOT NULL DEFAULT 1,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6) NOT NULL
)
;

-- ----------------------------
-- Table structure for input_frame
-- ----------------------------
DROP TABLE IF EXISTS "public"."input_frame";
CREATE TABLE "public"."input_frame" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "stream_session_id" uuid NOT NULL,
  "frame_seq" int8 NOT NULL,
  "occurred_at" timestamptz(6) NOT NULL,
  "stream_pts_ms" int8,
  "media_asset_id" uuid,
  "media_pts_ms" int8,
  "time_quality" varchar(24) COLLATE "pg_catalog"."default" NOT NULL,
  "width" int4 NOT NULL,
  "height" int4 NOT NULL,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6) NOT NULL
)
;

-- ----------------------------
-- Table structure for legacy_identity_map
-- ----------------------------
DROP TABLE IF EXISTS "public"."legacy_identity_map";
CREATE TABLE "public"."legacy_identity_map" (
  "legacy_namespace" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,
  "legacy_id" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "identity_id" uuid NOT NULL,
  "sample_id" uuid,
  "feature_space_id" varchar(128) COLLATE "pg_catalog"."default",
  "created_at" timestamptz(6) NOT NULL DEFAULT now()
)
;

-- ----------------------------
-- Table structure for llm_report
-- ----------------------------
DROP TABLE IF EXISTS "public"."llm_report";
CREATE TABLE "public"."llm_report" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "episode_id" uuid,
  "vad_id" int4,
  "prompt_type" text COLLATE "pg_catalog"."default",
  "prompt_version" text COLLATE "pg_catalog"."default",
  "report_json" jsonb NOT NULL,
  "report_text" text COLLATE "pg_catalog"."default",
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "subject_kind" varchar(16) COLLATE "pg_catalog"."default",
  "subject_id" uuid,
  "event_id" uuid,
  "query_id" uuid,
  "report_type" varchar(64) COLLATE "pg_catalog"."default",
  "completeness" varchar(16) COLLATE "pg_catalog"."default",
  "coverage_json" jsonb,
  "task_id" uuid,
  "run_id" uuid,
  "model_version" varchar(128) COLLATE "pg_catalog"."default",
  "processed_at" timestamptz(6),
  "revision" int8,
  "expires_at" timestamptz(6)
)
;

-- ----------------------------
-- Table structure for media_asset
-- ----------------------------
DROP TABLE IF EXISTS "public"."media_asset";
CREATE TABLE "public"."media_asset" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "stream_id" varchar COLLATE "pg_catalog"."default",
  "asset_type" text COLLATE "pg_catalog"."default" NOT NULL,
  "start_ts" timestamptz(6) NOT NULL,
  "duration_ms" int8 NOT NULL,
  "play_url" text COLLATE "pg_catalog"."default",
  "oss_bucket" text COLLATE "pg_catalog"."default",
  "oss_key" text COLLATE "pg_catalog"."default",
  "content_type" text COLLATE "pg_catalog"."default",
  "meta" jsonb,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "source_id" uuid,
  "stream_session_id" uuid,
  "producer_key" varchar(128) COLLATE "pg_catalog"."default",
  "storage_key" text COLLATE "pg_catalog"."default",
  "byte_size" int8,
  "checksum_sha256" char(64) COLLATE "pg_catalog"."default",
  "write_attempt_id" uuid,
  "write_lease_until" timestamptz(6),
  "state" varchar(24) COLLATE "pg_catalog"."default",
  "delete_attempts" int4 NOT NULL DEFAULT 0,
  "last_error_code" varchar(64) COLLATE "pg_catalog"."default",
  "revision" int8 NOT NULL DEFAULT 1,
  "expires_at" timestamptz(6)
)
;

-- ----------------------------
-- Table structure for outbox_event
-- ----------------------------
DROP TABLE IF EXISTS "public"."outbox_event";
CREATE TABLE "public"."outbox_event" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "event_type" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,
  "aggregate_type" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,
  "aggregate_id" uuid NOT NULL,
  "aggregate_revision" int8 NOT NULL,
  "payload_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "state" varchar(16) COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'pending'::character varying,
  "attempt_count" int4 NOT NULL DEFAULT 0,
  "next_attempt_at" timestamptz(6) NOT NULL DEFAULT now(),
  "last_error_code" varchar(64) COLLATE "pg_catalog"."default",
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6) NOT NULL
)
;

-- ----------------------------
-- Table structure for processing_coverage
-- ----------------------------
DROP TABLE IF EXISTS "public"."processing_coverage";
CREATE TABLE "public"."processing_coverage" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "source_id" uuid NOT NULL,
  "stream_session_id" uuid,
  "run_id" uuid,
  "result_set_id" uuid,
  "stage" varchar(24) COLLATE "pg_catalog"."default" NOT NULL,
  "coverage_key" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "closed" bool NOT NULL DEFAULT false,
  "start_at" timestamptz(6) NOT NULL,
  "end_at" timestamptz(6) NOT NULL,
  "status" varchar(16) COLLATE "pg_catalog"."default" NOT NULL,
  "analyzed_frame_count" int8 NOT NULL DEFAULT 0,
  "saved_frame_count" int8 NOT NULL DEFAULT 0,
  "frame_manifest_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "reason_code" varchar(64) COLLATE "pg_catalog"."default",
  "revision" int8 NOT NULL DEFAULT 1,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6) NOT NULL
)
;

-- ----------------------------
-- Table structure for query_candidate
-- ----------------------------
DROP TABLE IF EXISTS "public"."query_candidate";
CREATE TABLE "public"."query_candidate" (
  "query_id" uuid NOT NULL,
  "candidate_id" varchar(32) COLLATE "pg_catalog"."default" NOT NULL,
  "sample_id" uuid NOT NULL,
  "object_type" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,
  "bbox_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "confidence" float8 NOT NULL,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6) NOT NULL
)
;

-- ----------------------------
-- Table structure for query_request
-- ----------------------------
DROP TABLE IF EXISTS "public"."query_request";
CREATE TABLE "public"."query_request" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "owner_user_id" int8,
  "session_id" uuid,
  "query_kind" varchar(32) COLLATE "pg_catalog"."default" NOT NULL,
  "object_type" varchar(64) COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'person'::character varying,
  "input_asset_id" uuid,
  "input_sample_id" uuid,
  "selected_candidate_id" varchar(32) COLLATE "pg_catalog"."default",
  "identity_id" uuid,
  "feature_space_id" varchar(128) COLLATE "pg_catalog"."default",
  "start_at" timestamptz(6),
  "end_at" timestamptz(6),
  "scope_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "state" varchar(24) COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'pending'::character varying,
  "coverage_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "task_id" uuid,
  "revision" int8 NOT NULL DEFAULT 1,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6) NOT NULL
)
;
COMMENT ON COLUMN "public"."query_request"."owner_user_id" IS 'NULL: shared business query; non-NULL: existing user-owned query';

-- ----------------------------
-- Table structure for reid_match
-- ----------------------------
DROP TABLE IF EXISTS "public"."reid_match";
CREATE TABLE "public"."reid_match" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "tracklet_id" uuid NOT NULL,
  "ts" timestamptz(6) NOT NULL,
  "similarity" float8 NOT NULL,
  "threshold" float8 NOT NULL,
  "matched" bool NOT NULL,
  "target_id" uuid,
  "stranger_target_id" uuid,
  "query_asset_base64" text COLLATE "pg_catalog"."default",
  "evidence_asset_base64" text COLLATE "pg_catalog"."default",
  "meta" jsonb,
  "created_at" timestamptz(6) NOT NULL DEFAULT now()
)
;

-- ----------------------------
-- Table structure for reid_target
-- ----------------------------
DROP TABLE IF EXISTS "public"."reid_target";
CREATE TABLE "public"."reid_target" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "employee_id" text COLLATE "pg_catalog"."default",
  "name" text COLLATE "pg_catalog"."default" NOT NULL,
  "source_asset_id" uuid,
  "embedding" vector(3072) NOT NULL,
  "embedding_model" text COLLATE "pg_catalog"."default" NOT NULL,
  "is_active" bool NOT NULL DEFAULT true,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now(),
  "image_base64" text COLLATE "pg_catalog"."default" NOT NULL
)
;

-- ----------------------------
-- Table structure for reid_target_vit
-- ----------------------------
DROP TABLE IF EXISTS "public"."reid_target_vit";
CREATE TABLE "public"."reid_target_vit" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "employee_id" text COLLATE "pg_catalog"."default",
  "name" text COLLATE "pg_catalog"."default" NOT NULL,
  "source_asset_id" uuid,
  "embedding" vector(1280) NOT NULL,
  "embedding_model" text COLLATE "pg_catalog"."default" NOT NULL,
  "is_active" bool NOT NULL DEFAULT true,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now(),
  "image_base64" text COLLATE "pg_catalog"."default" NOT NULL
)
;

-- ----------------------------
-- Table structure for report_evidence_link
-- ----------------------------
DROP TABLE IF EXISTS "public"."report_evidence_link";
CREATE TABLE "public"."report_evidence_link" (
  "report_id" uuid NOT NULL,
  "evidence_id" uuid NOT NULL,
  "report_revision" int8 NOT NULL,
  "ordinal" int4 NOT NULL,
  "created_at" timestamptz(6) NOT NULL DEFAULT now()
)
;

-- ----------------------------
-- Table structure for request_deduplication
-- ----------------------------
DROP TABLE IF EXISTS "public"."request_deduplication";
CREATE TABLE "public"."request_deduplication" (
  "actor_key" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "operation" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "request_id" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "request_digest" char(64) COLLATE "pg_catalog"."default" NOT NULL,
  "state" varchar(16) COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'accepted'::character varying,
  "task_id" uuid,
  "response_json" jsonb,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6) NOT NULL
)
;

-- ----------------------------
-- Table structure for result_selection
-- ----------------------------
DROP TABLE IF EXISTS "public"."result_selection";
CREATE TABLE "public"."result_selection" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "source_id" uuid NOT NULL,
  "capability_code" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,
  "range_start" timestamptz(6) NOT NULL,
  "range_end" timestamptz(6) NOT NULL,
  "result_set_id" uuid NOT NULL,
  "generation" int8 NOT NULL,
  "revision" int8 NOT NULL DEFAULT 1,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6) NOT NULL
)
;

-- ----------------------------
-- Table structure for result_set
-- ----------------------------
DROP TABLE IF EXISTS "public"."result_set";
CREATE TABLE "public"."result_set" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "run_id" uuid NOT NULL,
  "source_id" uuid,
  "input_asset_id" uuid,
  "stream_session_id" uuid,
  "capability_code" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,
  "set_key" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "generation" int8 NOT NULL,
  "state" varchar(16) COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'collecting'::character varying,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6) NOT NULL,
  "device_task_binding_id" uuid
)
;
COMMENT ON COLUMN "public"."result_set"."device_task_binding_id" IS '可空巡检设备执行归属；不替代本成果的算法run_id';

-- ----------------------------
-- Table structure for result_type
-- ----------------------------
DROP TABLE IF EXISTS "public"."result_type";
CREATE TABLE "public"."result_type" (
  "type_code" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,
  "schema_version" varchar(32) COLLATE "pg_catalog"."default" NOT NULL,
  "json_schema" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "max_inline_bytes" int4 NOT NULL DEFAULT 1048576,
  "enabled" bool NOT NULL DEFAULT true,
  "created_at" timestamptz(6) NOT NULL DEFAULT now()
)
;

-- ----------------------------
-- Table structure for sample
-- ----------------------------
DROP TABLE IF EXISTS "public"."sample";
CREATE TABLE "public"."sample" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "purpose" varchar(16) COLLATE "pg_catalog"."default" NOT NULL,
  "asset_id" uuid NOT NULL,
  "input_frame_id" uuid,
  "tracklet_id" uuid,
  "identity_id" uuid,
  "query_id" uuid,
  "occurred_at" timestamptz(6) NOT NULL,
  "bbox_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "quality_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "available" bool NOT NULL DEFAULT true,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6)
)
;

-- ----------------------------
-- Table structure for search_hit
-- ----------------------------
DROP TABLE IF EXISTS "public"."search_hit";
CREATE TABLE "public"."search_hit" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "query_id" uuid NOT NULL,
  "rank_no" int4 NOT NULL,
  "hit_kind" varchar(16) COLLATE "pg_catalog"."default" NOT NULL,
  "identity_id" uuid,
  "tracklet_id" uuid,
  "sample_id" uuid NOT NULL,
  "feature_id" uuid,
  "feature_space_id" varchar(128) COLLATE "pg_catalog"."default",
  "score" float8,
  "score_metric" varchar(32) COLLATE "pg_catalog"."default",
  "basis_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6) NOT NULL
)
;

-- ----------------------------
-- Table structure for stranger_target
-- ----------------------------
DROP TABLE IF EXISTS "public"."stranger_target";
CREATE TABLE "public"."stranger_target" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "code" text COLLATE "pg_catalog"."default" NOT NULL,
  "status" text COLLATE "pg_catalog"."default" NOT NULL,
  "embedding" vector(3072),
  "embedding_model" text COLLATE "pg_catalog"."default" NOT NULL,
  "is_active" bool NOT NULL DEFAULT true,
  "promoted_target_id" uuid,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now(),
  "image_base64" text COLLATE "pg_catalog"."default"
)
;

-- ----------------------------
-- Table structure for stream_session
-- ----------------------------
DROP TABLE IF EXISTS "public"."stream_session";
CREATE TABLE "public"."stream_session" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "source_id" uuid NOT NULL,
  "camera_stream_id" uuid,
  "session_key" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "started_at" timestamptz(6) NOT NULL,
  "ended_at" timestamptz(6),
  "time_origin_at" timestamptz(6) NOT NULL,
  "time_basis" varchar(24) COLLATE "pg_catalog"."default" NOT NULL,
  "source_timezone" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,
  "source_width" int4 NOT NULL,
  "source_height" int4 NOT NULL,
  "state" varchar(16) COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'open'::character varying,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6) NOT NULL
)
;

-- ----------------------------
-- Table structure for task_attempt
-- ----------------------------
DROP TABLE IF EXISTS "public"."task_attempt";
CREATE TABLE "public"."task_attempt" (
  "run_id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "task_id" uuid NOT NULL,
  "generation" int8 NOT NULL,
  "legacy_run_id" varchar(64) COLLATE "pg_catalog"."default",
  "state" varchar(24) COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'pending'::character varying,
  "implementation_code" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "implementation_version" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "parameters_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "lease_owner" varchar(128) COLLATE "pg_catalog"."default",
  "lease_until" timestamptz(6),
  "started_at" timestamptz(6),
  "finished_at" timestamptz(6),
  "error_code" varchar(64) COLLATE "pg_catalog"."default",
  "error_message" text COLLATE "pg_catalog"."default",
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6) NOT NULL,
  "execution_token" uuid,
  "send_started" bool NOT NULL DEFAULT false,
  "terminal_digest" char(64) COLLATE "pg_catalog"."default"
)
;

-- ----------------------------
-- Table structure for task_output
-- ----------------------------
DROP TABLE IF EXISTS "public"."task_output";
CREATE TABLE "public"."task_output" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "task_id" uuid NOT NULL,
  "run_id" uuid NOT NULL,
  "result_type" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,
  "schema_version" varchar(32) COLLATE "pg_catalog"."default" NOT NULL,
  "payload_json" jsonb NOT NULL,
  "asset_id" uuid,
  "producer_result_key" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "payload_digest" char(64) COLLATE "pg_catalog"."default" NOT NULL,
  "created_at" timestamptz(6) NOT NULL DEFAULT now()
)
;

-- ----------------------------
-- Table structure for track_identity_assignment
-- ----------------------------
DROP TABLE IF EXISTS "public"."track_identity_assignment";
CREATE TABLE "public"."track_identity_assignment" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "tracklet_id" uuid NOT NULL,
  "identity_id" uuid NOT NULL,
  "valid_from" timestamptz(6) NOT NULL,
  "valid_to" timestamptz(6),
  "basis_type" varchar(32) COLLATE "pg_catalog"."default" NOT NULL,
  "score" float8,
  "run_id" uuid,
  "reason" text COLLATE "pg_catalog"."default",
  "revision" int8 NOT NULL DEFAULT 1,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6) NOT NULL
)
;

-- ----------------------------
-- Table structure for tracking_context
-- ----------------------------
DROP TABLE IF EXISTS "public"."tracking_context";
CREATE TABLE "public"."tracking_context" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "stream_session_id" uuid NOT NULL,
  "run_id" uuid NOT NULL,
  "context_key" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "source_width" int4 NOT NULL,
  "source_height" int4 NOT NULL,
  "started_at" timestamptz(6) NOT NULL,
  "ended_at" timestamptz(6),
  "reset_reason" varchar(64) COLLATE "pg_catalog"."default",
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "expires_at" timestamptz(6) NOT NULL
)
;

-- ----------------------------
-- Table structure for tracklet
-- ----------------------------
DROP TABLE IF EXISTS "public"."tracklet";
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
  "repr_embedding" vector(3072),
  "embedding_model" text COLLATE "pg_catalog"."default",
  "trajectory_points" jsonb,
  "meta" jsonb,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now(),
  "source_id" uuid,
  "stream_session_id" uuid,
  "tracking_context_id" uuid,
  "local_track_id" int8,
  "origin_result_set_id" uuid,
  "canonical_tracklet_id" uuid,
  "first_observed_at" timestamptz(6),
  "last_observed_at" timestamptz(6),
  "end_reason" varchar(32) COLLATE "pg_catalog"."default",
  "revision" int8 NOT NULL DEFAULT 1,
  "expires_at" timestamptz(6)
)
;

-- ----------------------------
-- Table structure for unified_event
-- ----------------------------
DROP TABLE IF EXISTS "public"."unified_event";
CREATE TABLE "public"."unified_event" (
  "event_id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "event_type" text COLLATE "pg_catalog"."default" NOT NULL,
  "stream_id" text COLLATE "pg_catalog"."default",
  "start_time" timestamptz(6),
  "end_time" timestamptz(6),
  "status" text COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'unknown'::text,
  "risk_level" text COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'unknown'::text,
  "location" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "title" text COLLATE "pg_catalog"."default" NOT NULL,
  "evidence" jsonb NOT NULL DEFAULT '[]'::jsonb,
  "reports" jsonb NOT NULL DEFAULT '[]'::jsonb,
  "sources" text[] COLLATE "pg_catalog"."default" NOT NULL,
  "source_refs" jsonb NOT NULL,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "data_origin" text COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'unknown'::text
)
;
COMMENT ON COLUMN "public"."unified_event"."event_id" IS '业务事件唯一UUID；同一事件更新、补证据或报告时保持不变';
COMMENT ON COLUMN "public"."unified_event"."event_type" IS '统一业务类型，如 behavior.fall/person.appeared/face.recognized；不是算法名称';
COMMENT ON COLUMN "public"."unified_event"."stream_id" IS '视频流标识，如 live/camera_1；视频事件应填写，非视频或历史未知允许为空';
COMMENT ON COLUMN "public"."unified_event"."start_time" IS '事件开始/首次观测时间；历史未知允许为空，不以入库时间伪造';
COMMENT ON COLUMN "public"."unified_event"."end_time" IS '事件发生过程结束时间；持续中为空，瞬时事件可等于开始时间';
COMMENT ON COLUMN "public"."unified_event"."status" IS '发生状态：active持续中/ended已结束/point瞬时/unknown未知；不是人工处理状态';
COMMENT ON COLUMN "public"."unified_event"."risk_level" IS '业务风险：unknown/info/low/medium/high/critical；与算法分数分开';
COMMENT ON COLUMN "public"."unified_event"."location" IS '位置对象：camera_id、zone_id、name；未知字段可为空';
COMMENT ON COLUMN "public"."unified_event"."title" IS '人类可读的事件标题';
COMMENT ON COLUMN "public"."unified_event"."evidence" IS '证据数组；每项建议 type/role/ref/status，ref 为 system/entity/id 对象；不存图片正文';
COMMENT ON COLUMN "public"."unified_event"."reports" IS '报告引用数组；建议 ref/status，支持多个报告；正文保留在原报告资源';
COMMENT ON COLUMN "public"."unified_event"."sources" IS '算法来源数组，如 {vad,llm}；不将来源名称用作业务类型';
COMMENT ON COLUMN "public"."unified_event"."source_refs" IS '非空原始记录引用数组；建议 source/system/entity/id，支持追溯；不自动实现去重';
COMMENT ON COLUMN "public"."unified_event"."created_at" IS '统一事件首次入库时间；与事件开始时间不同';
COMMENT ON COLUMN "public"."unified_event"."data_origin" IS '数据来源：production/demo/synthetic/replay/historical_import/unknown；演示数据不得标为production';
COMMENT ON TABLE "public"."unified_event" IS '统一业务事件草案表；暂不接入现有系统，创建时不导入数据';

-- ----------------------------
-- Table structure for vad
-- ----------------------------
DROP TABLE IF EXISTS "public"."vad";
CREATE TABLE "public"."vad" (
  "id" int4 NOT NULL GENERATED ALWAYS AS IDENTITY (
INCREMENT 1
MINVALUE  1
MAXVALUE 2147483647
START 1
CACHE 1
),
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "media_asset_id" uuid NOT NULL,
  "stream_id" varchar COLLATE "pg_catalog"."default",
  "frame_vad_base64" text COLLATE "pg_catalog"."default",
  "anomaly_name" varchar COLLATE "pg_catalog"."default",
  "anomaly_level" int4
)
;

-- ----------------------------
-- Function structure for armor
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."armor"(bytea, _text, _text);
CREATE FUNCTION "public"."armor"(bytea, _text, _text)
  RETURNS "pg_catalog"."text" AS '$libdir/pgcrypto', 'pg_armor'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for armor
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."armor"(bytea);
CREATE FUNCTION "public"."armor"(bytea)
  RETURNS "pg_catalog"."text" AS '$libdir/pgcrypto', 'pg_armor'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for array_to_halfvec
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."array_to_halfvec"(_numeric, int4, bool);
CREATE FUNCTION "public"."array_to_halfvec"(_numeric, int4, bool)
  RETURNS "public"."halfvec" AS '$libdir/vector', 'array_to_halfvec'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for array_to_halfvec
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."array_to_halfvec"(_int4, int4, bool);
CREATE FUNCTION "public"."array_to_halfvec"(_int4, int4, bool)
  RETURNS "public"."halfvec" AS '$libdir/vector', 'array_to_halfvec'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for array_to_halfvec
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."array_to_halfvec"(_float4, int4, bool);
CREATE FUNCTION "public"."array_to_halfvec"(_float4, int4, bool)
  RETURNS "public"."halfvec" AS '$libdir/vector', 'array_to_halfvec'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for array_to_halfvec
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."array_to_halfvec"(_float8, int4, bool);
CREATE FUNCTION "public"."array_to_halfvec"(_float8, int4, bool)
  RETURNS "public"."halfvec" AS '$libdir/vector', 'array_to_halfvec'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for array_to_sparsevec
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."array_to_sparsevec"(_int4, int4, bool);
CREATE FUNCTION "public"."array_to_sparsevec"(_int4, int4, bool)
  RETURNS "public"."sparsevec" AS '$libdir/vector', 'array_to_sparsevec'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for array_to_sparsevec
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."array_to_sparsevec"(_numeric, int4, bool);
CREATE FUNCTION "public"."array_to_sparsevec"(_numeric, int4, bool)
  RETURNS "public"."sparsevec" AS '$libdir/vector', 'array_to_sparsevec'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for array_to_sparsevec
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."array_to_sparsevec"(_float8, int4, bool);
CREATE FUNCTION "public"."array_to_sparsevec"(_float8, int4, bool)
  RETURNS "public"."sparsevec" AS '$libdir/vector', 'array_to_sparsevec'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for array_to_sparsevec
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."array_to_sparsevec"(_float4, int4, bool);
CREATE FUNCTION "public"."array_to_sparsevec"(_float4, int4, bool)
  RETURNS "public"."sparsevec" AS '$libdir/vector', 'array_to_sparsevec'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for array_to_vector
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."array_to_vector"(_float4, int4, bool);
CREATE FUNCTION "public"."array_to_vector"(_float4, int4, bool)
  RETURNS "public"."vector" AS '$libdir/vector', 'array_to_vector'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for array_to_vector
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."array_to_vector"(_float8, int4, bool);
CREATE FUNCTION "public"."array_to_vector"(_float8, int4, bool)
  RETURNS "public"."vector" AS '$libdir/vector', 'array_to_vector'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for array_to_vector
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."array_to_vector"(_numeric, int4, bool);
CREATE FUNCTION "public"."array_to_vector"(_numeric, int4, bool)
  RETURNS "public"."vector" AS '$libdir/vector', 'array_to_vector'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for array_to_vector
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."array_to_vector"(_int4, int4, bool);
CREATE FUNCTION "public"."array_to_vector"(_int4, int4, bool)
  RETURNS "public"."vector" AS '$libdir/vector', 'array_to_vector'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for binary_quantize
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."binary_quantize"("public"."vector");
CREATE FUNCTION "public"."binary_quantize"("public"."vector")
  RETURNS "pg_catalog"."bit" AS '$libdir/vector', 'binary_quantize'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for binary_quantize
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."binary_quantize"("public"."halfvec");
CREATE FUNCTION "public"."binary_quantize"("public"."halfvec")
  RETURNS "pg_catalog"."bit" AS '$libdir/vector', 'halfvec_binary_quantize'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for cash_dist
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."cash_dist"(money, money);
CREATE FUNCTION "public"."cash_dist"(money, money)
  RETURNS "pg_catalog"."money" AS '$libdir/btree_gist', 'cash_dist'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for cosine_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."cosine_distance"("public"."vector", "public"."vector");
CREATE FUNCTION "public"."cosine_distance"("public"."vector", "public"."vector")
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'cosine_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for cosine_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."cosine_distance"("public"."halfvec", "public"."halfvec");
CREATE FUNCTION "public"."cosine_distance"("public"."halfvec", "public"."halfvec")
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'halfvec_cosine_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for cosine_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."cosine_distance"("public"."sparsevec", "public"."sparsevec");
CREATE FUNCTION "public"."cosine_distance"("public"."sparsevec", "public"."sparsevec")
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'sparsevec_cosine_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for crypt
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."crypt"(text, text);
CREATE FUNCTION "public"."crypt"(text, text)
  RETURNS "pg_catalog"."text" AS '$libdir/pgcrypto', 'pg_crypt'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for date_dist
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."date_dist"(date, date);
CREATE FUNCTION "public"."date_dist"(date, date)
  RETURNS "pg_catalog"."int4" AS '$libdir/btree_gist', 'date_dist'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for dearmor
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."dearmor"(text);
CREATE FUNCTION "public"."dearmor"(text)
  RETURNS "pg_catalog"."bytea" AS '$libdir/pgcrypto', 'pg_dearmor'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for decrypt
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."decrypt"(bytea, bytea, text);
CREATE FUNCTION "public"."decrypt"(bytea, bytea, text)
  RETURNS "pg_catalog"."bytea" AS '$libdir/pgcrypto', 'pg_decrypt'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for decrypt_iv
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."decrypt_iv"(bytea, bytea, bytea, text);
CREATE FUNCTION "public"."decrypt_iv"(bytea, bytea, bytea, text)
  RETURNS "pg_catalog"."bytea" AS '$libdir/pgcrypto', 'pg_decrypt_iv'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for digest
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."digest"(text, text);
CREATE FUNCTION "public"."digest"(text, text)
  RETURNS "pg_catalog"."bytea" AS '$libdir/pgcrypto', 'pg_digest'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for digest
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."digest"(bytea, text);
CREATE FUNCTION "public"."digest"(bytea, text)
  RETURNS "pg_catalog"."bytea" AS '$libdir/pgcrypto', 'pg_digest'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for encrypt
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."encrypt"(bytea, bytea, text);
CREATE FUNCTION "public"."encrypt"(bytea, bytea, text)
  RETURNS "pg_catalog"."bytea" AS '$libdir/pgcrypto', 'pg_encrypt'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for encrypt_iv
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."encrypt_iv"(bytea, bytea, bytea, text);
CREATE FUNCTION "public"."encrypt_iv"(bytea, bytea, bytea, text)
  RETURNS "pg_catalog"."bytea" AS '$libdir/pgcrypto', 'pg_encrypt_iv'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for float4_dist
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."float4_dist"(float4, float4);
CREATE FUNCTION "public"."float4_dist"(float4, float4)
  RETURNS "pg_catalog"."float4" AS '$libdir/btree_gist', 'float4_dist'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for float8_dist
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."float8_dist"(float8, float8);
CREATE FUNCTION "public"."float8_dist"(float8, float8)
  RETURNS "pg_catalog"."float8" AS '$libdir/btree_gist', 'float8_dist'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_bit_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_bit_compress"(internal);
CREATE FUNCTION "public"."gbt_bit_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_bit_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_bit_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_bit_consistent"(internal, bit, int2, oid, internal);
CREATE FUNCTION "public"."gbt_bit_consistent"(internal, bit, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_bit_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_bit_penalty
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_bit_penalty"(internal, internal, internal);
CREATE FUNCTION "public"."gbt_bit_penalty"(internal, internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_bit_penalty'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_bit_picksplit
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_bit_picksplit"(internal, internal);
CREATE FUNCTION "public"."gbt_bit_picksplit"(internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_bit_picksplit'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_bit_same
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_bit_same"("public"."gbtreekey_var", "public"."gbtreekey_var", internal);
CREATE FUNCTION "public"."gbt_bit_same"("public"."gbtreekey_var", "public"."gbtreekey_var", internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_bit_same'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_bit_union
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_bit_union"(internal, internal);
CREATE FUNCTION "public"."gbt_bit_union"(internal, internal)
  RETURNS "public"."gbtreekey_var" AS '$libdir/btree_gist', 'gbt_bit_union'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_bool_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_bool_compress"(internal);
CREATE FUNCTION "public"."gbt_bool_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_bool_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_bool_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_bool_consistent"(internal, bool, int2, oid, internal);
CREATE FUNCTION "public"."gbt_bool_consistent"(internal, bool, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_bool_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_bool_fetch
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_bool_fetch"(internal);
CREATE FUNCTION "public"."gbt_bool_fetch"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_bool_fetch'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_bool_penalty
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_bool_penalty"(internal, internal, internal);
CREATE FUNCTION "public"."gbt_bool_penalty"(internal, internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_bool_penalty'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_bool_picksplit
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_bool_picksplit"(internal, internal);
CREATE FUNCTION "public"."gbt_bool_picksplit"(internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_bool_picksplit'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_bool_same
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_bool_same"("public"."gbtreekey2", "public"."gbtreekey2", internal);
CREATE FUNCTION "public"."gbt_bool_same"("public"."gbtreekey2", "public"."gbtreekey2", internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_bool_same'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_bool_union
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_bool_union"(internal, internal);
CREATE FUNCTION "public"."gbt_bool_union"(internal, internal)
  RETURNS "public"."gbtreekey2" AS '$libdir/btree_gist', 'gbt_bool_union'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_bpchar_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_bpchar_compress"(internal);
CREATE FUNCTION "public"."gbt_bpchar_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_bpchar_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_bpchar_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_bpchar_consistent"(internal, bpchar, int2, oid, internal);
CREATE FUNCTION "public"."gbt_bpchar_consistent"(internal, bpchar, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_bpchar_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_bytea_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_bytea_compress"(internal);
CREATE FUNCTION "public"."gbt_bytea_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_bytea_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_bytea_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_bytea_consistent"(internal, bytea, int2, oid, internal);
CREATE FUNCTION "public"."gbt_bytea_consistent"(internal, bytea, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_bytea_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_bytea_penalty
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_bytea_penalty"(internal, internal, internal);
CREATE FUNCTION "public"."gbt_bytea_penalty"(internal, internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_bytea_penalty'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_bytea_picksplit
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_bytea_picksplit"(internal, internal);
CREATE FUNCTION "public"."gbt_bytea_picksplit"(internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_bytea_picksplit'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_bytea_same
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_bytea_same"("public"."gbtreekey_var", "public"."gbtreekey_var", internal);
CREATE FUNCTION "public"."gbt_bytea_same"("public"."gbtreekey_var", "public"."gbtreekey_var", internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_bytea_same'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_bytea_union
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_bytea_union"(internal, internal);
CREATE FUNCTION "public"."gbt_bytea_union"(internal, internal)
  RETURNS "public"."gbtreekey_var" AS '$libdir/btree_gist', 'gbt_bytea_union'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_cash_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_cash_compress"(internal);
CREATE FUNCTION "public"."gbt_cash_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_cash_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_cash_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_cash_consistent"(internal, money, int2, oid, internal);
CREATE FUNCTION "public"."gbt_cash_consistent"(internal, money, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_cash_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_cash_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_cash_distance"(internal, money, int2, oid, internal);
CREATE FUNCTION "public"."gbt_cash_distance"(internal, money, int2, oid, internal)
  RETURNS "pg_catalog"."float8" AS '$libdir/btree_gist', 'gbt_cash_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_cash_fetch
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_cash_fetch"(internal);
CREATE FUNCTION "public"."gbt_cash_fetch"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_cash_fetch'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_cash_penalty
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_cash_penalty"(internal, internal, internal);
CREATE FUNCTION "public"."gbt_cash_penalty"(internal, internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_cash_penalty'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_cash_picksplit
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_cash_picksplit"(internal, internal);
CREATE FUNCTION "public"."gbt_cash_picksplit"(internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_cash_picksplit'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_cash_same
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_cash_same"("public"."gbtreekey16", "public"."gbtreekey16", internal);
CREATE FUNCTION "public"."gbt_cash_same"("public"."gbtreekey16", "public"."gbtreekey16", internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_cash_same'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_cash_union
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_cash_union"(internal, internal);
CREATE FUNCTION "public"."gbt_cash_union"(internal, internal)
  RETURNS "public"."gbtreekey16" AS '$libdir/btree_gist', 'gbt_cash_union'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_date_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_date_compress"(internal);
CREATE FUNCTION "public"."gbt_date_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_date_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_date_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_date_consistent"(internal, date, int2, oid, internal);
CREATE FUNCTION "public"."gbt_date_consistent"(internal, date, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_date_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_date_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_date_distance"(internal, date, int2, oid, internal);
CREATE FUNCTION "public"."gbt_date_distance"(internal, date, int2, oid, internal)
  RETURNS "pg_catalog"."float8" AS '$libdir/btree_gist', 'gbt_date_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_date_fetch
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_date_fetch"(internal);
CREATE FUNCTION "public"."gbt_date_fetch"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_date_fetch'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_date_penalty
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_date_penalty"(internal, internal, internal);
CREATE FUNCTION "public"."gbt_date_penalty"(internal, internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_date_penalty'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_date_picksplit
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_date_picksplit"(internal, internal);
CREATE FUNCTION "public"."gbt_date_picksplit"(internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_date_picksplit'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_date_same
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_date_same"("public"."gbtreekey8", "public"."gbtreekey8", internal);
CREATE FUNCTION "public"."gbt_date_same"("public"."gbtreekey8", "public"."gbtreekey8", internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_date_same'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_date_union
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_date_union"(internal, internal);
CREATE FUNCTION "public"."gbt_date_union"(internal, internal)
  RETURNS "public"."gbtreekey8" AS '$libdir/btree_gist', 'gbt_date_union'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_decompress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_decompress"(internal);
CREATE FUNCTION "public"."gbt_decompress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_decompress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_enum_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_enum_compress"(internal);
CREATE FUNCTION "public"."gbt_enum_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_enum_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_enum_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_enum_consistent"(internal, anyenum, int2, oid, internal);
CREATE FUNCTION "public"."gbt_enum_consistent"(internal, anyenum, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_enum_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_enum_fetch
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_enum_fetch"(internal);
CREATE FUNCTION "public"."gbt_enum_fetch"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_enum_fetch'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_enum_penalty
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_enum_penalty"(internal, internal, internal);
CREATE FUNCTION "public"."gbt_enum_penalty"(internal, internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_enum_penalty'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_enum_picksplit
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_enum_picksplit"(internal, internal);
CREATE FUNCTION "public"."gbt_enum_picksplit"(internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_enum_picksplit'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_enum_same
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_enum_same"("public"."gbtreekey8", "public"."gbtreekey8", internal);
CREATE FUNCTION "public"."gbt_enum_same"("public"."gbtreekey8", "public"."gbtreekey8", internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_enum_same'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_enum_union
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_enum_union"(internal, internal);
CREATE FUNCTION "public"."gbt_enum_union"(internal, internal)
  RETURNS "public"."gbtreekey8" AS '$libdir/btree_gist', 'gbt_enum_union'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_float4_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_float4_compress"(internal);
CREATE FUNCTION "public"."gbt_float4_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_float4_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_float4_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_float4_consistent"(internal, float4, int2, oid, internal);
CREATE FUNCTION "public"."gbt_float4_consistent"(internal, float4, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_float4_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_float4_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_float4_distance"(internal, float4, int2, oid, internal);
CREATE FUNCTION "public"."gbt_float4_distance"(internal, float4, int2, oid, internal)
  RETURNS "pg_catalog"."float8" AS '$libdir/btree_gist', 'gbt_float4_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_float4_fetch
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_float4_fetch"(internal);
CREATE FUNCTION "public"."gbt_float4_fetch"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_float4_fetch'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_float4_penalty
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_float4_penalty"(internal, internal, internal);
CREATE FUNCTION "public"."gbt_float4_penalty"(internal, internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_float4_penalty'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_float4_picksplit
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_float4_picksplit"(internal, internal);
CREATE FUNCTION "public"."gbt_float4_picksplit"(internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_float4_picksplit'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_float4_same
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_float4_same"("public"."gbtreekey8", "public"."gbtreekey8", internal);
CREATE FUNCTION "public"."gbt_float4_same"("public"."gbtreekey8", "public"."gbtreekey8", internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_float4_same'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_float4_union
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_float4_union"(internal, internal);
CREATE FUNCTION "public"."gbt_float4_union"(internal, internal)
  RETURNS "public"."gbtreekey8" AS '$libdir/btree_gist', 'gbt_float4_union'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_float8_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_float8_compress"(internal);
CREATE FUNCTION "public"."gbt_float8_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_float8_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_float8_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_float8_consistent"(internal, float8, int2, oid, internal);
CREATE FUNCTION "public"."gbt_float8_consistent"(internal, float8, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_float8_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_float8_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_float8_distance"(internal, float8, int2, oid, internal);
CREATE FUNCTION "public"."gbt_float8_distance"(internal, float8, int2, oid, internal)
  RETURNS "pg_catalog"."float8" AS '$libdir/btree_gist', 'gbt_float8_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_float8_fetch
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_float8_fetch"(internal);
CREATE FUNCTION "public"."gbt_float8_fetch"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_float8_fetch'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_float8_penalty
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_float8_penalty"(internal, internal, internal);
CREATE FUNCTION "public"."gbt_float8_penalty"(internal, internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_float8_penalty'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_float8_picksplit
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_float8_picksplit"(internal, internal);
CREATE FUNCTION "public"."gbt_float8_picksplit"(internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_float8_picksplit'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_float8_same
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_float8_same"("public"."gbtreekey16", "public"."gbtreekey16", internal);
CREATE FUNCTION "public"."gbt_float8_same"("public"."gbtreekey16", "public"."gbtreekey16", internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_float8_same'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_float8_union
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_float8_union"(internal, internal);
CREATE FUNCTION "public"."gbt_float8_union"(internal, internal)
  RETURNS "public"."gbtreekey16" AS '$libdir/btree_gist', 'gbt_float8_union'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_inet_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_inet_compress"(internal);
CREATE FUNCTION "public"."gbt_inet_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_inet_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_inet_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_inet_consistent"(internal, inet, int2, oid, internal);
CREATE FUNCTION "public"."gbt_inet_consistent"(internal, inet, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_inet_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_inet_penalty
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_inet_penalty"(internal, internal, internal);
CREATE FUNCTION "public"."gbt_inet_penalty"(internal, internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_inet_penalty'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_inet_picksplit
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_inet_picksplit"(internal, internal);
CREATE FUNCTION "public"."gbt_inet_picksplit"(internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_inet_picksplit'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_inet_same
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_inet_same"("public"."gbtreekey16", "public"."gbtreekey16", internal);
CREATE FUNCTION "public"."gbt_inet_same"("public"."gbtreekey16", "public"."gbtreekey16", internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_inet_same'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_inet_union
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_inet_union"(internal, internal);
CREATE FUNCTION "public"."gbt_inet_union"(internal, internal)
  RETURNS "public"."gbtreekey16" AS '$libdir/btree_gist', 'gbt_inet_union'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int2_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int2_compress"(internal);
CREATE FUNCTION "public"."gbt_int2_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_int2_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int2_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int2_consistent"(internal, int2, int2, oid, internal);
CREATE FUNCTION "public"."gbt_int2_consistent"(internal, int2, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_int2_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int2_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int2_distance"(internal, int2, int2, oid, internal);
CREATE FUNCTION "public"."gbt_int2_distance"(internal, int2, int2, oid, internal)
  RETURNS "pg_catalog"."float8" AS '$libdir/btree_gist', 'gbt_int2_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int2_fetch
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int2_fetch"(internal);
CREATE FUNCTION "public"."gbt_int2_fetch"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_int2_fetch'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int2_penalty
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int2_penalty"(internal, internal, internal);
CREATE FUNCTION "public"."gbt_int2_penalty"(internal, internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_int2_penalty'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int2_picksplit
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int2_picksplit"(internal, internal);
CREATE FUNCTION "public"."gbt_int2_picksplit"(internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_int2_picksplit'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int2_same
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int2_same"("public"."gbtreekey4", "public"."gbtreekey4", internal);
CREATE FUNCTION "public"."gbt_int2_same"("public"."gbtreekey4", "public"."gbtreekey4", internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_int2_same'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int2_union
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int2_union"(internal, internal);
CREATE FUNCTION "public"."gbt_int2_union"(internal, internal)
  RETURNS "public"."gbtreekey4" AS '$libdir/btree_gist', 'gbt_int2_union'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int4_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int4_compress"(internal);
CREATE FUNCTION "public"."gbt_int4_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_int4_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int4_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int4_consistent"(internal, int4, int2, oid, internal);
CREATE FUNCTION "public"."gbt_int4_consistent"(internal, int4, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_int4_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int4_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int4_distance"(internal, int4, int2, oid, internal);
CREATE FUNCTION "public"."gbt_int4_distance"(internal, int4, int2, oid, internal)
  RETURNS "pg_catalog"."float8" AS '$libdir/btree_gist', 'gbt_int4_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int4_fetch
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int4_fetch"(internal);
CREATE FUNCTION "public"."gbt_int4_fetch"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_int4_fetch'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int4_penalty
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int4_penalty"(internal, internal, internal);
CREATE FUNCTION "public"."gbt_int4_penalty"(internal, internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_int4_penalty'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int4_picksplit
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int4_picksplit"(internal, internal);
CREATE FUNCTION "public"."gbt_int4_picksplit"(internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_int4_picksplit'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int4_same
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int4_same"("public"."gbtreekey8", "public"."gbtreekey8", internal);
CREATE FUNCTION "public"."gbt_int4_same"("public"."gbtreekey8", "public"."gbtreekey8", internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_int4_same'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int4_union
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int4_union"(internal, internal);
CREATE FUNCTION "public"."gbt_int4_union"(internal, internal)
  RETURNS "public"."gbtreekey8" AS '$libdir/btree_gist', 'gbt_int4_union'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int8_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int8_compress"(internal);
CREATE FUNCTION "public"."gbt_int8_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_int8_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int8_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int8_consistent"(internal, int8, int2, oid, internal);
CREATE FUNCTION "public"."gbt_int8_consistent"(internal, int8, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_int8_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int8_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int8_distance"(internal, int8, int2, oid, internal);
CREATE FUNCTION "public"."gbt_int8_distance"(internal, int8, int2, oid, internal)
  RETURNS "pg_catalog"."float8" AS '$libdir/btree_gist', 'gbt_int8_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int8_fetch
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int8_fetch"(internal);
CREATE FUNCTION "public"."gbt_int8_fetch"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_int8_fetch'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int8_penalty
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int8_penalty"(internal, internal, internal);
CREATE FUNCTION "public"."gbt_int8_penalty"(internal, internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_int8_penalty'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int8_picksplit
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int8_picksplit"(internal, internal);
CREATE FUNCTION "public"."gbt_int8_picksplit"(internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_int8_picksplit'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int8_same
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int8_same"("public"."gbtreekey16", "public"."gbtreekey16", internal);
CREATE FUNCTION "public"."gbt_int8_same"("public"."gbtreekey16", "public"."gbtreekey16", internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_int8_same'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_int8_union
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_int8_union"(internal, internal);
CREATE FUNCTION "public"."gbt_int8_union"(internal, internal)
  RETURNS "public"."gbtreekey16" AS '$libdir/btree_gist', 'gbt_int8_union'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_intv_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_intv_compress"(internal);
CREATE FUNCTION "public"."gbt_intv_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_intv_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_intv_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_intv_consistent"(internal, interval, int2, oid, internal);
CREATE FUNCTION "public"."gbt_intv_consistent"(internal, interval, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_intv_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_intv_decompress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_intv_decompress"(internal);
CREATE FUNCTION "public"."gbt_intv_decompress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_intv_decompress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_intv_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_intv_distance"(internal, interval, int2, oid, internal);
CREATE FUNCTION "public"."gbt_intv_distance"(internal, interval, int2, oid, internal)
  RETURNS "pg_catalog"."float8" AS '$libdir/btree_gist', 'gbt_intv_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_intv_fetch
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_intv_fetch"(internal);
CREATE FUNCTION "public"."gbt_intv_fetch"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_intv_fetch'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_intv_penalty
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_intv_penalty"(internal, internal, internal);
CREATE FUNCTION "public"."gbt_intv_penalty"(internal, internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_intv_penalty'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_intv_picksplit
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_intv_picksplit"(internal, internal);
CREATE FUNCTION "public"."gbt_intv_picksplit"(internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_intv_picksplit'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_intv_same
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_intv_same"("public"."gbtreekey32", "public"."gbtreekey32", internal);
CREATE FUNCTION "public"."gbt_intv_same"("public"."gbtreekey32", "public"."gbtreekey32", internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_intv_same'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_intv_union
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_intv_union"(internal, internal);
CREATE FUNCTION "public"."gbt_intv_union"(internal, internal)
  RETURNS "public"."gbtreekey32" AS '$libdir/btree_gist', 'gbt_intv_union'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_macad8_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_macad8_compress"(internal);
CREATE FUNCTION "public"."gbt_macad8_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_macad8_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_macad8_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_macad8_consistent"(internal, macaddr8, int2, oid, internal);
CREATE FUNCTION "public"."gbt_macad8_consistent"(internal, macaddr8, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_macad8_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_macad8_fetch
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_macad8_fetch"(internal);
CREATE FUNCTION "public"."gbt_macad8_fetch"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_macad8_fetch'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_macad8_penalty
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_macad8_penalty"(internal, internal, internal);
CREATE FUNCTION "public"."gbt_macad8_penalty"(internal, internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_macad8_penalty'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_macad8_picksplit
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_macad8_picksplit"(internal, internal);
CREATE FUNCTION "public"."gbt_macad8_picksplit"(internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_macad8_picksplit'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_macad8_same
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_macad8_same"("public"."gbtreekey16", "public"."gbtreekey16", internal);
CREATE FUNCTION "public"."gbt_macad8_same"("public"."gbtreekey16", "public"."gbtreekey16", internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_macad8_same'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_macad8_union
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_macad8_union"(internal, internal);
CREATE FUNCTION "public"."gbt_macad8_union"(internal, internal)
  RETURNS "public"."gbtreekey16" AS '$libdir/btree_gist', 'gbt_macad8_union'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_macad_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_macad_compress"(internal);
CREATE FUNCTION "public"."gbt_macad_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_macad_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_macad_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_macad_consistent"(internal, macaddr, int2, oid, internal);
CREATE FUNCTION "public"."gbt_macad_consistent"(internal, macaddr, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_macad_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_macad_fetch
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_macad_fetch"(internal);
CREATE FUNCTION "public"."gbt_macad_fetch"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_macad_fetch'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_macad_penalty
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_macad_penalty"(internal, internal, internal);
CREATE FUNCTION "public"."gbt_macad_penalty"(internal, internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_macad_penalty'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_macad_picksplit
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_macad_picksplit"(internal, internal);
CREATE FUNCTION "public"."gbt_macad_picksplit"(internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_macad_picksplit'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_macad_same
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_macad_same"("public"."gbtreekey16", "public"."gbtreekey16", internal);
CREATE FUNCTION "public"."gbt_macad_same"("public"."gbtreekey16", "public"."gbtreekey16", internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_macad_same'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_macad_union
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_macad_union"(internal, internal);
CREATE FUNCTION "public"."gbt_macad_union"(internal, internal)
  RETURNS "public"."gbtreekey16" AS '$libdir/btree_gist', 'gbt_macad_union'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_numeric_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_numeric_compress"(internal);
CREATE FUNCTION "public"."gbt_numeric_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_numeric_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_numeric_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_numeric_consistent"(internal, numeric, int2, oid, internal);
CREATE FUNCTION "public"."gbt_numeric_consistent"(internal, numeric, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_numeric_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_numeric_penalty
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_numeric_penalty"(internal, internal, internal);
CREATE FUNCTION "public"."gbt_numeric_penalty"(internal, internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_numeric_penalty'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_numeric_picksplit
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_numeric_picksplit"(internal, internal);
CREATE FUNCTION "public"."gbt_numeric_picksplit"(internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_numeric_picksplit'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_numeric_same
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_numeric_same"("public"."gbtreekey_var", "public"."gbtreekey_var", internal);
CREATE FUNCTION "public"."gbt_numeric_same"("public"."gbtreekey_var", "public"."gbtreekey_var", internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_numeric_same'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_numeric_union
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_numeric_union"(internal, internal);
CREATE FUNCTION "public"."gbt_numeric_union"(internal, internal)
  RETURNS "public"."gbtreekey_var" AS '$libdir/btree_gist', 'gbt_numeric_union'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_oid_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_oid_compress"(internal);
CREATE FUNCTION "public"."gbt_oid_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_oid_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_oid_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_oid_consistent"(internal, oid, int2, oid, internal);
CREATE FUNCTION "public"."gbt_oid_consistent"(internal, oid, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_oid_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_oid_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_oid_distance"(internal, oid, int2, oid, internal);
CREATE FUNCTION "public"."gbt_oid_distance"(internal, oid, int2, oid, internal)
  RETURNS "pg_catalog"."float8" AS '$libdir/btree_gist', 'gbt_oid_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_oid_fetch
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_oid_fetch"(internal);
CREATE FUNCTION "public"."gbt_oid_fetch"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_oid_fetch'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_oid_penalty
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_oid_penalty"(internal, internal, internal);
CREATE FUNCTION "public"."gbt_oid_penalty"(internal, internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_oid_penalty'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_oid_picksplit
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_oid_picksplit"(internal, internal);
CREATE FUNCTION "public"."gbt_oid_picksplit"(internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_oid_picksplit'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_oid_same
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_oid_same"("public"."gbtreekey8", "public"."gbtreekey8", internal);
CREATE FUNCTION "public"."gbt_oid_same"("public"."gbtreekey8", "public"."gbtreekey8", internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_oid_same'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_oid_union
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_oid_union"(internal, internal);
CREATE FUNCTION "public"."gbt_oid_union"(internal, internal)
  RETURNS "public"."gbtreekey8" AS '$libdir/btree_gist', 'gbt_oid_union'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_text_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_text_compress"(internal);
CREATE FUNCTION "public"."gbt_text_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_text_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_text_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_text_consistent"(internal, text, int2, oid, internal);
CREATE FUNCTION "public"."gbt_text_consistent"(internal, text, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_text_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_text_penalty
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_text_penalty"(internal, internal, internal);
CREATE FUNCTION "public"."gbt_text_penalty"(internal, internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_text_penalty'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_text_picksplit
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_text_picksplit"(internal, internal);
CREATE FUNCTION "public"."gbt_text_picksplit"(internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_text_picksplit'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_text_same
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_text_same"("public"."gbtreekey_var", "public"."gbtreekey_var", internal);
CREATE FUNCTION "public"."gbt_text_same"("public"."gbtreekey_var", "public"."gbtreekey_var", internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_text_same'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_text_union
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_text_union"(internal, internal);
CREATE FUNCTION "public"."gbt_text_union"(internal, internal)
  RETURNS "public"."gbtreekey_var" AS '$libdir/btree_gist', 'gbt_text_union'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_time_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_time_compress"(internal);
CREATE FUNCTION "public"."gbt_time_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_time_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_time_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_time_consistent"(internal, time, int2, oid, internal);
CREATE FUNCTION "public"."gbt_time_consistent"(internal, time, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_time_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_time_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_time_distance"(internal, time, int2, oid, internal);
CREATE FUNCTION "public"."gbt_time_distance"(internal, time, int2, oid, internal)
  RETURNS "pg_catalog"."float8" AS '$libdir/btree_gist', 'gbt_time_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_time_fetch
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_time_fetch"(internal);
CREATE FUNCTION "public"."gbt_time_fetch"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_time_fetch'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_time_penalty
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_time_penalty"(internal, internal, internal);
CREATE FUNCTION "public"."gbt_time_penalty"(internal, internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_time_penalty'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_time_picksplit
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_time_picksplit"(internal, internal);
CREATE FUNCTION "public"."gbt_time_picksplit"(internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_time_picksplit'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_time_same
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_time_same"("public"."gbtreekey16", "public"."gbtreekey16", internal);
CREATE FUNCTION "public"."gbt_time_same"("public"."gbtreekey16", "public"."gbtreekey16", internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_time_same'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_time_union
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_time_union"(internal, internal);
CREATE FUNCTION "public"."gbt_time_union"(internal, internal)
  RETURNS "public"."gbtreekey16" AS '$libdir/btree_gist', 'gbt_time_union'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_timetz_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_timetz_compress"(internal);
CREATE FUNCTION "public"."gbt_timetz_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_timetz_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_timetz_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_timetz_consistent"(internal, timetz, int2, oid, internal);
CREATE FUNCTION "public"."gbt_timetz_consistent"(internal, timetz, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_timetz_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_ts_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_ts_compress"(internal);
CREATE FUNCTION "public"."gbt_ts_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_ts_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_ts_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_ts_consistent"(internal, timestamp, int2, oid, internal);
CREATE FUNCTION "public"."gbt_ts_consistent"(internal, timestamp, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_ts_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_ts_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_ts_distance"(internal, timestamp, int2, oid, internal);
CREATE FUNCTION "public"."gbt_ts_distance"(internal, timestamp, int2, oid, internal)
  RETURNS "pg_catalog"."float8" AS '$libdir/btree_gist', 'gbt_ts_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_ts_fetch
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_ts_fetch"(internal);
CREATE FUNCTION "public"."gbt_ts_fetch"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_ts_fetch'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_ts_penalty
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_ts_penalty"(internal, internal, internal);
CREATE FUNCTION "public"."gbt_ts_penalty"(internal, internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_ts_penalty'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_ts_picksplit
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_ts_picksplit"(internal, internal);
CREATE FUNCTION "public"."gbt_ts_picksplit"(internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_ts_picksplit'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_ts_same
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_ts_same"("public"."gbtreekey16", "public"."gbtreekey16", internal);
CREATE FUNCTION "public"."gbt_ts_same"("public"."gbtreekey16", "public"."gbtreekey16", internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_ts_same'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_ts_union
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_ts_union"(internal, internal);
CREATE FUNCTION "public"."gbt_ts_union"(internal, internal)
  RETURNS "public"."gbtreekey16" AS '$libdir/btree_gist', 'gbt_ts_union'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_tstz_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_tstz_compress"(internal);
CREATE FUNCTION "public"."gbt_tstz_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_tstz_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_tstz_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_tstz_consistent"(internal, timestamptz, int2, oid, internal);
CREATE FUNCTION "public"."gbt_tstz_consistent"(internal, timestamptz, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_tstz_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_tstz_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_tstz_distance"(internal, timestamptz, int2, oid, internal);
CREATE FUNCTION "public"."gbt_tstz_distance"(internal, timestamptz, int2, oid, internal)
  RETURNS "pg_catalog"."float8" AS '$libdir/btree_gist', 'gbt_tstz_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_uuid_compress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_uuid_compress"(internal);
CREATE FUNCTION "public"."gbt_uuid_compress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_uuid_compress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_uuid_consistent
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_uuid_consistent"(internal, uuid, int2, oid, internal);
CREATE FUNCTION "public"."gbt_uuid_consistent"(internal, uuid, int2, oid, internal)
  RETURNS "pg_catalog"."bool" AS '$libdir/btree_gist', 'gbt_uuid_consistent'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_uuid_fetch
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_uuid_fetch"(internal);
CREATE FUNCTION "public"."gbt_uuid_fetch"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_uuid_fetch'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_uuid_penalty
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_uuid_penalty"(internal, internal, internal);
CREATE FUNCTION "public"."gbt_uuid_penalty"(internal, internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_uuid_penalty'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_uuid_picksplit
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_uuid_picksplit"(internal, internal);
CREATE FUNCTION "public"."gbt_uuid_picksplit"(internal, internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_uuid_picksplit'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_uuid_same
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_uuid_same"("public"."gbtreekey32", "public"."gbtreekey32", internal);
CREATE FUNCTION "public"."gbt_uuid_same"("public"."gbtreekey32", "public"."gbtreekey32", internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_uuid_same'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_uuid_union
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_uuid_union"(internal, internal);
CREATE FUNCTION "public"."gbt_uuid_union"(internal, internal)
  RETURNS "public"."gbtreekey32" AS '$libdir/btree_gist', 'gbt_uuid_union'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_var_decompress
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_var_decompress"(internal);
CREATE FUNCTION "public"."gbt_var_decompress"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_var_decompress'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbt_var_fetch
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbt_var_fetch"(internal);
CREATE FUNCTION "public"."gbt_var_fetch"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/btree_gist', 'gbt_var_fetch'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbtreekey16_in
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbtreekey16_in"(cstring);
CREATE FUNCTION "public"."gbtreekey16_in"(cstring)
  RETURNS "public"."gbtreekey16" AS '$libdir/btree_gist', 'gbtreekey_in'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbtreekey16_out
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbtreekey16_out"("public"."gbtreekey16");
CREATE FUNCTION "public"."gbtreekey16_out"("public"."gbtreekey16")
  RETURNS "pg_catalog"."cstring" AS '$libdir/btree_gist', 'gbtreekey_out'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbtreekey2_in
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbtreekey2_in"(cstring);
CREATE FUNCTION "public"."gbtreekey2_in"(cstring)
  RETURNS "public"."gbtreekey2" AS '$libdir/btree_gist', 'gbtreekey_in'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbtreekey2_out
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbtreekey2_out"("public"."gbtreekey2");
CREATE FUNCTION "public"."gbtreekey2_out"("public"."gbtreekey2")
  RETURNS "pg_catalog"."cstring" AS '$libdir/btree_gist', 'gbtreekey_out'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbtreekey32_in
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbtreekey32_in"(cstring);
CREATE FUNCTION "public"."gbtreekey32_in"(cstring)
  RETURNS "public"."gbtreekey32" AS '$libdir/btree_gist', 'gbtreekey_in'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbtreekey32_out
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbtreekey32_out"("public"."gbtreekey32");
CREATE FUNCTION "public"."gbtreekey32_out"("public"."gbtreekey32")
  RETURNS "pg_catalog"."cstring" AS '$libdir/btree_gist', 'gbtreekey_out'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbtreekey4_in
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbtreekey4_in"(cstring);
CREATE FUNCTION "public"."gbtreekey4_in"(cstring)
  RETURNS "public"."gbtreekey4" AS '$libdir/btree_gist', 'gbtreekey_in'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbtreekey4_out
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbtreekey4_out"("public"."gbtreekey4");
CREATE FUNCTION "public"."gbtreekey4_out"("public"."gbtreekey4")
  RETURNS "pg_catalog"."cstring" AS '$libdir/btree_gist', 'gbtreekey_out'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbtreekey8_in
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbtreekey8_in"(cstring);
CREATE FUNCTION "public"."gbtreekey8_in"(cstring)
  RETURNS "public"."gbtreekey8" AS '$libdir/btree_gist', 'gbtreekey_in'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbtreekey8_out
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbtreekey8_out"("public"."gbtreekey8");
CREATE FUNCTION "public"."gbtreekey8_out"("public"."gbtreekey8")
  RETURNS "pg_catalog"."cstring" AS '$libdir/btree_gist', 'gbtreekey_out'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbtreekey_var_in
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbtreekey_var_in"(cstring);
CREATE FUNCTION "public"."gbtreekey_var_in"(cstring)
  RETURNS "public"."gbtreekey_var" AS '$libdir/btree_gist', 'gbtreekey_in'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gbtreekey_var_out
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gbtreekey_var_out"("public"."gbtreekey_var");
CREATE FUNCTION "public"."gbtreekey_var_out"("public"."gbtreekey_var")
  RETURNS "pg_catalog"."cstring" AS '$libdir/btree_gist', 'gbtreekey_out'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gen_random_bytes
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gen_random_bytes"(int4);
CREATE FUNCTION "public"."gen_random_bytes"(int4)
  RETURNS "pg_catalog"."bytea" AS '$libdir/pgcrypto', 'pg_random_bytes'
  LANGUAGE c VOLATILE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gen_random_uuid
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gen_random_uuid"();
CREATE FUNCTION "public"."gen_random_uuid"()
  RETURNS "pg_catalog"."uuid" AS '$libdir/pgcrypto', 'pg_random_uuid'
  LANGUAGE c VOLATILE
  COST 1;

-- ----------------------------
-- Function structure for gen_salt
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gen_salt"(text, int4);
CREATE FUNCTION "public"."gen_salt"(text, int4)
  RETURNS "pg_catalog"."text" AS '$libdir/pgcrypto', 'pg_gen_salt_rounds'
  LANGUAGE c VOLATILE STRICT
  COST 1;

-- ----------------------------
-- Function structure for gen_salt
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."gen_salt"(text);
CREATE FUNCTION "public"."gen_salt"(text)
  RETURNS "pg_catalog"."text" AS '$libdir/pgcrypto', 'pg_gen_salt'
  LANGUAGE c VOLATILE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec"("public"."halfvec", int4, bool);
CREATE FUNCTION "public"."halfvec"("public"."halfvec", int4, bool)
  RETURNS "public"."halfvec" AS '$libdir/vector', 'halfvec'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_accum
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_accum"(_float8, "public"."halfvec");
CREATE FUNCTION "public"."halfvec_accum"(_float8, "public"."halfvec")
  RETURNS "pg_catalog"."_float8" AS '$libdir/vector', 'halfvec_accum'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_add
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_add"("public"."halfvec", "public"."halfvec");
CREATE FUNCTION "public"."halfvec_add"("public"."halfvec", "public"."halfvec")
  RETURNS "public"."halfvec" AS '$libdir/vector', 'halfvec_add'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_avg
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_avg"(_float8);
CREATE FUNCTION "public"."halfvec_avg"(_float8)
  RETURNS "public"."halfvec" AS '$libdir/vector', 'halfvec_avg'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_cmp
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_cmp"("public"."halfvec", "public"."halfvec");
CREATE FUNCTION "public"."halfvec_cmp"("public"."halfvec", "public"."halfvec")
  RETURNS "pg_catalog"."int4" AS '$libdir/vector', 'halfvec_cmp'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_combine
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_combine"(_float8, _float8);
CREATE FUNCTION "public"."halfvec_combine"(_float8, _float8)
  RETURNS "pg_catalog"."_float8" AS '$libdir/vector', 'vector_combine'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_concat
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_concat"("public"."halfvec", "public"."halfvec");
CREATE FUNCTION "public"."halfvec_concat"("public"."halfvec", "public"."halfvec")
  RETURNS "public"."halfvec" AS '$libdir/vector', 'halfvec_concat'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_eq
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_eq"("public"."halfvec", "public"."halfvec");
CREATE FUNCTION "public"."halfvec_eq"("public"."halfvec", "public"."halfvec")
  RETURNS "pg_catalog"."bool" AS '$libdir/vector', 'halfvec_eq'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_ge
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_ge"("public"."halfvec", "public"."halfvec");
CREATE FUNCTION "public"."halfvec_ge"("public"."halfvec", "public"."halfvec")
  RETURNS "pg_catalog"."bool" AS '$libdir/vector', 'halfvec_ge'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_gt
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_gt"("public"."halfvec", "public"."halfvec");
CREATE FUNCTION "public"."halfvec_gt"("public"."halfvec", "public"."halfvec")
  RETURNS "pg_catalog"."bool" AS '$libdir/vector', 'halfvec_gt'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_in
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_in"(cstring, oid, int4);
CREATE FUNCTION "public"."halfvec_in"(cstring, oid, int4)
  RETURNS "public"."halfvec" AS '$libdir/vector', 'halfvec_in'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_l2_squared_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_l2_squared_distance"("public"."halfvec", "public"."halfvec");
CREATE FUNCTION "public"."halfvec_l2_squared_distance"("public"."halfvec", "public"."halfvec")
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'halfvec_l2_squared_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_le
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_le"("public"."halfvec", "public"."halfvec");
CREATE FUNCTION "public"."halfvec_le"("public"."halfvec", "public"."halfvec")
  RETURNS "pg_catalog"."bool" AS '$libdir/vector', 'halfvec_le'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_lt
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_lt"("public"."halfvec", "public"."halfvec");
CREATE FUNCTION "public"."halfvec_lt"("public"."halfvec", "public"."halfvec")
  RETURNS "pg_catalog"."bool" AS '$libdir/vector', 'halfvec_lt'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_mul
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_mul"("public"."halfvec", "public"."halfvec");
CREATE FUNCTION "public"."halfvec_mul"("public"."halfvec", "public"."halfvec")
  RETURNS "public"."halfvec" AS '$libdir/vector', 'halfvec_mul'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_ne
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_ne"("public"."halfvec", "public"."halfvec");
CREATE FUNCTION "public"."halfvec_ne"("public"."halfvec", "public"."halfvec")
  RETURNS "pg_catalog"."bool" AS '$libdir/vector', 'halfvec_ne'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_negative_inner_product
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_negative_inner_product"("public"."halfvec", "public"."halfvec");
CREATE FUNCTION "public"."halfvec_negative_inner_product"("public"."halfvec", "public"."halfvec")
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'halfvec_negative_inner_product'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_out
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_out"("public"."halfvec");
CREATE FUNCTION "public"."halfvec_out"("public"."halfvec")
  RETURNS "pg_catalog"."cstring" AS '$libdir/vector', 'halfvec_out'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_recv
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_recv"(internal, oid, int4);
CREATE FUNCTION "public"."halfvec_recv"(internal, oid, int4)
  RETURNS "public"."halfvec" AS '$libdir/vector', 'halfvec_recv'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_send
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_send"("public"."halfvec");
CREATE FUNCTION "public"."halfvec_send"("public"."halfvec")
  RETURNS "pg_catalog"."bytea" AS '$libdir/vector', 'halfvec_send'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_spherical_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_spherical_distance"("public"."halfvec", "public"."halfvec");
CREATE FUNCTION "public"."halfvec_spherical_distance"("public"."halfvec", "public"."halfvec")
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'halfvec_spherical_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_sub
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_sub"("public"."halfvec", "public"."halfvec");
CREATE FUNCTION "public"."halfvec_sub"("public"."halfvec", "public"."halfvec")
  RETURNS "public"."halfvec" AS '$libdir/vector', 'halfvec_sub'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_to_float4
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_to_float4"("public"."halfvec", int4, bool);
CREATE FUNCTION "public"."halfvec_to_float4"("public"."halfvec", int4, bool)
  RETURNS "pg_catalog"."_float4" AS '$libdir/vector', 'halfvec_to_float4'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_to_sparsevec
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_to_sparsevec"("public"."halfvec", int4, bool);
CREATE FUNCTION "public"."halfvec_to_sparsevec"("public"."halfvec", int4, bool)
  RETURNS "public"."sparsevec" AS '$libdir/vector', 'halfvec_to_sparsevec'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_to_vector
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_to_vector"("public"."halfvec", int4, bool);
CREATE FUNCTION "public"."halfvec_to_vector"("public"."halfvec", int4, bool)
  RETURNS "public"."vector" AS '$libdir/vector', 'halfvec_to_vector'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for halfvec_typmod_in
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."halfvec_typmod_in"(_cstring);
CREATE FUNCTION "public"."halfvec_typmod_in"(_cstring)
  RETURNS "pg_catalog"."int4" AS '$libdir/vector', 'halfvec_typmod_in'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for hamming_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."hamming_distance"(bit, bit);
CREATE FUNCTION "public"."hamming_distance"(bit, bit)
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'hamming_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for hmac
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."hmac"(bytea, bytea, text);
CREATE FUNCTION "public"."hmac"(bytea, bytea, text)
  RETURNS "pg_catalog"."bytea" AS '$libdir/pgcrypto', 'pg_hmac'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for hmac
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."hmac"(text, text, text);
CREATE FUNCTION "public"."hmac"(text, text, text)
  RETURNS "pg_catalog"."bytea" AS '$libdir/pgcrypto', 'pg_hmac'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for hnsw_bit_support
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."hnsw_bit_support"(internal);
CREATE FUNCTION "public"."hnsw_bit_support"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/vector', 'hnsw_bit_support'
  LANGUAGE c VOLATILE
  COST 1;

-- ----------------------------
-- Function structure for hnsw_halfvec_support
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."hnsw_halfvec_support"(internal);
CREATE FUNCTION "public"."hnsw_halfvec_support"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/vector', 'hnsw_halfvec_support'
  LANGUAGE c VOLATILE
  COST 1;

-- ----------------------------
-- Function structure for hnsw_sparsevec_support
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."hnsw_sparsevec_support"(internal);
CREATE FUNCTION "public"."hnsw_sparsevec_support"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/vector', 'hnsw_sparsevec_support'
  LANGUAGE c VOLATILE
  COST 1;

-- ----------------------------
-- Function structure for hnswhandler
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."hnswhandler"(internal);
CREATE FUNCTION "public"."hnswhandler"(internal)
  RETURNS "pg_catalog"."index_am_handler" AS '$libdir/vector', 'hnswhandler'
  LANGUAGE c VOLATILE
  COST 1;

-- ----------------------------
-- Function structure for inner_product
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."inner_product"("public"."halfvec", "public"."halfvec");
CREATE FUNCTION "public"."inner_product"("public"."halfvec", "public"."halfvec")
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'halfvec_inner_product'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for inner_product
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."inner_product"("public"."sparsevec", "public"."sparsevec");
CREATE FUNCTION "public"."inner_product"("public"."sparsevec", "public"."sparsevec")
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'sparsevec_inner_product'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for inner_product
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."inner_product"("public"."vector", "public"."vector");
CREATE FUNCTION "public"."inner_product"("public"."vector", "public"."vector")
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'inner_product'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for int2_dist
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."int2_dist"(int2, int2);
CREATE FUNCTION "public"."int2_dist"(int2, int2)
  RETURNS "pg_catalog"."int2" AS '$libdir/btree_gist', 'int2_dist'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for int4_dist
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."int4_dist"(int4, int4);
CREATE FUNCTION "public"."int4_dist"(int4, int4)
  RETURNS "pg_catalog"."int4" AS '$libdir/btree_gist', 'int4_dist'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for int8_dist
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."int8_dist"(int8, int8);
CREATE FUNCTION "public"."int8_dist"(int8, int8)
  RETURNS "pg_catalog"."int8" AS '$libdir/btree_gist', 'int8_dist'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for interval_dist
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."interval_dist"(interval, interval);
CREATE FUNCTION "public"."interval_dist"(interval, interval)
  RETURNS "pg_catalog"."interval" AS '$libdir/btree_gist', 'interval_dist'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for ivfflat_bit_support
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."ivfflat_bit_support"(internal);
CREATE FUNCTION "public"."ivfflat_bit_support"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/vector', 'ivfflat_bit_support'
  LANGUAGE c VOLATILE
  COST 1;

-- ----------------------------
-- Function structure for ivfflat_halfvec_support
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."ivfflat_halfvec_support"(internal);
CREATE FUNCTION "public"."ivfflat_halfvec_support"(internal)
  RETURNS "pg_catalog"."internal" AS '$libdir/vector', 'ivfflat_halfvec_support'
  LANGUAGE c VOLATILE
  COST 1;

-- ----------------------------
-- Function structure for ivfflathandler
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."ivfflathandler"(internal);
CREATE FUNCTION "public"."ivfflathandler"(internal)
  RETURNS "pg_catalog"."index_am_handler" AS '$libdir/vector', 'ivfflathandler'
  LANGUAGE c VOLATILE
  COST 1;

-- ----------------------------
-- Function structure for jaccard_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."jaccard_distance"(bit, bit);
CREATE FUNCTION "public"."jaccard_distance"(bit, bit)
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'jaccard_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for l1_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."l1_distance"("public"."sparsevec", "public"."sparsevec");
CREATE FUNCTION "public"."l1_distance"("public"."sparsevec", "public"."sparsevec")
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'sparsevec_l1_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for l1_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."l1_distance"("public"."vector", "public"."vector");
CREATE FUNCTION "public"."l1_distance"("public"."vector", "public"."vector")
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'l1_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for l1_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."l1_distance"("public"."halfvec", "public"."halfvec");
CREATE FUNCTION "public"."l1_distance"("public"."halfvec", "public"."halfvec")
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'halfvec_l1_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for l2_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."l2_distance"("public"."halfvec", "public"."halfvec");
CREATE FUNCTION "public"."l2_distance"("public"."halfvec", "public"."halfvec")
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'halfvec_l2_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for l2_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."l2_distance"("public"."vector", "public"."vector");
CREATE FUNCTION "public"."l2_distance"("public"."vector", "public"."vector")
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'l2_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for l2_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."l2_distance"("public"."sparsevec", "public"."sparsevec");
CREATE FUNCTION "public"."l2_distance"("public"."sparsevec", "public"."sparsevec")
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'sparsevec_l2_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for l2_norm
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."l2_norm"("public"."sparsevec");
CREATE FUNCTION "public"."l2_norm"("public"."sparsevec")
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'sparsevec_l2_norm'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for l2_norm
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."l2_norm"("public"."halfvec");
CREATE FUNCTION "public"."l2_norm"("public"."halfvec")
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'halfvec_l2_norm'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for l2_normalize
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."l2_normalize"("public"."halfvec");
CREATE FUNCTION "public"."l2_normalize"("public"."halfvec")
  RETURNS "public"."halfvec" AS '$libdir/vector', 'halfvec_l2_normalize'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for l2_normalize
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."l2_normalize"("public"."sparsevec");
CREATE FUNCTION "public"."l2_normalize"("public"."sparsevec")
  RETURNS "public"."sparsevec" AS '$libdir/vector', 'sparsevec_l2_normalize'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for l2_normalize
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."l2_normalize"("public"."vector");
CREATE FUNCTION "public"."l2_normalize"("public"."vector")
  RETURNS "public"."vector" AS '$libdir/vector', 'l2_normalize'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for oid_dist
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."oid_dist"(oid, oid);
CREATE FUNCTION "public"."oid_dist"(oid, oid)
  RETURNS "pg_catalog"."oid" AS '$libdir/btree_gist', 'oid_dist'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for pgp_armor_headers
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."pgp_armor_headers"(text, OUT "key" text, OUT "value" text);
CREATE FUNCTION "public"."pgp_armor_headers"(IN text, OUT "key" text, OUT "value" text)
  RETURNS SETOF "pg_catalog"."record" AS '$libdir/pgcrypto', 'pgp_armor_headers'
  LANGUAGE c IMMUTABLE STRICT
  COST 1
  ROWS 1000;

-- ----------------------------
-- Function structure for pgp_key_id
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."pgp_key_id"(bytea);
CREATE FUNCTION "public"."pgp_key_id"(bytea)
  RETURNS "pg_catalog"."text" AS '$libdir/pgcrypto', 'pgp_key_id_w'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for pgp_pub_decrypt
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."pgp_pub_decrypt"(bytea, bytea, text);
CREATE FUNCTION "public"."pgp_pub_decrypt"(bytea, bytea, text)
  RETURNS "pg_catalog"."text" AS '$libdir/pgcrypto', 'pgp_pub_decrypt_text'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for pgp_pub_decrypt
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."pgp_pub_decrypt"(bytea, bytea, text, text);
CREATE FUNCTION "public"."pgp_pub_decrypt"(bytea, bytea, text, text)
  RETURNS "pg_catalog"."text" AS '$libdir/pgcrypto', 'pgp_pub_decrypt_text'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for pgp_pub_decrypt
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."pgp_pub_decrypt"(bytea, bytea);
CREATE FUNCTION "public"."pgp_pub_decrypt"(bytea, bytea)
  RETURNS "pg_catalog"."text" AS '$libdir/pgcrypto', 'pgp_pub_decrypt_text'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for pgp_pub_decrypt_bytea
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."pgp_pub_decrypt_bytea"(bytea, bytea, text);
CREATE FUNCTION "public"."pgp_pub_decrypt_bytea"(bytea, bytea, text)
  RETURNS "pg_catalog"."bytea" AS '$libdir/pgcrypto', 'pgp_pub_decrypt_bytea'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for pgp_pub_decrypt_bytea
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."pgp_pub_decrypt_bytea"(bytea, bytea);
CREATE FUNCTION "public"."pgp_pub_decrypt_bytea"(bytea, bytea)
  RETURNS "pg_catalog"."bytea" AS '$libdir/pgcrypto', 'pgp_pub_decrypt_bytea'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for pgp_pub_decrypt_bytea
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."pgp_pub_decrypt_bytea"(bytea, bytea, text, text);
CREATE FUNCTION "public"."pgp_pub_decrypt_bytea"(bytea, bytea, text, text)
  RETURNS "pg_catalog"."bytea" AS '$libdir/pgcrypto', 'pgp_pub_decrypt_bytea'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for pgp_pub_encrypt
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."pgp_pub_encrypt"(text, bytea);
CREATE FUNCTION "public"."pgp_pub_encrypt"(text, bytea)
  RETURNS "pg_catalog"."bytea" AS '$libdir/pgcrypto', 'pgp_pub_encrypt_text'
  LANGUAGE c VOLATILE STRICT
  COST 1;

-- ----------------------------
-- Function structure for pgp_pub_encrypt
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."pgp_pub_encrypt"(text, bytea, text);
CREATE FUNCTION "public"."pgp_pub_encrypt"(text, bytea, text)
  RETURNS "pg_catalog"."bytea" AS '$libdir/pgcrypto', 'pgp_pub_encrypt_text'
  LANGUAGE c VOLATILE STRICT
  COST 1;

-- ----------------------------
-- Function structure for pgp_pub_encrypt_bytea
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."pgp_pub_encrypt_bytea"(bytea, bytea, text);
CREATE FUNCTION "public"."pgp_pub_encrypt_bytea"(bytea, bytea, text)
  RETURNS "pg_catalog"."bytea" AS '$libdir/pgcrypto', 'pgp_pub_encrypt_bytea'
  LANGUAGE c VOLATILE STRICT
  COST 1;

-- ----------------------------
-- Function structure for pgp_pub_encrypt_bytea
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."pgp_pub_encrypt_bytea"(bytea, bytea);
CREATE FUNCTION "public"."pgp_pub_encrypt_bytea"(bytea, bytea)
  RETURNS "pg_catalog"."bytea" AS '$libdir/pgcrypto', 'pgp_pub_encrypt_bytea'
  LANGUAGE c VOLATILE STRICT
  COST 1;

-- ----------------------------
-- Function structure for pgp_sym_decrypt
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."pgp_sym_decrypt"(bytea, text);
CREATE FUNCTION "public"."pgp_sym_decrypt"(bytea, text)
  RETURNS "pg_catalog"."text" AS '$libdir/pgcrypto', 'pgp_sym_decrypt_text'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for pgp_sym_decrypt
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."pgp_sym_decrypt"(bytea, text, text);
CREATE FUNCTION "public"."pgp_sym_decrypt"(bytea, text, text)
  RETURNS "pg_catalog"."text" AS '$libdir/pgcrypto', 'pgp_sym_decrypt_text'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for pgp_sym_decrypt_bytea
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."pgp_sym_decrypt_bytea"(bytea, text, text);
CREATE FUNCTION "public"."pgp_sym_decrypt_bytea"(bytea, text, text)
  RETURNS "pg_catalog"."bytea" AS '$libdir/pgcrypto', 'pgp_sym_decrypt_bytea'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for pgp_sym_decrypt_bytea
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."pgp_sym_decrypt_bytea"(bytea, text);
CREATE FUNCTION "public"."pgp_sym_decrypt_bytea"(bytea, text)
  RETURNS "pg_catalog"."bytea" AS '$libdir/pgcrypto', 'pgp_sym_decrypt_bytea'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for pgp_sym_encrypt
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."pgp_sym_encrypt"(text, text);
CREATE FUNCTION "public"."pgp_sym_encrypt"(text, text)
  RETURNS "pg_catalog"."bytea" AS '$libdir/pgcrypto', 'pgp_sym_encrypt_text'
  LANGUAGE c VOLATILE STRICT
  COST 1;

-- ----------------------------
-- Function structure for pgp_sym_encrypt
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."pgp_sym_encrypt"(text, text, text);
CREATE FUNCTION "public"."pgp_sym_encrypt"(text, text, text)
  RETURNS "pg_catalog"."bytea" AS '$libdir/pgcrypto', 'pgp_sym_encrypt_text'
  LANGUAGE c VOLATILE STRICT
  COST 1;

-- ----------------------------
-- Function structure for pgp_sym_encrypt_bytea
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."pgp_sym_encrypt_bytea"(bytea, text, text);
CREATE FUNCTION "public"."pgp_sym_encrypt_bytea"(bytea, text, text)
  RETURNS "pg_catalog"."bytea" AS '$libdir/pgcrypto', 'pgp_sym_encrypt_bytea'
  LANGUAGE c VOLATILE STRICT
  COST 1;

-- ----------------------------
-- Function structure for pgp_sym_encrypt_bytea
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."pgp_sym_encrypt_bytea"(bytea, text);
CREATE FUNCTION "public"."pgp_sym_encrypt_bytea"(bytea, text)
  RETURNS "pg_catalog"."bytea" AS '$libdir/pgcrypto', 'pgp_sym_encrypt_bytea'
  LANGUAGE c VOLATILE STRICT
  COST 1;

-- ----------------------------
-- Function structure for sparsevec
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."sparsevec"("public"."sparsevec", int4, bool);
CREATE FUNCTION "public"."sparsevec"("public"."sparsevec", int4, bool)
  RETURNS "public"."sparsevec" AS '$libdir/vector', 'sparsevec'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for sparsevec_cmp
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."sparsevec_cmp"("public"."sparsevec", "public"."sparsevec");
CREATE FUNCTION "public"."sparsevec_cmp"("public"."sparsevec", "public"."sparsevec")
  RETURNS "pg_catalog"."int4" AS '$libdir/vector', 'sparsevec_cmp'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for sparsevec_eq
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."sparsevec_eq"("public"."sparsevec", "public"."sparsevec");
CREATE FUNCTION "public"."sparsevec_eq"("public"."sparsevec", "public"."sparsevec")
  RETURNS "pg_catalog"."bool" AS '$libdir/vector', 'sparsevec_eq'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for sparsevec_ge
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."sparsevec_ge"("public"."sparsevec", "public"."sparsevec");
CREATE FUNCTION "public"."sparsevec_ge"("public"."sparsevec", "public"."sparsevec")
  RETURNS "pg_catalog"."bool" AS '$libdir/vector', 'sparsevec_ge'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for sparsevec_gt
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."sparsevec_gt"("public"."sparsevec", "public"."sparsevec");
CREATE FUNCTION "public"."sparsevec_gt"("public"."sparsevec", "public"."sparsevec")
  RETURNS "pg_catalog"."bool" AS '$libdir/vector', 'sparsevec_gt'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for sparsevec_in
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."sparsevec_in"(cstring, oid, int4);
CREATE FUNCTION "public"."sparsevec_in"(cstring, oid, int4)
  RETURNS "public"."sparsevec" AS '$libdir/vector', 'sparsevec_in'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for sparsevec_l2_squared_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."sparsevec_l2_squared_distance"("public"."sparsevec", "public"."sparsevec");
CREATE FUNCTION "public"."sparsevec_l2_squared_distance"("public"."sparsevec", "public"."sparsevec")
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'sparsevec_l2_squared_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for sparsevec_le
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."sparsevec_le"("public"."sparsevec", "public"."sparsevec");
CREATE FUNCTION "public"."sparsevec_le"("public"."sparsevec", "public"."sparsevec")
  RETURNS "pg_catalog"."bool" AS '$libdir/vector', 'sparsevec_le'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for sparsevec_lt
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."sparsevec_lt"("public"."sparsevec", "public"."sparsevec");
CREATE FUNCTION "public"."sparsevec_lt"("public"."sparsevec", "public"."sparsevec")
  RETURNS "pg_catalog"."bool" AS '$libdir/vector', 'sparsevec_lt'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for sparsevec_ne
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."sparsevec_ne"("public"."sparsevec", "public"."sparsevec");
CREATE FUNCTION "public"."sparsevec_ne"("public"."sparsevec", "public"."sparsevec")
  RETURNS "pg_catalog"."bool" AS '$libdir/vector', 'sparsevec_ne'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for sparsevec_negative_inner_product
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."sparsevec_negative_inner_product"("public"."sparsevec", "public"."sparsevec");
CREATE FUNCTION "public"."sparsevec_negative_inner_product"("public"."sparsevec", "public"."sparsevec")
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'sparsevec_negative_inner_product'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for sparsevec_out
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."sparsevec_out"("public"."sparsevec");
CREATE FUNCTION "public"."sparsevec_out"("public"."sparsevec")
  RETURNS "pg_catalog"."cstring" AS '$libdir/vector', 'sparsevec_out'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for sparsevec_recv
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."sparsevec_recv"(internal, oid, int4);
CREATE FUNCTION "public"."sparsevec_recv"(internal, oid, int4)
  RETURNS "public"."sparsevec" AS '$libdir/vector', 'sparsevec_recv'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for sparsevec_send
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."sparsevec_send"("public"."sparsevec");
CREATE FUNCTION "public"."sparsevec_send"("public"."sparsevec")
  RETURNS "pg_catalog"."bytea" AS '$libdir/vector', 'sparsevec_send'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for sparsevec_to_halfvec
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."sparsevec_to_halfvec"("public"."sparsevec", int4, bool);
CREATE FUNCTION "public"."sparsevec_to_halfvec"("public"."sparsevec", int4, bool)
  RETURNS "public"."halfvec" AS '$libdir/vector', 'sparsevec_to_halfvec'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for sparsevec_to_vector
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."sparsevec_to_vector"("public"."sparsevec", int4, bool);
CREATE FUNCTION "public"."sparsevec_to_vector"("public"."sparsevec", int4, bool)
  RETURNS "public"."vector" AS '$libdir/vector', 'sparsevec_to_vector'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for sparsevec_typmod_in
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."sparsevec_typmod_in"(_cstring);
CREATE FUNCTION "public"."sparsevec_typmod_in"(_cstring)
  RETURNS "pg_catalog"."int4" AS '$libdir/vector', 'sparsevec_typmod_in'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for subvector
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."subvector"("public"."vector", int4, int4);
CREATE FUNCTION "public"."subvector"("public"."vector", int4, int4)
  RETURNS "public"."vector" AS '$libdir/vector', 'subvector'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for subvector
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."subvector"("public"."halfvec", int4, int4);
CREATE FUNCTION "public"."subvector"("public"."halfvec", int4, int4)
  RETURNS "public"."halfvec" AS '$libdir/vector', 'halfvec_subvector'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for time_dist
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."time_dist"(time, time);
CREATE FUNCTION "public"."time_dist"(time, time)
  RETURNS "pg_catalog"."interval" AS '$libdir/btree_gist', 'time_dist'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for ts_dist
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."ts_dist"(timestamp, timestamp);
CREATE FUNCTION "public"."ts_dist"(timestamp, timestamp)
  RETURNS "pg_catalog"."interval" AS '$libdir/btree_gist', 'ts_dist'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for tstz_dist
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."tstz_dist"(timestamptz, timestamptz);
CREATE FUNCTION "public"."tstz_dist"(timestamptz, timestamptz)
  RETURNS "pg_catalog"."interval" AS '$libdir/btree_gist', 'tstz_dist'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector"("public"."vector", int4, bool);
CREATE FUNCTION "public"."vector"("public"."vector", int4, bool)
  RETURNS "public"."vector" AS '$libdir/vector', 'vector'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_accum
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_accum"(_float8, "public"."vector");
CREATE FUNCTION "public"."vector_accum"(_float8, "public"."vector")
  RETURNS "pg_catalog"."_float8" AS '$libdir/vector', 'vector_accum'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_add
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_add"("public"."vector", "public"."vector");
CREATE FUNCTION "public"."vector_add"("public"."vector", "public"."vector")
  RETURNS "public"."vector" AS '$libdir/vector', 'vector_add'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_avg
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_avg"(_float8);
CREATE FUNCTION "public"."vector_avg"(_float8)
  RETURNS "public"."vector" AS '$libdir/vector', 'vector_avg'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_cmp
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_cmp"("public"."vector", "public"."vector");
CREATE FUNCTION "public"."vector_cmp"("public"."vector", "public"."vector")
  RETURNS "pg_catalog"."int4" AS '$libdir/vector', 'vector_cmp'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_combine
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_combine"(_float8, _float8);
CREATE FUNCTION "public"."vector_combine"(_float8, _float8)
  RETURNS "pg_catalog"."_float8" AS '$libdir/vector', 'vector_combine'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_concat
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_concat"("public"."vector", "public"."vector");
CREATE FUNCTION "public"."vector_concat"("public"."vector", "public"."vector")
  RETURNS "public"."vector" AS '$libdir/vector', 'vector_concat'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_dims
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_dims"("public"."halfvec");
CREATE FUNCTION "public"."vector_dims"("public"."halfvec")
  RETURNS "pg_catalog"."int4" AS '$libdir/vector', 'halfvec_vector_dims'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_dims
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_dims"("public"."vector");
CREATE FUNCTION "public"."vector_dims"("public"."vector")
  RETURNS "pg_catalog"."int4" AS '$libdir/vector', 'vector_dims'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_eq
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_eq"("public"."vector", "public"."vector");
CREATE FUNCTION "public"."vector_eq"("public"."vector", "public"."vector")
  RETURNS "pg_catalog"."bool" AS '$libdir/vector', 'vector_eq'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_ge
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_ge"("public"."vector", "public"."vector");
CREATE FUNCTION "public"."vector_ge"("public"."vector", "public"."vector")
  RETURNS "pg_catalog"."bool" AS '$libdir/vector', 'vector_ge'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_gt
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_gt"("public"."vector", "public"."vector");
CREATE FUNCTION "public"."vector_gt"("public"."vector", "public"."vector")
  RETURNS "pg_catalog"."bool" AS '$libdir/vector', 'vector_gt'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_in
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_in"(cstring, oid, int4);
CREATE FUNCTION "public"."vector_in"(cstring, oid, int4)
  RETURNS "public"."vector" AS '$libdir/vector', 'vector_in'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_l2_squared_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_l2_squared_distance"("public"."vector", "public"."vector");
CREATE FUNCTION "public"."vector_l2_squared_distance"("public"."vector", "public"."vector")
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'vector_l2_squared_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_le
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_le"("public"."vector", "public"."vector");
CREATE FUNCTION "public"."vector_le"("public"."vector", "public"."vector")
  RETURNS "pg_catalog"."bool" AS '$libdir/vector', 'vector_le'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_lt
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_lt"("public"."vector", "public"."vector");
CREATE FUNCTION "public"."vector_lt"("public"."vector", "public"."vector")
  RETURNS "pg_catalog"."bool" AS '$libdir/vector', 'vector_lt'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_mul
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_mul"("public"."vector", "public"."vector");
CREATE FUNCTION "public"."vector_mul"("public"."vector", "public"."vector")
  RETURNS "public"."vector" AS '$libdir/vector', 'vector_mul'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_ne
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_ne"("public"."vector", "public"."vector");
CREATE FUNCTION "public"."vector_ne"("public"."vector", "public"."vector")
  RETURNS "pg_catalog"."bool" AS '$libdir/vector', 'vector_ne'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_negative_inner_product
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_negative_inner_product"("public"."vector", "public"."vector");
CREATE FUNCTION "public"."vector_negative_inner_product"("public"."vector", "public"."vector")
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'vector_negative_inner_product'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_norm
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_norm"("public"."vector");
CREATE FUNCTION "public"."vector_norm"("public"."vector")
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'vector_norm'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_out
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_out"("public"."vector");
CREATE FUNCTION "public"."vector_out"("public"."vector")
  RETURNS "pg_catalog"."cstring" AS '$libdir/vector', 'vector_out'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_recv
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_recv"(internal, oid, int4);
CREATE FUNCTION "public"."vector_recv"(internal, oid, int4)
  RETURNS "public"."vector" AS '$libdir/vector', 'vector_recv'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_send
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_send"("public"."vector");
CREATE FUNCTION "public"."vector_send"("public"."vector")
  RETURNS "pg_catalog"."bytea" AS '$libdir/vector', 'vector_send'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_spherical_distance
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_spherical_distance"("public"."vector", "public"."vector");
CREATE FUNCTION "public"."vector_spherical_distance"("public"."vector", "public"."vector")
  RETURNS "pg_catalog"."float8" AS '$libdir/vector', 'vector_spherical_distance'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_sub
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_sub"("public"."vector", "public"."vector");
CREATE FUNCTION "public"."vector_sub"("public"."vector", "public"."vector")
  RETURNS "public"."vector" AS '$libdir/vector', 'vector_sub'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_to_float4
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_to_float4"("public"."vector", int4, bool);
CREATE FUNCTION "public"."vector_to_float4"("public"."vector", int4, bool)
  RETURNS "pg_catalog"."_float4" AS '$libdir/vector', 'vector_to_float4'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_to_halfvec
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_to_halfvec"("public"."vector", int4, bool);
CREATE FUNCTION "public"."vector_to_halfvec"("public"."vector", int4, bool)
  RETURNS "public"."halfvec" AS '$libdir/vector', 'vector_to_halfvec'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_to_sparsevec
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_to_sparsevec"("public"."vector", int4, bool);
CREATE FUNCTION "public"."vector_to_sparsevec"("public"."vector", int4, bool)
  RETURNS "public"."sparsevec" AS '$libdir/vector', 'vector_to_sparsevec'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Function structure for vector_typmod_in
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."vector_typmod_in"(_cstring);
CREATE FUNCTION "public"."vector_typmod_in"(_cstring)
  RETURNS "pg_catalog"."int4" AS '$libdir/vector', 'vector_typmod_in'
  LANGUAGE c IMMUTABLE STRICT
  COST 1;

-- ----------------------------
-- Alter sequences owned by
-- ----------------------------
ALTER SEQUENCE "public"."identity_display_no_seq"
OWNED BY "public"."identity"."display_no";
SELECT setval('"public"."identity_display_no_seq"', 184, true);

-- ----------------------------
-- Alter sequences owned by
-- ----------------------------
ALTER SEQUENCE "public"."vad_id_seq"
OWNED BY "public"."vad"."id";
SELECT setval('"public"."vad_id_seq"', 9145, true);

-- ----------------------------
-- Indexes structure for table ai_task_run
-- ----------------------------
CREATE INDEX "idx_ai_task_run_camera_status" ON "public"."ai_task_run" USING btree (
  "camera_id" "pg_catalog"."int8_ops" ASC NULLS LAST,
  "status" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "idx_ai_task_run_camera_task_status" ON "public"."ai_task_run" USING btree (
  "camera_id" "pg_catalog"."int8_ops" ASC NULLS LAST,
  "task_code" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST,
  "status" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key structure for table ai_task_run
-- ----------------------------
ALTER TABLE "public"."ai_task_run" ADD CONSTRAINT "ai_task_run_pkey" PRIMARY KEY ("run_id");

-- ----------------------------
-- Indexes structure for table algorithm_result
-- ----------------------------
CREATE INDEX "ix_algorithm_result_type_time" ON "public"."algorithm_result" USING btree (
  "result_type" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST,
  "start_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST,
  "id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table algorithm_result
-- ----------------------------
ALTER TABLE "public"."algorithm_result" ADD CONSTRAINT "algorithm_result_result_set_id_producer_result_key_key" UNIQUE ("result_set_id", "producer_result_key");

-- ----------------------------
-- Checks structure for table algorithm_result
-- ----------------------------
ALTER TABLE "public"."algorithm_result" ADD CONSTRAINT "algorithm_result_check" CHECK (end_at IS NULL OR end_at >= start_at);

-- ----------------------------
-- Primary Key structure for table algorithm_result
-- ----------------------------
ALTER TABLE "public"."algorithm_result" ADD CONSTRAINT "algorithm_result_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table analysis_frame
-- ----------------------------
CREATE INDEX "ix_analysis_frame_input" ON "public"."analysis_frame" USING btree (
  "input_frame_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "result_set_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table analysis_frame
-- ----------------------------
ALTER TABLE "public"."analysis_frame" ADD CONSTRAINT "analysis_frame_result_set_id_input_frame_id_key" UNIQUE ("result_set_id", "input_frame_id");
ALTER TABLE "public"."analysis_frame" ADD CONSTRAINT "analysis_frame_result_set_id_producer_result_key_key" UNIQUE ("result_set_id", "producer_result_key");

-- ----------------------------
-- Checks structure for table analysis_frame
-- ----------------------------
ALTER TABLE "public"."analysis_frame" ADD CONSTRAINT "analysis_frame_target_count_check" CHECK (target_count >= 0);

-- ----------------------------
-- Primary Key structure for table analysis_frame
-- ----------------------------
ALTER TABLE "public"."analysis_frame" ADD CONSTRAINT "analysis_frame_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table asset_reference
-- ----------------------------
CREATE INDEX "ix_asset_ref_device_feedback" ON "public"."asset_reference" USING btree (
  "device_task_feedback_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE device_task_feedback_id IS NOT NULL;
CREATE INDEX "ix_asset_ref_evidence" ON "public"."asset_reference" USING btree (
  "evidence_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE evidence_id IS NOT NULL;
CREATE INDEX "ix_asset_ref_identity" ON "public"."asset_reference" USING btree (
  "identity_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE identity_id IS NOT NULL;
CREATE INDEX "ix_asset_ref_query" ON "public"."asset_reference" USING btree (
  "query_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE query_id IS NOT NULL;
CREATE INDEX "ix_asset_ref_result" ON "public"."asset_reference" USING btree (
  "result_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE result_id IS NOT NULL;
CREATE INDEX "ix_asset_ref_sample" ON "public"."asset_reference" USING btree (
  "sample_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE sample_id IS NOT NULL;
CREATE INDEX "ix_asset_reference_retention" ON "public"."asset_reference" USING btree (
  "asset_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "retain_until" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);
CREATE UNIQUE INDEX "uk_asset_ref_device_feedback" ON "public"."asset_reference" USING btree (
  "asset_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "device_task_feedback_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE device_task_feedback_id IS NOT NULL;
CREATE UNIQUE INDEX "uk_asset_ref_evidence" ON "public"."asset_reference" USING btree (
  "asset_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "evidence_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE evidence_id IS NOT NULL;
CREATE UNIQUE INDEX "uk_asset_ref_identity" ON "public"."asset_reference" USING btree (
  "asset_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "identity_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE identity_id IS NOT NULL;
CREATE UNIQUE INDEX "uk_asset_ref_query" ON "public"."asset_reference" USING btree (
  "asset_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "query_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE query_id IS NOT NULL;
CREATE UNIQUE INDEX "uk_asset_ref_result" ON "public"."asset_reference" USING btree (
  "asset_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "result_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE result_id IS NOT NULL;
CREATE UNIQUE INDEX "uk_asset_ref_sample" ON "public"."asset_reference" USING btree (
  "asset_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "sample_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE sample_id IS NOT NULL;

-- ----------------------------
-- Checks structure for table asset_reference
-- ----------------------------
ALTER TABLE "public"."asset_reference" ADD CONSTRAINT "ck_asset_ref_device_retention" CHECK (device_task_feedback_id IS NULL OR retain_until IS NOT NULL);
ALTER TABLE "public"."asset_reference" ADD CONSTRAINT "ck_asset_ref_owner_v02_device" CHECK (num_nonnulls(sample_id, evidence_id, query_id, identity_id, message_id, result_id, device_task_feedback_id) = 1);
ALTER TABLE "public"."asset_reference" ADD CONSTRAINT "ck_asset_ref_retention" CHECK (retain_until IS NOT NULL OR identity_id IS NOT NULL OR sample_id IS NOT NULL);
ALTER TABLE "public"."asset_reference" ADD CONSTRAINT "ck_asset_ref_stage2_owner" CHECK (message_id IS NULL);

-- ----------------------------
-- Primary Key structure for table asset_reference
-- ----------------------------
ALTER TABLE "public"."asset_reference" ADD CONSTRAINT "asset_reference_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table business_event
-- ----------------------------
CREATE INDEX "ix_event_expiry" ON "public"."business_event" USING btree (
  "expires_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);
CREATE INDEX "ix_event_type_time" ON "public"."business_event" USING btree (
  "event_type" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST,
  "start_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST,
  "id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table business_event
-- ----------------------------
ALTER TABLE "public"."business_event" ADD CONSTRAINT "business_event_event_type_event_key_key" UNIQUE ("event_type", "event_key");
ALTER TABLE "public"."business_event" ADD CONSTRAINT "business_event_legacy_vad_id_key" UNIQUE ("legacy_vad_id");

-- ----------------------------
-- Checks structure for table business_event
-- ----------------------------
ALTER TABLE "public"."business_event" ADD CONSTRAINT "business_event_state_check" CHECK (state::text = ANY (ARRAY['open'::character varying, 'closed'::character varying, 'interrupted'::character varying]::text[]));
ALTER TABLE "public"."business_event" ADD CONSTRAINT "ck_business_event_revision" CHECK (revision > 0);
ALTER TABLE "public"."business_event" ADD CONSTRAINT "business_event_check" CHECK (end_at IS NULL OR end_at >= start_at);
ALTER TABLE "public"."business_event" ADD CONSTRAINT "business_event_check1" CHECK (state::text = 'open'::text AND end_reason IS NULL OR (state::text = ANY (ARRAY['closed'::character varying, 'interrupted'::character varying]::text[])) AND end_at IS NOT NULL AND end_reason IS NOT NULL AND (end_reason::text = ANY (ARRAY['normal'::character varying, 'observation_interrupted'::character varying, 'cancelled'::character varying]::text[])));
ALTER TABLE "public"."business_event" ADD CONSTRAINT "business_event_end_reason_check" CHECK (end_reason IS NULL OR (end_reason::text = ANY (ARRAY['normal'::character varying, 'observation_interrupted'::character varying, 'cancelled'::character varying]::text[])));

-- ----------------------------
-- Primary Key structure for table business_event
-- ----------------------------
ALTER TABLE "public"."business_event" ADD CONSTRAINT "business_event_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table business_task
-- ----------------------------
CREATE INDEX "ix_task_expiry" ON "public"."business_task" USING btree (
  "expires_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);
CREATE INDEX "ix_task_namespace_pending" ON "public"."business_task" USING btree (
  "execution_namespace" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST,
  "created_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST,
  "task_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE state::text = 'pending'::text AND dispatch_mode::text = 'platform_managed'::text;
CREATE INDEX "ix_task_owner_state" ON "public"."business_task" USING btree (
  "owner_user_id" "pg_catalog"."int8_ops" ASC NULLS LAST,
  "state" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST,
  "created_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);
CREATE INDEX "ix_task_platform_pending" ON "public"."business_task" USING btree (
  "created_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST,
  "task_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE state::text = 'pending'::text AND dispatch_mode::text = 'platform_managed'::text;

-- ----------------------------
-- Uniques structure for table business_task
-- ----------------------------
ALTER TABLE "public"."business_task" ADD CONSTRAINT "uq_task_namespace_business_key" UNIQUE ("execution_namespace", "task_kind", "business_key");

-- ----------------------------
-- Checks structure for table business_task
-- ----------------------------
ALTER TABLE "public"."business_task" ADD CONSTRAINT "business_task_state_check" CHECK (state::text = ANY (ARRAY['pending'::character varying, 'running'::character varying, 'waiting_input'::character varying, 'succeeded'::character varying, 'partial'::character varying, 'failed'::character varying, 'cancelled'::character varying, 'expired'::character varying]::text[]));
ALTER TABLE "public"."business_task" ADD CONSTRAINT "business_task_check" CHECK (generation >= 0 AND progress >= 0::numeric AND progress <= 100::numeric AND revision > 0);
ALTER TABLE "public"."business_task" ADD CONSTRAINT "business_task_task_mode_check" CHECK (task_mode::text = ANY (ARRAY['once'::character varying, 'continuous'::character varying]::text[]));
ALTER TABLE "public"."business_task" ADD CONSTRAINT "business_task_dispatch_mode_check" CHECK (dispatch_mode::text = ANY (ARRAY['runtime_managed'::character varying, 'platform_managed'::character varying]::text[]));

-- ----------------------------
-- Primary Key structure for table business_task
-- ----------------------------
ALTER TABLE "public"."business_task" ADD CONSTRAINT "business_task_pkey" PRIMARY KEY ("task_id");

-- ----------------------------
-- Indexes structure for table camera
-- ----------------------------
CREATE INDEX "ix_camera_device" ON "public"."camera" USING btree (
  "device_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE device_id IS NOT NULL;

-- ----------------------------
-- Uniques structure for table camera
-- ----------------------------
ALTER TABLE "public"."camera" ADD CONSTRAINT "camera_camera_code_key" UNIQUE ("camera_code");
ALTER TABLE "public"."camera" ADD CONSTRAINT "uk_camera_device_channel" UNIQUE ("management_device_id", "channel_code");

-- ----------------------------
-- Checks structure for table camera
-- ----------------------------
ALTER TABLE "public"."camera" ADD CONSTRAINT "ck_camera_device_channel" CHECK ((management_device_id IS NULL) = (channel_code IS NULL));
ALTER TABLE "public"."camera" ADD CONSTRAINT "ck_camera_source_kind" CHECK (source_kind::text = ANY (ARRAY['camera'::character varying, 'device_video'::character varying, 'imported_video'::character varying]::text[]));

-- ----------------------------
-- Primary Key structure for table camera
-- ----------------------------
ALTER TABLE "public"."camera" ADD CONSTRAINT "camera_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table camera_stream
-- ----------------------------
CREATE INDEX "idx_camera_stream_camera_id" ON "public"."camera_stream" USING btree (
  "camera_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);
CREATE INDEX "idx_camera_stream_task_type" ON "public"."camera_stream" USING btree (
  "task_type" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table camera_stream
-- ----------------------------
ALTER TABLE "public"."camera_stream" ADD CONSTRAINT "camera_stream_shm_name_key" UNIQUE ("shm_name");
ALTER TABLE "public"."camera_stream" ADD CONSTRAINT "camera_stream_stream_name_key" UNIQUE ("stream_name");

-- ----------------------------
-- Primary Key structure for table camera_stream
-- ----------------------------
ALTER TABLE "public"."camera_stream" ADD CONSTRAINT "camera_stream_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Checks structure for table capability_definition
-- ----------------------------
ALTER TABLE "public"."capability_definition" ADD CONSTRAINT "capability_definition_check" CHECK (cardinality(object_types) > 0 AND cardinality(input_kinds) > 0);
ALTER TABLE "public"."capability_definition" ADD CONSTRAINT "capability_definition_revision_check" CHECK (revision > 0);

-- ----------------------------
-- Primary Key structure for table capability_definition
-- ----------------------------
ALTER TABLE "public"."capability_definition" ADD CONSTRAINT "capability_definition_pkey" PRIMARY KEY ("capability_code");

-- ----------------------------
-- Indexes structure for table capability_instance
-- ----------------------------
CREATE INDEX "ix_instance_selection" ON "public"."capability_instance" USING btree (
  "capability_code" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST,
  "enabled" "pg_catalog"."bool_ops" ASC NULLS LAST,
  "id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table capability_instance
-- ----------------------------
ALTER TABLE "public"."capability_instance" ADD CONSTRAINT "uk_capability_instance_key" UNIQUE ("capability_code", "instance_key");

-- ----------------------------
-- Checks structure for table capability_instance
-- ----------------------------
ALTER TABLE "public"."capability_instance" ADD CONSTRAINT "ck_instance_revision" CHECK (revision > 0);
ALTER TABLE "public"."capability_instance" ADD CONSTRAINT "capability_instance_dispatch_mode_check" CHECK (dispatch_mode::text = ANY (ARRAY['runtime_managed'::character varying, 'platform_managed'::character varying]::text[]));
ALTER TABLE "public"."capability_instance" ADD CONSTRAINT "ck_instance_sources" CHECK (array_position(source_ids, NULL::uuid) IS NULL);
ALTER TABLE "public"."capability_instance" ADD CONSTRAINT "ck_instance_keys" CHECK (char_length(btrim(instance_key::text)) > 0 AND char_length(btrim(implementation_code::text)) > 0 AND char_length(btrim(implementation_version::text)) > 0 AND char_length(btrim(service_ref::text)) > 0);

-- ----------------------------
-- Primary Key structure for table capability_instance
-- ----------------------------
ALTER TABLE "public"."capability_instance" ADD CONSTRAINT "pk_capability_instance" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table detection_observation
-- ----------------------------
CREATE INDEX "ix_observation_track_frame" ON "public"."detection_observation" USING btree (
  "tracklet_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "analysis_frame_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table detection_observation
-- ----------------------------
ALTER TABLE "public"."detection_observation" ADD CONSTRAINT "detection_observation_analysis_frame_id_target_index_key" UNIQUE ("analysis_frame_id", "target_index");

-- ----------------------------
-- Checks structure for table detection_observation
-- ----------------------------
ALTER TABLE "public"."detection_observation" ADD CONSTRAINT "detection_observation_check1" CHECK (target_index >= 0 AND (confidence IS NULL OR confidence >= 0::double precision AND confidence <= 1::double precision));
ALTER TABLE "public"."detection_observation" ADD CONSTRAINT "detection_observation_check2" CHECK (observation_kind::text = 'predicted'::text OR confidence IS NOT NULL);
ALTER TABLE "public"."detection_observation" ADD CONSTRAINT "detection_observation_observation_kind_check" CHECK (observation_kind::text = ANY (ARRAY['observed'::character varying, 'predicted'::character varying]::text[]));
ALTER TABLE "public"."detection_observation" ADD CONSTRAINT "detection_observation_check" CHECK (bbox_left >= 0::double precision AND bbox_top >= 0::double precision AND bbox_right <= 1::double precision AND bbox_bottom <= 1::double precision AND bbox_right > bbox_left AND bbox_bottom > bbox_top);

-- ----------------------------
-- Primary Key structure for table detection_observation
-- ----------------------------
ALTER TABLE "public"."detection_observation" ADD CONSTRAINT "detection_observation_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table device_registry
-- ----------------------------
CREATE INDEX "ix_device_registry_parent" ON "public"."device_registry" USING btree (
  "parent_device_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table device_registry
-- ----------------------------
ALTER TABLE "public"."device_registry" ADD CONSTRAINT "uk_device_registry_external" UNIQUE ("adapter_code", "external_device_id");

-- ----------------------------
-- Checks structure for table device_registry
-- ----------------------------
ALTER TABLE "public"."device_registry" ADD CONSTRAINT "device_registry_config_json_check" CHECK (jsonb_typeof(config_json) = 'object'::text);
ALTER TABLE "public"."device_registry" ADD CONSTRAINT "device_registry_check" CHECK (parent_device_id IS NULL OR parent_device_id <> id);
ALTER TABLE "public"."device_registry" ADD CONSTRAINT "device_registry_management_device_id_check" CHECK (management_device_id IS NULL OR management_device_id > 0);
ALTER TABLE "public"."device_registry" ADD CONSTRAINT "device_registry_check1" CHECK (revision > 0 AND btrim(adapter_code::text) <> ''::text AND btrim(external_device_id::text) <> ''::text AND btrim(device_type::text) <> ''::text AND btrim(display_name::text) <> ''::text);

-- ----------------------------
-- Primary Key structure for table device_registry
-- ----------------------------
ALTER TABLE "public"."device_registry" ADD CONSTRAINT "pk_device_registry" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table device_state_observation
-- ----------------------------
CREATE INDEX "ix_device_state_expiry" ON "public"."device_state_observation" USING btree (
  "expires_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST,
  "id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);
CREATE INDEX "ix_device_state_history" ON "public"."device_state_observation" USING btree (
  "device_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "observed_at" "pg_catalog"."timestamptz_ops" DESC NULLS FIRST,
  "received_at" "pg_catalog"."timestamptz_ops" DESC NULLS FIRST,
  "id" "pg_catalog"."uuid_ops" DESC NULLS FIRST
);
CREATE INDEX "ix_device_state_latest" ON "public"."device_state_observation" USING btree (
  "device_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "received_at" "pg_catalog"."timestamptz_ops" DESC NULLS FIRST,
  "id" "pg_catalog"."uuid_ops" DESC NULLS FIRST
);

-- ----------------------------
-- Uniques structure for table device_state_observation
-- ----------------------------
ALTER TABLE "public"."device_state_observation" ADD CONSTRAINT "uk_device_state_producer" UNIQUE ("device_id", "producer_session_key", "producer_message_key");

-- ----------------------------
-- Checks structure for table device_state_observation
-- ----------------------------
ALTER TABLE "public"."device_state_observation" ADD CONSTRAINT "device_state_observation_check2" CHECK (expires_at > observed_at);
ALTER TABLE "public"."device_state_observation" ADD CONSTRAINT "device_state_observation_payload_digest_check" CHECK (payload_digest ~ '^[0-9a-f]{64}$'::text);
ALTER TABLE "public"."device_state_observation" ADD CONSTRAINT "device_state_observation_payload_json_check" CHECK (jsonb_typeof(payload_json) = 'object'::text);
ALTER TABLE "public"."device_state_observation" ADD CONSTRAINT "device_state_observation_check" CHECK ((task_id IS NULL) = (run_id IS NULL));
ALTER TABLE "public"."device_state_observation" ADD CONSTRAINT "device_state_observation_time_quality_check" CHECK (time_quality::text = ANY (ARRAY['device_reported'::character varying, 'received_estimated'::character varying]::text[]));
ALTER TABLE "public"."device_state_observation" ADD CONSTRAINT "device_state_observation_record_kind_check" CHECK (record_kind::text = ANY (ARRAY['change'::character varying, 'sample'::character varying]::text[]));
ALTER TABLE "public"."device_state_observation" ADD CONSTRAINT "device_state_observation_check1" CHECK (btrim(producer_session_key::text) <> ''::text AND btrim(producer_message_key::text) <> ''::text AND btrim(state_code::text) <> ''::text AND btrim(schema_version::text) <> ''::text);

-- ----------------------------
-- Primary Key structure for table device_state_observation
-- ----------------------------
ALTER TABLE "public"."device_state_observation" ADD CONSTRAINT "pk_device_state_observation" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table device_task_binding
-- ----------------------------
CREATE INDEX "ix_device_task_device_time" ON "public"."device_task_binding" USING btree (
  "device_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "created_at" "pg_catalog"."timestamptz_ops" DESC NULLS FIRST,
  "id" "pg_catalog"."uuid_ops" DESC NULLS FIRST
);
CREATE INDEX "ix_device_task_expiry" ON "public"."device_task_binding" USING btree (
  "expires_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST,
  "id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table device_task_binding
-- ----------------------------
ALTER TABLE "public"."device_task_binding" ADD CONSTRAINT "uk_device_task_run" UNIQUE ("run_id");
ALTER TABLE "public"."device_task_binding" ADD CONSTRAINT "uk_device_task_dispatch" UNIQUE ("device_id", "dispatch_key");

-- ----------------------------
-- Checks structure for table device_task_binding
-- ----------------------------
ALTER TABLE "public"."device_task_binding" ADD CONSTRAINT "device_task_binding_check3" CHECK (dispatch_state::text <> 'acknowledged'::text OR dispatched_at IS NOT NULL AND acknowledged_at IS NOT NULL);
ALTER TABLE "public"."device_task_binding" ADD CONSTRAINT "device_task_binding_dispatch_state_check" CHECK (dispatch_state::text = ANY (ARRAY['pending'::character varying, 'sent'::character varying, 'acknowledged'::character varying, 'rejected'::character varying]::text[]));
ALTER TABLE "public"."device_task_binding" ADD CONSTRAINT "device_task_binding_check" CHECK (btrim(dispatch_key::text) <> ''::text AND (external_task_id IS NULL OR btrim(external_task_id::text) <> ''::text));
ALTER TABLE "public"."device_task_binding" ADD CONSTRAINT "device_task_binding_check1" CHECK (last_feedback_seq >= 0 AND revision > 0);
ALTER TABLE "public"."device_task_binding" ADD CONSTRAINT "device_task_binding_check2" CHECK (acknowledged_at IS NULL OR dispatched_at IS NULL OR acknowledged_at >= dispatched_at);

-- ----------------------------
-- Primary Key structure for table device_task_binding
-- ----------------------------
ALTER TABLE "public"."device_task_binding" ADD CONSTRAINT "pk_device_task_binding" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table device_task_feedback
-- ----------------------------
CREATE INDEX "ix_device_feedback_expiry" ON "public"."device_task_feedback" USING btree (
  "expires_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST,
  "id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);
CREATE INDEX "ix_device_feedback_order" ON "public"."device_task_feedback" USING btree (
  "binding_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "feedback_seq" "pg_catalog"."int8_ops" ASC NULLS LAST,
  "id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table device_task_feedback
-- ----------------------------
ALTER TABLE "public"."device_task_feedback" ADD CONSTRAINT "uk_device_feedback_key" UNIQUE ("binding_id", "feedback_key");
ALTER TABLE "public"."device_task_feedback" ADD CONSTRAINT "uk_device_feedback_seq" UNIQUE ("binding_id", "feedback_seq");

-- ----------------------------
-- Checks structure for table device_task_feedback
-- ----------------------------
ALTER TABLE "public"."device_task_feedback" ADD CONSTRAINT "device_task_feedback_feedback_type_check" CHECK (feedback_type::text = ANY (ARRAY['accepted'::character varying, 'started'::character varying, 'progress'::character varying, 'artifact'::character varying, 'completed'::character varying, 'failed'::character varying, 'cancelled'::character varying, 'rejected'::character varying]::text[]));
ALTER TABLE "public"."device_task_feedback" ADD CONSTRAINT "device_task_feedback_payload_digest_check" CHECK (payload_digest ~ '^[0-9a-f]{64}$'::text);
ALTER TABLE "public"."device_task_feedback" ADD CONSTRAINT "ck_device_feedback_state_required" CHECK ((feedback_type::text = ANY (ARRAY['accepted'::character varying, 'artifact'::character varying]::text[])) OR execution_state IS NOT NULL);
ALTER TABLE "public"."device_task_feedback" ADD CONSTRAINT "device_task_feedback_progress_check" CHECK (progress IS NULL OR progress >= 0::numeric AND progress <= 100::numeric);
ALTER TABLE "public"."device_task_feedback" ADD CONSTRAINT "device_task_feedback_payload_json_check" CHECK (jsonb_typeof(payload_json) = 'object'::text);
ALTER TABLE "public"."device_task_feedback" ADD CONSTRAINT "device_task_feedback_check" CHECK (feedback_seq > 0 AND btrim(feedback_key::text) <> ''::text AND btrim(schema_version::text) <> ''::text);
ALTER TABLE "public"."device_task_feedback" ADD CONSTRAINT "device_task_feedback_check1" CHECK ((feedback_type::text = ANY (ARRAY['accepted'::character varying, 'artifact'::character varying]::text[])) AND execution_state IS NULL OR (feedback_type::text = ANY (ARRAY['started'::character varying, 'progress'::character varying]::text[])) AND execution_state::text = 'running'::text OR feedback_type::text = 'completed'::text AND (execution_state::text = ANY (ARRAY['succeeded'::character varying, 'partial'::character varying]::text[])) OR (feedback_type::text = ANY (ARRAY['failed'::character varying, 'rejected'::character varying]::text[])) AND execution_state::text = 'failed'::text OR feedback_type::text = 'cancelled'::text AND execution_state::text = 'cancelled'::text);

-- ----------------------------
-- Primary Key structure for table device_task_feedback
-- ----------------------------
ALTER TABLE "public"."device_task_feedback" ADD CONSTRAINT "pk_device_task_feedback" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table episode
-- ----------------------------
CREATE INDEX "idx_episode_start_ts" ON "public"."episode" USING btree (
  "start_ts" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);
CREATE INDEX "ix_episode_identity_time" ON "public"."episode" USING btree (
  "identity_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "start_ts" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);
CREATE UNIQUE INDEX "uk_episode_open_identity" ON "public"."episode" USING btree (
  "identity_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "activity_type" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
) WHERE state::text = 'open'::text AND identity_id IS NOT NULL;

-- ----------------------------
-- Checks structure for table episode
-- ----------------------------
ALTER TABLE "public"."episode" ADD CONSTRAINT "ck_episode_end_reason" CHECK (state IS NULL OR state::text = 'open'::text AND end_reason IS NULL OR (state::text = ANY (ARRAY['closed'::character varying, 'interrupted'::character varying]::text[])) AND end_reason IS NOT NULL AND (end_reason::text = ANY (ARRAY['normal'::character varying, 'observation_interrupted'::character varying, 'cancelled'::character varying]::text[])));
ALTER TABLE "public"."episode" ADD CONSTRAINT "ck_episode_revision" CHECK (revision IS NULL OR revision > 0);
ALTER TABLE "public"."episode" ADD CONSTRAINT "ck_episode_state" CHECK (state::text = ANY (ARRAY['open'::character varying, 'closed'::character varying, 'interrupted'::character varying]::text[]));
ALTER TABLE "public"."episode" ADD CONSTRAINT "ck_episode_target_exclusive" CHECK (NOT (target_id IS NOT NULL AND stranger_target_id IS NOT NULL));

-- ----------------------------
-- Primary Key structure for table episode
-- ----------------------------
ALTER TABLE "public"."episode" ADD CONSTRAINT "episode_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table episode_media_link
-- ----------------------------
CREATE INDEX "idx_episode_media_link_episode_id" ON "public"."episode_media_link" USING btree (
  "episode_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);
CREATE INDEX "idx_episode_media_link_media_asset_id" ON "public"."episode_media_link" USING btree (
  "media_asset_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key structure for table episode_media_link
-- ----------------------------
ALTER TABLE "public"."episode_media_link" ADD CONSTRAINT "episode_media_link_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table episode_tracklet_link
-- ----------------------------
CREATE INDEX "idx_episode_tracklet_link_episode_id" ON "public"."episode_tracklet_link" USING btree (
  "episode_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);
CREATE INDEX "idx_episode_tracklet_link_tracklet_id" ON "public"."episode_tracklet_link" USING btree (
  "tracklet_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Checks structure for table episode_tracklet_link
-- ----------------------------
ALTER TABLE "public"."episode_tracklet_link" ADD CONSTRAINT "ck_episode_track_ordinal" CHECK (ordinal IS NULL OR ordinal >= 0);

-- ----------------------------
-- Primary Key structure for table episode_tracklet_link
-- ----------------------------
ALTER TABLE "public"."episode_tracklet_link" ADD CONSTRAINT "episode_tracklet_link_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table event_object_link
-- ----------------------------
CREATE INDEX "ix_event_object_identity" ON "public"."event_object_link" USING btree (
  "identity_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "event_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE identity_id IS NOT NULL;
CREATE INDEX "ix_event_object_sample" ON "public"."event_object_link" USING btree (
  "sample_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "event_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE sample_id IS NOT NULL;
CREATE INDEX "ix_event_object_track" ON "public"."event_object_link" USING btree (
  "tracklet_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "event_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE tracklet_id IS NOT NULL;
CREATE UNIQUE INDEX "uk_event_object_identity" ON "public"."event_object_link" USING btree (
  "event_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "identity_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "object_role" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
) WHERE identity_id IS NOT NULL;
CREATE UNIQUE INDEX "uk_event_object_sample" ON "public"."event_object_link" USING btree (
  "event_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "sample_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "object_role" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
) WHERE sample_id IS NOT NULL;
CREATE UNIQUE INDEX "uk_event_object_track" ON "public"."event_object_link" USING btree (
  "event_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "tracklet_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "object_role" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
) WHERE tracklet_id IS NOT NULL;

-- ----------------------------
-- Checks structure for table event_object_link
-- ----------------------------
ALTER TABLE "public"."event_object_link" ADD CONSTRAINT "event_object_link_check" CHECK (num_nonnulls(identity_id, tracklet_id, sample_id) = 1);

-- ----------------------------
-- Primary Key structure for table event_object_link
-- ----------------------------
ALTER TABLE "public"."event_object_link" ADD CONSTRAINT "event_object_link_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table evidence_reference
-- ----------------------------
CREATE INDEX "ix_evidence_activity" ON "public"."evidence_reference" USING btree (
  "activity_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);
CREATE INDEX "ix_evidence_event" ON "public"."evidence_reference" USING btree (
  "event_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Checks structure for table evidence_reference
-- ----------------------------
ALTER TABLE "public"."evidence_reference" ADD CONSTRAINT "evidence_reference_check1" CHECK (end_at IS NULL OR end_at >= start_at);
ALTER TABLE "public"."evidence_reference" ADD CONSTRAINT "evidence_reference_check2" CHECK (asset_id IS NOT NULL OR fact_snapshot <> '{}'::jsonb);
ALTER TABLE "public"."evidence_reference" ADD CONSTRAINT "evidence_reference_check" CHECK (num_nonnulls(activity_id, event_id) = 1);

-- ----------------------------
-- Primary Key structure for table evidence_reference
-- ----------------------------
ALTER TABLE "public"."evidence_reference" ADD CONSTRAINT "evidence_reference_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table feature
-- ----------------------------
CREATE INDEX "ix_feature_identity" ON "public"."feature" USING btree (
  "identity_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "feature_space_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "ix_feature_sample" ON "public"."feature" USING btree (
  "sample_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE sample_id IS NOT NULL;
CREATE INDEX "ix_feature_space_state_expiry" ON "public"."feature" USING btree (
  "feature_space_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST,
  "state" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST,
  "expires_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);
CREATE INDEX "ix_feature_track" ON "public"."feature" USING btree (
  "tracklet_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "feature_space_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table feature
-- ----------------------------
ALTER TABLE "public"."feature" ADD CONSTRAINT "feature_run_id_producer_feature_key_key" UNIQUE ("run_id", "producer_feature_key");

-- ----------------------------
-- Checks structure for table feature
-- ----------------------------
ALTER TABLE "public"."feature" ADD CONSTRAINT "feature_check1" CHECK (input_count >= used_count AND used_count > 0);
ALTER TABLE "public"."feature" ADD CONSTRAINT "feature_check2" CHECK (aggregation_method::text = 'single'::text AND sample_id IS NOT NULL AND used_count = 1 OR aggregation_method::text = 'mean_l2_v1'::text AND sample_id IS NULL);
ALTER TABLE "public"."feature" ADD CONSTRAINT "feature_state_check" CHECK (state::text = ANY (ARRAY['ready'::character varying, 'invalid'::character varying]::text[]));
ALTER TABLE "public"."feature" ADD CONSTRAINT "feature_aggregation_method_check" CHECK (aggregation_method::text = ANY (ARRAY['single'::character varying, 'mean_l2_v1'::character varying]::text[]));
ALTER TABLE "public"."feature" ADD CONSTRAINT "feature_check" CHECK (dimensions > 0 AND vector_dims(embedding) = dimensions);

-- ----------------------------
-- Primary Key structure for table feature
-- ----------------------------
ALTER TABLE "public"."feature" ADD CONSTRAINT "feature_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table feature_contribution
-- ----------------------------
CREATE INDEX "ix_contribution_sample" ON "public"."feature_contribution" USING btree (
  "sample_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "feature_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);
CREATE INDEX "ix_contribution_source_feature" ON "public"."feature_contribution" USING btree (
  "source_feature_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE source_feature_id IS NOT NULL;

-- ----------------------------
-- Uniques structure for table feature_contribution
-- ----------------------------
ALTER TABLE "public"."feature_contribution" ADD CONSTRAINT "feature_contribution_feature_id_sample_id_key" UNIQUE ("feature_id", "sample_id");

-- ----------------------------
-- Checks structure for table feature_contribution
-- ----------------------------
ALTER TABLE "public"."feature_contribution" ADD CONSTRAINT "feature_contribution_check" CHECK (ordinal >= 0 AND weight = 1::double precision);

-- ----------------------------
-- Primary Key structure for table feature_contribution
-- ----------------------------
ALTER TABLE "public"."feature_contribution" ADD CONSTRAINT "feature_contribution_pkey" PRIMARY KEY ("feature_id", "ordinal");

-- ----------------------------
-- Uniques structure for table feature_space
-- ----------------------------
ALTER TABLE "public"."feature_space" ADD CONSTRAINT "feature_space_definition_sha256_key" UNIQUE ("definition_sha256");
ALTER TABLE "public"."feature_space" ADD CONSTRAINT "feature_space_id_dimensions_key" UNIQUE ("id", "dimensions");

-- ----------------------------
-- Checks structure for table feature_space
-- ----------------------------
ALTER TABLE "public"."feature_space" ADD CONSTRAINT "feature_space_dtype_check" CHECK (dtype::text = 'float32'::text);
ALTER TABLE "public"."feature_space" ADD CONSTRAINT "feature_space_metric_check" CHECK (metric::text = ANY (ARRAY['cosine'::character varying, 'l2'::character varying, 'inner_product'::character varying]::text[]));
ALTER TABLE "public"."feature_space" ADD CONSTRAINT "feature_space_normalization_check" CHECK (normalization::text = ANY (ARRAY['l2'::character varying, 'none'::character varying]::text[]));
ALTER TABLE "public"."feature_space" ADD CONSTRAINT "feature_space_dimensions_check" CHECK (dimensions > 0);

-- ----------------------------
-- Primary Key structure for table feature_space
-- ----------------------------
ALTER TABLE "public"."feature_space" ADD CONSTRAINT "feature_space_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Primary Key structure for table hxjm_schema_migration
-- ----------------------------
ALTER TABLE "public"."hxjm_schema_migration" ADD CONSTRAINT "hxjm_schema_migration_pkey" PRIMARY KEY ("version");

-- ----------------------------
-- Indexes structure for table identity
-- ----------------------------
CREATE INDEX "ix_identity_kind_expiry" ON "public"."identity" USING btree (
  "identity_kind" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST,
  "expires_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);
CREATE INDEX "ix_identity_name" ON "public"."identity" USING btree (
  "display_name" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table identity
-- ----------------------------
ALTER TABLE "public"."identity" ADD CONSTRAINT "identity_display_no_key" UNIQUE ("display_no");

-- ----------------------------
-- Checks structure for table identity
-- ----------------------------
ALTER TABLE "public"."identity" ADD CONSTRAINT "identity_check" CHECK (identity_kind::text = 'temporary'::text AND registered_at IS NULL AND first_seen_at IS NOT NULL AND last_seen_at IS NOT NULL AND expires_at IS NOT NULL OR identity_kind::text = 'registered'::text AND registered_at IS NOT NULL);
ALTER TABLE "public"."identity" ADD CONSTRAINT "identity_check1" CHECK (first_seen_at IS NULL AND last_seen_at IS NULL OR first_seen_at IS NOT NULL AND last_seen_at IS NOT NULL AND last_seen_at >= first_seen_at);
ALTER TABLE "public"."identity" ADD CONSTRAINT "identity_identity_kind_check" CHECK (identity_kind::text = ANY (ARRAY['temporary'::character varying, 'registered'::character varying]::text[]));
ALTER TABLE "public"."identity" ADD CONSTRAINT "identity_revision_check" CHECK (revision > 0);

-- ----------------------------
-- Primary Key structure for table identity
-- ----------------------------
ALTER TABLE "public"."identity" ADD CONSTRAINT "identity_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table identity_link
-- ----------------------------
CREATE INDEX "ix_identity_link_registered" ON "public"."identity_link" USING btree (
  "registered_identity_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);
CREATE UNIQUE INDEX "uk_identity_link_current" ON "public"."identity_link" USING btree (
  "temporary_identity_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE valid_to IS NULL;

-- ----------------------------
-- Checks structure for table identity_link
-- ----------------------------
ALTER TABLE "public"."identity_link" ADD CONSTRAINT "ck_identity_link_revision" CHECK (revision > 0);
ALTER TABLE "public"."identity_link" ADD CONSTRAINT "identity_link_check" CHECK (temporary_identity_id <> registered_identity_id);
ALTER TABLE "public"."identity_link" ADD CONSTRAINT "identity_link_check1" CHECK (valid_to IS NULL OR valid_to >= valid_from);

-- ----------------------------
-- Primary Key structure for table identity_link
-- ----------------------------
ALTER TABLE "public"."identity_link" ADD CONSTRAINT "identity_link_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table input_frame
-- ----------------------------
CREATE INDEX "ix_frame_expiry" ON "public"."input_frame" USING btree (
  "expires_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);
CREATE INDEX "ix_frame_session_time" ON "public"."input_frame" USING btree (
  "stream_session_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "occurred_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST,
  "id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table input_frame
-- ----------------------------
ALTER TABLE "public"."input_frame" ADD CONSTRAINT "input_frame_stream_session_id_frame_seq_key" UNIQUE ("stream_session_id", "frame_seq");

-- ----------------------------
-- Checks structure for table input_frame
-- ----------------------------
ALTER TABLE "public"."input_frame" ADD CONSTRAINT "input_frame_check" CHECK (frame_seq >= 0 AND width > 0 AND height > 0);
ALTER TABLE "public"."input_frame" ADD CONSTRAINT "input_frame_check1" CHECK ((media_asset_id IS NULL) = (media_pts_ms IS NULL));
ALTER TABLE "public"."input_frame" ADD CONSTRAINT "input_frame_media_pts_ms_check" CHECK (media_pts_ms IS NULL OR media_pts_ms >= 0);
ALTER TABLE "public"."input_frame" ADD CONSTRAINT "input_frame_stream_pts_ms_check" CHECK (stream_pts_ms IS NULL OR stream_pts_ms >= 0);
ALTER TABLE "public"."input_frame" ADD CONSTRAINT "input_frame_time_quality_check" CHECK (time_quality::text = ANY (ARRAY['source_clock'::character varying, 'ingest_estimated'::character varying, 'reconciled'::character varying]::text[]));

-- ----------------------------
-- Primary Key structure for table input_frame
-- ----------------------------
ALTER TABLE "public"."input_frame" ADD CONSTRAINT "input_frame_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table legacy_identity_map
-- ----------------------------
CREATE INDEX "ix_legacy_identity" ON "public"."legacy_identity_map" USING btree (
  "identity_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key structure for table legacy_identity_map
-- ----------------------------
ALTER TABLE "public"."legacy_identity_map" ADD CONSTRAINT "legacy_identity_map_pkey" PRIMARY KEY ("legacy_namespace", "legacy_id");

-- ----------------------------
-- Indexes structure for table llm_report
-- ----------------------------
CREATE INDEX "idx_llm_report_episode_id" ON "public"."llm_report" USING btree (
  "episode_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);
CREATE INDEX "idx_llm_report_prompt_type" ON "public"."llm_report" USING btree (
  "prompt_type" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "idx_llm_report_vad_id" ON "public"."llm_report" USING btree (
  "vad_id" "pg_catalog"."int4_ops" ASC NULLS LAST
);
CREATE INDEX "ix_report_expiry" ON "public"."llm_report" USING btree (
  "expires_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table llm_report
-- ----------------------------
ALTER TABLE "public"."llm_report" ADD CONSTRAINT "uk_report_business_subject" UNIQUE ("subject_kind", "subject_id", "report_type");

-- ----------------------------
-- Checks structure for table llm_report
-- ----------------------------
ALTER TABLE "public"."llm_report" ADD CONSTRAINT "ck_report_subject" CHECK (subject_kind IS NULL AND subject_id IS NULL AND report_type IS NULL AND event_id IS NULL AND query_id IS NULL OR subject_kind IS NOT NULL AND subject_id IS NOT NULL AND report_type IS NOT NULL AND (subject_kind::text = 'activity'::text AND episode_id IS NOT NULL AND episode_id = subject_id AND event_id IS NULL AND query_id IS NULL OR subject_kind::text = 'event'::text AND event_id IS NOT NULL AND event_id = subject_id AND episode_id IS NULL AND query_id IS NULL OR subject_kind::text = 'query'::text AND query_id IS NOT NULL AND query_id = subject_id AND episode_id IS NULL AND event_id IS NULL OR subject_kind::text = 'legacy'::text AND subject_id = id AND episode_id IS NULL AND event_id IS NULL AND query_id IS NULL));
ALTER TABLE "public"."llm_report" ADD CONSTRAINT "ck_report_completeness" CHECK (completeness::text = ANY (ARRAY['partial'::character varying, 'complete'::character varying]::text[]));
ALTER TABLE "public"."llm_report" ADD CONSTRAINT "ck_report_revision" CHECK (revision IS NULL OR revision > 0);

-- ----------------------------
-- Primary Key structure for table llm_report
-- ----------------------------
ALTER TABLE "public"."llm_report" ADD CONSTRAINT "llm_report_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table media_asset
-- ----------------------------
CREATE INDEX "idx_media_asset_asset_type" ON "public"."media_asset" USING btree (
  "asset_type" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "idx_media_asset_start_ts" ON "public"."media_asset" USING btree (
  "start_ts" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);
CREATE INDEX "idx_media_asset_stream_id" ON "public"."media_asset" USING btree (
  "stream_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "ix_asset_expiry_state" ON "public"."media_asset" USING btree (
  "expires_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST,
  "state" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "ix_asset_source_time" ON "public"."media_asset" USING btree (
  "source_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "start_ts" "pg_catalog"."timestamptz_ops" ASC NULLS LAST,
  "id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);
CREATE UNIQUE INDEX "uk_asset_producer_key" ON "public"."media_asset" USING btree (
  "producer_key" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
) WHERE producer_key IS NOT NULL;
CREATE UNIQUE INDEX "uk_asset_storage_key" ON "public"."media_asset" USING btree (
  "storage_key" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
) WHERE storage_key IS NOT NULL;

-- ----------------------------
-- Checks structure for table media_asset
-- ----------------------------
ALTER TABLE "public"."media_asset" ADD CONSTRAINT "ck_asset_available_content" CHECK (state::text <> 'available'::text OR storage_key IS NULL OR byte_size IS NOT NULL AND checksum_sha256 IS NOT NULL);
ALTER TABLE "public"."media_asset" ADD CONSTRAINT "ck_asset_hash" CHECK (checksum_sha256 IS NULL OR checksum_sha256 ~ '^[0-9a-f]{64}$'::text);
ALTER TABLE "public"."media_asset" ADD CONSTRAINT "ck_asset_size" CHECK ((byte_size IS NULL OR byte_size >= 0) AND delete_attempts >= 0 AND revision > 0);
ALTER TABLE "public"."media_asset" ADD CONSTRAINT "chk_media_asset_type" CHECK (asset_type = ANY (ARRAY['segment'::text, 'clip'::text, 'snapshot'::text, 'recording'::text, 'crop'::text, 'evidence_clip'::text, 'algorithm_output'::text, 'query_image'::text, 'enrollment_image'::text]));
ALTER TABLE "public"."media_asset" ADD CONSTRAINT "ck_asset_state" CHECK (state::text = ANY (ARRAY['preparing'::character varying, 'available'::character varying, 'unavailable'::character varying, 'missing'::character varying, 'delete_pending'::character varying, 'deleted'::character varying]::text[]));

-- ----------------------------
-- Primary Key structure for table media_asset
-- ----------------------------
ALTER TABLE "public"."media_asset" ADD CONSTRAINT "media_asset_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table outbox_event
-- ----------------------------
CREATE INDEX "ix_outbox_pending" ON "public"."outbox_event" USING btree (
  "next_attempt_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST,
  "id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE state::text = 'pending'::text;

-- ----------------------------
-- Uniques structure for table outbox_event
-- ----------------------------
ALTER TABLE "public"."outbox_event" ADD CONSTRAINT "uk_outbox_aggregate_revision" UNIQUE ("event_type", "aggregate_type", "aggregate_id", "aggregate_revision");

-- ----------------------------
-- Checks structure for table outbox_event
-- ----------------------------
ALTER TABLE "public"."outbox_event" ADD CONSTRAINT "outbox_event_check" CHECK (aggregate_revision > 0 AND attempt_count >= 0);
ALTER TABLE "public"."outbox_event" ADD CONSTRAINT "outbox_event_state_check" CHECK (state::text = ANY (ARRAY['pending'::character varying, 'sent'::character varying, 'dead'::character varying]::text[]));

-- ----------------------------
-- Primary Key structure for table outbox_event
-- ----------------------------
ALTER TABLE "public"."outbox_event" ADD CONSTRAINT "outbox_event_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table processing_coverage
-- ----------------------------
CREATE INDEX "ix_coverage_source_stage_time" ON "public"."processing_coverage" USING btree (
  "source_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "stage" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST,
  "start_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST,
  "end_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table processing_coverage
-- ----------------------------
ALTER TABLE "public"."processing_coverage" ADD CONSTRAINT "uk_coverage_key" UNIQUE ("source_id", "stage", "coverage_key");

-- ----------------------------
-- Checks structure for table processing_coverage
-- ----------------------------
ALTER TABLE "public"."processing_coverage" ADD CONSTRAINT "ck_coverage_revision" CHECK (revision > 0);
ALTER TABLE "public"."processing_coverage" ADD CONSTRAINT "processing_coverage_stage_check" CHECK (stage::text = ANY (ARRAY['input'::character varying, 'recording'::character varying, 'analysis'::character varying, 'registration'::character varying, 'features'::character varying]::text[]));
ALTER TABLE "public"."processing_coverage" ADD CONSTRAINT "processing_coverage_status_check" CHECK (status::text = ANY (ARRAY['complete'::character varying, 'partial'::character varying, 'gap'::character varying, 'unavailable'::character varying]::text[]));
ALTER TABLE "public"."processing_coverage" ADD CONSTRAINT "processing_coverage_check" CHECK (end_at > start_at AND analyzed_frame_count >= 0 AND saved_frame_count >= 0 AND saved_frame_count <= analyzed_frame_count);

-- ----------------------------
-- Primary Key structure for table processing_coverage
-- ----------------------------
ALTER TABLE "public"."processing_coverage" ADD CONSTRAINT "processing_coverage_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table query_candidate
-- ----------------------------
CREATE INDEX "ix_query_candidate_sample" ON "public"."query_candidate" USING btree (
  "sample_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Checks structure for table query_candidate
-- ----------------------------
ALTER TABLE "public"."query_candidate" ADD CONSTRAINT "query_candidate_confidence_check" CHECK (confidence >= 0::double precision AND confidence <= 1::double precision);

-- ----------------------------
-- Primary Key structure for table query_candidate
-- ----------------------------
ALTER TABLE "public"."query_candidate" ADD CONSTRAINT "query_candidate_pkey" PRIMARY KEY ("query_id", "candidate_id");

-- ----------------------------
-- Indexes structure for table query_request
-- ----------------------------
CREATE INDEX "ix_query_owner_time" ON "public"."query_request" USING btree (
  "owner_user_id" "pg_catalog"."int8_ops" ASC NULLS LAST,
  "created_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST,
  "id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Checks structure for table query_request
-- ----------------------------
ALTER TABLE "public"."query_request" ADD CONSTRAINT "ck_query_stage2_session" CHECK (session_id IS NULL);
ALTER TABLE "public"."query_request" ADD CONSTRAINT "query_request_check" CHECK (end_at IS NULL OR start_at IS NULL OR end_at > start_at);
ALTER TABLE "public"."query_request" ADD CONSTRAINT "ck_query_request_revision" CHECK (revision > 0);
ALTER TABLE "public"."query_request" ADD CONSTRAINT "query_request_state_check" CHECK (state::text = ANY (ARRAY['pending'::character varying, 'running'::character varying, 'waiting_input'::character varying, 'succeeded'::character varying, 'partial'::character varying, 'failed'::character varying, 'cancelled'::character varying, 'expired'::character varying]::text[]));

-- ----------------------------
-- Primary Key structure for table query_request
-- ----------------------------
ALTER TABLE "public"."query_request" ADD CONSTRAINT "query_request_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table reid_match
-- ----------------------------
CREATE INDEX "idx_reid_match_tracklet_id" ON "public"."reid_match" USING btree (
  "tracklet_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);
CREATE INDEX "idx_reid_match_ts" ON "public"."reid_match" USING btree (
  "ts" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);

-- ----------------------------
-- Checks structure for table reid_match
-- ----------------------------
ALTER TABLE "public"."reid_match" ADD CONSTRAINT "ck_reid_match_target_exclusive" CHECK (NOT (target_id IS NOT NULL AND stranger_target_id IS NOT NULL));

-- ----------------------------
-- Primary Key structure for table reid_match
-- ----------------------------
ALTER TABLE "public"."reid_match" ADD CONSTRAINT "reid_match_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table reid_target
-- ----------------------------
CREATE INDEX "idx_reid_target_is_active" ON "public"."reid_target" USING btree (
  "is_active" "pg_catalog"."bool_ops" ASC NULLS LAST
);
CREATE INDEX "idx_reid_target_name" ON "public"."reid_target" USING btree (
  "name" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key structure for table reid_target
-- ----------------------------
ALTER TABLE "public"."reid_target" ADD CONSTRAINT "reid_target_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table reid_target_vit
-- ----------------------------
CREATE INDEX "idx_reid_target_vit_is_active" ON "public"."reid_target_vit" USING btree (
  "is_active" "pg_catalog"."bool_ops" ASC NULLS LAST
);
CREATE INDEX "idx_reid_target_vit_name" ON "public"."reid_target_vit" USING btree (
  "name" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key structure for table reid_target_vit
-- ----------------------------
ALTER TABLE "public"."reid_target_vit" ADD CONSTRAINT "reid_target_vit_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table report_evidence_link
-- ----------------------------
CREATE INDEX "ix_report_evidence_reverse" ON "public"."report_evidence_link" USING btree (
  "evidence_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table report_evidence_link
-- ----------------------------
ALTER TABLE "public"."report_evidence_link" ADD CONSTRAINT "report_evidence_link_report_id_ordinal_key" UNIQUE ("report_id", "ordinal");

-- ----------------------------
-- Checks structure for table report_evidence_link
-- ----------------------------
ALTER TABLE "public"."report_evidence_link" ADD CONSTRAINT "report_evidence_link_check" CHECK (report_revision > 0 AND ordinal >= 0);

-- ----------------------------
-- Primary Key structure for table report_evidence_link
-- ----------------------------
ALTER TABLE "public"."report_evidence_link" ADD CONSTRAINT "report_evidence_link_pkey" PRIMARY KEY ("report_id", "evidence_id");

-- ----------------------------
-- Indexes structure for table request_deduplication
-- ----------------------------
CREATE INDEX "ix_dedup_expiry" ON "public"."request_deduplication" USING btree (
  "expires_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);

-- ----------------------------
-- Checks structure for table request_deduplication
-- ----------------------------
ALTER TABLE "public"."request_deduplication" ADD CONSTRAINT "request_deduplication_state_check" CHECK (state::text = ANY (ARRAY['accepted'::character varying, 'completed'::character varying, 'failed'::character varying]::text[]));

-- ----------------------------
-- Primary Key structure for table request_deduplication
-- ----------------------------
ALTER TABLE "public"."request_deduplication" ADD CONSTRAINT "request_deduplication_pkey" PRIMARY KEY ("actor_key", "operation", "request_id");

-- ----------------------------
-- Indexes structure for table result_selection
-- ----------------------------
CREATE INDEX "ix_selection_set" ON "public"."result_selection" USING btree (
  "result_set_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);
CREATE INDEX "result_selection_source_id_capability_code_tstzrange_excl" ON "public"."result_selection" USING gist (
  "source_id" "public"."gist_uuid_ops",
  "capability_code" COLLATE "pg_catalog"."default" "public"."gist_text_ops",
  tstzrange(range_start, range_end, '[)'::text) "pg_catalog"."range_ops"
);

-- ----------------------------
-- Checks structure for table result_selection
-- ----------------------------
ALTER TABLE "public"."result_selection" ADD CONSTRAINT "result_selection_check" CHECK (range_end > range_start AND generation > 0 AND revision > 0);

-- ----------------------------
-- Excludes structure for table result_selection
-- ----------------------------
ALTER TABLE "public"."result_selection" ADD CONSTRAINT "result_selection_source_id_capability_code_tstzrange_excl" EXCLUDE USING gist ("source_id" "public"."gist_uuid_ops" WITH "pg_catalog".=, "capability_code" "public"."gist_text_ops" WITH "pg_catalog".=, "tstzrange(range_start, range_end, '[)'::text)" "pg_catalog"."range_ops" WITH "pg_catalog".&&);

-- ----------------------------
-- Primary Key structure for table result_selection
-- ----------------------------
ALTER TABLE "public"."result_selection" ADD CONSTRAINT "result_selection_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table result_set
-- ----------------------------
CREATE INDEX "ix_result_set_device_task" ON "public"."result_set" USING btree (
  "device_task_binding_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE device_task_binding_id IS NOT NULL;
CREATE INDEX "ix_result_set_run" ON "public"."result_set" USING btree (
  "run_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table result_set
-- ----------------------------
ALTER TABLE "public"."result_set" ADD CONSTRAINT "result_set_run_id_set_key_key" UNIQUE ("run_id", "set_key");
ALTER TABLE "public"."result_set" ADD CONSTRAINT "result_set_id_source_id_capability_code_key" UNIQUE ("id", "source_id", "capability_code");

-- ----------------------------
-- Checks structure for table result_set
-- ----------------------------
ALTER TABLE "public"."result_set" ADD CONSTRAINT "result_set_check" CHECK (source_id IS NOT NULL OR input_asset_id IS NOT NULL);
ALTER TABLE "public"."result_set" ADD CONSTRAINT "result_set_check1" CHECK (stream_session_id IS NULL OR source_id IS NOT NULL);
ALTER TABLE "public"."result_set" ADD CONSTRAINT "result_set_generation_check" CHECK (generation > 0);
ALTER TABLE "public"."result_set" ADD CONSTRAINT "result_set_state_check" CHECK (state::text = ANY (ARRAY['collecting'::character varying, 'ready'::character varying, 'partial'::character varying, 'failed'::character varying]::text[]));

-- ----------------------------
-- Primary Key structure for table result_set
-- ----------------------------
ALTER TABLE "public"."result_set" ADD CONSTRAINT "result_set_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Checks structure for table result_type
-- ----------------------------
ALTER TABLE "public"."result_type" ADD CONSTRAINT "result_type_json_schema_check" CHECK (jsonb_typeof(json_schema) = 'object'::text);
ALTER TABLE "public"."result_type" ADD CONSTRAINT "result_type_max_inline_bytes_check" CHECK (max_inline_bytes > 0);

-- ----------------------------
-- Primary Key structure for table result_type
-- ----------------------------
ALTER TABLE "public"."result_type" ADD CONSTRAINT "result_type_pkey" PRIMARY KEY ("type_code", "schema_version");

-- ----------------------------
-- Indexes structure for table sample
-- ----------------------------
CREATE INDEX "ix_sample_asset" ON "public"."sample" USING btree (
  "asset_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);
CREATE INDEX "ix_sample_expiry" ON "public"."sample" USING btree (
  "expires_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);
CREATE INDEX "ix_sample_frame" ON "public"."sample" USING btree (
  "input_frame_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE input_frame_id IS NOT NULL;
CREATE INDEX "ix_sample_identity" ON "public"."sample" USING btree (
  "identity_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "purpose" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "ix_sample_track_time" ON "public"."sample" USING btree (
  "tracklet_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "occurred_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);

-- ----------------------------
-- Checks structure for table sample
-- ----------------------------
ALTER TABLE "public"."sample" ADD CONSTRAINT "sample_check" CHECK (purpose::text = 'enrollment'::text OR expires_at IS NOT NULL);
ALTER TABLE "public"."sample" ADD CONSTRAINT "sample_purpose_check" CHECK (purpose::text = ANY (ARRAY['history'::character varying, 'enrollment'::character varying, 'query'::character varying, 'evidence'::character varying]::text[]));

-- ----------------------------
-- Primary Key structure for table sample
-- ----------------------------
ALTER TABLE "public"."sample" ADD CONSTRAINT "sample_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table search_hit
-- ----------------------------
CREATE INDEX "ix_search_hit_identity" ON "public"."search_hit" USING btree (
  "identity_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "query_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);
CREATE INDEX "ix_search_hit_sample" ON "public"."search_hit" USING btree (
  "sample_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table search_hit
-- ----------------------------
ALTER TABLE "public"."search_hit" ADD CONSTRAINT "search_hit_query_id_rank_no_key" UNIQUE ("query_id", "rank_no");

-- ----------------------------
-- Checks structure for table search_hit
-- ----------------------------
ALTER TABLE "public"."search_hit" ADD CONSTRAINT "search_hit_hit_kind_check" CHECK (hit_kind::text = ANY (ARRAY['gallery'::character varying, 'historical'::character varying]::text[]));
ALTER TABLE "public"."search_hit" ADD CONSTRAINT "search_hit_rank_no_check" CHECK (rank_no > 0);

-- ----------------------------
-- Primary Key structure for table search_hit
-- ----------------------------
ALTER TABLE "public"."search_hit" ADD CONSTRAINT "search_hit_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table stranger_target
-- ----------------------------
CREATE INDEX "idx_stranger_target_is_active" ON "public"."stranger_target" USING btree (
  "is_active" "pg_catalog"."bool_ops" ASC NULLS LAST
);
CREATE INDEX "idx_stranger_target_status" ON "public"."stranger_target" USING btree (
  "status" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table stranger_target
-- ----------------------------
ALTER TABLE "public"."stranger_target" ADD CONSTRAINT "stranger_target_code_key" UNIQUE ("code");

-- ----------------------------
-- Primary Key structure for table stranger_target
-- ----------------------------
ALTER TABLE "public"."stranger_target" ADD CONSTRAINT "stranger_target_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table stream_session
-- ----------------------------
CREATE INDEX "ix_stream_session_source_time" ON "public"."stream_session" USING btree (
  "source_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "started_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table stream_session
-- ----------------------------
ALTER TABLE "public"."stream_session" ADD CONSTRAINT "stream_session_source_id_session_key_key" UNIQUE ("source_id", "session_key");

-- ----------------------------
-- Checks structure for table stream_session
-- ----------------------------
ALTER TABLE "public"."stream_session" ADD CONSTRAINT "stream_session_check" CHECK (source_width > 0 AND source_height > 0);
ALTER TABLE "public"."stream_session" ADD CONSTRAINT "stream_session_check1" CHECK (ended_at IS NULL OR ended_at >= started_at);
ALTER TABLE "public"."stream_session" ADD CONSTRAINT "stream_session_check2" CHECK (state::text = 'open'::text AND ended_at IS NULL OR (state::text = ANY (ARRAY['closed'::character varying, 'interrupted'::character varying]::text[])) AND ended_at IS NOT NULL);
ALTER TABLE "public"."stream_session" ADD CONSTRAINT "stream_session_state_check" CHECK (state::text = ANY (ARRAY['open'::character varying, 'closed'::character varying, 'interrupted'::character varying]::text[]));
ALTER TABLE "public"."stream_session" ADD CONSTRAINT "stream_session_time_basis_check" CHECK (time_basis::text = ANY (ARRAY['source_clock'::character varying, 'ingest_clock'::character varying]::text[]));

-- ----------------------------
-- Primary Key structure for table stream_session
-- ----------------------------
ALTER TABLE "public"."stream_session" ADD CONSTRAINT "stream_session_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table task_attempt
-- ----------------------------
CREATE INDEX "ix_attempt_recovery" ON "public"."task_attempt" USING btree (
  "state" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST,
  "lease_until" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table task_attempt
-- ----------------------------
ALTER TABLE "public"."task_attempt" ADD CONSTRAINT "task_attempt_task_id_generation_key" UNIQUE ("task_id", "generation");
ALTER TABLE "public"."task_attempt" ADD CONSTRAINT "task_attempt_task_id_run_id_key" UNIQUE ("task_id", "run_id");
ALTER TABLE "public"."task_attempt" ADD CONSTRAINT "task_attempt_legacy_run_id_key" UNIQUE ("legacy_run_id");

-- ----------------------------
-- Checks structure for table task_attempt
-- ----------------------------
ALTER TABLE "public"."task_attempt" ADD CONSTRAINT "task_attempt_generation_check" CHECK (generation > 0);
ALTER TABLE "public"."task_attempt" ADD CONSTRAINT "task_attempt_state_check" CHECK (state::text = ANY (ARRAY['pending'::character varying, 'running'::character varying, 'waiting_input'::character varying, 'succeeded'::character varying, 'partial'::character varying, 'failed'::character varying, 'cancelled'::character varying, 'expired'::character varying]::text[]));
ALTER TABLE "public"."task_attempt" ADD CONSTRAINT "task_attempt_check" CHECK (finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at);

-- ----------------------------
-- Primary Key structure for table task_attempt
-- ----------------------------
ALTER TABLE "public"."task_attempt" ADD CONSTRAINT "task_attempt_pkey" PRIMARY KEY ("run_id");

-- ----------------------------
-- Indexes structure for table task_output
-- ----------------------------
CREATE INDEX "ix_task_output_page" ON "public"."task_output" USING btree (
  "task_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table task_output
-- ----------------------------
ALTER TABLE "public"."task_output" ADD CONSTRAINT "task_output_run_id_producer_result_key_key" UNIQUE ("run_id", "producer_result_key");

-- ----------------------------
-- Checks structure for table task_output
-- ----------------------------
ALTER TABLE "public"."task_output" ADD CONSTRAINT "task_output_producer_result_key_check" CHECK (btrim(producer_result_key::text) <> ''::text);
ALTER TABLE "public"."task_output" ADD CONSTRAINT "task_output_payload_digest_check" CHECK (payload_digest ~ '^[0-9a-f]{64}$'::text);

-- ----------------------------
-- Primary Key structure for table task_output
-- ----------------------------
ALTER TABLE "public"."task_output" ADD CONSTRAINT "task_output_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table track_identity_assignment
-- ----------------------------
CREATE INDEX "ix_assignment_identity" ON "public"."track_identity_assignment" USING btree (
  "identity_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "tracklet_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);
CREATE UNIQUE INDEX "uk_assignment_current" ON "public"."track_identity_assignment" USING btree (
  "tracklet_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE valid_to IS NULL;

-- ----------------------------
-- Checks structure for table track_identity_assignment
-- ----------------------------
ALTER TABLE "public"."track_identity_assignment" ADD CONSTRAINT "ck_track_identity_assignment_revision" CHECK (revision > 0);
ALTER TABLE "public"."track_identity_assignment" ADD CONSTRAINT "track_identity_assignment_check" CHECK (valid_to IS NULL OR valid_to >= valid_from);

-- ----------------------------
-- Primary Key structure for table track_identity_assignment
-- ----------------------------
ALTER TABLE "public"."track_identity_assignment" ADD CONSTRAINT "track_identity_assignment_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table tracking_context
-- ----------------------------
CREATE INDEX "ix_context_session" ON "public"."tracking_context" USING btree (
  "stream_session_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "started_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table tracking_context
-- ----------------------------
ALTER TABLE "public"."tracking_context" ADD CONSTRAINT "tracking_context_run_id_context_key_key" UNIQUE ("run_id", "context_key");

-- ----------------------------
-- Checks structure for table tracking_context
-- ----------------------------
ALTER TABLE "public"."tracking_context" ADD CONSTRAINT "tracking_context_check" CHECK (source_width > 0 AND source_height > 0);
ALTER TABLE "public"."tracking_context" ADD CONSTRAINT "tracking_context_check1" CHECK (ended_at IS NULL OR ended_at >= started_at);

-- ----------------------------
-- Primary Key structure for table tracking_context
-- ----------------------------
ALTER TABLE "public"."tracking_context" ADD CONSTRAINT "tracking_context_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table tracklet
-- ----------------------------
CREATE INDEX "idx_tracklet_gallery_target_id" ON "public"."tracklet" USING btree (
  "gallery_target_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);
CREATE INDEX "idx_tracklet_start_ts" ON "public"."tracklet" USING btree (
  "start_ts" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);
CREATE INDEX "idx_tracklet_stranger_target_id" ON "public"."tracklet" USING btree (
  "stranger_target_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);
CREATE INDEX "idx_tracklet_stream_id" ON "public"."tracklet" USING btree (
  "stream_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "ix_track_source_observed" ON "public"."tracklet" USING btree (
  "source_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "first_observed_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST,
  "last_observed_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);
CREATE UNIQUE INDEX "uk_track_context_local" ON "public"."tracklet" USING btree (
  "tracking_context_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "local_track_id" "pg_catalog"."int8_ops" ASC NULLS LAST
) WHERE tracking_context_id IS NOT NULL;

-- ----------------------------
-- Checks structure for table tracklet
-- ----------------------------
ALTER TABLE "public"."tracklet" ADD CONSTRAINT "ck_tracklet_context_pair" CHECK ((tracking_context_id IS NULL) = (local_track_id IS NULL));
ALTER TABLE "public"."tracklet" ADD CONSTRAINT "ck_tracklet_end_reason" CHECK (end_reason IS NULL OR (end_reason::text = ANY (ARRAY['normal'::character varying, 'observation_interrupted'::character varying, 'cancelled'::character varying]::text[])));
ALTER TABLE "public"."tracklet" ADD CONSTRAINT "ck_tracklet_local_id" CHECK (local_track_id IS NULL OR local_track_id >= 0);
ALTER TABLE "public"."tracklet" ADD CONSTRAINT "ck_tracklet_observed_time" CHECK (first_observed_at IS NULL AND last_observed_at IS NULL OR first_observed_at IS NOT NULL AND last_observed_at IS NOT NULL AND last_observed_at >= first_observed_at);
ALTER TABLE "public"."tracklet" ADD CONSTRAINT "ck_tracklet_target_exclusive" CHECK (NOT (gallery_target_id IS NOT NULL AND stranger_target_id IS NOT NULL));
ALTER TABLE "public"."tracklet" ADD CONSTRAINT "ck_tracklet_canonical" CHECK (canonical_tracklet_id IS NULL OR canonical_tracklet_id <> id);

-- ----------------------------
-- Primary Key structure for table tracklet
-- ----------------------------
ALTER TABLE "public"."tracklet" ADD CONSTRAINT "tracklet_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Checks structure for table unified_event
-- ----------------------------
ALTER TABLE "public"."unified_event" ADD CONSTRAINT "unified_event_data_origin_check" CHECK (data_origin = ANY (ARRAY['production'::text, 'demo'::text, 'synthetic'::text, 'replay'::text, 'historical_import'::text, 'unknown'::text]));
ALTER TABLE "public"."unified_event" ADD CONSTRAINT "unified_event_ended_time" CHECK (status <> 'ended'::text OR end_time IS NOT NULL);
ALTER TABLE "public"."unified_event" ADD CONSTRAINT "unified_event_event_type_check" CHECK (length(btrim(event_type)) > 0);
ALTER TABLE "public"."unified_event" ADD CONSTRAINT "unified_event_evidence_check" CHECK (jsonb_typeof(evidence) = 'array'::text);
ALTER TABLE "public"."unified_event" ADD CONSTRAINT "unified_event_location_check" CHECK (jsonb_typeof(location) = 'object'::text);
ALTER TABLE "public"."unified_event" ADD CONSTRAINT "unified_event_reports_check" CHECK (jsonb_typeof(reports) = 'array'::text);
ALTER TABLE "public"."unified_event" ADD CONSTRAINT "unified_event_risk_level_check" CHECK (risk_level = ANY (ARRAY['unknown'::text, 'info'::text, 'low'::text, 'medium'::text, 'high'::text, 'critical'::text]));
ALTER TABLE "public"."unified_event" ADD CONSTRAINT "unified_event_source_refs_check" CHECK (jsonb_typeof(source_refs) = 'array'::text AND jsonb_array_length(source_refs) > 0);
ALTER TABLE "public"."unified_event" ADD CONSTRAINT "unified_event_sources_check" CHECK (cardinality(sources) > 0 AND array_position(sources, NULL::text) IS NULL);
ALTER TABLE "public"."unified_event" ADD CONSTRAINT "unified_event_status_check" CHECK (status = ANY (ARRAY['active'::text, 'ended'::text, 'point'::text, 'unknown'::text]));
ALTER TABLE "public"."unified_event" ADD CONSTRAINT "unified_event_stream_id_check" CHECK (stream_id IS NULL OR length(btrim(stream_id)) > 0);
ALTER TABLE "public"."unified_event" ADD CONSTRAINT "unified_event_time_order" CHECK (end_time IS NULL OR start_time IS NOT NULL AND end_time >= start_time);
ALTER TABLE "public"."unified_event" ADD CONSTRAINT "unified_event_active_end" CHECK (status <> 'active'::text OR end_time IS NULL);
ALTER TABLE "public"."unified_event" ADD CONSTRAINT "unified_event_title_check" CHECK (length(btrim(title)) > 0);

-- ----------------------------
-- Primary Key structure for table unified_event
-- ----------------------------
ALTER TABLE "public"."unified_event" ADD CONSTRAINT "unified_event_pkey" PRIMARY KEY ("event_id");

-- ----------------------------
-- Indexes structure for table vad
-- ----------------------------
CREATE INDEX "idx_vad_created_at" ON "public"."vad" USING btree (
  "created_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);
CREATE INDEX "idx_vad_media_asset_id" ON "public"."vad" USING btree (
  "media_asset_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);
CREATE INDEX "idx_vad_stream_id" ON "public"."vad" USING btree (
  "stream_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key structure for table vad
-- ----------------------------
ALTER TABLE "public"."vad" ADD CONSTRAINT "vad_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Foreign Keys structure for table algorithm_result
-- ----------------------------
ALTER TABLE "public"."algorithm_result" ADD CONSTRAINT "fk_ar_asset" FOREIGN KEY ("payload_asset_id") REFERENCES "public"."media_asset" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."algorithm_result" ADD CONSTRAINT "fk_ar_frame" FOREIGN KEY ("input_frame_id") REFERENCES "public"."input_frame" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."algorithm_result" ADD CONSTRAINT "fk_ar_set" FOREIGN KEY ("result_set_id") REFERENCES "public"."result_set" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."algorithm_result" ADD CONSTRAINT "fk_ar_track" FOREIGN KEY ("tracklet_id") REFERENCES "public"."tracklet" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."algorithm_result" ADD CONSTRAINT "fk_ar_type" FOREIGN KEY ("result_type", "schema_version") REFERENCES "public"."result_type" ("type_code", "schema_version") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table analysis_frame
-- ----------------------------
ALTER TABLE "public"."analysis_frame" ADD CONSTRAINT "fk_af_input" FOREIGN KEY ("input_frame_id") REFERENCES "public"."input_frame" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."analysis_frame" ADD CONSTRAINT "fk_af_set" FOREIGN KEY ("result_set_id") REFERENCES "public"."result_set" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table asset_reference
-- ----------------------------
ALTER TABLE "public"."asset_reference" ADD CONSTRAINT "fk_asset_ref_asset" FOREIGN KEY ("asset_id") REFERENCES "public"."media_asset" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."asset_reference" ADD CONSTRAINT "fk_asset_ref_device_feedback" FOREIGN KEY ("device_task_feedback_id") REFERENCES "public"."device_task_feedback" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."asset_reference" ADD CONSTRAINT "fk_asset_ref_evidence" FOREIGN KEY ("evidence_id") REFERENCES "public"."evidence_reference" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."asset_reference" ADD CONSTRAINT "fk_asset_ref_identity" FOREIGN KEY ("identity_id") REFERENCES "public"."identity" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."asset_reference" ADD CONSTRAINT "fk_asset_ref_query" FOREIGN KEY ("query_id") REFERENCES "public"."query_request" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."asset_reference" ADD CONSTRAINT "fk_asset_ref_result" FOREIGN KEY ("result_id") REFERENCES "public"."algorithm_result" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."asset_reference" ADD CONSTRAINT "fk_asset_ref_sample" FOREIGN KEY ("sample_id") REFERENCES "public"."sample" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table business_event
-- ----------------------------
ALTER TABLE "public"."business_event" ADD CONSTRAINT "fk_event_run" FOREIGN KEY ("run_id") REFERENCES "public"."task_attempt" ("run_id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."business_event" ADD CONSTRAINT "fk_event_source" FOREIGN KEY ("source_id") REFERENCES "public"."camera" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."business_event" ADD CONSTRAINT "fk_event_vad" FOREIGN KEY ("legacy_vad_id") REFERENCES "public"."vad" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table business_task
-- ----------------------------
ALTER TABLE "public"."business_task" ADD CONSTRAINT "fk_task_cap" FOREIGN KEY ("capability_code") REFERENCES "public"."capability_definition" ("capability_code") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."business_task" ADD CONSTRAINT "fk_task_current_run" FOREIGN KEY ("task_id", "current_run_id") REFERENCES "public"."task_attempt" ("task_id", "run_id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table camera
-- ----------------------------
ALTER TABLE "public"."camera" ADD CONSTRAINT "fk_camera_device" FOREIGN KEY ("device_id") REFERENCES "public"."device_registry" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table capability_instance
-- ----------------------------
ALTER TABLE "public"."capability_instance" ADD CONSTRAINT "fk_instance_cap" FOREIGN KEY ("capability_code") REFERENCES "public"."capability_definition" ("capability_code") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table detection_observation
-- ----------------------------
ALTER TABLE "public"."detection_observation" ADD CONSTRAINT "fk_obs_frame" FOREIGN KEY ("analysis_frame_id") REFERENCES "public"."analysis_frame" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."detection_observation" ADD CONSTRAINT "fk_obs_track" FOREIGN KEY ("tracklet_id") REFERENCES "public"."tracklet" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table device_registry
-- ----------------------------
ALTER TABLE "public"."device_registry" ADD CONSTRAINT "fk_device_registry_parent" FOREIGN KEY ("parent_device_id") REFERENCES "public"."device_registry" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table device_state_observation
-- ----------------------------
ALTER TABLE "public"."device_state_observation" ADD CONSTRAINT "fk_device_state_attempt" FOREIGN KEY ("task_id", "run_id") REFERENCES "public"."task_attempt" ("task_id", "run_id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."device_state_observation" ADD CONSTRAINT "fk_device_state_device" FOREIGN KEY ("device_id") REFERENCES "public"."device_registry" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table device_task_binding
-- ----------------------------
ALTER TABLE "public"."device_task_binding" ADD CONSTRAINT "fk_device_task_attempt" FOREIGN KEY ("task_id", "run_id") REFERENCES "public"."task_attempt" ("task_id", "run_id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."device_task_binding" ADD CONSTRAINT "fk_device_task_device" FOREIGN KEY ("device_id") REFERENCES "public"."device_registry" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table device_task_feedback
-- ----------------------------
ALTER TABLE "public"."device_task_feedback" ADD CONSTRAINT "fk_device_feedback_binding" FOREIGN KEY ("binding_id") REFERENCES "public"."device_task_binding" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table episode
-- ----------------------------
ALTER TABLE "public"."episode" ADD CONSTRAINT "fk_episode_identity" FOREIGN KEY ("identity_id") REFERENCES "public"."identity" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table event_object_link
-- ----------------------------
ALTER TABLE "public"."event_object_link" ADD CONSTRAINT "fk_event_object_event" FOREIGN KEY ("event_id") REFERENCES "public"."business_event" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."event_object_link" ADD CONSTRAINT "fk_event_object_identity" FOREIGN KEY ("identity_id") REFERENCES "public"."identity" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."event_object_link" ADD CONSTRAINT "fk_event_object_sample" FOREIGN KEY ("sample_id") REFERENCES "public"."sample" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."event_object_link" ADD CONSTRAINT "fk_event_object_track" FOREIGN KEY ("tracklet_id") REFERENCES "public"."tracklet" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table evidence_reference
-- ----------------------------
ALTER TABLE "public"."evidence_reference" ADD CONSTRAINT "fk_evidence_activity" FOREIGN KEY ("activity_id") REFERENCES "public"."episode" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."evidence_reference" ADD CONSTRAINT "fk_evidence_asset" FOREIGN KEY ("asset_id") REFERENCES "public"."media_asset" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."evidence_reference" ADD CONSTRAINT "fk_evidence_event" FOREIGN KEY ("event_id") REFERENCES "public"."business_event" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."evidence_reference" ADD CONSTRAINT "fk_evidence_result" FOREIGN KEY ("original_result_id") REFERENCES "public"."algorithm_result" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."evidence_reference" ADD CONSTRAINT "fk_evidence_source" FOREIGN KEY ("source_id") REFERENCES "public"."camera" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."evidence_reference" ADD CONSTRAINT "fk_evidence_track" FOREIGN KEY ("original_tracklet_id") REFERENCES "public"."tracklet" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table feature
-- ----------------------------
ALTER TABLE "public"."feature" ADD CONSTRAINT "fk_feature_identity" FOREIGN KEY ("identity_id") REFERENCES "public"."identity" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."feature" ADD CONSTRAINT "fk_feature_run" FOREIGN KEY ("run_id") REFERENCES "public"."task_attempt" ("run_id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."feature" ADD CONSTRAINT "fk_feature_sample" FOREIGN KEY ("sample_id") REFERENCES "public"."sample" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."feature" ADD CONSTRAINT "fk_feature_space" FOREIGN KEY ("feature_space_id", "dimensions") REFERENCES "public"."feature_space" ("id", "dimensions") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."feature" ADD CONSTRAINT "fk_feature_track" FOREIGN KEY ("tracklet_id") REFERENCES "public"."tracklet" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table feature_contribution
-- ----------------------------
ALTER TABLE "public"."feature_contribution" ADD CONSTRAINT "fk_contrib_feature" FOREIGN KEY ("feature_id") REFERENCES "public"."feature" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."feature_contribution" ADD CONSTRAINT "fk_contrib_sample" FOREIGN KEY ("sample_id") REFERENCES "public"."sample" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."feature_contribution" ADD CONSTRAINT "fk_contrib_source_feature" FOREIGN KEY ("source_feature_id") REFERENCES "public"."feature" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table identity_link
-- ----------------------------
ALTER TABLE "public"."identity_link" ADD CONSTRAINT "fk_il_reg" FOREIGN KEY ("registered_identity_id") REFERENCES "public"."identity" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."identity_link" ADD CONSTRAINT "fk_il_run" FOREIGN KEY ("run_id") REFERENCES "public"."task_attempt" ("run_id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."identity_link" ADD CONSTRAINT "fk_il_temp" FOREIGN KEY ("temporary_identity_id") REFERENCES "public"."identity" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table input_frame
-- ----------------------------
ALTER TABLE "public"."input_frame" ADD CONSTRAINT "fk_frame_media" FOREIGN KEY ("media_asset_id") REFERENCES "public"."media_asset" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."input_frame" ADD CONSTRAINT "fk_frame_session" FOREIGN KEY ("stream_session_id") REFERENCES "public"."stream_session" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table legacy_identity_map
-- ----------------------------
ALTER TABLE "public"."legacy_identity_map" ADD CONSTRAINT "fk_lim_identity" FOREIGN KEY ("identity_id") REFERENCES "public"."identity" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."legacy_identity_map" ADD CONSTRAINT "fk_lim_sample" FOREIGN KEY ("sample_id") REFERENCES "public"."sample" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."legacy_identity_map" ADD CONSTRAINT "fk_lim_space" FOREIGN KEY ("feature_space_id") REFERENCES "public"."feature_space" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table llm_report
-- ----------------------------
ALTER TABLE "public"."llm_report" ADD CONSTRAINT "fk_report_event" FOREIGN KEY ("event_id") REFERENCES "public"."business_event" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."llm_report" ADD CONSTRAINT "fk_report_query" FOREIGN KEY ("query_id") REFERENCES "public"."query_request" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."llm_report" ADD CONSTRAINT "fk_report_run" FOREIGN KEY ("run_id") REFERENCES "public"."task_attempt" ("run_id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."llm_report" ADD CONSTRAINT "fk_report_task" FOREIGN KEY ("task_id") REFERENCES "public"."business_task" ("task_id") ON DELETE SET NULL ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table media_asset
-- ----------------------------
ALTER TABLE "public"."media_asset" ADD CONSTRAINT "fk_asset_session" FOREIGN KEY ("stream_session_id") REFERENCES "public"."stream_session" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."media_asset" ADD CONSTRAINT "fk_asset_source" FOREIGN KEY ("source_id") REFERENCES "public"."camera" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table processing_coverage
-- ----------------------------
ALTER TABLE "public"."processing_coverage" ADD CONSTRAINT "fk_cov_run" FOREIGN KEY ("run_id") REFERENCES "public"."task_attempt" ("run_id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."processing_coverage" ADD CONSTRAINT "fk_cov_session" FOREIGN KEY ("stream_session_id") REFERENCES "public"."stream_session" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."processing_coverage" ADD CONSTRAINT "fk_cov_set" FOREIGN KEY ("result_set_id") REFERENCES "public"."result_set" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."processing_coverage" ADD CONSTRAINT "fk_cov_source" FOREIGN KEY ("source_id") REFERENCES "public"."camera" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table query_candidate
-- ----------------------------
ALTER TABLE "public"."query_candidate" ADD CONSTRAINT "fk_candidate_query" FOREIGN KEY ("query_id") REFERENCES "public"."query_request" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."query_candidate" ADD CONSTRAINT "fk_candidate_sample" FOREIGN KEY ("sample_id") REFERENCES "public"."sample" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table query_request
-- ----------------------------
ALTER TABLE "public"."query_request" ADD CONSTRAINT "fk_query_asset" FOREIGN KEY ("input_asset_id") REFERENCES "public"."media_asset" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."query_request" ADD CONSTRAINT "fk_query_identity" FOREIGN KEY ("identity_id") REFERENCES "public"."identity" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."query_request" ADD CONSTRAINT "fk_query_sample" FOREIGN KEY ("input_sample_id") REFERENCES "public"."sample" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."query_request" ADD CONSTRAINT "fk_query_selected_candidate" FOREIGN KEY ("id", "selected_candidate_id") REFERENCES "public"."query_candidate" ("query_id", "candidate_id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."query_request" ADD CONSTRAINT "fk_query_space" FOREIGN KEY ("feature_space_id") REFERENCES "public"."feature_space" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."query_request" ADD CONSTRAINT "fk_query_task" FOREIGN KEY ("task_id") REFERENCES "public"."business_task" ("task_id") ON DELETE SET NULL ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table report_evidence_link
-- ----------------------------
ALTER TABLE "public"."report_evidence_link" ADD CONSTRAINT "fk_report_evidence_evidence" FOREIGN KEY ("evidence_id") REFERENCES "public"."evidence_reference" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."report_evidence_link" ADD CONSTRAINT "fk_report_evidence_report" FOREIGN KEY ("report_id") REFERENCES "public"."llm_report" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table request_deduplication
-- ----------------------------
ALTER TABLE "public"."request_deduplication" ADD CONSTRAINT "fk_dedup_task" FOREIGN KEY ("task_id") REFERENCES "public"."business_task" ("task_id") ON DELETE SET NULL ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table result_selection
-- ----------------------------
ALTER TABLE "public"."result_selection" ADD CONSTRAINT "fk_selection_set" FOREIGN KEY ("result_set_id", "source_id", "capability_code") REFERENCES "public"."result_set" ("id", "source_id", "capability_code") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table result_set
-- ----------------------------
ALTER TABLE "public"."result_set" ADD CONSTRAINT "fk_result_set_device_task" FOREIGN KEY ("device_task_binding_id") REFERENCES "public"."device_task_binding" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."result_set" ADD CONSTRAINT "fk_rs_cap" FOREIGN KEY ("capability_code") REFERENCES "public"."capability_definition" ("capability_code") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."result_set" ADD CONSTRAINT "fk_rs_input_asset" FOREIGN KEY ("input_asset_id") REFERENCES "public"."media_asset" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."result_set" ADD CONSTRAINT "fk_rs_run" FOREIGN KEY ("run_id") REFERENCES "public"."task_attempt" ("run_id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."result_set" ADD CONSTRAINT "fk_rs_session" FOREIGN KEY ("stream_session_id") REFERENCES "public"."stream_session" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."result_set" ADD CONSTRAINT "fk_rs_source" FOREIGN KEY ("source_id") REFERENCES "public"."camera" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table sample
-- ----------------------------
ALTER TABLE "public"."sample" ADD CONSTRAINT "fk_sample_asset" FOREIGN KEY ("asset_id") REFERENCES "public"."media_asset" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."sample" ADD CONSTRAINT "fk_sample_frame" FOREIGN KEY ("input_frame_id") REFERENCES "public"."input_frame" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."sample" ADD CONSTRAINT "fk_sample_identity" FOREIGN KEY ("identity_id") REFERENCES "public"."identity" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."sample" ADD CONSTRAINT "fk_sample_query" FOREIGN KEY ("query_id") REFERENCES "public"."query_request" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."sample" ADD CONSTRAINT "fk_sample_track" FOREIGN KEY ("tracklet_id") REFERENCES "public"."tracklet" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table search_hit
-- ----------------------------
ALTER TABLE "public"."search_hit" ADD CONSTRAINT "fk_hit_feature" FOREIGN KEY ("feature_id") REFERENCES "public"."feature" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."search_hit" ADD CONSTRAINT "fk_hit_identity" FOREIGN KEY ("identity_id") REFERENCES "public"."identity" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."search_hit" ADD CONSTRAINT "fk_hit_query" FOREIGN KEY ("query_id") REFERENCES "public"."query_request" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."search_hit" ADD CONSTRAINT "fk_hit_sample" FOREIGN KEY ("sample_id") REFERENCES "public"."sample" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."search_hit" ADD CONSTRAINT "fk_hit_space" FOREIGN KEY ("feature_space_id") REFERENCES "public"."feature_space" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."search_hit" ADD CONSTRAINT "fk_hit_track" FOREIGN KEY ("tracklet_id") REFERENCES "public"."tracklet" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table stream_session
-- ----------------------------
ALTER TABLE "public"."stream_session" ADD CONSTRAINT "fk_ss_source" FOREIGN KEY ("source_id") REFERENCES "public"."camera" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."stream_session" ADD CONSTRAINT "fk_ss_stream" FOREIGN KEY ("camera_stream_id") REFERENCES "public"."camera_stream" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table task_attempt
-- ----------------------------
ALTER TABLE "public"."task_attempt" ADD CONSTRAINT "fk_attempt_legacy" FOREIGN KEY ("legacy_run_id") REFERENCES "public"."ai_task_run" ("run_id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."task_attempt" ADD CONSTRAINT "fk_attempt_task" FOREIGN KEY ("task_id") REFERENCES "public"."business_task" ("task_id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table task_output
-- ----------------------------
ALTER TABLE "public"."task_output" ADD CONSTRAINT "task_output_asset_id_fkey" FOREIGN KEY ("asset_id") REFERENCES "public"."media_asset" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."task_output" ADD CONSTRAINT "task_output_result_type_schema_version_fkey" FOREIGN KEY ("result_type", "schema_version") REFERENCES "public"."result_type" ("type_code", "schema_version") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."task_output" ADD CONSTRAINT "task_output_task_id_run_id_fkey" FOREIGN KEY ("task_id", "run_id") REFERENCES "public"."task_attempt" ("task_id", "run_id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table track_identity_assignment
-- ----------------------------
ALTER TABLE "public"."track_identity_assignment" ADD CONSTRAINT "fk_tia_identity" FOREIGN KEY ("identity_id") REFERENCES "public"."identity" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."track_identity_assignment" ADD CONSTRAINT "fk_tia_run" FOREIGN KEY ("run_id") REFERENCES "public"."task_attempt" ("run_id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."track_identity_assignment" ADD CONSTRAINT "fk_tia_track" FOREIGN KEY ("tracklet_id") REFERENCES "public"."tracklet" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table tracking_context
-- ----------------------------
ALTER TABLE "public"."tracking_context" ADD CONSTRAINT "fk_context_run" FOREIGN KEY ("run_id") REFERENCES "public"."task_attempt" ("run_id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."tracking_context" ADD CONSTRAINT "fk_context_session" FOREIGN KEY ("stream_session_id") REFERENCES "public"."stream_session" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table tracklet
-- ----------------------------
ALTER TABLE "public"."tracklet" ADD CONSTRAINT "fk_track_canonical" FOREIGN KEY ("canonical_tracklet_id") REFERENCES "public"."tracklet" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."tracklet" ADD CONSTRAINT "fk_track_context" FOREIGN KEY ("tracking_context_id") REFERENCES "public"."tracking_context" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."tracklet" ADD CONSTRAINT "fk_track_result_set" FOREIGN KEY ("origin_result_set_id") REFERENCES "public"."result_set" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."tracklet" ADD CONSTRAINT "fk_track_session" FOREIGN KEY ("stream_session_id") REFERENCES "public"."stream_session" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
ALTER TABLE "public"."tracklet" ADD CONSTRAINT "fk_track_source" FOREIGN KEY ("source_id") REFERENCES "public"."camera" ("id") ON DELETE RESTRICT ON UPDATE NO ACTION;
