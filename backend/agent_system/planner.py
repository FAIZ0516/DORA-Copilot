"""DeepSeek planner constrained by deterministic steering and controls."""

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
from ..skills.entity_grounding import (
    compact_catalogue,
    filter_value_is_grounded,
    resolve_entities,
)
from ..skills.intent_matching import classify_intent
from ..skills.metric_selection import select_metric
from ..skills.dimension_discovery import (
    is_scope_widening_request,
    match_discovery_dimension,
)
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

    if match_discovery_dimension(message):
        return True
    intent = classify_intent(message)
    if intent["visualization_requested"]:
        return True
    has_data_action = bool(
        re.search(
            r"\b(show|list|compare|analy[sz]e|calculate|compute|retrieve|query|"
            r"summarize|summarise|explain|understand|investigate|evaluate|"
            r"break\s*down|rank|trend|count|available|"
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
            r"performance|delivery risk|engineering|titan|jaeger|dataset|data)\b",
            message,
            re.I,
        )
    )
    return has_dataset_signal and has_data_action


def _references_previous_answer(message: str, memory: dict[str, Any]) -> bool:
    """Detect semantic follow-ups without requiring a fixed phrase template."""

    turns = memory.get("turns", [])
    if not turns:
        return False
    lowered = message.casefold()
    if re.search(
        r"\b(that|same|previous|above|it|this|those|them|continue|"
        r"tell me more|elaborate|clarify|what do(?:es)? that mean|"
        r"explain|break\s*down|why is that)\b",
        lowered,
    ):
        return True

    # Resolve short definition questions against words actually used in the
    # preceding answer. This handles "what is caveats?" without treating an
    # unrelated "what is the weather?" as a dataset follow-up.
    last_answer = str(turns[-1].get("assistant", "")).casefold()
    if len(message.split()) <= 12 and re.search(
        r"\b(what (?:is|are|does)|meaning of|define|what do you mean by)\b",
        lowered,
    ):
        ignored = {
            "a", "an", "are", "by", "do", "does", "is", "it", "mean",
            "meaning", "of", "the", "this", "what", "you",
        }
        terms = {
            token
            for token in re.findall(r"[a-z0-9_-]+", lowered)
            if token not in ignored and len(token) > 2
        }
        return any(term in last_answer for term in terms)
    return False


