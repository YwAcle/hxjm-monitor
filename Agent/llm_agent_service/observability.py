"""Agent 服务的轻量结构化日志。"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from llm_report_service.llm.settings import LLM_BACKEND, LLM_MODE, REPOSITORY_ROOT

LOGGER_NAME = "llm_agent_service.events"
default_write_mode = os.getenv("LOG_WRITE_MODE", "append")
jsonl_write_mode = os.getenv("AGENT_JSONL_WRITE_MODE", default_write_mode)
for name, mode in (("LOG_WRITE_MODE", default_write_mode), ("AGENT_JSONL_WRITE_MODE", jsonl_write_mode)):
    if mode not in {"append", "overwrite"}:
        raise ValueError(f"{name} must be append or overwrite, got {mode!r}")
logger = logging.getLogger(LOGGER_NAME)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    jsonl_path = Path(os.getenv(
        "AGENT_JSONL_LOG",
        str(REPOSITORY_ROOT / ".runtime-cache" / "service-stack" / ("api" if LLM_MODE == "api" else LLM_BACKEND) / "agent.jsonl"),
    )).expanduser()
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_handler = logging.FileHandler(
        jsonl_path, mode="a" if jsonl_write_mode == "append" else "w", encoding="utf-8"
    )
    jsonl_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(jsonl_handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def emit_event(event: str, **fields: Any) -> None:
    """输出单行 JSON 日志；图片数据应先通过 log_payload 处理。"""

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **{key: value for key, value in fields.items() if value is not None},
    }
    logger.info(json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str))


def log_payload(value: Any) -> Any:
    """保留完整文本及结构化数据，用长度标记替代图片二进制内容。"""

    if isinstance(value, dict):
        return {
            key: (
                f"[image data omitted: {len(item)} chars]"
                if "base64" in str(key).lower() and isinstance(item, str)
                else log_payload(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [log_payload(item) for item in value]
    if isinstance(value, str) and value.startswith("data:image/"):
        return f"[image data omitted: {len(value)} chars]"
    return value


__all__ = ["LOGGER_NAME", "emit_event", "log_payload"]
