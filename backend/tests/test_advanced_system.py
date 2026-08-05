from datetime import date

from backend.agent_system.control import enforce_plan, public_policy
from backend.agent_system.graph import (
    AI_UNAVAILABLE_MESSAGE,
    AdvancedDoraDbAgent,
    _discovery_answer,
    _is_holistic_request,
    _wants_table,
)
from backend.agent_system.memory import SessionMemoryStore
from backend.agent_system.planner import create_plan, deterministic_plan
from backend.agent_system.result_validator import validate_answer, validate_results
from backend.context import load_context
from backend.doradb import _build_statement, _normalize_filters
from backend.doradb_catalog import DISCOVERY_DIMENSIONS
from backend.skills import (
    analyze_trend,
    build_chart_spec,
    classify_intent,
    compare_rows,
    detect_anomalies,
    extract_filters,
    filter_value_is_grounded,
    match_discovery_dimension,
    resolve_entities,
    select_metric,
)


def test_runtime_data_dictionary_covers_every_discoverable_dimension() -> None:
    context = load_context("data_dictionary.yaml")
    assert set(context["dimensions"]) == set(DISCOVERY_DIMENSIONS)
    assert context["entities"]["tbl_gdt_dte_jira_issues"]["grain"]


def test_discovery_language_routes_every_governed_dimension() -> None:
    cases = {
        "What projects are available?": "project",
        "Can you list all the squad that you have?": "squad",
        "Which release years exist?": "release_year",
        "List all releases": "release",
        "What issue types do you have?": "issue_type",
        "List all available statuses": "status",
        "What DORA metrics are supported?": "metric",
    }
    for question, dimension in cases.items():
        assert match_discovery_dimension(question) == dimension
        plan = deterministic_plan(question, {"last_context": {}})
        assert plan["mode"] == "data"
        assert plan["intent"] == "discovery"
        assert plan["actions"][0]["query_id"] == "list_dimension_values"
        assert plan["actions"][0]["filters"]["dimension"] == dimension


def test_discovery_does_not_inherit_stale_dimension_memory() -> None:
    plan = deterministic_plan(
        "List all the squads that you have",
        {
            "last_context": {
                "metric": "release_frequency",
                "filters": {"project_key": "DCPM", "dcpsquad": "JAEGER"},
                "query_ids": ["dora_metrics_by_squad"],
            }
        },
    )
    assert plan["actions"][0]["filters"] == {
        "dimension": "squad",
        "project_key": "DCPM",
    }


def test_generic_words_are_not_extracted_as_squad_names() -> None:
    for question in (
        "List all the squad that you have",
        "Which squad is available?",
        "Show every team recorded in the database",
    ):
        assert "dcpsquad" not in extract_filters(question)
    assert extract_filters("Show squad Droid Spark")["dcpsquad"] == "DROID SPARK"
    assert (
        extract_filters("Analyze data for the HIVE KNIGHT squad")["dcpsquad"]
        == "HIVE KNIGHT"
    )
    assert "fixversion" not in extract_filters("Show release that you have")
    assert match_discovery_dimension("Show me the releases") == "release"
    assert match_discovery_dimension("Give me all known teams") == "squad"


def test_generative_planner_owns_valid_discovery_plan() -> None:
    class DiscoveryLlm:
        enabled = True
        source = "deepseek:test"

        @staticmethod
        def complete(*_args: object, **_kwargs: object) -> str:
            return (
                '{"mode":"data","intent":"discover_available_squads",'
                '"confidence":0.95,"reason":"The user wants current squad names",'
                '"clarification":"","actions":[{"query_id":'
                '"list_dimension_values","filters":{"dimension":"squad"},'
                '"limit":100,"reason":"Retrieve the governed squad dimension"}]}'
            )

    plan, source = create_plan(
        "List all the squads that you have",
        memory={},
        browser_history=[],
        llm=DiscoveryLlm(),  # type: ignore[arg-type]
    )
    assert source == "deepseek:test"
    assert plan["intent"] == "discover_available_squads"
    assert plan["actions"][0]["query_id"] == "list_dimension_values"
    assert plan["actions"][0]["filters"]["dimension"] == "squad"


