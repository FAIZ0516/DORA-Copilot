"""User-scoped persistence for conversations and messages."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .db import Conversation, ConversationMessage


WORKSPACES = {"business", "technical"}
SAFE_STRUCTURED_KEYS = {
    "chart",
    "table",
    "warnings",
    "validation",
    "metadata",
    "detected_intent",
    "source_type",
    "query_identifiers",
    "query_parameters",
    "row_counts",
    "knowledge_sections",
    "error_state",
}


def generate_title(question: str) -> str:
    """Create a stable short title without an additional model request."""

    compact = re.sub(r"\s+", " ", question).strip()
    words = compact.split()
    title = " ".join(words[:9])
    if len(words) > 9:
        title += "..."
    return title[:157] or "New conversation"


def _safe_structured_content(value: dict[str, Any] | None) -> dict[str, Any]:
    if not value:
        return {}
    return {key: value[key] for key in SAFE_STRUCTURED_KEYS if key in value}


class ConversationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        user_id: str,
        workspace: str,
        project_scope: dict[str, Any],
        first_question: str = "",
        title: str | None = None,
    ) -> Conversation:
        if workspace not in WORKSPACES:
            raise ValueError("Unsupported workspace")
        conversation = Conversation(
            title=(title or generate_title(first_question))[:160],
            user_id=user_id,
            state={
                "workspace": workspace,
                "project_scope": project_scope,
                "summary": "",
                "turn_count": 0,
                "last_context": {},
                "query_cache": [],
            },
        )
        self.session.add(conversation)
        self.session.commit()
        self.session.refresh(conversation)
        return conversation

    def list_recent(self, *, user_id: str, limit: int = 30) -> list[Conversation]:
        return list(
            self.session.scalars(
                select(Conversation)
                .where(
                    Conversation.user_id == user_id,
                    Conversation.archived_at.is_(None),
                )
                .order_by(Conversation.updated_at.desc())
                .limit(max(1, min(limit, 100)))
            )
        )

    def get(
        self,
        conversation_id: UUID,
        *,
        user_id: str,
        include_messages: bool = False,
    ) -> Conversation | None:
        statement = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
            Conversation.archived_at.is_(None),
        )
        if include_messages:
            statement = statement.options(selectinload(Conversation.messages))
        return self.session.scalar(statement)

    def add_message(
        self,
        conversation: Conversation,
        *,
        role: str,
        content: str,
        structured_content: dict[str, Any] | None = None,
    ) -> ConversationMessage:
        if role not in {"user", "assistant", "system"}:
            raise ValueError("Unsupported message role")
        message = ConversationMessage(
            conversation_id=conversation.id,
            role=role,
            content=content,
            structured_content=_safe_structured_content(structured_content),
        )
        conversation.updated_at = datetime.now(timezone.utc)
        self.session.add_all([conversation, message])
        self.session.commit()
        self.session.refresh(message)
        return message

    def update_state(
        self,
        conversation: Conversation,
        state: dict[str, Any],
    ) -> None:
        conversation.state = state
        conversation.updated_at = datetime.now(timezone.utc)
        self.session.add(conversation)
        self.session.commit()

    def archive(self, conversation: Conversation) -> None:
        now = datetime.now(timezone.utc)
        conversation.archived_at = now
        conversation.updated_at = now
        self.session.add(conversation)
        self.session.commit()


def serialize_message(message: ConversationMessage) -> dict[str, Any]:
    return {
        "id": str(message.id),
        "role": message.role,
        "content": message.content,
        "structured_content": message.structured_content or {},
        "created_at": message.created_at,
    }


def serialize_conversation(
    conversation: Conversation,
    *,
    include_messages: bool = False,
) -> dict[str, Any]:
    state = conversation.state or {}
    payload: dict[str, Any] = {
        "id": str(conversation.id),
        "title": conversation.title,
        "workspace": state.get("workspace", "technical"),
        "project_scope": state.get("project_scope", {}),
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }
    if include_messages:
        payload["messages"] = [serialize_message(item) for item in conversation.messages]
    return payload


__all__ = [
    "ConversationRepository",
    "generate_title",
    "serialize_conversation",
    "serialize_message",
]
