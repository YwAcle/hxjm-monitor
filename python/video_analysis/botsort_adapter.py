"""Shared YOLOX/FastReID weights with independent per-camera tracking state."""
import math
import logging
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import numpy as np

from .config import OPENCV_THREADS, PYTHON_ROOT


BOT_ROOT = PYTHON_ROOT / 'tracker' / 'BoT-SORT'
# Shared weights live in the primary project; algorithm code comes from this release.
ASSET_ROOT = Path(os.getenv('BOTSORT_ROOT', str(BOT_ROOT))).resolve()
logger = logging.getLogger(__name__)


class CudaGraphDetector:
    """One fixed-size graph; callers own their output even when postprocessing in place."""
    def __init__(self, model, shape):
        import torch
        self.model = model
        self.graph = None
        self.input = torch.zeros(shape, device='cuda', dtype=torch.float16)
        with torch.inference_mode():
            stream = torch.cuda.Stream()
            stream.wait_stream(torch.cuda.current_stream())
            with torch.cuda.stream(stream):
                for _ in range(3):
                    model(self.input)
            torch.cuda.current_stream().wait_stream(stream)
            torch.cuda.synchronize()
            graph = torch.cuda.CUDAGraph()
            with torch.cuda.graph(graph):
                self.output = model(self.input)
            # Warm capture/replay must agree before this worker starts serving frames.
            graph.replay()
            if not torch.equal(self.output, model(self.input)):
                raise RuntimeError('CUDA graph changed detector output')
            self.graph = graph

    def __call__(self, image):
        if image.shape != self.input.shape or image.dtype != self.input.dtype or image.device != self.input.device:
            raise ValueError('CUDA graph detector requires its original shape, dtype and device')
        self.input.copy_(image)
        self.graph.replay()
        # YOLOX postprocess mutates coordinates; never expose the graph-owned buffer.
        return self.output.clone()


