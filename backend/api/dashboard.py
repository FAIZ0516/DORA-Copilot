"""Jira dashboard snapshot endpoint (REST-only, not part of the chat agent)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from ..config import settings
from ..dashboard_service import get_jira_dashboard
from ..database.doradb import DoraDbConfigurationError, DoraDbQueryRejected, doradb_session
from ..schemas import JiraDashboardResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/jira-dashboard", response_model=JiraDashboardResponse)
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


__all__ = ["router"]
