/*
 Navicat Premium Dump SQL

 Source Server         : hxjm_pg
 Source Server Type    : PostgreSQL
 Source Server Version : 160011 (160011)
 Source Host           : 192.168.109.191:5432
 Source Catalog        : postgres
 Source Schema         : public

 Target Server Type    : PostgreSQL
 Target Server Version : 160011 (160011)
 File Encoding         : 65001

 Date: 24/12/2025 11:09:01
*/


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
ALTER TABLE "public"."camera" OWNER TO "root";

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
ALTER TABLE "public"."camera_stream" OWNER TO "root";

-- ----------------------------
-- Table structure for episode
-- ----------------------------
DROP TABLE IF EXISTS "public"."episode";
CREATE TABLE "public"."episode" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "title" text COLLATE "pg_catalog"."default",
  "start_ts" timestamptz(6) NOT NULL,
  "end_ts" timestamptz(6) NOT NULL,
  "main_target_id" uuid,
  "status" text COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'open'::text,
  "meta" jsonb,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now()
)
;
ALTER TABLE "public"."episode" OWNER TO "root";

-- ----------------------------
-- Table structure for episode_media_link
-- ----------------------------
DROP TABLE IF EXISTS "public"."episode_media_link";
CREATE TABLE "public"."episode_media_link" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "episode_id" uuid NOT NULL,
  "media_asset_id" uuid NOT NULL,
  "role" text COLLATE "pg_catalog"."default" NOT NULL,
  "note" text COLLATE "pg_catalog"."default",
  "created_at" timestamptz(6) NOT NULL DEFAULT now()
)
;
ALTER TABLE "public"."episode_media_link" OWNER TO "root";

-- ----------------------------
-- Table structure for episode_tracklet_link
-- ----------------------------
DROP TABLE IF EXISTS "public"."episode_tracklet_link";
CREATE TABLE "public"."episode_tracklet_link" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "episode_id" uuid NOT NULL,
  "tracklet_id" uuid NOT NULL,
  "role" text COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'primary'::text,
  "note" text COLLATE "pg_catalog"."default",
  "created_at" timestamptz(6) NOT NULL DEFAULT now()
)
;
ALTER TABLE "public"."episode_tracklet_link" OWNER TO "root";

-- ----------------------------
-- Table structure for llm_report
-- ----------------------------
DROP TABLE IF EXISTS "public"."llm_report";
CREATE TABLE "public"."llm_report" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "episode_id" uuid NOT NULL,
  "prompt_version" text COLLATE "pg_catalog"."default",
  "report_json" jsonb NOT NULL,
  "report_text" text COLLATE "pg_catalog"."default",
  "created_at" timestamptz(6) NOT NULL DEFAULT now()
)
;
ALTER TABLE "public"."llm_report" OWNER TO "root";

-- ----------------------------
-- Table structure for media_asset
-- ----------------------------
DROP TABLE IF EXISTS "public"."media_asset";
CREATE TABLE "public"."media_asset" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "stream_id" uuid NOT NULL,
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
ALTER TABLE "public"."media_asset" OWNER TO "root";

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
  "query_asset_id" uuid,
  "evidence_asset_id" uuid,
  "meta" jsonb,
  "created_at" timestamptz(6) NOT NULL DEFAULT now()
)
;
ALTER TABLE "public"."reid_match" OWNER TO "root";

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
  "updated_at" timestamptz(6) NOT NULL DEFAULT now()
)
;
ALTER TABLE "public"."reid_target" OWNER TO "root";

-- ----------------------------
-- Table structure for stranger_target
-- ----------------------------
DROP TABLE IF EXISTS "public"."stranger_target";
CREATE TABLE "public"."stranger_target" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "code" text COLLATE "pg_catalog"."default" NOT NULL,
  "status" text COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'new'::text,
  "embedding" "public"."vector" NOT NULL,
  "embedding_model" text COLLATE "pg_catalog"."default" NOT NULL,
  "is_active" bool NOT NULL DEFAULT true,
  "promoted_target_id" uuid,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now()
)
;
ALTER TABLE "public"."stranger_target" OWNER TO "root";

