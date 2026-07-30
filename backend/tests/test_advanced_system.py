from backend.agent_system.control import enforce_plan, public_policy
from backend.agent_system.graph import (
    AI_UNAVAILABLE_MESSAGE,
    AdvancedDoraDbAgent,
    _is_holistic_request,
)
from backend.agent_system.memory import SessionMemoryStore
from backend.agent_system.planner import create_plan, deterministic_plan
from backend.agent_system.result_validator import validate_answer, validate_results
from backend.context import load_context
from backend.skills import (
    analyze_trend,
    build_chart_spec,
    classify_intent,
    compare_rows,
    detect_anomalies,
    extract_filters,
    select_metric,
)


def test_context_files_expose_formal_skill_pipeline() -> None:
    context = load_context("skills.yaml")
    assert "result_validation" not in context["pipeline"]
    assert context["pipeline"][-1] == "summarisation"
    assert len(context["pipeline"]) == 9


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


def test_explicit_data_request_uses_gemini_first_then_safe_fallback() -> None:
    class ConversationOnlyLlm:
        enabled = True
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

    assert source == "google-ai-studio:gemini-3.6-flash"
    assert llm.calls == 1
    assert plan["mode"] == "data"
    assert plan["actions"][0]["query_id"] == "dora_metrics_by_year"


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


def test_broad_metric_clarifies_but_explicit_count_executes() -> None:
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
    assert explicit["mode"] == "data"
    assert explicit["actions"][0]["query_id"] == "dora_metrics_by_year"


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
    action = plan["actions"][0]
    assert action["query_id"] == "dora_metrics_by_squad"
    assert action["filters"]["project_key"] == "DCPM"
    assert action["filters"]["dcpsquad"] == "TITAN"


def test_release_date_filter_accepts_malaysian_day_month_format() -> None:
    filters = extract_filters("Show the release on 24/9/2025")
    assert filters["release_date"] == "2025-09-24"
    assert filters["release_year"] == [2025]


def test_release_frequency_is_not_misread_as_a_fixversion() -> None:
    filters = extract_filters("Can you talk about release frequency?")
    assert filters == {"project_key": "DCPM"}


def test_unrelated_question_is_stopped_before_cloud_planning() -> None:
    class CountingLlm:
        enabled = True
        calls = 0

        def complete(self, *_args: object, **_kwargs: object) -> str:
            self.calls += 1
            return "{}"

    llm = CountingLlm()
    plan, source = create_plan(
        "What date is today?",
        memory={},
        browser_history=[],
        llm=llm,  # type: ignore[arg-type]
    )
    assert plan["mode"] == "out_of_scope"
    assert source == "scope-guard"
    assert llm.calls == 0


def test_agent_never_substitutes_a_template_when_ai_is_unavailable() -> None:
    class UnavailableLlm:
        enabled = True
        last_model = None

        @staticmethod
        def complete(*_args: object, **_kwargs: object) -> None:
            return None

    agent = AdvancedDoraDbAgent.__new__(AdvancedDoraDbAgent)
    agent.llm = UnavailableLlm()  # type: ignore[assignment]
    response = agent._respond(
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
    assert response["answer"] == AI_UNAVAILABLE_MESSAGE
    assert response["answer_source"] == "ai-provider-unavailable"
    assert "Found" not in response["answer"]
    assert "Recommended priorities" not in response["answer"]

    clarification = agent._respond(
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
    assert clarification["answer"] == AI_UNAVAILABLE_MESSAGE
    assert "Which squad" not in clarification["answer"]


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
