import time
from datetime import date
from unittest.mock import MagicMock

from sqlalchemy.exc import OperationalError

from backend.agent.agent_definition import AdvancedDoraDbAgent
from backend.agent.controls.execution_control import public_policy
from backend.agent.guardrails.tool_guardrail import enforce_plan
from backend.agent.orchestrator import _is_holistic_request
from backend.agent.response.responder import AI_UNAVAILABLE_MESSAGE, Responder
from backend.memory.memory import SessionMemoryStore
from backend.agent.planner import create_plan, deterministic_plan
from backend.agent.validators import validate_answer, validate_results
from backend.database.doradb import _normalize_filters
from backend.services import (
    analyze_trend,
    build_chart_spec,
    classify_intent,
    compare_rows,
    detect_anomalies,
    extract_filters,
    select_metric,
)


def test_skills_extract_and_analyze_without_llm_arithmetic() -> None:
    filters = extract_filters("Compare Change Failure Rate in 2025 and 2026")
    metric = select_metric("Change Failure Rate")
    rows = [
        {"release_year": 2025, "change_failure_rate_pct": 12.5},
        {"release_year": 2026, "change_failure_rate_pct": 10.0},
    ]
    assert filters["release_year"] == [2025, 2026]
    assert metric["field"] == "change_failure_rate_pct"
    assert compare_rows(rows, metric["field"])[0]["percent_change"] == -20.0
    assert analyze_trend(rows, metric["field"])["direction"] == "decreasing"
    assert detect_anomalies(rows, metric["field"]) == []


def test_chart_skill_supports_requested_visual_type() -> None:
    chart = build_chart_spec(
        query_id="dora_metrics_by_year",
        rows=[
            {"release_year": 2025, "release_frequency_months": 2.0},
            {"release_year": 2026, "release_frequency_months": 1.5},
        ],
        metric=select_metric("release frequency"),
        question="show a line chart",
    )
    assert chart is not None
    assert chart["type"] == "line"
    assert chart["x_key"] == "period"


def test_all_metrics_bar_chart_has_real_grouped_series() -> None:
    chart = build_chart_spec(
        query_id="dora_metrics_by_year",
        rows=[
            {
                "release_year": 2025,
                "release_frequency_months": 2.0,
                "change_failure_rate_pct": 10.0,
                "lead_time_for_change_months": 1.2,
                "delivery_cycle_time_months": 4.5,
            }
        ],
        metric=select_metric("release frequency"),
        question="Show all available DORA metrics in a bar chart",
    )
    assert chart is not None
    assert chart["type"] == "bar"
    assert len(chart["series"]) == 4
    assert chart["data"][0]["change_failure_rate_pct"] == 10.0


def test_scatter_chart_uses_two_numeric_dora_dimensions() -> None:
    chart = build_chart_spec(
        query_id="dora_metrics_by_year",
        rows=[
            {
                "release_year": 2025,
                "lead_time_for_change_months": 1.2,
                "delivery_cycle_time_months": 4.5,
            }
        ],
        metric=select_metric("lead time"),
        question="Create a scatter plot",
    )
    assert chart is not None
    assert chart["type"] == "scatter"
    assert chart["x_key"] == "lead_time"
    assert chart["series"][0]["key"] == "cycle_time"


def test_supported_chart_families_are_selected_from_natural_language() -> None:
    rows = [
        {
            "release_year": 2025,
            "release_frequency_months": 2.0,
            "change_failure_rate_pct": 10.0,
            "lead_time_for_change_months": 1.2,
            "delivery_cycle_time_months": 4.5,
        }
    ]
    cases = {
        "horizontal bar chart": "horizontal_bar",
        "stacked bar chart": "stacked_bar",
        "line chart": "line",
        "area chart": "area",
        "pie chart": "pie",
        "doughnut chart": "donut",
        "polar area chart": "polar_area",
        "radar chart": "radar",
        "scatter plot": "scatter",
    }
    for phrase, expected in cases.items():
        chart = build_chart_spec(
            query_id="dora_metrics_by_year",
            rows=rows,
            metric=select_metric("release frequency"),
            question=f"Show a {phrase}",
        )
        assert chart is not None
        assert chart["type"] == expected


