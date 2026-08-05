"""Deterministic routing for Jira knowledge, metadata, and safe data requests."""

from __future__ import annotations

import re

from ..config import settings
from ..doradb_catalog import QUERY_CATALOGUE
from .state import AgentPlan, QueryAction


DATABASE_METADATA = "DATABASE_METADATA"
KNOWLEDGE_EXPLANATION = "KNOWLEDGE_EXPLANATION"
DATA_RETRIEVAL = "DATA_RETRIEVAL"
ANALYSIS = "ANALYSIS"
CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"


def _action(
    query_id: str,
    *,
    filters: dict[str, object] | None = None,
    reason: str,
) -> QueryAction:
    return {
        "query_id": query_id,
        "filters": {
            "project_key": settings.doradb_project_key,
            **(filters or {}),
        },
        "limit": int(QUERY_CATALOGUE[query_id]["default_limit"]),
        "reason": reason,
    }


def _plan(
    *,
    mode: str,
    intent: str,
    reason: str,
    actions: list[QueryAction] | None = None,
    clarification: str = "",
) -> AgentPlan:
    return {
        "mode": mode,  # type: ignore[typeddict-item]
        "intent": intent,
        "confidence": 1.0,
        "actions": actions or [],
        "reason": reason,
        "clarification": clarification,
    }


def _jira_table_filters() -> dict[str, object]:
    return {"table_schema": "public", "table_name": "tbl_gdt_dte_jira_issues"}


def _column_search(message: str) -> str | None:
    lowered = message.lower()
    known = {
        "story point": "story",
        "lead time": "lead",
        "status category": "status_category",
        "squad": "squad",
    }
    for phrase, search in known.items():
        if phrase in lowered:
            return search
    backtick = re.search(r"`([a-z_][a-z0-9_]*)`", lowered)
    if backtick:
        return backtick.group(1)
    match = re.search(
        r"\b(?:contain|contains|have|has|include|includes)\s+(?:a\s+|an\s+|the\s+)?"
        r"([a-z][a-z0-9_ ]{1,40}?)(?:\s+column)?[?.!]*$",
        lowered,
    )
    if match:
        return re.sub(r"\s+", "_", match.group(1).strip())
    return None