def deterministic_plan(
    message: str,
    memory: dict[str, Any],
    *,
    entity_catalogue: dict[str, list[str]] | None = None,
    grounding: dict[str, Any] | None = None,
) -> AgentPlan:
    intent = classify_intent(message)
    grounding = grounding or resolve_entities(message, entity_catalogue or {})
    discovery_dimension = match_discovery_dimension(message)
    explicit_filters = extract_filters(
        message,
        project_key=settings.doradb_project_key,
    )
    explicit_filters.update(grounding.get("filters", {}))
    rejected_explicit = [
        key
        for key, value in explicit_filters.items()
        if key != "project_key"
        and not filter_value_is_grounded(key, value, entity_catalogue or {})
    ]
    if rejected_explicit:
        return {
            "mode": "clarification",
            "intent": "unknown_entity",
            "confidence": 1.0,
            "actions": [],
            "reason": "A named filter was not present in the live entity catalogue.",
            "clarification": (
                "I couldn't match that name to a current DoraDB project, squad, "
                "release, year, issue type, or status. Could you check the name "
                "or ask me to list the available values?"
            ),
        }
    if discovery_dimension:
        discovery_filters: dict[str, Any] = {
            "dimension": discovery_dimension,
            "project_key": settings.doradb_project_key.upper(),
        }
        if discovery_dimension == "release" and "release_year" in explicit_filters:
            discovery_filters["release_year"] = explicit_filters["release_year"]
        return {
            "mode": "data",
            "intent": "discovery",
            "confidence": 0.99,
            "actions": [
                {
                    "query_id": "list_dimension_values",
                    "filters": discovery_filters,
                    "limit": int(
                        QUERY_CATALOGUE["list_dimension_values"]["default_limit"]
                    ),
                    "reason": (
                        f"Retrieve current governed {discovery_dimension} values."
                    ),
                }
            ],
            "reason": "Explicit dimension-discovery request.",
            "clarification": "",
        }
    previous = memory.get("last_context", {})
    has_previous_topic = bool(previous.get("metric") or previous.get("query_ids"))
    filters = {
        **(previous.get("filters", {}) if has_previous_topic else {}),
        **explicit_filters,
    }

    # Keep conversational dimensions until the user explicitly widens scope.
    # This makes "what do you understand from release frequency?" continue to
    # mean the active Jaeger squad instead of silently switching to all squads.
    if is_scope_widening_request(message) or re.search(
        r"\boverall\b", message, re.I
    ):
        filters.pop("dcpsquad", None)
    if re.search(r"\b(all years?|every year|across years?)\b", message, re.I):
        filters.pop("release_year", None)
        filters.pop("release_date", None)

    follow_up = has_previous_topic and (
        _references_previous_answer(message, memory)
        or bool(
        re.search(
            r"\b(that|same|previous|above|it|this|those|them|"
            r"for\s+20\d{2}|chart|graph|plot|diagram|explain|break\s*down)\b",
            message,
            re.I,
        )
        )
    )
    grounded_dimensions = set(grounding.get("matches", {}))
    if intent["name"] == "general_conversation" and grounded_dimensions:
        if grounded_dimensions & {"issue_type", "status"}:
            grounded_intent = "issue_listing"
        elif "release" in grounded_dimensions:
            grounded_intent = "release_drilldown"
        else:
            grounded_intent = "metric_lookup"
        intent = {
            "name": grounded_intent,
            "confidence": 0.94,
            "visualization_requested": intent["visualization_requested"],
        }
    if follow_up:
        if intent["name"] == "general_conversation":
            if not _requires_dataset_action(message) and not (
                set(explicit_filters) - {"project_key"}
            ):
                return {
                    "mode": "conversation",
                    "intent": "context_follow_up",
                    "confidence": 0.94,
                    "actions": [],
                    "reason": "The question refers to the preceding in-domain answer.",
                    "clarification": "",
                }
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
    elif (
        intent["name"] == "release_drilldown"
        or "fixversion" in filters
        or "release_name" in filters
    ):
        query_id = "dora_metrics_release_detail"
    elif intent["name"] == "explanation" and (
        "release_year" in filters or "release_date" in filters
    ):
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
    entity_catalogue: dict[str, list[str]] | None = None,
    grounding: dict[str, Any] | None = None,
) -> tuple[AgentPlan, str]:
    """Let DeepSeek interpret the request, then validate its proposed actions.

    The deterministic plan is deliberately a fallback, not the primary router.
    It still blocks unsafe/out-of-domain requests before a cloud call and keeps
    the application useful when the provider is unavailable.
    """

    entity_catalogue = entity_catalogue or {}
    grounding = grounding or resolve_entities(message, entity_catalogue)
    fallback = deterministic_plan(
        message,
        memory,
        entity_catalogue=entity_catalogue,
        grounding=grounding,
    )
    if fallback["mode"] == "conversation":
        return enforce_plan(fallback), "conversation"
    if fallback["intent"] == "unsafe_request":
        return enforce_plan(fallback), "scope-guard"
    if not llm.enabled:
        return enforce_plan(fallback), "deterministic"

    supplied_history = browser_history or [
        {"role": "user", "content": str(item.get("user", ""))}
        for item in memory.get("turns", [])
    ] + [
        {"role": "assistant", "content": str(item.get("assistant", ""))}
        for item in memory.get("turns", [])
    ]
    history_text = "\n".join(
        f"{item.get('role', 'user').upper()}: {item.get('content', '')[:800]}"
        for item in supplied_history[-12:]
    )
    memory_context = json.dumps(memory.get("last_context", {}), default=str)
    entity_context = json.dumps(compact_catalogue(entity_catalogue), default=str)
    grounding_context = json.dumps(grounding, default=str)
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
- For requests asking what values exist or are available, use
  list_dimension_values with exactly one governed dimension. Do not use a
  metrics query to list dimension values.
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
- Treat the live entity catalogue as authoritative for projects, squads,
  release years, releases, issue types, statuses, and metrics. Understand any
  listed value regardless of casing or where it appears in the sentence.
