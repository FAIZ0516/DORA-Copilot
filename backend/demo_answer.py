"""One pinned answer, for recording a demonstration.

A demonstration cannot wait thirty seconds for a live answer, so exactly one
question may be answered from a stored response instead of from the database.

Three things keep this from becoming a way to make the assistant say untrue
things:

* It is off unless ``DEMO_ANSWER_ENABLED`` is set, so it cannot fire in normal
  use or on a deployed instance.
* It matches one question exactly. No fuzzy matching, no "close enough" -- a
  different question always reaches the real agent.
* The text below is not written by hand. It is what the assistant itself
  answered on 2026-08-20, copied verbatim, so the demonstration shows the
  product's own words rather than an idealised version of them.

The figures are therefore a snapshot. If the underlying data moves, this text
goes stale and will contradict the dashboard -- regenerate it before recording
by asking the question with the flag off.
"""

from __future__ import annotations

import logging
import re

from .config import settings

logger = logging.getLogger(__name__)

QUESTION = "Which squad has the most bugs?"

ANSWER = (
    "MBK has the most bugs, with 1,434 in the DCPM project data, ahead of "
    "JAEGER at 1,368 and Droid Spark at 1,003.\n\n"
    "These counts cover issues that have a squad recorded; 63,481 issue rows "
    "in the snapshot carry no squad, so the ranking reflects only the 21 named "
    "squads, not all open work."
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


__all__ = ["ANSWER", "ANSWER_SOURCE", "QUESTION", "demo_answer_for", "demo_result"]