def route_jira_request(message: str) -> AgentPlan | None:
    """Return a governed Jira route before the general DORA planner runs."""

    lowered = " ".join(message.lower().split())

    if "current jira issue composition" in lowered:
        return _plan(
            mode="data",
            intent=DATA_RETRIEVAL,
            reason="Aggregate current Jira composition by type and workflow state.",
            actions=[_action("jira_issue_counts_by_status", reason="Return issue-type and status-category counts.")],
        )

    if "current open jira work" in lowered:
        return _plan(
            mode="data",
            intent=ANALYSIS,
            reason="Aggregate open Jira work across the requested safe dimensions.",
            actions=[_action("jira_open_work_breakdown", reason="Return age, type, priority, status, and squad-coverage aggregates.")],
        )

    if "currently impeded jira issues" in lowered:
        return _plan(
            mode="data",
            intent=ANALYSIS,
            reason="Aggregate current impeded work without issue text or identities.",
            actions=[_action("jira_impeded_breakdown", reason="Return priority, age, type, and squad-coverage aggregates.")],
        )

    issue_type_match = re.search(r"issuetype is ['\"]([^'\"]{1,80})['\"]", message, re.I)
    if issue_type_match:
        return _plan(
            mode="data",
            intent=DATA_RETRIEVAL,
            reason="Use the selected dashboard issue type as an approved aggregate filter.",
            actions=[_action(
                "jira_issue_counts_by_status",
                filters={"issuetype": issue_type_match.group(1)},
                reason="Return current status counts for the selected issue type.",
            )],
        )

    age_bucket_match = re.search(r"open jira issues aged ['\"]([^'\"]+)['\"]", message, re.I)
    allowed_age_buckets = {
        "Less than 30 days", "30-60 days", "61-90 days",
        "More than 90 days", "Unknown created date",
    }
    if age_bucket_match and age_bucket_match.group(1) in allowed_age_buckets:
        return _plan(
            mode="data",
            intent=ANALYSIS,
            reason="Use the selected calendar-age bucket without treating it as cycle time.",
            actions=[_action(
                "jira_open_work_breakdown",
                filters={"ageing_bucket": age_bucket_match.group(1)},
                reason="Return safe aggregates for the selected open-work age bucket.",
            )],
        )

    if "impact of missing squad mappings" in lowered:
        return _plan(
            mode="conversation",
            intent=KNOWLEDGE_EXPLANATION,
            reason="Explain the verified reporting limitation without querying identities.",
        )

    if re.search(r"\b(which|what)\b.*\bsquad\b.*\b(most|highest)\b.*\bbugs?\b", lowered):
        return _plan(
            mode="data",
            intent=ANALYSIS,
            reason="Rank populated Jira squads using aggregate bug counts.",
            actions=[
                _action(
                    "jira_bug_counts_by_squad",
                    reason="The previous squad list cannot answer a bug ranking.",
                )
            ],
        )

    if re.search(
        r"\b(list|show|what|which|tell)\b.*\b(available\s+)?(squads?|teams?)\b",
        lowered,
    ):
        return _plan(
            mode="data",
            intent=DATA_RETRIEVAL,
            reason="Retrieve verified squad sources and distinct populated Jira squads.",
            actions=[
                _action(
                    "database_squad_sources",
                    reason="Inspect visible schema sources containing squad fields.",
                ),
                _action(
                    "jira_distinct_squads",
                    reason="Use the verified Jira squad field as the documented fallback.",
                ),
            ],
        )

    if re.search(r"\b(what|which|list|show)\b.*\btables?\b.*\b(database|exist|available)\b", lowered) or re.search(
        r"\bwhat tables (?:are|exist)\b", lowered
    ):
        return _plan(
            mode="data",
            intent=DATABASE_METADATA,
            reason="Inspect visible PostgreSQL schema objects.",
            actions=[
                _action(
                    "database_schema_objects",
                    reason="List visible non-system tables and views from metadata.",
                )
            ],
        )

    if "lead time" in lowered and re.search(
        r"\b(which table|what table|where|stored|column|field)\b", lowered
    ):
        return _plan(
            mode="data",
            intent=DATABASE_METADATA,
            reason="Verify candidate lead-time fields without running a DORA metric query.",
            actions=[
                _action(
                    "database_metric_columns",
                    reason="Discover lead, LTC, cycle, created, and resolved fields.",
                )
            ],
        )

    asks_columns = bool(
        re.search(r"\b(columns?|fields?|schema)\b", lowered)
        or re.search(r"\b(?:contain|contains|have|has|include|includes)\b", lowered)
    )
    if asks_columns and ("jira" in lowered or "this table" in lowered):
        filters = _jira_table_filters()
        search = _column_search(message)
        if search:
            filters["column_search"] = search
            actions = [
                _action(
                    "database_table_presence",
                    filters=_jira_table_filters(),
                    reason="Verify that the documented Jira table exists.",
                ),
                _action(
                    "database_columns",
                    filters=filters,
                    reason="Verify the requested column against live metadata.",
                ),
            ]
        else:
            actions = [
                _action(
                    "database_columns",
                    filters=filters,
                    reason="List the Jira table columns from live metadata.",
                )
            ]
        return _plan(
            mode="data",
            intent=DATABASE_METADATA,
            reason="Use live metadata and verified Jira documentation.",
            actions=actions,
        )

    if re.search(r"\bcount\b.*\bbugs?\b.*\bstatus", lowered):
        return _plan(
            mode="data",
            intent=DATA_RETRIEVAL,
            reason="Count Jira bugs by current status using an aggregate query.",
            actions=[
                _action(
                    "jira_issue_counts_by_status",
                    filters={"issuetype": "Bug"},
                    reason="Return non-sensitive aggregate bug counts by status.",
                )
            ],
        )

    age_match = re.search(r"\b(?:older than|over)\s+(\d{1,4})\s+days?\b", lowered)
    if "unresolved" in lowered and age_match:
        return _plan(
            mode="data",
            intent=DATA_RETRIEVAL,
            reason="Aggregate unresolved Jira issues older than the requested age.",
            actions=[
                _action(
                    "jira_unresolved_older_than_days",
                    filters={"age_days": int(age_match.group(1))},
                    reason="Return status aggregates without issue text or identities.",
                )
            ],
        )

    if re.search(r"\b(status|statuses)\b.*\b(biggest|largest|most)\b.*\b(backlog|open)", lowered) or re.search(
        r"\b(biggest|largest)\b.*\bbacklog\b", lowered
    ):
        return _plan(
            mode="data",
            intent=ANALYSIS,
            reason="Retrieve unresolved backlog counts before analysis.",
            actions=[
                _action(
                    "jira_backlog_by_status",
                    reason="Aggregate unresolved work by current status.",
                )
            ],
        )

    if "bug" in lowered and "resolution" in lowered and re.search(
        r"\b(trend|over time|monthly|yearly)\b", lowered
    ):
        return _plan(
            mode="data",
            intent=ANALYSIS,
            reason="Retrieve monthly bug arrival and resolution aggregates first.",
            actions=[
                _action(
                    "jira_bug_resolution_trend",
                    reason="Return non-sensitive monthly bug counts.",
                )
            ],
        )

    if (
        "jira" in lowered
        and re.search(r"\b(what is|what does|explain|difference|mean|calculate)\b", lowered)
    ) or "status_category" in lowered or (
        "status" in lowered and "resolution" in lowered
    ):
        return _plan(
            mode="conversation",
            intent=KNOWLEDGE_EXPLANATION,
            reason="Answer from the verified Jira knowledge document.",
        )

    if "story point" in lowered:
        return _plan(
            mode="data",
            intent=DATABASE_METADATA,
            reason="Verify the unsupported field against table and column metadata.",
            actions=[
                _action(
                    "database_table_presence",
                    filters=_jira_table_filters(),
                    reason="Verify that the Jira table exists.",
                ),
                _action(
                    "database_columns",
                    filters={**_jira_table_filters(), "column_search": "story"},
                    reason="Check whether any story-point column is present.",
                ),
            ],
        )

    if "lead time" in lowered and "jira" in lowered:
        return _plan(
            mode="conversation",
            intent=KNOWLEDGE_EXPLANATION,
            reason="Explain verified Jira resolution-duration limitations.",
        )

    ambiguous = re.fullmatch(
        r"(?:what is |show |calculate |analyse |analyze )?"
        r"(lead time|completed|successful release|productivity|blocked)[?.!]*",
        lowered,
    )
    if ambiguous:
        return _plan(
            mode="clarification",
            intent=CLARIFICATION_REQUIRED,
            reason="The requested business term has multiple incompatible meanings.",
            clarification=(
                "Which definition and data scope should I use? For example, Jira "
                "issue-resolution duration and DORA Lead Time for Changes require "
                "different evidence."
            ),
        )

    return None


__all__ = [
    "ANALYSIS",
    "CLARIFICATION_REQUIRED",
    "DATABASE_METADATA",
    "DATA_RETRIEVAL",
    "KNOWLEDGE_EXPLANATION",
    "route_jira_request",
]
