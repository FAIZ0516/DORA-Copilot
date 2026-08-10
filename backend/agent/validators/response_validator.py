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


def required_warnings_missing(answer: str, required_warnings: list[str]) -> bool:
    """Required limitations (e.g. from result validation) must appear in the answer."""

    return bool(required_warnings) and not any(
        warning.lower()[:35] in answer.lower() for warning in required_warnings
    )


def check_response_safety(answer: str) -> list[str]:
    """Restricted data is not exposed -- delegates to the output guardrail."""

    return check_output_safety(answer)


__all__ = ["check_response_safety", "find_temporal_errors", "required_warnings_missing"]
