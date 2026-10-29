"""
DBSession 使用示例

演示如何在项目中使用数据库会话保持类进行数据插入
"""

from datetime import datetime
from base.postgresql.db_session import DBSession

# 创建数据库会话实例（单例模式，只需创建一次）
# 默认连接参数：host="localhost", port=5432, database="postgres", user="root", password="123456"
db = DBSession(
    host="localhost",
    port=5432,
    database="postgres",
    user="root",
    password="123456"
)

# ==================== 示例1: 插入摄像头记录 ====================
camera_id = db.insert_camera(
    camera_code="CAM01",
    name="实验室A门口摄像头",
    location="实验室A门口",
    vendor="海康威视",
    model="DS-2CD2T47G1-L",
    stream_uri="rtsp://192.168.1.100:554/stream1",
    timezone="Asia/Singapore",
    calibration={"world_x": 100, "world_y": 200},
    meta={"resolution": "1920x1080", "fps": 25}
)
print(f"插入摄像头记录，ID: {camera_id}")

# ==================== 示例2: 插入流/任务实例记录 ====================
stream_id = db.insert_camera_stream(
    camera_id=camera_id,
    stream_name="camera_1_reid",
    task_type="reid",
    shm_name="/dev/shm/camera_1_reid",
    zmq_addr="ipc:///tmp/py_ai_reid.ipc",
    is_active=True,
    meta={"confidence_threshold": 0.85, "model_version": "v1.0"}
)
print(f"插入流记录，ID: {stream_id}")

# ==================== 示例3: 插入媒体资产记录 ====================
media_id = db.insert_media_asset(
    stream_id=stream_id,
    asset_type="segment",
    start_ts=datetime.now(),
    duration_ms=60000,  # 60秒
    play_url="https://example.com/video/segment_001.mp4",
    oss_bucket="video-bucket",
    oss_key="segments/2024/01/01/segment_001.mp4",
    content_type="video/mp4",
    meta={"fps": 25, "resolution": "1920x1080", "bitrate": 2000}
)
print(f"插入媒体资产记录，ID: {media_id}")

# ==================== 示例4: 插入轨迹记录 ====================
# 注意：embedding需要是512维的列表
embedding = [0.1] * 512  # 示例embedding，实际应该是真实的512维向量

tracklet_id = db.insert_tracklet(
    stream_id=stream_id,
    start_ts=datetime.now(),
    cls_name="person",
    quality=0.95,
    query_asset_id=media_id,
    gallery_similarity=0.92,
    repr_embedding=embedding,
    embedding_model="CLIP-ReID-ViT-B-16",
    trajectory_points={
        "points": [
            {"x": 100, "y": 200, "ts": "2024-01-01T10:00:00"},
            {"x": 150, "y": 250, "ts": "2024-01-01T10:00:01"}
        ]
    },
    keyframes={
        "frames": [
            {"bbox": [100, 200, 200, 400], "snapshot_asset_id": media_id}
        ]
    },
    meta={"tracker_ids": [1, 2, 3], "algorithm_version": "v1.0"}
)
print(f"插入轨迹记录，ID: {tracklet_id}")

# ==================== 示例5: 插入内部人员库记录 ====================
reid_target_id = db.insert_reid_target(
    name="张三",
    embedding=embedding,  # 512维向量
    embedding_model="CLIP-ReID-ViT-B-16",
    employee_id="EMP001",
    source_asset_id=media_id,
    is_active=True
)
print(f"插入内部人员记录，ID: {reid_target_id}")

# ==================== 示例6: 插入陌生人库记录 ====================
stranger_id = db.insert_stranger_target(
    code="STR-000001",
    status="new",
    embedding=embedding,  # 512维向量
    embedding_model="CLIP-ReID-ViT-B-16",
    is_active=True
)
print(f"插入陌生人记录，ID: {stranger_id}")

# ==================== 示例7: 插入ReID匹配结果记录 ====================
reid_match_id = db.insert_reid_match(
    tracklet_id=tracklet_id,
    ts=datetime.now(),
    similarity=0.92,
    threshold=0.85,
    matched=True,
    target_id=reid_target_id,
    query_asset_id=media_id,
    evidence_asset_id=media_id,
    meta={"processing_time_ms": 150, "model_version": "v1.0"}
)
print(f"插入ReID匹配记录，ID: {reid_match_id}")

# ==================== 示例8: 插入事件容器记录 ====================
episode_id = db.insert_episode(
    start_ts=datetime.now(),
    status="open",
    title="实验室A异常事件",
    main_target_id=reid_target_id,
    meta={"event_type": "unauthorized_access", "severity": "high"}
)
print(f"插入事件记录，ID: {episode_id}")

# ==================== 示例9: 插入Episode-Tracklet关联 ====================
link_id = db.insert_episode_tracklet_link(
    episode_id=episode_id,
    tracklet_id=tracklet_id,
    role="primary",
    note="主要轨迹"
)
print(f"插入Episode-Tracklet关联，ID: {link_id}")

# ==================== 示例10: 插入Episode-Media关联 ====================
media_link_id = db.insert_episode_media_link(
    episode_id=episode_id,
    media_asset_id=media_id,
    role="recording",
    note="事件录像"
)
print(f"插入Episode-Media关联，ID: {media_link_id}")

# ==================== 示例11: 插入LLM报告记录 ====================
llm_report_id = db.insert_llm_report(
    episode_id=episode_id,
    report_json={
        "summary": "检测到未授权人员进入实验室A",
        "details": "时间：2024-01-01 10:00:00，位置：实验室A门口",
        "recommendations": ["加强门禁管理", "检查监控系统"]
    },
    prompt_version="v1.0",
    report_text="检测到未授权人员进入实验室A，建议加强门禁管理。"
)
print(f"插入LLM报告记录，ID: {llm_report_id}")

# ==================== 使用完成后关闭连接池（可选） ====================
# db.close()  # 通常在程序退出时调用

