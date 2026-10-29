import hashlib
import io
from fractions import Fraction
from pathlib import Path
import tempfile
import threading
import unittest

try:
    import av
except ImportError:  # pragma: no cover - the project media environment provides PyAV
    av = None

from frame_hub.recording import BackgroundRecorder


class _Codec:
    name = "h264"


class _CodecContext:
    codec = _Codec()


class _VideoTemplate:
    type = "video"
    codec_context = _CodecContext()
    width = 16
    height = 16
    time_base = Fraction(1, 25)


class _Packet:
    def __init__(self, value, pts, dts=None, duration=1, keyframe=False):
        self._data = bytes([value])
        self.pts = pts
        self.dts = pts if dts is None else dts
        self.duration = duration
        self.time_base = Fraction(1, 25)
        self.is_keyframe = keyframe

    def __bytes__(self):
        return self._data


class _TemplateRates:
    def __init__(self, template, average_rate, base_rate):
        self._template = template
        self.average_rate = average_rate
        self.base_rate = base_rate

    def __getattr__(self, name):
        return getattr(self._template, name)


def _session(session_id="session-1"):
    return {
        "stream_session_id": session_id,
        "started_at_ms": 1700000000000,
        "width": 16,
        "height": 16,
    }


def _encoded_input(frame_count=4, key_interval=0, format_name="mp4"):
    """Return an open input container and its backing bytes buffer."""
    buffer = io.BytesIO()
    output = av.open(buffer, mode="w", format=format_name)
    options = {"g": str(key_interval), "keyint_min": str(key_interval), "sc_threshold": "0"} if key_interval else None
    stream = output.add_stream("h264", rate=25, options=options)
    stream.width = 16
    stream.height = 16
    stream.pix_fmt = "yuv420p"
    for index in range(frame_count):
        frame = av.VideoFrame(16, 16, "yuv420p")
        frame.pts = index
        for packet in stream.encode(frame):
            output.mux(packet)
    for packet in stream.encode():
        output.mux(packet)
    output.close()
    buffer.seek(0)
    container = av.open(buffer, mode="r")
    return container, container.streams.video[0]


