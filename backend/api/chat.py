"""The main conversational endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..chat_service import ConversationNotFound, run_chat_turn
from ..config import settings
from ..database.db import get_db
from ..database.doradb import DoraDbConfigurationError, DoraDbQueryRejected, doradb_session
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
    """Run configured-LLM planning and real DoraDB tools when data is required.

    The turn itself lives in ``chat_service.run_chat_turn`` so the realtime
    voice session runs exactly the same governed workflow rather than a second,
    weaker copy of it. This route keeps only the HTTP concerns.
    """

    try:
        result = run_chat_turn(
            runtime_session=runtime_session,
            user_id=user_id,
            message=request.message,
            conversation_id=request.conversation_id,
            workspace=request.workspace,
            project_key=request.project_key,
            dashboard_context=(
                request.dashboard_context.model_dump(mode="json", exclude_none=True)
                if request.dashboard_context
                else {}
            ),
            history=[item.model_dump() for item in request.history],
        )
        return ChatResponse.model_validate(result)
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail="Conversation not found.") from exc
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
