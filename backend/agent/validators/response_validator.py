"""Response validation: the final answer is consistent with validated evidence.

Guide Section 43 "Response validation": conclusion does not contradict
validated metrics; facts and interpretations are clearly separated; required
limitations are included; restricted data is not exposed. The last check is
delegated to ``guardrails.output_guardrail``, which is the one authoritative
implementation of restricted-field-leak detection -- reused here, not
duplicated.
"""

from __future__ import annotations

import re
from datetime import date

from ..guardrails.output_guardrail import check_output_safety

_INCOMPLETE_LANGUAGE = (
    r"(?:partial|year[- ]to[- ]date|ytd|so far|still in progress|"
    r"in-progress|may be incomplete|provisional|"
    r"until (?:more|additional) (?:data|releases?|records?) (?:accumulate|arrive)|"
    r"slow start(?: to the year)?)"
)


def find_temporal_errors(answer: str) -> list[str]:
    """A completed calendar year must never be described as still in progress."""

    current_year = date.today().year
    temporal_errors: list[str] = []
    for year_text in set(re.findall(r"\b20\d{2}\b", answer)):
        year = int(year_text)
        if year >= current_year:
            continue
        if re.search(
            rf"(?:\b{year}\b.{{0,90}}{_INCOMPLETE_LANGUAGE}|"
            rf"{_INCOMPLETE_LANGUAGE}.{{0,90}}\b{year}\b)",
            answer,
            re.I | re.S,
        ):
            temporal_errors.append(
                f"Completed calendar year {year} was described as in progress."
            )
    return temporal_errors


_WARNING_STOPWORDS = frozenset(
    {
        "the", "and", "for", "was", "are", "its", "not", "this", "that", "with",
        "from", "have", "has", "been", "were", "may", "can", "but", "all", "any",
        "returned", "matching", "values", "value", "rows", "row", "them", "their",
        "there", "which", "when", "into", "than", "then", "some", "such", "only",
        "unless", "until", "treat", "proves", "prove", "should", "would", "could",
    }
)


def _warning_keywords(warning: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]{4,}", warning.lower())
        if token not in _WARNING_STOPWORDS
    }


def _warning_conveyed(answer: str, warning: str) -> bool:
    """Return whether ``answer`` preserves one warning's user-facing meaning.

    Known validator warnings get small semantic checks so internal names do
    not have to leak into the answer. Unknown warnings retain a conservative
    keyword-overlap fallback.
    """

    lowered_answer = answer.lower()
    lowered_warning = warning.lower()

    if "no query results" in lowered_warning or (
        "no matching" in lowered_warning
        and ("rows" in lowered_warning or "values" in lowered_warning)
    ):
        return bool(
            re.search(
                r"\b(?:nothing|none)\s+matched\b|\bno\s+(?:matching\s+)?"
                r"(?:results?|records?|items?|data|values?)\b|"
                r"\b(?:could not|couldn't|did not|didn't)\s+find\b",
                lowered_answer,
            )
        )

    if "duplicate rows" in lowered_warning:
        return bool(re.search(r"\b(?:duplicate|duplicated|repeated)\b", lowered_answer))

    if "current calendar year" in lowered_warning and "incomplete" in lowered_warning:
        year_match = re.search(r"\b20\d{2}\b", warning)
        year_is_present = not year_match or year_match.group(0) in lowered_answer
        return year_is_present and bool(re.search(_INCOMPLETE_LANGUAGE, lowered_answer, re.I))

    if "outcome rating is outside" in lowered_warning:
        return "outcome" in lowered_answer and bool(
            re.search(r"\b(?:outside|invalid|out of range)\b", lowered_answer)
        )

    if "materialized view may be stale" in lowered_warning:
        return bool(
            re.search(
                r"\b(?:stale|out[- ]of[- ]date|not (?:fully )?current|"
                r"pending (?:a )?refresh)\b",
                lowered_answer,
            )
        )

    if "authoritative" in lowered_warning and "squad directory" in lowered_warning:
        subject_present = bool(re.search(r"\b(?:squads?|teams?)\b", lowered_answer))
        limitation_present = bool(
            re.search(
                r"\b(?:not|isn't|aren't)\s+(?:an?\s+)?(?:official|authoritative)\b|"
                r"\breporting labels?\b|\b(?:not|may not)\s+match\s+(?:the |your )?"
                r"(?:org(?:anisation|anization)? chart|team directory)\b",
                lowered_answer,
            )
        )
        return subject_present and limitation_present

    keywords = _warning_keywords(warning)
    if not keywords:
        return warning.lower()[:35] in lowered_answer
    answer_tokens = set(re.findall(r"[a-z0-9]{4,}", lowered_answer))
    hits = len(keywords & answer_tokens)
    return hits * 2 >= len(keywords)


def required_warnings_missing(answer: str, required_warnings: list[str]) -> bool:
    """Required limitations must be conveyed in the answer.

    Checks that every warning's *substance* survives, not its exact wording.
    The responder is instructed to reword limitations into plain business
    language, so a verbatim-prefix check would force internal validator text
    into otherwise user-friendly answers.
    """

    if not required_warnings:
        return False
    return any(not _warning_conveyed(answer, warning) for warning in required_warnings)


def check_response_safety(answer: str) -> list[str]:
    """Restricted data is not exposed -- delegates to the output guardrail."""

    return check_output_safety(answer)


__all__ = ["check_response_safety", "find_temporal_errors", "required_warnings_missing"]