def test_control_rejects_unapproved_model_tool() -> None:
    plan = enforce_plan(
        {
            "mode": "data",
            "intent": "metric_lookup",
            "confidence": 0.9,
            "actions": [
                {
                    "query_id": "generated_sql",
                    "filters": {},
                    "limit": 10,
                    "reason": "model proposal",
                }
            ],
            "reason": "test",
            "clarification": "",
        }
    )
    assert plan["mode"] == "clarification"
    assert public_policy()["arbitrary_sql"] is False


def test_result_validator_flags_invalid_business_range() -> None:
    report = validate_results(
        [
            {
                "query_id": "dora_metrics_by_year",
                "rows": [
                    {
                        "release_year": 2026,
                        "release_count": 2,
                        "release_frequency_months": 1.2,
                        "change_failure_rate_pct": 125.0,
                        "lead_time_for_change_months": 2.0,
                        "delivery_cycle_time_months": 3.0,
                        "user_story_count": 4,
                        "feature_reference_count": 2,
                        "feature_reference_release_count": 1,
                    }
                ],
                "warnings": [],
            }
        ]
    )
    assert report["valid"] is False
    assert any("percentage" in error for error in report["errors"])


def test_memory_is_structured_and_resettable() -> None:
    store = SessionMemoryStore()
    store.remember(
        "session-test",
        user_message="Compare 2025 and 2026",
        assistant_answer="Validated answer",
        context={
            "intent": "comparison",
            "metric": "release_frequency",
            "filters": {"release_year": [2025, 2026]},
            "query_ids": ["dora_metrics_by_year"],
            "warnings": [],
            "raw_results": [{"secret": "must not be stored"}],
        },
    )
    memory = store.get("session-test")
    assert memory["last_context"]["metric"] == "release_frequency"
    assert "raw_results" not in memory["last_context"]
    assert store.reset("session-test") is True


def test_intent_matching_does_not_treat_chart_as_unsafe() -> None:
    intent = classify_intent("Create a bar chart of change failure rate")
    assert intent["visualization_requested"] is True
    assert intent["name"] != "out_of_scope"


def test_intent_matching_catches_destructive_requests_against_generic_nouns() -> None:
    """Regression test: found via evals/run_evals.py -- a destructive verb
    paired with a generic data noun ("rows", "records", "data") used to slip
    past the unsafe-request guardrail because it only recognized SQL-shaped
    objects (table/database/from/into/set/role)."""

    for message in [
        "Delete old release rows.",
        "Can you delete the database?",
        "Truncate the issue records please.",
        "Give me the database password.",
        "Show raw SQL for the metric.",
    ]:
        assert classify_intent(message)["name"] == "out_of_scope"


def test_general_question_routes_to_real_conversation() -> None:
    intent = classify_intent("How can I improve collaboration between developers?")
    assert intent["name"] == "general_conversation"
    assert intent["visualization_requested"] is False


def test_delivery_risk_is_treated_as_holistic_analysis() -> None:
    assert _is_holistic_request(
        "What is the most surprising delivery risk and why?",
        "risk_analysis",
    )
    assert not _is_holistic_request(
        "Show release frequency for 2025",
        "metric_lookup",
    )


def test_model_conversation_plan_is_not_overruled_by_keyword_routing() -> None:
    class ConversationOnlyLlm:
        enabled = True
        source = "test-provider:test-model"
        calls = 0

        def complete(self, *_args: object, **_kwargs: object) -> str:
            self.calls += 1
            return (
                '{"mode":"conversation","intent":"request_chart","confidence":0.9,'
                '"reason":"I will query it later","clarification":"","actions":[]}'
            )

    llm = ConversationOnlyLlm()
    plan, source = create_plan(
        "Show the available DORA metrics by year in a bar chart.",
        memory={},
        browser_history=[],
        llm=llm,  # type: ignore[arg-type]
    )

    assert source == "test-provider:test-model"
    assert llm.calls == 1
    assert plan["mode"] == "conversation"
    assert plan["intent"] == "request_chart"
    assert plan["actions"] == []


