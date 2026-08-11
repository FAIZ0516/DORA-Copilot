"""Short-lived, project-scoped cache for safe Jira dashboard aggregates."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from threading import RLock
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import settings
from .dashboard_registry import (
    ATTENTION_THRESHOLDS,
    INVALID_SQUAD_VALUES,
    JIRA_TABLE,
    METRIC_REGISTRY,
    RELEASE_INFO_TABLE,
    public_metric_registry,
)
from .database.doradb import query_doradb


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


class UnknownSquadError(LookupError):
    """Raised when a squad is not present in the active project scope."""


def _execute_rows(
    session: Session,
    statement: str,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    return [dict(row) for row in session.execute(text(statement), params).mappings().all()]


def _scope_sql(
    *,
    project: str,
    squad: str | None = None,
    release: str | None = None,
    sprint: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[list[str], dict[str, Any]]:
    clauses = ["j.project_key = :project"]
    params: dict[str, Any] = {"project": project.strip().upper()}
    if squad:
        clauses.append("UPPER(BTRIM(j.dcpsquad)) = UPPER(:squad)")
        params["squad"] = squad.strip()
    if release:
        clauses.append(
            """EXISTS (
                SELECT 1
                FROM json_array_elements_text(
                    COALESCE(j.fixversions -> 'fixversions', '[]'::json)
                ) AS dashboard_release(value)
                WHERE BTRIM(dashboard_release.value) = :release
            )"""
        )
        params["release"] = release.strip()
    if sprint:
        clauses.append(
            """EXISTS (
                SELECT 1
                FROM json_array_elements(
                    COALESCE(j.sprints -> 'sprints', '[]'::json)
                ) AS dashboard_sprint(value)
                WHERE BTRIM(COALESCE(dashboard_sprint.value ->> 'name', '')) = :sprint
            )"""
        )
        params["sprint"] = sprint.strip()
    if date_from:
        clauses.append("j.created::date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        clauses.append("j.created::date <= :date_to")
        params["date_to"] = date_to
    return clauses, params


def _applied_filters(
    *,
    project: str,
    squad: str | None = None,
    release: str | None = None,
    sprint: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "project": project.strip().upper(),
            "squad": squad.strip() if squad else None,
            "release": release.strip() if release else None,
            "sprint": sprint.strip() if sprint else None,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "date_field": "created",
        }.items()
        if value is not None
    }


def _metric_cards(keys: list[str], values: dict[str, Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for key in keys:
        definition = METRIC_REGISTRY[key]
        cards.append({"key": key, "value": values.get(key), **definition})
    return cards


def get_dashboard_squads(session: Session, *, project: str) -> dict[str, Any]:
    rows = _execute_rows(
        session,
        f"""
        SELECT BTRIM(j.dcpsquad) AS name, COUNT(*) AS issue_count
        FROM {JIRA_TABLE} AS j
        WHERE j.project_key = :project
          AND j.dcpsquad IS NOT NULL
          AND BTRIM(j.dcpsquad) <> ''
        GROUP BY BTRIM(j.dcpsquad)
        ORDER BY LOWER(BTRIM(j.dcpsquad)), BTRIM(j.dcpsquad)
        LIMIT 200
        """,
        {"project": project.strip().upper()},
    )
    squads: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for row in rows:
        name = str(row["name"]).strip()
        reason = INVALID_SQUAD_VALUES.get(name.upper())
        if reason:
            excluded.append({"value": name, "reason": reason})
        else:
            squads.append({"name": name, "issue_count": int(row["issue_count"] or 0)})
    return {
        "project": project.strip().upper(),
        "squads": squads,
        "excluded_values": excluded,
        "validation_rule": "Trim non-empty values and exclude only documented generic placeholders.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _ensure_squad(session: Session, *, project: str, squad: str) -> str:
    available = get_dashboard_squads(session, project=project)["squads"]
    match = next(
        (row["name"] for row in available if row["name"].casefold() == squad.strip().casefold()),
        None,
    )
    if match is None:
        raise UnknownSquadError(f"Squad '{squad}' is not available in project {project.upper()}.")
    return str(match)


def get_dashboard_filter_options(
    session: Session,
    *,
    project: str,
    squad: str | None = None,
) -> dict[str, Any]:
    clauses, params = _scope_sql(project=project, squad=squad)
    where = " AND ".join(clauses)
    releases = _execute_rows(
        session,
        f"""
        SELECT BTRIM(release_value.value) AS value, COUNT(DISTINCT j.key) AS issue_count
        FROM {JIRA_TABLE} AS j
        CROSS JOIN LATERAL json_array_elements_text(
            COALESCE(j.fixversions -> 'fixversions', '[]'::json)
        ) AS release_value(value)
        WHERE {where} AND BTRIM(release_value.value) <> ''
        GROUP BY BTRIM(release_value.value)
        ORDER BY LOWER(BTRIM(release_value.value)), BTRIM(release_value.value)
        LIMIT 250
        """,
        params,
    )
    sprints = _execute_rows(
        session,
        f"""
        SELECT BTRIM(sprint_value.value ->> 'name') AS value,
               COUNT(DISTINCT j.key) AS issue_count
        FROM {JIRA_TABLE} AS j
        CROSS JOIN LATERAL json_array_elements(
            COALESCE(j.sprints -> 'sprints', '[]'::json)
        ) AS sprint_value(value)
        WHERE {where}
          AND BTRIM(COALESCE(sprint_value.value ->> 'name', '')) <> ''
        GROUP BY BTRIM(sprint_value.value ->> 'name')
        ORDER BY LOWER(BTRIM(sprint_value.value ->> 'name')),
                 BTRIM(sprint_value.value ->> 'name')
        LIMIT 250
        """,
        params,
    )
    date_rows = _execute_rows(
        session,
        f"SELECT MIN(j.created)::date AS minimum, MAX(j.created)::date AS maximum FROM {JIRA_TABLE} AS j WHERE {where}",
        params,
    )

    def issue_values(expression: str) -> list[dict[str, Any]]:
        """Return selectable values for one allowlisted ticket dimension."""

        return _execute_rows(
            session,
            f"""
            SELECT BTRIM({expression}) AS value, COUNT(*) AS issue_count
            FROM {JIRA_TABLE} AS j
            WHERE {where}
              AND {expression} IS NOT NULL
              AND BTRIM({expression}) <> ''
            GROUP BY BTRIM({expression})
            ORDER BY LOWER(BTRIM({expression})), BTRIM({expression})
            LIMIT 500
            """,
            params,
        )

    return {
        "project": project.strip().upper(),
        "squad": squad,
        "releases": releases,
        "sprints": sprints,
        "date_range": date_rows[0] if date_rows else {"minimum": None, "maximum": None},
        "date_field": "created",
        "issue_filters": {
            "issue_types": issue_values("j.issuetype"),
            "statuses": issue_values("j.status"),
            "priorities": issue_values("j.priority"),
            "assignees": issue_values("j.assignee"),
        },
        "notes": [
            "Release and sprint filters represent stored Jira associations, not deployment or commitment history.",
            "Date range filters Jira created dates.",
        ],
    }


def _attention(row: dict[str, Any]) -> dict[str, Any]:
    reasons: list[dict[str, Any]] = []
    if int(row.get("unknown_status_count") or 0) > 0:
        reasons.append({
            "metric": "status_category",
            "value": int(row["unknown_status_count"]),
            "reason": "issues have a missing status category",
        })
        status = "Data Incomplete"
    else:
        critical = ATTENTION_THRESHOLDS["needs_attention"]
        checks = [
            ("high_priority_open_bugs", int(row.get("high_priority_open_bugs") or 0), critical["high_priority_open_bugs"], "High-priority open bugs meet the escalation threshold"),
            ("oldest_unresolved_days", int(row.get("oldest_unresolved_days") or 0), critical["oldest_unresolved_days"], "oldest unresolved work exceeds the age threshold"),
            ("impeded_work", int(row.get("impeded_work") or 0), critical["impeded_work"], "current impeded work is present"),
        ]
        for metric, value, threshold, reason in checks:
            if value >= threshold:
                reasons.append({"metric": metric, "value": value, "threshold": threshold, "reason": reason})
        completion = float(row.get("completion_pct") or 0)
        if int(row.get("total_work") or 0) and completion < critical["completion_pct_below"]:
            reasons.append({
                "metric": "completion_pct",
                "value": completion,
                "threshold": critical["completion_pct_below"],
                "reason": "end-state percentage is below the configured threshold",
            })
        status = "Needs Attention" if reasons else "Healthy"
        if status == "Healthy":
            monitor = ATTENTION_THRESHOLDS["monitor"]
            monitor_checks = [
                ("high_priority_open_bugs", int(row.get("high_priority_open_bugs") or 0), monitor["high_priority_open_bugs"], "High-priority open bugs need monitoring"),
                ("oldest_unresolved_days", int(row.get("oldest_unresolved_days") or 0), monitor["oldest_unresolved_days"], "unresolved work is ageing"),
                ("unassigned_open_work", int(row.get("unassigned_open_work") or 0), monitor["unassigned_open_work"], "open work is unassigned"),
            ]
            for metric, value, threshold, reason in monitor_checks:
                if value >= threshold:
                    reasons.append({"metric": metric, "value": value, "threshold": threshold, "reason": reason})
            if int(row.get("total_work") or 0) and completion < monitor["completion_pct_below"]:
                reasons.append({
                    "metric": "completion_pct",
                    "value": completion,
                    "threshold": monitor["completion_pct_below"],
                    "reason": "end-state percentage is below the monitoring threshold",
                })
            if reasons:
                status = "Monitor"
    return {"status": status, "reasons": reasons}


def _aggregate_statement(where: str, *, group_by_squad: bool) -> str:
    squad_select = "BTRIM(j.dcpsquad) AS squad," if group_by_squad else ""
    squad_group = "GROUP BY BTRIM(j.dcpsquad)" if group_by_squad else ""
    populated = " AND j.dcpsquad IS NOT NULL AND BTRIM(j.dcpsquad) <> ''" if group_by_squad else ""
    return f"""
        SELECT
            {squad_select}
            COUNT(*) AS total_work,
            COUNT(*) FILTER (WHERE j.status_category = 'Done') AS completed_work,
            ROUND(100.0 * COUNT(*) FILTER (WHERE j.status_category = 'Done') / NULLIF(COUNT(*), 0), 2) AS completion_pct,
            COUNT(*) FILTER (WHERE j.resolved IS NULL AND COALESCE(j.status_category, '') <> 'Done') AS active_work,
            COUNT(*) FILTER (WHERE j.status_category = 'In Progress') AS in_progress_work,
            COUNT(*) FILTER (WHERE j.status_category = 'To Do') AS todo_work,
            COUNT(*) FILTER (
                WHERE LOWER(COALESCE(j.issuetype, '')) = 'bug'
                  AND j.resolved IS NULL AND COALESCE(j.status_category, '') <> 'Done'
            ) AS open_bugs,
            COUNT(*) FILTER (
                WHERE LOWER(COALESCE(j.issuetype, '')) = 'bug'
                  AND LOWER(COALESCE(j.priority, '')) = 'high'
                  AND j.resolved IS NULL AND COALESCE(j.status_category, '') <> 'Done'
            ) AS high_priority_open_bugs,
            COUNT(*) FILTER (
                WHERE j.resolved IS NULL AND COALESCE(j.status_category, '') <> 'Done'
                  AND (j.assignee IS NULL OR BTRIM(j.assignee) = '')
            ) AS unassigned_open_work,
            COUNT(*) FILTER (WHERE UPPER(COALESCE(j.status, '')) = 'IMPEDED') AS impeded_work,
            ROUND(AVG(CURRENT_DATE - j.created::date) FILTER (
                WHERE j.resolved IS NULL AND COALESCE(j.status_category, '') <> 'Done'
                  AND j.created IS NOT NULL
            ), 1) AS average_unresolved_days,
            MAX(CURRENT_DATE - j.created::date) FILTER (
                WHERE j.resolved IS NULL AND COALESCE(j.status_category, '') <> 'Done'
                  AND j.created IS NOT NULL
            ) AS oldest_unresolved_days,
            COUNT(*) FILTER (WHERE j.status_category IS NULL OR BTRIM(j.status_category) = '') AS unknown_status_count,
            COUNT(*) FILTER (WHERE j.issuetype IS NULL OR BTRIM(j.issuetype) = '') AS missing_issue_type_count
        FROM {JIRA_TABLE} AS j
        WHERE {where}{populated}
        {squad_group}
    """


def get_portfolio_dashboard(
    session: Session,
    *,
    project: str,
    release: str | None = None,
    sprint: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    clauses, params = _scope_sql(
        project=project, release=release, sprint=sprint, date_from=date_from, date_to=date_to
    )
    where = " AND ".join(clauses)
    aggregate_rows = _execute_rows(session, _aggregate_statement(where, group_by_squad=False), params)
    portfolio = aggregate_rows[0] if aggregate_rows else {}
    squad_rows = _execute_rows(session, _aggregate_statement(where, group_by_squad=True), params)
    comparison: list[dict[str, Any]] = []
    for raw in squad_rows:
        row = dict(raw)
        row.update(_attention(row))
        comparison.append(row)
    severity = {"Needs Attention": 0, "Data Incomplete": 1, "Monitor": 2, "Healthy": 3}
    comparison.sort(
        key=lambda item: (
            severity.get(str(item["status"]), 4),
            -int(item.get("high_priority_open_bugs") or 0),
            -int(item.get("oldest_unresolved_days") or 0),
            str(item.get("squad", "")).casefold(),
        )
    )
    quality_rows = _execute_rows(
        session,
        f"""
        SELECT
            COUNT(*) FILTER (WHERE j.dcpsquad IS NULL OR BTRIM(j.dcpsquad) = '') AS missing_squad,
            COUNT(*) FILTER (WHERE j.assignee IS NULL OR BTRIM(j.assignee) = '') AS missing_assignee,
            COUNT(*) FILTER (WHERE j.status_category = 'Done' AND j.resolved IS NULL) AS done_without_resolved
        FROM {JIRA_TABLE} AS j WHERE {where}
        """,
        params,
    )
    quality = quality_rows[0] if quality_rows else {}
    portfolio["total_squads"] = len(comparison)
    portfolio["missing_squad"] = int(quality.get("missing_squad") or 0)
    portfolio["squads_requiring_attention"] = sum(
        row["status"] in {"Needs Attention", "Data Incomplete"} for row in comparison
    )
    top_attention = [row for row in comparison if row["status"] != "Healthy"][:5]
    generated = datetime.now(timezone.utc).isoformat()
    return {
        "view": "portfolio",
        "applied_filters": _applied_filters(
            project=project, release=release, sprint=sprint, date_from=date_from, date_to=date_to
        ),
        "generated_at": generated,
        "empty": int(portfolio.get("total_work") or 0) == 0,
        "kpis": portfolio,
        "metric_cards": _metric_cards(
            [
                "total_work", "active_work", "completion_pct", "open_bugs",
                "high_priority_open_bugs", "in_progress_work", "todo_work",
                "unassigned_open_work", "missing_squad", "squads_requiring_attention",
            ],
            portfolio,
        ),
        "squad_comparison": comparison,
        "attention_items": top_attention,
        "data_quality": quality,
        "data_quality_notes": [
            f"{int(quality.get('missing_squad') or 0):,} scoped issues have no populated squad and are excluded from squad rows.",
            "Done is an end-state category and can include rejected or cancelled work.",
            "Attention is deterministic and rule-based; it is not AI confidence.",
        ],
        "attention_thresholds": ATTENTION_THRESHOLDS,
        "metric_registry": public_metric_registry(),
    }


def _breakdown(
    session: Session,
    *,
    where: str,
    params: dict[str, Any],
    select_expression: str,
    alias: str,
    extra_where: str = "",
) -> list[dict[str, Any]]:
    return _execute_rows(
        session,
        f"""
        SELECT {select_expression} AS {alias}, COUNT(*) AS issue_count
        FROM {JIRA_TABLE} AS j
        WHERE {where} {extra_where}
        GROUP BY {select_expression}
        ORDER BY issue_count DESC, {alias}
        LIMIT 100
        """,
        params,
    )


def get_squad_dashboard(
    session: Session,
    *,
    squad: str,
    project: str,
    release: str | None = None,
    sprint: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    canonical_squad = _ensure_squad(session, project=project, squad=squad)
    clauses, params = _scope_sql(
        project=project, squad=canonical_squad, release=release, sprint=sprint,
        date_from=date_from, date_to=date_to,
    )
    where = " AND ".join(clauses)
    rows = _execute_rows(session, _aggregate_statement(where, group_by_squad=False), params)
    kpis = rows[0] if rows else {}
    kpis.update(_attention(kpis))
    work_status = _breakdown(
        session, where=where, params=params,
        select_expression="COALESCE(NULLIF(BTRIM(j.status_category), ''), 'Unknown')",
        alias="status_category",
    )
    bug_priority = _breakdown(
        session, where=where, params=params,
        select_expression="COALESCE(NULLIF(BTRIM(j.priority), ''), 'Unknown')",
        alias="priority",
        extra_where="AND LOWER(COALESCE(j.issuetype, '')) = 'bug' AND j.resolved IS NULL AND COALESCE(j.status_category, '') <> 'Done'",
    )
    issue_types = _breakdown(
        session, where=where, params=params,
        select_expression="COALESCE(NULLIF(BTRIM(j.issuetype), ''), 'Unknown')",
        alias="issue_type",
    )
    feature_status = _breakdown(
        session, where=where, params=params,
        select_expression="COALESCE(NULLIF(BTRIM(j.status_category), ''), 'Unknown')",
        alias="status_category",
        extra_where="AND LOWER(COALESCE(j.issuetype, '')) = 'feature'",
    )
    test_status = _breakdown(
        session, where=where, params=params,
        select_expression="COALESCE(NULLIF(BTRIM(j.status_category), ''), 'Unknown')",
        alias="status_category",
        extra_where="AND LOWER(COALESCE(j.issuetype, '')) = 'test'",
    )
    release_info: list[dict[str, Any]] = []
    if release:
        release_info = _execute_rows(
            session,
            f"""
            SELECT fixversion, release_date, release_category,
                   release_plan_start, release_actual_start,
                   release_plan_end, release_actual_end
            FROM {RELEASE_INFO_TABLE}
            WHERE fixversion = :selected_release OR release_name_sorted = :selected_release
            ORDER BY release_date DESC NULLS LAST
            LIMIT 10
            """,
            {"selected_release": release.strip()},
        )
    generated = datetime.now(timezone.utc).isoformat()
    return {
        "view": "squad_detail",
        "squad": canonical_squad,
        "applied_filters": _applied_filters(
            project=project, squad=canonical_squad, release=release, sprint=sprint,
            date_from=date_from, date_to=date_to,
        ),
        "generated_at": generated,
        "empty": int(kpis.get("total_work") or 0) == 0,
        "kpis": kpis,
        "metric_cards": _metric_cards(
            [
                "total_work", "completed_work", "completion_pct", "in_progress_work",
                "todo_work", "open_bugs", "high_priority_open_bugs",
                "unassigned_open_work", "average_unresolved_days", "oldest_unresolved_days",
            ],
            kpis,
        ),
        "work_status": work_status,
        "bug_health": {"open_by_priority": bug_priority},
        "issue_types": issue_types,
        "feature_work_status": feature_status,
        "test_work_status": test_status,
        "release_information": release_info,
        "attention_items": kpis.get("reasons", []),
        "data_quality": {
            "unknown_status_count": int(kpis.get("unknown_status_count") or 0),
            "missing_issue_type_count": int(kpis.get("missing_issue_type_count") or 0),
        },
        "data_quality_notes": [
            "Test Work Status uses Jira status categories; no execution pass/fail field exists.",
            "Calendar issue age is not engineering cycle time or DORA Lead Time for Changes.",
            "Release and sprint membership are stored associations, not commitment history.",
        ],
        "attention_thresholds": ATTENTION_THRESHOLDS,
        "metric_registry": public_metric_registry(),
    }


ISSUE_SORT_FIELDS = {
    "issue_key": "j.key",
    "created": "j.created",
    "updated": "j.updated",
    "status": "j.status",
    "priority": "j.priority",
    "age": "age_days",
}


def get_dashboard_issues(
    session: Session,
    *,
    project: str,
    squad: str,
    release: str | None = None,
    sprint: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    issue_type: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    assignee: str | None = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "updated",
    sort_order: str = "desc",
) -> dict[str, Any]:
    canonical_squad = _ensure_squad(session, project=project, squad=squad)
    clauses, params = _scope_sql(
        project=project, squad=canonical_squad, release=release, sprint=sprint,
        date_from=date_from, date_to=date_to,
    )
    for name, value, expression in [
        ("issue_type", issue_type, "j.issuetype"),
        ("status", status, "j.status"),
        ("priority", priority, "j.priority"),
        ("assignee", assignee, "j.assignee"),
    ]:
        if value:
            clauses.append(f"UPPER(BTRIM({expression})) = UPPER(:{name})")
            params[name] = value.strip()
    where = " AND ".join(clauses)
    total_rows = _execute_rows(
        session,
        f"SELECT COUNT(*) AS total FROM {JIRA_TABLE} AS j WHERE {where}",
        params,
    )
    total = int(total_rows[0]["total"] if total_rows else 0)
    safe_page = max(1, page)
    safe_size = max(1, min(page_size, 100))
    params.update({"limit": safe_size, "offset": (safe_page - 1) * safe_size})
    order_column = ISSUE_SORT_FIELDS.get(sort_by, ISSUE_SORT_FIELDS["updated"])
    direction = "ASC" if sort_order.lower() == "asc" else "DESC"
    rows = _execute_rows(
        session,
        f"""
        SELECT
            j.key AS issue_key,
            j.summary,
            j.issuetype AS issue_type,
            j.status,
            j.status_category,
            j.priority,
            j.assignee,
            BTRIM(j.dcpsquad) AS squad,
            j.created,
            j.updated,
            j.resolved,
            CASE WHEN j.resolved IS NULL AND j.created IS NOT NULL
                 THEN GREATEST(0, CURRENT_DATE - j.created::date) END AS age_days,
            j.featurelink_key AS feature_link,
            (
                SELECT STRING_AGG(BTRIM(release_value.value), ', ' ORDER BY BTRIM(release_value.value))
                FROM json_array_elements_text(
                    COALESCE(j.fixversions -> 'fixversions', '[]'::json)
                ) AS release_value(value)
            ) AS releases,
            (
                SELECT STRING_AGG(BTRIM(sprint_value.value ->> 'name'), ', ' ORDER BY BTRIM(sprint_value.value ->> 'name'))
                FROM json_array_elements(
                    COALESCE(j.sprints -> 'sprints', '[]'::json)
                ) AS sprint_value(value)
                WHERE BTRIM(COALESCE(sprint_value.value ->> 'name', '')) <> ''
            ) AS sprints
        FROM {JIRA_TABLE} AS j
        WHERE {where}
        ORDER BY {order_column} {direction} NULLS LAST, j.key ASC
        LIMIT :limit OFFSET :offset
        """,
        params,
    )
    return {
        "items": rows,
        "page": safe_page,
        "page_size": safe_size,
        "total": total,
        "total_pages": (total + safe_size - 1) // safe_size,
        "sort_by": sort_by if sort_by in ISSUE_SORT_FIELDS else "updated",
        "sort_order": direction.lower(),
        "applied_filters": _applied_filters(
            project=project, squad=canonical_squad, release=release, sprint=sprint,
            date_from=date_from, date_to=date_to,
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


__all__ += [
    "ISSUE_SORT_FIELDS",
    "UnknownSquadError",
    "get_dashboard_filter_options",
    "get_dashboard_issues",
    "get_dashboard_squads",
    "get_portfolio_dashboard",
    "get_squad_dashboard",
]
