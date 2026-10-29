"""report服务聊天模型后端的构建。"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from llm_report_service.config import ModelConfig

def build_chat_model(cfg: ModelConfig) -> BaseChatModel:
    backend = cfg.backend.strip().lower()
    if backend not in {"sglang", "vllm"}:
        raise ValueError(f"不支持的 LLM 后端：{cfg.backend!r}；支持 'sglang'、'vllm'")

    from llm_report_service.llm.sglang_model import ChatSGLang
    from llm_report_service.llm.vllm_model import ChatVLLM

    model_class = ChatVLLM if backend == "vllm" else ChatSGLang
    return model_class(
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


__all__ = ["build_chat_model"]