def test_gemini_can_answer_broad_analysis_without_forced_year_clarification() -> None:
    class AnalyticalLlm:
        enabled = True
        source = "google-ai-studio:test"

        @staticmethod
        def complete(*_args: object, **_kwargs: object) -> str:
            return (
                '{"mode":"data","intent":"risk_analysis","confidence":0.93,'
                '"reason":"A multi-year overview can answer this request",'
                '"clarification":"","actions":[{"query_id":'
                '"dora_metrics_by_year","filters":{},"limit":10,'
                '"reason":"Inspect all delivery measures over time"}]}'
            )

    plan, source = create_plan(
        "Based on the real data, what is the most surprising delivery risk and why?",
        memory={},
        browser_history=[],
        llm=AnalyticalLlm(),  # type: ignore[arg-type]
    )

    assert source == "google-ai-studio:test"
    assert plan["mode"] == "data"
    assert plan["intent"] == "risk_analysis"
    assert plan["actions"][0]["query_id"] == "dora_metrics_by_year"
    assert plan["actions"][0]["filters"]["project_key"] == "DCPM"


def test_gemini_multi_query_plan_survives_allowlist_controls() -> None:
    class MultiQueryLlm:
        enabled = True
        source = "google-ai-studio:test"

        @staticmethod
        def complete(*_args: object, **_kwargs: object) -> str:
            return (
                '{"mode":"data","intent":"recommendation","confidence":0.96,'
                '"reason":"Use performance and composition evidence",'
                '"clarification":"","actions":['
                '{"query_id":"dora_metrics_by_squad","filters":'
                '{"dcpsquad":"JAEGER"},"limit":10,"reason":"Performance"},'
                '{"query_id":"story_to_feature_ratio","filters":'
                '{"release_year":[2025]},"limit":50,"reason":"Composition"}]}'
            )

    plan, _ = create_plan(
        "Recommend improvements for Jaeger in 2025 using all relevant data",
        memory={},
        browser_history=[],
        llm=MultiQueryLlm(),  # type: ignore[arg-type]
    )

    assert plan["mode"] == "data"
    assert [action["query_id"] for action in plan["actions"]] == [
        "dora_metrics_by_squad",
        "story_to_feature_ratio",
    ]
    assert all(
        action["filters"]["project_key"] == "DCPM"
        for action in plan["actions"]
    )


def test_model_clarification_is_not_replaced_by_keyword_selected_query() -> None:
    class ClarificationOnlyLlm:
        enabled = True

        @staticmethod
        def complete(*_args: object, **_kwargs: object) -> str:
            return (
                '{"mode":"clarification","intent":"metric","confidence":0.8,'
                '"reason":"ask for filters","clarification":"Which year?",'
                '"actions":[]}'
            )

    broad, _ = create_plan(
        "lead time",
        memory={},
        browser_history=[],
        llm=ClarificationOnlyLlm(),  # type: ignore[arg-type]
    )
    assert broad["mode"] == "clarification"

    explicit, _ = create_plan(
        "how many release years do you have",
        memory={},
        browser_history=[],
        llm=ClarificationOnlyLlm(),  # type: ignore[arg-type]
    )
    assert explicit["mode"] == "clarification"
    assert explicit["intent"] == "metric"
    assert explicit["actions"] == []


def test_follow_up_inherits_metric_and_year_context() -> None:
    memory = {
        "last_context": {
            "metric": "release_frequency",
            "filters": {"project_key": "DCPM"},
            "query_ids": [],
        }
    }
    year_plan = deterministic_plan(
        "Explain everything I need to know for 2022",
        memory,
    )
    assert year_plan["mode"] == "data"
    assert year_plan["actions"][0]["filters"]["release_year"] == [2022]

    chart_plan = deterministic_plan("Create a pie chart for it", memory)
    assert chart_plan["mode"] == "data"
    assert chart_plan["actions"][0]["query_id"] == "dora_metrics_by_year"


def test_recommendation_clarifies_squad_then_queries_all_squad_metrics() -> None:
    clarification = deterministic_plan(
        "Based on the data, suggest improvements for the squad",
        {"last_context": {}},
    )
    assert clarification["mode"] == "clarification"
    assert clarification["intent"] == "clarify_recommendation_scope"

    recommendation = deterministic_plan(
        "Suggest improvements for the Jaeger squad",
        {"last_context": {}},
    )
    assert recommendation["mode"] == "data"
    assert recommendation["intent"] == "recommendation"
    assert recommendation["actions"][0]["query_id"] == "dora_metrics_by_squad"
    assert recommendation["actions"][0]["filters"]["dcpsquad"] == "JAEGER"


