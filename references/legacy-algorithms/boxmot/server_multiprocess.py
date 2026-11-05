#!/usr/bin/env python3
"""
BoxMOT 行人跟踪 AI 服务 - 多进程版本
纯 ReID 特征匹配实现跨进程的全局行人 ID
"""

import os
import sys
import cv2
import logging
import numpy as np
import torch
import torchvision
from pathlib import Path
import time
import json
import fcntl
import threading
import gc
import traceback
import signal
import psutil
from scipy.optimize import linear_sum_assignment  # 匈牙利算法

# 优化 Python GC：减少自动垃圾回收频率，避免卡顿
gc.set_threshold(50000, 10, 10)  # 大幅提高触发阈值（默认700,10,10）

# 性能监控
ENABLE_PERFORMANCE_MONITOR = os.getenv("BOXMOT_PERF_MONITOR", "0") == "1"
ENABLE_SLOW_FRAME_ANALYSIS = os.getenv("BOXMOT_SLOW_FRAME_ANALYSIS", "1") == "1"

# GC 回调：监控垃圾回收
_gc_stats = {"count": 0, "total_time": 0.0, "last_time": 0.0}

def _gc_callback(phase, info):
    """GC 回调函数，记录垃圾回收时间"""
    if phase == "start":
        _gc_stats["_start_time"] = time.time()
        logger.print(f"[GC-START] Starting GC (generation={info.get('generation', '?')})")
    elif phase == "stop":
        if "_start_time" in _gc_stats:
            elapsed = time.time() - _gc_stats["_start_time"]
            _gc_stats["count"] += 1
            _gc_stats["total_time"] += elapsed
            _gc_stats["last_time"] = elapsed
            if elapsed > 10.0:  # GC超过10秒，极度严重
                logger.print(f"[GC] 🔥🔥🔥 CATASTROPHIC GC: {elapsed:.3f}s (generation={info.get('generation', '?')}) - THIS IS THE STUTTER!")
            elif elapsed > 1.0:  # GC超过1秒，严重
                logger.print(f"[GC] 🔥 CRITICAL GC: {elapsed:.3f}s (generation={info.get('generation', '?')})")
            elif elapsed > 0.1:  # GC超过100ms，警告
                logger.print(f"[GC] ⚠️  Slow GC: {elapsed:.3f}s (generation={info.get('generation', '?')})")
            else:
                logger.print(f"[GC-STOP] Finished GC in {elapsed:.3f}s (generation={info.get('generation', '?')})")
            del _gc_stats["_start_time"]

# 注册 GC 回调
gc.callbacks.append(_gc_callback)

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from base.server_base import BaseServer
from base.shm_utils import open_and_map, close_map
from base.sys_monitor import print_memory_warning, print_shm_info
import multiprocessing as mp
from base.logger import ServiceLogger
from boxmot import create_tracker, get_tracker_config

# 日志器
logger = ServiceLogger("boxmot_mp", __file__)

# 关闭多余日志
logging.getLogger("ultralytics").setLevel(logging.ERROR)

DEFAULT_IPC_ADDR = "ipc:///tmp/py_ai_boxmot.ipc"
DEFAULT_TRACKER_TYPE = "hybridsort"
DEFAULT_REID_WEIGHTS = "./weights/clip_market1501.pt"
DEFAULT_CONFIDENCE_THRESHOLD = 0.4  # 从 0.2 降低到 0.15，增加检测数量
DEFAULT_DETECTOR = "./weights/yolov8s.pt"  # 使用 YOLO，比 FasterRCNN 快 5-10 倍

# ReID 匹配参数
REID_MATCH_THRESHOLD = 0.50   # 特征匹配阈值
FEATURE_EXPIRE_SECONDS = 120  # 人离开后保留时间
SYNC_INTERVAL = 10  # 同步间隔（秒），减少文件IO频率
CLEANUP_INTERVAL = 60 # 清理过期数据的间隔（秒），大幅减少清理频率
DEBUG_REID = os.getenv("BOXMOT_DEBUG_REID", "1") == "1"  # 通过环境变量控制

# ========== 独立共享内存架构说明 ==========
# C++ 端每个线程使用不同的共享内存名称（已包含 threadId）：
# - 线程0: /ai_stream_camera_1_boxmot_0
# - 线程1: /ai_stream_camera_1_boxmot_1
# Python 端根据 meta["shmName"] 读取对应的共享内存，零竞争，无需加锁

def gpu_mem_mb():
    """返回当前 GPU 显存占用 (MB)"""
    if torch.cuda.is_available():
        return torch.cuda.memory_allocated() / 1024 / 1024
    return 0


