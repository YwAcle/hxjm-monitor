"""Grounding DINO implementation reused without its standalone camera/server."""
import os


class GarbageDetector:
    last_removed_tracks = ()

    def __init__(self):
        from garbage_detection.detector import Detector
        model = os.environ.get('GARBAGE_MODEL_PATH')
        if not model:
            raise ValueError('GARBAGE_MODEL_PATH must point to the existing local Grounding DINO model')
        self.detector = Detector(model, os.getenv('GARBAGE_DEVICE', 'cpu'))
        self.threshold = float(os.getenv('GARBAGE_THRESHOLD', '.25'))
        if not 0 < self.threshold <= 1:
            raise ValueError('GARBAGE_THRESHOLD must be in (0,1]')

    def infer(self, frame, metadata):
        from PIL import Image
        result = self.detector.infer(Image.fromarray(frame[:, :, ::-1]), threshold=self.threshold)
        detections = [dict(label=t['label'], bbox=[v / 1000 for v in t['bbox']],
                           confidence=t['confidence'], track_id=i, is_prediction=False)
                      for i, t in enumerate(result['targets']) if t['bbox'] is not None]
        return detections, result['inference_seconds'] * 1000


def garbage_results(frames):
    """Same spool identities and capture time; generic results do not invent person tracks."""
    return [dict(result_id=f['result_id'], producer_result_key=f['producer_result_key'],
                 start_at=f['occurred_at'], end_at=f['occurred_at'],
                 payload=dict(has_target=bool(f['targets']), targets=[
                     dict(category=t['class_code'], bbox=t['bbox'], confidence=t['confidence'])
                     for t in f['targets'] if not t['is_prediction']])) for f in frames]
