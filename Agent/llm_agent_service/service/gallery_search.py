"""用户主动检索：历史轨迹身份检索和登记照片文本检索。"""

from __future__ import annotations

import base64
import os
from collections import defaultdict
from datetime import tzinfo
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from PIL import Image

from llm_agent_service.db.identity_repo import (
    count_searchable_features,
    count_text_identities,
    count_text_samples,
    get_feature_space,
    list_occurrences,
    search_identities,
    search_text_identities,
    search_text_samples,
)
from llm_agent_service.service.clipreid_client import ClipReIDClient
from llm_agent_service.service.text_reid_client import TextReIDClient, TextTooLongError
from llm_report_service.llm.vision import decode_base64_image, image_to_data_url

_PREVIEW_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_PREVIEW_MAX_BYTES = 200 * 1024


class GallerySearchService:
    def __init__(self, *, engine, schema: str, feature_client: ClipReIDClient,
                 text_feature_client: TextReIDClient,
                 text_max_chars: int = 200,
                 occurrence_limit: int = 5, timezone: tzinfo | None = None,
                 media_root: str | Path | None = None):
        self.engine = engine
        self.schema = schema
        self.feature_client = feature_client
        self.text_feature_client = text_feature_client
        self.text_max_chars = text_max_chars
        self.occurrence_limit = occurrence_limit
        self.timezone = timezone if isinstance(timezone, tzinfo) else None
        root = media_root if media_root is not None else os.getenv("AGENT_MEDIA_ROOT", "")
        self.media_root = Path(root).expanduser().resolve() if str(root).strip() else None

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
        """按外观描述检索登记身份在 Chinese-CLIP 空间中的外观特征。"""
        base = {"type": "pedestrian_search", "search_type": "text",
                "scope": "registered_identity", "count": 0, "candidates": []}
        text = (description or "").strip()
        if not text:
            return dict(base, status="missing_description", message="请提供衣着、颜色、携带物品等外观描述。")
        if len(text) > self.text_max_chars:
            return dict(base, status="description_too_long",
                        message=f"外观描述过长，请精简到{self.text_max_chars}个字符以内。")
        info = self.text_feature_client.health()
        space = info["feature_space_id"]
        db_space = get_feature_space(self.engine, self.schema, space)
        if db_space is None:
            return dict(base, status="feature_space_missing",
                        message="数据库中还没有登记身份文本检索特征空间，未执行检索。")
        if (not db_space.enabled or db_space.metric != "cosine"
                or db_space.object_type != "person"
                or db_space.dimensions != info["embedding_dim"]):
            return dict(base, status="feature_space_incompatible",
                        message="登记身份文本检索特征空间与当前 Chinese-CLIP 不兼容，未执行检索。")
        scanned = count_text_identities(self.engine, self.schema, space)
        if scanned == 0:
            return dict(base, status="empty_gallery", scanned_count=0, compatible_count=0,
                        message="登记身份还没有可用的中文图文检索特征，未执行文本检索。")
        try:
            query, info = self.text_feature_client.query_text(text)
        except TextTooLongError:
            return dict(base, status="description_too_long",
                        message=f"外观描述超过模型可编码长度，请精简到{self.text_max_chars}个字符以内。")
        candidates = search_text_identities(
            self.engine, self.schema, space, self._vector_literal(query), top_k)
        if not candidates:
            return dict(base, status="no_identity_candidates", scanned_count=scanned,
                        compatible_count=0,
                        message="登记身份外观特征存在，但没有关联到有效登记身份，无法返回候选。")
        return dict(
            base,
            status="ok",
            method=self.text_feature_client.method,
            embedding_model=space,
            text_contract_id=info["text_contract_id"],
            feature_dimension=info["embedding_dim"],
            score_type="cosine_similarity",
            text_chars=info["text_chars"], token_count=info["token_count"],
            language=info["language"],
            scanned_count=scanned, compatible_count=candidates[0].compatible_count,
            count=len(candidates),
            message="按文本描述与登记身份照片在 Chinese-CLIP 同一特征空间中的余弦相似度排序；"
                    "没有校准阈值，候选仅用于外观筛选，不确认身份或在场情况。",
            candidates=[self._text_candidate(candidate) for candidate in candidates],
        )

    def search_description_in_history(self, description: str, top_k: int) -> dict:
        """按外观描述检索全部历史轨迹裁剪图，不限于已登记身份。

        与 ``search_description`` 使用同一个 Chinese-CLIP 文本空间，但读取样本
        管线为 history 样本写入的特征，因此候选是真实轨迹而不是登记照片。
        """
        base = {"type": "pedestrian_search", "search_type": "text",
                "scope": "history_samples", "count": 0, "candidates": []}
        text = (description or "").strip()
        if not text:
            return dict(base, status="missing_description", message="请提供衣着、颜色、携带物品等外观描述。")
        if len(text) > self.text_max_chars:
            return dict(base, status="description_too_long",
                        message=f"外观描述过长，请精简到{self.text_max_chars}个字符以内。")
        info = self.text_feature_client.health()
        space = info["feature_space_id"]
        db_space = get_feature_space(self.engine, self.schema, space)
        if db_space is None:
            return dict(base, status="feature_space_missing",
                        message="数据库中还没有登记身份文本检索特征空间，未执行检索。")
        if (not db_space.enabled or db_space.metric != "cosine"
                or db_space.object_type != "person"
                or db_space.dimensions != info["embedding_dim"]):
            return dict(base, status="feature_space_incompatible",
                        message="登记身份文本检索特征空间与当前 Chinese-CLIP 不兼容，未执行检索。")
        scanned = count_text_samples(self.engine, self.schema, space)
        if scanned == 0:
            return dict(base, status="empty_text_history", scanned_count=0, compatible_count=0,
                        message="历史轨迹还没有写入 Chinese-CLIP 特征，未执行文本检索。")
        try:
            query, info = self.text_feature_client.query_text(text)
        except TextTooLongError:
            return dict(base, status="description_too_long",
                        message=f"外观描述超过模型可编码长度，请精简到{self.text_max_chars}个字符以内。")
        candidates = search_text_samples(
            self.engine, self.schema, space, self._vector_literal(query), top_k)
        if not candidates:
            return dict(base, status="no_text_candidates", scanned_count=scanned,
                        compatible_count=0,
                        message="历史轨迹文本特征存在，但没有可返回的轨迹候选。")
        return dict(
            base,
            status="ok",
            method=self.text_feature_client.method,
            embedding_model=space,
            text_contract_id=info["text_contract_id"],
            feature_dimension=info["embedding_dim"],
            score_type="cosine_similarity",
            text_chars=info["text_chars"], token_count=info["token_count"],
            language=info["language"],
            scanned_count=scanned, compatible_count=candidates[0].compatible_count,
            count=len(candidates),
            message="在全部已入库历史轨迹裁剪图中按外观描述的余弦相似度排序；"
                    "候选是轨迹图像而不是身份确认，已关联身份的会显示姓名，"
                    "未识别轨迹没有姓名。结果只覆盖当前保留期内的图像。",
            candidates=[self._text_sample_candidate(candidate) for candidate in candidates],
        )

    def _text_sample_candidate(self, candidate) -> dict:
        kind = "登记身份" if candidate.identity_kind == "registered" else "临时身份"
        label = candidate.display_name or (
            f"{kind} #{candidate.display_no}"
            if candidate.display_no is not None else "未识别轨迹")
        occurrence = {
            "tracklet_id": candidate.tracklet_id,
            "source_id": candidate.source_id,
            "camera": candidate.camera_name or candidate.source_id,
            "start_at": self._time(candidate.first_observed_at),
            "end_at": self._time(candidate.last_observed_at),
            "asset_id": candidate.asset_id,
            "access_url": (f"/api/v1/business/assets/{candidate.asset_id}/content"
                           if candidate.asset_id else None),
        }
        return {
            "tracklet_id": candidate.tracklet_id,
            "sample_id": candidate.sample_id,
            "feature_id": candidate.feature_id,
            "asset_id": candidate.asset_id,
            "access_url": occurrence["access_url"],
            "image_base64": self._preview_data_url(
                SimpleNamespace(storage_key=candidate.storage_key,
                                content_type=candidate.content_type)),
            "similarity": candidate.similarity,
            "identity_id": candidate.identity_id,
            # 保留 person_id 字段供现有前端候选卡片复用；未识别轨迹为 null。
            "person_id": candidate.identity_id,
            "identity_kind": candidate.identity_kind,
            "display_no": candidate.display_no,
            "name": candidate.display_name,
            "label": label,
            "employee_id": candidate.employee_id,
            "occurred_at": self._time(candidate.occurred_at),
            "occurrence_count": 1,
            "occurrences": [occurrence],
        }

    def _text_candidate(self, candidate) -> dict:
        kind = "登记身份"
        label = candidate.display_name or (
            f"{kind} #{candidate.display_no}"
            if candidate.display_no is not None else kind)
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
            "sample_id": candidate.sample_id,
            "feature_id": candidate.feature_id,
            # 登记照片由素材接口读取，避免把数据库中的 Base64 大字段放进检索响应。
            "asset_id": candidate.asset_id,
            "access_url": (f"/api/v1/business/assets/{candidate.asset_id}/content"
                           if candidate.asset_id else None),
            "first_seen_at": self._time(candidate.first_seen_at),
            "last_seen_at": self._time(candidate.last_seen_at),
        }
