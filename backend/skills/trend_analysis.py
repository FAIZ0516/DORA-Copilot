"""Explain the direction and size of a validated metric series."""

from __future__ import annotations

from typing import Any


def analyze_trend(rows: list[dict[str, Any]], field: str, key: str = "release_year") -> dict[str, Any]:
    values = [
        (row.get(key), float(row[field]))
        for row in rows
        if row.get(key) is not None and isinstance(row.get(field), (int, float))
    ]
    values.sort(key=lambda item: str(item[0]))
    if len(values) < 2:
        return {"direction": "insufficient_data", "points": len(values)}
    delta = values[-1][1] - values[0][1]
    tolerance = max(abs(values[0][1]) * 0.03, 0.01)
    direction = "stable" if abs(delta) <= tolerance else "increasing" if delta > 0 else "decreasing"
    return {
        "direction": direction,
        "points": len(values),
        "start_period": values[0][0],
        "end_period": values[-1][0],
        "absolute_change": round(delta, 4),
    }
