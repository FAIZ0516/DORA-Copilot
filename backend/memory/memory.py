"""Bounded, structured, process-local conversation memory."""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from threading import RLock
from typing import Any

from ..config import settings


class SessionMemoryStore:
    """LRU memory that deliberately excludes raw database result sets."""

    def __init__(self) -> None:
        self._sessions: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = RLock()

    def get(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            value = self._sessions.get(session_id)
            if value is None:
                return {"turns": [], "last_context": {}}
            self._sessions.move_to_end(session_id)
            return deepcopy(value)

    def remember(
        self,
        session_id: str,
        *,
        user_message: str,
        assistant_answer: str,
        context: dict[str, Any],
    ) -> None:
        safe_context = {
            "intent": context.get("intent"),
            "metric": context.get("metric"),
            "filters": context.get("filters", {}),
            "query_ids": context.get("query_ids", []),
            "warnings": context.get("warnings", []),
            "entities": context.get("entities", {}),
            "discovered_values": context.get("discovered_values", {}),
            "user_goal": str(context.get("user_goal", ""))[:500],
        }
        turn = {
            "user": user_message[:2000],
            "assistant": assistant_answer[:3000],
        }
        with self._lock:
            current = self._sessions.get(session_id, {"turns": [], "last_context": {}})
            current["turns"] = (current["turns"] + [turn])[-settings.agent_memory_max_turns :]
            current["last_context"] = safe_context
            self._sessions[session_id] = current
            self._sessions.move_to_end(session_id)
            while len(self._sessions) > settings.agent_memory_max_sessions:
                self._sessions.popitem(last=False)

    def reset(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"active_sessions": len(self._sessions)}


memory_store = SessionMemoryStore()
