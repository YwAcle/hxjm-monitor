"""CLIP-ReID multipart 客户端；同一特征空间内检索，不覆盖数据库向量。"""

import base64
import json
import hashlib
from io import BytesIO
import math
from threading import Lock

import httpx
from PIL import Image, ImageOps

from llm_report_service.llm.vision import decode_base64_image


class ClipReIDClient:
    method = "remote_clipreid"

    def __init__(self, base_url: str, timeout_s: float = 30, feature_space_id: str = ""):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.expected_space = feature_space_id
        self._cache = {}
        self._lock = Lock()

    def _request(self, method, path, **kwargs):
        try:
            # 此服务是后端直连，避免系统 HTTP 代理转发私网图片。
            with httpx.Client(trust_env=False, timeout=httpx.Timeout(self.timeout_s, connect=5)) as client:
                response = client.request(method, self.base_url + path, **kwargs)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError):
            raise ValueError("CLIP-ReID 服务请求失败，请检查服务地址、图片限制或服务负载") from None
        if not isinstance(data, dict):
            raise ValueError("CLIP-ReID 响应格式无效")
        return data

    def health(self):
        data = self._request("GET", "/health")
        space = data.get("feature_space_id")
        if data.get("ready") is not True or data.get("embedding_dim") != 3072 or not isinstance(space, str) or not space:
            raise ValueError("CLIP-ReID 未就绪或特征空间无效")
        if self.expected_space and space != self.expected_space:
            raise ValueError("CLIP-ReID 特征空间与配置不一致")
        return data

    @staticmethod
    def screenshot_image(encoded):
        raw = base64.b64decode(encoded.split(",", 1)[-1])
        with Image.open(BytesIO(raw)) as image:
            return ImageOps.exif_transpose(image).convert("RGB")

    def _encode(self, image, space, bbox=None):
        buffer = BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
        data = self._request("POST", "/v1/reid/image-features",
                             files={"file": ("person.png", buffer.getvalue(), "image/png")},
                             data={"bbox": json.dumps(bbox)} if bbox is not None else {})
        return self._feature(data, space)

    def _feature(self, data, space):
        if (data.get("feature_space_id") != space or data.get("embedding_dim") != 3072
                or data.get("normalized") is not True or data.get("feature_type") != "image"):
            raise ValueError("CLIP-ReID 特征空间或响应类型不一致")
        vector = data.get("embedding")
        if (not isinstance(vector, list) or len(vector) != 3072
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in vector)):
            raise ValueError("CLIP-ReID 特征向量无效")
        try:
            norm = math.hypot(*vector)
        except (OverflowError, ValueError):
            raise ValueError("CLIP-ReID 特征向量无效") from None
        if not math.isfinite(norm) or abs(norm - 1) > 0.01:
            raise ValueError("CLIP-ReID 特征未正确归一化")
        return [v / norm for v in vector]

    def detect(self, image):
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return self._request("POST", "/v1/reid/person-crops",
                             files={"file": ("screenshot.png", buffer.getvalue(), "image/png")})

    def query_gallery(self, image, rows, *, bbox=None, feature=None):
        with self._lock:
            space = self.health()["feature_space_id"]
            query = self._feature(feature, space) if feature is not None else self._encode(image, space, bbox)
            current, vectors = {}, {}
            for row in rows:
                if not row.image_base64:
                    continue
                key = (space, row.id, hashlib.sha256(row.image_base64.encode()).hexdigest())
                vector = self._cache.get(key)
                if vector is None:
                    picture = decode_base64_image(row.image_base64)
                    if picture is None:
                        continue
                    vector = self._encode(picture, space)
                current[key] = vector
                vectors[row.id] = vector
            # 只保留本轮有效登记数据；任何接口失败都中止，避免返回不完整排序。
            self._cache = current
            return query, vectors, space
