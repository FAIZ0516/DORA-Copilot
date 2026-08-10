"""Conversation CRUD endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..conversation_repository import ConversationRepository, serialize_conversation, serialize_message
from ..database.db import get_db
from ..memory.memory import memory_store
from ..schemas import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationMessageCreate,
    ConversationMessageResponse,
    ConversationSummaryResponse,
)
from .dependencies import development_session

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.post("", response_model=ConversationSummaryResponse)
def create_conversation(
    request: ConversationCreate,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> ConversationSummaryResponse:
    conversation = ConversationRepository(session).create(
        user_id=user_id,
        workspace=request.workspace,
        project_scope=request.project_scope,
        first_question=request.first_question,
        title=request.title,
    )
    return ConversationSummaryResponse.model_validate(serialize_conversation(conversation))


@router.get("", response_model=ConversationListResponse)
def list_conversations(
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> ConversationListResponse:
    conversations = ConversationRepository(session).list_recent(user_id=user_id)
    return ConversationListResponse.model_validate(
        {"conversations": [serialize_conversation(item) for item in conversations]}
    )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation(
    conversation_id: UUID,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> ConversationDetailResponse:
    conversation = ConversationRepository(session).get(
        conversation_id, user_id=user_id, include_messages=True
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return ConversationDetailResponse.model_validate(
        serialize_conversation(conversation, include_messages=True)
    )


@router.post("/{conversation_id}/messages", response_model=ConversationMessageResponse)
def add_conversation_message(
    conversation_id: UUID,
    request: ConversationMessageCreate,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> ConversationMessageResponse:
    repository = ConversationRepository(session)
    conversation = repository.get(conversation_id, user_id=user_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    message = repository.add_message(
        conversation,
        role=request.role,
        content=request.content,
        structured_content=request.structured_content,
    )
    return ConversationMessageResponse.model_validate(serialize_message(message))


@router.delete("/{conversation_id}")
def archive_conversation(
    conversation_id: UUID,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> dict[str, str]:
    repository = ConversationRepository(session)
    conversation = repository.get(conversation_id, user_id=user_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    repository.archive(conversation)
    memory_store.reset(str(conversation_id))
    return {"status": "archived", "conversation_id": str(conversation_id)}


__all__ = ["router"]
