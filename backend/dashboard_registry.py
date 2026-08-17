"""Authoritative Jira dashboard field mapping, metrics, and attention rules."""

from __future__ import annotations

from typing import Any


JIRA_TABLE = "public.tbl_gdt_dte_jira_issues"
RELEASE_INFO_TABLE = "public.tbl_gdt_dte_release_info"

JIRA_FIELDS = {
    "issue_id": "id",
    "issue_key": "key",
    "summary": "summary",
    "issue_type": "issuetype",
    "priority": "priority",
    "status": "status",
    "status_category": "status_category",
    "progress": "progress_pct",
    "project": "project_key",
    "squad": "dcpsquad",
    "assignee": "assignee",
    "created": "created",
    "updated": "updated",
    "resolved": "resolved",
    "release": "fixversions",
    "sprint": "sprints",
    "feature_link": "featurelink_key",
    "resolution": "resolution",
}

# These values are never treated as squads. The API reports every excluded value
# and reason instead of silently dropping it. None matched the inspected snapshot.
INVALID_SQUAD_VALUES = {
    "ALL": "generic aggregate value",
    "N/A": "not an organisational squad",
    "NONE": "missing-value placeholder",
    "NULL": "missing-value placeholder",
    "UNKNOWN": "unknown-value placeholder",
    "UNASSIGNED": "ownership state rather than a squad",
    "PLATFORM": "generic platform value without a confirmed squad mapping",
}

ATTENTION_THRESHOLDS = {
    "needs_attention": {
        "high_priority_open_bugs": 3,
        "oldest_unresolved_days": 90,
        "completion_pct_below": 50,
        "impeded_work": 1,
    },
    "monitor": {
        "high_priority_open_bugs": 1,
        "oldest_unresolved_days": 60,
        "completion_pct_below": 75,
        "unassigned_open_work": 1,
    },
}

# How each threshold reads in a sentence. Keyed by the same names as
# ATTENTION_THRESHOLDS so a new rule cannot be described without being named.
_THRESHOLD_PHRASING = {
    "high_priority_open_bugs": "open bugs at High or Highest priority reaches {value}",
    "oldest_unresolved_days": "the oldest unresolved ticket reaches {value} days old",
    "completion_pct_below": "end-state completion falls below {value}%",
    "impeded_work": "at least {value} ticket is currently Impeded",
    "unassigned_open_work": "at least {value} open ticket has no assignee",
}

_BAND_PHRASING = {
    "needs_attention": "Needs Attention (the escalation band)",
    "monitor": "Monitor (the early-warning band)",
}


def attention_rules_text() -> str:
    """Describe the dashboard's attention rules in prose, from the constants.

    The dashboard labels a squad "Needs Attention" using ATTENTION_THRESHOLDS,
    but the assistant was never shown those numbers -- so asking Zara to explain
    a risk badge produced "the material does not define any attention reasons".
    The dashboard and the assistant now describe the same rules.

    This is generated rather than written into the verified-knowledge Markdown
    on purpose. A hand-copied threshold would silently start lying the moment
    someone edited the dict, and a confidently wrong explanation is worse than
    an honest "I don't know".
    """

    lines = [
        "The dashboard assigns each squad a delivery-risk status using fixed, "
        "deterministic thresholds. This is rule-based, not a model judgement "
        "and not a confidence score. A squad is evaluated against the "
        "escalation band first; if no escalation rule is met it is checked "
        "against the early-warning band; otherwise it is Healthy.",
        "",
    ]
    for band, rules in ATTENTION_THRESHOLDS.items():
        lines.append(f"**{_BAND_PHRASING.get(band, band)}** — flagged when any of these is true:")
        for metric, value in rules.items():
            phrasing = _THRESHOLD_PHRASING.get(metric)
            lines.append(
                f"- {phrasing.format(value=value)}"
                if phrasing
                else f"- `{metric}` reaches {value}"
            )
        lines.append("")
    lines.append(
        "Each triggered rule becomes one attention reason, carrying the metric, "
        "its measured value and the threshold it crossed. A status of "
        "'Data Incomplete' means some tickets have no status category, so the "
        "squad could not be scored at all."
    )
    return "\n".join(lines).strip()


_COMMON_ROLES = ["scrum_master", "head_of_department"]

