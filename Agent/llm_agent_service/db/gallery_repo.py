"""只读复用 reid_target；不修改已有身份关联和特征。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import text


@dataclass(frozen=True)
class GalleryTarget:
    id: str
    name: str
    employee_id: str | None
    image_base64: str | None


def list_gallery(engine, schema: str, limit: int) -> list[GalleryTarget]:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
        raise ValueError("不支持的数据库 schema 名称")
    with engine.connect() as conn:
        rows = conn.execute(text(f'''
            SELECT id, name, employee_id, image_base64
            FROM "{schema}".reid_target
            WHERE is_active = true
            ORDER BY id
            LIMIT :limit
        '''), {"limit": limit}).mappings().all()
    result = []
    for row in rows:
        result.append(GalleryTarget(
            id=str(row["id"]), name=row["name"], employee_id=row["employee_id"],
            image_base64=row["image_base64"],
        ))
    return result
