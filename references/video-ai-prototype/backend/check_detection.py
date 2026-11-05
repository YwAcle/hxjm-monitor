import json
import sys
from contextlib import redirect_stdout


def main():
    sys.dont_write_bytecode = True
    try:
        with redirect_stdout(sys.stderr):
            from .config import CAMERA_ID
            from .detector_adapter import detect_people
            from .stream_grabber import grab_frame

            captured = grab_frame()
            detections, inference_ms = detect_people(captured.frame)
            payload = {
                "camera_id": CAMERA_ID,
                "frame_ts_ms": captured.frame_ts_ms,
                "source_width": captured.source_width,
                "source_height": captured.source_height,
                "inference_ms": inference_ms,
                "detections": detections,
            }
            output = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    except ModuleNotFoundError as exc:
        print(f"Missing dependency in the algorithm environment: {exc.name}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Detection check failed ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 1

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
