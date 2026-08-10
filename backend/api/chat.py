"""The main conversational endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..config import settings
from ..conversation_context import persistent_context, recent_history, update_persistent_state
from ..conversation_repository import ConversationRepository
from ..database.db import get_db
from ..database.doradb import DoraDbConfigurationError, DoraDbQueryRejected, doradb_session
from ..doradb_agent import DoraDbAgent
from ..schemas import ChatRequest, ChatResponse
from .dependencies import development_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


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
    project_scope = {"project_key": request.project_key or settings.doradb_project_key}
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
    repository.add_message(conversation, role="user", content=request.message)
    try:
        if settings.doradb_configured:
            with doradb_session() as real_session:
                result = DoraDbAgent(real_session).chat(
                    request.message,
                    session_id=str(conversation.id),
                    history=history,
                    persistent_context=persistent_context(conversation.state or {}),
                    project_scope=project_scope,
                )
        else:
            # Safe conversation can still run through DeepSeek. Any plan that
            # requires dataset evidence is rejected before query execution.
            result = DoraDbAgent(None).chat(
                request.message,
                session_id=str(conversation.id),
                history=history,
                persistent_context=persistent_context(conversation.state or {}),
                project_scope=project_scope,
            )
        agent_persistence = result.pop("_persistence", {})
        result.setdefault("metadata", {})["conversation_id"] = str(conversation.id)
        result["metadata"]["workspace"] = request.workspace
        result["metadata"]["project_scope"] = project_scope
        repository.add_message(
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
        repository.update_state(
            conversation,
            update_persistent_state(
                conversation.state or {},
                workspace=request.workspace,
                project_scope=project_scope,
                question=request.message,
                answer=result["answer"],
                agent_persistence=agent_persistence,
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