# ========== 全局 ID 管理器（track → person 绑定 + 轨迹记录）==========
class ReIDPersonManager:
    """
    基于 ReID 特征的行人身份管理器
    
    核心逻辑：
    - track 出生时做一次 ReID，绑定 person_id
    - 多个临时 track 可能对应同一个 person（通过 ReID 关联）
    - 轨迹（Trajectory）记录一个人从出现到消失的完整轨迹
    
    数据结构：
    - persons: {person_id: {feature, last_seen}} - 行人特征库
    - trajectories: {trajectory_id: {person_id, start_time, end_time}} - 轨迹记录
    - track_map: 进程内临时，不持久化
    """
    
    DATA_FILE = "/tmp/boxmot_person_db.json"
    LOCK_FILE = "/tmp/boxmot_person.lock"
    TRAJECTORY_INACTIVE_SECONDS = 5  # 超过这个时间未更新，认为轨迹结束
    
    def __init__(self):
        self._local_lock = threading.Lock()
        self._cache = None  # 内存缓存
        self._track_map = {}  # 进程内临时: {composite_tid: {person_id, trajectory_id}}
        self._last_sync = 0
        self._last_cleanup = 0  # 最后一次清理时间
        self._load_cache()
    
    def _load_cache(self):
        """从文件加载到内存缓存（不加锁，调用者负责加锁）"""
        t_start = time.time()
        try:
            if os.path.exists(self.DATA_FILE):
                t_exists = time.time()
                with open(self.DATA_FILE, 'r') as f:
                    self._cache = json.load(f)
                t_load = time.time()
                # 确保字段完整
                if 'next_trajectory_id' not in self._cache:
                    self._cache['next_trajectory_id'] = 1
                if 'trajectories' not in self._cache:
                    self._cache['trajectories'] = {}
                t_end = time.time()
                
                if ENABLE_SLOW_FRAME_ANALYSIS and (t_end - t_start) > 0.05:
                    logger.print(f"[SLOW-LOAD-CACHE] _load_cache: total={t_end-t_start:.3f}s "
                          f"(check={t_exists-t_start:.3f} json_load={t_load-t_exists:.3f} validate={t_end-t_load:.3f})", 
                          flush=True)
                    pass
            else:
                self._cache = {
                    'next_id': 1,  # next_person_id
                    'next_trajectory_id': 1,
                    'persons': {},
                    'trajectories': {}
                }
        except Exception as e:
            t_end = time.time()
            if ENABLE_SLOW_FRAME_ANALYSIS and (t_end - t_start) > 0.05:
                logger.print(f"[SLOW-LOAD-CACHE] _load_cache error: {e}, took {t_end-t_start:.3f}s")
            self._cache = {
                'next_id': 1,
                'next_trajectory_id': 1,
                'persons': {},
                'trajectories': {}
            }
    
    def _sync_to_file(self, blocking: bool = True):
        """同步内存缓存到文件"""
        t_start = time.time()
        t_lock = t_dump = t_end = t_start
        try:
            with open(self.LOCK_FILE, 'w') as lock_f:
                t_open = time.time()
                # 使用非阻塞锁，避免长时间等待
                lock_type = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
                try:
                    fcntl.flock(lock_f, lock_type)
                    t_lock = time.time()
                except BlockingIOError:
                    # 锁被占用，跳过本次同步（下次再同步）
                    if DEBUG_REID:
                        logger.print(f"[ReIDPersonManager] Skipped sync (lock busy)")
                    return
                
                try:
                    with open(self.DATA_FILE, 'w') as f:
                        json.dump(self._cache, f)
                    t_dump = time.time()
                finally:
                    fcntl.flock(lock_f, fcntl.LOCK_UN)
                    t_end = time.time()
                
                if ENABLE_SLOW_FRAME_ANALYSIS and (t_end - t_start) > 0.05:
                    logger.print(f"[SLOW-SYNC] _sync_to_file: total={t_end-t_start:.3f}s "
                          f"(open={t_open-t_start:.3f} lock={t_lock-t_open:.3f} dump={t_dump-t_lock:.3f} unlock={t_end-t_dump:.3f})", 
                          flush=True)
                    pass
        except Exception as e:
            t_end = time.time()
            if ENABLE_SLOW_FRAME_ANALYSIS and (t_end - t_start) > 0.05:
                logger.print(f"[SLOW-SYNC] _sync_to_file error: {e}, took {t_end-t_start:.3f}s")
            logger.print(f"[ReIDPersonManager] sync error: {e}")
    def _maybe_sync(self, force: bool = False):
        """定期同步（使用非阻塞模式）"""
        now = time.time()
        if force or (now - self._last_sync > SYNC_INTERVAL):
            self._sync_to_file(blocking=force)  # 定期同步使用非阻塞模式
            self._last_sync = now
    
    @staticmethod
    def _batch_cosine_similarity(features: np.ndarray, stored_features: np.ndarray) -> np.ndarray:
        """
        批量计算余弦相似度矩阵
        
        Args:
            features: (N, dim) 查询特征
            stored_features: (M, dim) 存储的特征
        Returns:
            similarity_matrix: (N, M) 相似度矩阵
        """
        if len(features) == 0 or len(stored_features) == 0:
            return np.zeros((len(features), len(stored_features)), dtype=np.float32)
        
        # 归一化
        features_norm = features / (np.linalg.norm(features, axis=1, keepdims=True) + 1e-6)
        stored_norm = stored_features / (np.linalg.norm(stored_features, axis=1, keepdims=True) + 1e-6)
        
        # 批量计算余弦相似度
        similarity_matrix = np.dot(features_norm, stored_norm.T)
        
        return similarity_matrix
    
    @staticmethod
    def _iou(box1: np.ndarray, box2: np.ndarray) -> float:
        """计算 IOU"""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - inter
        
        return inter / union if union > 0 else 0.0
    
    def _cleanup_expired(self, current_time: float, force: bool = False):
        """清理过期的人（只在必要时执行）"""
        # 只在超过清理间隔时才执行，避免频繁清理
        if not force and current_time - self._last_cleanup < CLEANUP_INTERVAL:
            return
        
        self._last_cleanup = current_time
        expired = []
        for pid_str, person_data in self._cache['persons'].items():
            if current_time - person_data['last_seen'] > FEATURE_EXPIRE_SECONDS:
                expired.append(pid_str)
        
        if len(expired) > 0:
            for pid_str in expired:
                del self._cache['persons'][pid_str]
            if DEBUG_REID:
                logger.print(f"[ReIDPersonManager] Cleaned up {len(expired)} expired persons")
    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """计算余弦相似度"""
        a = a.flatten()
        b = b.flatten()
        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a < 1e-6 or norm_b < 1e-6:
            return 0.0
        return float(dot / (norm_a * norm_b))
    
    def get_or_create_person_for_track(self, composite_track_id: str, feature: np.ndarray, box: np.ndarray = None, debug_log: bool = False) -> tuple:
        """
        获取 track 绑定的 person_id 和 trajectory_id（使用批量矩阵计算）
        
        Args:
            composite_track_id: 组合 track_id = "{worker_key}_{track_id}"
            feature: ReID 特征向量
            box: 检测框
            debug_log: 是否输出详细日志
        Returns:
            (person_id, trajectory_id): 绑定的全局唯一行人 ID 和 轨迹 ID
        """
        # 先检查内存缓存
        if composite_track_id in self._track_map:
            info = self._track_map[composite_track_id]
            if debug_log:
                logger.print(f"[ReID] Track {composite_track_id} already bound to person_id={info['person_id']}, traj_id={info['trajectory_id']}")
            return info['person_id'], info['trajectory_id']
        
        current_time = time.time()
        feature = feature.flatten().reshape(1, -1)  # (1, dim)
        feature_norm = np.linalg.norm(feature)
        
        if debug_log:
            logger.print(f"[ReID] Matching track {composite_track_id}, feature_norm={feature_norm:.4f}")
        t_lock_start = time.time()
        with open(self.LOCK_FILE, 'w') as lock_f:
            fcntl.flock(lock_f, fcntl.LOCK_EX)
            t_lock_acquired = time.time()
            
            # 诊断：如果锁等待时间长，输出警告
            lock_wait_time = t_lock_acquired - t_lock_start
            if lock_wait_time > 0.05:  # 降低阈值到50ms
                msg = f"[LOCK-WAIT] Waited {lock_wait_time:.3f}s for file lock (this blocks ALL workers!)"
                logger.print(msg)
                if lock_wait_time > 0.5:
                    logger.info(msg)  # 严重的锁等待写入日志
            try:
                # 重新加载，防止其他进程已修改
                t_reload = time.time()
                self._load_cache()
                t_reload_done = time.time()
                if ENABLE_SLOW_FRAME_ANALYSIS and (t_reload_done - t_reload) > 0.05:
                    logger.print(f"[LOCK-RELOAD] Reloading cache took {t_reload_done - t_reload:.3f}s")
                # 再次检查（可能其他进程刚刚创建）
                if composite_track_id in self._track_map:
                    info = self._track_map[composite_track_id]
                    if debug_log:
                        logger.print(f"[ReID] Track {composite_track_id} bound by another process: person_id={info['person_id']}")
                    return info['person_id'], info['trajectory_id']
                
                # 只在必要时清理过期数据（大幅减少清理频率）
                self._cleanup_expired(current_time, force=False)
                
                # 使用批量矩阵计算相似度
                best_id = None
                best_sim = REID_MATCH_THRESHOLD
                
                n_persons = len(self._cache['persons'])
                if n_persons > 0:
                    # 构建存储特征矩阵
                    person_ids_list = []
                    stored_features_list = []
                    
                    for pid_str, person_data in self._cache['persons'].items():
                        person_ids_list.append(int(pid_str))
                        stored_features_list.append(person_data['feature'])
                    
                    stored_features = np.array(stored_features_list)  # (M, dim)
                    
                    # 批量计算相似度矩阵 (1, M)
                    similarity_matrix = self._batch_cosine_similarity(feature, stored_features)
                    similarities = similarity_matrix[0]  # (M,)
                    
                    if debug_log:
                        logger.print(f"[ReID] Searching in {n_persons} known persons, threshold={REID_MATCH_THRESHOLD:.3f}")
                        logger.print(f"[ReID] Similarity matrix shape: {similarity_matrix.shape}")
                        logger.print(f"[ReID] All similarities:")
                        for pid, sim in zip(person_ids_list, similarities):
                            if sim > 0.3:  # 只显示相似度较高的
                                logger.print(f"[ReID]   P{pid}: sim={sim:.4f}")
                    # 找到最佳匹配
                    best_idx = np.argmax(similarities)
                    best_sim = similarities[best_idx]
                    
                    if best_sim > REID_MATCH_THRESHOLD:
                        best_id = person_ids_list[best_idx]
                
                if best_id is not None:
                    # 匹配成功 - 已知的人
                    person_id = best_id
                    if debug_log:
                        logger.print(f"[ReID] ✓ Matched to existing person_id={person_id}, sim={best_sim:.4f}")
                    self._cache['persons'][str(person_id)]['last_seen'] = current_time
                    if box is not None:
                        self._cache['persons'][str(person_id)]['box'] = box[:4].tolist()
                else:
                    # 新人，分配新 person_id
                    person_id = self._cache['next_id']
                    self._cache['next_id'] += 1
                    new_person = {
                        'feature': feature.flatten().tolist(),
                        'last_seen': current_time
                    }
                    if box is not None:
                        new_person['box'] = box[:4].tolist()
                    self._cache['persons'][str(person_id)] = new_person

                    if debug_log:
                        max_sim = best_sim if n_persons > 0 else 0.0
                        logger.print(f"[ReID] ✗ No match (max_sim={max_sim:.4f} < {REID_MATCH_THRESHOLD:.3f}), created new person_id={person_id}")
                        logger.print(f"[ReID]   Stored feature: norm={feature_norm:.4f}, shape={feature.shape}")
                # 查找该 person 是否有活跃的轨迹
                active_traj_id = self._find_active_trajectory(person_id, current_time)
                
                if active_traj_id is not None:
                    # 有活跃轨迹，更新 end_time
                    trajectory_id = active_traj_id
                    self._cache['trajectories'][str(trajectory_id)]['end_time'] = current_time
                    if debug_log:
                        logger.print(f"[ReID]   Using existing trajectory_id={trajectory_id}")
                else:
                    # 创建新轨迹
                    trajectory_id = self._cache['next_trajectory_id']
                    self._cache['next_trajectory_id'] += 1
                    self._cache['trajectories'][str(trajectory_id)] = {
                        'person_id': person_id,
                        'start_time': current_time,
                        'end_time': current_time
                    }
                    if debug_log:
                        logger.print(f"[ReID]   Created new trajectory_id={trajectory_id}")
                # 绑定 track → (person, trajectory) 到内存
                self._track_map[composite_track_id] = {
                    'person_id': person_id,
                    'trajectory_id': trajectory_id
                }
                
                # 保存到文件
                t_save_start = time.time()
                with open(self.DATA_FILE, 'w') as f:
                    json.dump(self._cache, f)
                t_save_done = time.time()
                
                if ENABLE_SLOW_FRAME_ANALYSIS and (t_save_done - t_save_start) > 0.05:
                    logger.print(f"[LOCK-SAVE] Saving DB took {t_save_done - t_save_start:.3f}s")
                # 验证保存是否成功
                if debug_log:
                    db_person_count = len(self._cache['persons'])
                    saved_person = self._cache['persons'].get(str(person_id))
                    if saved_person:
                        saved_feat = np.array(saved_person['feature'])
                        saved_norm = np.linalg.norm(saved_feat)
                        logger.print(f"[ReID] ✓ Saved to DB, total persons={db_person_count}, "
                              f"person_id={person_id} feature_norm={saved_norm:.4f}, "
                              f"feature_dim={len(saved_feat)}")  # removed flush=True
                    else:
                        logger.print(f"[ReID] ✗ ERROR: Person {person_id} not found in DB after save!")
                return person_id, trajectory_id
            finally:
                fcntl.flock(lock_f, fcntl.LOCK_UN)
    
    def _find_active_trajectory(self, person_id: int, current_time: float) -> int:
        """查找 person 的活跃轨迹（最近更新过的）"""
        for traj_id_str, traj_data in self._cache['trajectories'].items():
            if traj_data['person_id'] == person_id:
                if current_time - traj_data['end_time'] < self.TRAJECTORY_INACTIVE_SECONDS:
                    return int(traj_id_str)
        return None
    
    def get_person_for_track(self, composite_track_id: str) -> tuple:
        """查询 track 绑定的 person_id 和 trajectory_id（仅查询，不创建）"""
        info = self._track_map.get(composite_track_id)
        if info:
            return info['person_id'], info['trajectory_id']
        return None, None
    
    def batch_match_tracks(self, track_list: list, debug_log: bool = False) -> dict:
        """
        批量匹配多个 track（一次锁，批量处理）
        
        Args:
            track_list: [(composite_track_id, feature, box), ...]
            debug_log: 是否输出详细日志
        Returns:
            {composite_track_id: (person_id, trajectory_id), ...}
        """
        if len(track_list) == 0:
            return {}
        
        current_time = time.time()
        results = {}
        
        if debug_log:
            logger.print(f"[ReID-Batch] Processing {len(track_list)} tracks in batch")
        with open(self.LOCK_FILE, 'w') as lock_f:
            fcntl.flock(lock_f, fcntl.LOCK_EX)
            try:
                self._load_cache()
                # 批量匹配时也减少清理频率
                self._cleanup_expired(current_time, force=False)
                
                # 准备批量特征矩阵
                query_features_list = []
                valid_tracks = []
                
                for composite_tid, feature, box in track_list:
                    if feature is not None and len(feature) > 0:
                        query_features_list.append(feature.flatten())
                        valid_tracks.append((composite_tid, feature, box))
                
                if len(valid_tracks) == 0:
                    return {}
                
                query_features = np.array(query_features_list)  # (N, dim)
                
                # 构建存储特征矩阵
                person_ids_list = []
                stored_features_list = []
                
                for pid_str, person_data in self._cache['persons'].items():
                    person_ids_list.append(int(pid_str))
                    stored_features_list.append(person_data['feature'])
                
                # 批量计算相似度矩阵 (N, M)
                if len(person_ids_list) > 0:
                    stored_features = np.array(stored_features_list)  # (M, dim)
                    similarity_matrix = self._batch_cosine_similarity(query_features, stored_features)
                    
                    if debug_log:
                        logger.print(f"[ReID-Batch] Similarity matrix shape: {similarity_matrix.shape}")
                else:
                    similarity_matrix = np.zeros((len(valid_tracks), 0))
                
                # 处理每个 track
                for idx, (composite_tid, feature, box) in enumerate(valid_tracks):
                    if similarity_matrix.shape[1] > 0:
                        similarities = similarity_matrix[idx]  # (M,)
                        best_idx = np.argmax(similarities)
                        best_sim = similarities[best_idx]
                        
                        if best_sim > REID_MATCH_THRESHOLD:
                            person_id = person_ids_list[best_idx]
                            
                            if debug_log:
                                logger.print(f"[ReID-Batch] {composite_tid}: Matched P{person_id}, sim={best_sim:.4f}")
                                                       
                            self._cache['persons'][str(person_id)]['last_seen'] = current_time
                            if box is not None:
                                self._cache['persons'][str(person_id)]['box'] = box[:4].tolist()
                        else:
                            # 创建新人
                            person_id = self._cache['next_id']
                            self._cache['next_id'] += 1
                            self._cache['persons'][str(person_id)] = {
                                'feature': feature.flatten().tolist(),
                                'last_seen': current_time,
                                'box': box[:4].tolist() if box is not None else None
                            }
                            
                            if debug_log:
                                logger.print(f"[ReID-Batch] {composite_tid}: New person P{person_id}, max_sim={best_sim:.4f}")
                    else:
                        # 没有已知人员，创建新人
                        person_id = self._cache['next_id']
                        self._cache['next_id'] += 1
                        self._cache['persons'][str(person_id)] = {
                            'feature': feature.flatten().tolist(),
                            'last_seen': current_time,
                            'box': box[:4].tolist() if box is not None else None
                        }
                        
                        if debug_log:
                            logger.print(f"[ReID-Batch] {composite_tid}: First person P{person_id}")
                    # 查找或创建轨迹
                    active_traj_id = self._find_active_trajectory(person_id, current_time)
                    if active_traj_id is not None:
                        trajectory_id = active_traj_id
                        self._cache['trajectories'][str(trajectory_id)]['end_time'] = current_time
                    else:
                        trajectory_id = self._cache['next_trajectory_id']
                        self._cache['next_trajectory_id'] += 1
                        self._cache['trajectories'][str(trajectory_id)] = {
                            'person_id': person_id,
                            'start_time': current_time,
                            'end_time': current_time
                        }
                    
                    # 绑定到内存
                    self._track_map[composite_tid] = {
                        'person_id': person_id,
                        'trajectory_id': trajectory_id
                    }
                    
                    results[composite_tid] = (person_id, trajectory_id)
                
                # 一次性保存
                with open(self.DATA_FILE, 'w') as f:
                    json.dump(self._cache, f)
                
                if debug_log:
                    logger.print(f"[ReID-Batch] ✓ Saved {len(results)} tracks, DB total={len(self._cache['persons'])} persons")
                return results
            finally:
                fcntl.flock(lock_f, fcntl.LOCK_UN)
    
    def get_or_create_person_for_track_excluding(self, composite_track_id: str, feature: np.ndarray, box: np.ndarray = None, exclude_pids: list = None, debug_log: bool = True) -> tuple:
        """
        获取 track 绑定的 person_id（排除指定的 person_id，用于同一帧内去重，使用批量矩阵计算）
        
        Args:
            composite_track_id: 组合 track_id
            feature: ReID 特征向量
            box: 检测框
            exclude_pids: 要排除的 person_id 列表
            debug_log: 是否输出详细日志
        Returns:
            (person_id, trajectory_id)
        """
        current_time = time.time()
        feature = feature.flatten().reshape(1, -1)  # (1, dim)
        exclude_pids = exclude_pids or []
        
        if debug_log:
            logger.print(f"[ReID-Exclude] Matching track {composite_track_id}, excluding PIDs: {exclude_pids}")
        with open(self.LOCK_FILE, 'w') as lock_f:
            fcntl.flock(lock_f, fcntl.LOCK_EX)
            try:
                self._load_cache()
                # 排除匹配时也减少清理频率
                self._cleanup_expired(current_time, force=False)
                
                # 使用批量矩阵计算相似度（排除指定 person_id）
                best_id = None
                best_sim = REID_MATCH_THRESHOLD
                
                # 构建未排除的特征矩阵
                person_ids_list = []
                stored_features_list = []
                
                for pid_str, person_data in self._cache['persons'].items():
                    person_id = int(pid_str)  # ⚠️ 修复：不要使用 pid 作为变量名，避免混淆
                    if person_id not in exclude_pids:
                        person_ids_list.append(person_id)
                        stored_features_list.append(person_data['feature'])
                
                if len(person_ids_list) > 0:
                    stored_features = np.array(stored_features_list)  # (M, dim)
                    
                    # 批量计算相似度矩阵 (1, M)
                    similarity_matrix = self._batch_cosine_similarity(feature, stored_features)
                    similarities = similarity_matrix[0]  # (M,)
                    
                    if debug_log:
                        logger.print(f"[ReID-Exclude] Searching in {len(person_ids_list)} candidates (excluded {len(exclude_pids)})")
                        logger.print(f"[ReID-Exclude] All similarities:")
                        for pid, sim in zip(person_ids_list, similarities):
                            if sim > 0.3:
                                logger.print(f"[ReID-Exclude]   P{pid}: sim={sim:.4f}")
                    # 找到最佳匹配
                    best_idx = np.argmax(similarities)
                    best_sim = similarities[best_idx]
                    
                    if best_sim > REID_MATCH_THRESHOLD:
                        best_id = person_ids_list[best_idx]
                
                if best_id is not None:
                    person_id = best_id
                    if debug_log:
                        logger.print(f"[ReID-Exclude] ✓ Matched to person_id={person_id}, sim={best_sim:.4f}")
                                       
                    self._cache['persons'][str(person_id)]['last_seen'] = current_time
                    if box is not None:
                        self._cache['persons'][str(person_id)]['box'] = box[:4].tolist()
                else:
                    # 新人，分配新 person_id
                    person_id = self._cache['next_id']
                    self._cache['next_id'] += 1
                    new_person = {
                        'feature': feature.flatten().tolist(),
                        'last_seen': current_time
                    }
                    if box is not None:
                        new_person['box'] = box[:4].tolist()
                    self._cache['persons'][str(person_id)] = new_person
                    
                    if debug_log:
                        logger.print(f"[ReID-Exclude] ✗ No match, created new person_id={person_id}")
                # 查找或创建轨迹
                active_traj_id = self._find_active_trajectory(person_id, current_time)
                
                if active_traj_id is not None:
                    trajectory_id = active_traj_id
                    self._cache['trajectories'][str(trajectory_id)]['end_time'] = current_time
                else:
                    trajectory_id = self._cache['next_trajectory_id']
                    self._cache['next_trajectory_id'] += 1
                    self._cache['trajectories'][str(trajectory_id)] = {
                        'person_id': person_id,
                        'start_time': current_time,
                        'end_time': current_time
                    }
                
                # 绑定到内存
                self._track_map[composite_track_id] = {
                    'person_id': person_id,
                    'trajectory_id': trajectory_id
                }
                
                # 保存
                with open(self.DATA_FILE, 'w') as f:
                    json.dump(self._cache, f)
                
                # 验证保存
                if debug_log:
                    saved_person = self._cache['persons'].get(str(person_id))
                    if saved_person:
                        saved_feat = np.array(saved_person['feature'])
                        saved_norm = np.linalg.norm(saved_feat)
                        logger.print(f"[ReID-Exclude] ✓ Saved person_id={person_id}, feature_norm={saved_norm:.4f}")
                    else:
                        logger.print(f"[ReID-Exclude] ✗ ERROR: Person {person_id} not found after save!")
                return person_id, trajectory_id
            finally:
                fcntl.flock(lock_f, fcntl.LOCK_UN)
    
    def update_trajectory(self, person_id: int, trajectory_id: int, box: np.ndarray):
        """更新轨迹的 end_time 和 person 位置（只更新内存，不同步文件）"""
        current_time = time.time()
        pid_str = str(person_id)
        traj_str = str(trajectory_id)
        
        # 更新内存
        if pid_str in self._cache['persons']:
            self._cache['persons'][pid_str]['box'] = box[:4].tolist()
            self._cache['persons'][pid_str]['last_seen'] = current_time
        
        if traj_str in self._cache['trajectories']:
            self._cache['trajectories'][traj_str]['end_time'] = current_time
        
        # 不在这里同步文件，避免频繁I/O（只在创建新人时同步）
        
    def get_db_stats(self) -> dict:
        """获取数据库统计信息"""
        t_start = time.time()
        with self._local_lock:
            t_lock = time.time()
            self._load_cache()
            t_load = time.time()
            result = {
                'total_persons': len(self._cache.get('persons', {})),
                'total_trajectories': len(self._cache.get('trajectories', {})),
                'next_person_id': self._cache.get('next_id', 1),
                'next_trajectory_id': self._cache.get('next_trajectory_id', 1),
                'person_ids': list(self._cache.get('persons', {}).keys())
            }
            t_end = time.time()
            
            if ENABLE_SLOW_FRAME_ANALYSIS and (t_end - t_start) > 0.05:
                logger.print(f"[SLOW-DB-STATS] get_db_stats: total={t_end-t_start:.3f}s "
                      f"(lock={t_lock-t_start:.3f} load={t_load-t_lock:.3f} build={t_end-t_load:.3f})", 
                      flush=True)
                pass
            return result
    
    @staticmethod
    def reset():
        """重置数据"""
        data = {
            'next_id': 1,
            'next_trajectory_id': 1,
            'persons': {},
            'trajectories': {}
        }
        try:
            with open(ReIDPersonManager.LOCK_FILE, 'w') as lock_f:
                fcntl.flock(lock_f, fcntl.LOCK_EX)
                try:
                    with open(ReIDPersonManager.DATA_FILE, 'w') as f:
                        json.dump(data, f)
                finally:
                    fcntl.flock(lock_f, fcntl.LOCK_UN)
        except Exception as e:
            logger.print(f"[ReIDPersonManager] Reset failed: {e}")
        logger.print("[ReIDPersonManager] Data reset.")


