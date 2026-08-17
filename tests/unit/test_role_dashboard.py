from unittest.mock import patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from backend.dashboard_registry import METRIC_REGISTRY, UNSUPPORTED_METRICS
from backend.agent.request_router import route_jira_request
from backend.database.doradb import _build_statement, _normalize_filters
from backend.dashboard_service import (
    UnknownSquadError,
    _aggregate_statement,
    _attention,
    _scope_sql,
    get_dashboard_issues,
    get_dashboard_filter_options,
    get_dashboard_squads,
    get_portfolio_dashboard,
)


def test_dashboard_filter_options_include_live_ticket_dimensions():
    rows = [
        [{"value": "4.3.0", "issue_count": 2}],
        [{"value": "TITAN Sprint 1", "issue_count": 2}],
        [{"minimum": "2026-01-01", "maximum": "2026-08-01"}],
        [{"value": "Bug", "issue_count": 2}],
        [{"value": "In Progress", "issue_count": 1}],
        [{"value": "High", "issue_count": 1}],
        [{"value": "Alex", "issue_count": 1}],
    ]
    with patch("backend.dashboard_service._execute_rows", side_effect=rows) as execute:
        payload = get_dashboard_filter_options(
            object(), project="dcpm", squad="TITAN"  # type: ignore[arg-type]
        )

    assert payload["issue_filters"] == {
        "issue_types": rows[3],
        "statuses": rows[4],
        "priorities": rows[5],
        "assignees": rows[6],
    }
    assert len(execute.call_args_list) == 7
    assert all(call.args[2]["squad"] == "TITAN" for call in execute.call_args_list)


def test_squad_list_excludes_only_documented_generic_values():
    rows = [
        {"name": "  TITAN  ", "issue_count": 10},
        {"name": "Unknown", "issue_count": 3},
        {"name": "JAEGER", "issue_count": 5},
    ]
    with patch("backend.dashboard_service._execute_rows", return_value=rows):
        payload = get_dashboard_squads(object(), project="dcpm")  # type: ignore[arg-type]
    assert [item["name"] for item in payload["squads"]] == ["TITAN", "JAEGER"]
    assert payload["excluded_values"] == [
        {"value": "Unknown", "reason": "unknown-value placeholder"}
    ]
    assert "documented" in payload["validation_rule"]


def test_dashboard_scope_filters_are_parameterized_and_use_real_fields():
    clauses, params = _scope_sql(
        project="DCPM",
        squad="TITAN' OR TRUE --",
        release="4.3.0' OR TRUE --",
        sprint="TITAN R19 SPRINT 4",
    )
    sql = " ".join(clauses)
    assert ":squad" in sql and ":release" in sql and ":sprint" in sql
    assert "TITAN' OR TRUE" not in sql and "4.3.0' OR TRUE" not in sql
    assert params["squad"] == "TITAN' OR TRUE --"
    assert "fixversions" in sql and "sprints" in sql


def test_portfolio_metrics_retain_project_and_filter_scope():
    aggregate = {
        "total_work": 10,
        "completed_work": 6,
        "completion_pct": 60,
        "active_work": 4,
        "open_bugs": 2,
        "high_priority_open_bugs": 0,
    }
    squad = {**aggregate, "squad": "TITAN", "oldest_unresolved_days": 10}
    quality = {"missing_squad": 1, "missing_assignee": 2, "done_without_resolved": 0}
    with patch(
        "backend.dashboard_service._execute_rows",
        side_effect=[[aggregate], [squad], [quality]],
    ) as execute:
        payload = get_portfolio_dashboard(
            object(), project="DCPM", release="4.3.0"  # type: ignore[arg-type]
        )
    assert payload["applied_filters"]["project"] == "DCPM"
    assert payload["applied_filters"]["release"] == "4.3.0"
    assert payload["kpis"]["total_work"] == 10
    assert all(call.args[2]["project"] == "DCPM" for call in execute.call_args_list)
    assert all(call.args[2]["release"] == "4.3.0" for call in execute.call_args_list)


