from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from llm_agent_service.config import ModelConfig
from llm_report_service.llm.factory import build_chat_model


def build_llm(cfg: ModelConfig) -> BaseChatModel:
    """共享聊天模型工厂的兼容性封装。"""

    return build_chat_model(cfg)


__all__ = ["build_chat_model", "build_llm"]
