"""通过 SGLang OpenAI 兼容接口调用模型的 LangChain 聊天模型。"""

from __future__ import annotations

import json
import time
from threading import RLock
from typing import Any, Iterator, Literal, Sequence

import httpx
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field, PrivateAttr

from llm_report_service.llm.settings import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_CONNECT_TIMEOUT_S,
    LLM_HEALTHCHECK,
    LLM_MODE,
    LLM_MAX_RETRIES,
    LLM_MODEL_ID,
    LLM_REQUEST_TIMEOUT_S,
    LLM_RESPONSE_FORMAT,
)


class SGLangRequestError(RuntimeError):
    """SGLang 接口拒绝请求或无法完成请求时抛出的异常。"""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

    @property
    def is_out_of_memory(self) -> bool:
        text = str(self).lower()
        return "out of memory" in text or "cuda oom" in text


class ChatSGLang(BaseChatModel):
    """通过 OpenAI 兼容的聊天补全接口调用 SGLang。"""

    base_url: str = LLM_BASE_URL
    model_name: str = LLM_MODEL_ID
    api_key: str = LLM_API_KEY
    max_new_tokens: int = Field(default=512, gt=0)
    temperature: float = Field(default=0.0, ge=0.0)
    connect_timeout_s: float = Field(default=LLM_CONNECT_TIMEOUT_S, gt=0.0)
    request_timeout_s: float = Field(default=LLM_REQUEST_TIMEOUT_S, gt=0.0)
    max_retries: int = Field(default=LLM_MAX_RETRIES, ge=0)
    enable_thinking: bool | None = None
    response_format_mode: Literal["json_schema", "json_object", "none"] = LLM_RESPONSE_FORMAT
    check_models: bool = (
        LLM_HEALTHCHECK == "models" or (LLM_HEALTHCHECK == "auto" and LLM_MODE == "local")
    )

    _client: httpx.Client | None = PrivateAttr(default=None)
    _client_lock: RLock = PrivateAttr(default_factory=RLock)

    @property
    def _llm_type(self) -> str:
        return "sglang_openai"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "model_name": self.model_name,
            "max_new_tokens": self.max_new_tokens,
            "temperature": self.temperature,
            "response_format_mode": self.response_format_mode,
        }

    @property
    def endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    @property
    def models_endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/models"

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    timeout = httpx.Timeout(
                        self.request_timeout_s,
                        connect=self.connect_timeout_s,
                    )
                    self._client = httpx.Client(
                        timeout=timeout,
                        headers={"Authorization": f"Bearer {self.api_key}"},
                    )
        return self._client

    def check_health(self) -> dict[str, Any]:
        """按配置检查模型列表；跳过时明确标记，不发起付费聊天请求。"""
        if not self.check_models:
            return {"model": self.model_name, "healthcheck": "skipped"}

        try:
            timeout = httpx.Timeout(10.0, connect=self.connect_timeout_s)
            response = self._get_client().get(
                self.models_endpoint,
                timeout=timeout,
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise SGLangRequestError(
                f"模型接口 健康检查失败：{exc}"
            ) from exc
        if response.status_code >= 400:
            raise SGLangRequestError(
                f"模型接口 健康检查返回 HTTP {response.status_code}："
                f"{response.text}",
                status_code=response.status_code,
            )
        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise SGLangRequestError(
                f"模型接口 健康检查返回了无效 JSON：{response.text}",
                status_code=response.status_code,
            ) from exc
        if not isinstance(data, dict):
            raise SGLangRequestError(
                f"模型接口 健康检查返回了无效数据：{data!r}",
                status_code=response.status_code,
            )

        items = data.get("data")
        if not isinstance(items, list):
            raise SGLangRequestError(
                f"模型接口 健康检查返回了无效的模型列表：{data!r}",
                status_code=response.status_code,
            )
        model_ids = [
            str(item.get("id"))
            for item in items
            if isinstance(item, dict) and item.get("id") is not None
        ]
        if self.model_name not in model_ids:
            raise SGLangRequestError(
                f"模型接口 未提供模型 {self.model_name!r}；"
                f"当前可用模型：{model_ids}"
            )
        return {"model": self.model_name, "available_models": model_ids}

    @staticmethod
    def _message_role(message: BaseMessage) -> str:
        if isinstance(message, SystemMessage):
            return "system"
        if isinstance(message, HumanMessage):
            return "user"
        if isinstance(message, AIMessage):
            return "assistant"
        raise TypeError(f"不支持的消息类型：{type(message).__name__}")

    @classmethod
    def _messages_to_openai(
        cls,
        messages: Sequence[BaseMessage],
    ) -> list[dict[str, Any]]:
        if not messages:
            raise ValueError("至少需要一条聊天消息")
        return [
            {"role": cls._message_role(message), "content": message.content}
            for message in messages
        ]

    def _payload(
        self,
        messages: Sequence[BaseMessage],
        stop: Sequence[str] | None,
        kwargs: dict[str, Any],
        *,
        stream: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": self._messages_to_openai(messages),
            "max_tokens": int(
                kwargs.get("max_tokens", kwargs.get("max_new_tokens", self.max_new_tokens))
            ),
            "temperature": float(kwargs.get("temperature", self.temperature)),
            "stream": stream,
        }
        if stop:
            payload["stop"] = list(stop)
        if self.enable_thinking is not None:
            payload["chat_template_kwargs"] = {
                "enable_thinking": self.enable_thinking,
            }

        for key in (
            "top_p",
            "seed",
            "frequency_penalty",
            "presence_penalty",
            "response_format",
        ):
            if key in kwargs and kwargs[key] is not None:
                payload[key] = kwargs[key]

        extra_body = kwargs.get("extra_body")
        if extra_body:
            payload.update(dict(extra_body))
        if "response_format" in payload:
            if self.response_format_mode == "json_object":
                payload["response_format"] = {"type": "json_object"}
            elif self.response_format_mode == "none":
                payload.pop("response_format")
        return payload

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        retryable_statuses = {429, 502, 503, 504}
        last_error: BaseException | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self._get_client().post(self.endpoint, json=payload)
                if response.status_code < 400:
                    return response
                if response.status_code not in retryable_statuses:
                    raise SGLangRequestError(
                        f"模型接口 返回 HTTP {response.status_code}：{response.text}",
                        status_code=response.status_code,
                    )
                last_error = SGLangRequestError(
                    f"模型接口 返回 HTTP {response.status_code}：{response.text}",
                    status_code=response.status_code,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc

            if attempt < self.max_retries:
                time.sleep(min(0.5 * (2**attempt), 2.0))

        raise SGLangRequestError(f"模型接口 请求失败：{last_error}") from last_error

    @staticmethod
    def _response_text(data: dict[str, Any]) -> str:
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise SGLangRequestError(
                f"模型接口 返回了无效响应：{json.dumps(data, ensure_ascii=False)}"
            ) from exc
        if content is None:
            return ""
        if not isinstance(content, str):
            raise SGLangRequestError(f"不支持的响应内容：{content!r}")
        return content

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        payload = self._payload(messages, stop, kwargs, stream=False)
        response = self._post(payload)
        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise SGLangRequestError(
                f"模型接口 返回了无效 JSON：{response.text}",
                status_code=response.status_code,
            ) from exc
        message = AIMessage(
            content=self._response_text(data),
            response_metadata={
                "model": data.get("model", self.model_name),
                "usage": data.get("usage", {}),
                "finish_reason": (data.get("choices") or [{}])[0].get(
                    "finish_reason"
                ),
            },
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        payload = self._payload(messages, stop, kwargs, stream=True)
        client = self._get_client()

        with client.stream("POST", self.endpoint, json=payload) as response:
            if response.status_code >= 400:
                body = response.read().decode("utf-8", errors="replace")
                raise SGLangRequestError(
                    f"模型接口 返回 HTTP {response.status_code}：{body}",
                    status_code=response.status_code,
                )
            completed = False
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                event = line[5:].strip()
                if event == "[DONE]":
                    completed = True
                    break
                if not event:
                    continue
                try:
                    data = json.loads(event)
                except json.JSONDecodeError as exc:
                    raise SGLangRequestError(
                        f"模型接口 返回了无效的 SSE 事件：{event}"
                    ) from exc
                if data.get("error"):
                    raise SGLangRequestError("模型接口 返回了流式错误")
                choices = data.get("choices") or []
                if not choices:
                    continue
                token = choices[0].get("delta", {}).get("content") or ""
                finish_reason = choices[0].get("finish_reason")
                if not token and finish_reason is None:
                    continue
                chunk = ChatGenerationChunk(message=AIMessageChunk(
                    content=token,
                    response_metadata={"finish_reason": finish_reason} if finish_reason is not None else {},
                ))
                if run_manager is not None and token:
                    run_manager.on_llm_new_token(token, chunk=chunk)
                yield chunk
            if not completed:
                raise SGLangRequestError("模型接口 流式连接在结束标记前中断")

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


__all__ = ["ChatSGLang", "SGLangRequestError"]
