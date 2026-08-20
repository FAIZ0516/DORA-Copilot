"""The pinned demonstration answer, and the fences around it.

Answering from stored text is the one thing this system is otherwise built to
prevent, so the tests here are mostly about what it must *not* do.
"""

from __future__ import annotations

import pytest

from backend import demo_answer
from backend.config import settings
from backend.demo_answer import ANSWER, QUESTION, demo_answer_for, demo_result


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


@pytest.mark.parametrize(
    "variant",
    [
        "which squad has the most bugs?",
        "  Which squad has the most bugs?  ",
        "Which squad has the most bugs",
        "Which  squad   has the most bugs?",
        "WHICH SQUAD HAS THE MOST BUGS!",
    ],
)
def test_only_the_wording_that_is_not_a_different_question_is_folded(enabled, variant):
    """Case, spacing and end punctuation. Nothing that changes the meaning."""

    assert demo_answer_for(variant) == ANSWER


@pytest.mark.parametrize(
    "other",
    [
        "Which squad has the most open bugs?",
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

    assert "63,481" in ANSWER, "the caveat the assistant itself gave must survive"
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
    assert settings.demo_answer_delay_seconds == 5.0
    field = type(settings).model_fields["demo_answer_delay_seconds"]
    assert any(getattr(m, "le", None) == 30 for m in field.metadata)
