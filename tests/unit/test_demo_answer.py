"""The pinned demonstration answer, and the fences around it.

Answering from stored text is the one thing this system is otherwise built to
prevent, so the tests here are mostly about what it must *not* do.
"""

from __future__ import annotations

import pytest

from backend import demo_answer
from backend.config import settings
from backend.demo_answer import ANSWER, PINNED, QUESTION, demo_answer_for, demo_result


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "demo_answer_enabled", True)


def test_it_does_nothing_unless_it_is_switched_on():
    """Off by default, so it cannot fire in normal use or on a deployment."""

    assert settings.demo_answer_enabled is False
    assert demo_answer_for(QUESTION) is None


def test_the_pinned_question_is_answered_from_the_stored_text(enabled):
    assert demo_answer_for(QUESTION) == ANSWER
    assert "MBK" in ANSWER and "1,434" in ANSWER


def test_the_greeting_is_optional(enabled):
    """Forgetting "Hi Zara" on camera must still hit it."""

    assert demo_answer_for("which squad have the most bug?") == ANSWER
    assert demo_answer_for("Which squad have the most bug") == ANSWER


def test_an_added_qualifier_is_a_different_question(enabled):
    """The folding is grammar only -- every other word must still match.

    "most open bugs" is a different number from "most bugs", so it has to
    reach the real agent no matter how close the sentence looks.
    """

    for question in [
        "Hi Zara, which squads have the most open bugs?",
        "Hi Zara, which squads have the most bugs in JAEGER?",
        "Hi Zara, which squads have the fewest bugs?",
    ]:
        assert demo_answer_for(question) is None, question


@pytest.mark.parametrize(
    "variant",
    [
        # As pinned.
        "Hi Zara, which squad have the most bug?",
        # Case, spacing, end punctuation.
        "hi zara, which squad have the most bug?",
        "  Hi Zara, which squad have the most bug?  ",
        "Hi Zara, which squad have the most bug",
        "Hi  Zara,   which squad have the most bug?",
        "HI ZARA, WHICH SQUAD HAVE THE MOST BUG!",
        # Singular or plural, and the verb that agrees with it. Asking about
        # "squads" and "bugs" is the same question, and this is the phrasing
        # that reads most naturally out loud.
        "Hi Zara, which squads have the most bugs?",
        "Which squad has the most bugs?",
        "which squads have the most bugs?",
        # The greeting is address, not question.
        "Hello Zara, which squads have the most bugs",
        "hi, which squad has the most bugs?",
        "Hey Zara which squads have the most bugs?",
    ],
)
def test_only_the_wording_that_is_not_a_different_question_is_folded(enabled, variant):
    """Case, spacing and end punctuation. Nothing that changes the meaning."""

    assert demo_answer_for(variant) == ANSWER


@pytest.mark.parametrize(
    "other",
    [
        "Which squad has the most open bugs?",
        "Hi Zara, which squad has the most open bugs?",
        "Which squad has the most bugs this month?",
        "Which release has the most bugs?",
        "Which squad has the fewest bugs?",
        "How many bugs does MBK have?",
        "Which squad has the most bugs in JAEGER?",
        "Which team has the most bugs?",
        "",
    ],
)
def test_every_other_question_still_reaches_the_real_agent(enabled, other):
    """A near miss is a different question, and must be answered properly.

    Matching loosely is how a pinned answer starts appearing on questions it
    does not actually answer -- "most open bugs" is a different number from
    "most bugs".
    """

    assert demo_answer_for(other) is None


def test_the_result_is_shaped_like_any_other_turn(enabled):
    """Nothing downstream should need to know this answer was pinned."""

    result = demo_result(QUESTION)
    assert result["answer"] == ANSWER
    for key in ("chart", "table", "warnings", "validation", "metadata", "_persistence"):
        assert key in result


def test_a_pinned_answer_is_labelled_as_one(enabled):
    """It must be identifiable in metadata and in the audit trail.

    Otherwise a stored answer looks exactly like a live one while debugging,
    and someone spends an afternoon wondering why the query log is empty.
    """

    metadata = demo_result(QUESTION)["metadata"]
    assert metadata["answer_source"] == "demo-template"
    assert metadata["demo_answer"] is True
    assert metadata["query_ids"] == []


