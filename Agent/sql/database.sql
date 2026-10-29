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

 Date: 16/09/2026 15:46:56
*/


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
ALTER TYPE "public"."halfvec" OWNER TO "root";

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
ALTER TYPE "public"."sparsevec" OWNER TO "root";

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
ALTER TYPE "public"."vector" OWNER TO "root";

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
-- Records of ai_task_run
-- ----------------------------
INSERT INTO "public"."ai_task_run" VALUES ('11037781-8b06-4086-9f09-3b89fba39174', 4, 'boxmot', 'FAILED', 'live/camera_4', 'live/camera_4_boxmot', 'http://192.168.109.191:8889/live/camera_4_boxmot', 'MediaMTX input path is offline', NULL, NULL, '2026-08-31 06:11:09.741+00', '2026-08-31 06:11:23.76+00');
INSERT INTO "public"."ai_task_run" VALUES ('8f73bf40-db6f-4e50-a0e6-d8b1429953c3', 1, 'deepsort', 'FAILED', 'live/camera_1', 'live/camera_1_deepsort', 'http://192.168.109.191:8889/live/camera_1_deepsort', '创建 MediaMTX 代理流失败', NULL, NULL, '2026-08-31 11:22:41.403+00', '2026-08-31 11:22:41.457+00');
INSERT INTO "public"."ai_task_run" VALUES ('88d5d3dd-f3e0-4503-a3e7-495f753256cb', 1, 'boxmot', 'FAILED', 'live/camera_1', 'live/camera_1_boxmot', 'http://192.168.109.191:8889/live/camera_1_boxmot', 'MediaMTX input path is missing', NULL, NULL, '2026-08-31 03:02:01.521+00', '2026-08-31 03:24:16.452+00');
INSERT INTO "public"."ai_task_run" VALUES ('27e80c17-dd95-4ee3-86db-04312ee00051', 2, 'boxmot', 'FAILED', 'live/camera_2', 'live/camera_2_boxmot', 'http://192.168.109.191:8889/live/camera_2_boxmot', 'MediaMTX input path is missing', NULL, NULL, '2026-08-31 03:02:01.875+00', '2026-08-31 03:24:16.472+00');
INSERT INTO "public"."ai_task_run" VALUES ('5dd82560-6607-4916-a8de-6f150bad126d', 3, 'boxmot', 'FAILED', 'live/camera_3', 'live/camera_3_boxmot', 'http://192.168.109.191:8889/live/camera_3_boxmot', 'MediaMTX input path is missing', NULL, NULL, '2026-08-31 03:02:01.957+00', '2026-08-31 03:24:16.487+00');
INSERT INTO "public"."ai_task_run" VALUES ('40f535ca-d1ea-47a4-80fd-41149794ac64', 4, 'boxmot', 'FAILED', 'live/camera_4', 'live/camera_4_boxmot', 'http://192.168.109.191:8889/live/camera_4_boxmot', 'MediaMTX input path is missing', NULL, NULL, '2026-08-31 03:02:02.012+00', '2026-08-31 03:24:16.5+00');
INSERT INTO "public"."ai_task_run" VALUES ('013b78ba-4397-4a36-b6ab-aef1d161f9ef', 1, 'deepsort', 'FAILED', 'live/camera_1', 'live/camera_1_deepsort', 'http://192.168.109.191:8889/live/camera_1_deepsort', '创建 MediaMTX 代理流失败', NULL, NULL, '2026-08-31 11:27:33.183+00', '2026-08-31 11:27:33.195+00');
INSERT INTO "public"."ai_task_run" VALUES ('4bd33fbf-873e-4d21-8fa6-8a1a69d928ec', 1, 'boxmot', 'FAILED', 'live/camera_1', 'live/camera_1_boxmot', 'http://192.168.109.191:8889/live/camera_1_boxmot', 'MediaMTX input path is offline', NULL, NULL, '2026-08-31 03:24:16.578+00', '2026-08-31 03:24:31.521+00');
INSERT INTO "public"."ai_task_run" VALUES ('cd16d12c-edb7-4c5c-b6a8-47d4c8a463a1', 2, 'boxmot', 'FAILED', 'live/camera_2', 'live/camera_2_boxmot', 'http://192.168.109.191:8889/live/camera_2_boxmot', 'MediaMTX input path is offline', NULL, NULL, '2026-08-31 03:24:17.024+00', '2026-08-31 03:24:31.532+00');
INSERT INTO "public"."ai_task_run" VALUES ('26dee923-d3d8-419a-ab8e-7b50451c4f3d', 3, 'boxmot', 'FAILED', 'live/camera_3', 'live/camera_3_boxmot', 'http://192.168.109.191:8889/live/camera_3_boxmot', 'MediaMTX input path is offline', NULL, NULL, '2026-08-31 03:24:17.108+00', '2026-08-31 03:24:31.542+00');
INSERT INTO "public"."ai_task_run" VALUES ('ec48f2a8-7316-4541-b73c-bc4f37d4fac9', 4, 'boxmot', 'FAILED', 'live/camera_4', 'live/camera_4_boxmot', 'http://192.168.109.191:8889/live/camera_4_boxmot', 'MediaMTX input path is offline', NULL, NULL, '2026-08-31 03:24:17.17+00', '2026-08-31 03:24:31.554+00');
INSERT INTO "public"."ai_task_run" VALUES ('ca8b3247-efc8-42d1-85e9-17321c4ad66c', 1, 'boxmot', 'FAILED', 'live/camera_1', 'live/camera_1_boxmot', 'http://192.168.109.191:8889/live/camera_1_boxmot', 'MediaMTX input path is offline', NULL, NULL, '2026-08-31 06:11:09.202+00', '2026-08-31 06:11:23.731+00');
INSERT INTO "public"."ai_task_run" VALUES ('1401831e-5081-425c-89ba-5fb3e3fe2730', 2, 'boxmot', 'FAILED', 'live/camera_2', 'live/camera_2_boxmot', 'http://192.168.109.191:8889/live/camera_2_boxmot', 'MediaMTX input path is offline', NULL, NULL, '2026-08-31 06:11:09.572+00', '2026-08-31 06:11:23.741+00');
INSERT INTO "public"."ai_task_run" VALUES ('0134cdd8-b159-4942-af83-61569d48b8fd', 3, 'boxmot', 'FAILED', 'live/camera_3', 'live/camera_3_boxmot', 'http://192.168.109.191:8889/live/camera_3_boxmot', 'MediaMTX input path is offline', NULL, NULL, '2026-08-31 06:11:09.687+00', '2026-08-31 06:11:23.749+00');
INSERT INTO "public"."ai_task_run" VALUES ('38171260-a84c-499d-bba3-e2b059f39e17', 1, 'boxmot', 'FAILED', 'live/camera_1', 'live/camera_1_boxmot', 'http://192.168.109.191:18889/live/camera_1_boxmot', 'MediaMTX input path is offline', NULL, NULL, '2026-09-15 10:33:59.167+00', '2026-09-15 10:34:14.066+00');
INSERT INTO "public"."ai_task_run" VALUES ('2b582fca-5002-4505-9ad2-1cdedb641209', 2, 'boxmot', 'FAILED', 'live/camera_2', 'live/camera_2_boxmot', 'http://192.168.109.191:18889/live/camera_2_boxmot', 'MediaMTX input path is offline', NULL, NULL, '2026-09-15 10:33:59.878+00', '2026-09-15 10:34:14.085+00');
INSERT INTO "public"."ai_task_run" VALUES ('c97364a2-3796-4429-87f3-3a288f71511d', 3, 'boxmot', 'FAILED', 'live/camera_3', 'live/camera_3_boxmot', 'http://192.168.109.191:18889/live/camera_3_boxmot', 'MediaMTX input path is offline', NULL, NULL, '2026-09-15 10:34:00.099+00', '2026-09-15 10:34:14.103+00');
INSERT INTO "public"."ai_task_run" VALUES ('700cd79a-f48c-4e84-ad73-f765dcd83d03', 4, 'boxmot', 'FAILED', 'live/camera_4', 'live/camera_4_boxmot', 'http://192.168.109.191:18889/live/camera_4_boxmot', 'MediaMTX input path is offline', NULL, NULL, '2026-09-15 10:34:00.218+00', '2026-09-15 10:34:14.11+00');
INSERT INTO "public"."ai_task_run" VALUES ('8e562200-81ae-4d2f-8870-2b012d43c237', 1, 'boxmot', 'FAILED', 'live/camera_1', 'live/camera_1_boxmot', 'http://192.168.109.191:18889/live/camera_1_boxmot', '创建 MediaMTX 代理流失败', NULL, NULL, '2026-09-15 11:53:28.791+00', '2026-09-15 11:53:28.807+00');

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
  "updated_at" timestamptz(6) NOT NULL DEFAULT now()
)
;

