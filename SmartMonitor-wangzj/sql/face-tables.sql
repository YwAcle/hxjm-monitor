/*
 Navicat Premium Data Transfer

 Source Server Type    : MySQL
 Source Server Version : 80043 (8.0.43-0ubuntu0.22.04.1)
 File Encoding         : 65001

 Date: 25/11/2025 15:00:00
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

USE hxjm_sm;

-- ----------------------------
-- Table structure for face_person
-- ----------------------------
DROP TABLE IF EXISTS `face_person`;
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
  KEY `idx_face_id` (`face_id`),
  KEY `idx_user_name` (`user_name`),
  KEY `idx_person_type` (`person_type`),
  KEY `idx_dept_id` (`dept_id`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='正式人员表';

INSERT INTO `face_person`
  (`id`, `face_id`, `user_name`, `face_encoding`, `face_image`, `face_image_thumbnail`,
   `metadata`, `status`, `gender`, `age`, `quality`,
   `person_type`, `job_no`, `id_card`, `phone`, `location`,
   `dept_id`, `dept_name`, `remark`, `create_time`, `update_time`)
VALUES
  (1, 'F123456', '张三', NULL, '/images/person/zhangsan.jpg', '/images/person/zhangsan_thumb.jpg',
   '{"source":"mock"}', 1, 1, 28, 0.97,
   'EMPLOYEE', '2023001', 'ID1234567890', '13800001234', '技术部A区',
   101, '技术部', '测试人员1', '2025-12-14 21:31:07', '2025-12-15 11:20:13'),
  (2, 'F123457', '李四', NULL, '/images/person/lisi.jpg', '/images/person/lisi_thumb.jpg',
   '{"source":"mock"}', 1, 2, 25, 0.93,
   'VISITOR', NULL, NULL, '13900001235', '行政部前台',
   102, '行政部', '测试人员2', '2025-12-14 21:31:07', '2025-12-14 21:31:07'),
  (3, 'F123458', '王五', NULL, '/images/person/wangwu.jpg', '/images/person/wangwu_thumb.jpg',
   '{"source":"mock"}', 1, 1, 32, 0.88,
   'EMPLOYEE', '2023010', 'ID1234500010', '13700001236', '研发部B区',
   103, '研发部', '测试人员3', '2025-12-14 21:31:07', '2025-12-14 21:31:07');

-- ----------------------------
-- Table structure for face_stranger
-- ----------------------------
DROP TABLE IF EXISTS `face_stranger`;
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
  KEY `idx_face_id` (`face_id`),
  KEY `idx_display_name` (`display_name`),
  KEY `idx_status` (`status`),
  KEY `idx_last_seen_time` (`last_seen_time`),
  KEY `idx_bind_person_id` (`bind_person_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='陌生人表';

INSERT INTO `face_stranger`
  (`id`, `face_id`, `display_name`, `face_encoding`, `face_image`, `face_image_thumbnail`,
   `metadata`, `status`, `gender`, `age`, `quality`,
   `first_seen_time`, `last_seen_time`, `seen_count`, `bind_person_id`,
   `remark`, `create_time`, `update_time`)
VALUES
  (1, NULL, '陌生人_20250101_101010', NULL, '/images/stranger/s1.jpg', '/images/stranger/s1_thumb.jpg',
   '{"source":"mock"}', 'PENDING', 0, 13, 0.72,
   '2025-12-14 21:31:07', '2025-12-14 21:31:07', 1, NULL,
   '首次出现', '2025-12-14 21:31:07', '2025-12-15 11:19:20'),
  (2, 'S987654', '陌生人_20250102_142300', NULL, '/images/stranger/s2.jpg', '/images/stranger/s2_thumb.jpg',
   '{"source":"mock"}', 'CONFIRMED', 2, 22, 0.81,
   '2025-12-14 21:31:07', '2025-12-14 21:31:07', 3, NULL,
   '重复出现', '2025-12-14 21:31:07', '2025-12-14 21:31:07'),
  (3, 'S987655', '陌生人_20250103_093000', NULL, '/images/stranger/s3.jpg', '/images/stranger/s3_thumb.jpg',
   '{"source":"mock"}', 'IGNORED', 0, 0, 0.65,
   '2025-12-14 21:31:07', '2025-12-14 21:31:07', 1, NULL,
   '低质量忽略', '2025-12-14 21:31:07', '2025-12-14 21:31:07');
SET FOREIGN_KEY_CHECKS = 1;