-- ----------------------------
-- Table structure for tracklet
-- ----------------------------
DROP TABLE IF EXISTS "public"."tracklet";
CREATE TABLE "public"."tracklet" (
  "id" uuid NOT NULL DEFAULT gen_random_uuid(),
  "stream_id" uuid NOT NULL,
  "start_ts" timestamptz(6) NOT NULL,
  "end_ts" timestamptz(6),
  "cls_name" text COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'person'::text,
  "quality" float8,
  "query_asset_id" uuid,
  "gallery_target_id" uuid,
  "gallery_similarity" float8,
  "stranger_target_id" uuid,
  "repr_embedding" "public"."vector",
  "embedding_model" text COLLATE "pg_catalog"."default",
  "trajectory_points" jsonb,
  "keyframes" jsonb,
  "meta" jsonb,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now()
)
;
ALTER TABLE "public"."tracklet" OWNER TO "root";

-- ----------------------------
-- Triggers structure for table camera
-- ----------------------------
CREATE TRIGGER "trg_camera_updated_at" BEFORE UPDATE ON "public"."camera"
FOR EACH ROW
EXECUTE PROCEDURE "public"."set_updated_at"();

-- ----------------------------
-- Uniques structure for table camera
-- ----------------------------
ALTER TABLE "public"."camera" ADD CONSTRAINT "camera_camera_code_key" UNIQUE ("camera_code");

