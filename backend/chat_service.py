"""One governed chat turn, independent of how it arrived.

Extracted from ``api/chat.py`` so the realtime voice session can run exactly
the same turn without an internal HTTP call back into the app. Both callers
share this function, so there is one place where a turn is planned, executed,
validated and persisted -- a voice question is not a second, weaker path.

Everything the HTTP route did still happens here: conversation resolution and
creation, dashboard scope seeding, the governed ``DoraDbAgent`` (approved
queries, guardrails, evidence validation), message persistence and state
update. The route keeps the HTTP concerns -- status codes and dependencies.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from .config import settings
from .conversation_context import persistent_context, recent_history, update_persistent_state
from .conversation_repository import ConversationRepository
from .database.db import Conversation
from .database.doradb import doradb_session
from .demo_answer import demo_answer_for, demo_result
from .doradb_agent import DoraDbAgent

logger = logging.getLogger(__name__)


class ConversationNotFound(LookupError):
    """The conversation does not exist, or belongs to another user."""


def resolve_conversation(
    repository: ConversationRepository,
    conversation_id: UUID | None,
    *,
    user_id: str,
) -> Conversation | None:
    """Fetch a conversation the caller owns, or raise if it is not theirs."""

    if conversation_id is None:
        return None
    conversation = repository.get(conversation_id, user_id=user_id, include_messages=True)
    if conversation is None:
        raise ConversationNotFound(str(conversation_id))
    return conversation


def build_project_scope(
    dashboard_context: dict[str, Any], project_key: str | None
) -> dict[str, Any]:
    active = dashboard_context.get("project") or project_key or settings.doradb_project_key
    scope: dict[str, Any] = {"project_key": str(active).strip().upper()}
    if dashboard_context:
        scope["dashboard_context"] = dashboard_context
    return scope


def seed_agent_context(
    conversation: Conversation, dashboard_context: dict[str, Any], project_scope: dict[str, Any]
) -> dict[str, Any]:
    """Carry the dashboard the user is looking at into the agent's context.

    Scope arrives as structured context and is never smuggled into the user's
    question as hidden text, so a question asked from a squad view is scoped to
    that squad without the user restating it.
    """

    agent_context = persistent_context(conversation.state or {})
    agent_context["dashboard_context"] = dashboard_context
    if not dashboard_context:
        return agent_context

    last_context = dict(agent_context.get("last_context", {}))
    filters = dict(last_context.get("filters", {}))
    if dashboard_context.get("squad"):
        filters["dcpsquad"] = dashboard_context["squad"]
    if dashboard_context.get("release"):
        filters["fixversion"] = dashboard_context["release"]
    filters["project_key"] = project_scope["project_key"]
    last_context["filters"] = filters
    if dashboard_context.get("selected_metric"):
        last_context["metric"] = dashboard_context["selected_metric"]
    last_context["dashboard_context"] = dashboard_context
    agent_context["last_context"] = last_context
    return agent_context


def run_chat_turn(
    *,
    runtime_session: Session,
    user_id: str,
    message: str,
    conversation_id: UUID | None = None,
    workspace: str = "technical",
    project_key: str | None = None,
    dashboard_context: dict[str, Any] | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Run one governed turn and persist it. Returns the agent result.

    Raises ``ConversationNotFound`` for an unknown or unowned conversation.
    Database and provider failures propagate unchanged so each caller can map
    them onto its own transport.
    """

    repository = ConversationRepository(runtime_session)
    conversation = resolve_conversation(repository, conversation_id, user_id=user_id)
    dashboard_context = dashboard_context or {}
    project_scope = build_project_scope(dashboard_context, project_key)

    if conversation is None:
        conversation = repository.create(
            user_id=user_id,
            workspace=workspace,
            project_scope=project_scope,
            first_question=message,
        )
        persisted_history: list[dict[str, str]] = []
    else:
        persisted_history = recent_history(conversation.messages)
    turn_history = persisted_history or list(history or [])

    repository.add_message(
        conversation,
        role="user",
        content=message,
        structured_content={"metadata": {"dashboard_context": dashboard_context}},
    )
    agent_context = seed_agent_context(conversation, dashboard_context, project_scope)

    # One pinned question, for recording a demonstration. Checked before any
    # planning so nothing else in the turn is touched, and disabled unless the
    # flag is set -- see demo_answer.py for why it is fenced this tightly.
    if demo_answer_for(message) is not None:
        time.sleep(settings.demo_answer_delay_seconds)
        result = demo_result(message)
    elif settings.doradb_configured:
        with doradb_session() as real_session:
            result = DoraDbAgent(real_session).chat(
                message,
                session_id=str(conversation.id),
                history=turn_history,
                persistent_context=agent_context,
                project_scope=project_scope,
            )
    else:
        # Safe conversation can still run through the configured LLM. Any plan
        # that requires dataset evidence is rejected before execution.
        result = DoraDbAgent(None).chat(
            message,
            session_id=str(conversation.id),
            history=turn_history,
            persistent_context=agent_context,
            project_scope=project_scope,
        )

    agent_persistence = result.pop("_persistence", {})
    result.setdefault("metadata", {})["conversation_id"] = str(conversation.id)
    result["metadata"]["workspace"] = workspace
    result["metadata"]["project_scope"] = project_scope
    result["metadata"]["dashboard_context"] = dashboard_context

    assistant_message = repository.add_message(
        conversation,
        role="assistant",
        content=result["answer"],
        structured_content={
            "chart": result.get("chart"),
            "table": result.get("table"),
            "warnings": result.get("warnings", []),
            "validation": result.get("validation", {}),
            "metadata": result.get("metadata", {}),
            "detected_intent": result.get("intent"),
            "source_type": result.get("metadata", {}).get("answer_source"),
            "query_identifiers": result.get("metadata", {}).get("query_ids", []),
            "row_counts": result.get("metadata", {}).get("row_counts", []),
            "knowledge_sections": result.get("metadata", {}).get("knowledge_sections", []),
        },
    )
    # The id only exists after the insert, so write it into both the response
    # and the stored copy -- otherwise a reloaded conversation has no id and
    # "Add to report" cannot reference the answer.
    result["metadata"]["message_id"] = str(assistant_message.id)
    stored = dict(assistant_message.structured_content or {})
    stored_metadata = dict(stored.get("metadata") or {})
    stored_metadata["message_id"] = str(assistant_message.id)
    stored["metadata"] = stored_metadata
    assistant_message.structured_content = stored
    runtime_session.commit()

    repository.update_state(
        conversation,
        update_persistent_state(
            conversation.state or {},
            workspace=workspace,
            project_scope=project_scope,
            question=message,
            answer=result["answer"],
            agent_persistence=agent_persistence,
            dashboard_context=dashboard_context,
        ),
    )
    return result


__all__ = [
    "ConversationNotFound",
    "build_project_scope",
    "resolve_conversation",
    "run_chat_turn",
    "seed_agent_context",
]
