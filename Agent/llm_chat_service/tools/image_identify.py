from __future__ import annotations

import base64
from io import BytesIO

import numpy as np
from PIL import Image
from sqlalchemy.engine import Engine

from llm_chat_service.db.reid_repo import list_reid_targets
from llm_report_service.llm.vision import decode_base64_image


def _load_image_from_bytes(image_bytes: bytes) -> Image.Image | None:
    try:
        return Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return None


def _ahash(image: Image.Image, hash_size: int = 8) -> np.ndarray:
    img = image.convert("L").resize((hash_size, hash_size), Image.Resampling.BILINEAR)
    arr = np.asarray(img, dtype=np.float32)
    mean = float(arr.mean()) if arr.size > 0 else 0.0
    return (arr >= mean).astype(np.uint8).reshape(-1)


def _ahash_similarity(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape or a.size == 0:
        return 0.0
    dist = int(np.bitwise_xor(a, b).sum())
    return 1.0 - (dist / float(a.size))


def identify_person_by_image(
    *,
    engine: Engine,
    schema: str,
    image_bytes: bytes,
    top_k: int = 3,
    candidate_limit: int = 2000,
    min_score: float = 0.72,
) -> dict:
    img = _load_image_from_bytes(image_bytes)
    if img is None:
        return {"type": "unknown", "candidates": []}

    qh = _ahash(img)
    targets = list_reid_targets(engine, schema, limit=int(candidate_limit), active_only=True)

    scored: list[dict] = []
    for t in targets:
        if t.image_base64 is None or str(t.image_base64).strip() == "":
            continue
        cand_img = decode_base64_image(t.image_base64)
        if cand_img is None:
            continue
        ch = _ahash(cand_img)
        score = _ahash_similarity(qh, ch)
        scored.append({"person_id": t.id, "name": t.name, "score": float(score)})

    scored.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    candidates = scored[: max(0, int(top_k))]

    if len(candidates) == 0:
        return {"type": "unknown", "candidates": []}

    best = candidates[0]
    if float(best.get("score", 0.0)) >= float(min_score):
        return {
            "type": "gallery",
            "id": best.get("person_id"),
            "name": best.get("name"),
            "candidates": candidates,
        }

    return {"type": "unknown", "candidates": candidates}
