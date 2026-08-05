"""Deterministic analytics skills used by the governed agent graph."""

from .anomaly_detection import detect_anomalies
from .chart_generation import build_chart_spec
from .comparison import compare_rows
from .dimension_discovery import (
    DIMENSION_ALIASES,
    is_scope_widening_request,
    match_discovery_dimension,
)
from .entity_grounding import (
    clear_entity_catalogue_cache,
    compact_catalogue,
    filter_value_is_grounded,
    load_entity_catalogue,
    merge_memory_entities,
    resolve_entities,
)
from .filter_extraction import extract_filters
from .intent_matching import classify_intent
from .metric_selection import (
    message_mentions_metric,
    select_delivery_performance_metric,
    select_metric,
    select_metric_by_id,
)
from .query_execution import execute_approved_query
from .trend_analysis import analyze_trend

__all__ = [
    "analyze_trend",
    "build_chart_spec",
    "classify_intent",
    "compare_rows",
    "detect_anomalies",
    "DIMENSION_ALIASES",
    "clear_entity_catalogue_cache",
    "compact_catalogue",
    "execute_approved_query",
    "extract_filters",
    "filter_value_is_grounded",
    "is_scope_widening_request",
    "match_discovery_dimension",
    "load_entity_catalogue",
    "merge_memory_entities",
    "message_mentions_metric",
    "select_delivery_performance_metric",
    "select_metric",
    "select_metric_by_id",
    "resolve_entities",
]