-- ----------------------------
-- Records of camera
-- ----------------------------
INSERT INTO "public"."camera" VALUES ('3180e74c-e18c-4288-97ea-ddc394efc15d', 'camera_1', '摄像头001', '位置1', NULL, NULL, NULL, NULL, NULL, NULL, '2026-08-14 12:17:13.801541+00', '2026-08-14 12:17:13.801541+00');
INSERT INTO "public"."camera" VALUES ('b01796f4-14ef-4125-b0bd-9f21419bd4e5', 'camera_2', '摄像头002', '位置2', NULL, NULL, NULL, NULL, NULL, NULL, '2026-08-14 12:17:13.801541+00', '2026-08-14 12:17:13.801541+00');
INSERT INTO "public"."camera" VALUES ('1206ff4c-e3ed-48c8-937a-8ff9eb63ca15', 'camera_3', '摄像头003', '位置3', NULL, NULL, NULL, NULL, NULL, NULL, '2026-08-14 12:17:13.801541+00', '2026-08-14 12:17:13.801541+00');
INSERT INTO "public"."camera" VALUES ('a6dd6e98-0aae-4f5a-8436-e1fbfbc8316a', 'camera_4', '摄像头004', '位置4', NULL, NULL, NULL, NULL, NULL, NULL, '2026-08-14 12:17:13.801541+00', '2026-08-14 12:17:13.801541+00');

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
-- Records of camera_stream
-- ----------------------------
INSERT INTO "public"."camera_stream" VALUES ('ea932945-8758-4c2f-920f-b98c7a599970', '3180e74c-e18c-4288-97ea-ddc394efc15d', 'camera_1', 'raw', NULL, NULL, 't', NULL, '2026-08-14 12:18:03.856969+00', '2026-08-14 12:18:03.856969+00');
INSERT INTO "public"."camera_stream" VALUES ('10b8a99a-c11f-4fb7-9d58-d659a1d8ed26', 'b01796f4-14ef-4125-b0bd-9f21419bd4e5', 'camera_2', 'raw', NULL, NULL, 't', NULL, '2026-08-14 12:18:03.856969+00', '2026-08-14 12:18:03.856969+00');
INSERT INTO "public"."camera_stream" VALUES ('a59359ef-8ad9-4400-bba8-31463760054c', '1206ff4c-e3ed-48c8-937a-8ff9eb63ca15', 'camera_3', 'raw', NULL, NULL, 't', NULL, '2026-08-14 12:18:03.856969+00', '2026-08-14 12:18:03.856969+00');
INSERT INTO "public"."camera_stream" VALUES ('f1171c95-4eb3-4419-9875-cd36de5cfe0f', 'a6dd6e98-0aae-4f5a-8436-e1fbfbc8316a', 'camera_4', 'raw', NULL, NULL, 't', NULL, '2026-08-14 12:18:03.856969+00', '2026-08-14 12:18:03.856969+00');
INSERT INTO "public"."camera_stream" VALUES ('89209349-bc17-4cdb-9ea8-b1d974779622', '3180e74c-e18c-4288-97ea-ddc394efc15d', 'camera_1_boxmot', 'boxmot', NULL, NULL, 't', NULL, '2026-08-14 12:18:13.115652+00', '2026-08-14 12:18:13.115652+00');
INSERT INTO "public"."camera_stream" VALUES ('81ff16a7-cb1f-4eb4-bb6e-1542189469e0', 'b01796f4-14ef-4125-b0bd-9f21419bd4e5', 'camera_2_boxmot', 'boxmot', NULL, NULL, 't', NULL, '2026-08-14 12:18:13.115652+00', '2026-08-14 12:18:13.115652+00');
INSERT INTO "public"."camera_stream" VALUES ('fc0c6bb9-1afb-42af-b6b4-9bbfb5aea1e7', '1206ff4c-e3ed-48c8-937a-8ff9eb63ca15', 'camera_3_boxmot', 'boxmot', NULL, NULL, 't', NULL, '2026-08-14 12:18:13.115652+00', '2026-08-14 12:18:13.115652+00');
INSERT INTO "public"."camera_stream" VALUES ('638e9ad9-a60b-4502-9902-d97c9f7720ef', 'a6dd6e98-0aae-4f5a-8436-e1fbfbc8316a', 'camera_4_boxmot', 'boxmot', NULL, NULL, 't', NULL, '2026-08-14 12:18:13.115652+00', '2026-08-14 12:18:13.115652+00');

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
  "meta" jsonb
)
;

