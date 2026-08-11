"""Response Controller behavior checks.

Mirrors the checklist in AI_AGENT_PROJECT_RESTRUCTURING_GUIDE.md Section 45:
simple question -> short/direct, "why?" follow-up -> preserve context,
"make it a table" -> format-only change, correction -> replace context,
comparison -> table, uncertain data -> explicit uncertainty, greeting ->
no evidence required, out-of-scope -> concise, language matching.
"""

from __future__ import annotations

from backend.agent.controls.response_controller import derive_policy


def _plan(mode: str, intent: str, **extra: object) -> dict[str, object]:
    return {
        "mode": mode,
        "intent": intent,
        "confidence": 0.9,
        "actions": [],
        "reason": "test",
        "clarification": "",
        **extra,
    }


def test_greeting_is_short_and_needs_no_evidence() -> None:
    policy = derive_policy("hi there", plan=_plan("conversation", "greeting"))
    assert policy["length"] == "short"
    assert policy["evidence_style"] == "none_required"
    assert policy["is_follow_up"] is False


def test_out_of_scope_is_short_and_needs_no_evidence() -> None:
    policy = derive_policy(
        "Can you delete the database?", plan=_plan("out_of_scope", "unsafe_request")
    )
    assert policy["length"] == "short"
    assert policy["evidence_style"] == "none_required"


def test_why_follow_up_preserves_context_and_deepens_explanation() -> None:
    policy = derive_policy(
        "why?",
        plan=_plan("data", "metric_lookup"),
        cache_reason="eligible_follow_up",
        query_result_reused=True,
        results=[{"query_id": "dora_metrics_by_year", "rows": [{"release_year": 2025}], "row_count": 1}],
    )
    assert policy["is_follow_up"] is True
    assert policy["context_reference"] is True
    assert policy["follow_up_type"] == "deeper_explanation"


def test_make_it_a_table_is_a_format_change_not_a_new_request() -> None:
    policy = derive_policy(
        "make it a table",
        plan=_plan("data", "metric_lookup"),
        cache_reason="eligible_follow_up",
        query_result_reused=True,
        results=[{"query_id": "dora_metrics_by_year", "rows": [{"release_year": 2025}], "row_count": 1}],
    )
    assert policy["is_follow_up"] is True
    assert policy["follow_up_type"] == "format_change"
    assert policy["format"] == "table"


def test_user_correction_is_detected_regardless_of_cache_state() -> None:
    policy = derive_policy(
        "That's wrong, the squad is Jaeger not Titan.",
        plan=_plan("data", "metric_lookup"),
    )
    assert policy["follow_up_type"] == "correction"


def test_comparison_intent_prefers_a_table() -> None:
    policy = derive_policy(
        "Compare release frequency between 2025 and 2026",
        plan=_plan("data", "comparison"),
        results=[{"query_id": "dora_metrics_by_year", "rows": [{}, {}], "row_count": 2}],
    )
    assert policy["format"] == "table"


def test_zero_rows_or_warnings_trigger_explicit_uncertainty() -> None:
    empty_result_policy = derive_policy(
        "How many releases happened in 2019?",
        plan=_plan("data", "metric_lookup"),
        results=[{"query_id": "dora_metrics_by_year", "rows": [], "row_count": 0}],
    )
    assert empty_result_policy["uncertainty_mode"] == "explicit"

    warned_policy = derive_policy(
        "How many releases happened in 2026?",
        plan=_plan("data", "metric_lookup"),
        results=[{"query_id": "dora_metrics_by_year", "rows": [{"release_year": 2026}], "row_count": 1}],
        warnings=["2026 is the current calendar year and may be incomplete."],
    )
    assert warned_policy["uncertainty_mode"] == "explicit"


def test_confident_results_do_not_add_unnecessary_uncertainty() -> None:
    policy = derive_policy(
        "What was release frequency in 2022?",
        plan=_plan("data", "metric_lookup"),
        results=[{"query_id": "dora_metrics_by_year", "rows": [{"release_year": 2022}], "row_count": 1}],
    )
    assert policy["uncertainty_mode"] == "normal"


def test_recommendation_intent_grounds_recommendations_in_evidence() -> None:
    policy = derive_policy(
        "Suggest improvements for the Jaeger squad",
        plan=_plan("data", "recommendation"),
        results=[{"query_id": "dora_metrics_by_squad", "rows": [{"dcpsquad": "JAEGER"}], "row_count": 1}],
    )
    assert policy["recommendation_mode"] == "evidence_based"

    no_evidence_policy = derive_policy(
        "Suggest improvements",
        plan=_plan("clarification", "clarify_recommendation_scope"),
    )
    assert no_evidence_policy["recommendation_mode"] == "none"


