"""
Conversational memory.
- In-process store always available (dev / single replica).
- When Redis is up, session snapshots are also written for multi-replica K8s.
"""
from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.models.schemas import ChatMessage


@dataclass
class SessionMemory:
    session_id: str
    user_id: str
    messages: List[ChatMessage] = field(default_factory=list)
    summary: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)

    def add_message(self, msg: ChatMessage) -> None:
        self.messages.append(msg)
        self.last_active = time.time()
        if len(self.messages) > 24:
            self.messages = self.messages[-20:]

    def get_context_window(self, max_turns: int = 6) -> List[Dict[str, str]]:
        recent = self.messages[-max_turns * 2 :]
        return [{"role": m.role, "content": m.content} for m in recent]

    def update_summary(self, new_summary: str) -> None:
        self.summary = new_summary
        self.last_active = time.time()

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "summary": self.summary,
            "metadata": self.metadata,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp.isoformat() if hasattr(m.timestamp, "isoformat") else str(m.timestamp),
                }
                for m in self.messages
            ],
        }


class MemoryStore:
    def __init__(self):
        self._sessions: Dict[str, SessionMemory] = {}
        self._user_sessions: Dict[str, List[str]] = defaultdict(list)

    def get_or_create(self, session_id: Optional[str], user_id: str) -> SessionMemory:
        if session_id and session_id in self._sessions:
            mem = self._sessions[session_id]
            mem.last_active = time.time()
            return mem
        new_id = session_id or str(uuid.uuid4())
        mem = SessionMemory(session_id=new_id, user_id=user_id)
        self._sessions[new_id] = mem
        self._user_sessions[user_id].append(new_id)
        return mem

    def get(self, session_id: str) -> Optional[SessionMemory]:
        return self._sessions.get(session_id)


_memory_store: Optional[MemoryStore] = None


def get_memory_store() -> MemoryStore:
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store