-- ----------------------------
-- Records of episode
-- ----------------------------

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
-- Records of episode_media_link
-- ----------------------------

-- ----------------------------
-- Table structure for episode_tracklet_link
-- ----------------------------
DROP TABLE IF EXISTS "public"."episode_tracklet_link";
CREATE TABLE "public"."episode_tracklet_link" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "episode_id" uuid NOT NULL,
  "tracklet_id" uuid NOT NULL,
  "note" text COLLATE "pg_catalog"."default",
  "created_at" timestamptz(6) NOT NULL DEFAULT now()
)
;

-- ----------------------------
-- Records of episode_tracklet_link
-- ----------------------------

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
  "created_at" timestamptz(6) NOT NULL DEFAULT now()
)
;

-- ----------------------------
-- Records of llm_report
-- ----------------------------
INSERT INTO "public"."llm_report" ("id", "episode_id", "vad_id", "prompt_type", "prompt_version", "report_json", "report_text", "created_at") VALUES ('d4d6e798-67b2-4c56-b91d-6e4d9abf5116', NULL, 5116, 'vad', 'demo-v1', '{"event_type": "fire", "summary": "摄像头 camera_4 检测到疑似火情，异常等级为 4，建议立即通知值班人员复核现场并按消防预案处置。", "risk_level": "high", "key_observations": ["事件来自 live/camera_4_vad 视频流", "VAD 异常类型为 fire，异常等级为 4", "该记录为演示报告，不代表模型实际分析结果"], "confidence": 0.85}'::jsonb, '摄像头 camera_4 检测到疑似火情，异常等级为 4，建议立即通知值班人员复核现场并按消防预案处置。', '2026-08-19 15:50:43+00');

