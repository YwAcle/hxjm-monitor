"""Encode the clean inference input, never a later capture or painted image."""
import base64

import cv2

from .config import SYNC_FRAME_WIDTH, SYNC_FRAME_HEIGHT, SYNC_JPEG_QUALITY, SYNC_MAX_JPEG_BYTES


def encode_frame(frame, frame_id):
    height, width = frame.shape[:2]
    scale = min(1, SYNC_FRAME_WIDTH / width, SYNC_FRAME_HEIGHT / height)
    if scale < 1:
        frame = cv2.resize(frame, (max(1, round(width * scale)), max(1, round(height * scale))))
    success, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, SYNC_JPEG_QUALITY])
    if not success or encoded.nbytes > SYNC_MAX_JPEG_BYTES:
        raise ValueError('Synchronized frame encoding failed or exceeded 2 MiB')
    return {'encoding': 'jpeg', 'frame_id': frame_id,
            'width': frame.shape[1], 'height': frame.shape[0],
            'data': base64.b64encode(encoded).decode('ascii')}