def test_invalid_ai_discovery_tool_falls_back_to_governed_plan() -> None:
    class InvalidToolLlm:
        enabled = True
        source = "deepseek:test"

        @staticmethod
        def complete(*_args: object, **_kwargs: object) -> str:
            return (
                '{"mode":"data","intent":"discover_squads","confidence":0.95,'
                '"reason":"Use an invented tool","clarification":"","actions":['
                '{"query_id":"semantic_sql_search","filters":{},'
                '"limit":100,"reason":"invalid"}]}'
            )

    plan, source = create_plan(
        "List all the squads that you have",
        memory={},
        browser_history=[],
        llm=InvalidToolLlm(),  # type: ignore[arg-type]
    )
    assert source == "deterministic-safety-fallback"
    assert plan["intent"] == "discovery"
    assert plan["actions"][0]["query_id"] == "list_dimension_values"


def test_discovery_filter_validation_is_allowlisted_and_supports_spaced_squads() -> None:
    filters = _normalize_filters(
        "list_dimension_values",
        {"dimension": "status", "project_key": "DCPM"},
    )
    assert filters["dimension"] == "status"

    squad_filters = _normalize_filters(
        "dora_metrics_by_squad",
        {"dcpsquad": "Droid Spark", "project_key": "DCPM"},
    )
    assert squad_filters["dcpsquad"] == "DROID SPARK"

    statement, params = _build_statement(
        "list_dimension_values",
        {"dimension": "metric", "project_key": "DCPM"},
        100,
    )
    assert "CAST(:metric_0 AS text)" in statement
    assert params["metric_0"] == "release_frequency"


def test_empty_discovery_answer_never_generalizes_to_an_empty_database() -> None:
    answer = _discovery_answer(
        {
            "query_id": "list_dimension_values",
            "filters": {"dimension": "status", "project_key": "DCPM"},
            "rows": [],
        }
    )
    assert "No matching status values" in answer
    assert "does not mean the rest of DoraDB is empty" in answer


def test_deepseek_synthesizes_discovery_answer_with_deterministic_outage_fallback() -> None:
    result = {
        "query_id": "list_dimension_values",
        "filters": {"dimension": "squad", "project_key": "DCPM"},
        "rows": [
            {
                "dimension": "squad",
                "value": "JAEGER",
                "record_count": 12,
                "total_values": 2,
            },
            {
                "dimension": "squad",
                "value": "TITAN",
                "record_count": 10,
                "total_values": 2,
            },
        ],
        "row_count": 2,
    }
    state = {
        "message": "List all the squads",
        "plan": {
            "mode": "data",
            "intent": "discover_squads",
            "confidence": 0.95,
            "actions": [],
            "reason": "test",
            "clarification": "",
        },
        "validation": {"valid": True},
        "results": [result],
        "metric": select_metric("release frequency"),
        "memory": {},
        "analysis": {},
        "chart": None,
        "browser_history": [],
    }

    class DiscoveryResponseLlm:
        enabled = True
        source = "deepseek:test"

        @staticmethod
        def complete(*_args: object, **_kwargs: object) -> str:
            return "The available squads are JAEGER and TITAN."

    agent = AdvancedDoraDbAgent.__new__(AdvancedDoraDbAgent)
    agent.llm = DiscoveryResponseLlm()  # type: ignore[assignment]
    response = agent._respond(state)  # type: ignore[arg-type]
    assert response["answer_source"] == "deepseek:test"
    assert response["answer"] == "The available squads are JAEGER and TITAN."

    class UnavailableResponseLlm:
        enabled = True
        source = "deepseek:test"

        @staticmethod
        def complete(*_args: object, **_kwargs: object) -> None:
            return None

    agent.llm = UnavailableResponseLlm()  # type: ignore[assignment]
    fallback = agent._respond(state)  # type: ignore[arg-type]
    assert fallback["answer_source"] == "deterministic-discovery"
    assert "JAEGER" in fallback["answer"]


def test_context_files_expose_formal_skill_pipeline() -> None:
    context = load_context("skills.yaml")
    assert context["pipeline"][:2] == ["entity_grounding", "context_resolution"]
    assert context["pipeline"][-1] == "summarisation"
    assert context["controls"] == [
        "plan_validation",
        "result_validation",
        "answer_validation",
    ]


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
            "entities": {"squad": ["MBK"]},
            "discovered_values": {"squad": ["MBK", "NAGA"]},
            "raw_results": [{"secret": "must not be stored"}],
        },
    )
    memory = store.get("session-test")
    assert memory["last_context"]["metric"] == "release_frequency"
    assert "raw_results" not in memory["last_context"]
    assert memory["last_context"]["discovered_values"]["squad"] == ["MBK", "NAGA"]
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