def test_normal_metric_follow_up_keeps_active_squad_context() -> None:
    memory = {
        "last_context": {
            "metric": "delivery_performance",
            "filters": {"project_key": "DCPM", "dcpsquad": "JAEGER"},
            "query_ids": ["dora_metrics_by_squad"],
        }
    }
    plan = deterministic_plan(
        "What do you understand from release frequency?",
        memory,
    )
    assert plan["mode"] == "data"
    assert plan["actions"][0]["query_id"] == "dora_metrics_by_squad"
    assert plan["actions"][0]["filters"]["dcpsquad"] == "JAEGER"


def test_squad_is_a_dimension_and_cannot_override_project_scope() -> None:
    class WrongProjectLlm:
        enabled = True

        @staticmethod
        def complete(*_args: object, **_kwargs: object) -> str:
            return (
                '{"mode":"data","intent":"squad_release_frequency",'
                '"confidence":0.9,"reason":"query squad","clarification":"",'
                '"actions":[{"query_id":"dora_metrics_by_year","filters":'
                '{"project_key":"TITAN"},"limit":10,"reason":"wrong mapping"}]}'
            )

    plan, _ = create_plan(
        "Analyze the release frequency from Titan squad",
        memory={},
        browser_history=[],
        llm=WrongProjectLlm(),  # type: ignore[arg-type]
    )
    assert plan["mode"] == "clarification"
    assert plan["intent"] == "model_plan_incomplete"
    assert plan["actions"] == []


def test_release_date_filter_accepts_malaysian_day_month_format() -> None:
    filters = extract_filters("Show the release on 24/9/2025")
    assert filters["release_date"] == "2025-09-24"
    assert filters["release_year"] == [2025]


def test_generic_each_squad_phrase_is_not_extracted_as_a_named_squad() -> None:
    filters = extract_filters(
        "Other than bug volume, what more data can I get for each squad?"
    )

    assert "dcpsquad" not in filters
    assert "issuetype" not in filters


def test_dimension_discovery_filter_survives_database_normalization() -> None:
    filters = _normalize_filters(
        "list_dimension_values",
        {"dimension": "squad", "project_key": "DCPM"},
    )

    assert filters["dimension"] == "squad"
    assert filters["project_key"] == "DCPM"


def test_release_frequency_is_not_misread_as_a_fixversion() -> None:
    filters = extract_filters("Can you talk about release frequency?")
    assert filters == {"project_key": "DCPM"}


def test_safe_general_question_routes_to_conversation_without_database_planning() -> None:
    class CountingLlm:
        enabled = True
        source = "test-provider:test-model"
        calls = 0

        def complete(self, *_args: object, **_kwargs: object) -> str:
            self.calls += 1
            return (
                '{"mode":"conversation","intent":"general_conversation",'
                '"confidence":0.99,"reason":"No data is required",'
                '"clarification":"","actions":[]}'
            )

    llm = CountingLlm()
    plan, source = create_plan(
        "What date is today?",
        memory={},
        browser_history=[],
        llm=llm,  # type: ignore[arg-type]
    )
    assert plan["mode"] == "conversation"
    assert source == "test-provider:test-model"
    assert llm.calls == 1


def test_malformed_model_plan_does_not_fall_back_to_keyword_routing() -> None:
    class MalformedPlannerLlm:
        enabled = True
        source = "test-provider:test-model"

        @staticmethod
        def complete(*_args: object, **_kwargs: object) -> str:
            return "not valid planning json"

    plan, source = create_plan(
        "List all available squads",
        memory={},
        browser_history=[],
        llm=MalformedPlannerLlm(),  # type: ignore[arg-type]
    )

    assert source == "ai-planner-unavailable"
    assert plan["mode"] == "clarification"
    assert plan["intent"] == "AI_PLANNER_UNAVAILABLE"
    assert plan["actions"] == []


def test_capability_question_guidance_keeps_semantic_choice_with_model() -> None:
    class CapabilityPlannerLlm:
        enabled = True
        source = "test-provider:test-model"
        system_prompt = ""

        def complete(self, system_prompt: str, *_args: object, **_kwargs: object) -> str:
            self.system_prompt = system_prompt
            return (
                '{"mode":"conversation","intent":"CAPABILITY_EXPLANATION",'
                '"confidence":0.99,"reason":"Capability question",'
                '"clarification":"","actions":[]}'
            )

    llm = CapabilityPlannerLlm()
    plan, source = create_plan(
        "Other than bug volume, what more data can I get for each squad?",
        memory={},
        browser_history=[],
        llm=llm,  # type: ignore[arg-type]
    )

    assert "Treat questions about what kinds of data" in llm.system_prompt
    assert plan["mode"] == "conversation"
    assert plan["intent"] == "CAPABILITY_EXPLANATION"
    assert plan["actions"] == []
    assert source == "test-provider:test-model"


