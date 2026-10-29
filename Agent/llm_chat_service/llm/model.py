from __future__ import annotations

from llm_report_service.llm.sglang_model import ChatSGLang

def build_llm(cfg):
    return ChatSGLang(
        base_url=cfg.base_url,
        model_name=cfg.model_name,
        api_key=cfg.api_key,
        max_new_tokens=cfg.max_new_tokens,
        temperature=cfg.temperature,
        connect_timeout_s=cfg.connect_timeout_s,
        request_timeout_s=cfg.request_timeout_s,
        max_retries=cfg.max_retries,
        enable_thinking=cfg.enable_thinking,
    )

__all__ = ["ChatSGLang", "build_llm"]
