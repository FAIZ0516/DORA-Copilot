"""Deterministic workflow limits with authority over model-generated plans."""

from __future__ import annotations

import time
from typing import Any

from ..config import settings
from ..doradb_catalog import (
    APPROVED_QUERY_IDS,
    LARGE_QUERY_IDS,
    LARGE_QUERY_REQUIRED_FILTERS,
    QUERY_CATALOGUE,
)
from .state import AgentPlan, QueryAction


class ControlViolation(ValueError):
    """A proposed model action exceeded an explicit control policy."""


def enforce_plan(plan: AgentPlan) -> AgentPlan:
    """Allowlist tools, bounds, filters, confidence, and action count."""

    if plan["mode"] != "data":
        return {**plan, "actions": []}
    if plan["confidence"] < settings.agent_confidence_threshold:
        return {
            **plan,
            "mode": "clarification",
            "actions": [],
            "clarification": (
                plan.get("clarification")
                or "Which release year, metric, or release should I analyze?"
            ),
        }
    actions: list[QueryAction] = []
    for action in plan["actions"][: settings.agent_max_tool_calls]:
        query_id = action["query_id"]
        if query_id not in APPROVED_QUERY_IDS:
            continue
        filters = {
            key: value
            for key, value in action.get("filters", {}).items()
            if key in QUERY_CATALOGUE[query_id]["allowed_filters"] and value not in (None, "")
        }
        if query_id == "dora_metrics_by_squad" and "dcpsquad" not in filters:
            continue
        if query_id in LARGE_QUERY_IDS and not (
            set(filters) & LARGE_QUERY_REQUIRED_FILTERS
        ):
            continue
        maximum = 200 if query_id in LARGE_QUERY_IDS else settings.result_limit
        actions.append(
            {
                "query_id": query_id,
                "filters": filters,
                "limit": min(maximum, max(1, int(action.get("limit") or 50))),
                "reason": str(action.get("reason") or "Approved analysis")[:240],
            }
        )
    if not actions:
        return {
            **plan,
            "mode": "clarification",
            "actions": [],
            "clarification": (
                plan.get("clarification")
                or "Please provide a release year, release name, issue type, or Jira key."
            ),
        }
    return {**plan, "actions": actions}


def ensure_within_deadline(started_at: float) -> None:
    if time.monotonic() - started_at > settings.agent_workflow_timeout_seconds:
        raise TimeoutError("Agent workflow exceeded its configured time limit")


def public_policy() -> dict[str, Any]:
    return {
        "max_tool_calls": settings.agent_max_tool_calls,
        "max_retries": settings.agent_max_retries,
        "confidence_threshold": settings.agent_confidence_threshold,
        "result_limit": settings.result_limit,
        "read_only": True,
        "arbitrary_sql": False,
    }