def test_capability_answer_rewrites_unqueried_dataset_counts_with_ai() -> None:
    class CapabilityAnswerLlm:
        source = "test-provider:test-model"
        calls = 0

        def complete(self, *_args: object, **_kwargs: object) -> str:
            self.calls += 1
            if self.calls == 1:
                return "The report covers 63,481 issues plus DORA metrics."
            return "The report supports named-squad DORA metrics without stale counts."

    llm = CapabilityAnswerLlm()
    response = Responder(llm).respond(  # type: ignore[arg-type]
        {
            "message": "What more data can I get for each squad?",
            "plan": {
                "mode": "conversation",
                "intent": "CAPABILITY_EXPLANATION",
                "confidence": 0.99,
                "actions": [],
                "reason": "Capability question",
                "clarification": "",
            },
        }  # type: ignore[arg-type]
    )

    assert llm.calls == 2
    assert "63,481" not in response["answer"]
    assert response["answer"].endswith(
        "The report supports named-squad DORA metrics without stale counts."
    )


def test_model_follow_up_without_compatible_cache_asks_instead_of_guessing() -> None:
    class FollowUpPlannerLlm:
        enabled = True
        source = "test-provider:test-model"

        @staticmethod
        def complete(*_args: object, **_kwargs: object) -> str:
            return (
                '{"mode":"conversation",'
                '"intent":"FOLLOW_UP_ON_EXISTING_RESULT",'
                '"confidence":0.98,"reason":"Refers to earlier evidence",'
                '"clarification":"","actions":[]}'
            )

    agent = AdvancedDoraDbAgent.__new__(AdvancedDoraDbAgent)
    agent.llm = FollowUpPlannerLlm()  # type: ignore[assignment]
    planned = agent._plan(
        {
            "message": "Could you explain that result further?",
            "memory": {"query_cache": [], "turns": []},
            "browser_history": [],
            "project_scope": {"project_key": "DCPM"},
        }  # type: ignore[arg-type]
    )

    assert planned["plan"]["mode"] == "clarification"
    assert planned["plan"]["intent"] == "model_plan_incomplete"
    assert planned["results"] == []


def test_general_conversation_receives_current_date_context() -> None:
    class CapturingLlm:
        source = "test-provider:test-model"
        system_prompt = ""

        def complete(self, system_prompt: str, _user_prompt: str) -> str:
            self.system_prompt = system_prompt
            return "A direct answer."

    llm = CapturingLlm()
    responder = Responder(llm)  # type: ignore[arg-type]

    response = responder.respond(
        {
            "message": "What date is today?",
            "plan": {
                "mode": "conversation",
                "intent": "general_conversation",
                "confidence": 0.99,
                "actions": [],
                "reason": "test",
                "clarification": "",
            },
        }  # type: ignore[arg-type]
    )

    assert f"Current date: {date.today().isoformat()}" in llm.system_prompt
    assert "Approved capability catalogue:" in llm.system_prompt
    assert "Authoritative squad-reporting boundary:" in llm.system_prompt
    # The response-protocol phrase is always prepended by the runtime
    # instructions; assert on the generated content, not the raw start.
    assert response["answer"].endswith("A direct answer.")
    assert response["answer_source"] == "test-provider:test-model"


def test_safe_clarification_is_worded_by_the_internal_model() -> None:
    class ClarifyingLlm:
        enabled = True
        source = "test-provider:test-model"
        calls = 0

        def complete(self, *_args: object, **_kwargs: object) -> str:
            self.calls += 1
            return "Which squad would you like me to evaluate?"

    llm = ClarifyingLlm()
    response = Responder(llm).respond(  # type: ignore[arg-type]
        {
            "message": "Suggest improvements for the squad",
            "planner_source": "deterministic-fallback",
            "plan": {
                "mode": "clarification",
                "intent": "clarify_recommendation_scope",
                "confidence": 0.95,
                "actions": [],
                "reason": "A squad is required for this comparison.",
                "clarification": "Which squad should I evaluate?",
            },
        }  # type: ignore[arg-type]
    )

    assert llm.calls == 1
    assert response["answer"].endswith(
        "Which squad would you like me to evaluate?"
    )
    assert response["answer_source"] == "test-provider:test-model"


