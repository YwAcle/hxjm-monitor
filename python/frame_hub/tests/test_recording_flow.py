"""Real codec data across public frame identities, recording and registration."""
from datetime import datetime
from fractions import Fraction
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock

try:
    import av
except ImportError:  # pragma: no cover - the media runtime supplies PyAV
    av = None

from frame_hub.hub import FrameHub
from frame_hub.recording import BackgroundRecorder
from frame_hub.tests.test_recording import _encoded_input
from video_analysis.business_runtime import BusinessRuntime
from video_analysis.frame_result import FrameResultInput, frame_result
from video_analysis.recording_delivery import RecordingDelivery
from video_analysis.stream_grabber import LatestFrameGrabber


SOURCE = "10000000-0000-4000-8000-000000000001"
STREAM = "20000000-0000-4000-8000-000000000001"
INSTANCE = "50000000-0000-4000-8000-000000000001"
TRACKING_CONTEXT = "70000000-0000-4000-8000-000000000001"
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _epoch_ms(value):
    return round(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def _input_with_nonzero_pts():
    original, stream = _encoded_input(frame_count=8, key_interval=2)
    buffer = io.BytesIO()
    output = av.open(buffer, mode="w", format="mp4")
    try:
        target = output.add_stream_from_template(stream)
        for packet in original.demux(stream):
            if packet.size:
                offset = int(Fraction(5) / packet.time_base)
                packet.pts += offset
                packet.dts += offset
                packet.stream = target
                output.mux(packet)
    finally:
        output.close()
        original.close()
    buffer.seek(0)
    return av.open(buffer, mode="r")


class _FixtureGrabber(LatestFrameGrabber):
    """Use the real capture loop with a finite local source instead of RTSP."""

    def __init__(self, container, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.container = container
        self.finished = threading.Event()
        self.failure = None

    def _run(self):
        try:
            self._run_pyav_session(self.container)
        except Exception as error:
            self.failure = error
        finally:
            self.container.close()
            self.finished.set()


@unittest.skipUnless(av is not None, "PyAV is required")
class RecordingFlowTests(unittest.TestCase):
    def test_nonzero_pts_frames_map_to_exactly_one_registered_decodable_segment(self):
        container = _input_with_nonzero_pts()
        outputs = []
        grabbers = []
        client = Mock()
        client.open_session.side_effect = lambda payload: {
            "source_id": payload["source_id"],
            "stream_session_id": payload["stream_session_id"],
        }
        client.register_asset.side_effect = lambda payload: {
            "asset_id": payload["asset_id"],
            "producer_key": payload["producer_key"],
            "state": "available",
            "revision": 1,
        }
        runtime = BusinessRuntime(client, source_streams={SOURCE: STREAM}, instances={
            (SOURCE, "botsort"): {"instance_id": INSTANCE, "capability_code": "tracking"},
        })
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / ".run") as directory:
            root = Path(directory)
            delivery = RecordingDelivery(client, runtime, storage_root=root,
                                         source_ids={SOURCE}, retry_interval=0.01)

            def grabber_factory(on_status, **options):
                publish = options.pop("on_frame")

                def on_frame(captured):
                    publish(captured)
                    outputs.append(frame_result(
                        FrameResultInput.from_capture(captured),
                        [{"label": "person", "bbox": [0.1, 0.1, 0.8, 0.9],
                          "confidence": 0.95, "track_id": 7}],
                        camera_id="camera_1", algorithm="botsort",
                        tracking_session=TRACKING_CONTEXT, session_generation=1,
                        worker_slot=0, worker_generation=1,
                        processed_at_ms=max(captured.frame_ts_ms, captured.decode_ts_ms),
                    ))

                grabber = _FixtureGrabber(container, on_status, on_frame=on_frame, **options)
                grabbers.append(grabber)
                return grabber

            hub = FrameHub(
                {SOURCE: "rtsp://fixture/nonzero-pts"}, grabber_factory=grabber_factory,
                recorder_factory=lambda source: BackgroundRecorder(
                    source, root, segment_seconds=0.08, on_segment=delivery),
            )
            delivery.start()
            try:
                hub.start()
                self.assertTrue(grabbers[0].finished.wait(5), "Capture did not finish")
                self.assertIsNone(grabbers[0].failure)
            finally:
                hub.stop()
                self.assertTrue(delivery.stop())
                container.close()

            self.assertEqual(len(outputs), 8)
            self.assertEqual([item["result"]["frame_seq"] for item in outputs], list(range(1, 9)))
            self.assertEqual(len({item["result"]["frame_id"] for item in outputs}), 8)
            self.assertEqual({item["result"]["stream_pts_ms"] for item in outputs},
                             set(range(5000, 5320, 40)))
            self.assertEqual(len({item["stream_session_id"] for item in outputs}), 1)
            session = outputs[0]["stream_session"]
            origin = _epoch_ms(session["time_origin_at"])
            self.assertEqual(_epoch_ms(session["started_at"]) - origin, 5000)
            for output in outputs:
                runtime.open_input(SOURCE, output["stream_session"])
                self.assertEqual(output["stream_session"], session)
                self.assertEqual(_epoch_ms(output["result"]["occurred_at"]),
                                 origin + output["result"]["stream_pts_ms"])

            manifests = [json.loads(path.read_text(encoding="utf-8"))
                         for path in root.rglob("*.mp4.manifest.json")]
            self.assertEqual(len(manifests), 4)
            self.assertEqual(client.open_session.call_count, 1)
            self.assertEqual(client.register_asset.call_count, 4)
            self.assertEqual(delivery.status()["confirmed_manifests"], 4)
            self.assertEqual(delivery.status()["pending_manifests"], 0)

            registered = {call.args[0]["asset_id"]: call.args[0]
                          for call in client.register_asset.call_args_list}
            decoded_pts = {}
            for manifest in manifests:
                alignment = manifest["recording_alignment"]
                self.assertEqual(manifest["stream_session_id"], session["stream_session_id"])
                self.assertEqual(_epoch_ms(manifest["stream_session"]["started_at"]),
                                 _epoch_ms(session["started_at"]))
                self.assertEqual(_epoch_ms(manifest["stream_session"]["time_origin_at"]), origin)
                self.assertEqual(_epoch_ms(manifest["start_at"]),
                                 origin + alignment["stream_start_pts_ms"])
                self.assertEqual(_epoch_ms(manifest["end_at"]),
                                 origin + alignment["stream_end_pts_ms"])
                asset = registered[manifest["asset_id"]]
                self.assertEqual(asset["recording_alignment"], alignment)
                self.assertNotIn("stream_session", asset)
                self.assertNotIn("end_timing", asset)
                path = root / manifest["storage_key"]
                self.assertTrue(path.with_suffix(".mp4.manifest.json.ack").is_file())
                with av.open(str(path), mode="r") as replay:
                    video = replay.streams.video[0]
                    self.assertEqual(video.duration * video.time_base * 1000,
                                     alignment["stream_end_pts_ms"] - alignment["stream_start_pts_ms"])
                    decoded_pts[manifest["asset_id"]] = {
                        frame.pts * frame.time_base * 1000 for frame in replay.decode(video=0)
                    }
                self.assertEqual(len(decoded_pts[manifest["asset_id"]]), 2)

            for output in outputs:
                pts = output["result"]["stream_pts_ms"]
                matches = [manifest for manifest in manifests
                           if manifest["recording_alignment"]["stream_start_pts_ms"] <= pts
                           < manifest["recording_alignment"]["stream_end_pts_ms"]]
                self.assertEqual(len(matches), 1)
                manifest = matches[0]
                alignment = manifest["recording_alignment"]
                media_pts = pts - alignment["stream_start_pts_ms"] + alignment["media_start_pts_ms"]
                self.assertIn(media_pts, decoded_pts[manifest["asset_id"]])
            self.assertIsNone(hub._sources[SOURCE].recorder.status()["last_error"])


if __name__ == "__main__":
    unittest.main()
