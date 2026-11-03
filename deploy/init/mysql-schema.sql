-- v0.2 schema-only baseline; exported read-only from stable database. No business rows.

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `alg_bk_machine_fr` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键',
  `machine_id` int DEFAULT NULL COMMENT '设备id',
  `status` varchar(255) DEFAULT 'inactive' COMMENT '机器状态，可能的值为 active, inactive, error',
  `start_time` datetime DEFAULT NULL COMMENT '状态开始时间',
  `end_time` datetime DEFAULT NULL COMMENT '状态结束时间',
  `program_info` varchar(1000) DEFAULT NULL COMMENT '记录程序信息',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='算法布控机器状态表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `alg_bk_management` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键',
  `alg_bk_name` varchar(255) DEFAULT NULL COMMENT '布控算法名称',
  `alg_bk_type` int DEFAULT NULL COMMENT '布控算法类型',
  `alg_bk_api_head` varchar(255) DEFAULT NULL COMMENT '布控算法api请求头编码',
  `status` int DEFAULT '0' COMMENT '启用标志',
  `table_name` varchar(255) DEFAULT NULL COMMENT '设备状态表名',
  `remark` varchar(255) DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ba_algmodel` (
  `algmodel_id` int NOT NULL AUTO_INCREMENT COMMENT '主键',
  `algmodel_code` varchar(100) DEFAULT NULL COMMENT '模型编码',
  `algmodel_name` varchar(100) NOT NULL COMMENT '模型名称',
  `algmodel_engines` varchar(255) DEFAULT NULL COMMENT '模型引擎',
  `algmodel_input` varchar(50) DEFAULT NULL COMMENT '输入类型',
  `algmodel_output` varchar(50) DEFAULT NULL COMMENT '输出类型',
  `path` varchar(255) DEFAULT NULL COMMENT '模型路径\n',
  `algtype_id` int DEFAULT NULL COMMENT '算法类型id',
  `isvalid` int DEFAULT NULL COMMENT '启用',
  `remark` varchar(255) DEFAULT NULL COMMENT '模型描述',
  `preview` varchar(5000) DEFAULT NULL COMMENT '封面图',
  `icon` varchar(255) DEFAULT NULL COMMENT '标签图',
  PRIMARY KEY (`algmodel_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='模型信息表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ba_algtype` (
  `algtype_id` int NOT NULL AUTO_INCREMENT COMMENT '主键',
  `algtype_code` varchar(100) DEFAULT NULL COMMENT '算法类型编码',
  `algtype_name` varchar(100) NOT NULL COMMENT '算法类型名称',
  `isvalid` int DEFAULT NULL COMMENT '是否展示',
  `remark` varchar(255) DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`algtype_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='模型类型表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ba_machine` (
  `machine_id` int NOT NULL AUTO_INCREMENT COMMENT '主键',
  `machine_code` varchar(255) DEFAULT NULL COMMENT '设备编码',
  `machine_name` varchar(100) DEFAULT NULL COMMENT '设备名称',
  `decoder` varchar(255) DEFAULT NULL COMMENT '解码器',
  `resolution` varchar(255) DEFAULT NULL COMMENT '分辨率',
  `video_url` varchar(255) DEFAULT NULL COMMENT '设备流',
  `location_id` int DEFAULT NULL COMMENT '所属区域id',
  `status` int DEFAULT NULL COMMENT '设备状态',
  `isvalid` int DEFAULT NULL COMMENT '启用标志',
  PRIMARY KEY (`machine_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='设备信息表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `face_database` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '自增ID，唯一标识每条记录',
  `face_id` varchar(255) NOT NULL COMMENT '人脸ID，唯一标识每个特征（通常是UUID）',
  `user_name` varchar(255) DEFAULT NULL COMMENT '人员姓名',
  `face_encoding` blob COMMENT '人脸特征向量，用于存储提取的人脸特征（例如128维、512维向量）',
  `face_image` mediumblob COMMENT '人脸原始图像，用于存储采集到的图像数据或图像路径',
  `face_image_thumbnail` blob COMMENT '人脸缩略图，用于存储缩小版的人脸图像，用于展示',
  `metadata` json DEFAULT NULL COMMENT '元数据（如：年龄、性别等信息），以JSON格式存储',
  `status` int DEFAULT NULL COMMENT '状态，表示人脸记录当前的状态',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间，记录人脸数据首次添加时间',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间，记录每次修改该记录的时间',
  `gender` int DEFAULT NULL COMMENT '性别',
  `age` int DEFAULT NULL COMMENT '年龄',
  `quality` double DEFAULT NULL COMMENT '质量',
  PRIMARY KEY (`id`),
  UNIQUE KEY `face_id` (`face_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='人脸信息表，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `face_person` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `face_id` varchar(64) DEFAULT NULL COMMENT '算法侧人脸ID',
  `user_name` varchar(50) NOT NULL COMMENT '姓名',
  `face_encoding` blob COMMENT '人脸特征向量',
  `face_image` varchar(255) DEFAULT NULL COMMENT '人脸原始图片路径',
  `face_image_thumbnail` varchar(255) DEFAULT NULL COMMENT '人脸缩略图路径',
  `metadata` text COMMENT '元数据（JSON）',
  `status` tinyint(1) DEFAULT '1' COMMENT '状态：1启用,0停用',
  `gender` tinyint(1) DEFAULT '0' COMMENT '性别：0未知,1男,2女',
  `age` int DEFAULT NULL COMMENT '年龄',
  `quality` float DEFAULT NULL COMMENT '人脸质量评分',
  `person_type` varchar(20) DEFAULT 'EMPLOYEE' COMMENT '人员类型：EMPLOYEE/VISITOR/BLACKLIST 等',
  `job_no` varchar(32) DEFAULT NULL COMMENT '工号/学号',
  `id_card` varchar(32) DEFAULT NULL COMMENT '证件号',
  `phone` varchar(20) DEFAULT NULL COMMENT '手机号',
  `location` varchar(100) DEFAULT NULL COMMENT '位置',
  `dept_id` bigint DEFAULT NULL COMMENT '部门ID',
  `dept_name` varchar(50) DEFAULT NULL COMMENT '部门名称',
  `remark` varchar(500) DEFAULT NULL COMMENT '备注',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_dept_id` (`dept_id`),
  KEY `idx_face_id` (`face_id`),
  KEY `idx_person_type` (`person_type`),
  KEY `idx_status` (`status`),
  KEY `idx_user_name` (`user_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='正式人员表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `face_recognition_events` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '自增ID，唯一标识每条事件记录',
  `track_id` varchar(255) DEFAULT NULL COMMENT '检测时的追踪id',
  `machine_id` int DEFAULT NULL COMMENT '关联设备',
  `face_id` varchar(255) DEFAULT NULL COMMENT '关联`face_features`表中的`face_id`，表示哪个人脸被识别',
  `confidence` float DEFAULT NULL COMMENT '识别置信度，表示系统对该识别结果的信任程度（范围：0到1）',
  `recognition_time` datetime DEFAULT NULL COMMENT '识别时间',
  `departure_time` datetime DEFAULT NULL COMMENT '离开时间',
  `detection_img` mediumblob,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `face_recognition_events_copy` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '自增ID，唯一标识每条事件记录',
  `face_id` varchar(255) NOT NULL COMMENT '关联`face_features`表中的`face_id`，表示哪个人脸被识别',
  `recognized_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '识别事件发生时间，记录人脸被识别的时间',
  `location` varchar(255) NOT NULL COMMENT '事件发生地点，记录事件发生的具体地点（如：摄像头位置）',
  `event_type` varchar(50) NOT NULL COMMENT '事件类型，标识事件的种类（如：entry, exit, alert等）',
  `event_description` text COMMENT '事件描述，用于详细说明事件（如：是否为正常进入、是否有异常行为等）',
  `camera_id` int DEFAULT NULL COMMENT '摄像头ID，标识该事件发生在哪个摄像头上',
  `confidence_level` decimal(5,4) DEFAULT '1.0000' COMMENT '识别置信度，表示系统对该识别结果的信任程度（范围：0到1）',
  `is_manual` tinyint(1) DEFAULT '0' COMMENT '是否为人工确认，表示该事件是否需要人工审核确认（例如报警事件）',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='人脸识别事件表，用于存储每次识别到人脸的详细事件信息，包括时间、地点、事件类型等';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `face_recognition_events_v1` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `track_id` varchar(64) DEFAULT NULL COMMENT '抓拍轨迹ID',
  `machine_id` bigint DEFAULT NULL COMMENT '设备ID',
  `identity_type` varchar(16) DEFAULT 'PERSON' COMMENT '身份类型：PERSON/STRANGER',
  `face_id` bigint DEFAULT NULL COMMENT '人员ID或陌生人ID',
  `confidence` decimal(5,2) DEFAULT NULL COMMENT '识别置信度',
  `recognition_time` datetime DEFAULT NULL COMMENT '识别时间',
  `departure_time` datetime DEFAULT NULL COMMENT '离开时间',
  `detection_img` varchar(255) DEFAULT NULL COMMENT '抓拍图片路径',
  PRIMARY KEY (`id`),
  KEY `idx_face_identity` (`face_id`,`identity_type`),
  KEY `idx_face_machine` (`machine_id`),
  KEY `idx_face_recognition_time` (`recognition_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='人脸识别事件表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `face_stranger` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '陌生人ID',
  `face_id` varchar(64) DEFAULT NULL COMMENT '算法侧人脸ID（可为空）',
  `display_name` varchar(100) NOT NULL COMMENT '展示名，如：陌生人_20251105_150935',
  `face_encoding` blob COMMENT '人脸特征向量',
  `face_image` varchar(255) DEFAULT NULL COMMENT '代表图路径',
  `face_image_thumbnail` varchar(255) DEFAULT NULL COMMENT '缩略图路径',
  `metadata` text COMMENT '元数据（JSON）',
  `status` varchar(20) DEFAULT 'PENDING' COMMENT '状态：PENDING/CONFIRMED/IGNORED',
  `gender` tinyint(1) DEFAULT '0' COMMENT '性别估计：0未知,1男,2女',
  `age` int DEFAULT NULL COMMENT '年龄估计',
  `quality` float DEFAULT NULL COMMENT '人脸质量评分',
  `first_seen_time` datetime DEFAULT NULL COMMENT '首次出现时间',
  `last_seen_time` datetime DEFAULT NULL COMMENT '最近一次出现时间',
  `seen_count` int DEFAULT '1' COMMENT '出现次数',
  `bind_person_id` bigint DEFAULT NULL COMMENT '若已转正，对应的正式人员ID',
  `remark` varchar(500) DEFAULT NULL COMMENT '备注',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_bind_person_id` (`bind_person_id`),
  KEY `idx_display_name` (`display_name`),
  KEY `idx_face_id` (`face_id`),
  KEY `idx_last_seen_time` (`last_seen_time`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='陌生人表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `gen_table` (
  `table_id` bigint NOT NULL AUTO_INCREMENT COMMENT '编号',
  `table_name` varchar(200) DEFAULT '' COMMENT '表名称',
  `table_comment` varchar(500) DEFAULT '' COMMENT '表描述',
  `sub_table_name` varchar(64) DEFAULT NULL COMMENT '关联子表的表名',
  `sub_table_fk_name` varchar(64) DEFAULT NULL COMMENT '子表关联的外键名',
  `class_name` varchar(100) DEFAULT '' COMMENT '实体类名称',
  `tpl_category` varchar(200) DEFAULT 'crud' COMMENT '使用的模板（crud单表操作 tree树表操作）',
  `tpl_web_type` varchar(30) DEFAULT '' COMMENT '前端模板类型（element-ui模版 element-plus模版）',
  `package_name` varchar(100) DEFAULT NULL COMMENT '生成包路径',
  `module_name` varchar(30) DEFAULT NULL COMMENT '生成模块名',
  `business_name` varchar(30) DEFAULT NULL COMMENT '生成业务名',
  `function_name` varchar(50) DEFAULT NULL COMMENT '生成功能名',
  `function_author` varchar(50) DEFAULT NULL COMMENT '生成功能作者',
  `gen_type` char(1) DEFAULT '0' COMMENT '生成代码方式（0zip压缩包 1自定义路径）',
  `gen_path` varchar(200) DEFAULT '/' COMMENT '生成路径（不填默认项目路径）',
  `options` varchar(1000) DEFAULT NULL COMMENT '其它生成选项',
  `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `remark` varchar(500) DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`table_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='代码生成业务表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `gen_table_column` (
  `column_id` bigint NOT NULL AUTO_INCREMENT COMMENT '编号',
  `table_id` bigint DEFAULT NULL COMMENT '归属表编号',
  `column_name` varchar(200) DEFAULT NULL COMMENT '列名称',
  `column_comment` varchar(500) DEFAULT NULL COMMENT '列描述',
  `column_type` varchar(100) DEFAULT NULL COMMENT '列类型',
  `java_type` varchar(500) DEFAULT NULL COMMENT 'JAVA类型',
  `java_field` varchar(200) DEFAULT NULL COMMENT 'JAVA字段名',
  `is_pk` char(1) DEFAULT NULL COMMENT '是否主键（1是）',
  `is_increment` char(1) DEFAULT NULL COMMENT '是否自增（1是）',
  `is_required` char(1) DEFAULT NULL COMMENT '是否必填（1是）',
  `is_insert` char(1) DEFAULT NULL COMMENT '是否为插入字段（1是）',
  `is_edit` char(1) DEFAULT NULL COMMENT '是否编辑字段（1是）',
  `is_list` char(1) DEFAULT NULL COMMENT '是否列表字段（1是）',
  `is_query` char(1) DEFAULT NULL COMMENT '是否查询字段（1是）',
  `query_type` varchar(200) DEFAULT 'EQ' COMMENT '查询方式（等于、不等于、大于、小于、范围）',
  `html_type` varchar(200) DEFAULT NULL COMMENT '显示类型（文本框、文本域、下拉框、复选框、单选框、日期控件）',
  `dict_type` varchar(200) DEFAULT '' COMMENT '字典类型',
  `sort` int DEFAULT NULL COMMENT '排序',
  `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`column_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='代码生成业务表字段';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_config` (
  `config_id` int NOT NULL AUTO_INCREMENT COMMENT '参数主键',
  `config_name` varchar(100) DEFAULT '' COMMENT '参数名称',
  `config_key` varchar(100) DEFAULT '' COMMENT '参数键名',
  `config_value` varchar(500) DEFAULT '' COMMENT '参数键值',
  `config_type` char(1) DEFAULT 'N' COMMENT '系统内置（Y是 N否）',
  `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `remark` varchar(500) DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`config_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='参数配置表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_dept` (
  `dept_id` bigint NOT NULL AUTO_INCREMENT COMMENT '部门id',
  `parent_id` bigint DEFAULT '0' COMMENT '父部门id',
  `ancestors` varchar(50) DEFAULT '' COMMENT '祖级列表',
  `dept_name` varchar(30) DEFAULT '' COMMENT '部门名称',
  `order_num` int DEFAULT '0' COMMENT '显示顺序',
  `leader` varchar(20) DEFAULT NULL COMMENT '负责人',
  `phone` varchar(11) DEFAULT NULL COMMENT '联系电话',
  `email` varchar(50) DEFAULT NULL COMMENT '邮箱',
  `status` char(1) DEFAULT '0' COMMENT '部门状态（0正常 1停用）',
  `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0代表存在 2代表删除）',
  `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`dept_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='部门表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_dict_data` (
  `dict_code` bigint NOT NULL AUTO_INCREMENT COMMENT '字典编码',
  `dict_sort` int DEFAULT '0' COMMENT '字典排序',
  `dict_label` varchar(100) DEFAULT '' COMMENT '字典标签',
  `dict_value` varchar(100) DEFAULT '' COMMENT '字典键值',
  `dict_type` varchar(100) DEFAULT '' COMMENT '字典类型',
  `css_class` varchar(100) DEFAULT NULL COMMENT '样式属性（其他样式扩展）',
  `list_class` varchar(100) DEFAULT NULL COMMENT '表格回显样式',
  `is_default` char(1) DEFAULT 'N' COMMENT '是否默认（Y是 N否）',
  `status` char(1) DEFAULT '0' COMMENT '状态（0正常 1停用）',
  `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `remark` varchar(500) DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`dict_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='字典数据表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_dict_type` (
  `dict_id` bigint NOT NULL AUTO_INCREMENT COMMENT 'å­—å…¸ä¸»é”®',
  `dict_name` varchar(100) DEFAULT '' COMMENT 'å­—å…¸åç§°',
  `dict_type` varchar(100) DEFAULT '' COMMENT 'å­—å…¸ç±»åž‹',
  `status` char(1) DEFAULT '0' COMMENT 'çŠ¶æ€ï¼ˆ0æ­£å¸¸ 1åœç”¨ï¼‰',
  `create_by` varchar(64) DEFAULT '' COMMENT 'åˆ›å»ºè€…',
  `create_time` datetime DEFAULT NULL COMMENT 'åˆ›å»ºæ—¶é—´',
  `update_by` varchar(64) DEFAULT '' COMMENT 'æ›´æ–°è€…',
  `update_time` datetime DEFAULT NULL COMMENT 'æ›´æ–°æ—¶é—´',
  `remark` varchar(500) DEFAULT NULL COMMENT 'å¤‡æ³¨',
  PRIMARY KEY (`dict_id`),
  UNIQUE KEY `dict_type` (`dict_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='å­—å…¸ç±»åž‹è¡¨';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_job` (
  `job_id` bigint NOT NULL AUTO_INCREMENT COMMENT '任务ID',
  `job_name` varchar(64) NOT NULL DEFAULT '' COMMENT '任务名称',
  `job_group` varchar(64) NOT NULL DEFAULT 'DEFAULT' COMMENT '任务组名',
  `invoke_target` varchar(500) NOT NULL COMMENT '调用目标字符串',
  `cron_expression` varchar(255) DEFAULT '' COMMENT 'cron执行表达式',
  `misfire_policy` varchar(20) DEFAULT '3' COMMENT '计划执行错误策略（1立即执行 2执行一次 3放弃执行）',
  `concurrent` char(1) DEFAULT '1' COMMENT '是否并发执行（0允许 1禁止）',
  `status` char(1) DEFAULT '0' COMMENT '状态（0正常 1暂停）',
  `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `remark` varchar(500) DEFAULT '' COMMENT '备注信息',
  PRIMARY KEY (`job_id`,`job_name`,`job_group`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='定时任务调度表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_job_log` (
  `job_log_id` bigint NOT NULL AUTO_INCREMENT COMMENT 'ä»»åŠ¡æ—¥å¿—ID',
  `job_name` varchar(64) NOT NULL COMMENT 'ä»»åŠ¡åç§°',
  `job_group` varchar(64) NOT NULL COMMENT 'ä»»åŠ¡ç»„å',
  `invoke_target` varchar(500) NOT NULL COMMENT 'è°ƒç”¨ç›®æ ‡å­—ç¬¦ä¸²',
  `job_message` varchar(500) DEFAULT NULL COMMENT 'æ—¥å¿—ä¿¡æ¯',
  `status` char(1) DEFAULT '0' COMMENT 'æ‰§è¡ŒçŠ¶æ€ï¼ˆ0æ­£å¸¸ 1å¤±è´¥ï¼‰',
  `exception_info` varchar(2000) DEFAULT '' COMMENT 'å¼‚å¸¸ä¿¡æ¯',
  `create_time` datetime DEFAULT NULL COMMENT 'åˆ›å»ºæ—¶é—´',
  PRIMARY KEY (`job_log_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='å®šæ—¶ä»»åŠ¡è°ƒåº¦æ—¥å¿—è¡¨';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_logininfor` (
  `info_id` bigint NOT NULL AUTO_INCREMENT COMMENT 'è®¿é—®ID',
  `user_name` varchar(50) DEFAULT '' COMMENT 'ç”¨æˆ·è´¦å·',
  `ipaddr` varchar(128) DEFAULT '' COMMENT 'ç™»å½•IPåœ°å€',
  `login_location` varchar(255) DEFAULT '' COMMENT 'ç™»å½•åœ°ç‚¹',
  `browser` varchar(50) DEFAULT '' COMMENT 'æµè§ˆå™¨ç±»åž‹',
  `os` varchar(50) DEFAULT '' COMMENT 'æ“ä½œç³»ç»Ÿ',
  `status` char(1) DEFAULT '0' COMMENT 'ç™»å½•çŠ¶æ€ï¼ˆ0æˆåŠŸ 1å¤±è´¥ï¼‰',
  `msg` varchar(255) DEFAULT '' COMMENT 'æç¤ºæ¶ˆæ¯',
  `login_time` datetime DEFAULT NULL COMMENT 'è®¿é—®æ—¶é—´',
  PRIMARY KEY (`info_id`),
  KEY `idx_sys_logininfor_s` (`status`),
  KEY `idx_sys_logininfor_lt` (`login_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='ç³»ç»Ÿè®¿é—®è®°å½•';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_menu` (
  `menu_id` bigint NOT NULL AUTO_INCREMENT COMMENT '菜单ID',
  `menu_name` varchar(50) NOT NULL COMMENT '菜单名称',
  `parent_id` bigint DEFAULT '0' COMMENT '父菜单ID',
  `order_num` int DEFAULT '0' COMMENT '显示顺序',
  `path` varchar(200) DEFAULT '' COMMENT '路由地址',
  `component` varchar(255) DEFAULT NULL COMMENT '组件路径',
  `query` varchar(255) DEFAULT NULL COMMENT '路由参数',
  `route_name` varchar(50) DEFAULT '' COMMENT '路由名称',
  `is_frame` int DEFAULT '1' COMMENT '是否为外链（0是 1否）',
  `is_cache` int DEFAULT '0' COMMENT '是否缓存（0缓存 1不缓存）',
  `menu_type` char(1) DEFAULT '' COMMENT '菜单类型（M目录 C菜单 F按钮）',
  `visible` char(1) DEFAULT '0' COMMENT '菜单状态（0显示 1隐藏）',
  `status` char(1) DEFAULT '0' COMMENT '菜单状态（0正常 1停用）',
  `perms` varchar(100) DEFAULT NULL COMMENT '权限标识',
  `icon` varchar(100) DEFAULT '#' COMMENT '菜单图标',
  `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `remark` varchar(500) DEFAULT '' COMMENT '备注',
  PRIMARY KEY (`menu_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='菜单权限表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_notice` (
  `notice_id` int NOT NULL AUTO_INCREMENT COMMENT '公告ID',
  `notice_title` varchar(50) NOT NULL COMMENT '公告标题',
  `notice_type` char(1) NOT NULL COMMENT '公告类型（1通知 2公告）',
  `notice_content` longblob COMMENT '公告内容',
  `status` char(1) DEFAULT '0' COMMENT '公告状态（0正常 1关闭）',
  `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `remark` varchar(255) DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`notice_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='通知公告表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_oper_log` (
  `oper_id` bigint NOT NULL AUTO_INCREMENT COMMENT 'æ—¥å¿—ä¸»é”®',
  `title` varchar(50) DEFAULT '' COMMENT 'æ¨¡å—æ ‡é¢˜',
  `business_type` int DEFAULT '0' COMMENT 'ä¸šåŠ¡ç±»åž‹ï¼ˆ0å…¶å®ƒ 1æ–°å¢ž 2ä¿®æ”¹ 3åˆ é™¤ï¼‰',
  `method` varchar(200) DEFAULT '' COMMENT 'æ–¹æ³•åç§°',
  `request_method` varchar(10) DEFAULT '' COMMENT 'è¯·æ±‚æ–¹å¼',
  `operator_type` int DEFAULT '0' COMMENT 'æ“ä½œç±»åˆ«ï¼ˆ0å…¶å®ƒ 1åŽå°ç”¨æˆ· 2æ‰‹æœºç«¯ç”¨æˆ·ï¼‰',
  `oper_name` varchar(50) DEFAULT '' COMMENT 'æ“ä½œäººå‘˜',
  `dept_name` varchar(50) DEFAULT '' COMMENT 'éƒ¨é—¨åç§°',
  `oper_url` varchar(255) DEFAULT '' COMMENT 'è¯·æ±‚URL',
  `oper_ip` varchar(128) DEFAULT '' COMMENT 'ä¸»æœºåœ°å€',
  `oper_location` varchar(255) DEFAULT '' COMMENT 'æ“ä½œåœ°ç‚¹',
  `oper_param` varchar(2000) DEFAULT '' COMMENT 'è¯·æ±‚å‚æ•°',
  `json_result` varchar(2000) DEFAULT '' COMMENT 'è¿”å›žå‚æ•°',
  `status` int DEFAULT '0' COMMENT 'æ“ä½œçŠ¶æ€ï¼ˆ0æ­£å¸¸ 1å¼‚å¸¸ï¼‰',
  `error_msg` varchar(2000) DEFAULT '' COMMENT 'é”™è¯¯æ¶ˆæ¯',
  `oper_time` datetime DEFAULT NULL COMMENT 'æ“ä½œæ—¶é—´',
  `cost_time` bigint DEFAULT '0' COMMENT 'æ¶ˆè€—æ—¶é—´',
  PRIMARY KEY (`oper_id`),
  KEY `idx_sys_oper_log_bt` (`business_type`),
  KEY `idx_sys_oper_log_s` (`status`),
  KEY `idx_sys_oper_log_ot` (`oper_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='æ“ä½œæ—¥å¿—è®°å½•';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_post` (
  `post_id` bigint NOT NULL AUTO_INCREMENT COMMENT 'å²—ä½ID',
  `post_code` varchar(64) NOT NULL COMMENT 'å²—ä½ç¼–ç ',
  `post_name` varchar(50) NOT NULL COMMENT 'å²—ä½åç§°',
  `post_sort` int NOT NULL COMMENT 'æ˜¾ç¤ºé¡ºåº',
  `status` char(1) NOT NULL COMMENT 'çŠ¶æ€ï¼ˆ0æ­£å¸¸ 1åœç”¨ï¼‰',
  `create_by` varchar(64) DEFAULT '' COMMENT 'åˆ›å»ºè€…',
  `create_time` datetime DEFAULT NULL COMMENT 'åˆ›å»ºæ—¶é—´',
  `update_by` varchar(64) DEFAULT '' COMMENT 'æ›´æ–°è€…',
  `update_time` datetime DEFAULT NULL COMMENT 'æ›´æ–°æ—¶é—´',
  `remark` varchar(500) DEFAULT NULL COMMENT 'å¤‡æ³¨',
  PRIMARY KEY (`post_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='å²—ä½ä¿¡æ¯è¡¨';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_role` (
  `role_id` bigint NOT NULL AUTO_INCREMENT COMMENT '角色ID',
  `role_name` varchar(30) NOT NULL COMMENT '角色名称',
  `role_key` varchar(100) NOT NULL COMMENT '角色权限字符串',
  `role_sort` int NOT NULL COMMENT '显示顺序',
  `data_scope` char(1) DEFAULT '1' COMMENT '数据范围（1：全部数据权限 2：自定数据权限 3：本部门数据权限 4：本部门及以下数据权限）',
  `menu_check_strictly` tinyint(1) DEFAULT '1' COMMENT '菜单树选择项是否关联显示',
  `dept_check_strictly` tinyint(1) DEFAULT '1' COMMENT '部门树选择项是否关联显示',
  `status` char(1) NOT NULL COMMENT '角色状态（0正常 1停用）',
  `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0代表存在 2代表删除）',
  `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `remark` varchar(500) DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`role_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='角色信息表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_role_dept` (
  `role_id` bigint NOT NULL COMMENT 'è§’è‰²ID',
  `dept_id` bigint NOT NULL COMMENT 'éƒ¨é—¨ID',
  PRIMARY KEY (`role_id`,`dept_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='è§’è‰²å’Œéƒ¨é—¨å…³è”è¡¨';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_role_menu` (
  `role_id` bigint NOT NULL COMMENT 'è§’è‰²ID',
  `menu_id` bigint NOT NULL COMMENT 'èœå•ID',
  PRIMARY KEY (`role_id`,`menu_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='è§’è‰²å’Œèœå•å…³è”è¡¨';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_user` (
  `user_id` bigint NOT NULL AUTO_INCREMENT COMMENT '用户ID',
  `dept_id` bigint DEFAULT NULL COMMENT '部门ID',
  `user_name` varchar(30) NOT NULL COMMENT '用户账号',
  `nick_name` varchar(30) NOT NULL COMMENT '用户昵称',
  `user_type` varchar(2) DEFAULT '00' COMMENT '用户类型（00系统用户）',
  `email` varchar(50) DEFAULT '' COMMENT '用户邮箱',
  `phonenumber` varchar(11) DEFAULT '' COMMENT '手机号码',
  `sex` char(1) DEFAULT '0' COMMENT '用户性别（0男 1女 2未知）',
  `avatar` varchar(100) DEFAULT '' COMMENT '头像地址',
  `password` varchar(100) DEFAULT '' COMMENT '密码',
  `status` char(1) DEFAULT '0' COMMENT '帐号状态（0正常 1停用）',
  `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0代表存在 2代表删除）',
  `login_ip` varchar(128) DEFAULT '' COMMENT '最后登录IP',
  `login_date` datetime DEFAULT NULL COMMENT '最后登录时间',
  `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `remark` varchar(500) DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='用户信息表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_user_post` (
  `user_id` bigint NOT NULL COMMENT 'ç”¨æˆ·ID',
  `post_id` bigint NOT NULL COMMENT 'å²—ä½ID',
  PRIMARY KEY (`user_id`,`post_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='ç”¨æˆ·ä¸Žå²—ä½å…³è”è¡¨';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_user_role` (
  `user_id` bigint NOT NULL COMMENT 'ç”¨æˆ·ID',
  `role_id` bigint NOT NULL COMMENT 'è§’è‰²ID',
  PRIMARY KEY (`user_id`,`role_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='ç”¨æˆ·å’Œè§’è‰²å…³è”è¡¨';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `tbl_cameras` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ip` varchar(255) DEFAULT NULL,
  `name` varchar(255) DEFAULT NULL,
  `pos_rows` int NOT NULL,
  `pos_cols` int NOT NULL,
  `floorid` int NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `tbl_floors` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) DEFAULT NULL,
  `address` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `tbl_testTexts` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `msg` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `tbl_videos` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) DEFAULT NULL,
  `cameraId` int DEFAULT NULL,
  `position` varchar(255) DEFAULT NULL,
  `createData` date DEFAULT NULL,
  `url` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

