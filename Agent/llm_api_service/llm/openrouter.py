"""
OpenRouter LLM 封装 - 兼容 LangChain
"""
from __future__ import annotations

import requests
from typing import Any, List, Optional, Mapping

try:
    # 新版 LangChain (>=0.2.0)
    from langchain_core.language_models.llms import LLM
    from langchain_core.callbacks.manager import CallbackManagerForLLMRun
except ImportError:
    # 旧版 LangChain (<0.2.0)
    from langchain.llms.base import LLM
    from langchain.callbacks.manager import CallbackManagerForLLMRun

from llm_api_service.config import OpenRouterConfig


class OpenRouterLLM(LLM):
    """
    OpenRouter API 封装，兼容 LangChain LLM 接口
    """
    
    api_key: str = ""
    model_name: str = "minimax/minimax-m2"
    base_url: str = "https://openrouter.ai/api/v1/chat/completions"
    max_tokens: int = 2048
    temperature: float = 0.1
    
    def __init__(self, config: Optional[OpenRouterConfig] = None, **kwargs):
        super().__init__(**kwargs)
        if config:
            self.api_key = config.api_key
            self.model_name = config.model
            self.base_url = config.base_url
            self.max_tokens = config.max_tokens
            self.temperature = config.temperature
    
    @property
    def _llm_type(self) -> str:
        return "openrouter"
    
    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        return {
            "model_name": self.model_name,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
    
    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs,
    ) -> str:
        """
        调用 OpenRouter API
        
        注意：prompt 应该已经包含完整的系统提示和对话历史
        """
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
        }
        
        if stop:
            payload["stop"] = stop
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/monitor-agent",
            "X-Title": "Monitor LLM Agent",
        }
        
        try:
            resp = requests.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=120,  # 增加超时时间
            )
            resp.raise_for_status()
            result = resp.json()
            return result["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"OpenRouter API 调用失败: {e}")
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"OpenRouter API 响应解析失败: {e}")


class OpenRouterChatLLM:
    """
    OpenRouter Chat API 封装（非 LangChain 版本，用于直接调用）
    """
    
    def __init__(self, config: OpenRouterConfig):
        self.api_key = config.api_key
        self.model_name = config.model
        self.base_url = config.base_url
        self.max_tokens = config.max_tokens
        self.temperature = config.temperature
    
    def chat(
        self,
        messages: List[dict],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stop: Optional[List[str]] = None,
    ) -> str:
        """
        发送聊天消息
        
        Args:
            messages: 消息列表，格式 [{"role": "user", "content": "..."}]
            max_tokens: 最大token数
            temperature: 温度参数
            stop: 停止词列表
            
        Returns:
            助手回复内容
        """
        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature or self.temperature,
        }
        
        if stop:
            payload["stop"] = stop
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        try:
            resp = requests.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            result = resp.json()
            return result["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"OpenRouter API 调用失败: {e}")
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"OpenRouter API 响应解析失败: {e}")

