"""Voice speaks the point, not the whole answer.

Read aloud, a status breakdown across eleven rows is half a minute of numbers
nobody can hold in their head. The screen keeps the full answer; the voice gets
a condensed version that is never added to it.
"""

from __future__ import annotations

import pytest

from backend.services.voice_summary import (
    LIST_ITEMS_TO_CONDENSE,
    MIN_SPOKEN_WORDS_TO_CONDENSE,
    spoken_summary,
)


LONG_ANSWER = (
    "There are 11,289 bugs in total across the DCPM project.\n\n"
    "That total breaks down by current status:\n\n"
    "- **Closed:** 8,860\n"
    "- **Rejected:** 1,660\n"
    "- **New:** 534\n"
    "- **Review In progress:** 77\n"
    "- **Assigned:** 40\n"
    "- **Fix In Progress:** 40\n"
    "- **Ready for Test:** 37\n"
    "- **Reopened:** 18\n"
    "- **Fixed:** 13\n"
    "- **Test In Progress:** 10\n"
)


class _Llm:
    """A stub standing in for the model, recording how it was called."""

    def __init__(self, reply: str | None = "", *, explode: bool = False) -> None:
        self.reply = reply
        self.explode = explode
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt, user_prompt, **_kwargs):
        if self.explode:
            raise RuntimeError("provider down")
        self.calls.append((system_prompt, user_prompt))
        return self.reply


def test_a_long_answer_is_condensed_to_what_is_worth_hearing():
    llm = _Llm(
        "There are 11,289 bugs in the DCPM project. Nearly all are closed or "
        "rejected, with 8,860 already closed."
    )
    spoken = spoken_summary(llm, question="How many bugs are there?", answer=LONG_ANSWER)

    assert spoken.startswith("There are 11,289 bugs")
    # The eleven-row breakdown is exactly what should not be read out.
    assert "Ready for Test" not in spoken
    assert len(spoken) < len(LONG_ANSWER) / 2


def test_a_figure_the_summary_worked_out_for_itself_is_refused():
    """Arithmetic is not condensing.

    11,289 - 8,860 - 1,660 = 769 open is a defensible sum, and still refused:
    the number is not in the answer, so nothing the user can see supports it.
    Deriving figures is how a summary starts being wrong while sounding right.
    """

    llm = _Llm("There are 11,289 bugs, leaving 769 still open.")
    assert spoken_summary(llm, question="How many bugs?", answer=LONG_ANSWER) == ""


def test_a_short_answer_is_spoken_as_written_without_a_model_call():
    """The fast path: nothing to condense, so nothing should cost a round trip."""

    llm = _Llm("should never be used")
    answer = "There are 21 squads in the DCPM data."
    assert len(answer.split()) < MIN_SPOKEN_WORDS_TO_CONDENSE

    assert spoken_summary(llm, question="How many squads?", answer=answer) == ""
    assert llm.calls == [], "a short answer must not delay speech with a model call"


def test_a_short_answer_that_is_a_list_is_still_condensed():
    """Length is the wrong test on its own.

    "Closed 8,860, Rejected 1,660, New 534, Review In Progress 77..." is forty
    words and impossible to follow by ear, because nobody can hold ten labelled
    figures in order without seeing them.
    """

    short_list = (
        "Three squads have open bugs:\n\n- MBK: 27\n- CASA: 14\n- ATOM: 9\n"
    )
    assert len(short_list.split()) < MIN_SPOKEN_WORDS_TO_CONDENSE
    assert short_list.count("- ") >= LIST_ITEMS_TO_CONDENSE

    llm = _Llm("Three squads have open bugs, with MBK carrying the most at 27.")
    spoken = spoken_summary(llm, question="Which squads have bugs?", answer=short_list)
    assert spoken and llm.calls, "a read-aloud list must be condensed whatever its length"


def test_a_summary_that_invents_a_number_is_refused():
    """The one failure that matters: a spoken figure the answer cannot support.

    The listener acts on what they hear and never sees the text that would
    have contradicted it, so an unsupported number falls back to the full
    answer rather than being spoken.
    """

    llm = _Llm("There are 11,289 bugs, and 402 of them are critical.")
    assert spoken_summary(llm, question="How many bugs?", answer=LONG_ANSWER) == ""


def test_dropping_numbers_is_exactly_what_condensing_means():
    llm = _Llm("There are 11,289 bugs in the DCPM project, and most are closed.")
    spoken = spoken_summary(llm, question="How many bugs?", answer=LONG_ANSWER)
    assert spoken, "omitting figures must be allowed -- that is the whole point"
    assert "8,860" not in spoken


def test_thousands_separators_do_not_read_as_invented_numbers():
    """11,289 and 11289 are the same figure and must compare equal."""

    llm = _Llm("There are 11289 bugs in the project overall.")
    assert spoken_summary(llm, question="How many bugs?", answer=LONG_ANSWER)


@pytest.mark.parametrize("reply", ["", None, "   "])
def test_an_empty_summary_falls_back_to_the_full_answer(reply):
    assert spoken_summary(_Llm(reply), question="q", answer=LONG_ANSWER) == ""


def test_a_provider_failure_falls_back_to_the_full_answer():
    """Speaking too much is a far smaller failure than saying nothing."""

    assert spoken_summary(_Llm(explode=True), question="q", answer=LONG_ANSWER) == ""


def test_a_summary_that_ignored_the_length_rule_is_discarded():
    llm = _Llm(" ".join(["word"] * 400))
    assert spoken_summary(llm, question="q", answer=LONG_ANSWER) == ""


def test_markdown_never_reaches_the_speech_engine():
    llm = _Llm("**There are 11,289 bugs** in the project, mostly `Closed`.")
    spoken = spoken_summary(llm, question="q", answer=LONG_ANSWER)
    assert "**" not in spoken and "`" not in spoken


def test_the_instruction_forbids_new_facts_and_follow_up_offers():
    llm = _Llm("There are 11,289 bugs in the project overall, mostly closed.")
    spoken_summary(llm, question="How many bugs?", answer=LONG_ANSWER)
    system_prompt, user_prompt = llm.calls[0]

    assert "ONLY facts that appear in the answer" in system_prompt
    assert "Never add, infer, round, or recalculate a number" in system_prompt
    assert "Do not offer further help" in system_prompt
    # And it must see the answer it is condensing, not just the question.
    assert "11,289" in user_prompt


def test_the_summary_is_never_added_to_the_written_answer():
    """The screen keeps the full answer; the summary is spoken and discarded."""

    import inspect

    import backend.api.voice as voice_module

    body = inspect.getsource(voice_module._handle_utterance)
    # assistant.text carries the full answer ...
    assert 'text=result.get("answer") or ""' in body
    # ... and only _speak receives the condensed one.
    assert "await _speak(sender, session, spoken or answer, turn_id)" in body
    assert body.index("assistant.text") < body.index("spoken_summary")
