"""One pinned answer, for recording a demonstration.

A demonstration cannot wait thirty seconds for a live answer, so a small,
explicit set of questions may be answered from a stored response instead of
from the database. Everything not in that set runs through the agent as
usual.

Three things keep this from becoming a way to make the assistant say untrue
things:

* It is off unless ``DEMO_ANSWER_ENABLED`` is set, so it cannot fire in normal
  use or on a deployed instance.
* It matches those questions and no others. Greeting, case, spacing and
  singular/plural are
  folded, because none of those changes what is being asked; every other
  word must match exactly. No similarity score and no "close enough", so a
  different question always reaches the real agent.
* The text below is not written by hand. The assistant was asked this exact
  question several times and one of its own replies was copied verbatim --
  the one that greets back, since the question opens with a greeting. It is
  a real answer chosen from real answers, not an idealised version of one.

The figures are therefore a snapshot. If the underlying data moves, this text
goes stale and will contradict the dashboard -- regenerate it before recording
by asking the question with the flag off.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from .config import settings

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class PinnedAnswer:
    """One question that skips the agent, and the reply it gives instead."""

    question: str
    answer: str


PINNED: tuple[PinnedAnswer, ...] = (
    PinnedAnswer(
        question="Hi Zara, which squad have the most bug?",
        answer=(
            "Hi! Based on the DCPM data as of the current snapshot, **MBK** is the squad with the most bugs \u2014 1,434, more than any other squad.\n"
            "\n"
            "Top three by bug count:\n"
            "- MBK \u2014 1,434\n"
            "- JAEGER \u2014 1,368\n"
            "- Droid Spark \u2014 1,003\n"
            "\n"
            "One caveat: these totals cover only bugs that carry a squad tag. A large part of the dataset has no squad recorded, so the ranking could shift if that work were attributed. MBK still leads by a clear margin on the tagged work."
        ),
    ),
    PinnedAnswer(
        question="Hi Zara, how many releases did we ship last year?",
        answer=(
            "Hi! For DCPM, you shipped **5 releases in 2025** \u2014 on average one every 2.3 months \u2014 and the DORA picture for the year is steady: regular delivery, no recorded failures, and a short lead time for change.\n"
            "\n"
            "- **Release frequency:** average 2.29 months between releases\n"
            "- **Change failure rate:** 0%\n"
            "- **Lead time for change:** 1.0 month average\n"
            "- **Delivery cycle time:** 5.28 months average from development start through release\n"
            "\n"
            "Those releases were tied to 1,201 user stories and 182 feature references, so the cadence supported a substantial amount of delivery volume.\n"
            "\n"
            "This reflects DCPM data in the 2026-08-25 snapshot, covering the 2025 release year."
        ),
    ),
)

# Kept for the tests and for anything that wants the first one by name.
QUESTION = PINNED[0].question
ANSWER = PINNED[0].answer

# Marks the answer in metadata and in the audit trail, so a pinned answer is
# never mistaken for a live one while debugging.
ANSWER_SOURCE = "demo-template"


# An opening greeting, which is address rather than question.
_GREETING = re.compile(r"^(?:hi|hey|hello)\b[\s,]*(?:zara\b[\s,]*)?", re.I)

# Grammar that differs without the question differing. Singular and plural of
# the same nouns, and the verb that agrees with them: "which squads have the
# most bugs" asks precisely what "which squad has the most bug" asks.
_GRAMMAR = {
    "squads": "squad",
    "bugs": "bug",
    "teams": "team",
    "releases": "release",
    "shipped": "ship",
    "has": "have",
    "is": "are",
}

# Words that join a question together without saying anything about what is
# being asked. Speech recognition swaps between them freely -- a spoken "how
# many releases did we ship last year" came back as "how many release that we
# ship last year", which is the same question and matched nothing.
#
# Only auxiliaries and relativisers belong here. They can never carry the
# subject or the scope, so dropping them cannot turn one question into
# another: "did MBK ship" still keeps MBK, and "in 2024" still keeps the year.
_FILLER = frozenset({"did", "do", "does", "that"})


def _normalise(message: str) -> str:
    """Fold what is phrasing, and nothing that is meaning.

    Case, spacing, a trailing question mark, an opening greeting,
    singular/plural agreement, and the auxiliaries that hold a question
    together without saying anything.

    Deliberately not a similarity score: every remaining word must still
    match exactly, so "which squad has the most *open* bugs" keeps its extra
    word and stays a different question -- which it is, being a different
    number. Same for a named year and a named squad.
    """

    text = re.sub(r"\s+", " ", (message or "").strip().lower()).rstrip("?.! ")
    text = _GREETING.sub("", text).strip()
    words = (_GRAMMAR.get(word, word) for word in text.split())
    return " ".join(word for word in words if word not in _FILLER)


def demo_answer_for(message: str) -> str | None:
    """The pinned answer for this message, or ``None`` to run the real agent."""

    if not settings.demo_answer_enabled:
        return None
    asked = _normalise(message)
    for pinned in PINNED:
        if asked == _normalise(pinned.question):
            logger.info("Serving the pinned demo answer for %r", pinned.question)
            return pinned.answer
    return None


def demo_result(message: str) -> dict[str, object]:
    """Shape the pinned answer like any other turn, so nothing downstream cares."""

    return {
        "answer": demo_answer_for(message) or PINNED[0].answer,
        "intent": "ANALYSIS",
        "chart": None,
        "table": None,
        "warnings": [],
        "validation": {},
        "metadata": {
            "answer_source": ANSWER_SOURCE,
            "query_ids": [],
            "row_counts": [],
            "demo_answer": True,
        },
        "_persistence": {},
    }


__all__ = [
    "ANSWER",
    "PINNED",
    "PinnedAnswer",
    "ANSWER_SOURCE",
    "QUESTION",
    "demo_answer_for",
    "demo_result",
]
