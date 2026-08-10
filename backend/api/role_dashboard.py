"""Role dashboard endpoints (Scrum Master / Head of Department views).

Ported from the zara-data-workspace branch, where these lived directly in
``main.py``. In this architecture ``main.py`` is only a composition root, so
request handling belongs here alongside the other routers (AGENTS.md §4).
All values come from read-only, parameterized DoraDB queries via
``dashboard_service``; nothing here builds SQL.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from ..config import settings
from ..dashboard_registry import (
    ATTENTION_THRESHOLDS,
    UNSUPPORTED_METRICS,
    public_metric_registry,
)
from ..dashboard_service import (
    ISSUE_SORT_FIELDS,
    UnknownSquadError,
    get_dashboard_filter_options,
    get_dashboard_issues,
    get_dashboard_squads,
    get_portfolio_dashboard,
    get_squad_dashboard,
)
from ..database.doradb import DoraDbConfigurationError, doradb_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["role-dashboard"])


def _check_date_range(date_from: date | None, date_to: date | None) -> None:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must not be after date_to.")


def _active_project(project: str | None) -> str:
    return (project or settings.doradb_project_key).strip().upper()


@router.get("/metrics")
def dashboard_metrics() -> dict[str, Any]:
    return {
        "metrics": public_metric_registry(),
        "unsupported_metrics": UNSUPPORTED_METRICS,
        "attention_thresholds": ATTENTION_THRESHOLDS,
    }


@router.get("/squads")
def dashboard_squads(project: str | None = None) -> dict[str, Any]:
    active_project = _active_project(project)
    try:
        with doradb_session() as real_session:
            return get_dashboard_squads(real_session, project=active_project)
    except DoraDbConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception("Dashboard squad lookup failed project=%s", active_project)
        raise HTTPException(
            status_code=503, detail="Squad data is temporarily unavailable."
        ) from exc


@router.get("/filters")
def dashboard_filters(
    project: str | None = None,
    squad: str | None = Query(default=None, max_length=80),
) -> dict[str, Any]:
    active_project = _active_project(project)
    try:
        with doradb_session() as real_session:
            return get_dashboard_filter_options(
                real_session, project=active_project, squad=squad
            )
    except DoraDbConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception(
            "Dashboard filter lookup failed project=%s squad=%s", active_project, squad
        )
        raise HTTPException(
            status_code=503, detail="Dashboard filters are temporarily unavailable."
        ) from exc


@router.get("/portfolio")
def dashboard_portfolio(
    project: str | None = None,
    release: str | None = Query(default=None, max_length=120),
    sprint: str | None = Query(default=None, max_length=200),
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    _check_date_range(date_from, date_to)
    active_project = _active_project(project)
    try:
        with doradb_session() as real_session:
            payload = get_portfolio_dashboard(
                real_session,
                project=active_project,
                release=release,
                sprint=sprint,
                date_from=date_from,
                date_to=date_to,
            )
        logger.info(
            "dashboard_portfolio project=%s filters=%s",
            active_project,
            payload["applied_filters"],
        )
        return payload
    except DoraDbConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception("Portfolio dashboard query failed project=%s", active_project)
        raise HTTPException(
            status_code=503,
            detail="Portfolio dashboard data is temporarily unavailable.",
        ) from exc


@router.get("/squad/{squad_name}")
def dashboard_squad_detail(
    squad_name: str,
    project: str | None = None,
    release: str | None = Query(default=None, max_length=120),
    sprint: str | None = Query(default=None, max_length=200),
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    _check_date_range(date_from, date_to)
    active_project = _active_project(project)
    try:
        with doradb_session() as real_session:
            payload = get_squad_dashboard(
                real_session,
                project=active_project,
                squad=squad_name,
                release=release,
                sprint=sprint,
                date_from=date_from,
                date_to=date_to,
            )
        logger.info("dashboard_squad project=%s squad=%s", active_project, payload["squad"])
        return payload
    except DoraDbConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except UnknownSquadError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception(
            "Squad dashboard query failed project=%s squad=%s", active_project, squad_name
        )
        raise HTTPException(
            status_code=503, detail="Squad dashboard data is temporarily unavailable."
        ) from exc


@router.get("/issues")
def dashboard_issues(
    squad: str = Query(min_length=1, max_length=80),
    project: str | None = None,
    release: str | None = Query(default=None, max_length=120),
    sprint: str | None = Query(default=None, max_length=200),
    date_from: date | None = None,
    date_to: date | None = None,
    issue_type: str | None = Query(default=None, max_length=80),
    status: str | None = Query(default=None, max_length=80),
    priority: str | None = Query(default=None, max_length=80),
    assignee: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1, le=100_000),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="updated"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    _check_date_range(date_from, date_to)
    if sort_by not in ISSUE_SORT_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"sort_by must be one of: {', '.join(sorted(ISSUE_SORT_FIELDS))}.",
        )
    active_project = _active_project(project)
    try:
        with doradb_session() as real_session:
            return get_dashboard_issues(
                real_session,
                project=active_project,
                squad=squad,
                release=release,
                sprint=sprint,
                date_from=date_from,
                date_to=date_to,
                issue_type=issue_type,
                status=status,
                priority=priority,
                assignee=assignee,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
            )
    except DoraDbConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except UnknownSquadError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception(
            "Dashboard issue lookup failed project=%s squad=%s", active_project, squad
        )
        raise HTTPException(
            status_code=503, detail="Issue details are temporarily unavailable."
        ) from exc


__all__ = ["router"]
