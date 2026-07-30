import pytest

from backend.doradb import DoraDbQueryRejected, query_doradb
from backend.doradb_agent import _local_plan, _make_chart


def test_general_metric_question_routes_to_yearly_allowlist() -> None:
    plan = _local_plan("Compare Change Failure Rate between 2025 and 2026")
    assert plan["mode"] == "data"
    assert plan["actions"][0]["query_id"] == "dora_metrics_by_year"
    assert plan["actions"][0]["filters"]["release_year"] == [2025, 2026]
    assert plan["actions"][0]["filters"]["project_key"] == "DCPM"


def test_large_feature_query_requires_a_narrowing_filter() -> None:
    plan = _local_plan("Which issues are included in releases?")
    assert plan["mode"] == "clarification"
    assert not plan["actions"]


def test_story_to_feature_ratio_routes_to_approved_query() -> None:
    plan = _local_plan("Show the User Story-to-Feature ratio for release 4.1.0")
    assert plan["actions"][0]["query_id"] == "story_to_feature_ratio"
    assert plan["actions"][0]["filters"]["fixversion"] == "4.1.0"


def test_unknown_query_id_is_rejected_before_database_execution() -> None:
    with pytest.raises(DoraDbQueryRejected):
        query_doradb(  # type: ignore[arg-type]
            None,
            query_id="generated_sql",
            filters={},
            limit=10,
        )


def test_yearly_failure_rate_generates_a_valid_chart() -> None:
    results = [
        {
            "query_id": "dora_metrics_by_year",
            "rows": [
                {"release_year": 2025, "change_failure_rate_pct": 12.5},
                {"release_year": 2026, "change_failure_rate_pct": 9.25},
            ],
        }
    ]
    chart = _make_chart(results, "Create a chart of Change Failure Rate by year")
    assert chart is not None
    assert chart["labels"] == ["2025", "2026"]
    assert chart["values"] == [12.5, 9.25]
    assert chart["unit"] == "%"