METRIC_REGISTRY: dict[str, dict[str, Any]] = {
    "total_work": {
        "title": "Total Tickets",
        "description": "All Jira tickets in the current dashboard scope.",
        "why_it_matters": "Shows the size of the visible Jira work set; issues are not equal units of effort.",
        "formula": "Count of distinct Jira issue keys in scope.",
        "data_quality_note": "This is a ticket count, not an estimate of effort, complexity, or team capacity.",
        "required_fields": ["key", "project_key"],
        "source_tables": [JIRA_TABLE],
        "supported_roles": _COMMON_ROLES,
        "suggested_questions": [
            "What makes up this work total?",
            "Show the work by issue type and status.",
            "Which part of this scope needs attention?",
        ],
    },
    "active_work": {
        "title": "Open Work",
        "description": "Tickets that are unresolved and not in Jira's Done category.",
        "why_it_matters": "Highlights the current open workload without treating ended work as active.",
        "formula": "Count where resolved is null and status_category is not Done.",
        "data_quality_note": "Resolved tickets and tickets in Jira's Done category are excluded.",
        "required_fields": ["resolved", "status_category"],
        "source_tables": [JIRA_TABLE],
        "supported_roles": _COMMON_ROLES,
        "suggested_questions": ["What is driving the current level of active work?", "Show the oldest active work.", "What should we prioritise?"],
    },
    "completed_work": {
        "title": "End-state Work",
        "description": "Issues currently classified in Jira's Done status category.",
        "why_it_matters": "Shows workflow end-state coverage, including rejected or cancelled outcomes.",
        "formula": "Count where status_category equals Done.",
        "required_fields": ["status_category", "resolution"],
        "source_tables": [JIRA_TABLE],
        "supported_roles": _COMMON_ROLES,
        "suggested_questions": ["How much Done work was cancelled or rejected?", "Show the end-state mix."],
    },
    "completion_pct": {
        "title": "Work Completed",
        "description": "Percentage of scoped tickets currently in Jira's Done category.",
        "why_it_matters": "Provides a transparent workflow-position indicator, not a productivity or success score.",
        "formula": "100 × end-state issue count ÷ total issue count.",
        "data_quality_note": "Done is a Jira workflow end state and can include rejected or cancelled outcomes.",
        "required_fields": ["status_category", "key"],
        "source_tables": [JIRA_TABLE],
        "supported_roles": _COMMON_ROLES,
        "suggested_questions": ["What is still outside Done?", "How much Done work was cancelled or rejected?", "How has ticket creation compared with resolution recently?"],
    },
    "in_progress_work": {
        "title": "In Progress",
        "description": "Issues in Jira's In Progress status category.",
        "why_it_matters": "Shows work currently positioned in active workflow states.",
        "formula": "Count where status_category equals In Progress.",
        "required_fields": ["status_category"],
        "source_tables": [JIRA_TABLE],
        "supported_roles": _COMMON_ROLES,
        "suggested_questions": ["Which in-progress work is oldest?", "Show in-progress work by priority."],
    },
    "todo_work": {
        "title": "To Do",
        "description": "Issues in Jira's To Do status category.",
        "why_it_matters": "Shows work that has not entered an active or end-state category.",
        "formula": "Count where status_category equals To Do.",
        "required_fields": ["status_category"],
        "source_tables": [JIRA_TABLE],
        "supported_roles": _COMMON_ROLES,
        "suggested_questions": ["Which To Do items are highest priority?", "Show To Do work by issue type."],
    },
    "open_bugs": {
        "title": "Open Bugs",
        "description": "Bug tickets in scope that are unresolved and not in Jira's Done category.",
        "why_it_matters": "Highlights unresolved defect work without inventing business impact or severity.",
        "formula": "Count where issuetype is Bug, resolved is null, and status_category is not Done.",
        "data_quality_note": "This reflects Jira issue type and workflow state; it does not infer defect severity or business impact.",
        "required_fields": ["issuetype", "resolved", "status_category"],
        "source_tables": [JIRA_TABLE],
        "supported_roles": _COMMON_ROLES,
        "suggested_questions": ["Which open bugs are highest priority?", "Which open bugs are oldest?", "What should we prioritise this week?"],
    },
    "high_priority_open_bugs": {
        "title": "High-priority Open Bugs",
        "description": "Open bugs whose real Jira priority is High.",
        "why_it_matters": "Surfaces urgent defect work while keeping priority distinct from severity.",
        "formula": "Open Bugs filtered where priority equals High.",
        "required_fields": ["issuetype", "priority", "resolved", "status_category"],
        "source_tables": [JIRA_TABLE],
        "supported_roles": _COMMON_ROLES,
        "suggested_questions": ["List the High-priority open bugs.", "Rank them by age and explain the factors."],
    },
    "unassigned_open_work": {
        "title": "Unassigned Open Work",
        "description": "Active Jira work with a blank or null assignee.",
        "why_it_matters": "Shows ownership gaps, while recognising that queue ownership can be valid.",
        "formula": "Active Jira Work where assignee is null or blank.",
        "required_fields": ["assignee", "resolved", "status_category"],
        "source_tables": [JIRA_TABLE],
        "supported_roles": _COMMON_ROLES,
        "suggested_questions": ["Show unassigned open work by priority.", "Which ownership gaps need review?"],
    },
    "oldest_unresolved_days": {
        "title": "Oldest Unresolved Age",
        "description": "Calendar days since the oldest unresolved issue was created.",
        "why_it_matters": "Highlights ageing work; age alone does not prove risk or cycle time.",
        "formula": "Maximum of current date minus created date for unresolved, non-Done work.",
        "required_fields": ["created", "resolved", "status_category"],
        "source_tables": [JIRA_TABLE],
        "supported_roles": _COMMON_ROLES,
        "suggested_questions": ["Show the oldest unresolved issues.", "Why are these issues still open?"],
    },
    "average_unresolved_days": {
        "title": "Average Unresolved Age",
        "description": "Average calendar age of unresolved, non-Done work.",
        "why_it_matters": "Provides ageing context without calling it engineering cycle time.",
        "formula": "Average of current date minus created date for unresolved, non-Done work with a created date.",
        "required_fields": ["created", "resolved", "status_category"],
        "source_tables": [JIRA_TABLE],
        "supported_roles": _COMMON_ROLES,
        "suggested_questions": ["Which issue types drive the average age?", "Show ageing by priority."],
    },
    "missing_squad": {
        "title": "Missing Squad",
        "description": "Issues whose DCP squad field is null or blank.",
        "why_it_matters": "Missing ownership limits squad comparison coverage.",
        "formula": "Count where dcpsquad is null or blank.",
        "required_fields": ["dcpsquad"],
        "source_tables": [JIRA_TABLE],
        "supported_roles": ["head_of_department"],
        "suggested_questions": ["How does missing squad data affect this dashboard?", "Which work types have missing squad coverage?"],
    },
    "squads_requiring_attention": {
        "title": "Squads Requiring Attention",
        "description": "Squads matching one or more transparent attention thresholds.",
        "why_it_matters": "Focuses review on observable delivery conditions rather than AI confidence.",
        "formula": "Deterministic rules using High-priority open bugs, unresolved age, end-state percentage, and current impeded work.",
        "required_fields": ["dcpsquad", "priority", "created", "status", "status_category"],
        "source_tables": [JIRA_TABLE],
        "supported_roles": ["head_of_department"],
        "suggested_questions": ["Which squad should I investigate first?", "Explain every attention reason."],
    },
}

UNSUPPORTED_METRICS = {
    "story_point_velocity": ["story_points", "sprint commitment history"],
    "true_sprint_commitment": ["scope-at-commitment history"],
    "test_pass_rate": ["test execution outcome", "execution timestamp"],
    "due_date_compliance": ["due_date"],
    "severity": ["severity"],
    "capacity_utilisation": ["team capacity", "effort"],
    "mttr": ["incident start", "service restoration timestamp"],
}


def public_metric_registry() -> dict[str, dict[str, Any]]:
    """Return JSON-safe registry content without sharing mutable global objects."""

    return {key: dict(value) for key, value in METRIC_REGISTRY.items()}


__all__ = [
    "ATTENTION_THRESHOLDS",
    "attention_rules_text",
    "INVALID_SQUAD_VALUES",
    "JIRA_FIELDS",
    "JIRA_TABLE",
    "METRIC_REGISTRY",
    "RELEASE_INFO_TABLE",
    "UNSUPPORTED_METRICS",
    "public_metric_registry",
]