# ========== ReID 特征提取器 ==========
class ReIDExtractor:
    """ReID 特征提取器"""
    def __init__(self, weights_path: str, device: str):
        from boxmot.reid.core.auto_backend import ReidAutoBackend
        
        reid_device = 0 if device == "cuda" else "cpu"
        self.model = ReidAutoBackend(
            weights=Path(weights_path),
            device=reid_device,
            half=False
        ).model
        logger.print(f"[BoxMOTServer-MP] ReID weights: {weights_path}")
        self.device = device
    
    def extract(self, frame: np.ndarray, boxes: np.ndarray) -> np.ndarray:
        """提取 ReID 特征"""
        if len(boxes) == 0:
            return np.empty((0, 512))
        
        features = self.model.get_features(boxes, frame)
        return features


# ========== 工具函数 ==========
def create_optimized_tracker(tracker_type, reid_weights, device):
    """创建跟踪器"""
    reid_path = Path(reid_weights)
    
    if device == "cuda" or device == torch.device("cuda"):
        device = 0
    
    if tracker_type == 'hybridsort':
        return create_tracker(
            tracker_type='hybridsort',
            tracker_config=None,
            reid_weights=reid_path,
            device=device,
            half=False,
            per_class=False,
        )
    elif tracker_type == 'deepocsort':
        tracker_conf = get_tracker_config('deepocsort')
        return create_tracker(
            tracker_type='deepocsort',
            tracker_config=tracker_conf,
            reid_weights=reid_path,
            device=device,
            half=False,
            per_class=False,
        )
    elif tracker_type == 'boosttrack':
        return create_tracker(
            tracker_type='boosttrack',
            tracker_config=None,
            reid_weights=reid_path,
            device=device,
            half=False,
            per_class=False,
        )
    elif tracker_type == 'strongsort':
        return create_tracker(
            tracker_type='strongsort',
            tracker_config=None,
            reid_weights=reid_path,
            device=device,
            half=False,
        )
    elif tracker_type == 'bytetrack':
        return create_tracker(
            tracker_type='bytetrack',
            tracker_config=None,
            reid_weights=reid_path,
            device=device,
            half=False,
        )
    else:
        from boxmot import BotSort
        return BotSort(
            reid_weights=reid_path,
            device=device,
            half=False,
            track_high_thresh=0.5,
            track_low_thresh=0.05,
            new_track_thresh=0.8,
            track_buffer=50,
            match_thresh=0.85,
            proximity_thresh=0.6,
            appearance_thresh=0.2,
            cmc_method='ecc',
            with_reid=True,
            max_age=50,
            min_hits=2,
            iou_threshold=0.35,
        )


