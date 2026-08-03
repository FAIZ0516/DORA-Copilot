"""Gemini planner constrained by deterministic steering and controls."""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from ..config import settings
from ..doradb_catalog import (
    LARGE_QUERY_IDS,
    LARGE_QUERY_REQUIRED_FILTERS,
    QUERY_CATALOGUE,
    planner_context,
)
from ..llm import GenerativeAIClient
from ..skills.filter_extraction import extract_filters
from ..skills.intent_matching import classify_intent
from ..skills.metric_selection import select_metric
from .control import enforce_plan
from .state import AgentPlan, QueryAction


def _parse_json(raw: str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None


def _requires_dataset_action(message: str) -> bool:
    """Detect requests that must execute now instead of returning a tool promise."""

    intent = classify_intent(message)
    if intent["visualization_requested"]:
        return True
    has_data_action = bool(
        re.search(
            r"\b(show|list|compare|analy[sz]e|calculate|compute|retrieve|query|"
            r"summarize|summarise|break\s*down|rank|trend|count|available|"
            r"how many|do you have|give me|recommend|suggest|improv(?:e|ement)|"
            r"action plan|next steps?)\b",
            message,
            re.I,
        )
    )
    has_dataset_signal = bool(
        re.search(
            r"\b(dora|doradb|metric|release|deploy|failure|lead time|cycle time|"
            r"jira|ticket|issue|feature|user stor(?:y|ies)|year|squad|team|"
            r"titan|jaeger|dataset|data)\b",
            message,
            re.I,
        )
    )
    return has_dataset_signal and has_data_action


def deterministic_plan(message: str, memory: dict[str, Any]) -> AgentPlan:
    intent = classify_intent(message)
    explicit_filters = extract_filters(
        message,
        project_key=settings.doradb_project_key,
    )
    previous = memory.get("last_context", {})
    has_previous_topic = bool(previous.get("metric") or previous.get("query_ids"))
    filters = {
        **(previous.get("filters", {}) if has_previous_topic else {}),
        **explicit_filters,
    }

    # Keep conversational dimensions until the user explicitly widens scope.
    # This makes "what do you understand from release frequency?" continue to
    # mean the active Jaeger squad instead of silently switching to all squads.
    if re.search(r"\b(overall|all squads?|every squad|across squads?)\b", message, re.I):
        filters.pop("dcpsquad", None)
    if re.search(r"\b(all years?|every year|across years?)\b", message, re.I):
        filters.pop("release_year", None)
        filters.pop("release_date", None)

    follow_up = has_previous_topic and bool(
        re.search(
            r"\b(that|same|previous|above|it|this|those|them|"
            r"for\s+20\d{2}|chart|graph|plot|diagram|explain|break\s*down)\b",
            message,
            re.I,
        )
    )
    if follow_up:
        if intent["name"] == "general_conversation":
            intent = {
                "name": (
                    "visualization"
                    if intent["visualization_requested"]
                    else "metric_lookup"
                ),
                "confidence": 0.94,
                "visualization_requested": intent["visualization_requested"],
            }

    if intent["name"] == "out_of_scope":
        return {
            "mode": "out_of_scope",
            "intent": "unsafe_request",
            "confidence": 1.0,
            "actions": [],
            "reason": "Database writes and arbitrary SQL are prohibited.",
            "clarification": "",
        }
    if intent["name"] in {"help", "greeting"}:
        return {
            "mode": "conversation",
            "intent": intent["name"],
            "confidence": intent["confidence"],
            "actions": [],
            "reason": "A safe conversational response does not require a data query.",
            "clarification": "",
        }
    if intent["name"] == "general_conversation":
        return {
            "mode": "out_of_scope",
            "intent": "out_of_context",
            "confidence": 1.0,
            "actions": [],
            "reason": "The question is unrelated to the connected DoraDB scope.",
            "clarification": "",
        }

    non_project_filters = set(filters) - {"project_key"}
    if (
        intent["name"] == "recommendation"
        and re.search(r"\b(squad|team)\b", message, re.I)
        and "dcpsquad" not in filters
    ):
        return {
            "mode": "clarification",
            "intent": "clarify_recommendation_scope",
            "confidence": 0.96,
            "actions": [],
            "reason": "The recommendation request needs a squad dimension.",
            "clarification": "Which squad should I evaluate for improvement?",
        }
    if (
        intent["name"] == "metric_lookup"
        and not non_project_filters
        and not _requires_dataset_action(message)
    ):
        metric = select_metric(message)
        return {
            "mode": "clarification",
            "intent": "clarify_metric_scope",
            "confidence": 0.92,
            "actions": [],
            "reason": "The metric topic is clear but the requested analysis is not.",
            "clarification": (
                f"What would you like to explore about {metric['label'].lower()}—"
                "its definition, a specific year or squad, a trend comparison, "
                "or a visualization?"
            ),
        }

    query_id = "dora_metrics_by_year"
    if "release_date" in filters:
        query_id = "dora_metrics_release_detail"
    elif "dcpsquad" in filters and intent["name"] not in {"issue_listing", "ratio"}:
        query_id = "dora_metrics_by_squad"
    elif intent["name"] == "ratio":
        query_id = "story_to_feature_ratio"
    elif intent["name"] == "issue_listing":
        query_id = (
            "feature_vs_release_frequency"
            if re.search(r"\b(affect|frequency|outcome)\b", message, re.I)
            else "feature_vs_user_story"
        )
    elif intent["name"] in {"explanation", "release_drilldown"}:
        query_id = "dora_metrics_release_detail"

    if query_id in LARGE_QUERY_IDS and not (set(filters) & LARGE_QUERY_REQUIRED_FILTERS):
        return {
            "mode": "clarification",
            "intent": intent["name"],
            "confidence": intent["confidence"],
            "actions": [],
            "reason": "A high-volume query requires a narrowing filter.",
            "clarification": "Which release year, release name, issue type, or Jira key should I use?",
        }
    actions: list[QueryAction] = [
        {
            "query_id": query_id,
            "filters": filters,
            "limit": int(QUERY_CATALOGUE[query_id]["default_limit"]),
            "reason": "Deterministic steering route.",
        }
    ]
    if query_id == "dora_metrics_release_detail" and not (
        {"release_year", "release_date", "fixversion", "release_name"} & set(filters)
    ):
        return {
            "mode": "clarification",
            "intent": intent["name"],
            "confidence": intent["confidence"],
            "actions": [],
            "reason": "An explanation needs a reporting period.",
            "clarification": "Which release year should I investigate?",
        }
    return {
        "mode": "data",
        "intent": intent["name"],
        "confidence": intent["confidence"],
        "actions": actions,
        "reason": "Mapped to an approved DoraDB query.",
        "clarification": "",
    }


def create_plan(
    message: str,
    *,
    memory: dict[str, Any],
    browser_history: list[dict[str, str]],
    llm: GenerativeAIClient,
) -> tuple[AgentPlan, str]:
    """Let the configured LLM interpret the request, then validate its actions.

    The deterministic plan is deliberately a fallback, not the primary router.
    It still blocks unsafe/out-of-domain requests before a cloud call and keeps
    the application useful when the provider is unavailable.
    """

    fallback = deterministic_plan(message, memory)
    if fallback["mode"] == "conversation":
        return enforce_plan(fallback), "conversation"
    if fallback["intent"] in {"out_of_context", "unsafe_request"}:
        return enforce_plan(fallback), "scope-guard"
    if not llm.enabled:
        return enforce_plan(fallback), "deterministic"

    history_text = "\n".join(
        f"{item.get('role', 'user').upper()}: {item.get('content', '')[:800]}"
        for item in browser_history[-8:]
    )
    memory_context = json.dumps(memory.get("last_context", {}), default=str)
    system = f"""You are the reasoning and tool-planning agent for a governed
DoraDB assistant. Understand the user's actual objective from their wording,
recent conversation, and structured memory. Decide what evidence is needed now.
Return JSON only with:
{{"mode":"data|conversation|clarification|out_of_scope","intent":"...",
"confidence":0.0,"reason":"...","clarification":"","actions":[
{{"query_id":"approved ID","filters":{{}},"limit":50,"reason":"..."}}]}}

{planner_context()}
The control layer will reject tools, filters, and limits outside this catalogue.
Never emit SQL.

Planning principles:
- For broad analytical questions such as delivery risk, overall performance,
  surprising patterns, recommendations, or "what do you understand", execute
  an overview query instead of demanding a year. Prefer
  dora_metrics_by_year when no narrower dimension was supplied.
- Ask a clarification only when a required dimension is genuinely unknowable,
  such as "the squad" when no squad exists in the current request or memory, or
  an issue-level query whose required narrowing filter is missing.
- Do not ask whether the user wants a definition, chart, year, or comparison
  when a useful evidence-grounded overview can answer the request.
- Use one primary action and add a second approved action only when it provides
  materially different evidence needed for the user's objective.
- A named squad must use dora_metrics_by_squad with dcpsquad. A squad never
  replaces project_key.
- Use structured memory to resolve follow-ups such as "for 2022", "explain
  that", "compare it", or "make a chart for it".
- Use mode=conversation only when no database evidence is required. Never
  promise that a query will happen later.
- Chart requests are safe data requests.
- Use mode=out_of_scope only for writes, secrets, or harmful requests."""
    raw = llm.complete(
        system,
        (
            f"Current date: {date.today().isoformat()}\n"
            f"Memory context: {memory_context}\n"
            f"Conversation: {history_text or '(none)'}\n"
            f"Request: {message}"
        ),
        json_mode=True,
        temperature=settings.llm_planner_temperature,
    )
    parsed = _parse_json(raw) if raw else None
    if not parsed:
        return enforce_plan(fallback), "deterministic-fallback"

    try:
        mode = str(parsed.get("mode", "data"))
        if mode not in {"data", "conversation", "clarification", "out_of_scope"}:
            raise ValueError("invalid mode")
        actions: list[QueryAction] = []
        base_filters = (
            dict(fallback["actions"][0]["filters"])
            if fallback["mode"] == "data" and fallback["actions"]
            else extract_filters(
                message,
                project_key=settings.doradb_project_key,
            )
        )
        for item in parsed.get("actions", []):
            if not isinstance(item, dict):
                continue
            model_filters = item.get("filters") if isinstance(item.get("filters"), dict) else {}
            safe_model_filters = {
                key: value
                for key, value in model_filters.items()
                if key != "project_key"
            }
            actions.append(
                {
                    "query_id": str(item.get("query_id", "")),
                    "filters": {
                        **safe_model_filters,
                        **base_filters,
                        "project_key": settings.doradb_project_key.upper(),
                    },
                    "limit": int(item.get("limit") or 50),
                    "reason": str(item.get("reason") or "Generative plan"),
                }
            )
        plan: AgentPlan = {
            "mode": mode,  # type: ignore[typeddict-item]
            "intent": str(parsed.get("intent") or fallback["intent"])[:100],
            "confidence": max(0.0, min(1.0, float(parsed.get("confidence", 0.75)))),
            "actions": actions,
            "reason": str(parsed.get("reason") or fallback["reason"])[:300],
            "clarification": str(parsed.get("clarification") or "")[:300],
        }

        # The public scope guard, not the model, owns out-of-scope decisions.
        if plan["mode"] == "out_of_scope" and fallback["mode"] != "out_of_scope":
            plan = {
                **plan,
                "mode": "conversation",
                "actions": [],
                "reason": "The request is safe but does not need DoraDB evidence.",
            }

        # An explicit request for data must execute now. If the model omitted a
        # usable action, the conservative allowlisted fallback supplies it.
        if (
            _requires_dataset_action(message)
            and (plan["mode"] != "data" or not plan["actions"])
            and fallback["mode"] == "data"
        ):
            plan = fallback

        planner_source = getattr(
            llm,
            "source",
            settings.llm_source,
        )
        if (
            fallback["mode"] == "data"
            and fallback["actions"]
            and "dcpsquad" in fallback["actions"][0]["filters"]
            and (
                plan["mode"] != "data"
                or not any(
                    action["query_id"] == "dora_metrics_by_squad"
                    for action in plan["actions"]
                )
            )
        ):
            # A named squad is an explicit user constraint. The model may add
            # supporting actions, but it cannot silently widen to all squads.
            plan = fallback
            planner_source = "deterministic-context-repair"

        controlled = enforce_plan(plan)
        if (
            controlled["mode"] == "clarification"
            and plan["mode"] == "data"
            and fallback["mode"] == "data"
        ):
            # Invalid model tools never execute. Prefer a known-safe fallback
            # rather than presenting a generic control-layer clarification.
            controlled = enforce_plan(fallback)
            return controlled, "deterministic-safety-fallback"
        return controlled, planner_source
    except (TypeError, ValueError):
        return enforce_plan(fallback), "deterministic-fallback"
