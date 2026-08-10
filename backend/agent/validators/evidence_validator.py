"""Evidence validation: every numeric claim in the answer must be grounded.

Guide Section 43 "Evidence validation": check that important claims are
supported by the actual data/result.
"""

from __future__ import annotations

import json
import re
from typing import Any


def find_unsupported_numbers(
    answer: str,
    *,
    results: list[dict[str, Any]],
    analysis: dict[str, Any] | None,
    question: str,
) -> list[str]:
    """Reject numeric claims absent from the question or validated evidence."""

    evidence_text = json.dumps(
        {"results": results, "deterministic_analysis": analysis or {}}, default=str
    )
    evidence_numbers = [
        float(token)
        for source in (evidence_text, question)
        for token in re.findall(r"(?<![\w-])-?\d+(?:\.\d+)?", source)
    ]
    answer_numbers = set(re.findall(r"(?<![\w-])-?\d+(?:\.\d+)?", answer))

    def supported(token: str) -> bool:
        value = float(token)
        return any(
            abs(value - evidence) <= 0.011 or abs(abs(value) - abs(evidence)) <= 0.011
            for evidence in evidence_numbers
        )

    # Markdown list indices and rounded values can be legitimate; the caller
    # only fails validation when more than one unsupported claim appears.
    return sorted(token for token in answer_numbers if not supported(token))


__all__ = ["find_unsupported_numbers"]
