"""Response models: the shapes a responder is allowed to return.

Moved out of ``backend/schemas.py`` so the agent's response layer owns its
own output contract (guide Section 42). ``backend/schemas.py`` re-exports
these for the API layer's ``ChatResponse`` -- its contract with the
frontend -- so there is exactly one definition of each shape, not two.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChartSeries(BaseModel):
    key: str
    label: str
    unit: str = ""


class ChartData(BaseModel):
    type: Literal[
        "bar",
        "horizontal_bar",
        "stacked_bar",
        "line",
        "area",
        "pie",
        "donut",
        "scatter",
        "radar",
        "polar_area",
        "table",
        "metric_card",
    ]
    title: str
    x_key: str | None = None
    x_label: str | None = None
    point_label_key: str | None = None
    series: list[ChartSeries] = Field(default_factory=list)
    data: list[dict[str, Any]] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)
    unit: str = ""


class DataTable(BaseModel):
    title: str
    columns: list[dict[str, str]]
    rows: list[dict[str, Any]]
    truncated: bool = False


__all__ = ["ChartData", "ChartSeries", "DataTable"]
