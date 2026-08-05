"""Conversation-scoped reuse policy for validated query results."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from ..config import settings
from ..doradb_catalog import QUERY_CATALOGUE


FOLLOW_UP_ON_EXISTING_RESULT = "FOLLOW_UP_ON_EXISTING_RESULT"
REFRESH_PATTERN = re.compile(r"\b(current|latest|refresh|refreshed|rerun|re-run|updated)\b", re.I)
FOLLOW_UP_PATTERN = re.compile(
    r"\b(how many did you find|how many|which one|compare them|why\??|"
    r"explain|these|those|that squad|show (?:it|that|them).*(?:table|chart)|"
    r"format|visuali[sz]e)\b",
    re.I,
)
SENSITIVE_FIELDS = {
    "summary",
    "reporter",
    "assignee",
    "root_cause",
    "how_to_fix",
    "labels",
}


@dataclass(frozen=True)
class CacheDecision:
    action: Literal["none", "reuse", "refresh"]
    entry: dict[str, Any] | None = None
    reason: str = ""


def _normal_scope(scope: dict[str, Any]) -> str:
    return json.dumps(scope or {}, sort_keys=True, default=str)


def _is_fresh(entry: dict[str, Any]) -> bool:
    try:
        generated = datetime.fromisoformat(str(entry["generated_at"]))
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - generated).total_seconds()
        return 0 <= age <= settings.query_result_cache_ttl_seconds
    except (KeyError, TypeError, ValueError):
        return False


def choose_cache_action(
    message: str,
    *,
    memory: dict[str, Any],
    project_scope: dict[str, Any],
) -> CacheDecision:
    entries = memory.get("query_cache", [])
    if not isinstance(entries, list) or not entries:
        return CacheDecision("none", reason="no_cache")
    entry = entries[-1]
    if not isinstance(entry, dict) or not entry.get("complete"):
        return CacheDecision("none", reason="incomplete")
    if int(entry.get("row_count", 0)) <= 0:
        return CacheDecision("none", reason="zero_rows")
    if _normal_scope(entry.get("project_scope", {})) != _normal_scope(project_scope):
        return CacheDecision("none", reason="scope_changed")
    if not _is_fresh(entry):
        return CacheDecision("none", reason="stale")

    lowered = message.lower()
    cached_filters = {
        key: value
        for result in entry.get("results", [])
        if isinstance(result, dict)
        for key, value in result.get("filters", {}).items()
    }
    if "bug" in lowered and str(cached_filters.get("issuetype", "")).lower() != "bug":
        return CacheDecision("none", reason="filter_changed")
    if REFRESH_PATTERN.search(message):
        return CacheDecision("refresh", entry=entry, reason="explicit_refresh")
    if not FOLLOW_UP_PATTERN.search(message):
        return CacheDecision("none", reason="standalone_request")

    query_ids = set(entry.get("query_ids", []))
    if "squad" in lowered and not any("squad" in query_id for query_id in query_ids):
        return CacheDecision("none", reason="required_fields_missing")
    return CacheDecision("reuse", entry=entry, reason="eligible_follow_up")


def actions_from_cache(entry: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for result in entry.get("results", []):
        query_id = str(result.get("query_id", ""))
        if query_id not in QUERY_CATALOGUE:
            continue
        actions.append(
            {
                "query_id": query_id,
                "filters": dict(result.get("filters", {})),
                "limit": int(
                    result.get("limit_applied")
                    or QUERY_CATALOGUE[query_id]["default_limit"]
                ),
                "reason": "Explicitly refresh the previous approved query.",
            }
        )
    return actions[: settings.agent_max_tool_calls]


def results_from_cache(entry: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in entry.get("results", []) if isinstance(item, dict)]


def _safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _safe_value(item)
            for key, item in value.items()
            if key not in SENSITIVE_FIELDS
        }
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    if isinstance(value, str):
        return value[:500]
    return value


def build_cache_entry(
    *,
    intent: str,
    results: list[dict[str, Any]],
    project_scope: dict[str, Any],
) -> dict[str, Any] | None:
    if not results or any(int(result.get("row_count", 0)) <= 0 for result in results):
        return None
    safe_results: list[dict[str, Any]] = []
    for result in results:
        rows = [
            _safe_value(row)
            for row in result.get("rows", [])[: settings.query_result_cache_max_rows]
        ]
        safe_results.append(
            {
                "query_id": result.get("query_id"),
                "filters": _safe_value(result.get("filters", {})),
                "rows": rows,
                "row_count": result.get("row_count", len(rows)),
                "limit_applied": result.get("limit_applied"),
                "warnings": list(result.get("warnings", [])),
            }
        )
    serialized = json.dumps(safe_results, default=str)
    if len(serialized) > settings.query_result_cache_max_chars:
        return None
    return {
        "cache_key": json.dumps(
            {
                "query_ids": [item["query_id"] for item in safe_results],
                "filters": [item["filters"] for item in safe_results],
                "project_scope": project_scope,
            },
            sort_keys=True,
            default=str,
        ),
        "intent": intent,
        "query_ids": [item["query_id"] for item in safe_results],
        "project_scope": project_scope,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "row_count": sum(int(item["row_count"]) for item in safe_results),
        "results": safe_results,
        "data_source": "doradb",
        "complete": True,
    }


__all__ = [
    "FOLLOW_UP_ON_EXISTING_RESULT",
    "actions_from_cache",
    "build_cache_entry",
    "choose_cache_action",
    "results_from_cache",
]
