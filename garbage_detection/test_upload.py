import base64
import io
import unittest
from unittest.mock import patch

from PIL import Image
from server import Camera, Service, decode_upload


class UploadTests(unittest.TestCase):
    def image_bytes(self, format="PNG"):
        buffer = io.BytesIO()
        Image.new("RGB", (60, 30), "white").save(buffer, format)
        return buffer.getvalue()

    def test_valid_formats_and_invalid_images(self):
        for format in ("JPEG", "PNG", "WEBP"):
            with Image.open(io.BytesIO(decode_upload(self.image_bytes(format)))) as image:
                self.assertEqual(image.size, (60, 30))
                self.assertEqual(image.format, "PNG")
        for data in (b"not an image", b"", self.image_bytes("GIF"), self.image_bytes()[:25]):
            with self.assertRaises(ValueError):
                decode_upload(data)
        with patch("server.MAX_UPLOAD_BYTES", 10), self.assertRaises(ValueError):
            decode_upload(self.image_bytes())
        with patch("server.MAX_UPLOAD_PIXELS", 100), self.assertRaises(ValueError):
            decode_upload(self.image_bytes())

    def test_orientation_and_transparency(self):
        buffer = io.BytesIO()
        image = Image.new("RGB", (60, 30))
        exif = image.getexif()
        exif[274] = 6
        image.save(buffer, "JPEG", exif=exif)
        with Image.open(io.BytesIO(decode_upload(buffer.getvalue()))) as corrected:
            self.assertEqual(corrected.size, (30, 60))
        buffer = io.BytesIO()
        Image.new("RGBA", (2, 2), (0, 0, 0, 0)).save(buffer, "PNG")
        with Image.open(io.BytesIO(decode_upload(buffer.getvalue()))) as corrected:
            self.assertEqual(corrected.getpixel((0, 0)), (255, 255, 255))

    def test_upload_works_without_camera_and_preserves_source(self):
        class FakeDetector:
            device = "cpu"
            def load(self):
                pass
            def infer(self, image):
                return {"has_garbage": False, "targets": [], "unlocalized": False}
        service = Service(Camera("rtsp://offline.invalid"), FakeDetector())
        image = decode_upload(self.image_bytes())
        with patch("server.threading.Thread") as thread:
            job = service.start(image, "样本.png")
            self.assertIsNotNone(job)
            self.assertEqual(service.job["source"], "upload")
            self.assertIsNone(service.start(image, "other.png"))
            thread.return_value.start.assert_called_once()
        service.detect(job, image, "test", "upload", "样本.png")
        self.assertEqual(service.job["state"], "done")
        self.assertEqual(service.result["file_name"], "样本.png")
        self.assertIsNone(service.result["camera_id"])
        self.assertEqual(service.result["source"], "upload")
        self.assertEqual(service.result["image_width"], 60)
        self.assertTrue(service.result["image"].startswith("data:image/jpeg;base64,"))

    def test_large_upload_keeps_inference_resolution_but_bounds_result_preview(self):
        from unittest.mock import Mock
        detector = Mock(device="cpu")
        inference_sizes = []
        def infer(image):
            inference_sizes.append(image.size)
            return {"has_garbage": False, "targets": []}
        detector.infer.side_effect = infer
        service = Service(Camera("rtsp://offline.invalid"), detector)
        output = io.BytesIO()
        Image.new("RGB", (3000, 1500), "white").save(output, "PNG")
        service.detect("large", output.getvalue(), "test", "upload", "large.png")
        self.assertEqual(service.job["state"], "done")
        self.assertEqual(inference_sizes, [(3000, 1500)])
        self.assertEqual(service.result["image_width"], 3000)
        preview = base64.b64decode(service.result["image"].split(",", 1)[1])
        with Image.open(io.BytesIO(preview)) as image:
            self.assertEqual(image.size, (2048, 1024))


if __name__ == "__main__":
    unittest.main()
