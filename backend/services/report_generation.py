"""Answer a template's standard questions from live data.

This is what makes a template reproducible: the questions are fixed, so the
same report run next week asks exactly the same things and reports whatever the
database says then. The answers are produced by the existing governed agent --
the same approved queries, guardrails and validation as any chat answer -- so a
generated report carries real provenance rather than model prose.

No planner, validator or query catalogue is duplicated here. This module only
sequences existing pieces.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from ..dashboard_service import get_portfolio_dashboard, get_squad_dashboard
from ..database.doradb import query_doradb

logger = logging.getLogger(__name__)


_ALL_SCOPE_LABELS = {
    "all squads",
    "all sprints",
    "all releases",
    "all available dates",
    "all visible features",
    "all features",
    "all tickets",
    "all ticket types",
    "all statuses",
    "all priorities",
    "all assignees",
}

_REPORT_SCOPE_KEYS = (
    "project", "squad", "sprint", "release", "date_from", "date_to",
    "feature", "issue_type", "status", "priority",
)


def normalize_report_scope(scope: dict[str, Any] | None) -> dict[str, Any]:
    """Keep identifiers only and turn UI-wide labels into no restriction.

    This is deliberately server-side even though the frontend also omits empty
    selections. A crafted request containing ``All sprints`` must never become
    a query for a sprint literally carrying that display label. Browser metric
    values and selected dashboard rows are not allowlisted here.
    """

    normalized: dict[str, Any] = {}
    for key in _REPORT_SCOPE_KEYS:
        raw = (scope or {}).get(key)
        if raw is None:
            continue
        value = raw.isoformat() if isinstance(raw, (date, datetime)) else str(raw).strip()
        if not value or value.casefold() in _ALL_SCOPE_LABELS:
            continue
        normalized[key] = value.upper() if key == "project" else value
    normalized.setdefault("project", "DCPM")
    return normalized


def _date_filter(value: Any) -> date | None:
    if not value:
        return None


def _json_safe(value: Any) -> Any:
    """Convert database-native scalar types before JSON-column persistence."""

    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _display_number(value: Any, *, percentage: bool = False) -> str:
    if value is None:
        return "Unavailable"
    number = float(value)
    rendered = f"{number:,.2f}".rstrip("0").rstrip(".")
    return f"{rendered}%" if percentage else rendered


def _dashboard_metric_items(payload: dict[str, Any], scope: dict[str, Any]) -> list[dict[str, Any]]:
    kpis = payload.get("kpis") or {}
    registry = payload.get("metric_registry") or {}
    labels = {
        "total_work": "Total Tickets",
        "completed_work": "Done / End-State Work",
        "completion_pct": "Sprint Completion" if scope.get("squad") else "Work Completed",
        "active_work": "Open Work",
        "impeded_work": "Active Blockers",
        "open_bugs": "Open Bugs",
        "delivery_risk": "Delivery Risk",
    }
    formulas = {
        "completed_work": "Count where Jira status_category is Done.",
        "impeded_work": "Count where the current Jira status is exactly Impeded.",
        "delivery_risk": "Deterministic dashboard attention thresholds; not an AI score.",
    }
    values = {
        "total_work": kpis.get("total_work"),
        "completed_work": kpis.get("completed_work"),
        "completion_pct": kpis.get("completion_pct"),
        "active_work": kpis.get("active_work"),
        "impeded_work": kpis.get("impeded_work"),
        "open_bugs": kpis.get("open_bugs"),
        "delivery_risk": kpis.get("status") or "Unavailable",
    }
    items: list[dict[str, Any]] = []
    for key, value in values.items():
        definition = registry.get(key) or {}
        display = (
            str(value)
            if key == "delivery_risk"
            else _display_number(value, percentage=key == "completion_pct")
        )
        items.append({
            "key": key,
            "label": labels[key],
            "value": display,
            "raw_value": value,
            "formula": definition.get("formula") or formulas.get(key) or "Verified dashboard aggregate.",
        })
    return items


def _summary_text(payload: dict[str, Any], scope: dict[str, Any]) -> str:
    kpis = payload.get("kpis") or {}
    subject = scope.get("squad") or f"project {scope.get('project', 'DCPM')}"
    return (
        f"{subject} has {_display_number(kpis.get('total_work'))} scoped tickets. "
        f"{_display_number(kpis.get('completed_work'))} are in Jira's Done category "
        f"({_display_number(kpis.get('completion_pct'), percentage=True)}), while "
        f"{_display_number(kpis.get('active_work'))} remain open. The current scope "
        f"contains {_display_number(kpis.get('impeded_work'))} tickets in Impeded status "
        f"and {_display_number(kpis.get('open_bugs'))} open bugs. The deterministic "
        f"dashboard delivery status is {kpis.get('status') or 'Unavailable'}."
    )


def _finding_text(payload: dict[str, Any]) -> str:
    kpis = payload.get("kpis") or {}
    lines = [
        f"Done / end-state work accounts for {_display_number(kpis.get('completion_pct'), percentage=True)} of the current filtered scope.",
        f"Open work is {_display_number(kpis.get('active_work'))}; this is the existing backend active_work calculation, not a frontend subtraction.",
        f"Active blockers are {_display_number(kpis.get('impeded_work'))}, based strictly on the current Impeded status definition.",
        f"Open bugs are {_display_number(kpis.get('open_bugs'))}, limited to unresolved Bug tickets outside Jira's Done category.",
    ]
    status_rows = payload.get("work_status") or []
    if status_rows:
        breakdown = ", ".join(
            f"{row.get('status_category') or 'Unknown'} {_display_number(row.get('issue_count'))}"
            for row in status_rows
        )
        lines.append(f"Stored Jira status-category breakdown: {breakdown}.")
    return "\n".join(lines)


def _risk_text(payload: dict[str, Any]) -> str:
    reasons = payload.get("attention_items") or []
    if not reasons:
        return "No configured dashboard attention threshold is currently triggered in this scope."
    lines = []
    for reason in reasons:
        threshold = reason.get("threshold")
        suffix = f"; configured threshold {threshold}" if threshold is not None else ""
        reason_text = str(reason.get("reason") or reason.get("metric") or "Attention signal")
        lines.append(
            f"{reason_text[:1].upper() + reason_text[1:]}: "
            f"{_display_number(reason.get('value'))}{suffix}."
        )
    return "\n".join(lines)


def _recommendation_text(payload: dict[str, Any]) -> str:
    kpis = payload.get("kpis") or {}
    reasons = payload.get("attention_items") or []
    actions: list[str] = []
    for metric in dict.fromkeys(str(reason.get("metric")) for reason in reasons):
        if metric == "impeded_work":
            actions.append(
                f"Review the {_display_number(kpis.get('impeded_work'))} tickets currently in Impeded status and record an owner and next action."
            )
        elif metric == "high_priority_open_bugs":
            actions.append(
                f"Review the {_display_number(kpis.get('high_priority_open_bugs'))} open High-priority bugs and agree their delivery order."
            )
        elif metric == "oldest_unresolved_days":
            actions.append(
                f"Review ageing unresolved work, beginning with items up to {_display_number(kpis.get('oldest_unresolved_days'))} days old."
            )
        elif metric == "unassigned_open_work":
            actions.append(
                f"Confirm ownership for the {_display_number(kpis.get('unassigned_open_work'))} unassigned open tickets."
            )
        elif metric == "completion_pct":
            actions.append(
                f"Review the {_display_number(kpis.get('active_work'))} tickets outside Done and confirm near-term priorities."
            )
        elif metric == "status_category":
            actions.append("Resolve missing Jira status-category data before relying on completion comparisons.")
    if not actions:
        actions.append("Continue monitoring the verified dashboard measures and reassess when the scope changes.")
    return "\n".join(actions)


def current_view_dashboard_evidence(doradb, scope: dict[str, Any] | None) -> dict[str, Any]:
    """Re-run the trusted dashboard calculation and shape it for a report.

    The caller supplies identifiers only. Metric values are read from DoraDB by
    the same service functions used by ``/api/dashboard`` and are then frozen
    into a report evidence snapshot before any narrative model is consulted.
    """

    normalized = normalize_report_scope(scope)
    kwargs = {
        "project": normalized["project"],
        "release": normalized.get("release"),
        "sprint": normalized.get("sprint"),
        "date_from": _date_filter(normalized.get("date_from")),
        "date_to": _date_filter(normalized.get("date_to")),
    }
    if normalized.get("squad"):
        payload = get_squad_dashboard(doradb, squad=normalized["squad"], **kwargs)
        calculation = "dashboard_service.get_squad_dashboard"
    else:
        payload = get_portfolio_dashboard(doradb, **kwargs)
        calculation = "dashboard_service.get_portfolio_dashboard"

    applied = {
        **normalized,
        **{key: value for key, value in (payload.get("applied_filters") or {}).items() if key != "date_field"},
    }
    generated_at = payload.get("generated_at") or datetime.now(timezone.utc).isoformat()
    if payload.get("empty"):
        return {
            "state": "needs_input",
            "reason": "The trusted dashboard calculation returned no tickets for this scope.",
            "scope": applied,
            "generated_at": generated_at,
        }

    items = _dashboard_metric_items(payload, applied)
    summary = _summary_text(payload, applied)
    findings = _finding_text(payload)
    risks = _risk_text(payload)
    recommendations = _recommendation_text(payload)
    quality_notes = list(payload.get("data_quality_notes") or [])
    quality_labels = {
        "unknown_status_count": "tickets with a missing status category",
        "missing_issue_type_count": "tickets with a missing issue type",
        "missing_squad": "tickets with no populated squad",
        "missing_assignee": "tickets with no populated assignee",
        "done_without_resolved": "Done-category tickets with no resolved timestamp",
    }
    for key, value in (payload.get("data_quality") or {}).items():
        if value and key in quality_labels:
            quality_notes.append(f"{_display_number(value)} {quality_labels[key]} are present in this scope.")
    extra_filters = [
        f"{key}={applied[key]}" for key in ("feature", "issue_type", "status", "priority")
        if applied.get(key)
    ]
    if extra_filters:
        quality_notes.append(
            "Issue-table presentation filters were retained in report scope but do not alter "
            f"the dashboard KPI aggregate: {', '.join(extra_filters)}."
        )
    quality = "\n".join(quality_notes) or "No additional dashboard data-quality note was returned."
    filters = ", ".join(f"{key}={value}" for key, value in applied.items())
    methodology = (
        f"Verified source: {calculation}, executed server-side against read-only DoraDB. "
        f"Applied scope: {filters}. Metrics use the dashboard's parameterized aggregate "
        "and deterministic attention rules. Browser-rendered metric values were not accepted "
        "as evidence. Done is an end-state category and may include rejected or cancelled work."
    )
    evidence = {
        "generated_by": "report_template",
        "evidence_type": "verified_dashboard_snapshot",
        "question": "Verified current dashboard snapshot",
        "answer": "\n".join((summary, findings, risks, recommendations, quality, methodology)),
        "query_ids": [calculation],
        "calculation_ids": [calculation],
        "row_counts": [int((payload.get("kpis") or {}).get("total_work") or 0)],
        "validation": {"valid": True, "source": "server_side_dashboard"},
        "answer_source": "server_side_dashboard",
        "generated_at": generated_at,
        "metrics": {item["key"]: item["raw_value"] for item in items},
        "attention_items": payload.get("attention_items") or [],
        "data_quality": payload.get("data_quality") or {},
        "warnings": quality_notes,
    }
    return {
        "state": "ready",
        "scope": applied,
        "generated_at": generated_at,
        "evidence": _json_safe(evidence),
        "sections": _json_safe({
            "executive_summary": {"content": summary},
            "kpi_group": {
                "payload": {
                    "state": "ready",
                    "items": items,
                    "columns": [
                        {"key": "label", "label": "Measure"},
                        {"key": "value", "label": "Value"},
                        {"key": "formula", "label": "Calculation"},
                    ],
                    "rows": items,
                }
            },
            "key_finding": {"content": findings},
            "risk": {"content": risks},
            "recommendation": {"content": recommendations},
            "action_list": {"content": recommendations},
            "data_quality": {"content": quality},
            "methodology": {"content": methodology},
        }),
    }


def weekly_scrum_feature_evidence(doradb, scope: dict[str, Any]) -> dict[str, Any]:
    """Return the Feature's own stored status for one verified squad/sprint.

    No child-ticket inference is performed. A missing scope or empty result is
    represented as a deterministic needs_input payload for the report UI.
    """

    squad = (scope.get("squad") or "").strip()
    sprint = (scope.get("sprint") or "").strip()
    if not squad or not sprint:
        return {
            "state": "needs_input",
            "reason": "Choose both a squad and sprint to retrieve Feature statuses.",
            "rows": [],
        }
    result = query_doradb(
        doradb,
        query_id="jira_weekly_scrum_feature_status",
        filters={"project_key": scope.get("project") or "DCPM", "dcpsquad": squad, "sprint": sprint},
        limit=200,
    )
    rows = [
        {
            "feature": row.get("feature_key"),
            "feature_name": row.get("feature_summary") or row.get("feature_key"),
            "status": row.get("status") or "Needs Input",
            "status_category": row.get("status_category"),
        }
        for row in result["rows"]
    ]
    if not rows:
        return {
            "state": "needs_input",
            "reason": "No Feature issues with a verified status were found for this squad and sprint.",
            "rows": [],
            "query_id": result["query_id"],
        }
    missing_status = any(row["status"] == "Needs Input" for row in rows)
    return {
        "state": "needs_input" if missing_status else "ready",
        "reason": (
            "One or more linked Features do not have an available Feature status."
            if missing_status else ""
        ),
        "columns": [
            {"key": "feature", "label": "Feature ID"},
            {"key": "feature_name", "label": "Feature Name"},
            {"key": "status", "label": "Status"},
        ],
        "rows": rows,
        "query_id": result["query_id"],
        "row_count": result["row_count"],
        "data_as_of": datetime.now(timezone.utc).isoformat(),
    }


def scope_to_question(question: str, scope: dict[str, Any]) -> str:
    """Bind a template question to the report's scope.

    A template question is written generically ("Show the current delivery
    position"), but a report is always about a specific slice. Naming the slice
    in the question is what stops the assistant asking which squad was meant --
    the same fix applied to the dashboard's Ask Zara buttons.
    """

    parts = [f"squad {scope['squad']}" if scope.get("squad") else "all squads"]
    if scope.get("sprint"):
        parts.append(f"sprint {scope['sprint']}")
    if scope.get("release"):
        parts.append(f"release {scope['release']}")
    where = f"{', '.join(parts)} in {scope.get('project') or 'DCPM'}"
    if scope.get("date_from") or scope.get("date_to"):
        where += f", between {scope.get('date_from') or 'the earliest data'} and {scope.get('date_to') or 'today'}"
    return f"For {where}: {question}"


def dashboard_context_for(scope: dict[str, Any]) -> dict[str, Any]:
    """The structured scope the agent expects alongside the question."""

    context = {
        "project": scope.get("project") or "DCPM",
        "squad": scope.get("squad") or None,
        "sprint": scope.get("sprint") or None,
        "release": scope.get("release") or None,
        "date_from": scope.get("date_from") or None,
        "date_to": scope.get("date_to") or None,
    }
    return {key: value for key, value in context.items() if value}


def run_template_questions(
    *,
    agent_factory,
    questions: list[str],
    scope: dict[str, Any],
    session_id: str,
) -> list[dict[str, Any]]:
    """Ask each question and return its answer plus structured evidence.

    One failed question does not fail the report: it is recorded and skipped,
    because a partial report with honest gaps is more useful than none.
    """

    results: list[dict[str, Any]] = []
    dashboard_context = dashboard_context_for(scope)
    project = scope.get("project") or "DCPM"

    for index, question in enumerate(questions):
        grounded = scope_to_question(question, scope)
        try:
            agent = agent_factory()
            answer = agent.chat(
                grounded,
                session_id=f"{session_id}-{index}",
                persistent_context={
                    "dashboard_context": dashboard_context,
                    "last_context": {
                        "filters": {
                            key: value
                            for key, value in (
                                ("dcpsquad", scope.get("squad")),
                                ("project_key", project),
                            )
                            if value
                        },
                        "dashboard_context": dashboard_context,
                    },
                },
                project_scope={"project_key": project},
            )
        except Exception as exc:  # noqa: BLE001 - one question must not sink the report
            logger.warning("Report question failed (%s): %s", question, exc)
            results.append({"question": grounded, "error": str(exc)[:200]})
            continue

        metadata = answer.get("metadata") or {}
        results.append(
            {
                "question": grounded,
                "answer": answer.get("answer") or "",
                # Shaped like a stored conversation message so the same
                # snapshot code handles chat-sourced and generated evidence.
                "structured_content": {
                    "chart": answer.get("chart"),
                    "table": answer.get("table"),
                    "warnings": answer.get("warnings") or [],
                    "validation": answer.get("validation") or {},
                    "query_identifiers": metadata.get("query_ids") or [],
                    "row_counts": metadata.get("row_counts") or [],
                    "knowledge_sections": metadata.get("knowledge_sections") or [],
                    "detected_intent": answer.get("intent"),
                    "source_type": metadata.get("answer_source"),
                    "metadata": {
                        "dashboard_context": dashboard_context,
                        "project_scope": {"project_key": project},
                        "generated_at": metadata.get("generated_at"),
                    },
                },
            }
        )
    return results


__all__ = [
    "current_view_dashboard_evidence", "dashboard_context_for",
    "normalize_report_scope", "run_template_questions", "scope_to_question",
    "weekly_scrum_feature_evidence",
]
