"""Runtime context: application-owned state for one agent turn.

Formalizes what used to be loose keyword arguments to
``AdvancedDoraDbAgent.chat()`` into one typed object (guide Section 10:
context should support tools and policies without manually stuffing request
internals into every call site). ``AgentState`` (``state.py``) remains the
LangGraph-native state the graph actually executes with;
``RuntimeContext.to_initial_state()`` is the one place a chat request is
turned into that initial state.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class RuntimeContext:
    session_id: str
    message: str
    history: list[dict[str, str]] = field(default_factory=list)
    persistent_context: dict[str, Any] = field(default_factory=dict)
    project_scope: dict[str, Any] = field(default_factory=dict)
    db_session: Session | None = None

    def to_initial_state(self) -> dict[str, Any]:
        return {
            "request_id": str(uuid.uuid4()),
            "session_id": self.session_id,
            "message": self.message,
            "browser_history": self.history[-12:],
            "persistent_context": self.persistent_context,
            "project_scope": self.project_scope,
            "db_session": self.db_session,
        }


__all__ = ["RuntimeContext"]
