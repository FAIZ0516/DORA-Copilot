"""The AI may rewrite language. It may not change the facts.

These cover the guard that separates "rewrite for clarity" from "silently
alter the numbers", plus the strict schema that stops raw model JSON being
trusted.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.services.report_composition import (
    classification_issues,
    compose_sections,
    extract_numbers,
    fact_check,
    normalize_number,
    parse_refinement_response,
    parse_response,
)
from backend.services.report_evidence import detect_scope_conflicts, staleness


class _Llm:
    """Stand-in provider returning a scripted response."""

    enabled = True
    source = "test:script"

    def __init__(self, payload: str) -> None:
        self._payload = payload
        self.calls = 0
        self.last_system = ""
        self.last_user = ""

    def complete(self, system: str, user: str, **_kwargs: object) -> str:
        self.calls += 1
        self.last_system = system
        self.last_user = user
        return self._payload


SECTIONS = [
    {
        "id": "sec-1",
        "type": "executive_summary",
        "title": "Summary",
        "content_mode": "rewrite",
        "content_classification": "interpretation",
        "manually_edited": False,
        "visible": True,
    }
]
SOURCES = [
    {
        "id": "src-1",
        "label": "TITAN progress",
        "scope": {"project": "DCPM", "squad": "TITAN"},
        "evidence": {
            "question": "How is TITAN progressing?",
            "answer": "TITAN has completed 812 of 1,876 tickets, which is 43.2%.",
            "warnings": [],
        },
    }
]

ORIGINAL = "TITAN has completed 812 of 1,876 tickets, which is 43.2%."


def test_numbers_are_compared_by_value_not_by_spelling() -> None:
    assert normalize_number("1,876") == normalize_number("1876")
    assert normalize_number("43.20%") == normalize_number("43.2%")
    # A percentage is not the same figure as the bare number.
    assert normalize_number("43.2%") != normalize_number("43.2")
    assert extract_numbers("812 of 1,876 (43.2%)") == {"812", "1876", "43.2%"}


def test_a_rewrite_may_reword_and_shorten() -> None:
    assert fact_check(ORIGINAL, "TITAN reached 43.2% completion, closing 812 of 1876 tickets.") == []
    # Summarising away a figure is a legitimate mode, not a fault.
    assert fact_check(ORIGINAL, "TITAN is at 43.2% completion.") == []
    assert fact_check(ORIGINAL, "Delivery progressed during the period.") == []


def test_a_rewrite_may_not_invent_a_figure() -> None:
    issues = fact_check(ORIGINAL, "TITAN completed 812 tickets and 9 releases shipped.")
    assert issues and "9" in issues[0]


def test_an_altered_number_is_caught() -> None:
    issues = fact_check("TITAN has completed 812 of 1,876 tickets.", "TITAN has completed 912 of 1,876 tickets.")
    assert issues and "912" in issues[0]


def test_observed_facts_may_not_carry_recommendation_language() -> None:
    assert classification_issues("observed_fact", "The squad has 12 open bugs.") == []
    issues = classification_issues("observed_fact", "The squad should triage its 12 open bugs.")
    assert issues and "recommendation" in issues[0].lower()
    # A recommendation block is allowed to recommend.
    assert classification_issues("recommendation", "The squad should triage its bugs.") == []


def test_model_json_is_validated_not_trusted() -> None:
    assert parse_response(None) is None
    assert parse_response("not json at all") is None
    assert parse_response('{"sections": "wrong type"}') is None
    parsed = parse_response('{"sections":[{"section_id":"a","title":"T","content":"C"}]}')
    assert parsed is not None
    assert parsed.sections[0].section_id == "a"
    # Prose wrapped around the JSON object is tolerated.
    assert parse_response('Here you go: {"sections":[]} thanks') is not None


def test_selected_section_refinement_has_a_dedicated_strict_contract() -> None:
    canonical = parse_refinement_response(
        '{"section":{"section_id":"sec-1","title":"Summary","content":"Shorter."}}',
        expected_section_id="sec-1",
    )
    assert canonical is not None and canonical.content == "Shorter."
    # A provider returning the valid selected-section object without its
    # envelope is normalized, then validated against the same strict schema.
    bare = parse_refinement_response(
        '{"section_id":"sec-1","title":"Summary","content":"Shorter."}',
        expected_section_id="sec-1",
    )
    assert bare is not None
    assert parse_refinement_response(
        '{"section":{"section_id":"another-section","content":"Wrong target."}}',
        expected_section_id="sec-1",
    ) is None


def test_refinement_accepts_one_selected_section_and_preserves_numbers() -> None:
    llm = _Llm(
        '{"section":{"section_id":"sec-1","title":"Summary",'
        '"content":"TITAN is at 43.2% completion."}}'
    )
    result = compose_sections(
        llm=llm,
        sections=[{**SECTIONS[0], "content": ORIGINAL, "source_ids": ["src-1"]}],
        sources=SOURCES,
        audience="senior_leadership",
        tone="executive",
        detail_level="standard",
        instructions={"sec-1": "Make this shorter."},
        include_manual=True,
    )
    assert result["sections"] == {"sec-1": "TITAN is at 43.2% completion."}
    assert "Make this shorter." in llm.last_user
    assert "current_content=" in llm.last_user
    assert "VERIFIED EVIDENCE" in llm.last_user


def test_management_friendly_refinement_reaches_the_flexible_llm_path() -> None:
    llm = _Llm(
        '{"section":{"section_id":"sec-1","title":"Summary",'
        '"content":"For management: TITAN is at 43.2% completion."}}'
    )
    result = compose_sections(
        llm=llm,
        sections=[{**SECTIONS[0], "content": ORIGINAL, "source_ids": ["src-1"]}],
        sources=SOURCES,
        audience="senior_leadership",
        tone="executive",
        detail_level="standard",
        instructions={"sec-1": "Explain this for management."},
        include_manual=True,
    )
    assert result["sections"]["sec-1"].startswith("For management")
    assert "Explain this for management." in llm.last_user


def test_valid_bullet_style_refinement_is_accepted() -> None:
    llm = _Llm(
        '{"section":{"section_id":"sec-1","title":"Summary",'
        '"content":"- TITAN completed 812 tickets.\\n- Total scope is 1,876 tickets.\\n- Completion is 43.2%."}}'
    )
    result = compose_sections(
        llm=llm,
        sections=[{**SECTIONS[0], "content": ORIGINAL, "source_ids": ["src-1"]}],
        sources=SOURCES,
        audience="senior_leadership",
        tone="executive",
        detail_level="standard",
        instructions={"sec-1": "Rewrite this as three concise bullet points."},
        include_manual=True,
    )
    assert result["sections"]["sec-1"].count("- ") == 3
    assert "paragraph/list presentation" in llm.last_system


def test_refinement_cannot_change_a_verified_number() -> None:
    llm = _Llm(
        '{"section":{"section_id":"sec-1","title":"Summary",'
        '"content":"TITAN is at 99% completion."}}'
    )
    result = compose_sections(
        llm=llm,
        sections=[{**SECTIONS[0], "content": ORIGINAL, "source_ids": ["src-1"]}],
        sources=SOURCES,
        audience="senior_leadership",
        tone="executive",
        detail_level="standard",
        instructions={"sec-1": "Make this management-friendly."},
        include_manual=True,
    )
    assert result["sections"] == {}
    assert any("99%" in warning for warning in result["warnings"])


def test_composition_accepts_a_faithful_rewrite() -> None:
    llm = _Llm(
        '{"sections":[{"section_id":"sec-1","title":"Summary",'
        '"content":"TITAN reached 43.2% completion across 1876 tickets."}]}'
    )
    result = compose_sections(
        llm=llm,
        sections=SECTIONS,
        sources=SOURCES,
        audience="senior_leadership",
        tone="executive",
        detail_level="standard",
    )
    assert result["sections"]["sec-1"].startswith("TITAN reached 43.2%")
    assert result["warnings"] == []


def test_composition_rejects_an_invented_figure_and_keeps_the_old_text() -> None:
    llm = _Llm(
        '{"sections":[{"section_id":"sec-1","title":"Summary",'
        '"content":"TITAN reached 43.2% and deployed 15 releases."}]}'
    )
    result = compose_sections(
        llm=llm,
        sections=SECTIONS,
        sources=SOURCES,
        audience="senior_leadership",
        tone="executive",
        detail_level="standard",
    )
    # Nothing is written, so the report keeps its existing content rather than
    # publishing an unverifiable number.
    assert result["sections"] == {}
    assert any("15" in warning for warning in result["warnings"])


def test_numeric_fact_check_is_scoped_to_the_selected_sections_sources() -> None:
    llm = _Llm('{"sections":[{"section_id":"sec-1","content":"TITAN has 3 open bugs."}]}')
    scoped_sections = [{**SECTIONS[0], "source_ids": ["summary-source"]}]
    scoped_sources = [
        {"id": "summary-source", "scope": {"squad": "TITAN"}, "evidence": {"answer": "TITAN is at 43.2% completion.", "warnings": []}},
        {"id": "bug-source", "scope": {"squad": "TITAN"}, "evidence": {"answer": "TITAN has 3 open bugs.", "warnings": []}},
    ]
    result = compose_sections(llm=llm, sections=scoped_sections, sources=scoped_sources, audience="delivery_manager", tone="professional", detail_level="standard")
    assert result["sections"] == {}
    assert any("3" in warning for warning in result["warnings"])


def test_a_hand_edited_section_is_never_regenerated() -> None:
    llm = _Llm('{"sections":[{"section_id":"sec-1","content":"overwritten"}]}')
    edited = [{**SECTIONS[0], "manually_edited": True}]
    result = compose_sections(
        llm=llm,
        sections=edited,
        sources=SOURCES,
        audience="senior_leadership",
        tone="executive",
        detail_level="standard",
    )
    assert result["sections"] == {}
    assert llm.calls == 0, "the provider should not even be called"


def test_composition_degrades_safely_without_a_provider() -> None:
    class _Down:
        enabled = False

        def complete(self, *_a: object, **_k: object) -> str:  # pragma: no cover
            raise AssertionError("must not be called")

    result = compose_sections(
        llm=_Down(),
        sections=SECTIONS,
        sources=SOURCES,
        audience="senior_leadership",
        tone="executive",
        detail_level="standard",
    )
    assert result["sections"] == {}
    assert any("unavailable" in warning.lower() for warning in result["warnings"])


def test_unparseable_model_output_changes_nothing() -> None:
    result = compose_sections(
        llm=_Llm("the model rambled instead of returning json"),
        sections=SECTIONS,
        sources=SOURCES,
        audience="senior_leadership",
        tone="executive",
        detail_level="standard",
    )
    assert result["sections"] == {}
    assert any("verified content was kept" in warning.lower() for warning in result["warnings"])


def test_composition_without_sources_asks_for_evidence_instead_of_inventing() -> None:
    result = compose_sections(
        llm=_Llm('{"sections":[]}'),
        sections=SECTIONS,
        sources=[],
        audience="senior_leadership",
        tone="executive",
        detail_level="standard",
    )
    assert result["sections"] == {}
    assert any("no evidence" in warning.lower() for warning in result["warnings"])


def test_conflicting_scopes_surface_before_any_merging() -> None:
    conflicts = detect_scope_conflicts(
        [
            {"id": "a", "label": "TITAN view", "scope": {"squad": "TITAN"}},
            {"id": "b", "label": "MBK view", "scope": {"squad": "MBK"}},
        ]
    )
    assert conflicts
    assert conflicts[0]["severity"] == "conflict"
    assert "TITAN" in conflicts[0]["message"]
    assert "MBK" in conflicts[0]["message"]


def test_a_narrowed_and_a_widened_source_are_flagged_as_widening() -> None:
    conflicts = detect_scope_conflicts(
        [
            {"id": "a", "label": "TITAN view", "scope": {"squad": "TITAN"}},
            {"id": "b", "label": "All squads", "scope": {"squad": None}},
        ]
    )
    assert conflicts
    assert conflicts[0]["severity"] == "widening"
    assert "TITAN" in conflicts[0]["message"]


def test_a_single_source_cannot_conflict_with_itself() -> None:
    assert detect_scope_conflicts([{"id": "a", "label": "x", "scope": {"squad": "TITAN"}}]) == []


def test_staleness_is_reported_from_the_retrieval_time() -> None:
    now = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)
    assert staleness(now - timedelta(hours=2), now=now)["stale"] is False
    old = staleness(now - timedelta(hours=48), now=now)
    assert old["stale"] is True
    assert old["age_hours"] == 48.0
    assert staleness(None, now=now)["stale"] is False
