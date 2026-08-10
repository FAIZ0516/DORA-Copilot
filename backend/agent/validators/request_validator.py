"""Request validation: is this a structurally well-formed request.

Guide Section 43 "Request validation": required parameters present,
supported query type. This runs *before* guardrails decide whether a
request is *permitted* (``guardrails/tool_guardrail.py``); it only checks
whether it is well-formed enough to reason about at all -- catching a
malformed model-generated action (missing/wrong-typed field) with a clear
message instead of a raw ``KeyError``/``TypeError`` surfacing later.

This intentionally does not duplicate the read-only-safety parameter
normalization in ``database/doradb.py`` (year ranges, date formats, squad/
Jira-key patterns) -- that logic stays adjacent to query execution because
it is a security boundary, not a general-purpose validator.
"""

from __future__ import annotations

from typing import Any


def validate_query_action_shape(action: dict[str, Any]) -> list[str]:
    """Structural checks only: required keys and basic types."""

    errors: list[str] = []
    if not isinstance(action.get("query_id"), str) or not action.get("query_id"):
        errors.append("query_id must be a non-empty string.")
    if not isinstance(action.get("filters"), dict):
        errors.append("filters must be an object.")
    limit = action.get("limit")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        errors.append("limit must be a positive integer.")
    return errors


def validate_plan_shape(actions: list[dict[str, Any]]) -> list[str]:
    """Structural checks for every action in a proposed plan."""

    errors: list[str] = []
    for index, action in enumerate(actions):
        errors.extend(
            f"action[{index}]: {message}" for message in validate_query_action_shape(action)
        )
    return errors


__all__ = ["validate_plan_shape", "validate_query_action_shape"]
