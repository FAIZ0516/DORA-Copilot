"""Authoritative DoraDB query catalogue and agent steering definitions.

The cloud model sees this metadata, never executable SQL. Python maps a
validated query ID to a static, parameterized statement in :mod:`backend.doradb`.
"""

from __future__ import annotations

from typing import Any

from .context import load_context


DEFAULT_PROJECT_KEY = "DCPM"
DATA_DICTIONARY = load_context("data_dictionary.yaml")
DISCOVERY_DIMENSIONS: dict[str, dict[str, Any]] = DATA_DICTIONARY["dimensions"]
APPROVED_QUERY_IDS = {
    "list_dimension_values",
    "database_schema_objects",
    "database_table_presence",
    "database_columns",
    "database_metric_columns",
    "database_squad_sources",
    "jira_distinct_squads",
    "jira_bug_counts_by_squad",
    "jira_issue_counts_by_status",
    "jira_unresolved_older_than_days",
    "jira_backlog_by_status",
    "jira_bug_resolution_trend",
    "jira_dashboard_kpis",
    "jira_dashboard_status_categories",
    "jira_dashboard_issue_types",
    "jira_dashboard_open_ageing",
    "jira_dashboard_data_quality",
    "jira_open_work_breakdown",
    "jira_impeded_breakdown",
    "dora_metrics_by_year",
    "dora_metrics_by_squad",
    "dora_metrics_release_detail",
    "feature_vs_release_frequency",
    "feature_vs_user_story",
    "story_to_feature_ratio",
}
DETAIL_QUERY_IDS = {
    "dora_metrics_release_detail",
    "feature_vs_release_frequency",
    "feature_vs_user_story",
    "story_to_feature_ratio",
}
LARGE_QUERY_IDS = {"feature_vs_release_frequency", "feature_vs_user_story"}
LARGE_QUERY_REQUIRED_FILTERS = {
    "dcpsquad",
    "release_date",
    "release_year",
    "fixversion",
    "release_name",
    "issuetype",
    "jira_key",
}
ALLOWED_FILTERS = {
    "release_year",
    "release_date",
    "fixversion",
    "release_name",
    "issuetype",
    "jira_key",
    "status",
    "project_key",
    "dcpsquad",
    "table_schema",
    "table_name",
    "column_search",
    "age_days",
    "ageing_bucket",
}

