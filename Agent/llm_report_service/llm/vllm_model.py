"""vLLM uses the same OpenAI chat protocol as the SGLang client."""

from llm_report_service.llm.sglang_model import ChatSGLang


class ChatVLLM(ChatSGLang):
    @property
    def _llm_type(self) -> str:
        return "vllm_openai"


__all__ = ["ChatVLLM"]
