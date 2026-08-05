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
    "status",
}
ALLOWED_FILTERS = {
    "dimension",
    "release_year",
    "release_date",
    "fixversion",
    "release_name",
    "issuetype",
    "jira_key",
    "status",
    "project_key",
    "dcpsquad",
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
            "summary",
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
            "summary",
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
    dimensions = "\n".join(
        f"- {name} ({definition['label']}): {definition['meaning']}"
        for name, definition in DISCOVERY_DIMENSIONS.items()
    )
    entities = "\n".join(
        f"- {entity}: {definition['grain']} Important fields: "
        + "; ".join(
            f"{field} = {meaning}"
            for field, meaning in definition.get("important_fields", {}).items()
        )
        for entity, definition in DATA_DICTIONARY["entities"].items()
    )
    return f"""Approved DoraDB query tools:
{routes}

DoraDB discoverable dimensions:
{dimensions}

DoraDB entity semantics:
{entities}

DoraDB metric definitions:
{metrics}

Rules:
- Default project_key to DCPM.
- Use list_dimension_values for requests that ask what values exist, what is
  available, or to list/count projects, squads, release years, releases,
  issue types, statuses, or supported metrics. Set its dimension filter to one
  of: {", ".join(DISCOVERY_DIMENSIONS)}.
- Use dora_metrics_by_year first for general DORA questions and comparisons.
- Use dora_metrics_by_squad when dcpsquad is present. A squad is a dimension
  inside DCPM and must never replace project_key.
- Use dora_metrics_release_detail only for release drill-down or explanations.
- feature_vs_release_frequency and feature_vs_user_story require at least one
  narrowing filter: release_year, fixversion/release_name, issuetype, or jira_key.
- Use at most two query actions: one primary query and one justified drill-down.
- A chart request is read-only and safe.
- Never produce SQL. Return only approved query IDs and structured filters."""
