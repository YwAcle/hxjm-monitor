"""
人员数据访问层 - reid_target 表
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class PersonRow:
    """人员数据行"""
    id: str
    name: str
    employee_id: Optional[str]
    image_base64: Optional[str]
    is_active: bool


def get_person_by_name(
    engine: Engine,
    schema: str,
    name: str,
) -> Optional[PersonRow]:
    """
    根据姓名查找人员（模糊匹配）
    
    Args:
        engine: 数据库引擎
        schema: 数据库schema
        name: 人员姓名
        
    Returns:
        PersonRow 或 None
    """
    sql = text(
        f"""
        SELECT id, name, employee_id, image_base64, is_active
        FROM {schema}.reid_target
        WHERE is_active = true
          AND (name ILIKE :pattern OR name = :exact_name)
        ORDER BY 
            CASE WHEN name = :exact_name THEN 0 ELSE 1 END,
            created_at DESC
        LIMIT 1
        """
    )
    
    with engine.connect() as conn:
        row = conn.execute(
            sql,
            {"pattern": f"%{name}%", "exact_name": name},
        ).mappings().first()
    
    if row is None:
        return None
    
    return PersonRow(
        id=str(row["id"]),
        name=str(row["name"]),
        employee_id=str(row["employee_id"]) if row["employee_id"] else None,
        image_base64=str(row["image_base64"]) if row["image_base64"] else None,
        is_active=bool(row["is_active"]),
    )


def get_person_by_id(
    engine: Engine,
    schema: str,
    person_id: str,
) -> Optional[PersonRow]:
    """
    根据ID查找人员
    
    Args:
        engine: 数据库引擎
        schema: 数据库schema
        person_id: 人员ID
        
    Returns:
        PersonRow 或 None
    """
    sql = text(
        f"""
        SELECT id, name, employee_id, image_base64, is_active
        FROM {schema}.reid_target
        WHERE id = :person_id
        LIMIT 1
        """
    )
    
    with engine.connect() as conn:
        row = conn.execute(
            sql,
            {"person_id": person_id},
        ).mappings().first()
    
    if row is None:
        return None
    
    return PersonRow(
        id=str(row["id"]),
        name=str(row["name"]),
        employee_id=str(row["employee_id"]) if row["employee_id"] else None,
        image_base64=str(row["image_base64"]) if row["image_base64"] else None,
        is_active=bool(row["is_active"]),
    )


def list_all_persons(
    engine: Engine,
    schema: str,
    active_only: bool = True,
    limit: int = 100,
) -> list[PersonRow]:
    """
    列出所有人员
    
    Args:
        engine: 数据库引擎
        schema: 数据库schema
        active_only: 是否只返回有效人员
        limit: 最大返回数量
        
    Returns:
        PersonRow 列表
    """
    where_clause = "WHERE is_active = true" if active_only else ""
    
    sql = text(
        f"""
        SELECT id, name, employee_id, image_base64, is_active
        FROM {schema}.reid_target
        {where_clause}
        ORDER BY name
        LIMIT :limit
        """
    )
    
    with engine.connect() as conn:
        rows = conn.execute(sql, {"limit": limit}).mappings().all()
    
    return [
        PersonRow(
            id=str(row["id"]),
            name=str(row["name"]),
            employee_id=str(row["employee_id"]) if row["employee_id"] else None,
            image_base64=str(row["image_base64"]) if row["image_base64"] else None,
            is_active=bool(row["is_active"]),
        )
        for row in rows
    ]

