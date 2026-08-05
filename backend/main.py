"""FastAPI entry point for the DoraDB-only conversational AI application."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .agent_system.audit import audit_log
from .agent_system.control import public_policy
from .agent_system.memory import memory_store
from .config import settings
from .db import get_db, init_db
from .doradb import (
    DoraDbConfigurationError,
    DoraDbQueryRejected,
    check_doradb,
    doradb_session,
)
from .doradb_agent import DoraDbAgent
from .doradb_catalog import METRIC_DEFINITIONS, QUERY_CATALOGUE
from .schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
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
    # SQLite is retained only for ElevenLabs character-usage accounting.
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    description=(
        "DeepSeek-powered conversational DORA intelligence over the real, "
        "read-only PostgreSQL DoraDB dataset."
    ),
    version="0.4.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


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

    if not settings.deepseek_configured:
        status = "degraded"
        detail = "DEEPSEEK_API_KEY is required for generative responses."

    return HealthResponse(
        status=status,
        database=database,
        data_source="doradb",
        database_connected=database_connected,
        llm_provider=f"deepseek:{settings.deepseek_model}",
        llm_configured=settings.deepseek_configured,
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


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Run DeepSeek planning and real DoraDB tools when data is required."""

    history = [item.model_dump() for item in request.history]
    try:
        if settings.doradb_configured:
            with doradb_session() as real_session:
                result = DoraDbAgent(real_session).chat(
                    request.message,
                    session_id=request.session_id,
                    history=history,
                )
        else:
            # Safe conversation can still run through DeepSeek. Any plan that
            # requires dataset evidence is rejected before query execution.
            result = DoraDbAgent(None).chat(
                request.message,
                session_id=request.session_id,
                history=history,
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
