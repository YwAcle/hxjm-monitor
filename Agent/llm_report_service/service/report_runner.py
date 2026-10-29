from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from llm_report_service.config import ServiceConfig
from llm_report_service.db.media_repo import MediaAssetRow
from llm_report_service.llm.parser import ReportOutput, normalize_report
from llm_report_service.llm.prompt import REPORT_SYSTEM, REPORT_USER_TEMPLATE
from llm_report_service.llm.sglang_model import SGLangRequestError
from llm_report_service.llm.vision import (
    decode_base64_image,
    image_to_data_url,
    load_video_frame_images,
)
from llm_report_service.service.episode_builder import (
    EpisodeSemanticInput,
    semantic_input_to_json_str,
)

# 约定大模型响应格式
def _format_instructions() -> str:
    return (
        '{"event_type": "...", "summary": "...", '
        '"risk_level": "low|medium|high", '
        '"key_observations": ["..."], "confidence": 0.0}'
    )


def _build_user_prompt(episode_json: str) -> str:
    return REPORT_USER_TEMPLATE.format(
        episode_json=episode_json,
        format_instructions=_format_instructions(),
    )


def _extract_json(text: str) -> dict[str, Any]:
    value = text.strip()
    if "```" in value:
        import re

        match = re.search(r"```(?:json)?(.*?)```", value, re.DOTALL)
        if match:
            value = match.group(1).strip()

    start = value.find("{")
    end = value.rfind("}")
    if start != -1 and end > start:
        value = value[start : end + 1]

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        import ast

        fallback = ast.literal_eval(value)
        if not isinstance(fallback, dict):
            raise TypeError("模型响应不是 JSON 对象")
        return fallback


def _resolve_media_path(path: str | None, media_base_dir: str) -> str:
    if not path:
        return ""
    parsed = urlparse(path)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return path
    return str((Path(media_base_dir) / path).resolve())

# 为 SGLang 远程后端构造 OpenAI 兼容的多模态消息内容
def build_remote_multimodal_content(
    semantic: EpisodeSemanticInput,
    media_assets: list[MediaAssetRow],
    max_video_frames: int,
    media_base_dir: str,
) -> list[dict[str, Any]]:
    """构造 OpenAI 兼容的交错文本和图片内容块。"""

    content: list[dict[str, Any]] = []
    person_image = (
        decode_base64_image(semantic.person.get("image_base64"))
        if semantic.person
        else None
    )
    if person_image is not None:
        content.extend(
            [
                {"type": "text", "text": "PersonSnapshot:"},
                {
                    "type": "image_url",
                    "image_url": {"url": image_to_data_url(person_image)},
                },
            ]
        )

    for video_index, media in enumerate(media_assets, start=1):
        video_path = _resolve_media_path(media.path, media_base_dir)
        try:
            frames = load_video_frame_images(
                video_path,
                num_segments=int(max_video_frames),
            )
        except Exception as exc:
            print(f"读取视频帧失败，路径={video_path!r}，错误={exc}")
            frames = []

        if not frames:
            content.append(
                {"type": "text", "text": f"Video{video_index}-PATH: {media.path}"}
            )
            continue

        for frame_index, frame in enumerate(frames, start=1):
            content.extend(
                [
                    {
                        "type": "text",
                        "text": f"Video{video_index}-Frame{frame_index}:",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": image_to_data_url(frame)},
                    },
                ]
            )

    episode_json = semantic_input_to_json_str(semantic)
    content.append({"type": "text", "text": _build_user_prompt(episode_json)})
    return content


def _response_text(message: BaseMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    if isinstance(message.content, list):
        parts = []
        for block in message.content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("text") is not None:
                parts.append(str(block["text"]))
        return "".join(parts)
    return str(message.content)


def _report_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "monitoring_report",
            "strict": True,
            "schema": ReportOutput.model_json_schema(),
        },
    }


def _invoke_remote(
    llm: BaseChatModel,
    content: str | list[dict[str, Any]],
    *,
    max_new_tokens: int | None = None,
) -> str:
    kwargs: dict[str, Any] = {"response_format": _report_response_format()}
    if max_new_tokens is not None:
        kwargs["max_new_tokens"] = max_new_tokens
    response = llm.invoke(
        [SystemMessage(content=REPORT_SYSTEM), HumanMessage(content=content)],
        **kwargs,
    )
    return _response_text(response)


def run_llm_report(
    llm: BaseChatModel,
    semantic: EpisodeSemanticInput,
    media_assets: list[MediaAssetRow],
    svc_cfg: ServiceConfig,
) -> tuple[dict[str, Any], str | None]:
    if getattr(llm, "_llm_type", "") not in {"sglang_openai", "vllm_openai"}:
        raise RuntimeError("报告服务当前仅支持 SGLang 或 vLLM 后端")

    content = build_remote_multimodal_content(
        semantic,
        media_assets,
        svc_cfg.max_video_frames,
        svc_cfg.media_base_dir,
    )
    try:
        raw = _invoke_remote(llm, content)
    except SGLangRequestError as exc:
        if not exc.is_out_of_memory or not svc_cfg.oom_fallback_text_only:
            raise
        fallback = _build_user_prompt(
            "[multimodal omitted due to remote OOM]\n"
            + semantic_input_to_json_str(semantic)
        )
        raw = _invoke_remote(
            llm,
            fallback,
            max_new_tokens=int(svc_cfg.oom_retry_max_new_tokens),
        )

    report_json = normalize_report(_extract_json(raw))
    report_text = report_json.get("summary")
    return report_json, report_text
