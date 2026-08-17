import json
from unittest.mock import MagicMock, patch

from backend.agent.orchestrator import AgentOrchestrator
from backend.agent.request_router import route_jira_request
from backend.agent.response.responder import Responder, focused_dashboard_evidence
from backend.database.doradb import _build_statement, _normalize_filters, query_doradb
from backend.services.metric_selection import (
    message_mentions_metric,
    select_metric,
    select_metric_by_id,
)


BO_QUESTION = (
    "Sprint Completion for squad BO in DCPM is 20.00 and is flagged by the "
    "dashboard attention rules. What is driving the current completion rate? "
    "Break down work still outside Done by status category and issue type."
)


def test_completion_language_maps_to_canonical_dashboard_metric() -> None:
    for phrase in (
        "Sprint Completion",
        "completion",
        "completion rate",
        "completion percentage",
        "completion_pct",
    ):
        metric = select_metric(phrase)
        assert metric["id"] == "completion_pct"
        assert metric["field"] == "completion_pct"
        assert message_mentions_metric(phrase) is True
    assert select_metric_by_id("completion_pct")["id"] == "completion_pct"


def test_exact_bo_question_routes_to_open_work_breakdown() -> None:
    plan = route_jira_request(BO_QUESTION)

    assert plan is not None
    assert plan["mode"] == "data"
    assert plan["actions"][0]["query_id"] == "jira_open_work_breakdown"


def test_open_work_breakdown_executes_with_bound_case_insensitive_squad() -> None:
    session = MagicMock()
    session.execute.return_value.mappings.return_value.all.return_value = [
        {
            "ageing_bucket": "Less than 30 days",
            "issuetype": "Bug",
            "priority": "High",
            "status_category": "In Progress",
            "squad_coverage": "Squad populated",
            "issue_count": 8,
        },
        {
            "ageing_bucket": "30-60 days",
            "issuetype": "Bug",
            "priority": "Medium",
            "status_category": "To Do",
            "squad_coverage": "Squad populated",
            "issue_count": 4,
        },
    ]

    result = query_doradb(
        session,
        query_id="jira_open_work_breakdown",
        filters={"project_key": "DCPM", "dcpsquad": "bo"},
        limit=200,
    )

    statement, params = session.execute.call_args.args
    assert "UPPER(BTRIM(j.dcpsquad))" in str(statement)
    assert ":open_work_dcpsquad" in str(statement)
    assert params["open_work_dcpsquad"] == "BO"
    assert result["filters"]["dcpsquad"] == "BO"
    assert sum(row["issue_count"] for row in result["rows"]) == 12


def test_open_work_breakdown_preserves_all_squads_and_named_squad_behavior() -> None:
    all_filters = _normalize_filters(
        "jira_open_work_breakdown", {"project_key": "DCPM"}
    )
    _, all_params = _build_statement("jira_open_work_breakdown", all_filters, 200)
    assert "dcpsquad" not in all_filters
    assert all_params["open_work_dcpsquad"] is None

    jaeger_filters = _normalize_filters(
        "jira_open_work_breakdown",
        {"project_key": "DCPM", "dcpsquad": "Jaeger"},
    )
    _, jaeger_params = _build_statement(
        "jira_open_work_breakdown", jaeger_filters, 200
    )
    assert jaeger_filters["dcpsquad"] == "JAEGER"
    assert jaeger_params["open_work_dcpsquad"] == "JAEGER"


def test_focused_dashboard_scope_overrides_stale_conversation_squad() -> None:
    class OverClarifyingLlm:
        enabled = True
        source = "test-provider:test-model"

        @staticmethod
        def complete(*_args: object, **_kwargs: object) -> str:
            return (
                '{"mode":"clarification","intent":"model_plan_incomplete",'
                '"confidence":0.9,"reason":"needs breakdown",'
                '"clarification":"Which scope?","actions":[]}'
            )

    agent = AgentOrchestrator.__new__(AgentOrchestrator)
    agent.llm = OverClarifyingLlm()  # type: ignore[assignment]
    state = {
        "session_id": "test-bo",
        "message": BO_QUESTION,
        "memory": {
            "dashboard_context": {
                "project": "DCPM",
                "squad": "BO",
                "selected_metric": "completion_pct",
                "current_metric_value": 20.0,
                "selected_squad_row": {
                    "squad": "BO",
                    "total_work": 15,
                    "completed_work": 3,
                    "completion_pct": 20.0,
                    "active_work": 12,
                    "open_bugs": 10,
                },
            },
            "last_context": {
                "metric": "release_frequency",
                "filters": {"project_key": "DCPM", "dcpsquad": "JAEGER"},
            },
            "query_cache": [],
            "turns": [],
        },
        "browser_history": [],
        "project_scope": {"project_key": "DCPM"},
        "db_session": object(),
    }
    with patch(
        "backend.agent.orchestrator.load_entity_catalogue",
        return_value={"squad": ["BO", "JAEGER"]},
    ):
        planned = agent._plan(state)  # type: ignore[arg-type]

    assert planned["metric"]["id"] == "completion_pct"
    assert planned["plan"]["mode"] == "data"
    assert planned["plan"]["intent"] != "model_plan_incomplete"
    assert planned["plan"]["actions"][0]["query_id"] == "jira_open_work_breakdown"
    assert planned["plan"]["actions"][0]["filters"]["dcpsquad"] == "BO"


