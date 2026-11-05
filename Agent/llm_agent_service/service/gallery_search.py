"""用户主动检索：历史轨迹身份检索和登记照片文本检索。"""

from __future__ import annotations

import base64
import math
import os
from collections import defaultdict
from datetime import tzinfo
from pathlib import Path
from uuid import uuid4

from PIL import Image

from llm_agent_service.db.gallery_repo import GalleryTarget, list_gallery
from llm_agent_service.db.identity_repo import (
    count_searchable_features,
    get_feature_space,
    list_occurrences,
    search_identities,
)
from llm_agent_service.service.clipreid_client import ClipReIDClient
from llm_agent_service.service.text_reid_client import TextReIDClient, TextTooLongError
from llm_report_service.llm.vision import decode_base64_image, image_to_data_url

_PREVIEW_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_PREVIEW_MAX_BYTES = 200 * 1024


class GallerySearchService:
    def __init__(self, *, engine, schema: str, feature_client: ClipReIDClient,
                 text_feature_client: TextReIDClient,
                 candidate_limit: int = 2000, text_max_chars: int = 200,
                 occurrence_limit: int = 5, timezone: tzinfo | None = None,
                 media_root: str | Path | None = None):
        self.engine = engine
        self.schema = schema
        self.feature_client = feature_client
        self.text_feature_client = text_feature_client
        self.candidate_limit = candidate_limit
        self.text_max_chars = text_max_chars
        self.occurrence_limit = occurrence_limit
        self.timezone = timezone if isinstance(timezone, tzinfo) else None
        root = media_root if media_root is not None else os.getenv("AGENT_MEDIA_ROOT", "")
        self.media_root = Path(root).expanduser().resolve() if str(root).strip() else None

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
        # 查询图仍由 CLIP-ReID 编码；候选向量直接读取样本管线已写入的 feature 表。
        query, space = self.feature_client.query_feature(image, bbox=bbox, feature=feature)
        base = {
            "type": "pedestrian_search", "search_type": "image",
            "scope": "identity_history", "method": self.feature_client.method,
            "embedding_model": space, "feature_dimension": len(query),
            "score_type": "cosine_similarity", "count": 0, "candidates": [],
        }
        info = get_feature_space(self.engine, self.schema, space)
        if info is None:
            return dict(base, status="feature_space_missing",
                        message="数据库中没有该特征空间，未执行轨迹检索。")
        if (not info.enabled or info.metric != "cosine"
                or info.dimensions != len(query) or info.object_type != "person"):
            return dict(base, status="feature_space_incompatible",
                        message="数据库特征空间与当前 CLIP-ReID 不兼容，未执行轨迹检索。")
        scanned = count_searchable_features(self.engine, self.schema, space)
        if scanned == 0:
            return dict(base, status="empty_history", scanned_count=0,
                        compatible_count=0, skipped_count=0,
                        message="已入库历史轨迹中没有可检索特征（可能尚未写入或已到期）。")
        candidates = search_identities(
            self.engine, self.schema, space, self._vector_literal(query), top_k)
        if not candidates:
            return dict(base, status="no_identity_candidates", scanned_count=scanned,
                        compatible_count=0, skipped_count=0,
                        message="历史轨迹特征存在，但没有关联到有效身份，无法返回人员候选。")
        occurrences = list_occurrences(
            self.engine, self.schema,
            [candidate.identity_id for candidate in candidates],
            per_identity=self.occurrence_limit,
        )
        grouped = defaultdict(list)
        for item in occurrences:
            grouped[item.identity_id].append(item)
        items = [self._identity_candidate(candidate, grouped.get(candidate.identity_id, []))
                 for candidate in candidates]
        return dict(
            base, status="ok", scanned_count=scanned,
            compatible_count=candidates[0].compatible_count, skipped_count=0,
            count=len(items),
            message="在已入库历史轨迹特征中按余弦相似度排序；候选是临时身份或登记身份，"
                    "相似度不是身份确认。occurrences 是该身份最近的真实轨迹出现记录，"
                    "不是实时位置，且只覆盖当前保留期内的轨迹。",
            candidates=items,
        )

    @staticmethod
    def _vector_literal(vector) -> str:
        return "[" + ",".join(str(float(value)) for value in vector) + "]"

    def _time(self, value) -> str | None:
        if value is None:
            return None
        if self.timezone is not None and value.tzinfo is not None:
            value = value.astimezone(self.timezone)
        return value.isoformat()

    def _identity_candidate(self, candidate, occurrences) -> dict:
        first = occurrences[0] if occurrences else None
        kind = "登记身份" if candidate.identity_kind == "registered" else "临时身份"
        label = candidate.display_name or (
            f"{kind} #{candidate.display_no}" if candidate.display_no is not None else kind)
        return {
            "identity_id": candidate.identity_id,
            # 保留 person_id 字段供现有前端候选卡片复用；它不是旧登记库 ID。
            "person_id": candidate.identity_id,
            "identity_kind": candidate.identity_kind,
            "display_no": candidate.display_no,
            "name": candidate.display_name,
            "label": label,
            "employee_id": candidate.employee_id,
            "similarity": candidate.similarity,
            # 用最近一次轨迹的裁剪图作为候选预览，避免前端另需通行证或鉴权接口。
            "image_base64": self._preview_data_url(first),
            "first_seen_at": self._time(candidate.first_seen_at)
            or (self._time(first.first_seen_at) if first else None),
            "last_seen_at": self._time(candidate.last_seen_at)
            or (self._time(first.last_seen_at) if first else None),
            "occurrence_count": first.occurrence_count if first else 0,
            "occurrences": [self._occurrence(row) for row in occurrences],
        }

    def _preview_data_url(self, row) -> str | None:
        """按 media_asset.storage_key 读取本地裁剪图并编码为 data URL。

        只有显式配置媒体根目录时才读取，避免服务进程随意访问任意路径。
        """
        if row is None or self.media_root is None or not row.storage_key:
            return None
        content_type = (row.content_type or "").lower()
        if content_type not in _PREVIEW_CONTENT_TYPES:
            return None
        try:
            path = (self.media_root / row.storage_key).resolve()
            if not path.is_relative_to(self.media_root) or not path.is_file():
                return None
            if path.stat().st_size > _PREVIEW_MAX_BYTES:
                return None
            data = path.read_bytes()
        except (OSError, ValueError):
            return None
        return f"data:{content_type};base64,{base64.b64encode(data).decode('ascii')}"

    def _occurrence(self, row) -> dict:
        return {
            "tracklet_id": row.tracklet_id,
            "source_id": row.source_id,
            "camera": row.camera_name or row.source_id,
            "start_at": self._time(row.first_observed_at),
            "end_at": self._time(row.last_observed_at),
            "asset_id": row.asset_id,
            # 与后端的素材读取接口一致；是否需要鉴权由前端当前登录态处理。
            "access_url": (f"/api/v1/business/assets/{row.asset_id}/content"
                           if row.asset_id else None),
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
