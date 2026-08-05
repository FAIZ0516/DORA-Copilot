"""Schema, quality, business-rule, and answer consistency validation."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from ..doradb_catalog import QUERY_CATALOGUE


_PERCENT_FIELDS = {"change_failure_rate_pct", "outcome_rating"}
_NON_NEGATIVE_FRAGMENTS = ("time", "frequency", "count", "ratio", "rating")


def validate_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[str] = []
    current_year = date.today().year
    if not results:
        return {
            "valid": True,
            "status": "empty",
            "checks": ["empty_results"],
            "errors": [],
            "warnings": ["No query results were returned."],
        }
    for result in results:
        query_id = result.get("query_id")
        rows = result.get("rows")
        if query_id not in QUERY_CATALOGUE or not isinstance(rows, list):
            errors.append("Result envelope is invalid.")
            continue
        expected = set(QUERY_CATALOGUE[query_id]["expected_columns"])
        if rows:
            missing = expected - set(rows[0])
            if missing:
                errors.append(f"{query_id} missing fields: {', '.join(sorted(missing))}")
        else:
            if query_id == "list_dimension_values":
                dimension = str(result.get("filters", {}).get("dimension", "values"))
                label = dimension.replace("_", " ")
                warnings.append(
                    f"No matching {label} values were returned for the applied filters."
                )
            else:
                warnings.append(f"{query_id} returned no matching rows.")
        checks.append("expected_columns")

        serialized = [json.dumps(row, sort_keys=True, default=str) for row in rows]
        if len(serialized) != len(set(serialized)):
            warnings.append(f"{query_id} contains duplicate rows.")
        checks.append("duplicate_rows")

        for row_index, row in enumerate(rows):
            if row.get("release_year") == current_year:
                warnings.append(
                    f"{current_year} is the current calendar year and may be incomplete; "
                    "treat its totals as year-to-date unless the source proves otherwise."
                )
            for key, value in row.items():
                if value is None:
                    continue
                if isinstance(value, (int, float)):
                    lowered = key.lower()
                    if any(fragment in lowered for fragment in _NON_NEGATIVE_FRAGMENTS) and value < 0:
                        errors.append(f"{query_id} row {row_index + 1} has negative {key}.")
                    if key == "change_failure_rate_pct" and not 0 <= value <= 100:
                        errors.append(f"{query_id} row {row_index + 1} has invalid percentage.")
                    if key == "outcome_rating" and not 0 <= value <= 1:
                        warnings.append(f"{query_id} row {row_index + 1} outcome rating is outside 0-1.")
                if key.endswith("_date") and isinstance(value, str):
                    try:
                        date.fromisoformat(value[:10])
                    except ValueError:
                        errors.append(f"{query_id} row {row_index + 1} has invalid {key}.")
        checks.extend(["numeric_ranges", "date_parseability", "business_rules"])
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
    """Reject numeric claims absent from the question or validated evidence."""

    evidence_text = json.dumps(
        {"results": results, "deterministic_analysis": analysis or {}},
        default=str,
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
            abs(value - evidence) <= 0.011
            or abs(abs(value) - abs(evidence)) <= 0.011
            for evidence in evidence_numbers
        )

    unsupported = sorted(token for token in answer_numbers if not supported(token))
    # Markdown list indices and rounded values can be legitimate. Only fail when
    # more than one unsupported numeric claim appears.
    warning_missing = bool(required_warnings) and not any(
        warning.lower()[:35] in answer.lower() for warning in required_warnings
    )
    current_year = date.today().year
    temporal_errors: list[str] = []
    incomplete_language = (
        r"(?:partial|year[- ]to[- ]date|ytd|so far|still in progress|"
        r"in-progress|may be incomplete|provisional|"
        r"until (?:more|additional) (?:data|releases?|records?) (?:accumulate|arrive)|"
        r"slow start(?: to the year)?)"
    )
    for year_text in set(re.findall(r"\b20\d{2}\b", answer)):
        year = int(year_text)
        if year >= current_year:
            continue
        if re.search(
            rf"(?:\b{year}\b.{{0,90}}{incomplete_language}|"
            rf"{incomplete_language}.{{0,90}}\b{year}\b)",
            answer,
            re.I | re.S,
        ):
            temporal_errors.append(
                f"Completed calendar year {year} was described as in progress."
            )
    valid = len(unsupported) <= 1 and not warning_missing and not temporal_errors
    return {
        "valid": valid,
        "unsupported_numbers": unsupported,
        "warning_missing": warning_missing,
        "temporal_errors": temporal_errors,
    }
