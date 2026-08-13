"""Template questions are fixed; the answers come from live data.

That is what makes a template reproducible -- the same report next week asks
the same things and reports whatever the data says then.
"""

from __future__ import annotations

from backend.services.report_generation import (
    dashboard_context_for,
    run_template_questions,
    scope_to_question,
)
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