-- ----------------------------
-- Table structure for media_asset
-- ----------------------------
DROP TABLE IF EXISTS "public"."media_asset";
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
)
;

-- ----------------------------
-- Records of media_asset
-- ----------------------------
INSERT INTO "public"."media_asset" VALUES ('281565a0-8378-40e1-9402-822c7d163028', 'live/camera_3', 'segment', '2026-08-10 02:16:53.651+00', 30267, 'http://192.168.109.191:9996/get?duration=30.267&path=live%2Fcamera_3&start=2026-08-10T10%3A16%3A53.651509%2B08%3A00', NULL, './recordings/live/camera_3/2026-08-10_10-16-53-651509.mp4', 'video/mp4', NULL, '2026-08-10 02:17:23.95+00');
-- 后面还有两万条，只列出一条样例

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
-- Records of reid_match
-- ----------------------------

-- ----------------------------
-- Table structure for reid_target
-- ----------------------------
DROP TABLE IF EXISTS "public"."reid_target";
CREATE TABLE "public"."reid_target" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "employee_id" text COLLATE "pg_catalog"."default",
  "name" text COLLATE "pg_catalog"."default" NOT NULL,
  "source_asset_id" uuid,
  "embedding" "public"."vector" NOT NULL,
  "embedding_model" text COLLATE "pg_catalog"."default" NOT NULL,
  "is_active" bool NOT NULL DEFAULT true,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now(),
  "image_base64" text COLLATE "pg_catalog"."default" NOT NULL
)
;

