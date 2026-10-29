"""会话级图片资产库：图片单独保存，后续追问按引用重新附带。

聊天历史只保存文本，图片按会话保存在这里。资产带 TTL 和容量上限，
不写磁盘、不写数据库；服务重启或会话清理后即失效。
"""

from __future__ import annotations

import hashlib
import re
from collections import OrderedDict
from dataclasses import dataclass, replace
from threading import RLock
from time import monotonic
from uuid import uuid4

# 引用此前图片的常见说法；只在没有新上传图片时用于决定回注哪一张。
_REFERENCE_KEYWORDS = (
    "上图", "上一张", "上张", "前一张", "刚才的图", "刚才那张", "刚才的图片", "刚才上传",
    "之前的图", "之前那张", "前面那张", "那张图", "这张图", "那张照片", "这张照片",
    "张图", "这幅", "原图", "图片里", "图片中", "图中", "图里", "图上",
    "照片里", "照片中", "照片上", "画面", "影像", "镜头", "截图里", "截图中",
    "previous image", "last image", "image above", "that image", "this image",
    "the picture", "the photo", "in the picture", "in the photo",
)

_ORDINALS = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}

_ORDINAL_PATTERN = re.compile(
    r"第\s*([0-9]{1,2}|[一二三四五六七八九十两])\s*[张幅]\s*(?:图|图片|照片|截图)?"
)

_DATA_URL_PATTERN = re.compile(r"^data:([^;,]+)?(?:;[^,]*)?,(.*)$", re.S)

IMAGE_ASSET_MISSING_NOTE = (
    "（系统提示：用户引用了此前上传的图片，但该图片已过期或不存在，本轮没有附带任何图片。"
    "不要根据历史文字猜测画面，也不要声称看过图片；请让用户重新上传。）"
)


def image_reference(prompt: str) -> tuple[bool, int | None]:
    """判断用户是否引用会话图片，并返回显式序号（从旧到新，1 起）。"""

    text = str(prompt or "").strip()
    if not text:
        return False, None
    match = _ORDINAL_PATTERN.search(text)
    if match:
        raw = match.group(1)
        ordinal = int(raw) if raw.isdigit() else _ORDINALS.get(raw)
        if ordinal:
            return True, ordinal
    lowered = text.lower()
    if any(word in lowered for word in _REFERENCE_KEYWORDS):
        return True, None
    return False, None


def _split_data_url(data_url: str) -> tuple[str, str]:
    """拆分 Data URL，返回 (Base64 负载, MIME)；普通 Base64 原样返回。"""

    match = _DATA_URL_PATTERN.match(data_url)
    if match:
        return match.group(2), (match.group(1) or "application/octet-stream").lower()
    return data_url, ""


