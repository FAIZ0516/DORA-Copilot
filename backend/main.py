"""FastAPI entry point for the DoraDB-only conversational AI application."""

from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .agent_system.audit import audit_log
from .agent_system.control import public_policy
from .agent_system.memory import memory_store
from .config import settings
from .conversation_context import persistent_context, recent_history, update_persistent_state
from .conversation_repository import ConversationRepository, serialize_conversation, serialize_message
from .db import get_db, init_db
from .dashboard_service import get_jira_dashboard
from .doradb import (
    DoraDbConfigurationError,
    DoraDbQueryRejected,
    check_doradb,
    doradb_session,
)
from .doradb_agent import DoraDbAgent
from .doradb_catalog import METRIC_DEFINITIONS, QUERY_CATALOGUE
from .llm import GenerativeAIClient
from .schemas import (
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationMessageCreate,
    ConversationMessageResponse,
    ConversationSummaryResponse,
    HealthResponse,
    JiraDashboardResponse,
    SessionResetRequest,
    TTSRequest,
)
from .tts import (
    TTSNotConfiguredError,
    TTSProviderError,
    TTSQuotaExceededError,
    create_audio_stream,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Initialize the writable runtime store; analytical DoraDB remains read-only.
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    description=(
        "Configured-LLM conversational DORA intelligence over the real, "
        "read-only PostgreSQL DoraDB dataset."
    ),
    version="0.4.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["Content-Type", "X-Development-Session"],
)


def development_session(
    value: str = Header(default="local-development", alias="X-Development-Session"),
) -> str:
    """Temporary browser identity for development; replace with authenticated user IDs."""

    cleaned = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,120}", cleaned):
        raise HTTPException(status_code=400, detail="Invalid development session identifier.")
    return cleaned


@app.post("/api/conversations", response_model=ConversationSummaryResponse)
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


@app.get("/api/conversations", response_model=ConversationListResponse)
def list_conversations(
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> ConversationListResponse:
    conversations = ConversationRepository(session).list_recent(user_id=user_id)
    return ConversationListResponse.model_validate(
        {"conversations": [serialize_conversation(item) for item in conversations]}
    )


@app.get("/api/conversations/{conversation_id}", response_model=ConversationDetailResponse)
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


@app.post(
    "/api/conversations/{conversation_id}/messages",
    response_model=ConversationMessageResponse,
)
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


@app.delete("/api/conversations/{conversation_id}")
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


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    database_connected = False
    database = f"postgresql:{settings.doradb_name}"
    status = "ok"
    detail: str | None = None

    if not settings.doradb_configured:
        status = "degraded"
        database = "DoraDB credentials required"
        detail = "Configure DORADB_USER and DORADB_PASSWORD to enable dataset analysis."
    else:
        try:
            with doradb_session() as real_session:
                check_doradb(real_session)
            database_connected = True
        except (DoraDbConfigurationError, SQLAlchemyError) as exc:
            logger.warning("DoraDB health check failed: %s", exc)
            status = "degraded"
            detail = "DoraDB is configured but not reachable."

    llm = GenerativeAIClient(settings)
    try:
        llm_status = llm.check_availability()
    finally:
        llm.close()
    if not llm_status.available:
        status = "degraded"
        if llm_status.detail:
            detail = f"{detail} {llm_status.detail}" if detail else llm_status.detail

    return HealthResponse(
        status=status,
        database=database,
        data_source="doradb",
        database_connected=database_connected,
        llm_provider=settings.llm_source,
        llm_model=settings.llm_model,
        llm_configured=llm_status.configured,
        llm_available=llm_status.available,
        tts_configured=bool(settings.elevenlabs_api_key),
        detail=detail,
    )


@app.get("/api/projects")
def projects() -> dict[str, list[dict[str, Any]]]:
    """Return the single configured real DoraDB project scope."""

    return {
        "projects": [
            {
                "key": settings.doradb_project_key,
                "name": f"{settings.doradb_project_key} · DoraDB",
                "issue_count": None,
            }
        ]
    }


@app.get("/api/jira-dashboard", response_model=JiraDashboardResponse)
def jira_dashboard(
    project_key: str | None = None,
    refresh: bool = False,
) -> JiraDashboardResponse:
    """Return bounded Jira snapshot aggregates; manual refresh bypasses cache."""

    active_project = (project_key or settings.doradb_project_key).strip().upper()
    try:
        with doradb_session() as real_session:
            payload = get_jira_dashboard(
                real_session,
                project_key=active_project,
                refresh=refresh,
            )
        logger.info(
            "jira_dashboard project=%s cached=%s",
            active_project,
            payload["cached"],
        )
        return JiraDashboardResponse.model_validate(payload)
    except DoraDbConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DoraDbQueryRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception("Jira dashboard query failed for project=%s", active_project)
        raise HTTPException(
            status_code=503,
            detail="The Jira dashboard data is temporarily unavailable.",
        ) from exc


@app.post("/api/chat", response_model=ChatResponse)
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
            # Safe conversation can still run through the configured LLM. Any plan that
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


@app.post("/api/reset-session")
def reset_session(request: SessionResetRequest) -> dict[str, Any]:
    removed = memory_store.reset(request.session_id)
    return {"status": "ok", "session_id": request.session_id, "memory_removed": removed}


@app.get("/api/metrics")
def metrics() -> dict[str, Any]:
    return {
        "project": settings.doradb_project_key,
        "metrics": [
            {"id": key, "definition": value}
            for key, value in METRIC_DEFINITIONS.items()
        ],
    }


@app.get("/api/query-catalogue")
def query_catalogue() -> dict[str, Any]:
    return {
        "queries": [
            {
                "id": query_id,
                "purpose": definition["purpose"],
                "allowed_filters": definition["allowed_filters"],
                "default_limit": definition["default_limit"],
            }
            for query_id, definition in QUERY_CATALOGUE.items()
        ],
        "control": public_policy(),
    }


@app.get("/api/audit/recent")
def recent_audit(limit: int = 25) -> dict[str, Any]:
    return {"records": audit_log.recent(limit), "memory": memory_store.stats()}


@app.post(
    "/api/tts",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"audio/mpeg": {}}},
        413: {"description": "Text exceeds the per-request voice limit"},
        429: {"description": "Monthly character allowance exhausted"},
        503: {"description": "ElevenLabs is not configured"},
    },
)
async def text_to_speech(
    request: TTSRequest,
    session: Session = Depends(get_db),
) -> StreamingResponse:
    if len(request.text) > settings.elevenlabs_max_chars_per_request:
        raise HTTPException(
            status_code=413,
            detail=(
                "Voice text is too long. "
                f"Maximum: {settings.elevenlabs_max_chars_per_request:,} characters."
            ),
        )
    try:
        audio = await create_audio_stream(request.text, session)
    except TTSNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TTSQuotaExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except TTSProviderError as exc:
        logger.warning("ElevenLabs generation failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    headers = {
        "Cache-Control": "private, max-age=3600",
        "X-TTS-Characters-Used": str(audio.usage.used),
        "X-TTS-Characters-Remaining": str(audio.usage.remaining),
    }
    if audio.request_id:
        headers["X-ElevenLabs-Request-ID"] = audio.request_id
    return StreamingResponse(audio.chunks, media_type="audio/mpeg", headers=headers)
