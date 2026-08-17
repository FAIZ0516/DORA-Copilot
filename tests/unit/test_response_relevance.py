"""Answers contain what the request earned, and nothing else.

Every case here is something the system used to do: offer "Worth knowing" on a
one-number answer, end a count with a suggestion nobody asked for, restate a
whole previous answer when asked to reformat it. The padding was being
*instructed* -- the structure rules named "Worth knowing" as an example header
and fifteen skill templates ended with "Would you like me to..." -- so these
tests cover both the gating and the deterministic strip.
"""

from __future__ import annotations

import pytest

from backend.agent.controls.response_controller import derive_policy
from backend.agent.response.response_decision import (
    PROHIBITED_HEADINGS,
    decide_response,
    describe_decision,
)
from backend.agent.validators.relevance_validator import (
    find_relevance_violations,
    strip_unpermitted_sections,
)


def _decide(message, *, mode="data", intent="ANALYSIS", rows=None, warnings=None):
    plan = {"mode": mode, "intent": intent}
    results = [{"query_id": "q", "row_count": len(rows or []), "rows": rows or [{"n": 1}]}]
    policy = derive_policy(message, plan=plan, results=results, warnings=warnings or [])
    return decide_response(
        message, plan=plan, policy=policy, results=results, warnings=warnings or []
    )


def _codes(answer, decision, **kwargs):
    return {v.code for v in find_relevance_violations(answer, decision, **kwargs)}


# --------------------------------------------------------------------------- #
# 1-5: what a short answer must not grow                                      #
# --------------------------------------------------------------------------- #


def test_a_direct_metric_question_does_not_get_a_worth_knowing_section():
    decision = _decide("What is the change failure rate for MBK?")
    assert decision["profile"] == "direct_fact"
    assert "Worth knowing" not in describe_decision(decision)

    answer = (
        "MBK's change failure rate is 12%.\n\n"
        "**Worth knowing**\n"
        "The DCPM project tracks 21 squads in total.\n"
    )
    assert "generic_supplementary_heading" in _codes(answer, decision)
    stripped = strip_unpermitted_sections(answer, decision)
    assert "Worth knowing" not in stripped
    assert "21 squads" not in stripped
    assert "MBK's change failure rate is 12%." in stripped


def test_a_count_question_does_not_get_unrequested_recommendations():
    decision = _decide("How many open bugs does MBK have?")
    assert "recommendation" not in decision["allowed_blocks"]

    answer = (
        "MBK has 27 open bugs.\n\n"
        "I recommend prioritising the oldest of these before the next release.\n"
    )
    assert "unrequested_recommendation" in _codes(answer, decision)


def test_a_list_question_returns_the_values_without_unrelated_background():
    decision = _decide("List all the squads.")
    assert decision["profile"] == "list"
    assert "breakdown" in decision["required_blocks"]

    answer = (
        "There are 3 squads.\n\n"
        "- MBK\n- CASA\n- ATOM\n\n"
        "**Background**\n"
        "Jira was adopted by the DCPM programme in 2019.\n"
    )
    assert "generic_supplementary_heading" in _codes(answer, decision)
    stripped = strip_unpermitted_sections(answer, decision)
    assert "- MBK" in stripped and "- ATOM" in stripped
    assert "2019" not in stripped


def test_a_comparison_does_not_wander_outside_the_compared_metrics():
    decision = _decide("Compare MBK and CASA on change failure rate.")
    assert decision["profile"] == "comparison"

    answer = (
        "CASA's change failure rate is lower: 8% against MBK's 12%.\n\n"
        "**Other considerations**\n"
        "Lead time for changes is not measured for either squad.\n"
    )
    assert "generic_supplementary_heading" in _codes(answer, decision)
    assert "Other considerations" not in strip_unpermitted_sections(answer, decision)


def test_a_short_answer_gets_no_automatic_headings():
    decision = _decide("How many squads are there?")
    guidance = describe_decision(decision)
    # The guidance names the banned headings only to ban them -- it never
    # offers one as an example to fill in, which is what the structure rules
    # used to do with "Worth knowing".
    banned_clause = guidance.lower().split("never use these headings:")[1]
    for heading in PROHIBITED_HEADINGS:
        assert heading in banned_clause
    assert "**Worth knowing**" not in guidance

    answer = "There are 21 squads."
    assert _codes(answer, decision) == set()
    assert strip_unpermitted_sections(answer, decision) == answer