def test_explicit_data_request_uses_deepseek_first_then_safe_fallback() -> None:
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

    assert source == "deepseek:deepseek-v4-flash"
    assert llm.calls == 1
    assert plan["mode"] == "data"
    assert plan["actions"][0]["query_id"] == "dora_metrics_by_year"


def test_deepseek_can_answer_broad_analysis_without_forced_year_clarification() -> None:
    class AnalyticalLlm:
        enabled = True
        source = "deepseek:test"

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

    assert source == "deepseek:test"
    assert plan["mode"] == "data"
    assert plan["intent"] == "risk_analysis"
    assert plan["actions"][0]["query_id"] == "dora_metrics_by_year"
    assert plan["actions"][0]["filters"]["project_key"] == "DCPM"


def test_deepseek_multi_query_plan_survives_allowlist_controls() -> None:
    class MultiQueryLlm:
        enabled = True
        source = "deepseek:test"

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
    assert explicit["actions"][0]["query_id"] == "list_dimension_values"
    assert explicit["actions"][0]["filters"]["dimension"] == "release_year"


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


def test_unrelated_question_is_semantically_scoped_by_cloud_planning() -> None:
    class CountingLlm:
        enabled = True
        calls = 0

        def complete(self, *_args: object, **_kwargs: object) -> str:
            self.calls += 1
            return (
                '{"mode":"out_of_scope","intent":"out_of_context",'
                '"confidence":0.99,"reason":"Unrelated to the governed domain",'
                '"clarification":"","actions":[]}'
            )

    llm = CountingLlm()
    plan, source = create_plan(
        "What date is today?",
        memory={},
        browser_history=[],
        llm=llm,  # type: ignore[arg-type]
    )
    assert plan["mode"] == "out_of_scope"
    assert source == "deepseek:deepseek-v4-flash"
    assert llm.calls == 1


def test_live_entities_are_grounded_across_every_filterable_dimension() -> None:
    catalogue = {
        "project": ["DCPM"],
        "squad": ["MBK", "Droid Spark", "NAGA"],
        "release_year": ["2025", "2026"],
        "release": ["R-4.2.0"],
        "issue_type": ["Bug", "User Story"],
        "status": ["In Progress", "Done"],
        "metric": ["release_frequency", "change_failure_rate"],
    }
    cases = {
        "Show mbk performance": ("dcpsquad", "MBK"),
        "Analyze Droid Spark": ("dcpsquad", "Droid Spark"),
        "Explain release R-4.2.0": ("fixversion", "R-4.2.0"),
        "List Bug issues": ("issuetype", "Bug"),
        "Show work In Progress": ("status", "In Progress"),
        "Compare release frequency in 2025": ("release_year", [2025]),
    }
    for message, (filter_name, expected) in cases.items():
        grounding = resolve_entities(message, catalogue)
        assert grounding["filters"][filter_name] == expected


def test_any_live_squad_name_routes_to_squad_metrics_without_hardcoding() -> None:
    catalogue = {"squad": ["MBK", "NAGA", "HIVE KNIGHT"]}
    for squad in catalogue["squad"]:
        plan = deterministic_plan(
            f"Show {squad.lower()} performance",
            {"last_context": {}},
            entity_catalogue=catalogue,
        )
        assert plan["mode"] == "data"
        assert plan["actions"][0]["query_id"] == "dora_metrics_by_squad"
        assert plan["actions"][0]["filters"]["dcpsquad"] == squad


def test_definition_of_previous_answer_term_is_a_contextual_follow_up() -> None:
    memory = {
        "turns": [
            {
                "user": "Analyze 2026",
                "assistant": "There are two important caveats for the year-to-date figures.",
            }
        ],
        "last_context": {
            "metric": "release_frequency",
            "filters": {"project_key": "DCPM", "release_year": [2026]},
            "query_ids": ["dora_metrics_by_year"],
        },
    }
    plan = deterministic_plan("What is caveats?", memory)
    assert plan["mode"] == "conversation"
    assert plan["intent"] == "context_follow_up"