def apply_nms(dets, nms_thresh=0.4):
    """应用NMS"""
    if len(dets) == 0:
        return dets
    
    boxes = dets[:, :4]
    scores = dets[:, 4]
    
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        
        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter)
        
        inds = np.where(iou <= nms_thresh)[0]
        order = order[inds + 1]
    
    return dets[keep]


def id_to_color(person_id):
    """person_id 到颜色（稳定）"""
    np.random.seed(int(person_id) % 10000)
    return tuple(np.random.randint(0, 255, 3).tolist())


def draw_persons(frame, boxes, person_ids, confs):
    """绘制行人（使用 person_id）"""
    if len(boxes) == 0:
        return frame
    
    for i in range(len(boxes)):
        x1, y1, x2, y2 = map(int, boxes[i][:4])
        person_id = person_ids[i]
        conf = confs[i] if i < len(confs) else 1.0
        
        color = id_to_color(person_id)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        
        label = f'P{person_id}'
        label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.rectangle(frame, (x1, y1 - label_size[1] - 10), 
                     (x1 + label_size[0] + 4, y1), color, -1)
        cv2.putText(frame, label, (x1 + 2, y1 - 5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    
    return frame


# ========== 全局管理器（单例）==========
_person_manager = None


def get_person_manager():
    global _person_manager
    if _person_manager is None:
        _person_manager = ReIDPersonManager()
    return _person_manager


# ========== 性能监控线程 ==========
class PerformanceMonitor:
    """性能监控器，定期报告 GC 和系统状态"""
    
    def __init__(self, interval: int = 60):
        self.interval = interval
        self.running = False
        self.thread = None
    
    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        logger.print(f"[PerfMonitor] Started (interval={self.interval}s)")
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
    
    def _monitor_loop(self):
        while self.running:
            time.sleep(self.interval)
            self._report()
    
    def _report(self):
        """报告性能统计"""
        try:
            # GC 统计
            gc_stats = gc.get_stats()
            gc_count = gc.get_count()
            
            # GPU 显存
            gpu_mem = gpu_mem_mb()
            
            # 进程内存
            try:
                import psutil
                process = psutil.Process(os.getpid())
                mem_info = process.memory_info()
                rss_mb = mem_info.rss / 1024 / 1024
                logger.print(f"[PerfMonitor] GC count: {gc_count}, GPU: {gpu_mem:.0f}MB, RAM: {rss_mb:.0f}MB")
            except ImportError:
                logger.print(f"[PerfMonitor] GC count: {gc_count}, GPU: {gpu_mem:.0f}MB")
            # 如果 GC 触发过多，警告
            if gc_count[0] > 40000:
                logger.print(f"[PerfMonitor] ⚠️  GC gen0 count high: {gc_count[0]}, consider manual gc.collect()")
        except Exception as e:
            logger.print(f"[PerfMonitor] Error: {e}")

class BoxMOTMultiProcessServer(BaseServer):
    def __init__(self):
        addr = os.getenv("BOXMOT_ZMQ_ADDR", DEFAULT_IPC_ADDR)
        super().__init__(addr)
        self._last_frame_time = {}  # 记录每个worker的最后帧时间，用于诊断
    
    @staticmethod
    def init_model_context():
        pid = os.getpid()
        logger.print(f"[PID:{pid}] [BoxMOT-MP] CUDA: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            logger.print(f"[PID:{pid}] [BoxMOT-MP] GPU: {torch.cuda.get_device_name(0)}")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        device_id = 0 if device == "cuda" else "cpu"
        
        # 使用 YOLO 检测器（比 FasterRCNN 快 5-10 倍）
        detector_model = os.getenv("BOXMOT_DETECTOR", DEFAULT_DETECTOR)
        logger.print(f"[PID:{pid}] [BoxMOT-MP] Loading detector ({detector_model})...")
        from boxmot.detectors.ultralytics import UltralyticsYolo
        detector = UltralyticsYolo(
            path=detector_model,
            device=device_id,
            conf=float(os.getenv("BOXMOT_CONFIDENCE_THRESHOLD", DEFAULT_CONFIDENCE_THRESHOLD)),
            iou=0.35,  # NMS IOU阈值，0.35可以保留更多重叠框
            imgsz=640  # 输入图像尺寸（640=快速，1280=高精度但慢4倍）
        )
        
        tracker_type = os.getenv("BOXMOT_TRACKER_TYPE", DEFAULT_TRACKER_TYPE)
        reid_weights = os.getenv("BOXMOT_REID_WEIGHTS", DEFAULT_REID_WEIGHTS)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # reid_path = os.path.join(script_dir, reid_weights) if not os.path.isabs(reid_weights) else reid_weights
        reid_path = reid_weights
        logger.print(f"[PID:{pid}] [BoxMOT-MP] Loading tracker: {tracker_type}, reid: {reid_path}")
        tracker = create_optimized_tracker(tracker_type, reid_path, device)
        
        logger.print(f"[PID:{pid}] [BoxMOT-MP] Loading ReID extractor...")
        reid_extractor = ReIDExtractor(reid_path, device)
        
        conf_thresh = float(os.getenv("BOXMOT_CONFIDENCE_THRESHOLD", DEFAULT_CONFIDENCE_THRESHOLD))
        
        logger.print(f"[PID:{pid}] [BoxMOT-MP] Warming up...")
        dummy = np.zeros((480, 640, 3), dtype=np.uint8)
        _ = detector(dummy, classes=[0])  # class 0 = person
        
        torch.cuda.empty_cache()
        logger.print(f"[PID:{pid}] [BoxMOT-MP] Ready, detector={detector_model}, tracker={tracker_type}")
        
        person_manager = get_person_manager()
        
        return {
            "detector": detector,
            "tracker": tracker,
            "reid_extractor": reid_extractor,
            "device": device,
            "conf_thresh": conf_thresh,
            "person_manager": person_manager,
            "pid": pid
        }
    
    def process_frame(self, meta: dict, model_ctx: dict):
        import time as T
        
        # Ping watchdog：告诉监控线程主线程还活着
        ping_watchdog()

        # ========== 完整时间追踪 ==========
        t_function_entry = T.time()  # 函数入口时间（真正的开始）
        t0 = T.time()  # 将在共享内存操作前重新设置
        t_checkpoint = t_function_entry  # 用于检测每个阶段的延迟
        
        # 从 Worker 传来的时间信息
        worker_queue_wait = meta.get("_worker_queue_wait", 0)
        worker_gap = meta.get("_worker_gap", 0)
        worker_got_at = meta.get("_worker_got_at", t0)
        
        # 从 worker_got_at 到现在的延迟
        delay_before_process = t0 - worker_got_at
        
        if delay_before_process > 0.1:
            logger.print(f"[DELAY] From worker.get() to process_frame(): {delay_before_process:.3f}s")
        # 检查点1：进入函数
        t_now = T.time()
        if t_now - t_checkpoint > 0.01:
            logger.print(f"[TIME-CHECK] After t0 init: {t_now - t_checkpoint:.3f}s (abs={t_now:.3f})")
        t_checkpoint = t_now
        
        mem0 = gpu_mem_mb()
        pid = os.getpid()

        shm_name = meta.get("shmName", "")
        shm_len = int(meta.get("shmLen", 0))
        width = int(meta.get("width", 0))
        height = int(meta.get("height", 0))
        stride = int(meta.get("stride", width * 3))
        frame_id = meta.get("frameId", "?")  # 帧序号
        timestamp_from_cpp = meta.get("timestamp", 0)  # C++ 端发送时间
        logger.print(f"[PID:{pid}] [BoxMOT-MP] Processing frame: shm={shm_name}, size={width}x{height}")
        # 检查点2：基本变量初始化后
        t_now = T.time()
        if t_now - t_checkpoint > 0.01:
            logger.print(f"[TIME-CHECK] After basic vars: {t_now - t_checkpoint:.3f}s (abs={t_now:.3f})")
        t_checkpoint = t_now
        
        # worker_key 用于多进程区分 track_id（关键：确保不同进程的 track_id 不冲突）
        # 格式：shm_name 或 pid，确保唯一性
        worker_key = shm_name.replace("/", "_").replace(".", "_") if shm_name else f"pid{model_ctx['pid']}"

        # ========== 详细的帧间隔诊断（同时输出到控制台和日志文件）==========
        frame_received_time = t0
        queue_wait_time = 0
        if timestamp_from_cpp > 0:
            queue_wait_time = t0 - timestamp_from_cpp
            if queue_wait_time > 0.5:
                msg = f"[QUEUE-DELAY] Frame {frame_id} waited {queue_wait_time:.3f}s in queue (from C++ {timestamp_from_cpp:.3f} to Python {t0:.3f})"
                logger.print(msg)
                logger.info(msg, pid=pid)  # 也写入日志文件
        
        if worker_key in self._last_frame_time:
            frame_interval = t0 - self._last_frame_time[worker_key]
            # 降低阈值到0.1秒，更敏感地检测卡顿
            if frame_interval > 0.1:
                msg = f"[FRAME-GAP] Frame {frame_id}: {frame_interval:.3f}s since last frame (last was at {self._last_frame_time[worker_key]:.3f}, now {t0:.3f})"
                logger.print(msg)
                logger.info(msg, pid=pid)  # 也写入日志文件
                
                if frame_interval > 1.0:
                    msg2 = f"[FRAME-GAP] ⚠️  LARGE GAP! {frame_interval:.3f}s - this is likely the stutter you're experiencing!"
                    logger.print(msg2)
                    logger.info(msg2, pid=pid)  # 也写入日志文件
        else:
            msg = f"[FRAME-GAP] First frame {frame_id} for worker {worker_key}"
            logger.print(msg)
            logger.info(msg, pid=pid)  # 也写入日志文件
        
        self._last_frame_time[worker_key] = t0
        
        # 检查点3：帧间隔诊断后
        t_now = T.time()
        if t_now - t_checkpoint > 0.01:
            logger.print(f"[TIME-CHECK] After frame gap check: {t_now - t_checkpoint:.3f}s (abs={t_now:.3f})")
        t_checkpoint = t_now

        # 健康检查：记录处理开始
        if DEBUG_REID:
            logger.print(f"[PID:{pid}] [Frame] Processing frame: shm={shm_name}, size={width}x{height}")
        fd, mm, map_len = None, None, 0

        try:
            # 检查点4：准备打开共享内存
            t_now = T.time()
            if t_now - t_checkpoint > 0.01:
                logger.print(f"[TIME-CHECK] Before open_and_map: {t_now - t_checkpoint:.3f}s (abs={t_now:.3f})")
            t_checkpoint = t_now
            
            # ========== 共享内存操作（独立共享内存，无竞争）==========
            # 🎯 每个线程使用独立的共享内存段（shmName 包含 threadId）
            # 例如：/ai_stream_camera_1_boxmot_0, /ai_stream_camera_1_boxmot_1
            
            # 🔍 重要：在这里重新设置 t0，因为前面的 print() 可能阻塞很久
            t_before_all_setup = t_function_entry
            t_setup_duration = T.time() - t_function_entry
            if t_setup_duration > 1.0:
                logger.print(f"[SETUP-SLOW] ⚠️⚠️⚠️ Setup (prints, checks) took {t_setup_duration:.3f}s before SHM! (pid={pid})")
            t_shm_start = T.time()
            t0 = t_shm_start  # 🔥 重新设置 t0 为共享内存操作的真正开始时间
            
            logger.print(f"[SHM-START] Opening independent shm={shm_name} at t={t_shm_start:.3f} (pid={pid}) (setup_delay={t_setup_duration:.3f}s)")
            # 🔍 系统级监控：记录进入 open_and_map 前的时间
            t_before_open_and_map = T.time()
            
            # 直接执行共享内存操作，无需加锁
            fd, mm, map_len = open_and_map(shm_name)
            
            # 🔍 记录 open_and_map 返回后的时间
            t_after_open_and_map = T.time()
            open_and_map_duration = t_after_open_and_map - t_before_open_and_map
            
            if open_and_map_duration > 1.0:
                msg = f"[SHM-CRITICAL] ⚠️⚠️⚠️ open_and_map BLOCKED {open_and_map_duration:.3f}s! (pid={pid} shm={shm_name})"
                logger.print(msg)
                logger.info(msg, pid=pid)
            
            t_shm_open = T.time()
            
            shm_open_duration = t_shm_open - t_shm_start
            if shm_open_duration > 1.0:  # 超过1秒就警告
                msg = f"[SHM-SLOW] ⚠️⚠️⚠️ open_and_map took {shm_open_duration:.3f}s! This is the bottleneck!"
                logger.print(msg)
                logger.info(msg, pid=pid)
                
                # 打印系统资源信息，帮助诊断
                print_memory_warning()
                print_shm_info()
            
            # 检查点5：共享内存打开后
            if shm_open_duration > 0.01:
                logger.print(f"[TIME-CHECK] open_and_map took: {shm_open_duration:.3f}s (abs={t_shm_open:.3f})")
            t_checkpoint = t_shm_open
            
            if fd is None or mm is None:
                logger.print(f"[PID:{pid}] [BoxMOT-MP] ❌ Failed to open shared memory: {shm_name}")
                return  # 静默返回，避免崩溃
            if shm_len <= 0 or shm_len > map_len:
                shm_len = map_len
            
            # 检查点6：准备创建 buffer
            t_now = T.time()
            if t_now - t_checkpoint > 0.01:
                logger.print(f"[TIME-CHECK] Before frombuffer: {t_now - t_checkpoint:.3f}s (abs={t_now:.3f})")
            t_checkpoint = t_now
            
            # 🔍 frombuffer 监控
            t_before_frombuffer = T.time()
            buf = np.frombuffer(mm, dtype=np.uint8, count=height * stride)
            t_after_frombuffer = T.time()
            frombuffer_duration = t_after_frombuffer - t_before_frombuffer
            
            if frombuffer_duration > 1.0:
                msg = f"[FROMBUFFER-CRITICAL] ⚠️⚠️⚠️ frombuffer BLOCKED {frombuffer_duration:.3f}s! (pid={pid})"
                logger.print(msg)
                logger.info(msg, pid=pid)
            
            t_buf_create = T.time()
            
            # 检查点7：frombuffer 后
            if t_buf_create - t_checkpoint > 0.01:
                logger.print(f"[TIME-CHECK] frombuffer took: {t_buf_create - t_checkpoint:.3f}s (abs={t_buf_create:.3f})")
            t_checkpoint = t_buf_create
            
            # 🔍 reshape+copy 监控
            t_before_reshape = T.time()
            frame = buf.reshape((height, stride))[:, :width * 3].reshape((height, width, 3)).copy()
            t_after_reshape = T.time()
            reshape_duration = t_after_reshape - t_before_reshape
            
            if reshape_duration > 1.0:
                msg = f"[RESHAPE-CRITICAL] ⚠️⚠️⚠️ reshape+copy BLOCKED {reshape_duration:.3f}s! (pid={pid})"
                logger.print(msg)
                logger.info(msg, pid=pid)
            
            t1 = T.time()
            
            # 检查点8：copy 后
            if t1 - t_checkpoint > 0.01:
                logger.print(f"[TIME-CHECK] reshape+copy took: {t1 - t_checkpoint:.3f}s (abs={t1:.3f})")
            t_checkpoint = t1
            
            # 🔍 close_map 监控
            t_before_close = T.time()
            close_map(fd, mm)
            t_after_close = T.time()
            close_duration = t_after_close - t_before_close
            
            if close_duration > 1.0:
                msg = f"[CLOSE-CRITICAL] ⚠️⚠️⚠️ close_map BLOCKED {close_duration:.3f}s! (pid={pid})"
                logger.print(msg)
                logger.info(msg, pid=pid)
            
            # 诊断：如果共享内存操作慢，输出详细信息
            buf_time = t_buf_create - t_shm_open
            copy_time = t1 - t_buf_create
            total_read_time = t1 - t_shm_start
            
            if total_read_time > 0.1:  # 超过100ms警告
                logger.print(f"[PID:{pid}] [BoxMOT-MP] ⚠️  Slow frame read: total={total_read_time:.3f}s (open={shm_open_duration:.3f}s, buf={buf_time:.3f}s, copy={copy_time:.3f}s)")
            detector = model_ctx["detector"]
            tracker = model_ctx["tracker"]
            reid_extractor = model_ctx["reid_extractor"]
            person_manager = model_ctx["person_manager"]
            # ⚠️ 不要覆盖 pid 变量！已经在上面用 os.getpid() 设置了
            # pid = model_ctx["pid"]  # 这行导致 pid 被覆盖成其他值
            mem1 = gpu_mem_mb()
            
            # 检测（使用 YOLO，只检测行人 class=0）
            dets = detector(frame, classes=[0])  # 返回 (N, 6): x1,y1,x2,y2,conf,cls
            t2 = T.time()
            mem2 = gpu_mem_mb()
            
            # NMS
            if len(dets) > 0:
                dets = apply_nms(dets, nms_thresh=0.4)
            n_dets = len(dets)
            t3 = T.time()
            
            # 跟踪（获取 track_id）
            tracks = tracker.update(dets, frame)
            t4 = T.time()
            mem3 = gpu_mem_mb()
            n_tracks = len(tracks)
            
            # ========== 快速路径：没有 track 时直接跳过 ==========
            if n_tracks == 0:
                # 空帧，直接绘制并返回
                t5 = t6 = t7 = T.time()
                mem4 = mem5 = mem3
                result = frame  # 不绘制
                
                # 写回
                flat = result.reshape(-1).tobytes()
                mm[:min(len(flat), shm_len)] = flat
                t8 = T.time()
                
                # 检查点：写入共享内存后
                t_now = T.time()
                if t_now - t_checkpoint > 0.01:
                    logger.print(f"[TIME-CHECK] After write to shm: {t_now - t_checkpoint:.3f}s (abs={t_now:.3f})")
                t_checkpoint = t_now
                
                # 获取 DB 统计（打点）
                t_db_start = T.time()
                db_stats = person_manager.get_db_stats()
                t_db_end = T.time()
                
                # 检查点：DB统计后
                if t_db_end - t_checkpoint > 0.01:
                    logger.print(f"[TIME-CHECK] get_db_stats took: {t_db_end - t_checkpoint:.3f}s (abs={t_db_end:.3f})")
                t_checkpoint = t_db_end
                
                log_msg = (f"frame={frame_id} dets={n_dets} tracks=0 reid=0 persons=[] unique=0 trajs=[] | "
                          f"DB: total_persons={db_stats['total_persons']} "
                          f"next_id={db_stats['next_person_id']} | "
                          f"read={t1-t0:.3f}s det={t2-t1:.3f}s nms={t3-t2:.3f}s trk={t4-t3:.3f}s "
                          f"match=0.000s draw=0.000s write={t8-t7:.3f}s "
                          f"total={t8-t0:.3f}s | "
                          f"worker_wait={worker_queue_wait:.3f}s worker_gap={worker_gap:.3f}s queue_wait={queue_wait_time:.3f}s | "
                          f"mem: {mem0:.0f}->{mem5:.0f}MB")
                
                logger.print(f"[PID:{pid}] [BoxMOT-MP] {log_msg}")
                logger.info(log_msg, pid=pid)
                
                # 慢帧剖析（空帧，同时输出到控制台和日志文件）
                # 检查点：准备记录日志
                t_now = T.time()
                if t_now - t_checkpoint > 0.01:
                    logger.print(f"[TIME-CHECK] Before logging (empty): {t_now - t_checkpoint:.3f}s (abs={t_now:.3f})")
                t_checkpoint = t_now
                
                t_end = T.time()
                
                # 检查点：t_end 记录后
                if t_end - t_checkpoint > 0.01:
                    logger.print(f"[TIME-CHECK] ⚠️  HUGE GAP before t_end: {t_end - t_checkpoint:.3f}s (abs={t_end:.3f})")
                # 计算各步骤时间总和
                step_sum = (t1-t0) + (t2-t1) + (t3-t2) + (t4-t3) + (t8-t7) + (t_db_end-t_db_start)
                missing_time = (t_end - t0) - step_sum
                
                if ENABLE_SLOW_FRAME_ANALYSIS and (t_end - t0) > 0.5:
                    slow_msg = (f"[SLOW-EMPTY] total={t_end-t0:.3f}s "
                               f"read={t1-t0:.3f} det={t2-t1:.3f} nms={t3-t2:.3f} trk={t4-t3:.3f} "
                               f"write={t8-t7:.3f} db={t_db_end-t_db_start:.3f} "
                               f"step_sum={step_sum:.3f} missing={missing_time:.3f} | "
                               f"worker_wait={worker_queue_wait:.3f} worker_gap={worker_gap:.3f} queue_wait={queue_wait_time:.3f} | "
                               f"gc_last={_gc_stats['last_time']:.3f}")
                    logger.print(slow_msg)
                    logger.info(slow_msg, pid=pid)  # 也写入日志文件
                
                # 即使不慢，也记录大的 gap
                if worker_gap > 5.0:
                    gap_msg = f"[SLOW-GAP] worker_gap={worker_gap:.3f}s (Worker 等待下一帧的空闲时间 = C++端发送延迟)"
                    logger.print(gap_msg)
                    logger.info(gap_msg, pid=pid)
                
                return  # 快速返回
            
            # ========== 核心：行人 ReID 匹配 + 同一帧内去重（简化版）==========
            person_ids = []
            trajectory_ids = []
            boxes_to_draw = []
            confs_to_draw = []
            reid_count = 0
            track_info_list = []  # 记录每个 track 信息用于去重
            
            # 第一步：收集所有 track 信息
            all_tracks_info = []
            for track in tracks:
                bbox = track[:4]
                track_id = int(track[4])
                conf = float(track[5]) if len(track) > 5 else 1.0
                composite_tid = f"{worker_key}_{track_id}"
                
                # 检查是否已绑定 person_id
                person_id, trajectory_id = person_manager.get_person_for_track(composite_tid)
                
                all_tracks_info.append({
                    'bbox': bbox,
                    'track_id': track_id,
                    'composite_tid': composite_tid,
                    'conf': conf,
                    'person_id': person_id,
                    'trajectory_id': trajectory_id,
                    'is_new': (person_id is None)
                })
            
            if DEBUG_REID and len(all_tracks_info) > 0:
                n_new = sum(1 for t in all_tracks_info if t['is_new'])
                n_exist = len(all_tracks_info) - n_new
                logger.print(f"[PID:{pid}] [Frame] Total tracks={len(all_tracks_info)}, new={n_new}, existing={n_exist}")
            
            # 第二步：批量处理新 track（一次锁，提升性能）
            new_tracks = [item for item in all_tracks_info if item['is_new']]
            
            if len(new_tracks) > 0:
                # 批量提取特征
                try:
                    new_bboxes = np.array([item['bbox'] for item in new_tracks])
                    new_features = reid_extractor.extract(frame, new_bboxes)
                    
                    if DEBUG_REID:
                        logger.print(f"[PID:{pid}] [Frame] Batch extracting features for {len(new_tracks)} new tracks, got {len(new_features)} features")
                except Exception as e:
                    logger.print(f"[PID:{pid}] [Frame] ⚠️  Feature extraction error: {e}")
                    new_features = []
                
                # 构建批量匹配列表
                batch_list = []
                failed_tracks = []
                
                for idx, item in enumerate(new_tracks):
                    try:
                        if idx < len(new_features) and len(new_features[idx]) > 0:
                            batch_list.append((item['composite_tid'], new_features[idx], item['bbox']))
                        else:
                            # 特征提取失败，标记为失败
                            failed_tracks.append(item)
                            if DEBUG_REID:
                                logger.print(f"[PID:{pid}] [Frame] Track {item['composite_tid']} feature extraction failed (idx={idx}, total_features={len(new_features)})")
                    except Exception as e:
                        logger.print(f"[PID:{pid}] [Frame] ⚠️  Error processing track {item['composite_tid']}: {e}")
                        failed_tracks.append(item)
                
                # 批量匹配（一次锁）
                if len(batch_list) > 0:
                    # 检查点：准备批量匹配
                    t_now = T.time()
                    if t_now - t_checkpoint > 0.01:
                        logger.print(f"[TIME-CHECK] Before batch_match_tracks: {t_now - t_checkpoint:.3f}s (abs={t_now:.3f})")
                    t_checkpoint = t_now
                    
                    try:
                        batch_results = person_manager.batch_match_tracks(batch_list, debug_log=DEBUG_REID)
                        reid_count = len(batch_results)
                        
                        # 检查点：批量匹配完成
                        t_now = T.time()
                        if t_now - t_checkpoint > 0.01:
                            logger.print(f"[TIME-CHECK] batch_match_tracks took: {t_now - t_checkpoint:.3f}s (abs={t_now:.3f})")
                        t_checkpoint = t_now

                        # 更新结果
                        for item in new_tracks:
                            if item['composite_tid'] in batch_results:
                                person_id, trajectory_id = batch_results[item['composite_tid']]
                                item['person_id'] = person_id
                                item['trajectory_id'] = trajectory_id
                            elif item not in failed_tracks:
                                # 不在结果中且不在失败列表，说明批量匹配时跳过了
                                # 使用临时 ID
                                item['person_id'] = item['track_id']
                                item['trajectory_id'] = 0
                                if DEBUG_REID:
                                    logger.print(f"[PID:{pid}] [Frame] Track {item['composite_tid']} not in batch results, using temporary ID")
                    except Exception as e:
                        logger.print(f"[PID:{pid}] [Frame] ⚠️  Batch matching error: {e}")
                        # ⚠️  修复：不打印完整的traceback，避免日志过多
                        # traceback.print_exc()
                        # 批量匹配失败，所有 track 使用临时 ID
                        for item in new_tracks:
                            if item['person_id'] is None:
                                item['person_id'] = item['track_id']
                                item['trajectory_id'] = 0
                        logger.print(f"[PID:{pid}] [Frame] ⚠️  Batch matching failed, using {len(new_tracks)} temporary IDs")
                # 处理失败的 track
                for item in failed_tracks:
                    if item['person_id'] is None:
                        item['person_id'] = item['track_id']
                        item['trajectory_id'] = 0
            
            # 第三步：处理已绑定的 track（更新轨迹，批量更新，不同步文件）
            # ⚠️ 重要优化：已存在的track完全不需要文件锁，只更新内存！
            existing_tracks = [item for item in all_tracks_info if not item['is_new']]
            for item in existing_tracks:
                person_manager.update_trajectory(item['person_id'], item['trajectory_id'], item['bbox'])
            
            # 定期同步到文件（非阻塞）- 只在有新track时才同步
            if len(new_tracks) > 0:
                person_manager._maybe_sync(force=False)
            
            # 第四步：收集结果（确保所有值都不是 None）
            for item in all_tracks_info:
                # 安全检查：确保 person_id 和 trajectory_id 不为 None
                if item['person_id'] is None:
                    logger.print(f"[PID:{pid}] [Frame] ⚠️  WARNING: Track {item['composite_tid']} has None person_id, using fallback")
                    item['person_id'] = item['track_id']
                    item['trajectory_id'] = 0
                
                person_ids.append(item['person_id'])
                trajectory_ids.append(item['trajectory_id'])
                boxes_to_draw.append(item['bbox'])
                confs_to_draw.append(item['conf'])
                track_info_list.append(item)
            
            # 第五步：验证 track 绑定的唯一性
            if DEBUG_REID:
                track_bindings = {}
                for item in track_info_list:
                    tid = item['composite_tid']
                    person_id = item['person_id']  # ⚠️ 修复：不要覆盖 pid 变量！
                    if tid in track_bindings and track_bindings[tid] != person_id:
                        logger.print(f"[PID:{pid}] [Frame] ⚠️  Track binding conflict! {tid} was bound to {track_bindings[tid]}, now {person_id}")
                    track_bindings[tid] = person_id
            
            # 第六步：统一去重检查（确保同一帧内没有重复 person_id）
            person_id_to_indices = {}
            for idx, pid in enumerate(person_ids):
                if pid not in person_id_to_indices:
                    person_id_to_indices[pid] = []
                person_id_to_indices[pid].append(idx)
            
            # 检测并批量修复重复
            duplicates_found = []
            for person_id, indices in person_id_to_indices.items():
                if len(indices) > 1:
                    duplicates_found.append((person_id, indices))
            
            if len(duplicates_found) > 0:
                if DEBUG_REID:
                    logger.print(f"[PID:{pid}] [Frame] ⚠️  Found {len(duplicates_found)} duplicate person_ids in frame!")
                # 收集所有需要重新匹配的 track
                rematch_list = []
                rematch_indices = []
                
                for person_id, indices in duplicates_found:
                    if DEBUG_REID:
                        tids = [track_info_list[idx]['composite_tid'] for idx in indices]
                        logger.print(f"[PID:{pid}] [Frame]   Duplicate person_id={person_id} in tracks: {tids}")
                    
                    # 保留第一个，重新匹配其他的
                    for dup_idx in indices[1:]:
                        track_item = track_info_list[dup_idx]
                        rematch_list.append(track_item)
                        rematch_indices.append(dup_idx)
                
                # 批量提取特征
                if len(rematch_list) > 0:
                    rematch_bboxes = np.array([item['bbox'] for item in rematch_list])
                    rematch_features = reid_extractor.extract(frame, rematch_bboxes)
                    
                    if DEBUG_REID:
                        logger.print(f"[PID:{pid}] [Frame] Batch re-extracting features for {len(rematch_list)} duplicate tracks")
                    # 批量重新匹配
                    rematch_batch_list = []
                    for idx, (item, feat_idx) in enumerate(zip(rematch_list, range(len(rematch_features)))):
                        if feat_idx < len(rematch_features) and len(rematch_features[feat_idx]) > 0:
                            composite_tid = item['composite_tid']
                            
                            # 清除旧绑定
                            if composite_tid in person_manager._track_map:
                                del person_manager._track_map[composite_tid]
                            
                            # 排除当前已匹配的所有 person_id
                            exclude_list = list(set(person_ids[:rematch_indices[idx] + 1]))
                            
                            rematch_batch_list.append((composite_tid, rematch_features[feat_idx], item['bbox'], exclude_list))
                    
                    # 使用批量排除匹配
                    if len(rematch_batch_list) > 0:
                        for composite_tid, feat, box, exclude_pids in rematch_batch_list:
                            new_person_id, new_trajectory_id = person_manager.get_or_create_person_for_track_excluding(
                                composite_tid, feat, box, 
                                exclude_pids=exclude_pids, debug_log=DEBUG_REID
                            )
                            
                            # 找到对应的索引并更新
                            for idx, item in enumerate(rematch_list):
                                if item['composite_tid'] == composite_tid:
                                    real_idx = rematch_indices[idx]
                                    person_ids[real_idx] = new_person_id
                                    trajectory_ids[real_idx] = new_trajectory_id
                                    track_info_list[real_idx]['person_id'] = new_person_id
                                    track_info_list[real_idx]['trajectory_id'] = new_trajectory_id
                                    reid_count += 1
                                    
                                    if DEBUG_REID:
                                        logger.print(f"[PID:{pid}] [Frame]   ✓ Re-matched {composite_tid} to new person_id={new_person_id}")
                                    break
            
            t5 = T.time()
            t6 = T.time()
            mem4 = gpu_mem_mb()
            
            # 绘制（使用 person_id）
            result = draw_persons(frame, boxes_to_draw, person_ids, confs_to_draw)
            t7 = T.time()
            
            # ⚠️  移除频繁的 GPU 缓存清理（这是主要卡顿源）
            # 只在显存使用超过阈值时才清理，避免每帧都清理导致卡顿
            mem5 = gpu_mem_mb()
            t_cache_start = T.time()
            if mem5 > 2000:  # 显存超过2GB时才清理
                torch.cuda.empty_cache()
                mem5 = gpu_mem_mb()
            t_cache_end = T.time()
            if ENABLE_SLOW_FRAME_ANALYSIS and (t_cache_end - t_cache_start) > 0.01:
                logger.print(f"[SLOW-CACHE] empty_cache took {t_cache_end - t_cache_start:.3f}s (mem: {mem5:.0f}MB)")
            # 写回
            flat = result.reshape(-1).tobytes()
            mm[:min(len(flat), shm_len)] = flat
            
            person_info = ','.join([str(p) for p in person_ids])
            traj_info = ','.join([str(t) for t in trajectory_ids])
            
            # 检查点：准备获取DB统计
            t_now = T.time()
            if t_now - t_checkpoint > 0.01:
                logger.print(f"[TIME-CHECK] Before get_db_stats: {t_now - t_checkpoint:.3f}s (abs={t_now:.3f})")
            t_checkpoint = t_now
            
            # 获取 DB 统计信息（打点）
            t_db_start = T.time()
            db_stats = person_manager.get_db_stats()
            t_db_end = T.time()
            if ENABLE_SLOW_FRAME_ANALYSIS and (t_db_end - t_db_start) > 0.01:
                logger.print(f"[SLOW-DB] get_db_stats took {t_db_end - t_db_start:.3f}s")
            # 检查点：DB统计后
            if t_db_end - t_checkpoint > 0.01:
                logger.print(f"[TIME-CHECK] get_db_stats took: {t_db_end - t_checkpoint:.3f}s (abs={t_db_end:.3f})")
            t_checkpoint = t_db_end
            
            unique_persons_in_frame = len(set(person_ids))
            
            # 【严格检查】确保同一帧内绝对没有重复的 person_id
            if unique_persons_in_frame < len(person_ids):
                duplicate_pids = [pid for pid in set(person_ids) if person_ids.count(pid) > 1]
                logger.print(f"[PID:{pid}] [BoxMOT-MP] ❌ CRITICAL ERROR: Duplicate person_ids in same frame: {duplicate_pids}")
                logger.print(f"[PID:{pid}] [BoxMOT-MP]   Full person_ids list: {person_ids}")
                logger.print(f"[PID:{pid}] [BoxMOT-MP]   This should NEVER happen! Check ReID logic!")
                
                # 紧急修复：强制使每个 person_id 唯一（给重复的分配新 ID）
                seen_pids = set()
                for idx, pid in enumerate(person_ids):
                    if pid in seen_pids:
                        # 分配新的临时 ID（使用负数以便区分）
                        new_temp_id = -(idx + 1000)
                        logger.print(f"[PID:{pid}] [BoxMOT-MP]   Emergency fix: {pid} -> {new_temp_id} at index {idx}")
                        person_ids[idx] = new_temp_id
                    else:
                        seen_pids.add(pid)
                
                # 重新计算
                unique_persons_in_frame = len(set(person_ids))
                person_info = ','.join([str(p) for p in person_ids])
            t8 = T.time()
            log_msg = (f"frame={frame_id} dets={n_dets} tracks={n_tracks} reid={reid_count} "
                      f"persons=[{person_info}] unique={unique_persons_in_frame} "
                      f"trajs=[{traj_info}] | "
                      f"DB: total_persons={db_stats['total_persons']} "
                      f"next_id={db_stats['next_person_id']} | "
                      f"read={t1-t0:.3f}s det={t2-t1:.3f}s nms={t3-t2:.3f}s trk={t4-t3:.3f}s "
                      f"match={t5-t4:.3f}s draw={t7-t6:.3f}s write={t8-t7:.3f}s "
                      f"total={t8-t0:.3f}s | "
                      f"worker_wait={worker_queue_wait:.3f}s worker_gap={worker_gap:.3f}s queue_wait={queue_wait_time:.3f}s | "
                      f"mem: {mem0:.0f}->{mem5:.0f}MB")
            
            # 性能监控：检查是否有异常延迟
            processing_time = t8 - t0
            if processing_time > 0.5:  # 超过500ms警告
                logger.print(f"[PID:{pid}] [BoxMOT-MP] ⚠️  SLOW FRAME: {processing_time:.3f}s (normal: <0.1s)")
            # 控制台 + 文件日志
            logger.print(f"[PID:{pid}] [BoxMOT-MP] {log_msg}")
            logger.info(log_msg, pid=pid)
            
            # ========== 慢帧剖析（同时输出到控制台和日志文件）==========
            # 检查点：准备记录日志
            t_now = T.time()
            if t_now - t_checkpoint > 0.01:
                logger.print(f"[TIME-CHECK] Before logging (full): {t_now - t_checkpoint:.3f}s (abs={t_now:.3f})")
            t_checkpoint = t_now
            
            t_end = T.time()
            
            # 检查点：t_end 记录后
            if t_end - t_checkpoint > 0.01:
                logger.print(f"[TIME-CHECK] ⚠️  HUGE GAP before t_end: {t_end - t_checkpoint:.3f}s (abs={t_end:.3f})")
            # 计算各步骤时间总和
            step_sum = (t1-t0) + (t2-t1) + (t3-t2) + (t4-t3) + (t5-t4) + (t7-t6) + (t8-t7) + (t_db_end-t_db_start) + (t_cache_end-t_cache_start)
            missing_time = (t_end - t0) - step_sum
            
            if ENABLE_SLOW_FRAME_ANALYSIS and (t_end - t0) > 0.5:
                slow_msg = (f"[SLOW] total={t_end-t0:.3f}s "
                           f"read={t1-t0:.3f} det={t2-t1:.3f} nms={t3-t2:.3f} trk={t4-t3:.3f} "
                           f"match={t5-t4:.3f} draw={t7-t6:.3f} write={t8-t7:.3f} "
                           f"db={t_db_end-t_db_start:.3f} cache={t_cache_end-t_cache_start:.3f} "
                           f"step_sum={step_sum:.3f} missing={missing_time:.3f} | "
                           f"worker_wait={worker_queue_wait:.3f} worker_gap={worker_gap:.3f} queue_wait={queue_wait_time:.3f} | "
                           f"gc_last={_gc_stats['last_time']:.3f} gc_total={_gc_stats['total_time']:.3f} gc_count={_gc_stats['count']}")
                logger.print(slow_msg)
                logger.info(slow_msg, pid=pid)  # 也写入日志文件
                    
            # 即使不慢，也记录大的 gap
            if worker_gap > 5.0:
                gap_msg = f"[SLOW-GAP] worker_gap={worker_gap:.3f}s (Worker 等待下一帧的空闲时间 = C++端发送延迟)"
                logger.print(gap_msg)
                logger.info(gap_msg, pid=pid)
            
            # 如果启用了 DEBUG_REID，输出更详细的信息
            if DEBUG_REID and len(person_ids) > 0:
                logger.print(f"[PID:{pid}] [BoxMOT-MP] DB person_ids: {db_stats['person_ids']}")
        except Exception as e:
            logger.print(f"[PID:{pid}] [BoxMOT-MP] ❌ CRITICAL ERROR in process_frame: {e}")
            traceback.print_exc()
            # 尝试在共享内存中写入错误信息（如果可能）
            try:
                if mm is not None:
                    error_frame = np.zeros((height, width, 3), dtype=np.uint8)
                    error_text = f"ERROR: {str(e)[:50]}"
                    cv2.putText(error_frame, error_text, (10, 30),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    flat = error_frame.reshape(-1).tobytes()
                    mm[:min(len(flat), shm_len)] = flat
            except Exception as write_e:
                logger.print(f"[PID:{pid}] [BoxMOT-MP] ⚠️  Failed to write error to shared memory: {write_e}")
            # ⚠️  修复：不重新抛出异常，避免 Worker 进程崩溃
            # 改为返回错误状态，让 Worker 继续运行
            return  # 静默返回，让 Worker 继续处理下一帧
        finally:
            # close_map 已在共享内存读取后立即执行，这里不需要额外操作
            pass
    
    def select_worker_key(self, meta: dict) -> str:
        shm_name = meta.get("shmName", "")
        return f"boxmot:{shm_name}" if shm_name else "boxmot:default"


def main():
    logger.print("[BoxMOTServer-MultiProcess] Starting...")
    
    # 显示 GC 配置
    gc_thresholds = gc.get_threshold()
    logger.print(f"[BoxMOTServer-MP] Python GC thresholds: {gc_thresholds}")
    
    # 启动性能监控（如果启用）
    if ENABLE_PERFORMANCE_MONITOR:
        perf_monitor = PerformanceMonitor(interval=60)
        perf_monitor.start()
    
    if os.getenv("BOXMOT_RESET_IDS", "1") == "1":
        ReIDPersonManager.reset()
        logger.print("[BoxMOTServer-MP] Person DB reset.")
    
    # 显示初始 DB 状态
    manager = get_person_manager()
    db_stats = manager.get_db_stats()
    logger.print(f"[BoxMOTServer-MP] Initial DB state: {db_stats['total_persons']} persons, "
          f"next_id={db_stats['next_person_id']}, "
          f"person_ids={db_stats['person_ids']}")
    
    if os.getenv("BOXMOT_PRELOAD", "0") == "1":
        logger.print("[BoxMOTServer-MP] Preloading model...")
        _ = BoxMOTMultiProcessServer.init_model_context()
        logger.print("[BoxMOTServer-MP] Preload done.")
        torch.cuda.empty_cache()
        gc.collect()  # 预加载后手动清理一次
    
    server = BoxMOTMultiProcessServer()
    logger.print(f"[BoxMOTServer-MP] Binding to {server.addr}")
    logger.print(f"[BoxMOTServer-MP] Person DB: {ReIDPersonManager.DATA_FILE}")
    logger.print(f"[BoxMOTServer-MP] Match threshold: {REID_MATCH_THRESHOLD}")
    logger.print(f"[BoxMOTServer-MP] DEBUG_REID: {DEBUG_REID}")
    logger.print(f"[BoxMOTServer-MP] Sync interval: {SYNC_INTERVAL}s, Cleanup interval: {CLEANUP_INTERVAL}s")
    logger.print(f"[BoxMOTServer-MP] Performance monitor: {ENABLE_PERFORMANCE_MONITOR}")
    logger.print(f"[BoxMOTServer-MP] Slow frame analysis: {ENABLE_SLOW_FRAME_ANALYSIS} (threshold: >0.5s)")
    logger.print(f"[BoxMOTServer-MP] GC callback registered: monitoring GC pauses")
    
    
    server.serve()


if __name__ == "__main__":
    main()
