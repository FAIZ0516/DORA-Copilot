from __future__ import annotations

from unittest.mock import MagicMock

from backend.agent_system.graph import AdvancedDoraDbAgent
from backend.agent_system.planner import create_plan
from backend.agent_system.request_router import (
    DATABASE_METADATA,
    DATA_RETRIEVAL,
    KNOWLEDGE_EXPLANATION,
)
from backend.doradb import query_doradb
from backend.knowledge_service import (
    knowledge_fallback_answer,
    load_jira_knowledge,
    select_knowledge_sections,
)


class NoCallLlm:
    enabled = True
    calls = 0

    def complete(self, *_args: object, **_kwargs: object) -> str:
        self.calls += 1
        return "unexpected"


class DisabledLlm:
    enabled = False
    unavailable_message = "provider unavailable"


def plan_for(message: str):
    llm = NoCallLlm()
    plan, source = create_plan(
        message,
        memory={},
        browser_history=[],
        llm=llm,  # type: ignore[arg-type]
    )
    return plan, source, llm


def result_envelope(query_id: str, rows: list[dict[str, object]]):
    return {
        "query_id": query_id,
        "project_key": "DCPM",
        "filters": {"project_key": "DCPM"},
        "rows": rows,
        "row_count": len(rows),
        "limit_applied": 100,
        "warnings": [],
    }


def test_jira_table_explanation_uses_cached_markdown_without_data_query() -> None:
    plan, source, llm = plan_for("What is the Jira issues table?")

    assert plan["intent"] == KNOWLEDGE_EXPLANATION
    assert plan["mode"] == "conversation"
    assert plan["actions"] == []
    assert source == "jira-router"
    assert llm.calls == 0

    first = load_jira_knowledge()
    second = load_jira_knowledge()
    sections = select_knowledge_sections("What is the Jira issues table?")
    assert first is second
    assert any("Jira Issues Table Represents" in section.title for section in sections)
    assert "snapshot" in " ".join(section.content for section in sections).lower()


def test_lead_time_location_uses_metadata_and_explains_metric_boundary() -> None:
    plan, _, _ = plan_for("Which table has lead time?")

    assert plan["intent"] == DATABASE_METADATA
    assert [action["query_id"] for action in plan["actions"]] == [
        "database_metric_columns"
    ]
    assert all(
        action["query_id"] != "dora_metrics_by_year" for action in plan["actions"]
    )

    answer = knowledge_fallback_answer("Which table has lead time?")
    assert "issue-resolution duration" in answer
    assert "not DORA Lead Time for Changes" in answer
    assert "code-change" in answer and "production-deployment" in answer


def test_list_available_squads_uses_distinct_dcpsquad_not_available_filter() -> None:
    plan, _, _ = plan_for("List available squads.")

    assert plan["intent"] == DATA_RETRIEVAL
    assert [action["query_id"] for action in plan["actions"]] == [
        "database_squad_sources",
        "jira_distinct_squads",
    ]
    assert all(
        action["filters"].get("dcpsquad") != "AVAILABLE"
        for action in plan["actions"]
    )


def test_list_all_teams_uses_real_squad_query() -> None:
    plan, _, _ = plan_for("List all the teams.")
    assert plan["intent"] == DATA_RETRIEVAL
    assert [action["query_id"] for action in plan["actions"]] == [
        "database_squad_sources",
        "jira_distinct_squads",
    ]

    session = MagicMock()
    session.execute.return_value.mappings.return_value.all.return_value = [
        {"dcpsquad": "JAEGER", "missing_squad_rows": 10},
        {"dcpsquad": "TITAN", "missing_squad_rows": 10},
    ]
    result = query_doradb(
        session,
        query_id="jira_distinct_squads",
        filters={"project_key": "DCPM"},
        limit=100,
    )

    statement, params = session.execute.call_args.args
    assert "BTRIM(j.dcpsquad)" in str(statement)
    assert "AVAILABLE" not in str(statement)
    assert "AVAILABLE" not in params.values()
    assert result["row_count"] == 2
    assert "authoritative" in result["warnings"][0]


