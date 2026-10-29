from __future__ import annotations

import re


def guess_person_name(query: str) -> str | None:
    q = (query or "").strip()
    if q == "":
        return None

    m = re.search(r"今天\s*(上午|下午)?\s*([A-Za-z0-9_\-]{2,32})\s*", q)
    if m:
        return m.group(2)

    m = re.search(r"(上午|下午)?\s*([A-Za-z0-9_\-]{2,32})\s*(干了什么|做了什么|怎么样|情况)", q)
    if m:
        return m.group(2)

    m = re.search(r"([\u4e00-\u9fff]{2,6})\s*(干了什么|做了什么|怎么样|情况)", q)
    if m:
        return m.group(1)

    return None
