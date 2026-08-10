"""Evidence validation: every numeric claim in the answer must be grounded.

Guide Section 43 "Evidence validation": check that important claims are
supported by the actual data/result.
"""

from __future__ import annotations

import json
import re
from typing import Any

_NUMBER = re.compile(r"(?<![\w-])-?\d[\d,]*(?:\.\d+)?")


def _number_value(token: str) -> float:
    return float(token.replace(",", ""))


def _is_markdown_list_index(answer: str, match: re.Match[str]) -> bool:
    """Distinguish ``1. item`` from a numeric claim in prose."""

    if match.group(0).startswith("-"):
        return False
    line_start = answer.rfind("\n", 0, match.start()) + 1
    if answer[line_start : match.start()].strip():
        return False
    return bool(re.match(r"[.)]\s", answer[match.end() :]))


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
        _number_value(match.group(0))
        for source in (evidence_text, question)
        for match in _NUMBER.finditer(source)
    ]
    answer_numbers = {
        match.group(0)
        for match in _NUMBER.finditer(answer)
        if not _is_markdown_list_index(answer, match)
    }

    def supported(token: str) -> bool:
        value = _number_value(token)
        decimals = len(token.rsplit(".", 1)[1]) if "." in token else 0
        for evidence in evidence_numbers:
            if abs(value - evidence) <= 0.011 or abs(abs(value) - abs(evidence)) <= 0.011:
                return True
            # A model may reasonably present a validated decimal at lower
            # precision. Compare at exactly the precision it chose rather
            # than allowing one arbitrary unsupported number through.
            if (
                round(evidence, decimals) == value
                or round(abs(evidence), decimals) == abs(value)
            ):
                return True
        return False

    return sorted(token for token in answer_numbers if not supported(token))


__all__ = ["find_unsupported_numbers"]
