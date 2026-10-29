"""Chinese-CLIP 文本→图像检索客户端；与 CLIP-ReID 图片特征空间严格隔离。"""

import hashlib
import json
import math
from io import BytesIO
from threading import Lock

import httpx

from llm_report_service.llm.vision import decode_base64_image


class TextTooLongError(ValueError):
    """文本描述超过模型可编码长度，需要精简后重试。"""


class TextReIDClient:
    method = "remote_chinese_clip_text"
    profile = "chinese_clip_text_reid"
    text_path = "/v1/reid/text-features"
    image_path = "/v1/reid/text-reid-image-features"

    def __init__(self, base_url: str, timeout_s: float = 30, feature_space_id: str = "",
                 text_contract_id: str = "", max_text_chars: int = 200):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.expected_space = feature_space_id
        self.expected_contract = text_contract_id
        self.max_text_chars = max_text_chars
        self._cache = {}
        self._lock = Lock()

    @staticmethod
    def _error_code(response):
        try:
            detail = response.json().get("detail")
        except (ValueError, AttributeError):
            return ""
        return detail.get("error_code") if isinstance(detail, dict) else ""

    def _request(self, method, path, **kwargs):
        try:
            # 与 CLIP-ReID 客户端一致，私网直连不走系统 HTTP 代理。
            with httpx.Client(trust_env=False, timeout=httpx.Timeout(self.timeout_s, connect=5)) as client:
                response = client.request(method, self.base_url + path, **kwargs)
        except httpx.HTTPError:
            raise ValueError("Chinese-CLIP 文本检索服务请求失败，请检查服务地址或服务负载") from None
        if response.status_code == 422 and self._error_code(response) == "TEXT_TOO_LONG":
            raise TextTooLongError("文本描述超过模型可编码长度，请精简后重试")
        if response.status_code >= 400:
            raise ValueError("Chinese-CLIP 文本检索服务请求失败，请检查服务地址、文本限制或服务负载")
        try:
            data = response.json()
        except (ValueError, AttributeError):
            raise ValueError("Chinese-CLIP 文本检索响应格式无效") from None
        if not isinstance(data, dict):
            raise ValueError("Chinese-CLIP 文本检索响应格式无效")
        return data

    def health(self):
        data = self._request("GET", "/health")
        block = data.get("text_reid")
        if not isinstance(block, dict):
            raise ValueError("远端未提供 Chinese-CLIP 文本检索配置")
        space = block.get("feature_space_id")
        dim = block.get("embedding_dim")
        contract = block.get("text_contract_id")
        if (block.get("ready") is not True or block.get("alignment_verified") is not True
                or not isinstance(space, str) or not space
                or type(dim) is not int or dim <= 0
                or not isinstance(contract, str) or not contract):
            raise ValueError("Chinese-CLIP 文本检索未就绪或特征空间无效")
        if self.expected_space and space != self.expected_space:
            raise ValueError("Chinese-CLIP 文本特征空间与配置不一致")
        if self.expected_contract and contract != self.expected_contract:
            raise ValueError("Chinese-CLIP 文本契约与配置不一致")
        return block

    def _feature(self, data, space, dim, expected_type, contract=None):
        if (data.get("feature_space_id") != space or data.get("embedding_dim") != dim
                or data.get("feature_type") != expected_type
                or data.get("model_profile") != self.profile
                or data.get("normalized") is not True):
            raise ValueError("Chinese-CLIP 特征空间或响应类型不一致")
        if expected_type == "text":
            if data.get("text_contract_id") != contract:
                raise ValueError("Chinese-CLIP 文本契约不一致")
            if data.get("truncated") is not False:
                raise ValueError("Chinese-CLIP 文本被截断，结果不可信")
        vector = data.get("embedding")
        if (not isinstance(vector, list) or len(vector) != dim
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in vector)):
            raise ValueError("Chinese-CLIP 特征向量无效")
        try:
            norm = math.hypot(*vector)
        except (OverflowError, ValueError):
            raise ValueError("Chinese-CLIP 特征向量无效") from None
        if not math.isfinite(norm) or abs(norm - 1) > 0.01:
            raise ValueError("Chinese-CLIP 特征未正确归一化")
        return [v / norm for v in vector]

    def _encode_text(self, text, space, dim, contract):
        data = self._request("POST", self.text_path, json={
            "text": text, "language": "auto", "template_id": "", "metadata": {},
        })
        vector = self._feature(data, space, dim, "text", contract)
        language = data.get("language")
        token_count = data.get("token_count")
        text_chars = data.get("text_chars")
        if (not isinstance(language, str) or not language
                or type(token_count) is not int or token_count < 1
                or type(text_chars) is not int or text_chars < 1):
            raise ValueError("Chinese-CLIP 文本编码信息无效")
        return vector, {"language": language, "token_count": token_count, "text_chars": text_chars}

    def _encode_image(self, image, space, dim):
        buffer = BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
        data = self._request("POST", self.image_path,
                             files={"file": ("person.png", buffer.getvalue(), "image/png")})
        return self._feature(data, space, dim, "image")

    def query_gallery(self, text: str, rows):
        text = (text or "").strip()
        if not text:
            raise ValueError("文本描述为空")
        if len(text) > self.max_text_chars:
            raise TextTooLongError("文本描述超过可编码长度，请精简后重试")
        with self._lock:
            info = self.health()
            space, dim, contract = (info["feature_space_id"], info["embedding_dim"],
                                    info["text_contract_id"])
            # 先编码文本，超长或契约不符时不会浪费登记图编码。
            query, text_info = self._encode_text(text, space, dim, contract)
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
                    vector = self._encode_image(picture, space, dim)
                current[key] = vector
                vectors[row.id] = vector
            # 只保留本轮有效登记图；任一失败都中止，避免返回不完整排序。
            self._cache = current
            return query, vectors, {
                "feature_space_id": space, "embedding_dim": dim,
                "text_contract_id": contract, **text_info,
            }