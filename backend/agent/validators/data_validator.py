"""Data validation: required fields, types, duplicates, empty results.

Guide Section 43 "Data validation": required fields present; data types
correct; duplicates handled; null/missing values understood; reporting
period valid.
"""

from __future__ import annotations

import json
from typing import Any

from ...database.doradb_catalog import QUERY_CATALOGUE


def validate_result_envelope(
    result: dict[str, Any],
) -> tuple[list[str], list[str], list[str], list[dict[str, Any]] | None]:
    """Return (errors, warnings, checks, rows) for one query result.

    ``rows`` is ``None`` iff the envelope itself is invalid (unknown
    ``query_id`` or non-list ``rows``) -- callers must not attempt further
    per-row validation in that case. A "missing expected fields" error does
    *not* set ``rows`` to ``None``: the caller still validates whatever rows
    came back.
    """

    errors: list[str] = []
    warnings: list[str] = []
    checks: list[str] = []
    query_id = result.get("query_id")
    rows = result.get("rows")
    if query_id not in QUERY_CATALOGUE or not isinstance(rows, list):
        errors.append("Result envelope is invalid.")
        return errors, warnings, checks, None

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

    return errors, warnings, checks, rows


__all__ = ["validate_result_envelope"]
