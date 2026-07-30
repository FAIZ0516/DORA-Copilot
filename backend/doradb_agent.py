"""Compatibility imports for the governed DoraDB agent."""

from .agent_system.graph import AdvancedDoraDbAgent
from .agent_system.planner import deterministic_plan
from .doradb import DoraDbQueryRejected
from .skills.chart_generation import build_chart_spec
from .skills.metric_selection import select_metric

DoraDbAgent = AdvancedDoraDbAgent


def _local_plan(message: str):
    """Backward-compatible deterministic planner used by focused unit tests."""

    return deterministic_plan(message, {"turns": [], "last_context": {}})


def _make_chart(results, question):
    """Return the legacy chart fields alongside the richer chart contract."""

    if not results or not results[0].get("rows"):
        return None
    metric = select_metric(question)
    chart = build_chart_spec(
        query_id=results[0]["query_id"],
        rows=results[0]["rows"],
        metric=metric,
        question=question,
    )
    if not chart:
        return None
    values = [
        float(row[chart["series"][0]["key"]])
        for row in chart["data"]
        if row.get(chart["series"][0]["key"]) is not None
    ]
    labels = [str(row.get(chart["x_key"], "")) for row in chart["data"]]
    return {
        **chart,
        "labels": labels,
        "values": values,
        "unit": chart["series"][0].get("unit", ""),
    }


__all__ = ["DoraDbAgent", "DoraDbQueryRejected", "_local_plan", "_make_chart"]
