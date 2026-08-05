from datetime import datetime, timezone
from unittest.mock import patch

from backend.dashboard_service import (
    DashboardAggregateCache,
    _load_dashboard,
)
from backend.agent_system.request_router import route_jira_request
from backend.doradb import _build_statement


def test_dashboard_queries_use_explicit_safe_aggregate_columns():
    query_ids = [
        "jira_dashboard_kpis",
        "jira_dashboard_status_categories",
        "jira_dashboard_issue_types",
        "jira_dashboard_open_ageing",
        "jira_dashboard_data_quality",
    ]
    sensitive = {"summary", "reporter", "root_cause", "how_to_fix"}
    for query_id in query_ids:
        statement, params = _build_statement(query_id, {"project_key": "DCPM"}, 50)
        assert "SELECT *" not in statement
        assert not any(field in statement.lower() for field in sensitive)
        assert params["project_key"] == "DCPM"


def test_missing_squad_percentage_uses_total_issue_denominator_safely():
    statement, _ = _build_statement(
        "jira_dashboard_kpis", {"project_key": "DCPM"}, 1
    )
    compact = " ".join(statement.split())
    assert "100.0 * COUNT(*) FILTER" in compact
    assert "/ NULLIF(COUNT(*), 0)" in compact


def test_open_age_buckets_are_mutually_exclusive_and_calendar_based():
    statement, _ = _build_statement(
        "jira_dashboard_open_ageing", {"project_key": "DCPM"}, 5
    )
    assert "< 30" in statement
    assert "BETWEEN 30 AND 60" in statement
    assert "BETWEEN 61 AND 90" in statement
    assert "resolved IS NULL" in statement
    assert "cycle" not in statement.lower()
    assert "lead time" not in statement.lower()


def test_dashboard_cache_is_project_scoped_and_refresh_bypasses_cache():
    cache = DashboardAggregateCache(ttl_seconds=60)
    calls = []

    def loader():
        calls.append(len(calls) + 1)
        return {"value": calls[-1]}

    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    assert cache.get("DCPM", loader, now=now)["cached"] is False
    assert cache.get("DCPM", loader, now=now)["cached"] is True
    assert cache.get("DCPM", loader, refresh=True, now=now)["value"] == 2
    assert cache.get("OTHER", loader, now=now)["value"] == 3
    assert len(calls) == 3


def test_dashboard_payload_has_safe_counts_and_required_limit_notes():
    side_effect = [
        [{
            "total_issues": 100,
            "open_work_count": 30,
            "impeded_issues": 4,
            "missing_squad_count": 25,
            "missing_squad_pct": 25.0,
        }],
        [{"status_category": "Done", "issue_count": 70}],
        [{"issuetype": "Bug", "issue_count": 20}],
        [{"ageing_bucket": "30-60 days", "issue_count": 8, "bucket_order": 2}],
        [{
            "missing_squad_count": 25,
            "missing_assignee_count": 10,
            "done_without_resolved_count": 3,
            "invalid_resolution_interval_count": 2,
        }],
    ]
    with patch("backend.dashboard_service._rows", side_effect=side_effect):
        payload = _load_dashboard(object(), "DCPM")  # type: ignore[arg-type]

    assert payload["kpis"]["missing_squad_pct"] == 25.0
    serialized = str(payload).lower()
    assert "successful delivery" in serialized and "does not mean" in serialized
    assert "not cycle time or dora lead time" in serialized
    for field in ["summary", "reporter", "assignee_name", "root_cause", "how_to_fix"]:
        assert field not in serialized


def test_zero_total_is_a_valid_dashboard_empty_state():
    with patch("backend.dashboard_service._rows", side_effect=[[], [], [], [], []]):
        payload = _load_dashboard(object(), "DCPM")  # type: ignore[arg-type]
    assert payload["empty"] is True
    assert payload["kpis"]["total_issues"] == 0


def test_dashboard_drill_down_prompts_route_to_matching_safe_aggregates():
    cases = {
        "Explain the current Jira issue composition by issue type and status category.": "jira_issue_counts_by_status",
        "Analyse the current open Jira work by age, issue type, priority and squad coverage.": "jira_open_work_breakdown",
        "Analyse currently impeded Jira issues by priority, age and squad coverage without exposing sensitive issue details.": "jira_impeded_breakdown",
        "Analyse current Jira issues where issuetype is 'Bug'.": "jira_issue_counts_by_status",
        "Analyse open Jira issues aged '30-60 days' and summarise their status, priority and ownership coverage.": "jira_open_work_breakdown",
    }
    for question, query_id in cases.items():
        plan = route_jira_request(question)
        assert plan is not None
        assert plan["actions"][0]["query_id"] == query_id

    missing_squad = route_jira_request(
        "Explain the impact of missing squad mappings on team-level reporting."
    )
    assert missing_squad is not None
    assert missing_squad["mode"] == "conversation"
    assert missing_squad["actions"] == []