- When two values from one dimension are compared, create separate governed
  actions where the selected tool accepts only one value per action.
- Use structured memory to resolve follow-ups such as "for 2022", "explain
  that", "what does that term mean", "compare it", or "make a chart for it".
- Use mode=conversation only when no database evidence is required. Never
  promise that a query will happen later.
- Chart requests are safe data requests.
- Use mode=out_of_scope for writes, secrets, harmful requests, or questions
  unrelated to DoraDB, DORA, Jira, releases, and software delivery. Never mark
  a message out of scope merely because it is short or uses an unfamiliar
  sentence structure."""
    raw = llm.complete(
        system,
        (
            f"Current date: {date.today().isoformat()}\n"
            f"Memory context: {memory_context}\n"
            f"Live governed entity catalogue: {entity_context}\n"
            f"Entities matched in this request: {grounding_context}\n"
            f"Conversation: {history_text or '(none)'}\n"
            f"Request: {message}"
        ),
        json_mode=True,
        temperature=settings.deepseek_planner_temperature,
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
            {
                key: value
                for key, value in fallback["actions"][0]["filters"].items()
                # Discovery identity belongs to the generative planner. The
                # deterministic dimension is reserved for fallback only.
                if key != "dimension"
            }
            if fallback["mode"] == "data" and fallback["actions"]
            else {
                **extract_filters(
                    message,
                    project_key=settings.doradb_project_key,
                ),
                **grounding.get("filters", {}),
            }
        )
        rejected_entity_filters: list[str] = [
            f"{key}={value}"
            for key, value in base_filters.items()
            if key != "project_key"
            and not filter_value_is_grounded(key, value, entity_catalogue)
        ]
        base_filters = {
            key: value
            for key, value in base_filters.items()
            if key == "project_key"
            or filter_value_is_grounded(key, value, entity_catalogue)
        }
        for item in parsed.get("actions", []):
            if not isinstance(item, dict):
                continue
            model_filters = item.get("filters") if isinstance(item.get("filters"), dict) else {}
            safe_model_filters: dict[str, Any] = {}
            for key, value in model_filters.items():
                if key == "project_key":
                    continue
                if not filter_value_is_grounded(key, value, entity_catalogue):
                    rejected_entity_filters.append(f"{key}={value}")
                    continue
                safe_model_filters[key] = value
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

        if rejected_entity_filters:
            plan = {
                **plan,
                "mode": "clarification",
                "intent": "unknown_entity",
                "actions": [],
                "confidence": 1.0,
                "reason": "A proposed filter was not present in the live entity catalogue.",
                "clarification": (
                    "I couldn't match one of the requested names to a current "
                    "DoraDB project, squad, release, year, issue type, or status. "
                    "Could you check the name or ask me to list the available values?"
                ),
            }

        # A model cannot discard a request already grounded in live data or
        # structured conversation context merely because its phrasing is terse.
        if plan["mode"] == "out_of_scope" and (
            fallback["mode"] != "out_of_scope"
            or grounding.get("has_matches")
            or _references_previous_answer(message, memory)
        ):
            plan = {
                **plan,
                "mode": "conversation",
                "actions": [],
                "intent": "context_follow_up",
                "reason": "The request is grounded in the governed domain or prior context.",
            }

        # An explicit request for data must execute now. If the model omitted a
        # usable action, the conservative allowlisted fallback supplies it.
        if (
            _requires_dataset_action(message)
            and (plan["mode"] != "data" or not plan["actions"])
            and fallback["mode"] == "data"
            and plan["intent"] != "unknown_entity"
        ):
            plan = fallback

        planner_source = getattr(
            llm,
            "source",
            f"deepseek:{settings.deepseek_model}",
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
