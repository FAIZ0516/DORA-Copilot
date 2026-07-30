"""Map business language and synonyms to governed metric definitions."""

from __future__ import annotations

from typing import TypedDict


class MetricSelection(TypedDict):
    id: str
    field: str
    label: str
    unit: str
    direction: str


_METRICS: tuple[tuple[tuple[str, ...], MetricSelection], ...] = (
    (
        ("release frequency", "release cadence"),
        {"id": "release_frequency", "field": "release_frequency_months", "label": "Release frequency", "unit": "months", "direction": "lower_is_better"},
    ),
    (
        ("failure", "cfr", "outcome"),
        {"id": "change_failure_rate", "field": "change_failure_rate_pct", "label": "Change failure rate", "unit": "%", "direction": "lower_is_better"},
    ),
    (
        ("lead time", "load time", "ltc"),
        {"id": "lead_time_for_change", "field": "lead_time_for_change_months", "label": "Lead time for change", "unit": "months", "direction": "lower_is_better"},
    ),
    (
        ("cycle", "delivery time"),
        {"id": "delivery_cycle_time", "field": "delivery_cycle_time_months", "label": "Delivery cycle time", "unit": "months", "direction": "lower_is_better"},
    ),
    (
        ("release count", "number of release", "how many release"),
        {"id": "release_count", "field": "release_count", "label": "Major release count", "unit": "releases", "direction": "contextual"},
    ),
    (
        ("ratio", "per feature"),
        {"id": "story_to_feature_ratio", "field": "user_story_to_feature_ratio", "label": "User Story-to-Feature ratio", "unit": "ratio", "direction": "contextual"},
    ),
)

_DEFAULT_METRIC: MetricSelection = {
    "id": "release_frequency",
    "field": "release_frequency_months",
    "label": "Release frequency",
    "unit": "months",
    "direction": "lower_is_better",
}

_DELIVERY_PERFORMANCE_METRIC: MetricSelection = {
    "id": "delivery_performance",
    "field": "release_frequency_months",
    "label": "Overall delivery performance",
    "unit": "",
    "direction": "contextual",
}


def select_metric(message: str) -> MetricSelection:
    lowered = message.lower()
    for synonyms, metric in _METRICS:
        if any(synonym in lowered for synonym in synonyms):
            return dict(metric)  # type: ignore[return-value]
    return dict(_DEFAULT_METRIC)


def message_mentions_metric(message: str) -> bool:
    """Return whether the user explicitly named a supported metric."""

    lowered = message.lower()
    return any(
        synonym in lowered
        for synonyms, _metric in _METRICS
        for synonym in synonyms
    )


def select_metric_by_id(metric_id: str | None) -> MetricSelection:
    """Resolve a metric stored in structured memory."""

    if metric_id:
        if metric_id == _DELIVERY_PERFORMANCE_METRIC["id"]:
            return dict(_DELIVERY_PERFORMANCE_METRIC)
        for _synonyms, metric in _METRICS:
            if metric["id"] == metric_id:
                return dict(metric)  # type: ignore[return-value]
    return dict(_DEFAULT_METRIC)


def select_delivery_performance_metric() -> MetricSelection:
    """Return the holistic metric used for multi-metric recommendations."""

    return dict(_DELIVERY_PERFORMANCE_METRIC)
