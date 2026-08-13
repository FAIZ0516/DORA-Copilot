"""Draw report charts as vector graphics for the PDF.

Charts previously exported as value tables: accurate, but a table of numbers is
not a diagram, and a management report is largely read at a glance. These are
real ReportLab drawings -- vector, so they stay sharp in print and at any zoom,
and they need no browser or headless renderer on the server.

Everything here is deterministic. The captions state only what the data already
says (highest, lowest, total, direction); no model writes them, so a chart's
explanation can never drift from the numbers beside it.
"""

from __future__ import annotations

from typing import Any

from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors

# Same hues as the app's --chart-series-* tokens, so an exported chart and the
# one on screen are recognisably the same chart.
SERIES_COLORS = [
    colors.HexColor("#4f46e5"),
    colors.HexColor("#0ea5e9"),
    colors.HexColor("#14b8a6"),
    colors.HexColor("#f59e0b"),
    colors.HexColor("#f43f5e"),
    colors.HexColor("#8b5cf6"),
    colors.HexColor("#22c55e"),
    colors.HexColor("#64748b"),
]
AXIS = colors.HexColor("#5b6b80")
GRID = colors.HexColor("#e8eef6")

MAX_CATEGORIES = 12


def _number(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return result if result == result else 0.0  # drop NaN


def _short(label: Any, limit: int = 14) -> str:
    text = str(label if label is not None else "")
    return f"{text[: limit - 1]}…" if len(text) > limit else text


def _pretty(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    return f"{value:g}"


def series_of(chart: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in (chart.get("series") or []) if isinstance(item, dict)]


def rows_of(chart: dict[str, Any]) -> list[dict[str, Any]]:
    """Plotted rows, capped so a wide chart stays readable on the page."""

    rows = [row for row in (chart.get("data") or []) if isinstance(row, dict)]
    return rows[:MAX_CATEGORIES]


def describe(chart: dict[str, Any]) -> str:
    """A factual one-line reading of the chart.

    Deliberately mechanical: it reports the extremes and the total that are
    already in the data. Nothing here is inferred, so the sentence under a
    chart cannot contradict the chart.
    """

    series = series_of(chart)
    rows = rows_of(chart)
    if not series or not rows:
        return ""
    primary = series[0]
    key = primary.get("key")
    unit = primary.get("unit") or ""
    x_key = chart.get("x_key") or "label"
    pairs = [(str(row.get(x_key, "")), _number(row.get(key))) for row in rows]
    if not pairs:
        return ""

    top = max(pairs, key=lambda pair: pair[1])
    bottom = min(pairs, key=lambda pair: pair[1])
    total = sum(value for _, value in pairs)
    suffix = f" {unit}" if unit and unit != "%" else ("%" if unit == "%" else "")

    parts = [
        f"{len(pairs)} categories shown.",
        f"Highest: {top[0]} at {_pretty(top[1])}{suffix}.",
    ]
    if bottom[0] != top[0]:
        parts.append(f"Lowest: {bottom[0]} at {_pretty(bottom[1])}{suffix}.")
    # A total is meaningful for counts, misleading for percentages and rates.
    if unit not in {"%", "months", "days"} and len(pairs) > 1:
        parts.append(f"Total across those categories: {_pretty(total)}{suffix}.")
    if len(series) > 1:
        parts.append(f"{len(series)} measures are plotted.")
    return " ".join(parts)


def _legend(drawing: Drawing, series: list[dict[str, Any]], width: float) -> None:
    if len(series) < 2:
        return
    legend = Legend()
    legend.x = 6
    legend.y = 12
    legend.alignment = "right"
    legend.columnMaximum = 2
    legend.fontName = "Helvetica"
    legend.fontSize = 7
    legend.dxTextSpace = 4
    legend.deltax = max(70.0, width / max(len(series), 1))
    legend.colorNamePairs = [
        (SERIES_COLORS[index % len(SERIES_COLORS)], str(item.get("label") or item.get("key")))
        for index, item in enumerate(series)
    ]
    drawing.add(legend)


def _style_axes(chart_obj: Any, labels: list[str], *, horizontal: bool = False) -> None:
    value_axis = chart_obj.valueAxis
    value_axis.valueMin = 0
    value_axis.strokeColor = GRID
    value_axis.gridStrokeColor = GRID
    value_axis.visibleGrid = True
    value_axis.labels.fontName = "Helvetica"
    value_axis.labels.fontSize = 7
    value_axis.labels.fillColor = AXIS

    category_axis = chart_obj.categoryAxis
    category_axis.categoryNames = labels
    category_axis.strokeColor = GRID
    category_axis.labels.fontName = "Helvetica"
    category_axis.labels.fontSize = 7
    category_axis.labels.fillColor = AXIS
    if not horizontal:
        # Angle the labels rather than let long squad names collide.
        category_axis.labels.angle = 30 if any(len(name) > 6 for name in labels) else 0
        category_axis.labels.dy = -6
        category_axis.labels.boxAnchor = "ne" if category_axis.labels.angle else "n"


def draw_chart(chart: dict[str, Any], width: float, height: float = 190.0) -> Drawing | None:
    """Render a chart spec as a vector Drawing, or None if it cannot be drawn."""

    series = series_of(chart)
    rows = rows_of(chart)
    if not series or not rows:
        return None

    kind = str(chart.get("type") or "bar")
    x_key = chart.get("x_key") or "label"
    labels = [_short(row.get(x_key)) for row in rows]
    data = [[_number(row.get(item.get("key"))) for row in rows] for item in series]

    drawing = Drawing(width, height)

    if kind in {"pie", "donut", "polar_area"}:
        values = data[0]
        if sum(values) <= 0:
            return None
        pie = Pie()
        pie.x = 12
        pie.y = 16
        pie.width = min(height - 34, width / 2)
        pie.height = pie.width
        pie.data = values
        pie.labels = labels
        pie.sideLabels = True
        pie.slices.strokeColor = colors.white
        pie.slices.strokeWidth = 1.2
        pie.slices.fontName = "Helvetica"
        pie.slices.fontSize = 7
        if kind == "donut":
            pie.innerRadiusFraction = 0.55
        for index in range(len(values)):
            pie.slices[index].fillColor = SERIES_COLORS[index % len(SERIES_COLORS)]
        drawing.add(pie)
        return drawing

    if kind == "horizontal_bar":
        bars = HorizontalBarChart()
        bars.x = 74
        bars.y = 22
        bars.width = width - 96
        bars.height = height - 40
        bars.data = data
        bars.barSpacing = 1.5
        bars.groupSpacing = 7
        _style_axes(bars, labels, horizontal=True)
        for index in range(len(series)):
            bars.bars[index].fillColor = SERIES_COLORS[index % len(SERIES_COLORS)]
            bars.bars[index].strokeColor = None
        drawing.add(bars)
        _legend(drawing, series, width)
        return drawing

    if kind in {"line", "area"}:
        line = HorizontalLineChart()
        line.x = 44
        line.y = 30
        line.width = width - 62
        line.height = height - 50
        line.data = data
        line.joinedLines = 1
        _style_axes(line, labels)
        for index in range(len(series)):
            line.lines[index].strokeColor = SERIES_COLORS[index % len(SERIES_COLORS)]
            line.lines[index].strokeWidth = 1.8
            line.lines[index].symbol = None
        drawing.add(line)
        _legend(drawing, series, width)
        return drawing

    # bar, stacked_bar and anything else cartesian
    bars = VerticalBarChart()
    bars.x = 44
    bars.y = 30
    bars.width = width - 62
    bars.height = height - 50
    bars.data = data
    bars.barSpacing = 1.5
    bars.groupSpacing = 8
    if kind == "stacked_bar" and len(series) > 1:
        bars.categoryAxis.style = "stacked"
    _style_axes(bars, labels)
    for index in range(len(series)):
        bars.bars[index].fillColor = SERIES_COLORS[index % len(SERIES_COLORS)]
        bars.bars[index].strokeColor = None
    drawing.add(bars)
    _legend(drawing, series, width)
    return drawing


def truncation_note(chart: dict[str, Any]) -> str:
    """Say so when the plot shows only part of the data."""

    total = len([row for row in (chart.get("data") or []) if isinstance(row, dict)])
    if total <= MAX_CATEGORIES:
        return ""
    return (
        f"Showing the first {MAX_CATEGORIES} of {total} categories so the chart stays "
        f"readable. The full set is in the underlying data."
    )


def title_string(drawing: Drawing, text: str, width: float) -> None:
    drawing.add(
        String(
            width / 2, drawing.height - 10, text,
            fontName="Helvetica-Bold", fontSize=8,
            fillColor=colors.HexColor("#1f2d3d"), textAnchor="middle",
        )
    )


__all__ = [
    "MAX_CATEGORIES",
    "SERIES_COLORS",
    "describe",
    "draw_chart",
    "rows_of",
    "series_of",
    "title_string",
    "truncation_note",
]
