"""Map component lifetimes to explicit input sessions and immutable frame facts."""
from datetime import datetime, timedelta, timezone
import math
import uuid


def new_id():
    return str(uuid.uuid4())


def instant(milliseconds):
    return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def after(value):
    return (datetime.fromisoformat(value.replace('Z', '+00:00')) + timedelta(microseconds=1)).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


def frame_fact(captured, detections):
    for name in ('frame_id', 'source_width', 'source_height'):
        value = getattr(captured, name)
        minimum = 0 if name == 'frame_id' else 1
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= 9007199254740991:
            raise ValueError('Invalid input frame dimensions or sequence')
    targets = []
    identifiers = set()
    for index, item in enumerate(detections):
        local = item['track_id']
        if isinstance(local, bool) or not isinstance(local, int) or not 0 <= local <= 9007199254740991 or local in identifiers:
            raise ValueError('Expected unique safe-integer local track IDs')
        identifiers.add(local)
        box = item['bbox']
        if (len(box) != 4 or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or not 0 <= x <= 1 for x in box)
                or box[0] >= box[2] or box[1] >= box[3]):
            raise ValueError('Expected a positive normalized source bbox')
        prediction = item['is_prediction']
        confidence = item['confidence']
        if not isinstance(prediction, bool):
            raise ValueError('Prediction flag must be boolean')
        if confidence is not None and (isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError('Invalid detection confidence')
        if not prediction and confidence is None:
            raise ValueError('Real observations need confidence')
        if item.get('label') != 'person':
            raise ValueError('Unregistered class mapping')
        targets.append(dict(target_index=index, object_type='person', class_code='person', bbox=list(box),
                            confidence=confidence, is_prediction=prediction, local_track_id=local))
    pts = getattr(captured, 'media_pts_ms', None)
    pts = round(pts) if isinstance(pts, (int, float)) and math.isfinite(pts) and pts >= 0 else None
    return dict(result_id=new_id(), frame_id=new_id(), frame_seq=captured.frame_id,
                producer_result_key='frame:' + str(captured.frame_id), occurred_at=instant(captured.frame_ts_ms),
                stream_pts_ms=pts, time_quality='ingest_estimated', media_asset_id=None, media_pts_ms=None,
                source_width=captured.source_width, source_height=captured.source_height, targets=targets)