def test_valid_bug_count_query_executes_and_is_summarised() -> None:
    plan, _, _ = plan_for("Count bugs by status.")
    assert plan["actions"][0]["query_id"] == "jira_issue_counts_by_status"
    assert plan["actions"][0]["filters"]["issuetype"] == "Bug"

    session = MagicMock()
    session.execute.return_value.mappings.return_value.all.return_value = [
        {
            "issuetype": "Bug",
            "status": "To Do",
            "status_category": "To Do",
            "issue_count": 5,
        }
    ]
    result = query_doradb(
        session,
        query_id="jira_issue_counts_by_status",
        filters={"project_key": "DCPM", "issuetype": "Bug"},
        limit=100,
    )
    assert session.execute.called
    assert result["rows"][0]["issue_count"] == 5

    class SummaryLlm:
        enabled = True
        source = "test-provider:test-model"

        @staticmethod
        def complete(*_args: object, **_kwargs: object) -> str:
            return "There are 5 bugs in the To Do status."

    agent = AdvancedDoraDbAgent.__new__(AdvancedDoraDbAgent)
    agent.llm = SummaryLlm()  # type: ignore[assignment]
    response = agent._respond(
        {
            "message": "Count bugs by status.",
            "plan": plan,
            "metric": {"id": "delivery_performance"},
            "results": [result],
            "analysis": {},
            "validation": {"valid": True},
            "warnings": [],
            "knowledge_sections": [],
        }  # type: ignore[arg-type]
    )
    assert response["answer"] == "There are 5 bugs in the To Do status."


def test_zero_rows_reports_no_matches_not_missing_schema_object() -> None:
    plan, _, _ = plan_for("Count bugs by status.")
    agent = AdvancedDoraDbAgent.__new__(AdvancedDoraDbAgent)
    agent.llm = DisabledLlm()  # type: ignore[assignment]
    response = agent._respond(
        {
            "message": "Count bugs by status.",
            "plan": plan,
            "metric": {"id": "delivery_performance"},
            "results": [result_envelope("jira_issue_counts_by_status", [])],
            "validation": {"valid": True},
            "warnings": [],
            "knowledge_sections": [],
        }  # type: ignore[arg-type]
    )

    assert "query ran successfully" in response["answer"]
    assert "no records matched" in response["answer"]
    assert "does not mean the table or column is absent" in response["answer"]


def test_nonexistent_column_verifies_table_and_column_separately() -> None:
    message = "Does the Jira issues table contain `frobnitz`?"
    plan, _, _ = plan_for(message)

    assert plan["intent"] == DATABASE_METADATA
    assert [action["query_id"] for action in plan["actions"]] == [
        "database_table_presence",
        "database_columns",
    ]
    assert plan["actions"][1]["filters"]["column_search"] == "frobnitz"

    agent = AdvancedDoraDbAgent.__new__(AdvancedDoraDbAgent)
    agent.llm = DisabledLlm()  # type: ignore[assignment]
    response = agent._respond(
        {
            "message": message,
            "plan": plan,
            "metric": {"id": "delivery_performance"},
            "results": [
                result_envelope(
                    "database_table_presence",
                    [
                        {
                            "table_schema": "public",
                            "table_name": "tbl_gdt_dte_jira_issues",
                            "object_type": "table",
                        }
                    ],
                ),
                result_envelope("database_columns", []),
            ],
            "validation": {"valid": True},
            "warnings": [],
            "knowledge_sections": [],
        }  # type: ignore[arg-type]
    )

    assert "table exists" in response["answer"]
    assert "no matching column was found" in response["answer"]


def test_story_points_are_verified_as_unsupported_not_replaced_by_progress() -> None:
    plan, _, _ = plan_for("Does the Jira issues table contain story points?")

    assert plan["intent"] == DATABASE_METADATA
    assert plan["actions"][0]["query_id"] == "database_table_presence"
    assert plan["actions"][1]["query_id"] == "database_columns"
    assert plan["actions"][1]["filters"]["column_search"] == "story"

    answer = knowledge_fallback_answer(
        "Does the Jira issues table contain story points?"
    )
    assert "not available" in answer
    assert "progress_pct" in answer
    assert "must not be used as a substitute" in answer