-- ----------------------------
-- Primary Key structure for table camera
-- ----------------------------
ALTER TABLE "public"."camera" ADD CONSTRAINT "camera_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table camera_stream
-- ----------------------------
CREATE INDEX "idx_camera_stream_active" ON "public"."camera_stream" USING btree (
  "is_active" "pg_catalog"."bool_ops" ASC NULLS LAST
);
CREATE INDEX "idx_camera_stream_camera_id" ON "public"."camera_stream" USING btree (
  "camera_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Triggers structure for table camera_stream
-- ----------------------------
CREATE TRIGGER "trg_camera_stream_updated_at" BEFORE UPDATE ON "public"."camera_stream"
FOR EACH ROW
EXECUTE PROCEDURE "public"."set_updated_at"();

-- ----------------------------
-- Uniques structure for table camera_stream
-- ----------------------------
ALTER TABLE "public"."camera_stream" ADD CONSTRAINT "camera_stream_stream_name_key" UNIQUE ("stream_name");
ALTER TABLE "public"."camera_stream" ADD CONSTRAINT "camera_stream_shm_name_key" UNIQUE ("shm_name");

-- ----------------------------
-- Checks structure for table camera_stream
-- ----------------------------
ALTER TABLE "public"."camera_stream" ADD CONSTRAINT "chk_camera_stream_task_type" CHECK (task_type = ANY (ARRAY['reid'::text, 'yolo'::text, 'sam'::text, 'pose'::text, 'track'::text, 'other'::text]));

-- ----------------------------
-- Primary Key structure for table camera_stream
-- ----------------------------
ALTER TABLE "public"."camera_stream" ADD CONSTRAINT "camera_stream_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table episode
-- ----------------------------
CREATE INDEX "idx_episode_main_target" ON "public"."episode" USING btree (
  "main_target_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
) WHERE main_target_id IS NOT NULL;
CREATE INDEX "idx_episode_time" ON "public"."episode" USING btree (
  "start_ts" "pg_catalog"."timestamptz_ops" ASC NULLS LAST,
  "end_ts" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);

-- ----------------------------
-- Triggers structure for table episode
-- ----------------------------
CREATE TRIGGER "trg_episode_updated_at" BEFORE UPDATE ON "public"."episode"
FOR EACH ROW
EXECUTE PROCEDURE "public"."set_updated_at"();

-- ----------------------------
-- Checks structure for table episode
-- ----------------------------
ALTER TABLE "public"."episode" ADD CONSTRAINT "chk_episode_status" CHECK (status = ANY (ARRAY['open'::text, 'closed'::text, 'reviewed'::text]));

-- ----------------------------
-- Primary Key structure for table episode
-- ----------------------------
ALTER TABLE "public"."episode" ADD CONSTRAINT "episode_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table episode_media_link
-- ----------------------------
CREATE INDEX "idx_episode_media_link_episode" ON "public"."episode_media_link" USING btree (
  "episode_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);
CREATE INDEX "idx_episode_media_link_media" ON "public"."episode_media_link" USING btree (
  "media_asset_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Checks structure for table episode_media_link
-- ----------------------------
ALTER TABLE "public"."episode_media_link" ADD CONSTRAINT "chk_episode_media_role" CHECK (role = ANY (ARRAY['recording'::text, 'clip'::text, 'snapshot'::text, 'keyframe'::text]));

-- ----------------------------
-- Primary Key structure for table episode_media_link
-- ----------------------------
ALTER TABLE "public"."episode_media_link" ADD CONSTRAINT "episode_media_link_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table episode_tracklet_link
-- ----------------------------
CREATE INDEX "idx_episode_tracklet_link_episode" ON "public"."episode_tracklet_link" USING btree (
  "episode_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);
CREATE INDEX "idx_episode_tracklet_link_tracklet" ON "public"."episode_tracklet_link" USING btree (
  "tracklet_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table episode_tracklet_link
-- ----------------------------
ALTER TABLE "public"."episode_tracklet_link" ADD CONSTRAINT "uq_episode_tracklet" UNIQUE ("episode_id", "tracklet_id");

-- ----------------------------
-- Checks structure for table episode_tracklet_link
-- ----------------------------
ALTER TABLE "public"."episode_tracklet_link" ADD CONSTRAINT "chk_episode_tracklet_role" CHECK (role = ANY (ARRAY['primary'::text, 'secondary'::text]));

-- ----------------------------
-- Primary Key structure for table episode_tracklet_link
-- ----------------------------
ALTER TABLE "public"."episode_tracklet_link" ADD CONSTRAINT "episode_tracklet_link_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table llm_report
-- ----------------------------
CREATE INDEX "idx_llm_report_episode_time" ON "public"."llm_report" USING btree (
  "episode_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "created_at" "pg_catalog"."timestamptz_ops" DESC NULLS FIRST
);

-- ----------------------------
-- Primary Key structure for table llm_report
-- ----------------------------
ALTER TABLE "public"."llm_report" ADD CONSTRAINT "llm_report_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table media_asset
-- ----------------------------
CREATE INDEX "idx_media_asset_stream_start" ON "public"."media_asset" USING btree (
  "stream_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "start_ts" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);
CREATE INDEX "idx_media_asset_type_start" ON "public"."media_asset" USING btree (
  "asset_type" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST,
  "start_ts" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);

-- ----------------------------
-- Checks structure for table media_asset
-- ----------------------------
ALTER TABLE "public"."media_asset" ADD CONSTRAINT "media_asset_duration_ms_check" CHECK (duration_ms >= 0);
ALTER TABLE "public"."media_asset" ADD CONSTRAINT "chk_media_asset_type" CHECK (asset_type = ANY (ARRAY['segment'::text, 'clip'::text, 'snapshot'::text]));

-- ----------------------------
-- Primary Key structure for table media_asset
-- ----------------------------
ALTER TABLE "public"."media_asset" ADD CONSTRAINT "media_asset_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table reid_match
-- ----------------------------
CREATE INDEX "idx_reid_match_matched_ts" ON "public"."reid_match" USING btree (
  "matched" "pg_catalog"."bool_ops" ASC NULLS LAST,
  "ts" "pg_catalog"."timestamptz_ops" DESC NULLS FIRST
);
CREATE INDEX "idx_reid_match_stranger_ts" ON "public"."reid_match" USING btree (
  "stranger_target_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "ts" "pg_catalog"."timestamptz_ops" DESC NULLS FIRST
) WHERE stranger_target_id IS NOT NULL;
CREATE INDEX "idx_reid_match_target_ts" ON "public"."reid_match" USING btree (
  "target_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "ts" "pg_catalog"."timestamptz_ops" DESC NULLS FIRST
) WHERE target_id IS NOT NULL;
CREATE INDEX "idx_reid_match_tracklet_ts" ON "public"."reid_match" USING btree (
  "tracklet_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "ts" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);

-- ----------------------------
-- Checks structure for table reid_match
-- ----------------------------
ALTER TABLE "public"."reid_match" ADD CONSTRAINT "chk_reid_match_target_oneof" CHECK (NOT (target_id IS NOT NULL AND stranger_target_id IS NOT NULL));

-- ----------------------------
-- Primary Key structure for table reid_match
-- ----------------------------
ALTER TABLE "public"."reid_match" ADD CONSTRAINT "reid_match_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table reid_target
-- ----------------------------
CREATE INDEX "idx_reid_target_active" ON "public"."reid_target" USING btree (
  "is_active" "pg_catalog"."bool_ops" ASC NULLS LAST
);

-- ----------------------------
-- Triggers structure for table reid_target
-- ----------------------------
CREATE TRIGGER "trg_reid_target_updated_at" BEFORE UPDATE ON "public"."reid_target"
FOR EACH ROW
EXECUTE PROCEDURE "public"."set_updated_at"();

-- ----------------------------
-- Primary Key structure for table reid_target
-- ----------------------------
ALTER TABLE "public"."reid_target" ADD CONSTRAINT "reid_target_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table stranger_target
-- ----------------------------
CREATE INDEX "idx_stranger_target_active" ON "public"."stranger_target" USING btree (
  "is_active" "pg_catalog"."bool_ops" ASC NULLS LAST
);
CREATE INDEX "idx_stranger_target_status" ON "public"."stranger_target" USING btree (
  "status" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Triggers structure for table stranger_target
-- ----------------------------
CREATE TRIGGER "trg_stranger_target_updated_at" BEFORE UPDATE ON "public"."stranger_target"
FOR EACH ROW
EXECUTE PROCEDURE "public"."set_updated_at"();

-- ----------------------------
-- Uniques structure for table stranger_target
-- ----------------------------
ALTER TABLE "public"."stranger_target" ADD CONSTRAINT "stranger_target_code_key" UNIQUE ("code");

-- ----------------------------
-- Checks structure for table stranger_target
-- ----------------------------
ALTER TABLE "public"."stranger_target" ADD CONSTRAINT "chk_stranger_status" CHECK (status = ANY (ARRAY['new'::text, 'watch'::text, 'cleared'::text, 'promoted'::text]));

-- ----------------------------
-- Primary Key structure for table stranger_target
-- ----------------------------
ALTER TABLE "public"."stranger_target" ADD CONSTRAINT "stranger_target_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table tracklet
-- ----------------------------
CREATE INDEX "idx_tracklet_gallery_start" ON "public"."tracklet" USING btree (
  "gallery_target_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "start_ts" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
) WHERE gallery_target_id IS NOT NULL;
CREATE INDEX "idx_tracklet_stranger_start" ON "public"."tracklet" USING btree (
  "stranger_target_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "start_ts" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
) WHERE stranger_target_id IS NOT NULL;
CREATE INDEX "idx_tracklet_stream_start" ON "public"."tracklet" USING btree (
  "stream_id" "pg_catalog"."uuid_ops" ASC NULLS LAST,
  "start_ts" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);

-- ----------------------------
-- Triggers structure for table tracklet
-- ----------------------------
CREATE TRIGGER "trg_tracklet_updated_at" BEFORE UPDATE ON "public"."tracklet"
FOR EACH ROW
EXECUTE PROCEDURE "public"."set_updated_at"();

-- ----------------------------
-- Checks structure for table tracklet
-- ----------------------------
ALTER TABLE "public"."tracklet" ADD CONSTRAINT "chk_tracklet_identity_oneof" CHECK (NOT (gallery_target_id IS NOT NULL AND stranger_target_id IS NOT NULL));

-- ----------------------------
-- Primary Key structure for table tracklet
-- ----------------------------
ALTER TABLE "public"."tracklet" ADD CONSTRAINT "tracklet_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Foreign Keys structure for table camera_stream
-- ----------------------------
ALTER TABLE "public"."camera_stream" ADD CONSTRAINT "camera_stream_camera_id_fkey" FOREIGN KEY ("camera_id") REFERENCES "public"."camera" ("id") ON DELETE CASCADE ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table episode
-- ----------------------------
ALTER TABLE "public"."episode" ADD CONSTRAINT "episode_main_target_id_fkey" FOREIGN KEY ("main_target_id") REFERENCES "public"."reid_target" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table episode_media_link
-- ----------------------------
ALTER TABLE "public"."episode_media_link" ADD CONSTRAINT "episode_media_link_episode_id_fkey" FOREIGN KEY ("episode_id") REFERENCES "public"."episode" ("id") ON DELETE CASCADE ON UPDATE NO ACTION;
ALTER TABLE "public"."episode_media_link" ADD CONSTRAINT "episode_media_link_media_asset_id_fkey" FOREIGN KEY ("media_asset_id") REFERENCES "public"."media_asset" ("id") ON DELETE CASCADE ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table episode_tracklet_link
-- ----------------------------
ALTER TABLE "public"."episode_tracklet_link" ADD CONSTRAINT "episode_tracklet_link_episode_id_fkey" FOREIGN KEY ("episode_id") REFERENCES "public"."episode" ("id") ON DELETE CASCADE ON UPDATE NO ACTION;
ALTER TABLE "public"."episode_tracklet_link" ADD CONSTRAINT "episode_tracklet_link_tracklet_id_fkey" FOREIGN KEY ("tracklet_id") REFERENCES "public"."tracklet" ("id") ON DELETE CASCADE ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table llm_report
-- ----------------------------
ALTER TABLE "public"."llm_report" ADD CONSTRAINT "llm_report_episode_id_fkey" FOREIGN KEY ("episode_id") REFERENCES "public"."episode" ("id") ON DELETE CASCADE ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table media_asset
-- ----------------------------
ALTER TABLE "public"."media_asset" ADD CONSTRAINT "media_asset_stream_id_fkey" FOREIGN KEY ("stream_id") REFERENCES "public"."camera_stream" ("id") ON DELETE CASCADE ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table reid_match
-- ----------------------------
ALTER TABLE "public"."reid_match" ADD CONSTRAINT "reid_match_evidence_asset_id_fkey" FOREIGN KEY ("evidence_asset_id") REFERENCES "public"."media_asset" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."reid_match" ADD CONSTRAINT "reid_match_query_asset_id_fkey" FOREIGN KEY ("query_asset_id") REFERENCES "public"."media_asset" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."reid_match" ADD CONSTRAINT "reid_match_stranger_target_id_fkey" FOREIGN KEY ("stranger_target_id") REFERENCES "public"."stranger_target" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."reid_match" ADD CONSTRAINT "reid_match_target_id_fkey" FOREIGN KEY ("target_id") REFERENCES "public"."reid_target" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."reid_match" ADD CONSTRAINT "reid_match_tracklet_id_fkey" FOREIGN KEY ("tracklet_id") REFERENCES "public"."tracklet" ("id") ON DELETE CASCADE ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table reid_target
-- ----------------------------
ALTER TABLE "public"."reid_target" ADD CONSTRAINT "reid_target_source_asset_id_fkey" FOREIGN KEY ("source_asset_id") REFERENCES "public"."media_asset" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table stranger_target
-- ----------------------------
ALTER TABLE "public"."stranger_target" ADD CONSTRAINT "stranger_target_promoted_target_id_fkey" FOREIGN KEY ("promoted_target_id") REFERENCES "public"."reid_target" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table tracklet
-- ----------------------------
ALTER TABLE "public"."tracklet" ADD CONSTRAINT "tracklet_gallery_target_id_fkey" FOREIGN KEY ("gallery_target_id") REFERENCES "public"."reid_target" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."tracklet" ADD CONSTRAINT "tracklet_query_asset_id_fkey" FOREIGN KEY ("query_asset_id") REFERENCES "public"."media_asset" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."tracklet" ADD CONSTRAINT "tracklet_stranger_target_id_fkey" FOREIGN KEY ("stranger_target_id") REFERENCES "public"."stranger_target" ("id") ON DELETE SET NULL ON UPDATE NO ACTION;
ALTER TABLE "public"."tracklet" ADD CONSTRAINT "tracklet_stream_id_fkey" FOREIGN KEY ("stream_id") REFERENCES "public"."camera_stream" ("id") ON DELETE CASCADE ON UPDATE NO ACTION;
