"""Create truthful, frontend-neutral chart specifications from validated rows."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any


YEARLY_METRIC_SERIES: tuple[dict[str, str], ...] = (
    {
        "key": "release_frequency_months",
        "label": "Release frequency",
        "unit": "months",
    },
    {
        "key": "change_failure_rate_pct",
        "label": "Change failure rate",
        "unit": "%",
    },
    {
        "key": "lead_time_for_change_months",
        "label": "Lead time for change",
        "unit": "months",
    },
    {
        "key": "delivery_cycle_time_months",
        "label": "Delivery cycle time",
        "unit": "months",
    },
)


def _requested_chart_type(question: str) -> str:
    lowered = question.lower()
    chart_tokens = (
        (r"\b(horizontal|horizontal bar)\b", "horizontal_bar"),
        (r"\b(stacked|stacked bar)\b", "stacked_bar"),
        (r"\b(doughnut|donut)\b", "donut"),
        (r"\bpolar(?: area)?\b", "polar_area"),
        (r"\bradar\b", "radar"),
        (r"\bscatter(?: plot)?\b", "scatter"),
        (r"\barea(?: chart| graph)?\b", "area"),
        (r"\bline(?: chart| graph)?\b", "line"),
        (r"\bpie(?: chart)?\b", "pie"),
        (r"\b(table|tabular)\b", "table"),
        (r"\b(bar|column)(?: chart| graph)?\b", "bar"),
    )
    for pattern, chart_type in chart_tokens:
        if re.search(pattern, lowered):
            return chart_type
    return "bar"


def _all_metrics_requested(question: str) -> bool:
    return bool(
        re.search(
            r"\b(all|every|available)\b.{0,20}\b(dora )?metrics?\b|"
            r"\bmetrics?\b.{0,20}\b(all|every|available)\b",
            question,
            re.I,
        )
    )


def _yearly_chart(
    rows: list[dict[str, Any]],
    metric: dict[str, str],
    question: str,
    requested_type: str,
) -> dict[str, Any]:
    all_metrics = _all_metrics_requested(question)

    if requested_type == "scatter":
        points = [
            {
                "period": str(row["release_year"]),
                "lead_time": float(row["lead_time_for_change_months"]),
                "cycle_time": float(row["delivery_cycle_time_months"]),
            }
            for row in rows
            if row.get("lead_time_for_change_months") is not None
            and row.get("delivery_cycle_time_months") is not None
        ]
        return {
            "type": "scatter",
            "title": "Lead time vs delivery cycle time by year",
            "x_key": "lead_time",
            "x_label": "Lead time for change (months)",
            "point_label_key": "period",
            "series": [
                {
                    "key": "cycle_time",
                    "label": "Delivery cycle time",
                    "unit": "months",
                }
            ],
            "data": points,
        }

    if all_metrics and requested_type not in {"pie", "donut", "polar_area"}:
        series = [dict(item) for item in YEARLY_METRIC_SERIES]
        points = [
            {
                "period": str(row["release_year"]),
                **{
                    item["key"]: float(row[item["key"]])
                    for item in YEARLY_METRIC_SERIES
                    if row.get(item["key"]) is not None
                },
            }
            for row in rows
        ]
        return {
            "type": requested_type,
            "title": "DORA metrics by year",
            "x_key": "period",
            "series": series,
            "data": points,
        }

    field = metric["field"]
    points = [
        {"period": str(row["release_year"]), "value": float(row[field])}
        for row in rows
        if row.get(field) is not None
    ]
    return {
        "type": requested_type,
        "title": f"{metric['label']} by year",
        "x_key": "period",
        "series": [
            {"key": "value", "label": metric["label"], "unit": metric["unit"]}
        ],
        "data": points,
    }


def build_chart_spec(
    *,
    query_id: str,
    rows: list[dict[str, Any]],
    metric: dict[str, str],
    question: str,
) -> dict[str, Any] | None:
    """Map validated query rows to real chart coordinates and series."""

    if not rows:
        return None
    requested_type = _requested_chart_type(question)
    if requested_type == "table":
        return None

    if query_id in {"dora_metrics_by_year", "dora_metrics_by_squad"}:
        return _yearly_chart(rows, metric, question, requested_type)

    if query_id == "dora_metrics_release_detail":
        detail_fields = {
            "change_failure_rate": ("outcome_rating", "Release outcome rating", ""),
            "lead_time_for_change": ("ltc", "Lead time by release", "months"),
            "delivery_cycle_time": (
                "delivery_cycle_time",
                "Cycle time by release",
                "months",
            ),
        }
        field, title, unit = detail_fields.get(
            metric["id"],
            ("release_frequency", "Release frequency by release", "months"),
        )
        points = [
            {"period": str(row["fixversion"]), "value": float(row[field])}
            for row in rows[:30]
            if row.get(field) is not None
        ]
        return {
            "type": requested_type,
            "title": title,
            "x_key": "period",
            "series": [{"key": "value", "label": title, "unit": unit}],
            "data": points,
        }

    if query_id == "story_to_feature_ratio":
        points = [
            {
                "period": str(row["fixversion"]),
                "ratio": float(row["user_story_to_feature_ratio"]),
                "stories": float(row.get("user_story_count") or 0),
                "features": float(row.get("feature_count") or 0),
            }
            for row in rows[:30]
            if row.get("user_story_to_feature_ratio") is not None
        ]
        show_counts = _all_metrics_requested(question) or bool(
            re.search(r"\b(count|stories|features|grouped|stacked)\b", question, re.I)
        )
        series = (
            [
                {"key": "stories", "label": "User Stories", "unit": "references"},
                {"key": "features", "label": "Features", "unit": "references"},
            ]
            if show_counts
            else [{"key": "ratio", "label": "Story-to-Feature ratio", "unit": "ratio"}]
        )
        return {
            "type": requested_type,
            "title": "User Story-to-Feature analysis by release",
            "x_key": "period",
            "series": series,
            "data": points,
        }

    counts = Counter(str(row.get("issuetype") or "Unknown") for row in rows)
    safe_type = (
        requested_type
        if requested_type not in {"line", "area", "scatter", "radar"}
        else "bar"
    )
    return {
        "type": safe_type,
        "title": "Returned Jira references by issue type",
        "x_key": "type",
        "series": [{"key": "count", "label": "References", "unit": "references"}],
        "data": [{"type": name, "count": count} for name, count in counts.items()],
    }