def test_agent_never_substitutes_a_template_when_ai_is_unavailable() -> None:
    class UnavailableLlm:
        enabled = True
        last_model = None

        @staticmethod
        def complete(*_args: object, **_kwargs: object) -> None:
            return None

    responder = Responder(UnavailableLlm())  # type: ignore[arg-type]
    response = responder.respond(
        {
            "message": "Suggest improvements for the Jaeger squad",
            "plan": {
                "mode": "data",
                "intent": "recommendation",
                "confidence": 0.95,
                "actions": [],
                "reason": "test",
                "clarification": "",
            },
            "metric": {
                "id": "delivery_performance",
                "field": "release_frequency_months",
                "label": "Overall delivery performance",
                "unit": "",
                "direction": "contextual",
            },
            "validation": {"valid": True},
            "results": [
                {
                    "query_id": "dora_metrics_by_squad",
                    "filters": {"dcpsquad": "JAEGER", "project_key": "DCPM"},
                    "rows": [{"dcpsquad": "JAEGER", "release_year": 2026}],
                }
            ],
            "analysis": {},
            "chart": None,
            "warnings": [],
        }  # type: ignore[arg-type]
    )
    # The response-protocol phrase is always prepended by the runtime
    # instructions; assert on the generated content, not the raw start.
    assert response["answer"].endswith(AI_UNAVAILABLE_MESSAGE)
    assert response["answer_source"] == "ai-provider-unavailable"
    assert "Found" not in response["answer"]
    assert "Recommended priorities" not in response["answer"]

    clarification = responder.respond(
        {
            "message": "Suggest improvements for the squad",
            "planner_source": "deterministic-fallback",
            "plan": {
                "mode": "clarification",
                "intent": "clarify_recommendation_scope",
                "confidence": 0.95,
                "actions": [],
                "reason": "test",
                "clarification": "Which squad should I evaluate?",
            },
        }  # type: ignore[arg-type]
    )
    assert clarification["answer"].endswith(AI_UNAVAILABLE_MESSAGE)
    assert "Which squad" not in clarification["answer"]


def test_execute_node_catches_db_failure_instead_of_aborting_the_graph() -> None:
    """A DoraDB connection failure inside _execute must not raise -- it
    should be captured as state so the graph can still reach `respond`
    (previously this propagated out of .invoke() entirely)."""

    agent = AdvancedDoraDbAgent.__new__(AdvancedDoraDbAgent)
    session = MagicMock()
    session.execute.side_effect = OperationalError(
        "SELECT 1", {}, Exception("connection refused")
    )
    result = agent._execute(
        {
            "started_at": time.monotonic(),
            "session_id": "test",
            "db_session": session,
            "plan": {
                "mode": "data",
                "intent": "data_retrieval",
                "confidence": 0.9,
                "actions": [
                    {
                        "query_id": "jira_distinct_squads",
                        "filters": {"project_key": "DCPM"},
                        "limit": 100,
                        "reason": "test",
                    }
                ],
                "reason": "test",
                "clarification": "",
            },
        }  # type: ignore[arg-type]
    )
    assert result["results"] == []
    assert result["database_error"] == "The DoraDB database is temporarily unavailable."
    assert result["database_query_executed"] is False


def test_database_error_is_composed_by_the_llm_not_a_raw_string() -> None:
    """Regression test: a DoraDB connectivity failure used to abort the
    LangGraph run entirely (raised out of _execute), so the user got a raw
    HTTP-layer error string and the LLM was never called. _execute/_repair
    now catch the failure and let `respond` compose an honest explanation
    through the normal instructions/skill pipeline."""

    class RecordingLlm:
        enabled = True
        source = "test-provider:test-model"
        last_prompt = ""

        def complete(self, system_prompt: str, _user_prompt: str) -> str:
            self.last_prompt = system_prompt
            return "I couldn't reach the database just now, please try again shortly."

    llm = RecordingLlm()
    responder = Responder(llm)  # type: ignore[arg-type]
    response = responder.respond(
        {
            "message": "list the squad",
            "plan": {
                "mode": "data",
                "intent": "data_retrieval",
                "confidence": 0.9,
                "actions": [],
                "reason": "test",
                "clarification": "",
            },
            "metric": {"id": "delivery_performance"},
            "results": [],
            "database_error": "The DoraDB database is temporarily unavailable.",
            "analysis": {},
            "validation": {"valid": True},
            "warnings": [],
            "knowledge_sections": [],
        }  # type: ignore[arg-type]
    )
    assert "database" in llm.last_prompt.lower()
    assert response["answer"].endswith(
        "I couldn't reach the database just now, please try again shortly."
    )
    assert response["answer_source"] == "test-provider:test-model"


