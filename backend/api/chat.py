"""The main conversational endpoint."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..config import settings
from ..conversation_context import persistent_context, recent_history, update_persistent_state
from ..conversation_repository import ConversationRepository
from ..database.db import get_db
from ..database.doradb import DoraDbConfigurationError, DoraDbQueryRejected, doradb_session
from ..doradb_agent import DoraDbAgent
from ..llm import GenerativeAIClient
from ..services.entity_grounding import load_entity_catalogue
from ..agent.response.responder import generate_follow_up_questions
from ..schemas import (
    ChatRequest,
    ChatResponse,
    FollowUpQuestionRequest,
    FollowUpQuestionResponse,
)
from .dependencies import development_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat/follow-ups", response_model=FollowUpQuestionResponse)
def chat_follow_ups(
    request: FollowUpQuestionRequest,
    _user_id: str = Depends(development_session),
) -> FollowUpQuestionResponse:
    """Generate optional next questions after the main answer has returned."""

    dashboard_context = (
        request.dashboard_context.model_dump(mode="json", exclude_none=True)
        if request.dashboard_context
        else {}
    )
    squads: list[str] = []
    if settings.doradb_configured:
        try:
            with doradb_session() as real_session:
                squads = load_entity_catalogue(
                    real_session,
                    project_key=dashboard_context.get("project"),
                ).get("squad", [])
        except (DoraDbConfigurationError, DoraDbQueryRejected, SQLAlchemyError) as exc:
            logger.warning("Follow-up scope catalogue unavailable: %s", type(exc).__name__)
    if dashboard_context.get("squad") and not squads:
        return FollowUpQuestionResponse(suggestions=[])
    llm = GenerativeAIClient(settings)
    try:
        suggestions = generate_follow_up_questions(
            llm,
            question=request.question,
            answer=request.answer,
            dashboard_context=dashboard_context,
            squads=squads,
        )
    finally:
        llm.close()
    return FollowUpQuestionResponse(suggestions=suggestions)


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    user_id: str = Depends(development_session),
    runtime_session: Session = Depends(get_db),
) -> ChatResponse:
    """Run configured-LLM planning and real DoraDB tools when data is required."""

    repository = ConversationRepository(runtime_session)
    conversation = (
        repository.get(request.conversation_id, user_id=user_id, include_messages=True)
        if request.conversation_id
        else None
    )
    if request.conversation_id and conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    # Dashboard scope arrives as structured context, never by rewriting the
    # user's question to smuggle hidden scope text into it.
    dashboard_context = (
        request.dashboard_context.model_dump(mode="json", exclude_none=True)
        if request.dashboard_context
        else {}
    )
    active_project = (
        dashboard_context.get("project")
        or request.project_key
        or settings.doradb_project_key
    )
    project_scope: dict[str, Any] = {"project_key": str(active_project).strip().upper()}
    if dashboard_context:
        project_scope["dashboard_context"] = dashboard_context
    if conversation is None:
        conversation = repository.create(
            user_id=user_id,
            workspace=request.workspace,
            project_scope=project_scope,
            first_question=request.message,
        )
        persisted_history: list[dict[str, str]] = []
    else:
        persisted_history = recent_history(conversation.messages)
    history = persisted_history or [item.model_dump() for item in request.history]
    repository.add_message(
        conversation,
        role="user",
        content=request.message,
        structured_content={"metadata": {"dashboard_context": dashboard_context}},
    )
    agent_context = persistent_context(conversation.state or {})
    agent_context["dashboard_context"] = dashboard_context
    if dashboard_context:
        # Seed the agent's active filters from the dashboard the user is
        # looking at, so a question asked from a squad view is scoped to that
        # squad without the user restating it.
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
    try:
        if settings.doradb_configured:
            with doradb_session() as real_session:
                result = DoraDbAgent(real_session).chat(
                    request.message,
                    session_id=str(conversation.id),
                    history=history,
                    persistent_context=agent_context,
                    project_scope=project_scope,
                )
        else:
            # Safe conversation can still run through the configured LLM. Any
            # plan that requires dataset evidence is rejected before execution.
            result = DoraDbAgent(None).chat(
                request.message,
                session_id=str(conversation.id),
                history=history,
                persistent_context=agent_context,
                project_scope=project_scope,
            )
        agent_persistence = result.pop("_persistence", {})
        result.setdefault("metadata", {})["conversation_id"] = str(conversation.id)
        result["metadata"]["workspace"] = request.workspace
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
        # The id only exists after the insert, so write it into both the
        # response and the stored copy -- otherwise a reloaded conversation has
        # no id and "Add to report" cannot reference the answer.
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
                workspace=request.workspace,
                project_scope=project_scope,
                question=request.message,
                answer=result["answer"],
                agent_persistence=agent_persistence,
                dashboard_context=dashboard_context,
            ),
        )
        return ChatResponse.model_validate(result)
    except DoraDbConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DoraDbQueryRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception("DoraDB query failed")
        raise HTTPException(
            status_code=503,
            detail="The DoraDB database is temporarily unavailable.",
        ) from exc
    except Exception as exc:
        logger.exception("Agent workflow failed")
        raise HTTPException(
            status_code=500,
            detail="The AI assistant could not process that request.",
        ) from exc


__all__ = ["router"]