# --------------------------------------------------------------------------- #
# 6-8: blocks appear only when something supports them                        #
# --------------------------------------------------------------------------- #


def test_an_optional_block_with_no_supported_content_is_omitted():
    """Optional is a permission, not an instruction to write something."""

    decision = _decide("What is the release frequency for MBK?")
    assert "limitation" in decision["optional_blocks"]
    assert decision["limitation_required"] is False
    assert "Do not add a limitations section" in describe_decision(decision)

    answer = "MBK released every 2.4 months.\n\n**Limitations**\nNone worth noting.\n"
    assert "unnecessary_limitation" in _codes(answer, decision)


def test_a_material_limitation_is_required_and_kept():
    warning = "Squad names are reporting labels, not an authoritative squad directory."
    decision = _decide("List all the squads.", warnings=[warning])

    assert decision["limitation_required"] is True
    assert "limitation" in decision["required_blocks"]
    assert "limitation" not in decision["optional_blocks"]
    assert "state it once, as a closing sentence" in describe_decision(decision)

    answer = (
        "There are 21 squads.\n\n- MBK\n- CASA\n\n"
        "**Limitations**\n"
        "These are reporting labels rather than an official team directory.\n"
    )
    codes = _codes(answer, decision)
    assert "unnecessary_limitation" not in codes
    # And the strip must not remove it.
    assert "reporting labels" in strip_unpermitted_sections(answer, decision)


def test_an_immaterial_limitation_is_not_invented():
    decision = _decide("How many open bugs does MBK have?")
    assert decision["limitation_required"] is False
    assert "Do not add a limitations section" in describe_decision(decision)


# --------------------------------------------------------------------------- #
# 9-10: follow-ups answer only the new need                                   #
# --------------------------------------------------------------------------- #


def test_a_format_change_follow_up_does_not_repeat_the_previous_explanation():
    """"Put that in a table" wants the table, not the essay again."""

    previous = (
        "MBK has 27 open bugs across four statuses. The Done category includes "
        "cancelled work, so it does not prove successful delivery. Squad names "
        "come from how teams tag their work in Jira rather than a directory."
    )
    decision = _decide("Put that in a table.")

    repeated = previous + "\n\n| Status | Count |\n| --- | --- |\n| Open | 27 |\n"
    assert "follow_up_repeats_previous_answer" in _codes(
        repeated, decision, previous_answer=previous
    )

    concise = "Here it is as a table.\n\n| Status | Count |\n| --- | --- |\n| Open | 27 |\n"
    assert "follow_up_repeats_previous_answer" not in _codes(
        concise, decision, previous_answer=previous
    )


def test_suggested_follow_up_questions_are_not_duplicated_in_the_answer_body():
    """The interface already offers follow-ups; the answer must not."""

    decision = _decide("How many open bugs does MBK have?")
    assert "next_step" not in decision["allowed_blocks"]
    assert "separate feature of the interface" in describe_decision(decision)

    answer = (
        "MBK has 27 open bugs.\n\n"
        "Would you like me to break this down by status or squad?\n"
    )
    assert "unrequested_next_steps" in _codes(answer, decision)


# --------------------------------------------------------------------------- #
# The profiles themselves                                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("How many open bugs does MBK have?", "direct_fact"),
        ("List all the squads.", "list"),
        ("Compare MBK and CASA.", "comparison"),
        ("What does status category mean?", "explanation"),
        ("What should we do to improve delivery?", "recommendation"),
        ("Write me a report on delivery performance.", "report"),
    ],
)
def test_the_profile_follows_the_request(message, expected):
    assert _decide(message)["profile"] == expected


def test_a_failed_query_is_an_error_not_a_lecture():
    plan = {"mode": "data", "intent": "ANALYSIS"}
    policy = derive_policy("How many bugs?", plan=plan)
    decision = decide_response(
        "How many bugs?", plan=plan, policy=policy, results=[], database_error=True
    )
    assert decision["profile"] == "error"
    assert decision["allowed_blocks"] == {"answer", "next_step"}
    assert "State what failed" in describe_decision(decision)