QUERY_CATALOGUE: dict[str, dict[str, Any]] = {
    "list_dimension_values": {
        "purpose": (
            "List the current distinct values for a governed dimension. Use for "
            "catalogue questions about projects, squads, release years, releases, "
            "issue types, statuses, or supported metrics; never use an analytical "
            "metrics query to enumerate dimension values."
        ),
        "default_limit": 100,
        "allowed_filters": ["dimension", "release_year", "project_key"],
        "required_filters": ["dimension"],
        "expected_columns": [
            "dimension",
            "value",
            "record_count",
            "total_values",
        ],
    },
    "database_schema_objects": {
        "purpose": "Visible non-system PostgreSQL tables and views from metadata.",
        "default_limit": 200,
        "allowed_filters": ["table_schema", "table_name"],
        "expected_columns": ["table_schema", "table_name", "object_type"],
    },
    "database_table_presence": {
        "purpose": "Verify whether a named PostgreSQL table or view exists.",
        "default_limit": 20,
        "allowed_filters": ["table_schema", "table_name"],
        "expected_columns": ["table_schema", "table_name", "object_type"],
    },
    "database_columns": {
        "purpose": "Visible PostgreSQL column metadata for a verified table or search term.",
        "default_limit": 200,
        "allowed_filters": ["table_schema", "table_name", "column_search"],
        "expected_columns": [
            "table_schema",
            "table_name",
            "column_name",
            "data_type",
            "is_nullable",
            "ordinal_position",
        ],
    },
    "database_metric_columns": {
        "purpose": (
            "Discover visible lead-time, LTC, cycle-time, created, and resolved "
            "columns without querying business rows."
        ),
        "default_limit": 200,
        "allowed_filters": [],
        "expected_columns": [
            "table_schema",
            "table_name",
            "column_name",
            "data_type",
        ],
    },
    "database_squad_sources": {
        "purpose": "Discover visible tables and views containing squad or team columns.",
        "default_limit": 100,
        "allowed_filters": [],
        "expected_columns": [
            "table_schema",
            "table_name",
            "column_name",
            "data_type",
        ],
    },
    "jira_distinct_squads": {
        "purpose": (
            "Distinct non-blank dcpsquad values from the verified public Jira issue "
            "table, with missing-squad row count."
        ),
        "default_limit": 100,
        "allowed_filters": ["project_key"],
        "expected_columns": ["dcpsquad", "missing_squad_rows"],
    },
    "jira_bug_counts_by_squad": {
        "purpose": "Non-sensitive Jira bug counts grouped by populated squad value.",
        "default_limit": 100,
        "allowed_filters": ["project_key"],
        "expected_columns": ["dcpsquad", "bug_count"],
    },
    "jira_issue_counts_by_status": {
        "purpose": "Non-sensitive Jira issue counts grouped by type and current status.",
        "default_limit": 100,
        "allowed_filters": ["project_key", "issuetype", "status"],
        "expected_columns": [
            "issuetype",
            "status",
            "status_category",
            "issue_count",
        ],
    },
    "jira_unresolved_older_than_days": {
        "purpose": "Unresolved Jira issue aggregates older than a bounded number of days.",
        "default_limit": 100,
        "allowed_filters": ["project_key", "age_days"],
        "expected_columns": [
            "status",
            "status_category",
            "issue_count",
            "oldest_created",
        ],
    },
    "jira_backlog_by_status": {
        "purpose": "Current unresolved Jira backlog counts grouped by status.",
        "default_limit": 100,
        "allowed_filters": ["project_key"],
        "expected_columns": ["status", "status_category", "issue_count"],
    },
    "jira_bug_resolution_trend": {
        "purpose": "Monthly Jira bug creation and resolution counts.",
        "default_limit": 120,
        "allowed_filters": ["project_key"],
        "expected_columns": ["month", "created_bug_count", "resolved_bug_count"],
    },
    "jira_dashboard_kpis": {
        "purpose": "Snapshot Jira issue, open-work, impeded, and missing-squad KPIs.",
        "default_limit": 1,
        "allowed_filters": ["project_key"],
        "expected_columns": [
            "total_issues",
            "open_work_count",
            "impeded_issues",
            "missing_squad_count",
            "missing_squad_pct",
        ],
    },
    "jira_dashboard_status_categories": {
        "purpose": "Current Jira issue counts grouped by stored status category.",
        "default_limit": 20,
        "allowed_filters": ["project_key"],
        "expected_columns": ["status_category", "issue_count"],
    },
    "jira_dashboard_issue_types": {
        "purpose": "Current Jira issue counts grouped by actual issue type.",
        "default_limit": 50,
        "allowed_filters": ["project_key"],
        "expected_columns": ["issuetype", "issue_count"],
    },
    "jira_dashboard_open_ageing": {
        "purpose": "Calendar-age buckets for Jira open work using created timestamps.",
        "default_limit": 5,
        "allowed_filters": ["project_key"],
        "expected_columns": ["ageing_bucket", "issue_count", "bucket_order"],
    },
    "jira_dashboard_data_quality": {
        "purpose": "Aggregate Jira snapshot completeness and timestamp-quality checks.",
        "default_limit": 1,
        "allowed_filters": ["project_key"],
        "expected_columns": [
            "missing_squad_count",
            "missing_assignee_count",
            "done_without_resolved_count",
            "invalid_resolution_interval_count",
        ],
    },
    "jira_open_work_breakdown": {
        "purpose": "Aggregate open Jira work by calendar age, type, priority, status category, and squad coverage.",
        "default_limit": 200,
        "allowed_filters": ["project_key", "ageing_bucket"],
        "expected_columns": [
            "ageing_bucket",
            "issuetype",
            "priority",
            "status_category",
            "squad_coverage",
            "issue_count",
        ],
    },
    "jira_impeded_breakdown": {
        "purpose": "Aggregate currently impeded Jira work by calendar age, type, priority, and squad coverage.",
        "default_limit": 200,
        "allowed_filters": ["project_key"],
        "expected_columns": [
            "ageing_bucket",
            "issuetype",
            "priority",
            "squad_coverage",
            "issue_count",
        ],
    },
    "dora_metrics_by_year": {
        "purpose": (
            "Yearly release frequency, change failure rate, lead time for change, "
            "delivery cycle time, release counts, and multi-year trends."
        ),
        "default_limit": 10,
        "allowed_filters": ["release_year", "project_key"],
        "expected_columns": [
            "release_year",
            "release_count",
            "release_frequency_months",
            "change_failure_rate_pct",
            "lead_time_for_change_months",
            "delivery_cycle_time_months",
            "user_story_count",
            "feature_reference_count",
            "feature_reference_release_count",
        ],
    },
    "dora_metrics_by_squad": {
        "purpose": (
            "Yearly DORA release metrics for releases associated with Jira "
            "issues owned by a DCPM squad such as TITAN or JAEGER."
        ),
        "default_limit": 10,
        "allowed_filters": ["release_year", "dcpsquad", "project_key"],
        "expected_columns": [
            "dcpsquad",
            "release_year",
            "release_count",
            "release_frequency_months",
            "change_failure_rate_pct",
            "lead_time_for_change_months",
            "delivery_cycle_time_months",
            "user_story_count",
            "feature_reference_count",
            "feature_reference_release_count",
        ],
    },
    "dora_metrics_release_detail": {
        "purpose": (
            "Release-level dates, outcomes, timelines, and drill-down evidence "
            "for explaining why a yearly metric changed."
        ),
        "default_limit": 50,
        "allowed_filters": [
            "release_year",
            "release_date",
            "fixversion",
            "release_name",
            "project_key",
        ],
        "expected_columns": [
            "fixversion",
            "release_year",
            "release_date",
            "release_frequency",
            "outcome_rating",
            "delivery_cycle_time",
            "ltc",
        ],
    },
    "feature_vs_release_frequency": {
        "purpose": (
            "Relate Features, User Stories, Bugs, Tasks, or Tests to major "
            "release frequency and outcomes."
        ),
        "default_limit": 50,
        "allowed_filters": sorted(ALLOWED_FILTERS),
        "requires_narrowing_filter": True,
        "expected_columns": [
            "fixversion",
            "release_year",
            "issuetype",
            "jira_key",
            "status",
            "outcome_rating",
            "release_date",
            "release_frequency_months",
        ],
    },
    "feature_vs_user_story": {
        "purpose": (
            "List Features, User Stories, Bugs, Tasks, or Tests belonging to a "
            "specific release and provide Feature Reference details."
        ),
        "default_limit": 50,
        "allowed_filters": sorted(ALLOWED_FILTERS),
        "requires_narrowing_filter": True,
        "expected_columns": [
            "release_year",
            "fixversion",
            "release_name",
            "jira_key",
            "issuetype",
            "status",
            "release_date",
        ],
    },
    "story_to_feature_ratio": {
        "purpose": (
            "User Story reference count divided by Feature reference count, "
            "grouped by release."
        ),
        "default_limit": 100,
        "allowed_filters": ["release_year", "fixversion", "release_name", "project_key"],
        "expected_columns": [
            "release_year",
            "fixversion",
            "user_story_to_feature_ratio",
            "user_story_count",
            "feature_count",
        ],
    },
}

