"""Run explicitly INSIDE the analysis image with one GPU and a real person image.

This is an acceptance probe, not a CPU fallback or a service launcher.
"""
import json
import sys
import time
import cv2
import torch
from video_analysis.botsort_adapter import BoTSortPipeline

if __name__ == '__main__':
    frame = cv2.imread(sys.argv[1])
    if frame is None:
        raise SystemExit('Supply a readable person image')
    if not torch.cuda.is_available():
        raise SystemExit('GPU unavailable; probe refused')
    torch.cuda.reset_peak_memory_stats()
    pipeline = BoTSortPipeline()
    rows = []
    for index in range(1, 4):
        targets, elapsed = pipeline.infer(frame, {
            'camera_id': 'camera_1', 'stream_session_id': 'acceptance',
            'stream_epoch': 1, 'frame_id': index,
            'decode_ts_ms': time.time() * 1000, 'media_pts_ms': index * 250})
        rows.append({'frame': index, 'targets': len(targets), 'elapsed_ms': elapsed})
    torch.cuda.synchronize()
    if not any(row['targets'] for row in rows):
        raise AssertionError('No person tracked; zero-target inference is insufficient')
    print(json.dumps({'pipeline_constructions': 1, 'frames': rows,
        'torch': torch.__version__, 'cuda': torch.version.cuda,
        'peak_allocated_mib': round(torch.cuda.max_memory_allocated() / 2**20, 1),
        'peak_reserved_mib': round(torch.cuda.max_memory_reserved() / 2**20, 1)}))