@unittest.skipUnless(av is not None, "PyAV is required")
class BackgroundRecorderTests(unittest.TestCase):
    def test_start_does_not_create_storage_until_a_packet_is_written(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3] / '.run') as directory:
            root = Path(directory) / "storage"
            recorder = BackgroundRecorder("source", root)
            recorder.start()
            try:
                self.assertFalse(root.exists())
                self.assertTrue(recorder.status()["thread_alive"])
            finally:
                self.assertTrue(recorder.stop(2))

    def test_remuxes_b_frames_and_publishes_verified_manifest(self):
        container, stream = _encoded_input()
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3] / '.run') as directory:
            manifests = []
            recorder = BackgroundRecorder("source", directory, on_segment=manifests.append)
            recorder.start()
            try:
                packets = [packet for packet in container.demux(stream) if packet.size]
                expected_payloads = [bytes(packet) for packet in packets]
                expected_end_ms = max((packet.pts + packet.duration) * packet.time_base * 1000 for packet in packets)
                self.assertTrue(all(recorder.offer(packet, stream, _session()) for packet in packets))
            finally:
                self.assertTrue(recorder.stop(5))
                container.close()
            self.assertEqual(len(manifests), 1)
            manifest = manifests[0]
            path = Path(directory) / manifest["storage_key"]
            self.assertTrue(path.is_file())
            self.assertEqual(manifest["byte_size"], path.stat().st_size)
            self.assertEqual(manifest["checksum_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(manifest["content_type"], "video/mp4")
            self.assertEqual(manifest["recording_alignment"]["media_start_pts_ms"], 0)
            self.assertEqual(manifest["recording_alignment"]["stream_end_pts_ms"], expected_end_ms)
            self.assertEqual(manifest["stream_session"], {
                "stream_session_id": "session-1",
                "started_at": "2023-11-14T22:13:20.000Z",
                "time_origin_at": "2023-11-14T22:13:20.000Z",
                "time_basis": "ingest_clock",
                "source_timezone": "UTC",
                "source_width": 16,
                "source_height": 16,
            })

            replay = av.open(str(path), mode="r")
            replay_packets = [packet for packet in replay.demux(replay.streams.video[0]) if packet.size]
            self.assertGreater(len(replay_packets), 1)
            self.assertEqual([bytes(packet) for packet in replay_packets], expected_payloads)
            self.assertEqual(replay_packets[0].pts, 0)
            # The input encoder emits a B-frame with a negative DTS.  PTS and
            # DTS are both shifted by the first PTS; they must not be swapped.
            self.assertLess(replay_packets[0].dts, replay_packets[0].pts)
            replay.close()
            with av.open(str(path), mode="r") as replay:
                self.assertEqual(len(list(replay.decode(video=0))), len(expected_payloads))

    def test_first_non_keyframe_is_skipped_and_segments_start_on_keyframes(self):
        container, stream = _encoded_input(frame_count=6, key_interval=2)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3] / '.run') as directory:
            manifests = []
            recorder = BackgroundRecorder("source", directory, segment_seconds=0.05, on_segment=manifests.append)
            recorder.start()
            try:
                packets = [packet for packet in container.demux(stream) if packet.size]
                # Start on an actual non-keyframe, as after a live-stream join.
                self.assertFalse(packets[1].is_keyframe)
                for packet in packets[1:]:
                    recorder.offer(packet, stream, _session())
            finally:
                self.assertTrue(recorder.stop(5))
                container.close()
            self.assertEqual(len(manifests), 2)
            for manifest in manifests:
                path = Path(directory) / manifest["storage_key"]
                replay = av.open(str(path), mode="r")
                packet = next(packet for packet in replay.demux(replay.streams.video[0]) if packet.size)
                self.assertTrue(packet.is_keyframe)
                self.assertEqual(packet.pts, 0)
                replay.close()
                with av.open(str(path), mode="r") as replay:
                    self.assertEqual(len(list(replay.decode(video=0))), 2)

    def test_queued_packet_snapshots_outlive_input_container(self):
        container, stream = _encoded_input(frame_count=4)
        entered = threading.Event()
        release = threading.Event()
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3] / '.run') as directory:
            manifests = []
            recorder = BackgroundRecorder("source", directory, on_segment=manifests.append)
            write_offer = recorder._write_offer

            def delayed_write(item):
                entered.set()
                if not release.wait(3):
                    raise RuntimeError("test did not release recorder")
                write_offer(item)

            recorder._write_offer = delayed_write
            recorder.start()
            try:
                packets = [packet for packet in container.demux(stream) if packet.size]
                expected_payloads = [bytes(packet) for packet in packets]
                for packet in packets:
                    self.assertTrue(recorder.offer(packet, stream, _session()))
                self.assertTrue(entered.wait(1))
                container.close()
            finally:
                release.set()
                self.assertTrue(recorder.stop(5))
                container.close()
            self.assertEqual(len(manifests), 1)
            path = Path(directory) / manifests[0]["storage_key"]
            with av.open(str(path), mode="r") as replay:
                self.assertEqual(
                    [bytes(packet) for packet in replay.demux(replay.streams.video[0]) if packet.size],
                    expected_payloads,
                )
            with av.open(str(path), mode="r") as replay:
                self.assertEqual(len(list(replay.decode(video=0))), len(expected_payloads))

    def test_next_keyframe_bounds_segment_when_estimated_tail_overlaps_one_ms(self):
        container, stream = _encoded_input(frame_count=6, key_interval=2)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3] / '.run') as directory:
            manifests = []
            recorder = BackgroundRecorder("source", directory, segment_seconds=0.05,
                                          on_segment=manifests.append)
            recorder.start()
            try:
                for packet in container.demux(stream):
                    if not packet.size:
                        continue
                    pts_ms = int(packet.pts * packet.time_base * 1000)
                    dts_ms = int(packet.dts * packet.time_base * 1000)
                    # A live GOP may start 1 ms earlier than its declared rate predicts.
                    shift_ms = 1 if pts_ms >= 80 else 0
                    packet.pts = pts_ms - shift_ms
                    packet.dts = dts_ms - shift_ms
                    packet.duration = 0
                    packet.time_base = Fraction(1, 1000)
                    self.assertTrue(recorder.offer(packet, _TemplateRates(stream, Fraction(25), None), _session()))
            finally:
                self.assertTrue(recorder.stop(5))
                container.close()
            self.assertEqual(len(manifests), 3)
            self.assertEqual(manifests[0]["recording_alignment"]["stream_end_pts_ms"], 79)
            for previous, following in zip(manifests, manifests[1:]):
                self.assertEqual(previous["recording_alignment"]["stream_end_pts_ms"],
                                 following["recording_alignment"]["stream_start_pts_ms"])
                self.assertEqual(previous["end_at"], following["start_at"])
                self.assertEqual(previous["end_timing"], "next_keyframe")
            self.assertEqual(manifests[-1]["end_timing"], "average_rate")
            self.assertEqual(manifests[-1]["recording_alignment"]["stream_end_pts_ms"], 239)
            for manifest in manifests:
                with av.open(str(Path(directory) / manifest["storage_key"]), mode="r") as replay:
                    self.assertEqual(len(list(replay.decode(video=0))), 2)

    def test_annex_b_input_uses_mp4_codec_tag_and_decodes(self):
        container, stream = _encoded_input(format_name="mpegts")
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3] / '.run') as directory:
            manifests = []
            recorder = BackgroundRecorder("source", directory, on_segment=manifests.append)
            recorder.start()
            try:
                packets = [packet for packet in container.demux(stream) if packet.size]
                for packet in packets:
                    self.assertTrue(recorder.offer(packet, stream, _session()))
            finally:
                self.assertTrue(recorder.stop(5))
                container.close()
            self.assertEqual(len(manifests), 1)
            path = Path(directory) / manifests[0]["storage_key"]
            with av.open(str(path), mode="r") as replay:
                self.assertEqual(replay.streams.video[0].codec_context.codec_tag, "avc1")
                self.assertEqual(len(list(replay.decode(video=0))), len(packets))

    def test_zero_packet_duration_uses_declared_rate_or_observed_pts(self):
        cases = (
            (Fraction(25), Fraction(24), "average_rate"),
            (None, Fraction(25), "base_rate"),
            (None, None, "observed_pts_gap"),
        )
        for average_rate, base_rate, expected_basis in cases:
            with self.subTest(end_timing=expected_basis):
                container, stream = _encoded_input(frame_count=4)
                template = _TemplateRates(stream, average_rate, base_rate)
                with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3] / '.run') as directory:
                    manifests = []
                    recorder = BackgroundRecorder("source", directory, on_segment=manifests.append)
                    recorder.start()
                    try:
                        packets = [packet for packet in container.demux(stream) if packet.size]
                        expected_end_ms = max((packet.pts + packet.duration) * packet.time_base * 1000 for packet in packets)
                        for packet in packets:
                            packet.duration = 0
                            self.assertTrue(recorder.offer(packet, template, _session()))
                    finally:
                        self.assertTrue(recorder.stop(5))
                        container.close()
                    self.assertEqual(len(manifests), 1)
                    manifest = manifests[0]
                    self.assertEqual(manifest["end_timing"], expected_basis)
                    self.assertEqual(manifest["recording_alignment"]["stream_end_pts_ms"], expected_end_ms)
                    path = Path(directory) / manifest["storage_key"]
                    with av.open(str(path), mode="r") as replay:
                        video = replay.streams.video[0]
                        self.assertEqual(video.duration * video.time_base * 1000, expected_end_ms)
                        self.assertEqual(len(list(replay.decode(video=0))), len(packets))

    def test_unknown_final_frame_duration_does_not_publish_available_manifest(self):
        container, stream = _encoded_input(frame_count=1)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3] / '.run') as directory:
            manifests = []
            recorder = BackgroundRecorder("source", directory, on_segment=manifests.append)
            with self.assertLogs("frame_hub.recording", level="ERROR"):
                recorder.start()
                try:
                    packet = next(packet for packet in container.demux(stream) if packet.size)
                    packet.duration = 0
                    self.assertTrue(recorder.offer(packet, _TemplateRates(stream, None, None), _session()))
                finally:
                    self.assertTrue(recorder.stop(5))
                    container.close()
            self.assertEqual(manifests, [])
            self.assertEqual(list(Path(directory).rglob("*.manifest.json")), [])
            self.assertIn("recording end time is unknown", recorder.status()["last_error"])

    def test_offer_is_bounded_and_does_not_wait_for_full_queue(self):
        template = _VideoTemplate()
        entered = threading.Event()
        release = threading.Event()
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3] / '.run') as directory:
            recorder = BackgroundRecorder("source", directory, queue_size=1)
            recorder._write_offer = lambda item: (entered.set(), release.wait(2))
            recorder.start()
            try:
                self.assertTrue(recorder.offer(_Packet(1, 0, keyframe=True), template, _session()))
                self.assertTrue(entered.wait(1))
                self.assertTrue(recorder.offer(_Packet(2, 1), template, _session()))
                self.assertFalse(recorder.offer(_Packet(3, 2), template, _session()))
                self.assertEqual(recorder.status()["rejected_packets"], 1)
            finally:
                release.set()
                self.assertTrue(recorder.stop(3))

    def test_callback_failure_keeps_manifest_pending_until_acknowledged(self):
        container, stream = _encoded_input(frame_count=1)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3] / '.run') as directory:
            recorder = BackgroundRecorder("source", directory, on_segment=lambda _: (_ for _ in ()).throw(RuntimeError("offline")))
            recorder.start()
            try:
                packet = next(packet for packet in container.demux(stream) if packet.size)
                self.assertTrue(recorder.offer(packet, stream, _session()))
            finally:
                self.assertTrue(recorder.stop(5))
                container.close()
            pending = recorder.pending_manifests()
            self.assertEqual(len(pending), 1)
            self.assertTrue(recorder.acknowledge(pending[0]["asset_id"]))
            self.assertEqual(recorder.pending_manifests(), [])
            self.assertFalse(recorder.acknowledge(pending[0]["asset_id"]))

    def test_audio_templates_are_rejected_without_silent_drop(self):
        class AudioTemplate:
            type = "audio"

        recorder = BackgroundRecorder("source")
        packet = _Packet(1, 0, keyframe=True)
        self.assertFalse(recorder.offer(packet, AudioTemplate(), _session()))
        self.assertEqual(recorder.status()["rejected_packets"], 1)


if __name__ == "__main__":
    unittest.main()