class BoTSortPipeline:
    def __init__(self):
        # These imports and all CUDA allocations stay inside the spawned worker.
        sys.path.insert(0, str(BOT_ROOT))
        os.environ.setdefault('MPLBACKEND', 'Agg')
        import cv2
        import torch
        torch.set_num_threads(1)
        torch.set_grad_enabled(False)
        if not torch.cuda.is_available():
            raise RuntimeError('BoT-SORT requires CUDA in the botsort39 environment')
        gpu = int(os.getenv('VIDEO_ANALYSIS_GPU', '0'))
        torch.cuda.set_device(gpu)
        from tools.demo import Predictor, make_parser
        from tracker.bot_sort import BoTSORT
        from tracker.tracking_utils.timer import Timer
        from yolox.exp import get_exp
        from yolox.utils import fuse_model

        args = make_parser().parse_args(['video', '--with-reid', '--recover-lost',
                                        '--fuse-score', '--fp16', '--fuse', '--fps',
                                        os.getenv('VIDEO_ANALYSIS_TRACK_FPS', '20')])
        if args.fps <= 0:
            raise ValueError('VIDEO_ANALYSIS_TRACK_FPS must be positive')
        args.fast_reid_config = str(BOT_ROOT / 'fast_reid/configs/MOT17/sbs_S50.yml')
        args.fast_reid_weights = str(ASSET_ROOT / 'pretrained/mot17_sbs_S50.pth')
        checkpoint = ASSET_ROOT / 'pretrained/bytetrack_x_mot17.pth.tar'
        for path in (Path(args.fast_reid_config), Path(args.fast_reid_weights), checkpoint):
            if not path.is_file():
                raise FileNotFoundError(f'Local BoT-SORT asset missing: {path}')
        args.device = 'cuda'
        args.ablation = False
        args.mot20 = not args.fuse_score
        exp = get_exp(str(BOT_ROOT / 'yolox/exps/example/mot/yolox_x_mix_det.py'), None)
        # Fuse/load on CPU; do not deepcopy/profile the model on a nearly full GPU.
        model = exp.get_model().eval().requires_grad_(False)
        weights = torch.load(str(checkpoint), map_location='cpu')
        model.load_state_dict(weights['model'])
        del weights
        model = fuse_model(model).half().to('cuda')
        self.predictor = Predictor(model, exp, device=torch.device('cuda'), fp16=True)
        self.args = args
        self._tracker_class = BoTSORT
        self.encoder = BoTSORT(args, frame_rate=args.fps, reset_id=False).encoder
        self.encoder.model.requires_grad_(False)
        self.timer = Timer()
        self.cameras = {}
        if os.getenv('VIDEO_ANALYSIS_CUDA_GRAPH', '1') == '1':
            # Capture failure retires this worker instead of reusing an invalid CUDA context.
            self.predictor.model = CudaGraphDetector(model, (1, 3, *exp.test_size))
            logger.info('YOLOX CUDA graph enabled with input %s', exp.test_size)
        # YOLOX imports disable OpenCV threads; apply our bounded pool afterwards.
        cv2.setNumThreads(OPENCV_THREADS)

    def infer(self, frame, metadata):
        import torch
        identity = (metadata['camera_id'], metadata.get('tracking_context_id') or metadata['stream_session_id'],
                    metadata['stream_epoch'], frame.shape[:2])
        state = self.cameras.get(identity[0])
        if state is None or identity != state.identity:
            tracker = self._tracker_class(self.args, frame_rate=self.args.fps,
                                          encoder=self.encoder, reset_id=False)
            state = SimpleNamespace(identity=identity, tracker=tracker, last_frame_id=0,
                                    last_pts=None, last_decode=None, clock_ms=0.)
            self.cameras[identity[0]] = state
        if metadata['frame_id'] <= state.last_frame_id:
            raise ValueError('Tracking frames must be strictly ordered')
        decode = metadata['decode_ts_ms']
        pts = metadata.get('media_pts_ms')
        valid_pts = isinstance(pts, (int, float)) and math.isfinite(pts) and pts >= 0
        delta = 1000. / self.args.fps if state.last_decode is None else max(1., decode - state.last_decode)
        if valid_pts and state.last_pts is not None and 0 < pts - state.last_pts < 10000:
            delta = pts - state.last_pts
        state.clock_ms += delta
        state.last_decode, state.last_pts = decode, pts if valid_pts else None
        state.last_frame_id = metadata['frame_id']
        started = time.perf_counter()
        # Original FastReID inference is not decorated with no_grad.
        with torch.inference_mode():
            outputs, info = self.predictor.inference(frame, self.timer)
            detections = np.empty((0, 7), dtype=np.float32)
            if outputs[0] is not None:
                detections = outputs[0].cpu().numpy()[:, :7].copy()
                detections[:, :4] /= info['ratio']
            try:
                tracks = state.tracker.update(detections, frame, timestamp_ms=state.clock_ms)
            except np.linalg.LinAlgError:
                # A broken trajectory must not discard shared models or other cameras.
                self.cameras.pop(identity[0], None)
                raise
        height, width = frame.shape[:2]
        result = []
        for track in tracks:
            if not track.is_activated:
                continue
            x, y, w, h = track.tlwh
            if (not np.isfinite([x, y, w, h]).all() or w <= 0 or h <= 0
                    or w * h <= self.args.min_box_area or w / h > self.args.aspect_ratio_thresh):
                continue
            box = np.clip([x / width, y / height, (x + w) / width, (y + h) / height], 0., 1.).tolist()
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            result.append({'label': 'person', 'track_id': int(track.track_id), 'bbox': box,
                           'confidence': None if track.is_prediction else float(track.score),
                           'is_prediction': bool(track.is_prediction),
                           'missed_frames': int(track.missed_frames)})
        return result, round((time.perf_counter() - started) * 1000, 3)
