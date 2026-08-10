"""Deterministic comparisons so arithmetic is not delegated to the LLM."""

from __future__ import annotations

from typing import Any


def compare_rows(rows: list[dict[str, Any]], field: str, key: str = "release_year") -> list[dict[str, Any]]:
    points = [
        (row.get(key), float(row[field]))
        for row in rows
        if row.get(key) is not None and isinstance(row.get(field), (int, float))
    ]
    points.sort(key=lambda item: str(item[0]))
    comparisons: list[dict[str, Any]] = []
    for (previous_key, previous), (current_key, current) in zip(points, points[1:]):
        absolute = current - previous
        percent = (absolute / abs(previous) * 100) if previous else None
        comparisons.append(
            {
                "from": previous_key,
                "to": current_key,
                "absolute_change": round(absolute, 4),
                "percent_change": round(percent, 2) if percent is not None else None,
                "direction": "up" if absolute > 0 else "down" if absolute < 0 else "flat",
            }
        )
    return comparisons
