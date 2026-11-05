from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def get_stranger_code(engine: Engine, schema: str, stranger_target_id: str) -> str | None:
    stranger_target_id = (stranger_target_id or "").strip()
    if stranger_target_id == "":
        return None

    sql = text(
        f"""
        select code
        from {schema}.stranger_target
        where id = :id
        limit 1
        """
    )

    with engine.connect() as conn:
        r = conn.execute(sql, {"id": stranger_target_id}).mappings().first()

    if r is None:
        return None

    v = r.get("code")
    if v is None:
        return None

    return str(v)
