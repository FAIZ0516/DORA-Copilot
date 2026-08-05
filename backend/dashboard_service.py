"""Short-lived, project-scoped cache for safe Jira dashboard aggregates."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any, Callable

from sqlalchemy.orm import Session

from .config import settings
from .doradb import query_doradb


DashboardLoader = Callable[[], dict[str, Any]]


class DashboardAggregateCache:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl = timedelta(seconds=ttl_seconds)
        self.entries: dict[str, tuple[datetime, dict[str, Any]]] = {}
        self.lock = RLock()

    def get(
        self,
        project_key: str,
        loader: DashboardLoader,
        *,
        refresh: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        timestamp = now or datetime.now(timezone.utc)
        cache_key = project_key.strip().upper()
        with self.lock:
            cached = self.entries.get(cache_key)
            if not refresh and cached and timestamp - cached[0] <= self.ttl:
                payload = deepcopy(cached[1])
                payload["cached"] = True
                return payload

        payload = loader()
        payload["cached"] = False
        payload["refreshed_at"] = timestamp.isoformat()
        with self.lock:
            self.entries[cache_key] = (timestamp, deepcopy(payload))
        return payload

    def clear(self) -> None:
        with self.lock:
            self.entries.clear()


def _rows(
    session: Session,
    query_id: str,
    project_key: str,
) -> list[dict[str, Any]]:
    return query_doradb(
        session,
        query_id=query_id,
        filters={"project_key": project_key},
    )["rows"]


def _load_dashboard(session: Session, project_key: str) -> dict[str, Any]:
    kpi_rows = _rows(session, "jira_dashboard_kpis", project_key)
    status_rows = _rows(session, "jira_dashboard_status_categories", project_key)
    type_rows = _rows(session, "jira_dashboard_issue_types", project_key)
    ageing_rows = _rows(session, "jira_dashboard_open_ageing", project_key)
    quality_rows = _rows(session, "jira_dashboard_data_quality", project_key)

    kpis = kpi_rows[0] if kpi_rows else {
        "total_issues": 0,
        "open_work_count": 0,
        "impeded_issues": 0,
        "missing_squad_count": 0,
        "missing_squad_pct": 0.0,
    }
    quality = quality_rows[0] if quality_rows else {
        "missing_squad_count": 0,
        "missing_assignee_count": 0,
        "done_without_resolved_count": 0,
        "invalid_resolution_interval_count": 0,
    }
    return {
        "project_scope": {"project_key": project_key.upper()},
        "empty": int(kpis.get("total_issues") or 0) == 0,
        "kpis": kpis,
        "status_categories": status_rows,
        "issue_types": type_rows,
        "open_ageing": ageing_rows,
        "data_quality": quality,
        "notes": [
            "Open Work is a local reporting definition: unresolved and not in the Done category.",
            "Done is an end-state and may include rejected or cancelled work; it does not mean successful delivery.",
            "Ageing is calendar age from created date, not cycle time or DORA Lead Time for Changes.",
            "Issue counts do not represent equal effort, productivity, or business value.",
        ],
    }


dashboard_cache = DashboardAggregateCache(settings.jira_dashboard_cache_ttl_seconds)


def get_jira_dashboard(
    session: Session,
    *,
    project_key: str,
    refresh: bool = False,
) -> dict[str, Any]:
    return dashboard_cache.get(
        project_key,
        lambda: _load_dashboard(session, project_key),
        refresh=refresh,
    )


__all__ = ["DashboardAggregateCache", "dashboard_cache", "get_jira_dashboard"]