def test_database_error_falls_back_honestly_when_llm_also_unavailable() -> None:
    class DeadLlm:
        enabled = True

        @staticmethod
        def complete(*_args: object, **_kwargs: object) -> None:
            return None

    responder = Responder(DeadLlm())  # type: ignore[arg-type]
    response = responder.respond(
        {
            "message": "list the squad",
            "plan": {
                "mode": "data",
                "intent": "data_retrieval",
                "confidence": 0.9,
                "actions": [],
                "reason": "test",
                "clarification": "",
            },
            "metric": {"id": "delivery_performance"},
            "results": [],
            "database_error": "The DoraDB database is temporarily unavailable.",
            "analysis": {},
            "validation": {"valid": True},
            "warnings": [],
            "knowledge_sections": [],
        }  # type: ignore[arg-type]
    )
    assert "temporarily unavailable" in response["answer"]
    assert response["answer_source"] == "database-unavailable"


def test_chart_is_only_built_when_visualization_is_requested() -> None:
    agent = AdvancedDoraDbAgent.__new__(AdvancedDoraDbAgent)
    rows = [
        {
            "release_year": 2022,
            "release_frequency_months": 1.44,
        }
    ]
    base_state = {
        "results": [{"query_id": "dora_metrics_by_year", "rows": rows}],
        "metric": select_metric("release frequency"),
    }
    without_chart = agent._analyze(
        {**base_state, "message": "Explain release frequency for 2022"}  # type: ignore[arg-type]
    )
    with_chart = agent._analyze(
        {**base_state, "message": "Create a pie chart for 2022"}  # type: ignore[arg-type]
    )
    assert without_chart["chart"] is None
    assert with_chart["chart"]["type"] == "pie"
    assert without_chart["table"] is None

    with_table = agent._analyze(
        {**base_state, "message": "Show release frequency as a table for 2022"}  # type: ignore[arg-type]
    )
    assert with_table["table"]["title"] == "Supporting data"


def test_answer_validation_accepts_deterministic_analysis_numbers() -> None:
    validation = validate_answer(
        "The metric improved by 20%.",
        results=[{"query_id": "dora_metrics_by_year", "rows": []}],
        analysis={"comparisons": [{"percent_change": -20.0}]},
        question="How did it change?",
        required_warnings=[],
    )
    assert validation["valid"] is True


def test_reworded_warning_still_counts_as_conveyed() -> None:
    """The responder is told to reword limitations into plain business
    language, so the validator must accept a reworded warning -- a verbatim
    prefix check would have forced raw validator strings at the user."""

    reworded = (
        "These squad names are reporting labels rather than an official team "
        "directory, so they may not match your org chart exactly."
    )
    validation = validate_answer(
        reworded,
        results=[{"query_id": "jira_distinct_squads", "rows": []}],
        analysis={},
        question="list all squad",
        required_warnings=[
            "Jira dcpsquad values are not confirmed as an authoritative "
            "organisation-wide squad directory."
        ],
    )
    assert validation["warning_missing"] is False

    omitted = validate_answer(
        "I found the requested squad names.",
        results=[{"query_id": "jira_distinct_squads", "rows": []}],
        analysis={},
        question="list all squad",
        required_warnings=[
            "Jira dcpsquad values are not confirmed as an authoritative "
            "organisation-wide squad directory."
        ],
    )
    assert omitted["warning_missing"] is True


def test_every_required_warning_must_be_conveyed() -> None:
    validation = validate_answer(
        "Nothing matched the current filters.",
        results=[{"query_id": "jira_distinct_squads", "rows": []}],
        analysis={},
        question="list all squad",
        required_warnings=[
            "jira_distinct_squads returned no matching rows.",
            "Jira dcpsquad values are not confirmed as an authoritative "
            "organisation-wide squad directory.",
        ],
    )
    assert validation["warning_missing"] is True


