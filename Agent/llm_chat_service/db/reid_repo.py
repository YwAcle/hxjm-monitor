from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class ReidTargetRow:
    id: str
    name: str
    is_active: bool
    image_base64: str | None


def list_reid_targets(engine: Engine, schema: str, limit: int = 2000, active_only: bool = True, table_name: str = "reid_target") -> list[ReidTargetRow]:
    where = "where is_active = true" if active_only else ""
    sql = text(
        f"""
        select id, name, is_active, image_base64
        from {schema}.{table_name}
        {where}
        order by updated_at desc, created_at desc
        limit :limit
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(sql, {"limit": int(limit)}).mappings().all()

    return [
        ReidTargetRow(
            id=str(r["id"]),
            name=str(r["name"]),
            is_active=bool(r["is_active"]),
            image_base64=(str(r["image_base64"]) if r["image_base64"] is not None else None),
        )
        for r in rows
    ]


def get_person_by_id(engine: Engine, schema: str, person_id: str, table_name: str = "reid_target") -> ReidTargetRow | None:
    person_id = (person_id or "").strip()
    if person_id == "":
        return None

    sql = text(
        f"""
        select id, name, is_active, image_base64
        from {schema}.{table_name}
        where id = :id
        limit 1
        """
    )

    with engine.connect() as conn:
        r = conn.execute(sql, {"id": person_id}).mappings().first()

    if r is None:
        return None

    return ReidTargetRow(
        id=str(r["id"]),
        name=str(r["name"]),
        is_active=bool(r["is_active"]),
        image_base64=(str(r["image_base64"]) if r["image_base64"] is not None else None),
    )


def get_person_by_name(engine: Engine, schema: str, name: str, table_name: str = "reid_target") -> ReidTargetRow | None:
    name = (name or "").strip()
    if name == "":
        return None

    sql = text(
        f"""
        select id, name, is_active, image_base64
        from {schema}.{table_name}
        where name ilike :name
        order by is_active desc, updated_at desc, created_at desc
        limit 1
        """
    )

    with engine.connect() as conn:
        r = conn.execute(sql, {"name": f"%{name}%"}).mappings().first()

    if r is None:
        return None

    return ReidTargetRow(
        id=str(r["id"]),
        name=str(r["name"]),
        is_active=bool(r["is_active"]),
        image_base64=(str(r["image_base64"]) if r["image_base64"] is not None else None),
    )


def list_persons_by_name(engine: Engine, schema: str, name: str, limit: int = 100, table_name: str = "reid_target") -> list[ReidTargetRow]:
    """
    根据姓名查找所有匹配的人员（可能有多条记录）
    
    Args:
        engine: 数据库引擎
        schema: 数据库schema
        name: 人员姓名
        limit: 最大返回数量
        table_name: 表名，默认为 reid_target
        
    Returns:
        匹配的人员列表，按 is_active desc, updated_at desc, created_at desc 排序
    """
    name = (name or "").strip()
    if name == "":
        return []

    sql = text(
        f"""
        select id, name, is_active, image_base64
        from {schema}.{table_name}
        where name ilike :name
        order by is_active desc, updated_at desc, created_at desc
        limit :limit
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(sql, {"name": f"%{name}%", "limit": limit}).mappings().all()

    return [
        ReidTargetRow(
            id=str(r["id"]),
            name=str(r["name"]),
            is_active=bool(r["is_active"]),
            image_base64=(str(r["image_base64"]) if r["image_base64"] is not None else None),
        )
        for r in rows
    ]
