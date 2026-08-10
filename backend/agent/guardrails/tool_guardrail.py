"""Tool guardrail: validates and blocks disallowed tool calls before execution.

This is the single place a model-proposed plan is checked against reality
before anything touches the database (guide Section 17.2: "validate tool
arguments; block disallowed tool calls; enforce data scopes; block unsafe
query parameters; check permissions before execution"). It calls
``controls.permission_control`` for the static allowlist and
``controls.execution_control`` for the approval/bounds checks, then applies
the per-query completeness rules that only make sense at the tool-call level
(e.g. ``dora_metrics_by_squad`` requires a ``dcpsquad`` value; large queries
require a narrowing filter).

Nothing here trusts the model's own confidence claim or filter shape --
every field is re-validated even though the planner already tried to
produce a valid plan.
"""

from __future__ import annotations

from ...database.doradb_catalog import (
    DISCOVERY_DIMENSIONS,
    LARGE_QUERY_IDS,
    LARGE_QUERY_REQUIRED_FILTERS,
)
from ..controls.execution_control import bounded_tool_calls, confidence_is_sufficient
from ..controls.permission_control import (
    filter_is_permitted,
    permitted_result_limit,
    query_id_is_permitted,
)
from ..state import AgentPlan, QueryAction


class ToolGuardrailViolation(ValueError):
    """A proposed model action exceeded an explicit tool guardrail."""


def _passes_completeness_rules(query_id: str, filters: dict[str, object]) -> bool:
    """Per-query rules a call must satisfy beyond simple filter allowlisting."""

    if query_id == "list_dimension_values" and filters.get("dimension") not in DISCOVERY_DIMENSIONS:
        return False
    if query_id == "dora_metrics_by_squad" and "dcpsquad" not in filters:
        return False
    if query_id in LARGE_QUERY_IDS and not (set(filters) & LARGE_QUERY_REQUIRED_FILTERS):
        return False
    return True


def enforce_plan(plan: AgentPlan) -> AgentPlan:
    """Allowlist tools, bounds, filters, confidence, and action count.

    This is the tool guardrail's single entry point: the planner's output is
    never trusted directly. A plan that is not in "data" mode has no tool
    calls to guard and passes through with an empty action list.
    """

    if plan["mode"] != "data":
        return {**plan, "actions": []}
    if not confidence_is_sufficient(plan["confidence"]):
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
    for action in bounded_tool_calls(plan["actions"]):
        query_id = action["query_id"]
        if not query_id_is_permitted(query_id):
            continue
        filters = {
            key: value
            for key, value in action.get("filters", {}).items()
            if filter_is_permitted(query_id, key) and value not in (None, "")
        }
        if not _passes_completeness_rules(query_id, filters):
            continue
        maximum = permitted_result_limit(query_id)
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


__all__ = ["ToolGuardrailViolation", "enforce_plan"]
