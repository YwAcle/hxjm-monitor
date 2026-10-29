#!/usr/bin/env python3
"""Read a MediaMTX RTSP stream with OpenCV.

Examples:
  python3 read_rtsp.py --camera-id 1 --show
  python3 read_rtsp.py --camera-id 1 --task boxmot --save-frame frame.jpg
  python3 read_rtsp.py --url rtsp://192.168.5.53:8554/live/camera_1 --show
"""

import argparse
import os
import time
from pathlib import Path

# Must be set before importing cv2. TCP avoids UDP/RTP packet loss on most LANs.
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;500000",
)

import cv2


def parse_args():
    parser = argparse.ArgumentParser(description="Read a MediaMTX RTSP stream")
    parser.add_argument("--host", default="127.0.0.1", help="MediaMTX host or IP")
    parser.add_argument("--port", type=int, default=8554, help="MediaMTX RTSP port")
    parser.add_argument("--camera-id", type=int, default=1, help="Camera ID in the stream name")
    parser.add_argument("--task", help="Algorithm task, such as boxmot or vad")
    parser.add_argument("--url", help="Complete RTSP URL; overrides host/port/camera-id/task")
    parser.add_argument("--show", action="store_true", help="Show frames in an OpenCV window")
    parser.add_argument("--save-frame", metavar="PATH", help="Write the first decoded frame to PATH")
    return parser.parse_args()


def build_url(args):
    if args.url:
        return args.url
    stream_name = f"camera_{args.camera_id}"
    if args.task:
        stream_name += f"_{args.task}"
    return f"rtsp://{args.host}:{args.port}/live/{stream_name}"


def open_capture(url):
    return cv2.VideoCapture(url, cv2.CAP_FFMPEG)


def resolve_frame_path(value):
    path = Path(value).expanduser()
    # A directory (including './' or a path that does not exist yet but ends
    # with a separator) means use the conventional output filename.
    if path.is_dir() or value.endswith(('/', os.sep)):
        path = path / "frame.jpg"
    if not path.suffix:
        raise ValueError("--save-frame must be an image filename such as frame.jpg")
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def main():
    args = parse_args()
    url = build_url(args)
    if args.save_frame:
        try:
            args.save_frame = resolve_frame_path(args.save_frame)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
    print(f"Reading {url}")

    capture = None
    frame_count = 0
    saved = False
    try:
        while True:
            if capture is None or not capture.isOpened():
                if capture is not None:
                    capture.release()
                print("Connecting...")
                capture = open_capture(url)
                if not capture.isOpened():
                    print("Connection failed; retrying in 2 seconds")
                    time.sleep(2)
                    continue

            ok, frame = capture.read()
            if not ok:
                print("Stream read failed; reconnecting")
                capture.release()
                capture = None
                continue

            frame_count += 1

            # `frame` is a BGR numpy.ndarray. Call your model here.
            # result = model(frame)

            if args.save_frame and not saved:
                if not cv2.imwrite(args.save_frame, frame):
                    raise RuntimeError(f"Cannot write {args.save_frame}")
                print(f"Saved frame: {args.save_frame}")
                saved = True
                if not args.show:
                    return

            if args.show:
                cv2.imshow("MediaMTX RTSP", frame)
                if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                    return

            if frame_count % 100 == 0:
                height, width = frame.shape[:2]
                print(f"Decoded {frame_count} frames ({width}x{height})")
    finally:
        if capture is not None:
            capture.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
