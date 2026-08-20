"""One pinned answer, for recording a demonstration.

A demonstration cannot wait thirty seconds for a live answer, so exactly one
question may be answered from a stored response instead of from the database.

Three things keep this from becoming a way to make the assistant say untrue
things:

* It is off unless ``DEMO_ANSWER_ENABLED`` is set, so it cannot fire in normal
  use or on a deployed instance.
* It matches one question exactly. No fuzzy matching, no "close enough" -- a
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

# Accepted verbatim, both with and without the greeting. Two literals, not
# a fuzzy match: dropping "Hi Zara," leaves the same question, and on
# camera the greeting is easy to forget.
ACCEPTED = (
    QUESTION,
    "which squad have the most bug?",
)

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


def _normalise(message: str) -> str:
    """Fold the differences that are not the user asking something else.

    Case, spacing and a trailing question mark. Nothing more: matching loosely
    is how a pinned answer would start appearing on questions it does not
    actually answer.
    """

    return re.sub(r"\s+", " ", (message or "").strip().lower()).rstrip("?.! ")


def demo_answer_for(message: str) -> str | None:
    """The pinned answer for this message, or ``None`` to run the real agent."""

    if not settings.demo_answer_enabled:
        return None
    if _normalise(message) not in {_normalise(q) for q in ACCEPTED}:
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
    "ACCEPTED",
    "ANSWER",
    "ANSWER_SOURCE",
    "QUESTION",
    "demo_answer_for",
    "demo_result",
]
