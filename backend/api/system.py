"""Health, capability, and observability endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from sqlalchemy.exc import SQLAlchemyError

from ..agent.audit import audit_log
from ..agent.controls.execution_control import public_policy
from ..config import settings
from ..database.doradb import DoraDbConfigurationError, check_doradb, doradb_session
from ..database.doradb_catalog import METRIC_DEFINITIONS, QUERY_CATALOGUE
from ..llm import GenerativeAIClient
from ..memory.memory import memory_store
from ..schemas import HealthResponse, SessionResetRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health", response_model=HealthResponse)
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


@router.get("/projects")
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


@router.post("/reset-session")
def reset_session(request: SessionResetRequest) -> dict[str, Any]:
    removed = memory_store.reset(request.session_id)
    return {"status": "ok", "session_id": request.session_id, "memory_removed": removed}


@router.get("/metrics")
def metrics() -> dict[str, Any]:
    return {
        "project": settings.doradb_project_key,
        "metrics": [
            {"id": key, "definition": value}
            for key, value in METRIC_DEFINITIONS.items()
        ],
    }


@router.get("/query-catalogue")
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


@router.get("/audit/recent")
def recent_audit(limit: int = 25) -> dict[str, Any]:
    return {"records": audit_log.recent(limit), "memory": memory_store.stats()}


__all__ = ["router"]