def test_cached_llm_answer_is_still_evidence_validated() -> None:
    agent = AdvancedDoraDbAgent.__new__(AdvancedDoraDbAgent)
    result = agent._validate_answer(
        {
            "answer": "I found 999 squads.",
            "answer_source": "conversation-cache",
            "message": "How many did you find?",
            "plan": {"mode": "data"},
            "results": [
                {
                    "query_id": "jira_distinct_squads",
                    "rows": [{"dcpsquad": "TITAN"}],
                    "row_count": 1,
                }
            ],
            "analysis": {},
            "warnings": [],
        }  # type: ignore[arg-type]
    )
    assert result["answer_validation"]["unsupported_numbers"] == ["999"]
    assert result["answer_validation"]["valid"] is False


def test_unnecessary_clarification_recovers_via_deterministic_router() -> None:
    """Regression: the planner prompt says "NEVER set mode='conversation' for
    a data question", but the model still answered "LIST SQUAD" with a
    clarifying question and zero queries. Prompt text is not enforcement, so
    an unnecessary clarification on a request the deterministic router
    unambiguously recognizes must recover into a real query."""

    class OverClarifyingLlm:
        enabled = True
        source = "test-provider:test-model"

        @staticmethod
        def complete(*_args: object, **_kwargs: object) -> str:
            return (
                '{"mode":"clarification","intent":"DATA_RETRIEVAL",'
                '"confidence":0.9,"reason":"needs scope",'
                '"clarification":"Which scope did you mean?","actions":[]}'
            )

    plan, source = create_plan(
        "LIST SQUAD",
        memory={},
        browser_history=[],
        llm=OverClarifyingLlm(),  # type: ignore[arg-type]
    )

    assert plan["mode"] == "data"
    assert source == "deterministic-recovery"
    assert [a["query_id"] for a in plan["actions"]] == [
        "database_squad_sources",
        "jira_distinct_squads",
    ]


def test_recovery_never_overrides_a_deliberate_conversation_plan() -> None:
    """A capability question ("what data CAN I get") is deliberately answered
    conversationally. Recovery must not turn it into a data query even though
    the deterministic router would match the word "squad"."""

    class CapabilityLlm:
        enabled = True
        source = "test-provider:test-model"

        @staticmethod
        def complete(*_args: object, **_kwargs: object) -> str:
            return (
                '{"mode":"conversation","intent":"CAPABILITY_EXPLANATION",'
                '"confidence":0.99,"reason":"capability","clarification":"",'
                '"actions":[]}'
            )

    plan, _ = create_plan(
        "Other than bug volume, what more data can I get for each squad?",
        memory={},
        browser_history=[],
        llm=CapabilityLlm(),  # type: ignore[arg-type]
    )

    assert plan["mode"] == "conversation"
    assert plan["actions"] == []


def test_recovery_never_overrides_an_out_of_scope_decision() -> None:
    """Safety decisions are never second-guessed by keyword recovery."""

    class UnsafeEchoLlm:
        enabled = True
        source = "test-provider:test-model"

        @staticmethod
        def complete(*_args: object, **_kwargs: object) -> str:
            return "{}"

    plan, source = create_plan(
        "Delete all squad rows from the database",
        memory={},
        browser_history=[],
        llm=UnsafeEchoLlm(),  # type: ignore[arg-type]
    )

    assert plan["mode"] == "out_of_scope"
    assert source == "scope-guard"
    assert plan["actions"] == []


def test_all_squad_metric_questions_use_the_all_squads_query() -> None:
    """Regression: dora_metrics_by_squad returns ONE squad per call and the
    per-turn tool-call budget is 2, so "same delivery metric for all squads"
    silently reported on one squad and made the other 20 look like they had
    no data. An all-squads question must use the single-query variant."""

    from backend.agent.request_router import route_jira_request

    for message in [
        "pull the same delivery metric to all squad",
        "compare the squads delivery performance",
        "show DORA metrics for each squad",
    ]:
        plan = route_jira_request(message)
        assert plan is not None, message
        assert [a["query_id"] for a in plan["actions"]] == ["dora_metrics_all_squads"]
        # No dcpsquad filter -- that would collapse it back to one squad.
        assert "dcpsquad" not in plan["actions"][0]["filters"]


def test_listing_squads_is_not_hijacked_by_the_metrics_route() -> None:
    """"list all the squad" wants the squad names, not DORA measures."""

    from backend.agent.request_router import route_jira_request

    plan = route_jira_request("list all the squad")
    assert plan is not None
    assert [a["query_id"] for a in plan["actions"]] == [
        "database_squad_sources",
        "jira_distinct_squads",
    ]
