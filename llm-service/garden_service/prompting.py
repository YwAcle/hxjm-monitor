#!/usr/bin/env python3
"""Prompt and response parsing helpers for Garden.

This module defines the prompt-template boundary: loading template files,
rendering placeholders, and extracting structured JSON from model output. It is
kept free of model-loading and transport concerns on purpose.
"""

import json
import re
from typing import Any, Dict, List, Optional


def read_json(path: str) -> Dict[str, Any]:
    """Read a UTF-8 JSON file into a dictionary."""
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def strip_code_fence(text: str) -> str:
    """Remove optional markdown code fences before JSON extraction."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def extract_json_candidate(text: str) -> str:
    """Extract the outermost JSON object candidate from model output text."""
    cleaned = strip_code_fence(text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return cleaned[start:end + 1]
    return cleaned


def parse_model_json(text: str) -> Optional[Dict[str, Any]]:
    """Best-effort parse for model output that should contain one JSON object."""
    candidate = extract_json_candidate(text)
    try:
        return json.loads(candidate)
    except Exception:
        return None


def should_alert_from_text(text: str, predicates: List[str]) -> bool:
    """Check whether raw text already contains any configured alert markers."""
    return any(token in text for token in predicates)


def normalize_stream_name(meta: Dict[str, Any]) -> str:
    """Normalize upstream frame metadata to a stable stream identifier."""
    return meta.get("streamName") or meta.get("stream_name") or "unknown_stream"


def normalize_camera_id(payload: Dict[str, Any]) -> str:
    """Normalize downstream payloads to the camera identifier field."""
    return payload.get("camera_id") or payload.get("stream_name") or "unknown_stream"


# Only simple placeholders are substituted so JSON examples embedded in prompt
# text remain untouched.
PLACEHOLDER_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def render_prompt_template(template: str, context: Dict[str, str]) -> str:
    """
    Only replace simple placeholders like {stream_name}.
    Leave all other braces untouched so embedded JSON examples remain valid.
    """

    def replace(match: re.Match) -> str:
        key = match.group(1)
        return str(context.get(key, match.group(0)))

    return PLACEHOLDER_PATTERN.sub(replace, template)


class GardenPromptTemplate:
    """Load one prompt template file and build chat-format model messages."""

    def __init__(self, path: str):
        self.path = path
        self.reload()

    def reload(self) -> None:
        """Reload the prompt file so manual edits take effect without restart."""
        self.payload = read_json(self.path)

    @property
    def alert_predicates(self) -> List[str]:
        return list(self.payload.get("alert_predicates", []))

    @property
    def generation(self) -> Dict[str, Any]:
        generation = dict(self.payload.get("generation", {}))
        generation.setdefault("max_new_tokens", 192)
        generation.setdefault("do_sample", False)
        if generation.get("do_sample"):
            generation.setdefault("temperature", 0.2)
        else:
            generation.pop("temperature", None)
        return generation

    def build_messages(self, meta: Dict[str, Any], image) -> List[Dict[str, Any]]:
        """Render one multimodal request from frame metadata and image."""
        stream_name = normalize_stream_name(meta)
        context = {
            "stream_name": stream_name,
            "timestamp_ms": str(meta.get("timestamp", "")),
            "path": meta.get("path", ""),
            "task": meta.get("task", "garden"),
        }
        system_prompt = render_prompt_template(
            self.payload.get("system_prompt", ""), context
        )
        user_prompt = render_prompt_template(
            self.payload.get("user_prompt_template", ""), context
        )
        return [
            {
                "role": "system",
                "content": [{"type": "text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": user_prompt},
                ],
            },
        ]
