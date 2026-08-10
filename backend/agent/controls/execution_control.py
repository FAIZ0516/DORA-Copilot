"""Execution control: operational limits, independent of tool identity.

This module answers "how much/how long is the agent allowed to work" --
timeouts, retry/tool-call counts, the confidence-threshold approval gate,
and the publicly exposed policy summary. It does not decide *which* tools
or filters are allowed; that is ``permission_control.py`` +
``backend/agent/guardrails/tool_guardrail.py``.
"""

from __future__ import annotations

import time
from typing import Any

from ...config import settings


def confidence_is_sufficient(confidence: float) -> bool:
    """Approval gate: a plan below the configured confidence must clarify."""

    return confidence >= settings.agent_confidence_threshold


def bounded_tool_calls(actions: list[Any]) -> list[Any]:
    """Enforce the maximum number of tool calls per turn."""

    return actions[: settings.agent_max_tool_calls]


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


__all__ = [
    "bounded_tool_calls",
    "confidence_is_sufficient",
    "ensure_within_deadline",
    "public_policy",
]
