"""Validation: deterministic checks split by concern (guide Section 43).

``validate_results``/``validate_answer`` are the two composed entry points
the orchestrator calls -- this preserves the previous single-module public
API (``result_validator.py``) while each concern now has one focused,
independently testable module instead of two functions that mixed every
concern together.
"""

from __future__ import annotations

from typing import Any

from .data_validator import validate_result_envelope
from .evidence_validator import find_unsupported_numbers
from .metric_validator import validate_metric_rows
from .request_validator import validate_plan_shape, validate_query_action_shape
from .response_validator import (
    check_response_safety,
    find_temporal_errors,
    required_warnings_missing,
)


def validate_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "valid": True,
            "status": "empty",
            "checks": ["empty_results"],
            "errors": [],
            "warnings": ["No query results were returned."],
        }
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[str] = []
    for result in results:
        envelope_errors, envelope_warnings, envelope_checks, rows = validate_result_envelope(
            result
        )
        errors.extend(envelope_errors)
        warnings.extend(envelope_warnings)
        checks.extend(envelope_checks)
        if rows is None:
            continue
        query_id = str(result.get("query_id", ""))
        metric_errors, metric_warnings, metric_checks = validate_metric_rows(query_id, rows)
        errors.extend(metric_errors)
        warnings.extend(metric_warnings)
        checks.extend(metric_checks)
        warnings.extend(str(item) for item in result.get("warnings", []))
    return {
        "valid": not errors,
        "status": "passed" if not errors else "failed",
        "checks": sorted(set(checks)),
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
    }


def validate_answer(
    answer: str,
    *,
    results: list[dict[str, Any]],
    analysis: dict[str, Any] | None = None,
    question: str,
    required_warnings: list[str],
) -> dict[str, Any]:
    unsupported = find_unsupported_numbers(
        answer, results=results, analysis=analysis, question=question
    )
    warning_missing = required_warnings_missing(answer, required_warnings)
    temporal_errors = find_temporal_errors(answer)
    restricted_field_leaks = check_response_safety(answer)
    valid = (
        not unsupported
        and not warning_missing
        and not temporal_errors
        and not restricted_field_leaks
    )
    return {
        "valid": valid,
        "unsupported_numbers": unsupported,
        "warning_missing": warning_missing,
        "temporal_errors": temporal_errors,
        "restricted_field_leaks": restricted_field_leaks,
    }


__all__ = [
    "check_response_safety",
    "validate_answer",
    "validate_plan_shape",
    "validate_query_action_shape",
    "validate_results",
]