def test_primary_metric_registry_uses_friendly_labels_without_changing_formulas():
    assert METRIC_REGISTRY["total_work"]["title"] == "Total Tickets"
    assert METRIC_REGISTRY["active_work"]["title"] == "Open Work"
    assert METRIC_REGISTRY["completion_pct"]["title"] == "Work Completed"
    assert METRIC_REGISTRY["open_bugs"]["title"] == "Open Bugs"
    assert METRIC_REGISTRY["active_work"]["formula"] == (
        "Count where resolved is null and status_category is not Done."
    )
    assert METRIC_REGISTRY["completion_pct"]["formula"] == (
        "100 × end-state issue count ÷ total issue count."
    )


def test_open_bugs_exclude_done_and_age_ignores_null_created_dates():
    sql = _aggregate_statement("j.project_key = :project", group_by_squad=False)
    compact = " ".join(sql.split())
    assert "LOWER(COALESCE(j.issuetype, '')) = 'bug'" in compact
    assert "j.resolved IS NULL" in compact
    assert "COALESCE(j.status_category, '') <> 'Done'" in compact
    assert "j.created IS NOT NULL" in compact
    assert "MAX(CURRENT_DATE - j.created::date)" in compact
    assert "UPPER(COALESCE(j.status, '')) = 'IMPEDED'" in compact
    assert "issuelinks" not in compact.lower()


def test_squad_scope_and_invalid_squad_are_distinct_conditions():
    clauses, params = _scope_sql(project="DCPM", squad="TITAN")
    assert any("dcpsquad" in clause for clause in clauses)
    assert params["squad"] == "TITAN"
    with patch(
        "backend.dashboard_service.get_dashboard_squads",
        return_value={"squads": []},
    ):
        with pytest.raises(UnknownSquadError):
            get_dashboard_issues(
                object(), project="DCPM", squad="MISSING"  # type: ignore[arg-type]
            )


def test_database_failure_does_not_produce_fake_zero_values():
    with patch(
        "backend.dashboard_service._execute_rows",
        side_effect=SQLAlchemyError("offline"),
    ):
        with pytest.raises(SQLAlchemyError):
            get_dashboard_squads(object(), project="DCPM")  # type: ignore[arg-type]


def test_attention_status_is_deterministic_and_not_ai_confidence():
    result = _attention(
        {
            "total_work": 10,
            "completion_pct": 40,
            "high_priority_open_bugs": 3,
            "oldest_unresolved_days": 100,
            "impeded_work": 0,
            "unassigned_open_work": 0,
            "unknown_status_count": 0,
        }
    )
    assert result["status"] == "Needs Attention"
    assert {reason["metric"] for reason in result["reasons"]} >= {
        "completion_pct",
        "high_priority_open_bugs",
        "oldest_unresolved_days",
    }


def test_unsupported_metrics_are_not_exposed_as_supported_registry_entries():
    assert "test_pass_rate" in UNSUPPORTED_METRICS
    assert "story_point_velocity" in UNSUPPORTED_METRICS
    assert not set(UNSUPPORTED_METRICS) & set(METRIC_REGISTRY)


def test_bug_prioritisation_routes_to_bounded_issue_key_evidence():
    plan = route_jira_request("Which open bugs are highest priority and oldest?")
    assert plan is not None
    assert plan["actions"][0]["query_id"] == "jira_prioritized_open_bugs"
    assert plan["actions"][0]["limit"] == 25


def test_prioritized_bug_query_binds_squad_release_and_sprint_context():
    filters = _normalize_filters(
        "jira_prioritized_open_bugs",
        {
            "project_key": "DCPM",
            "dcpsquad": "Droid Spark",
            "fixversion": "4.3.0",
            "sprint": "Droid Spark R13 Sprint 2",
        },
    )
    statement, params = _build_statement("jira_prioritized_open_bugs", filters, 25)
    assert "Droid Spark" not in statement and "4.3.0" not in statement
    assert params["dashboard_dcpsquad"] == "DROID SPARK"
    assert params["dashboard_fixversion"] == "4.3.0"
    assert params["dashboard_sprint"] == "Droid Spark R13 Sprint 2"
    assert "approved.jira_key" in statement
    for sensitive in ["summary", "reporter", "assignee", "root_cause", "how_to_fix"]:
        assert sensitive not in statement.lower()
