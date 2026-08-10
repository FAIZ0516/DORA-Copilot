"""Transparent z-score anomaly flags over validated numeric evidence."""

from __future__ import annotations

import math
from typing import Any


def detect_anomalies(
    rows: list[dict[str, Any]],
    field: str,
    key: str = "release_year",
    *,
    threshold: float = 2.0,
) -> list[dict[str, Any]]:
    points = [
        (row.get(key), float(row[field]))
        for row in rows
        if row.get(key) is not None and isinstance(row.get(field), (int, float))
    ]
    if len(points) < 3:
        return []
    mean = sum(value for _, value in points) / len(points)
    variance = sum((value - mean) ** 2 for _, value in points) / len(points)
    standard_deviation = math.sqrt(variance)
    if standard_deviation == 0:
        return []
    return [
        {"period": period, "value": value, "z_score": round((value - mean) / standard_deviation, 2)}
        for period, value in points
        if abs((value - mean) / standard_deviation) >= threshold
    ]
