"""Persistent conversation summary and cache-state construction."""

from __future__ import annotations

import json
from typing import Any

from .agent_system.result_cache import build_cache_entry
from .config import settings
from .db import ConversationMessage


def recent_history(messages: list[ConversationMessage]) -> list[dict[str, str]]:
    eligible = [item for item in messages if item.role in {"user", "assistant"}]
    return [
        {"role": item.role, "content": item.content[:3000]}
        for item in eligible[-settings.conversation_recent_message_limit :]
    ]


def persistent_context(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "conversation_summary": str(state.get("summary", ""))[
            : settings.conversation_summary_max_chars
        ],
        "last_context": dict(state.get("last_context", {})),
        "query_cache": list(state.get("query_cache", []))[
            -settings.query_result_cache_max_entries :
        ],
        "workspace": state.get("workspace", "technical"),
        "project_scope": dict(state.get("project_scope", {})),
    }


def _build_summary(
    *,
    workspace: str,
    project_scope: dict[str, Any],
    question: str,
    answer: str,
    context: dict[str, Any],
    previous_summary: str,
) -> str:
    filters = context.get("filters", {})
    parts = [
        f"Workspace: {workspace}.",
        f"Project scope: {json.dumps(project_scope, sort_keys=True, default=str)}.",
        f"Current objective: {question[:500]}.",
    ]
    if filters:
        parts.append(f"Established filters: {json.dumps(filters, sort_keys=True, default=str)}.")
    if context.get("query_ids"):
        parts.append(f"Previous approved queries: {', '.join(context['query_ids'])}.")
    parts.append(f"Latest finding: {answer[:800]}.")
    if context.get("warnings"):
        parts.append("Important limitations: " + " ".join(context["warnings"])[:700])
    if context.get("intent") == "CLARIFICATION_REQUIRED":
        parts.append(f"Unresolved clarification: {question[:400]}.")
    if previous_summary:
        parts.insert(0, f"Earlier context: {previous_summary[:900]}")
    return " ".join(parts)[: settings.conversation_summary_max_chars]


def update_persistent_state(
    current: dict[str, Any],
    *,
    workspace: str,
    project_scope: dict[str, Any],
    question: str,
    answer: str,
    agent_persistence: dict[str, Any],
) -> dict[str, Any]:
    next_state = dict(current or {})
    next_state["workspace"] = workspace
    next_state["project_scope"] = project_scope
    next_state["turn_count"] = int(next_state.get("turn_count", 0)) + 2
    next_state["last_context"] = dict(agent_persistence.get("last_context", {}))

    cache = list(next_state.get("query_cache", []))
    if not agent_persistence.get("query_result_reused"):
        entry = build_cache_entry(
            intent=str(agent_persistence.get("intent", "")),
            results=list(agent_persistence.get("results", [])),
            project_scope=project_scope,
        )
        if entry:
            cache = [item for item in cache if item.get("cache_key") != entry["cache_key"]]
            cache.append(entry)
    next_state["query_cache"] = cache[-settings.query_result_cache_max_entries :]

    if next_state["turn_count"] >= settings.conversation_summary_trigger_messages:
        next_state["summary"] = _build_summary(
            workspace=workspace,
            project_scope=project_scope,
            question=question,
            answer=answer,
            context=next_state["last_context"],
            previous_summary=str(next_state.get("summary", "")),
        )
    else:
        next_state.setdefault("summary", "")
    return next_state


__all__ = ["persistent_context", "recent_history", "update_persistent_state"]