def test_model_can_compare_multiple_grounded_values_in_one_dimension() -> None:
    class ComparisonLlm:
        enabled = True
        source = "deepseek:test"

        @staticmethod
        def complete(*_args: object, **_kwargs: object) -> str:
            return (
                '{"mode":"data","intent":"squad_comparison","confidence":0.96,'
                '"reason":"Compare both grounded squads","clarification":"",'
                '"actions":['
                '{"query_id":"dora_metrics_by_squad","filters":{"dcpsquad":"MBK"},'
                '"limit":10,"reason":"MBK evidence"},'
                '{"query_id":"dora_metrics_by_squad","filters":{"dcpsquad":"NAGA"},'
                '"limit":10,"reason":"NAGA evidence"}]}'
            )

    catalogue = {"squad": ["MBK", "NAGA"]}
    plan, _ = create_plan(
        "Compare MBK and NAGA performance",
        memory={},
        browser_history=[],
        llm=ComparisonLlm(),  # type: ignore[arg-type]
        entity_catalogue=catalogue,
    )
    assert [action["filters"]["dcpsquad"] for action in plan["actions"]] == [
        "MBK",
        "NAGA",
    ]


def test_hallucinated_model_entity_is_not_executed() -> None:
    class HallucinatingLlm:
        enabled = True
        source = "deepseek:test"

        @staticmethod
        def complete(*_args: object, **_kwargs: object) -> str:
            return (
                '{"mode":"data","intent":"squad_performance","confidence":0.96,'
                '"reason":"query squad","clarification":"","actions":['
                '{"query_id":"dora_metrics_by_squad",'
                '"filters":{"dcpsquad":"GHOST"},"limit":10,"reason":"test"}]}'
            )

    plan, _ = create_plan(
        "Show Ghost performance",
        memory={},
        browser_history=[],
        llm=HallucinatingLlm(),  # type: ignore[arg-type]
        entity_catalogue={"squad": ["MBK", "NAGA"]},
    )
    assert plan["mode"] == "clarification"
    assert plan["intent"] == "unknown_entity"
    assert plan["actions"] == []
    assert filter_value_is_grounded("dcpsquad", "GHOST", {"squad": ["MBK"]}) is False

    explicit_unknown = deterministic_plan(
        "Show squad GHOST performance",
        {"last_context": {}},
        entity_catalogue={"squad": ["MBK", "NAGA"]},
    )
    assert explicit_unknown["mode"] == "clarification"
    assert explicit_unknown["intent"] == "unknown_entity"


def test_small_discovery_does_not_force_an_evidence_table() -> None:
    results = [{"query_id": "list_dimension_values", "row_count": 5, "rows": []}]
    assert _wants_table("List squads", "discovery", results) is False
    assert _wants_table("List squads as a table", "discovery", results) is True


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


def test_answer_validation_rejects_completed_year_as_year_to_date() -> None:
    completed_year = date.today().year - 1
    validation = validate_answer(
        f"{completed_year} has one release so far and is still in progress.",
        results=[
            {
                "query_id": "dora_metrics_by_year",
                "rows": [{"release_year": completed_year, "release_count": 1}],
            }
        ],
        analysis={},
        question="Explain the yearly result",
        required_warnings=[],
    )
    assert validation["valid"] is False
    assert validation["temporal_errors"]

    provisional = validate_answer(
        f"The {completed_year} result is provisional until more releases accumulate.",
        results=[
            {
                "query_id": "dora_metrics_by_year",
                "rows": [{"release_year": completed_year, "release_count": 1}],
            }
        ],
        analysis={},
        question="Explain the yearly result",
        required_warnings=[],
    )
    assert provisional["valid"] is False
    assert provisional["temporal_errors"]


def test_current_year_results_receive_incomplete_period_warning() -> None:
    current_year = date.today().year
    report = validate_results(
        [
            {
                "query_id": "dora_metrics_by_year",
                "rows": [
                    {
                        "release_year": current_year,
                        "release_count": 1,
                        "release_frequency_months": 2.0,
                        "change_failure_rate_pct": 0.0,
                        "lead_time_for_change_months": 1.0,
                        "delivery_cycle_time_months": 4.0,
                        "user_story_count": 1,
                        "feature_reference_count": 1,
                        "feature_reference_release_count": 1,
                    }
                ],
                "warnings": [],
            }
        ]
    )
    assert any(str(current_year) in warning for warning in report["warnings"])
