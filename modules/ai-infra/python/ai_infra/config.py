from dataclasses import dataclass

from ai_infra.settings import (
    LLM_BACKEND,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_CONNECT_TIMEOUT_S,
    LLM_ENABLE_THINKING,
    LLM_MAX_RETRIES,
    LLM_MODEL_ID,
    LLM_REQUEST_TIMEOUT_S,
)

@dataclass(frozen=True)
class ModelConfig:
    backend: str = LLM_BACKEND
    base_url: str = LLM_BASE_URL
    model_name: str = LLM_MODEL_ID
    api_key: str = LLM_API_KEY
    connect_timeout_s: float = LLM_CONNECT_TIMEOUT_S
    request_timeout_s: float = LLM_REQUEST_TIMEOUT_S
    max_retries: int = LLM_MAX_RETRIES
    enable_thinking: bool | None = LLM_ENABLE_THINKING
    max_new_tokens: int = 256
    temperature: float = 0.0