-- ----------------------------
-- Records of reid_target
-- ----------------------------
INSERT INTO "public"."reid_target" VALUES ('10880170-fbca-4768-83ad-df182d9079c0', '00015', '谭梓豪', NULL, '[0.021993052,0.0069864714,0.01700852,0.0298312,0.00086814666,1.76e-42,0.08674057,0.0035019165,0.0039138137,0.0019249024,0.0018016695,0.003690927,...超级长]', 'CLIP-ReID-ResNet50', 't', '2026-08-09 08:32:25.35699+00', '2026-08-09 08:32:25.357006+00', '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAIBAQEBAQIBAQECAgICAgQDAgICAgUEBAMEBgUGBgYFBgYGBwkIBgcJBwYGCAsICQoKCgoKBggLDAsKDAkKCgr/2wBDAQICAgICAgUDAwUKBwYHCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgr/wAARCAGpAJsDASIAAhEBAxEB/...超级长'
-- 后面还有几十条，只列出一条样例，存储的目标人名还有 任路阳，王新龙

-- ----------------------------
-- Table structure for reid_target_vit
-- ----------------------------
DROP TABLE IF EXISTS "public"."reid_target_vit";
CREATE TABLE "public"."reid_target_vit" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "employee_id" text COLLATE "pg_catalog"."default",
  "name" text COLLATE "pg_catalog"."default" NOT NULL,
  "source_asset_id" uuid,
  "embedding" "public"."vector" NOT NULL,
  "embedding_model" text COLLATE "pg_catalog"."default" NOT NULL,
  "is_active" bool NOT NULL DEFAULT true,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now(),
  "image_base64" text COLLATE "pg_catalog"."default" NOT NULL
)
;

-- ----------------------------
-- Records of reid_target_vit
-- ----------------------------

-- ----------------------------
-- Table structure for stranger_target
-- ----------------------------
DROP TABLE IF EXISTS "public"."stranger_target";
CREATE TABLE "public"."stranger_target" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "code" text COLLATE "pg_catalog"."default" NOT NULL,
  "status" text COLLATE "pg_catalog"."default" NOT NULL,
  "embedding" "public"."vector",
  "embedding_model" text COLLATE "pg_catalog"."default" NOT NULL,
  "is_active" bool NOT NULL DEFAULT true,
  "promoted_target_id" uuid,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now(),
  "image_base64" text COLLATE "pg_catalog"."default"
)
;

-- ----------------------------
-- Records of stranger_target
-- ----------------------------

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
  "repr_embedding" "public"."vector",
  "embedding_model" text COLLATE "pg_catalog"."default",
  "trajectory_points" jsonb,
  "meta" jsonb,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now()
)
;

-- ----------------------------
-- Records of tracklet
-- ----------------------------

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
-- Records of vad
-- ----------------------------
INSERT INTO "public"."vad" OVERRIDING SYSTEM VALUE VALUES (5116, '2026-08-19 15:50:42.546184+00', 'c8805dd9-75e5-44d2-8752-c3adb58c5be9', 'live/camera_4_vad', '/9j/4AAQSkZJRgABAQAAAQABAAD/....超级长'
-- 后面还有很多条，只列举一条示例
