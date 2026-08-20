"""One pinned answer, for recording a demonstration.

A demonstration cannot wait thirty seconds for a live answer, so exactly one
question may be answered from a stored response instead of from the database.

Three things keep this from becoming a way to make the assistant say untrue
things:

* It is off unless ``DEMO_ANSWER_ENABLED`` is set, so it cannot fire in normal
  use or on a deployed instance.
* It matches one question. Greeting, case, spacing and singular/plural are
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

from .config import settings

logger = logging.getLogger(__name__)

QUESTION = "Hi Zara, which squad have the most bug?"

ANSWER = (
    "Hi! Based on the DCPM data as of the current snapshot, **MBK** is the squad with the most bugs \u2014 1,434, more than any other squad.\n"
    "\n"
    "Top three by bug count:\n"
    "- MBK \u2014 1,434\n"
    "- JAEGER \u2014 1,368\n"
    "- Droid Spark \u2014 1,003\n"
    "\n"
    "One caveat: these totals cover only bugs that carry a squad tag. A large part of the dataset has no squad recorded, so the ranking could shift if that work were attributed. MBK still leads by a clear margin on the tagged work."
)

# Marks the answer in metadata and in the audit trail, so a pinned answer is
# never mistaken for a live one while debugging.
ANSWER_SOURCE = "demo-template"


# An opening greeting, which is address rather than question.
_GREETING = re.compile(r"^(?:hi|hey|hello)\b[\s,]*(?:zara\b[\s,]*)?", re.I)

# Grammar that differs without the question differing. Singular and plural of
# the same nouns, and the verb that agrees with them: "which squads have the
# most bugs" asks precisely what "which squad has the most bug" asks.
_GRAMMAR = {"squads": "squad", "bugs": "bug", "teams": "team", "has": "have", "is": "are"}


def _normalise(message: str) -> str:
    """Fold what is phrasing, and nothing that is meaning.

    Case, spacing, a trailing question mark, an opening greeting, and
    singular/plural agreement. Deliberately not a similarity score: every
    remaining word must still match exactly, so "which squad has the most
    *open* bugs" keeps its extra word and stays a different question -- which
    it is, being a different number.
    """

    text = re.sub(r"\s+", " ", (message or "").strip().lower()).rstrip("?.! ")
    text = _GREETING.sub("", text).strip()
    return " ".join(_GRAMMAR.get(word, word) for word in text.split())


def demo_answer_for(message: str) -> str | None:
    """The pinned answer for this message, or ``None`` to run the real agent."""

    if not settings.demo_answer_enabled:
        return None
    if _normalise(message) != _normalise(QUESTION):
        return None
    logger.info("Serving the pinned demo answer for %r", QUESTION)
    return ANSWER


def demo_result(message: str) -> dict[str, object]:
    """Shape the pinned answer like any other turn, so nothing downstream cares."""

    return {
        "answer": demo_answer_for(message) or ANSWER,
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
    "ANSWER_SOURCE",
    "QUESTION",
    "demo_answer_for",
    "demo_result",
]