def test_the_stored_text_is_the_assistant_s_own_wording():
    """Not written by hand -- copied from what the assistant actually said.

    A demonstration should show the product's own words, including the
    coverage caveat it chose to add.
    """

    assert "MBK" in ANSWER and "1,434" in ANSWER
    # The coverage caveat it chose to add must survive the copy.
    assert "squad" in ANSWER.lower() and "caveat" in ANSWER.lower()
    # And it answers the greeting, because the question opens with one.
    assert ANSWER.lower().startswith("hi")
    assert ANSWER.strip() == ANSWER


def test_the_turn_short_circuits_before_any_planning(enabled):
    """Checked ahead of the agent, so no other question's path is touched."""

    import inspect

    from backend import chat_service

    body = inspect.getsource(chat_service.run_chat_turn)
    assert "if demo_answer_for(message) is not None:" in body
    assert body.index("demo_answer_for(message)") < body.index("DoraDbAgent")
    # And it waits, so the answer does not arrive suspiciously instantly.
    assert "time.sleep(settings.demo_answer_delay_seconds)" in body


def test_the_delay_is_configurable_and_bounded():
    assert settings.demo_answer_delay_seconds == 4.0
    field = type(settings).model_fields["demo_answer_delay_seconds"]
    assert any(getattr(m, "le", None) == 30 for m in field.metadata)


# --------------------------------------------------------------------------- #
# The second pinned answer: last year's releases                              #
# --------------------------------------------------------------------------- #

RELEASES = PINNED[1]


def test_a_second_question_can_be_pinned_without_disturbing_the_first(enabled):
    assert len(PINNED) == 2
    assert demo_answer_for(PINNED[0].question) == PINNED[0].answer
    assert demo_answer_for(RELEASES.question) == RELEASES.answer
    assert PINNED[0].answer != RELEASES.answer


@pytest.mark.parametrize(
    "variant",
    [
        "Hi Zara, how many releases did we ship last year?",
        "how many releases did we ship last year?",
        "Hi Zara, how many release did we ship last year",
        "HOW MANY RELEASES DID WE SHIP LAST YEAR!",
        "Hello Zara,  how many releases did we ship last year?",
    ],
)
def test_the_release_question_is_matched_however_it_is_said(enabled, variant):
    assert demo_answer_for(variant) == RELEASES.answer


@pytest.mark.parametrize(
    "other",
    [
        # A named year is a different year's number.
        "Hi Zara, how many releases did we ship in 2024?",
        "Hi Zara, how many releases did we ship this year?",
        # A squad scope is a different count.
        "Hi Zara, how many releases did MBK ship last year?",
        # A different noun entirely.
        "Hi Zara, how many bugs did we ship last year?",
    ],
)
def test_a_narrower_release_question_still_reaches_the_agent(enabled, other):
    assert demo_answer_for(other) is None


def test_the_release_answer_is_detailed_but_not_long(enabled):
    """The point of pinning this one was a fuller answer, not just a faster one.

    It has to stay readable on screen, so length is bounded as well as
    floored -- a wall of text is as bad on camera as a bare number.
    """

    words = len(RELEASES.answer.split())
    assert 70 <= words <= 140, f"{words} words"
    # Structured rather than a paragraph blob.
    assert RELEASES.answer.count('\n- ') >= 3
    # And it answers the greeting, since the question opens with one.
    assert RELEASES.answer.lower().startswith("hi")


def test_every_figure_in_the_release_answer_is_one_the_data_supports():
    """Verified against dora_metrics_by_year for 2025 when it was captured.

    A pinned answer states numbers nobody re-derives at demo time, so the
    numbers have to be the database's own. These are the 2025 row: five
    releases, 2.29 months apart, no recorded failures, a one-month lead time,
    5.28 months of cycle time, over 1,201 stories and 182 feature references.
    """

    for figure in ("5 releases", "2.29", "0%", "1.0 month", "5.28", "1,201", "182"):
        assert figure in RELEASES.answer, figure
