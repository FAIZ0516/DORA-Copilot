"""Metric validation: numeric ranges, business rules, date parseability.

Guide Section 43 "Metric validation": percentage in valid range; non-negative
counts; consistent totals; valid denominators; valid time intervals.
"""

from __future__ import annotations

from datetime import date
from typing import Any

_NON_NEGATIVE_FRAGMENTS = ("time", "frequency", "count", "ratio", "rating")


def validate_metric_rows(
    query_id: str, rows: list[dict[str, Any]]
) -> tuple[list[str], list[str], list[str]]:
    """Return (errors, warnings, checks) for one query result's row values."""

    errors: list[str] = []
    warnings: list[str] = []
    checks: list[str] = []
    current_year = date.today().year
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
    return errors, warnings, checks


__all__ = ["validate_metric_rows"]
