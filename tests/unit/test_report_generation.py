"""Template questions are fixed; the answers come from live data.

That is what makes a template reproducible -- the same report next week asks
the same things and reports whatever the data says then.
"""

from __future__ import annotations

import json
from decimal import Decimal

from backend.services.report_generation import (
    current_view_dashboard_evidence,
    dashboard_context_for,
    normalize_report_scope,
    run_template_questions,
    scope_to_question,
    weekly_scrum_feature_evidence,
)
from backend.schemas import ReportScope
from backend.services.report_templates import TEMPLATES, questions_for_template


class _Agent:
    """Stand-in for the governed agent."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.asked: list[str] = []
        self._fail_on = fail_on

    def chat(self, message, *, session_id, persistent_context=None, project_scope=None):
        self.asked.append(message)
        if self._fail_on and self._fail_on in message:
            raise RuntimeError("provider exploded")
        return {
            "answer": "MBK completed 812 of 1,876 tickets.",
            "chart": {"type": "bar", "title": "Status", "series": [], "data": []},
            "table": None,
            "warnings": ["Done is an end state."],
            "validation": {"valid": True},
            "intent": "ANALYSIS",
            "metadata": {
                "query_ids": ["jira_dashboard_kpis"],
                "row_counts": [1],
                "knowledge_sections": ["Squad"],
                "answer_source": "deepseek",
                "generated_at": "2026-08-13T09:00:00+00:00",
            },
        }


SCOPE = {"project": "DCPM", "squad": "MBK"}


def test_every_non_blank_template_ships_standard_questions() -> None:
    for key in TEMPLATES:
        questions = questions_for_template(key)
        if key == "blank":
            assert questions == []
        else:
            assert questions, f"{key} has no standard questions"
            assert all(q.endswith("?") or q.endswith(".") for q in questions), key


def test_a_question_is_bound_to_the_reports_scope() -> None:
    # A generic template question would otherwise make the assistant ask which
    # squad was meant -- the same deixis problem as the dashboard buttons.
    grounded = scope_to_question("Show the current delivery position.", SCOPE)
    assert "squad MBK" in grounded
    assert "DCPM" in grounded
    assert grounded.endswith("Show the current delivery position.")


def test_an_unscoped_report_says_all_squads_rather_than_nothing() -> None:
    grounded = scope_to_question("Show the position.", {"project": "DCPM"})
    assert "all squads in DCPM" in grounded


def test_dates_and_extra_filters_are_carried_into_the_question() -> None:
    grounded = scope_to_question(
        "Show it.",
        {"project": "DCPM", "squad": "MBK", "sprint": "S4", "date_from": "2026-08-01"},
    )
    assert "sprint S4" in grounded
    assert "2026-08-01" in grounded


def test_dashboard_context_drops_empty_values() -> None:
    context = dashboard_context_for({"project": "DCPM", "squad": "", "release": None})
    assert context == {"project": "DCPM"}


def test_each_answer_is_shaped_like_stored_evidence() -> None:
    agent = _Agent()
    results = run_template_questions(
        agent_factory=lambda: agent,
        questions=["Show the position.", "What is at risk?"],
        scope=SCOPE,
        session_id="report-1",
    )
    assert len(results) == 2
    assert all("squad MBK" in item["question"] for item in results)
    structured = results[0]["structured_content"]
    # Same shape as a conversation message, so one snapshot path handles both.
    assert structured["query_identifiers"] == ["jira_dashboard_kpis"]
    assert structured["row_counts"] == [1]
    assert structured["warnings"] == ["Done is an end state."]
    assert structured["metadata"]["dashboard_context"]["squad"] == "MBK"


def test_one_failed_question_does_not_sink_the_whole_report() -> None:
    # A partial report with an honest gap is more useful than none at all.
    agent = _Agent(fail_on="What is at risk")
    results = run_template_questions(
        agent_factory=lambda: agent,
        questions=["Show the position.", "What is at risk?"],
        scope=SCOPE,
        session_id="report-2",
    )
    assert len(results) == 2
    assert "error" in results[1]
    assert "answer" in results[0]


def test_each_question_gets_its_own_session_so_answers_do_not_bleed() -> None:
    agent = _Agent()
    run_template_questions(
        agent_factory=lambda: agent,
        questions=["One.", "Two."],
        scope=SCOPE,
        session_id="report-3",
    )
    assert len(agent.asked) == 2
    assert agent.asked[0] != agent.asked[1]


def test_weekly_scrum_template_has_the_fixed_mvp_sections() -> None:
    types = [item["type"] for item in TEMPLATES["weekly_scrum"]["sections"]]
    assert types == [
        "kpi_group", "feature_status", "executive_summary", "key_finding", "risk",
        "action_list", "data_quality",
    ]


def test_feature_status_requires_verified_squad_and_sprint() -> None:
    result = weekly_scrum_feature_evidence(None, {"project": "DCPM", "squad": "MBK"})
    assert result["state"] == "needs_input"
    assert result["rows"] == []


def test_feature_status_preserves_real_stored_status(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.services.report_generation.query_doradb",
        lambda *_args, **_kwargs: {
            "query_id": "jira_weekly_scrum_feature_status", "row_count": 1,
            "rows": [{"feature_key": "DCPM-42", "feature_summary": "Payments upgrade", "status": "READY FOR TEST", "status_category": "In Progress"}],
        },
    )
    result = weekly_scrum_feature_evidence(object(), {"project": "DCPM", "squad": "MBK", "sprint": "Sprint 24"})
    assert result["state"] == "ready"
    assert result["rows"] == [{"feature": "DCPM-42", "feature_name": "Payments upgrade", "status": "READY FOR TEST", "status_category": "In Progress"}]
    assert [column["label"] for column in result["columns"]] == ["Feature ID", "Feature Name", "Status"]


def test_feature_status_falls_back_to_key_when_summary_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.services.report_generation.query_doradb",
        lambda *_args, **_kwargs: {
            "query_id": "jira_weekly_scrum_feature_status", "row_count": 1,
            "rows": [{"feature_key": "DCPM-77", "feature_summary": None, "status": "In Development", "status_category": "In Progress"}],
        },
    )
    result = weekly_scrum_feature_evidence(object(), {"project": "DCPM", "squad": "KAIJU", "sprint": "Sprint 24"})
    assert result["rows"][0]["feature_name"] == "DCPM-77"
    assert result["rows"][0]["status"] == "In Development"


def _dashboard_payload() -> dict:
    return {
        "view": "squad_detail",
        "squad": "JAEGER",
        "applied_filters": {"project": "DCPM", "squad": "JAEGER", "date_field": "created"},
        "generated_at": "2026-08-14T10:00:00+00:00",
        "empty": False,
        "kpis": {
            "total_work": 2682,
            "completed_work": 2480,
            "completion_pct": Decimal("92.47"),
            "active_work": 202,
            "open_bugs": 53,
            "high_priority_open_bugs": 9,
            "impeded_work": 16,
            "oldest_unresolved_days": 101,
            "status": "Needs Attention",
        },
        "metric_registry": {
            "active_work": {"formula": "Count where resolved is null and status_category is not Done."},
            "completion_pct": {"formula": "100 × end-state issue count ÷ total issue count."},
            "open_bugs": {"formula": "Unresolved Bug tickets outside Done."},
            "total_work": {"formula": "Count of distinct Jira issue keys in scope."},
        },
        "work_status": [
            {"status_category": "Done", "issue_count": 2480},
            {"status_category": "In Progress", "issue_count": 202},
        ],
        "attention_items": [
            {"metric": "impeded_work", "value": 16, "threshold": 1, "reason": "current impeded work is present"},
        ],
        "data_quality": {"unknown_status_count": 0},
        "data_quality_notes": ["Done is an end-state category and can include rejected or cancelled work."],
    }


def test_scope_normalization_drops_ui_all_labels_and_browser_values() -> None:
    scope = normalize_report_scope({
        "project": "dcpm",
        "squad": " JAEGER ",
        "sprint": "All sprints",
        "release": "All releases",
        "date_from": "All available dates",
        "current_metric_value": 92.47,
        "selected_squad_row": {"completion_pct": 92.47},
    })
    assert scope == {"project": "DCPM", "squad": "JAEGER"}

    contract = ReportScope.model_validate({
        "project": "dcpm", "sprint": "All sprints", "release": "All releases",
        "current_metric_value": 1,
    })
    assert contract.model_dump(exclude_none=True) == {"project": "DCPM"}


def test_current_view_reuses_the_squad_dashboard_calculation(monkeypatch) -> None:
    calls = []

    def dashboard(_session, **kwargs):
        calls.append(kwargs)
        return _dashboard_payload()

    monkeypatch.setattr("backend.services.report_generation.get_squad_dashboard", dashboard)
    result = current_view_dashboard_evidence(
        object(),
        {"project": "DCPM", "squad": "JAEGER", "sprint": "All sprints", "release": "All releases"},
    )

    assert calls == [{
        "project": "DCPM", "squad": "JAEGER", "release": None,
        "sprint": None, "date_from": None, "date_to": None,
    }]
    assert result["state"] == "ready"
    assert result["evidence"]["answer_source"] == "server_side_dashboard"
    assert result["evidence"]["query_ids"] == ["dashboard_service.get_squad_dashboard"]
    assert result["evidence"]["metrics"]["completion_pct"] == 92.47
    json.dumps(result)  # PostgreSQL numerics must be safe for the JSON evidence column.


def test_verified_dashboard_data_populates_supported_sections_only(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.services.report_generation.get_squad_dashboard",
        lambda *_args, **_kwargs: _dashboard_payload(),
    )
    result = current_view_dashboard_evidence(object(), {"project": "DCPM", "squad": "JAEGER"})
    sections = result["sections"]
    assert {
        "executive_summary", "kpi_group", "key_finding", "risk",
        "recommendation", "action_list", "data_quality",
    } <= sections.keys()
    assert "methodology" not in sections
    assert "92.47%" in sections["executive_summary"]["content"]
    key_measures = sections["kpi_group"]["payload"]
    assert key_measures["state"] == "ready"
    assert {item["key"] for item in key_measures["items"]} >= {
        "completion_pct", "active_work", "open_bugs", "impeded_work", "completed_work",
    }
    assert "Feature Status" not in sections


def test_main_report_content_is_management_facing_and_grounded(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.services.report_generation.get_squad_dashboard",
        lambda *_args, **_kwargs: _dashboard_payload(),
    )
    result = current_view_dashboard_evidence(
        object(), {"project": "DCPM", "squad": "JAEGER"}
    )
    sections = result["sections"]
    primary = "\n".join(
        sections[section_type]["content"]
        for section_type in ("executive_summary", "key_finding", "risk", "action_list")
    )
    lowered = primary.casefold()
    for internal_phrase in (
        "active_work", "frontend subtraction", "existing backend",
        "configured threshold", "deterministic dashboard",
    ):
        assert internal_phrase not in lowered

    assert "92.47%" in sections["executive_summary"]["content"]
    assert "202 work items still open" in sections["executive_summary"]["content"]
    assert "16 blocked work items" in sections["executive_summary"]["content"]
    assert "16 work items are currently blocked" in sections["risk"]["content"]
    assert "Review the 16 blocked work items" in sections["action_list"]["content"]


def test_main_report_uses_singular_wording_for_one_open_item(monkeypatch) -> None:
    payload = _dashboard_payload()
    payload["kpis"] = {
        **payload["kpis"], "active_work": 1, "impeded_work": 0, "open_bugs": 0,
        "oldest_unresolved_days": 1,
    }
    payload["attention_items"] = [{
        "metric": "oldest_unresolved_days", "value": 1, "reason": "ageing work",
    }]
    monkeypatch.setattr(
        "backend.services.report_generation.get_squad_dashboard",
        lambda *_args, **_kwargs: payload,
    )
    sections = current_view_dashboard_evidence(
        object(), {"project": "DCPM", "squad": "JAEGER"}
    )["sections"]
    assert "1 work item still open" in sections["executive_summary"]["content"]
    assert "1 work item remains open" in sections["key_finding"]["content"]
    assert "open for 1 day" in sections["risk"]["content"]
    assert "up to 1 day old" in sections["action_list"]["content"]


def test_provenance_stays_internal_and_metric_definitions_remain_available(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.services.report_generation.get_squad_dashboard",
        lambda *_args, **_kwargs: _dashboard_payload(),
    )
    result = current_view_dashboard_evidence(
        object(), {"project": "DCPM", "squad": "JAEGER"}
    )
    assert "methodology" not in result["sections"]
    internal_evidence = result["evidence"]["answer"]
    assert "dashboard_service.get_squad_dashboard" in internal_evidence
    assert "server-side against read-only DoraDB" in internal_evidence
    assert "current Jira status is Impeded" in internal_evidence
    assert "Browser-rendered metric values were not accepted" in internal_evidence

    measures = result["sections"]["kpi_group"]["payload"]
    assert [column["key"] for column in measures["columns"]] == ["label", "value"]
    assert all("formula" not in row for row in measures["rows"])
    assert all("formula" in item for item in measures["items"])
