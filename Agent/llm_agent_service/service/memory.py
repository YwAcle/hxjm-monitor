"""按会话 ID 管理的线程安全、有上限的 LangChain 聊天历史。"""

from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import RLock
from typing import Iterator

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


@dataclass
class SessionConversation:
    history: InMemoryChatMessageHistory
    max_messages: int
    lock: RLock = field(default_factory=RLock)

    def messages(self) -> list[BaseMessage]:
        return list(self.history.messages)

    def add_exchange(self, user_text: str, assistant_text: str) -> None:
        self.history.add_messages(
            [
                HumanMessage(content=user_text),
                AIMessage(content=assistant_text),
            ]
        )
        if len(self.history.messages) > self.max_messages:
            self.history.messages = self.history.messages[-self.max_messages :]


class SessionMemoryStore:
    """为有限数量的会话保存最近的 LangChain 消息。"""

    def __init__(self, *, max_sessions: int = 1000, max_messages: int = 20) -> None:
        if max_sessions < 1:
            raise ValueError("max_sessions 至少必须为 1")
        if max_messages < 2:
            raise ValueError("max_messages 至少必须为 2")
        if max_messages % 2 != 0:
            raise ValueError("max_messages 必须是偶数")

        self.max_sessions = max_sessions
        self.max_messages = max_messages
        self._sessions: OrderedDict[str, SessionConversation] = OrderedDict()
        self._lock = RLock()

    def _get_or_create(self, session_id: str) -> SessionConversation:
        with self._lock:
            conversation = self._sessions.get(session_id)
            if conversation is None:
                conversation = SessionConversation(
                    history=InMemoryChatMessageHistory(),
                    max_messages=self.max_messages,
                )
                self._sessions[session_id] = conversation
            else:
                self._sessions.move_to_end(session_id)

            while len(self._sessions) > self.max_sessions:
                self._sessions.popitem(last=False)
            return conversation

    @contextmanager
    def conversation(self, session_id: str) -> Iterator[SessionConversation]:
        conversation = self._get_or_create(session_id)
        with conversation.lock:
            yield conversation

    def clear(self, session_id: str) -> bool:
        with self._lock:
            conversation = self._sessions.pop(session_id, None)
        if conversation is None:
            return False
        with conversation.lock:
            conversation.history.clear()
        return True


__all__ = ["SessionConversation", "SessionMemoryStore"]
