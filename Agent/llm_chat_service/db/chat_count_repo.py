from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def inc_chat_count(engine: Engine, schema: str) -> None:
    sql_update = text(
        f"""
        update {schema}.chat_count
        set chatcount = coalesce(chatcount, 0) + 1
        """
    )

    sql_insert = text(
        f"""
        insert into {schema}.chat_count (chatcount)
        values (1)
        """
    )

    with engine.begin() as conn:
        res = conn.execute(sql_update)
        if getattr(res, "rowcount", 0) == 0:
            conn.execute(sql_insert)