METRIC_DEFINITIONS = {
    "release_frequency": (
        "Average number of months between releases in DoraDB. Lower means "
        "releases occur more frequently."
    ),
    "change_failure_rate": "Average outcome_rating multiplied by 100.",
    "lead_time_for_change": (
        "Elapsed time from release_actual_start to release_actual_end, in "
        "30-day months. 'Load Time' is interpreted as Lead Time."
    ),
    "delivery_cycle_time": (
        "Elapsed time from dev_insprint_actual_start to release_actual_end, in "
        "30-day months."
    ),
    "feature_reference_count": (
        "Number of Feature rows associated with releases; not necessarily "
        "globally distinct Jira Feature IDs."
    ),
    "story_to_feature_ratio": (
        "User Story reference count divided by Feature reference count for a release."
    ),
}


def planner_context() -> str:
    """Return a compact steering prompt derived from the approved catalogue."""

    routes = "\n".join(
        f"- {query_id}: {definition['purpose']} Allowed filters: "
        f"{', '.join(definition['allowed_filters'])}."
        for query_id, definition in QUERY_CATALOGUE.items()
    )
    metrics = "\n".join(f"- {name}: {definition}" for name, definition in METRIC_DEFINITIONS.items())
    return f"""Approved DoraDB query tools:
{routes}

DoraDB metric definitions:
{metrics}

Rules:
- Default project_key to DCPM.
- Use dora_metrics_by_year first for general DORA questions and comparisons.
- Use dora_metrics_by_squad when dcpsquad is present. A squad is a dimension
  inside DCPM and must never replace project_key.
- Use dora_metrics_release_detail only for release drill-down or explanations.
- feature_vs_release_frequency and feature_vs_user_story require at least one
  narrowing filter: release_year, fixversion/release_name, issuetype, or jira_key.
- Use at most two query actions: one primary query and one justified drill-down.
- A chart request is read-only and safe.
- Never produce SQL. Return only approved query IDs and structured filters."""
