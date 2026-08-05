"""Ground natural-language entities against live governed DoraDB dimensions.

The model may reason about a user's wording, but it must not invent values for
database filters.  This module keeps a small TTL cache of distinct, read-only
dimension values and resolves exact natural-language mentions before planning.
"""

from __future__ import annotations

import re
import time
from threading import RLock
from typing import Any

from sqlalchemy.orm import Session

from ..config import settings
from ..doradb_catalog import DISCOVERY_DIMENSIONS, METRIC_DEFINITIONS
from .query_execution import execute_approved_query


EntityCatalogue = dict[str, list[str]]

DIMENSION_FILTERS: dict[str, str] = {
    "project": "project_key",
    "squad": "dcpsquad",
    "release_year": "release_year",
    "release": "fixversion",
    "issue_type": "issuetype",
    "status": "status",
}
FILTER_DIMENSIONS = {value: key for key, value in DIMENSION_FILTERS.items()}
FILTER_DIMENSIONS["release_name"] = "release"

_CACHE: dict[str, tuple[float, EntityCatalogue]] = {}
_CACHE_LOCK = RLock()
_CACHE_TTL_SECONDS = 300.0


def _tokens(value: str) -> tuple[str, ...]:
    """Normalize punctuation/casing while preserving ordered entity tokens."""

    return tuple(re.findall(r"[a-z0-9]+", value.casefold()))


def _contains_tokens(message_tokens: tuple[str, ...], value_tokens: tuple[str, ...]) -> bool:
    if not value_tokens or len(value_tokens) > len(message_tokens):
        return False
    width = len(value_tokens)
    return any(
        message_tokens[index : index + width] == value_tokens
        for index in range(len(message_tokens) - width + 1)
    )


def clear_entity_catalogue_cache() -> None:
    """Clear process-local catalogue state (primarily for tests/admin refresh)."""

    with _CACHE_LOCK:
        _CACHE.clear()


def load_entity_catalogue(
    session: Session | None,
    *,
    project_key: str | None = None,
    force_refresh: bool = False,
) -> EntityCatalogue:
    """Load every governed dimension using approved parameterized queries.

    A cache avoids issuing seven discovery queries for every chat request.
    Empty dimensions remain present so callers can distinguish an unavailable
    catalogue from a dimension with no current values.
    """

    project = (project_key or settings.doradb_project_key).upper()
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(project)
        if cached and not force_refresh and now - cached[0] < _CACHE_TTL_SECONDS:
            return {key: list(values) for key, values in cached[1].items()}

    catalogue: EntityCatalogue = {
        dimension: [] for dimension in DISCOVERY_DIMENSIONS
    }
    # Metrics are application-governed and do not require a database round trip.
    catalogue["metric"] = list(METRIC_DEFINITIONS)
    if session is None:
        return catalogue

    for dimension in DISCOVERY_DIMENSIONS:
        if dimension == "metric":
            continue
        result = execute_approved_query(
            session,
            query_id="list_dimension_values",
            filters={"dimension": dimension, "project_key": project},
            limit=settings.result_limit,
        )
        values = {
            str(row.get("value", "")).strip()
            for row in result.get("rows", [])
            if str(row.get("value", "")).strip()
        }
        catalogue[dimension] = sorted(values, key=str.casefold)

    with _CACHE_LOCK:
        _CACHE[project] = (now, catalogue)
    return {key: list(values) for key, values in catalogue.items()}


def merge_memory_entities(
    catalogue: EntityCatalogue,
    memory: dict[str, Any],
) -> EntityCatalogue:
    """Merge previously discovered values without retaining raw result rows."""

    merged = {key: list(values) for key, values in catalogue.items()}
    discovered = memory.get("last_context", {}).get("discovered_values", {})
    if not isinstance(discovered, dict):
        return merged
    for dimension, values in discovered.items():
        if dimension not in DISCOVERY_DIMENSIONS or not isinstance(values, list):
            continue
        current = {value.casefold(): value for value in merged.get(dimension, [])}
        for raw_value in values:
            value = str(raw_value).strip()
            if value:
                current.setdefault(value.casefold(), value)
        merged[dimension] = sorted(current.values(), key=str.casefold)
    return merged


def resolve_entities(message: str, catalogue: EntityCatalogue) -> dict[str, Any]:
    """Resolve all exact catalogue values mentioned in a user message.

    Multiple values in one dimension are retained for comparisons.  A filter
    is emitted only for unambiguous single values; the planner can create two
    governed actions when, for example, two squads are compared.
    """

    message_tokens = _tokens(message)
    matches: dict[str, list[str]] = {}
    for dimension, values in catalogue.items():
        found: list[tuple[int, str]] = []
        for value in values:
            value_tokens = _tokens(value)
            # One-character values are too ambiguous in natural language.
            if not value_tokens or (len(value_tokens) == 1 and len(value_tokens[0]) < 2):
                continue
            if _contains_tokens(message_tokens, value_tokens):
                found.append((len(value_tokens), value))
        if found:
            # Prefer longer values while retaining genuinely separate mentions.
            found.sort(key=lambda item: (-item[0], item[1].casefold()))
            selected: list[str] = []
            selected_tokens: list[tuple[str, ...]] = []
            for _, value in found:
                value_tokens = _tokens(value)
                if any(
                    len(value_tokens) < len(existing)
                    and _contains_tokens(existing, value_tokens)
                    for existing in selected_tokens
                ):
                    continue
                selected.append(value)
                selected_tokens.append(value_tokens)
            matches[dimension] = selected

    filters: dict[str, Any] = {}
    for dimension, values in matches.items():
        filter_name = DIMENSION_FILTERS.get(dimension)
        if not filter_name or len(values) != 1:
            continue
        filters[filter_name] = (
            [int(values[0])] if dimension == "release_year" else values[0]
        )

    return {
        "matches": matches,
        "filters": filters,
        "has_matches": bool(matches),
    }


def filter_value_is_grounded(
    filter_name: str,
    raw_value: Any,
    catalogue: EntityCatalogue,
) -> bool:
    """Return whether a model-proposed entity filter exists in the catalogue."""

    dimension = FILTER_DIMENSIONS.get(filter_name)
    if not dimension or not catalogue.get(dimension):
        return True
    # Release discovery is intentionally capped by the global row limit. An
    # exact parameterized release filter outside that cached page remains safe
    # and will simply return no rows if it does not exist.
    if dimension == "release" and len(catalogue[dimension]) >= settings.result_limit:
        return True
    raw_values = raw_value if isinstance(raw_value, list) else [raw_value]
    known = {_tokens(str(value)) for value in catalogue[dimension]}
    return all(_tokens(str(value)) in known for value in raw_values)


def compact_catalogue(catalogue: EntityCatalogue, *, limit: int = 100) -> dict[str, Any]:
    """Create bounded model context without exposing database records."""

    return {
        dimension: {
            "values": values[:limit],
            "total": len(values),
            "truncated": len(values) > limit,
        }
        for dimension, values in catalogue.items()
    }


__all__ = [
    "DIMENSION_FILTERS",
    "EntityCatalogue",
    "clear_entity_catalogue_cache",
    "compact_catalogue",
    "filter_value_is_grounded",
    "load_entity_catalogue",
    "merge_memory_entities",
    "resolve_entities",
]