def test_malay_message_is_flagged_for_malay_response() -> None:
    policy = derive_policy(
        "Berapa banyak bug yang ada?",
        plan=_plan("data", "metric_lookup"),
    )
    assert policy["language"] == "ms"


def test_english_message_defers_to_match_user_language() -> None:
    policy = derive_policy(
        "How many bugs are there?",
        plan=_plan("data", "metric_lookup"),
    )
    assert policy["language"] == "match_user"


def test_explicit_length_and_explanation_requests_are_honored() -> None:
    short_policy = derive_policy(
        "Just give me the answer, briefly.",
        plan=_plan("data", "metric_lookup"),
    )
    assert short_policy["length"] == "short"

    detailed_policy = derive_policy(
        "Explain this in depth and in full detail.",
        plan=_plan("data", "explanation"),
    )
    assert detailed_policy["length"] == "detailed"

    technical_policy = derive_policy(
        "Give me a technical explanation of lead time.",
        plan=_plan("conversation", "knowledge_explanation"),
    )
    assert technical_policy["explanation_level"] == "technical"


def test_policy_always_carries_plain_language_rules() -> None:
    """Every rendered policy must carry the plain-language rules, because
    describe_policy() is injected into every LLM call in the app -- data
    answers, follow-ups, knowledge answers and error explanations alike."""

    from backend.agent.controls.response_controller import describe_policy

    rendered = describe_policy(
        derive_policy("list all squad", plan=_plan("data", "data_retrieval"))
    ).lower()
    assert "delivery manager" in rendered
    assert "database administrator" in rendered
    assert "dcpsquad" in rendered  # named as an example of what NOT to say
    assert "plumbing" in rendered


def test_domain_noun_table_is_not_treated_as_a_format_request() -> None:
    """Regression: this app's domain is full of database tables, so a bare
    'table' in the question must not switch the answer format to a table."""

    for message in [
        "What does the Jira issues table represent, and what does one row mean?",
        "What tables exist in the database?",
        "explain the table structure",
    ]:
        policy = derive_policy(message, plan=_plan("data", "metric_lookup"))
        assert policy["format"] != "table", message


def test_policy_always_carries_structure_rules() -> None:
    """describe_policy() reaches every LLM call, so layout rules must ride
    along with every answer, not just the main data prompt."""

    from backend.agent.controls.response_controller import describe_policy

    rendered = describe_policy(
        derive_policy("list all the squad", plan=_plan("data", "DATA_RETRIEVAL"))
    ).lower()
    assert "one-sentence direct answer" in rendered
    assert "markdown bullet list" in rendered
    assert "wall of text" in rendered


def test_enumeration_requests_use_bullets_for_live_intent_names() -> None:
    """Regression: _detect_format only knew the retired lowercase planner
    intents ("discovery"), so every live uppercase intent fell through to
    "paragraph" and 21-item lists were rendered as inline comma prose."""

    for intent in ["DATA_RETRIEVAL", "LIST_SQUADS", "DATABASE_METADATA"]:
        policy = derive_policy("list all the squad", plan=_plan("data", intent))
        assert policy["format"] == "bullets", intent

    # Legacy lowercase vocabulary must keep working too.
    assert derive_policy(
        "list all squads", plan=_plan("data", "discovery")
    )["format"] == "bullets"


def test_non_enumeration_question_stays_paragraph() -> None:
    """An explanatory question must not be forced into a bullet list."""

    policy = derive_policy(
        "What does the Jira issues table represent, and what does one row mean?",
        plan=_plan("conversation", "KNOWLEDGE_EXPLANATION"),
    )
    assert policy["format"] == "paragraph"


def test_recommendation_detected_under_live_intent_names() -> None:
    """Regression: recommendation_mode/evidence_style only knew the retired
    lowercase "recommendation" intent, so live uppercase intents always gave
    recommendation_mode="none" and the evidence-grounding guidance never
    reached the model."""

    results = [{"query_id": "dora_metrics_by_squad", "rows": [{"a": 1}], "row_count": 1}]
    for message in [
        "Suggest improvements for the Jaeger squad",
        "What should we do to improve delivery?",
        "How can the team improve?",
    ]:
        policy = derive_policy(
            message, plan=_plan("data", "ANALYSIS"), results=results
        )
        assert policy["recommendation_mode"] == "evidence_based", message
        assert policy["evidence_style"] == "detailed_evidence", message


def test_plain_metric_question_is_not_treated_as_a_recommendation() -> None:
    """ANALYSIS is the generic intent for most data questions, so it must not
    by itself mark a request as a recommendation."""

    results = [{"query_id": "dora_metrics_by_year", "rows": [{"a": 1}], "row_count": 1}]
    policy = derive_policy(
        "What was release frequency in 2022?",
        plan=_plan("data", "ANALYSIS"),
        results=results,
    )
    assert policy["recommendation_mode"] == "none"
    assert policy["evidence_style"] == "metric_support"