def test_responder_receives_only_relevant_matching_dashboard_evidence() -> None:
    context = {
        "project": "DCPM",
        "squad": "BO",
        "selected_metric": "completion_pct",
        "current_metric_value": 20.0,
        "frontend_debug_state": {"must_not": "reach model"},
        "selected_squad_row": {
            "squad": "BO",
            "total_work": 15,
            "completed_work": 3,
            "completion_pct": 20.0,
            "active_work": 12,
            "open_bugs": 10,
            "unrelated_frontend_value": "omit",
        },
    }

    evidence = focused_dashboard_evidence(context)

    assert evidence["scope"] == {"project": "DCPM", "squad": "BO"}
    assert evidence["selected_metric"] == "completion_pct"
    assert evidence["selected_squad_kpis"]["active_work"] == 12
    assert "frontend_debug_state" not in json.dumps(evidence)
    assert "unrelated_frontend_value" not in json.dumps(evidence)

    stale = focused_dashboard_evidence(
        {**context, "selected_squad_row": {"squad": "JAEGER", "active_work": 99}}
    )
    assert "selected_squad_kpis" not in stale


def test_data_responder_receives_dashboard_kpis_and_query_breakdown_together() -> None:
    class CapturingLlm:
        enabled = True
        source = "test-provider:test-model"
        evidence = {}

        def complete(self, _system_prompt: str, user_prompt: str, **_kwargs: object) -> str:
            self.evidence = json.loads(user_prompt)
            return "BO has 12 unresolved items across In Progress and To Do."

    llm = CapturingLlm()
    response = Responder(llm).respond(  # type: ignore[arg-type]
        {
            "message": BO_QUESTION,
            "plan": {
                "mode": "data",
                "intent": "ANALYSIS",
                "confidence": 1.0,
                "actions": [],
                "reason": "test",
                "clarification": "",
            },
            "metric": select_metric(BO_QUESTION),
            "results": [
                {
                    "query_id": "jira_open_work_breakdown",
                    "filters": {"project_key": "DCPM", "dcpsquad": "BO"},
                    "rows": [
                        {
                            "issuetype": "Bug",
                            "status_category": "In Progress",
                            "issue_count": 8,
                        },
                        {
                            "issuetype": "Bug",
                            "status_category": "To Do",
                            "issue_count": 2,
                        },
                        {
                            "issuetype": "User Story",
                            "status_category": "To Do",
                            "issue_count": 2,
                        },
                    ],
                    "row_count": 3,
                    "warnings": [],
                }
            ],
            "analysis": {},
            "validation": {"valid": True},
            "warnings": [],
            "knowledge_sections": [],
            "memory": {
                "dashboard_context": {
                    "project": "DCPM",
                    "squad": "BO",
                    "selected_metric": "completion_pct",
                    "current_metric_value": 20.0,
                    "selected_squad_row": {
                        "squad": "BO",
                        "total_work": 15,
                        "completed_work": 3,
                        "completion_pct": 20.0,
                        "active_work": 12,
                        "open_bugs": 10,
                    },
                }
            },
        }  # type: ignore[arg-type]
    )

    assert response["answer"].startswith("BO has 12 unresolved")
    assert llm.evidence["metric"]["id"] == "completion_pct"
    assert llm.evidence["verified_dashboard_evidence"]["selected_squad_kpis"][
        "active_work"
    ] == 12
    assert llm.evidence["results"][0]["filters"]["dcpsquad"] == "BO"
    assert llm.evidence["results"][0]["rows"][0]["status_category"] == "In Progress"


def test_normal_answers_are_not_forced_to_start_with_zara_identity_phrase() -> None:
    class DirectLlm:
        source = "test-provider:test-model"

        @staticmethod
        def complete(*_args: object, **_kwargs: object) -> str:
            return "Here is the verified result."

    response = Responder(DirectLlm()).respond(  # type: ignore[arg-type]
        {
            "message": "Explain the result.",
            "plan": {
                "mode": "conversation",
                "intent": "general_conversation",
                "confidence": 1.0,
                "actions": [],
                "reason": "test",
                "clarification": "",
            },
        }  # type: ignore[arg-type]
    )

    assert response["answer"] == "Here is the verified result."
    assert not response["answer"].startswith("Yes, I'm Zara.")