def _base64_bytes(payload: str) -> int:
    """按 Base64 长度估算原始字节数，不真正解码。"""

    cleaned = "".join(payload.split())
    padding = len(cleaned) - len(cleaned.rstrip("="))
    return max(0, len(cleaned) * 3 // 4 - padding)


@dataclass(frozen=True)
class ImageAsset:
    """一张会话图片；Data URL 只在服务端和模型输入中使用。"""

    asset_id: str
    data_url: str
    mime: str
    bytes_len: int
    sha256: str
    created: float

    def describe(self) -> dict[str, object]:
        return {
            "asset_id": self.asset_id,
            "mime": self.mime,
            "bytes": self.bytes_len,
            "sha256_prefix": self.sha256[:12],
            "created": round(self.created, 3),
        }


class SessionImageAssets:
    """按会话保存最近上传的图片，支持去重、TTL 和容量上限。"""

    def __init__(
        self,
        *,
        ttl_s: int = 1800,
        max_per_session: int = 4,
        max_bytes_per_session: int = 32 * 1024 * 1024,
        max_total_bytes: int = 256 * 1024 * 1024,
    ) -> None:
        for name, value in (
            ("ttl_s", ttl_s),
            ("max_per_session", max_per_session),
            ("max_bytes_per_session", max_bytes_per_session),
            ("max_total_bytes", max_total_bytes),
        ):
            if value < 1:
                raise ValueError(f"{name} 至少必须为 1")
        self.ttl_s = ttl_s
        self.max_per_session = max_per_session
        self.max_bytes_per_session = max_bytes_per_session
        self.max_total_bytes = max_total_bytes
        self._sessions: OrderedDict[str, OrderedDict[str, ImageAsset]] = OrderedDict()
        # 全局插入顺序，仅用于超出总容量时淘汰最早的图片。
        self._global_order: OrderedDict[tuple[str, str], int] = OrderedDict()
        self._total_bytes = 0
        self._lock = RLock()

    def put(self, session_id: str, data_url: str) -> ImageAsset:
        """保存一张图片；同会话重复图片复用原资产并刷新时间。"""

        if not session_id:
            raise ValueError("session_id 不能为空")
        url = str(data_url or "").strip()
        if not url:
            raise ValueError("图片内容为空")
        payload, mime = _split_data_url(url)
        bytes_len = _base64_bytes(payload)
        if bytes_len > self.max_bytes_per_session or bytes_len > self.max_total_bytes:
            raise ValueError("图片超过会话图片资产容量限制")
        digest = hashlib.sha256(payload.encode("ascii", "ignore")).hexdigest()

        with self._lock:
            self._prune()
            session = self._sessions.get(session_id) or {}
            duplicate = next(
                (asset for asset in session.values() if asset.sha256 == digest), None
            )
            if duplicate is not None:
                self._remove(session_id, duplicate.asset_id)
                asset = replace(duplicate, created=monotonic())
                self._add(session_id, asset)
                return asset

            asset = ImageAsset(uuid4().hex, url, mime, bytes_len, digest, monotonic())
            while True:
                current = self._sessions.get(session_id) or {}
                if len(current) < self.max_per_session and (
                    sum(item.bytes_len for item in current.values()) + bytes_len
                    <= self.max_bytes_per_session
                ):
                    break
                # 单会话先淘汰最早的图片，再做全局淘汰。
                self._remove(session_id, next(iter(current)))
            self._add(session_id, asset)
            while self._total_bytes > self.max_total_bytes and self._global_order:
                old_session, old_asset = next(iter(self._global_order))
                self._remove(old_session, old_asset)
            return asset

    def assets(self, session_id: str) -> list[ImageAsset]:
        """按上传顺序返回会话内有效图片，最早的在前。"""

        if not session_id:
            return []
        with self._lock:
            self._prune()
            return list((self._sessions.get(session_id) or {}).values())

    def latest(self, session_id: str) -> ImageAsset | None:
        assets = self.assets(session_id)
        return assets[-1] if assets else None

    def resolve(self, session_id: str, prompt: str) -> tuple[ImageAsset | None, str]:
        """按用户说法选择要回注的图片。

        返回 `(asset, status)`，status 为 `no_reference`、`available` 或 `missing`。
        """

        referenced, ordinal = image_reference(prompt)
        if not referenced:
            return None, "no_reference"
        assets = self.assets(session_id)
        if not assets:
            return None, "missing"
        if ordinal is None:
            asset = assets[-1]
        elif 1 <= ordinal <= len(assets):
            asset = assets[ordinal - 1]
        else:
            return None, "missing"
        self._touch(session_id, asset.asset_id)
        return asset, "available"

    def clear(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session is None:
                return False
            for asset_id, asset in session.items():
                self._global_order.pop((session_id, asset_id), None)
                self._total_bytes -= asset.bytes_len
            return True

    def _touch(self, session_id: str, asset_id: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            asset = (session or {}).get(asset_id)
            if asset is None:
                return
            session[asset_id] = replace(asset, created=monotonic())
            self._sessions.move_to_end(session_id)

    def _add(self, session_id: str, asset: ImageAsset) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            session = OrderedDict()
            self._sessions[session_id] = session
        else:
            self._sessions.move_to_end(session_id)
        session[asset.asset_id] = asset
        self._global_order[(session_id, asset.asset_id)] = asset.bytes_len
        self._total_bytes += asset.bytes_len

    def _remove(self, session_id: str, asset_id: str) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        asset = session.pop(asset_id, None)
        if asset is None:
            return
        self._global_order.pop((session_id, asset_id), None)
        self._total_bytes -= asset.bytes_len
        if not session:
            self._sessions.pop(session_id, None)

    def _prune(self) -> None:
        now = monotonic()
        for session_id in list(self._sessions):
            for asset in list(self._sessions[session_id].values()):
                if now - asset.created >= self.ttl_s:
                    self._remove(session_id, asset.asset_id)


__all__ = [
    "IMAGE_ASSET_MISSING_NOTE",
    "ImageAsset",
    "SessionImageAssets",
    "image_reference",
]