def test_nothing_found_explains_the_search_without_teaching():
    plan = {"mode": "data", "intent": "ANALYSIS"}
    results = [{"query_id": "q", "row_count": 0, "rows": []}]
    policy = derive_policy("How many bugs for XYZ?", plan=plan, results=results)
    decision = decide_response(
        "How many bugs for XYZ?", plan=plan, policy=policy, results=results
    )
    assert decision["profile"] == "no_result"
    assert "recommendation" not in decision["allowed_blocks"]
    assert "unrelated educational content" in describe_decision(decision)


def test_a_clarification_asks_one_question_and_stops():
    plan = {"mode": "clarification", "intent": "CLARIFICATION_REQUIRED"}
    policy = derive_policy("Show me that one.", plan=plan)
    decision = decide_response("Show me that one.", plan=plan, policy=policy)
    assert decision["profile"] == "clarification"
    assert decision["required_blocks"] == ("clarifying_question",)
    assert decision["optional_blocks"] == ()


def test_the_strip_never_empties_an_answer_made_only_of_prose():
    decision = _decide("How many squads are there?")
    answer = "There are 21 squads, counting each distinct name once."
    assert strip_unpermitted_sections(answer, decision) == answer


def test_repeating_the_conclusion_under_two_headings_is_caught():
    decision = _decide("Write me a report on open bugs.")
    conclusion = "MBK carries the largest share of open bugs at 27 of 104."
    answer = f"{conclusion}\n\n**Evidence**\n{conclusion}\n"
    assert "repeated_conclusion" in _codes(answer, decision)


def test_a_closing_offer_of_help_is_removed_not_just_flagged():
    """The habit that survives section-stripping, because it is prose.

    Fifteen skill templates ended with "Would you like me to break this down
    by...", and the interface already has its own follow-up feature.
    """

    decision = _decide("How many open bugs does MBK have?")
    answer = (
        "MBK has 27 open bugs.\n\n"
        "Would you like me to break this down by status or squad?\n"
    )
    stripped = strip_unpermitted_sections(answer, decision)
    assert stripped == "MBK has 27 open bugs."


def test_an_offer_sharing_a_line_with_real_content_keeps_the_content():
    decision = _decide("How many open bugs does MBK have?")
    answer = "MBK has 27 open bugs. Would you like me to break that down?"
    assert strip_unpermitted_sections(answer, decision) == "MBK has 27 open bugs."


def test_a_clarifying_question_is_never_stripped_for_offering_options():
    """Asking what the user wants *is* the answer here.

    The clarifying question is usually phrased as an offer, so the offer-strip
    would delete the entire reply.
    """

    plan = {"mode": "clarification", "intent": "CLARIFICATION_REQUIRED"}
    policy = derive_policy("Show me that one.", plan=plan)
    decision = decide_response("Show me that one.", plan=plan, policy=policy)
    answer = "Would you like the open bugs for the whole project, or for one squad?"
    assert strip_unpermitted_sections(answer, decision) == answer


def test_an_answer_that_is_only_an_offer_is_left_alone():
    """Something imperfect beats an empty reply."""

    decision = _decide("How many open bugs does MBK have?")
    answer = "Would you like me to pull that for the whole project instead?"
    assert strip_unpermitted_sections(answer, decision) == answer


def test_a_clarification_offering_options_is_not_flagged_as_a_next_step():
    """Detection and stripping must agree about the clarification exemption."""

    plan = {"mode": "clarification", "intent": "CLARIFICATION_REQUIRED"}
    policy = derive_policy("Put that in a table.", plan=plan)
    decision = decide_response("Put that in a table.", plan=plan, policy=policy)
    answer = (
        "What would you like me to put in a table? I can table the DORA "
        "metrics, issue counts by type, or open work by squad — just let me "
        "know which one you're after."
    )
    assert "unrequested_next_steps" not in _codes(answer, decision)
    assert strip_unpermitted_sections(answer, decision) == answer
