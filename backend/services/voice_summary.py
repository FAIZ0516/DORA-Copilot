"""What Zara says out loud, as opposed to what she writes.

A written answer and a spoken one want different things. On screen a status
breakdown across eleven rows is easy to skim and genuinely useful. Read aloud
it is half a minute of numbers nobody can hold in their head, and the listener
has already stopped following by the fourth one.

So voice mode speaks a condensed version while the chat still shows the answer
in full. The condensed version is never added to the answer itself -- there is
no "Key points" section on screen, and the written answer is untouched. It
exists only to be spoken and is discarded afterwards.

Nothing here is allowed to introduce a fact. The summary is drawn from an
answer the agent has already produced under evidence validation, and this stage
may only choose what to leave out. When it fails, or returns something that
looks invented, the caller falls back to speaking the full answer: too much
speech is a far smaller failure than confident speech that is wrong.
"""

from __future__ import annotations

import logging
import re

from ..llm import GenerativeAIClient
from .voice_speech import markdown_to_speech

logger = logging.getLogger(__name__)

# Below this an answer is already about as short as its summary would be, so
# condensing costs a model call and a second or two of delay to save nothing.
# Roughly twenty seconds of speech.
MIN_SPOKEN_WORDS_TO_CONDENSE = 45

# A list is unusable read aloud at any length. "Closed 8,860, Rejected 1,660,
# New 534, Review In Progress 77..." is only forty words and still impossible
# to follow, so length alone is the wrong test -- shape matters more.
LIST_ITEMS_TO_CONDENSE = 3

# A spoken turn people will actually listen to the end of.
MAX_SPOKEN_WORDS = 60

_PROMPT = """You are choosing what to say out loud from an answer the user can \
also read on screen.

Speak only what matters most: the direct answer, and at most one or two \
supporting facts that change how the listener should act. Leave out full \
breakdowns, lists of statuses, per-item figures, and anything the listener \
would need to see written down to follow.

Rules:
- Use ONLY facts that appear in the answer. Never add, infer, round, or \
recalculate a number.
- Two or three short sentences. Under 60 words.
- Plain spoken English. No markdown, no bullet points, no headings, no tables.
- Do not say "in summary", "the key points are", "to summarise", or refer to \
the written answer.
- Do not offer further help or ask a follow-up question.
- Start with the answer itself.

Return only the sentences to speak."""


def _list_items(answer: str) -> int:
    """How many enumerated items the written answer contains."""

    return len(
        re.findall(r"(?m)^\s*(?:[-*+]|\d+[.)])\s+\S", answer)
    ) + len(re.findall(r"(?m)^\s*\|.+\|\s*$", answer))


def _worth_condensing(answer: str, speakable: str) -> bool:
    """Would speaking this in full actually be worse than a shorter version?

    Two independent reasons. It is long, or it is a list -- and a list is
    unlistenable whatever its length, because the listener has no way to hold
    ten labelled figures in order without seeing them.
    """

    if len(speakable.split()) > MIN_SPOKEN_WORDS_TO_CONDENSE:
        return True
    return _list_items(answer) >= LIST_ITEMS_TO_CONDENSE


def _numbers(text: str) -> set[str]:
    """Numeric tokens, normalised so 1,434 and 1434 compare equal."""

    return {
        match.replace(",", "").rstrip(".")
        for match in re.findall(r"\d[\d,]*(?:\.\d+)?", text)
    }


def _is_faithful(summary: str, answer: str) -> bool:
    """Every number spoken must appear in the answer it came from.

    The one failure that matters here is a spoken figure the written answer
    does not support -- the user hears it, acts on it, and never sees the text
    that would have contradicted it. Dropping numbers is fine; that is the
    whole point of condensing.
    """

    return _numbers(summary) <= _numbers(answer)


def spoken_summary(llm: GenerativeAIClient, *, question: str, answer: str) -> str:
    """The condensed answer to speak, or "" to speak the answer in full.

    Blocking -- call it off the event loop.
    """

    speakable = markdown_to_speech(answer or "").strip()
    if not speakable:
        return ""
    if not _worth_condensing(answer, speakable):
        # Already short enough to say straight through. Skipping the call keeps
        # the fast path fast: no model round trip before the first word.
        return ""

    try:
        generated = llm.complete(
            _PROMPT,
            f"Question: {question}\n\nAnswer shown on screen:\n{answer}",
            temperature=0.1,
        )
    except Exception as exc:  # noqa: BLE001 - speaking the full answer is fine
        logger.warning("Spoken summary failed: %s", type(exc).__name__)
        return ""
    if not generated:
        return ""

    summary = markdown_to_speech(generated).strip()
    if not summary:
        return ""
    if not _is_faithful(summary, speakable):
        logger.warning(
            "Spoken summary introduced a number the answer does not contain; "
            "speaking the full answer instead."
        )
        return ""
    if len(summary.split()) > MAX_SPOKEN_WORDS * 2:
        # It ignored the length rule entirely; nothing was gained.
        return ""
    return summary


__all__ = ["MAX_SPOKEN_WORDS", "MIN_CHARS_TO_CONDENSE", "spoken_summary"]
