"""用户主动检索登记库：CLIP-ReID 图片检索和 Chinese-CLIP 文本检索。"""

from __future__ import annotations

import math
from uuid import uuid4

from PIL import Image

from llm_agent_service.db.gallery_repo import GalleryTarget, list_gallery
from llm_agent_service.service.clipreid_client import ClipReIDClient
from llm_agent_service.service.text_reid_client import TextReIDClient, TextTooLongError
from llm_report_service.llm.vision import decode_base64_image, image_to_data_url


class GallerySearchService:
    def __init__(self, *, engine, schema: str, feature_client: ClipReIDClient,
                 text_feature_client: TextReIDClient,
                 candidate_limit: int = 2000, text_max_chars: int = 200):
        self.engine = engine
        self.schema = schema
        self.feature_client = feature_client
        self.text_feature_client = text_feature_client
        self.candidate_limit = candidate_limit
        self.text_max_chars = text_max_chars

    @staticmethod
    def _candidate(row: GalleryTarget) -> dict:
        return {"person_id": row.id, "name": row.name, "employee_id": row.employee_id,
                "image_base64": row.image_base64}

    def search_image(self, image_base64: str, top_k: int) -> dict:
        base = {"type": "pedestrian_search", "search_type": "image", "scope": "active_reid_target",
                "count": 0, "candidates": []}
        if not image_base64:
            return dict(base, status="missing_image", message="请上传一张单人行人裁剪图。")
        image = decode_base64_image(image_base64)
        if image is None:
            raise ValueError("查询图片无法解码")
        return self._search_with_features(image, top_k)

    def search_screenshot(self, image_base64: str, top_k: int) -> dict:
        if not image_base64:
            return {"type": "pedestrian_search", "status": "missing_image", "message": "请上传截图。"}
        image = self.feature_client.screenshot_image(image_base64)
        detected = self.feature_client.detect(image)
        status = detected.get("status")
        if status not in {"extracted", "selection_required", "no_person"}:
            raise ValueError("截图检测返回未知状态")
        if status == "no_person":
            return {"type": "pedestrian_search", "status": status, "message": "未检测到行人，请上传更清晰的图片或裁剪单人图片后重试。"}
        if detected.get("coordinate_system") != "xyxy_pixels_exif_corrected":
            raise ValueError("截图检测坐标系不支持")
        if (detected.get("image_width"), detected.get("image_height")) != image.size:
            raise ValueError("截图检测尺寸不一致")
        candidates = detected.get("candidates")
        if not isinstance(candidates, list) or not 1 <= len(candidates) <= 100:
            raise ValueError("截图检测候选无效")
        ids = set()
        for candidate in candidates:
            if not isinstance(candidate, dict):
                raise ValueError("截图候选格式无效")
            cid, bbox = candidate.get("candidate_id"), candidate.get("bbox")
            if not isinstance(cid, str) or not cid.isdigit() or cid in ids:
                raise ValueError("截图候选编号无效")
            ids.add(cid)
            if (not isinstance(bbox, list) or len(bbox) != 4 or any(type(v) is not int for v in bbox)
                    or not 0 <= bbox[0] < bbox[2] <= image.width
                    or not 0 <= bbox[1] < bbox[3] <= image.height):
                raise ValueError("截图候选坐标无效")
        if status == "extracted":
            if len(candidates) != 1 or not isinstance(detected.get("feature"), dict):
                raise ValueError("单人截图特征缺失")
            return self._search_with_features(image, top_k, feature=detected["feature"])
        if len(candidates) < 2 or detected.get("feature") is not None:
            raise ValueError("多人截图检测响应无效")
        return {"type": "pedestrian_selection", "status": "selection_required",
                "source_asset_id": uuid4().hex, "image_width": image.width, "image_height": image.height,
                "coordinate_system": "xyxy_pixels_exif_corrected", "candidates": [dict(c, image_base64=image_to_data_url(image.crop(c["bbox"]), max_side=256)) for c in candidates], "top_k": top_k,
                "message": "检测到多名行人，请明确回复选择编号，例如：选择2。编号仅对应本次截图，不是人员身份。"}

    def search_selected(self, image_base64, bbox, top_k):
        return self._search_with_features(self.feature_client.screenshot_image(image_base64), top_k, bbox=bbox)

    @staticmethod
    def _rank(rows, query, vectors):
        ranked = []
        for row in rows:
            vector = vectors.get(row.id)
            if vector is not None:
                score = max(-1.0, min(1.0, math.fsum(a * b for a, b in zip(query, vector))))
                ranked.append((score, row))
        ranked.sort(key=lambda item: (-item[0], item[1].id))
        return ranked

    def _search_with_features(self, image: Image.Image, top_k: int, *, bbox=None, feature=None) -> dict:
        rows = list_gallery(self.engine, self.schema, self.candidate_limit + 1)
        truncated = len(rows) > self.candidate_limit
        rows = rows[:self.candidate_limit]
        # 原库特征未经版本验证；查询和登记照片由同一编码器提取特征。
        query, vectors, model_id = self.feature_client.query_gallery(image, rows, bbox=bbox, feature=feature)
        ranked = self._rank(rows, query, vectors)
        return {
            "type": "pedestrian_search", "search_type": "image",
            "status": "ok" if ranked else ("empty_gallery" if not rows else "no_valid_images"),
            "scope": "active_reid_target", "method": self.feature_client.method,
            "embedding_model": model_id, "feature_dimension": len(query),
            "score_type": "cosine_similarity", "scanned_count": len(rows),
            "compatible_count": len(ranked), "skipped_count": len(rows) - len(ranked),
            "gallery_truncated": truncated, "count": min(top_k, len(ranked)),
            "message": "同一特征空间检索登记照片的外观相似候选，不确认身份或在场情况；未使用原库特征。",
            "candidates": [dict(self._candidate(row), similarity=score) for score, row in ranked[:top_k]],
        }

    def search_description(self, description: str, top_k: int) -> dict:
        """按外观描述在登记库中做文本→图像向量检索。"""
        base = {"type": "pedestrian_search", "search_type": "text", "scope": "active_reid_target",
                "count": 0, "candidates": []}
        text = (description or "").strip()
        if not text:
            return dict(base, status="missing_description", message="请提供衣着、颜色、携带物品等外观描述。")
        if len(text) > self.text_max_chars:
            return dict(base, status="description_too_long",
                        message=f"外观描述过长，请精简到{self.text_max_chars}个字符以内。")
        rows = list_gallery(self.engine, self.schema, self.candidate_limit + 1)
        truncated = len(rows) > self.candidate_limit
        rows = rows[:self.candidate_limit]
        if not rows:
            return dict(base, status="empty_gallery", scanned_count=0, compatible_count=0,
                        skipped_count=0, gallery_truncated=False,
                        message="登记库中没有有效登记照片，未执行文本检索。")
        try:
            query, vectors, info = self.text_feature_client.query_gallery(text, rows)
        except TextTooLongError:
            return dict(base, status="description_too_long",
                        message=f"外观描述超过模型可编码长度，请精简到{self.text_max_chars}个字符以内。")
        ranked = self._rank(rows, query, vectors)
        return dict(
            base,
            status="ok" if ranked else "no_valid_images",
            method=self.text_feature_client.method,
            embedding_model=info["feature_space_id"],
            text_contract_id=info["text_contract_id"],
            feature_dimension=info["embedding_dim"],
            score_type="cosine_similarity",
            text_chars=info["text_chars"], token_count=info["token_count"],
            language=info["language"],
            scanned_count=len(rows), compatible_count=len(ranked),
            skipped_count=len(rows) - len(ranked), gallery_truncated=truncated,
            count=min(top_k, len(ranked)),
            message="按文本描述与登记照片在 Chinese-CLIP 同一特征空间中的余弦相似度排序；"
                    "没有校准阈值，候选仅用于外观筛选，不确认身份或在场情况。",
            candidates=[dict(self._candidate(row), similarity=score)
                        for score, row in ranked[:top_k]],
        )
