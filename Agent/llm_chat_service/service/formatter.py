from __future__ import annotations

from llm_chat_service.llm.json_utils import dumps


def format_with_json_block(text: str, data: dict) -> str:
    return (text or "").rstrip() + "\n\n#### " + dumps(data) + " ####"
