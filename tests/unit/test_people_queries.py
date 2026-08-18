"""Assignee and reporter names are answerable, with the caveats attached.

These were blocked by three independent layers -- a restricted-field set, an
approved-query catalogue with no per-person query, and a data guide instructing
the model to refuse. The owner of the data asked for them to be reportable, so
all three had to move together; changing one alone produces a system that
half-refuses.

What stays true is the reading. Assignee is the *current* snapshot owner, not
who did the work, so a count says where work sits rather than how much anyone
delivered. Reporter describes intake, not delivery.
"""

from __future__ import annotations

import pytest

from backend.agent.guardrails.output_guardrail import (
    RESTRICTED_FIELDS,
    check_output_safety,
    strip_sensitive_fields,
)
from backend.agent.request_router import route_jira_request
from backend.database.doradb_catalog import APPROVED_QUERY_IDS, QUERY_CATALOGUE

ASSIGNEE_QUERY = "jira_issue_counts_by_assignee"
REPORTER_QUERY = "jira_issue_counts_by_reporter"


# --------------------------------------------------------------------------- #
# The three layers agree                                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("field", ["assignee", "reporter"])
def test_names_are_no_longer_stripped_from_results(field):
    """The guardrail used to remove these keys before anything could use them."""

    assert field not in RESTRICTED_FIELDS
    row = {field: "A Person", "issue_count": 12}
    assert strip_sensitive_fields(row) == row


@pytest.mark.parametrize("field", ["summary", "root_cause", "how_to_fix", "labels"])
def test_issue_text_is_still_protected(field):
    """Only identities were unblocked. Issue text describes incidents.

    Nothing about naming people requires the free text, so opening one door
    must not open the other.
    """

    assert field in RESTRICTED_FIELDS
    assert strip_sensitive_fields({field: "secret", "issue_count": 3}) == {"issue_count": 3}
    assert check_output_safety(f"{field}: something confidential")


def test_naming_a_person_in_an_answer_is_not_flagged():
    assert check_output_safety("Aisyah has 41 open issues, the most of any assignee.") == []


@pytest.mark.parametrize("query_id", [ASSIGNEE_QUERY, REPORTER_QUERY])
def test_the_query_is_approved_and_catalogued(query_id):
    """Unblocking the field is useless without a query that returns it."""

    assert query_id in APPROVED_QUERY_IDS
    entry = QUERY_CATALOGUE[query_id]
    assert "dcpsquad" in entry["allowed_filters"]
    # The count of people with nothing against them travels with every row.
    assert any(
        column in entry["expected_columns"]
        for column in ("unassigned_rows", "missing_reporter_rows")
    )


@pytest.mark.parametrize(
    ("query_id", "must_say"),
    [
        (ASSIGNEE_QUERY, "productivity measure"),
        (ASSIGNEE_QUERY, "not who did the work historically"),
        (REPORTER_QUERY, "intake"),
        (REPORTER_QUERY, "never delivery"),
    ],
)
def test_the_catalogue_carries_the_reading_with_the_numbers(query_id, must_say):
    """The purpose text reaches the planner, so the caveat rides with the data.

    A per-person count is trivially misread as a performance measure. The
    reading has to travel with the query rather than being remembered.
    """

    assert must_say in QUERY_CATALOGUE[query_id]["purpose"].lower()


# --------------------------------------------------------------------------- #
# The path from question to query                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "question",
    [
        "can you give the name for the assignee?",
        "who is working on the open bugs?",
        "show me the workload by assignee",
        "which issues are assigned to each person?",
        "who owns the most issues?",
    ],
)
def test_an_assignee_question_reaches_the_assignee_query(question):
    """Routing is deterministic on purpose.

    The model had nothing to reach for before and answered that the data was
    unavailable, so leaving this to inference is precisely what failed.
    """

    plan = route_jira_request(question)
    assert plan is not None, "the question must reach a deterministic route"
    assert plan["mode"] == "data"
    assert ASSIGNEE_QUERY in [action["query_id"] for action in plan["actions"]]


@pytest.mark.parametrize(
    "question",
    ["who reported the most bugs?", "give me the reporter names", "who raised these issues?"],
)
def test_a_reporter_question_reaches_the_reporter_query(question):
    plan = route_jira_request(question)
    assert plan is not None, "the question must reach a deterministic route"
    assert plan["mode"] == "data"
    assert REPORTER_QUERY in [action["query_id"] for action in plan["actions"]]


def test_squad_questions_are_not_captured_by_the_people_routes():
    """The new routes must not swallow questions that were already answered."""

    plan = route_jira_request("which squad has the most bugs?")
    assert plan is not None
    query_ids = [action["query_id"] for action in plan["actions"]]
    assert ASSIGNEE_QUERY not in query_ids
    assert REPORTER_QUERY not in query_ids


# --------------------------------------------------------------------------- #
# The model must not talk about the data instead of returning it              #
# --------------------------------------------------------------------------- #


def _conversation_plan():
    return {
        "mode": "conversation",
        "intent": "CAPABILITY_EXPLANATION",
        "actions": [],
        "reason": "",
        "clarification": "",
        "confidence": 0.8,
    }


def test_asking_for_names_is_not_answered_with_a_description_of_them():
    """"Can you give the name for the assignee?" reads as a capability question.

    The model answered it as one -- "yes, assignee names are available" -- which
    is true and useless. Asking for a thing by name is a request for the thing.
    """

    from backend.agent.planner import _deterministic_recovery

    recovered = _deterministic_recovery(
        "can you give the name for the assignee?", _conversation_plan()
    )
    assert recovered is not None, "the question must reach the database"
    plan, source = recovered
    assert plan["mode"] == "data"
    assert source == "deterministic-recovery"
    assert ASSIGNEE_QUERY in [action["query_id"] for action in plan["actions"]]


def test_a_genuine_capability_question_is_still_left_alone():
    """The recovery must not turn every conversational turn into a query.

    Answering "what data can I get?" with a data dump is the failure this
    guard was written to avoid, so widening it for people questions must not
    reopen it.
    """

    from backend.agent.planner import _deterministic_recovery

    for question in ["what data can I get?", "what can you do?", "hello"]:
        assert _deterministic_recovery(question, _conversation_plan()) is None, question
