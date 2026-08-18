"""DeepSeek planner constrained by deterministic steering and controls. v2"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from ..config import settings
from ..database.doradb_catalog import (
    LARGE_QUERY_IDS,
    LARGE_QUERY_REQUIRED_FILTERS,
    QUERY_CATALOGUE,
    planner_context,
)
from ..llm import GenerativeAIClient
from ..services.filter_extraction import extract_filters
from ..services.entity_grounding import (
    compact_catalogue,
    filter_value_is_grounded,
    resolve_entities,
)
from ..services.intent_matching import classify_intent
from ..services.metric_selection import select_metric
from ..services.dimension_discovery import (
    is_scope_widening_request,
    match_discovery_dimension,
)
from .guardrails.tool_guardrail import enforce_plan
from .request_router import route_jira_request
from .state import AgentPlan, QueryAction


RUNTIME_INSTRUCTIONS_PATH = Path(__file__).resolve().parent / "INSTRUCTIONS.md"
AI_PLANNER_UNAVAILABLE = "AI_PLANNER_UNAVAILABLE"

# Clarifications the model (or the filter guard) raised *deliberately* --
# recovery must not paper over these. "unknown_entity" means the user named
# something that genuinely isn't in the catalogue; asking is the correct
# answer, and silently substituting a generic listing would be worse.
# Only `unknown_entity` belongs here: it means the user named something that
# genuinely isn't in the catalogue, so asking is the correct answer.
# `model_plan_incomplete` was previously listed too, which was wrong -- it
# means the model FAILED to produce a usable plan (e.g. it dropped a named
# squad), which is precisely when the deterministic router should take over.
# Skipping it made questions like "list all the squad and show the values
# available for each" return a clarifying question with zero queries.
_INTENTIONAL_CLARIFICATIONS = frozenset({"unknown_entity"})


def _planner_unavailable(reason: str) -> AgentPlan:
    """Fail closed when the model cannot provide a usable semantic plan."""

    return {
        "mode": "clarification",
        "intent": AI_PLANNER_UNAVAILABLE,
        "confidence": 1.0,
        "actions": [],
        "reason": reason,
        "clarification": "",
    }


# Queries whose subject is a concrete named column, so a question mentioning it
# is a request for the values rather than for a description of them. Kept
# deliberately small: widening this re-opens the "answered a capability
# question with a data dump" failure the recovery is otherwise careful to
# avoid.
_ANSWER_OUTRIGHT = frozenset(
    {"jira_issue_counts_by_assignee", "jira_issue_counts_by_reporter"}
)


def _deterministic_recovery(message: str, plan: AgentPlan) -> tuple[AgentPlan, str] | None:
    """Recover when the model asked an unnecessary clarifying question.

    The model stays the semantic interpreter. This fires in exactly one
    situation: the model understood the request well enough to answer
    coherently but returned ``mode="clarification"`` with no actions for a
    request the deterministic router unambiguously recognizes. Observed
    live -- "LIST SQUAD" produced clarification/0 actions while the
    equivalent "list all the squad" produced a correct data plan, so the
    model is simply flaky here. The planner prompt already instructs
    "NEVER set mode='conversation' for a data question"; prompt text alone
    did not hold, which is why this backstop is in code.

    It also fires for ``mode="conversation"``, but only for the handful of
    queries in ``_ANSWER_OUTRIGHT`` whose subject is a concrete named column.
    Conversation is otherwise a deliberate semantic choice and is left alone --
    answering "what data can I get?" with a data dump would be wrong. But "can
    you give the name for the assignee?" reads as a capability question, and
    the model duly explained that names are available instead of giving any.
    Asking for a thing by name is a request for the thing.

    Deliberately narrow -- it never:
      * touches ``mode="conversation"`` for anything outside
        ``_ANSWER_OUTRIGHT`` (KNOWLEDGE_EXPLANATION and general capability
        questions stay conversational);
      * touches ``mode="out_of_scope"`` (a safety decision);
      * runs when the model produced a usable data plan;
      * runs when the model/planner failed outright (malformed, invalid, or
        provider down) -- those fail closed, because a broken interpreter
        means we cannot trust that keyword routing answers the *asked*
        question;
      * overrides an intentional clarification (see the set above);
      * invents a query the deterministic router doesn't already recognize.
    """

    if plan["mode"] not in {"clarification", "conversation"}:
        return None
    if plan["mode"] == "clarification" and plan["intent"] in _INTENTIONAL_CLARIFICATIONS:
        return None
    route = route_jira_request(message)
    if plan["mode"] == "conversation":
        # Conversation is normally a deliberate semantic choice and is left
        # alone -- answering "what data can I get?" with a data dump would be
        # wrong. The exception is a question naming a concrete column the
        # router can answer outright. "Can you give the name for the assignee?"
        # reads as a capability question, and the model duly explained that
        # names are available instead of giving any: an answer that is true and
        # useless. Asking for a thing by name is a request for the thing.
        if route is None or not _ANSWER_OUTRIGHT.issuperset(
            action["query_id"] for action in route.get("actions", [])
        ):
            return None
    if route is None or route["mode"] != "data" or not route["actions"]:
        return None
    recovered = enforce_plan(route)
    if recovered["mode"] != "data" or not recovered["actions"]:
        return None
    return recovered, "deterministic-recovery"


def _load_planner_guidance() -> str:
    """Load the planner-relevant sections from the runtime instructions.

    Returns just the SOP skill-trigger matrix + the rule that every
    data question MUST execute a query. Kept short so the planner
    prompt doesn't overflow. Reads from backend/agent/INSTRUCTIONS.md
    (the runtime system prompt source), never from the root AGENTS.md, which
    is IDE/development guidance only and must not reach the model.
    """
    try:
        full = RUNTIME_INSTRUCTIONS_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""

    # Extract Section 2 (SOP) — the skill-trigger table + query-first rule
    m = re.search(
        r"(## 2\. Standard Operating Procedure.*?)(?=\n## 3\.|\Z)",
        full,
        re.DOTALL,
    )
    if not m:
        return ""
    sop = m.group(1).strip()

    # Extract the critical planning rules
    return (
        "CRITICAL PLANNING RULES:\n"
        "- For ANY data question (counts, types, status, metrics, squads, releases, "
        "bugs, backlogs, ageing, quality), set mode='data' and include at least one "
        "approved query_id. NEVER set mode='conversation' for a data question.\n"
        "- 'How many...', 'Show me...', 'What are the...', 'List...', 'Break down...' "
        "questions are ALWAYS data questions, not conversation.\n\n"
        + sop
    )


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
            r"how many|how much|do you have|give me|recommend|suggest|improv(?:e|ement)|"
            r"action plan|next steps?|what (?:is|are) the|tell me|"
            r"are there|find|get|fetch|display)\b",
            message,
            re.I,
        )
    )
    has_dataset_signal = bool(
        re.search(
            r"\b(dora|doradb|metric|release|deploy|failure|lead time|cycle time|"
            r"jira|tickets?|issues?|bugs?|feature|user stor(?:y|ies)|year|squad|team|"
            r"performance|delivery risk|engineering|titan|jaeger|dataset|data|"
            r"backlog|status|ageing|quality|blocked|impeded|open|resolved)\b",
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
        if _requires_dataset_action(message):
            # The user asked a data question using general language
            # (e.g. "how many open issues"). Escalate to a data query.
            return {
                "mode": "data",
                "intent": "data_overview",
                "confidence": 0.85,
                "actions": [
                    {
                        "query_id": "jira_dashboard_kpis",
                        "filters": {
                            "project_key": settings.doradb_project_key.upper(),
                        },
                        "limit": 50,
                        "reason": "User asked a data question — retrieve dashboard KPIs.",
                    }
                ],
                "reason": "Data question detected in general language — querying database.",
                "clarification": "",
            }
        return {
            "mode": "conversation",
            "intent": "general_conversation",
            "confidence": intent["confidence"],
            "actions": [],
            "reason": "A safe general question does not require a database query.",
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

    The configured model is the semantic interpreter. Deterministic code may
    block an unsafe request or reject an invalid model-selected tool, but it
    must not replace failed model understanding with a keyword-selected query.
    """

    entity_catalogue = entity_catalogue or {}
    grounding = grounding or resolve_entities(message, entity_catalogue)

    baseline_intent = classify_intent(message)
    if baseline_intent["name"] == "out_of_scope":
        return enforce_plan(
            {
                "mode": "out_of_scope",
                "intent": "unsafe_request",
                "confidence": 1.0,
                "actions": [],
                "reason": "The deterministic input guardrail blocked the request.",
                "clarification": "",
            }
        ), "scope-guard"
    if not llm.enabled:
        # Fail closed: with no working interpreter we cannot confirm that a
        # keyword-matched query answers the question actually asked.
        return _planner_unavailable("The configured AI planner is unavailable."), (
            "ai-provider-unavailable"
        )

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
    memory_context = json.dumps(
        {
            "conversation_summary": str(memory.get("conversation_summary", ""))[:3000],
            "last_context": memory.get("last_context", {}),
            "available_cached_evidence": (
                {
                    "query_ids": memory.get("query_cache", [])[-1].get("query_ids", []),
                    "row_count": memory.get("query_cache", [])[-1].get("row_count", 0),
                    "generated_at": memory.get("query_cache", [])[-1].get(
                        "generated_at", ""
                    ),
                    "complete": memory.get("query_cache", [])[-1].get(
                        "complete", False
                    ),
                }
                if memory.get("query_cache")
                and isinstance(memory.get("query_cache", [])[-1], dict)
                else None
            ),
        },
        default=str,
    )
    entity_context = json.dumps(compact_catalogue(entity_catalogue), default=str)
    grounding_context = json.dumps(grounding, default=str)
    system = f"""{_load_planner_guidance()}

You are the reasoning and tool-planning agent for a governed
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
- Treat questions about what kinds of data, metrics, reports, or analyses are
  available as capability explanations, not requests for current database
  values. Use mode=conversation with intent CAPABILITY_EXPLANATION and no
  actions. Explain the approved capabilities directly; do not require a
  squad, release, or year unless the user asks to retrieve actual values.
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
- For "all squads", "every squad", "each squad", or any squad-to-squad
  comparison, use dora_metrics_all_squads with NO dcpsquad filter. It returns
  every squad in one call. Never try to cover all squads by issuing repeated
  dora_metrics_by_squad calls: only a couple of tool calls are permitted per
  turn, so that silently reports on one or two squads and leaves the rest
  looking like they have no data.
- Treat the live entity catalogue as authoritative for projects, squads,
  release years, releases, issue types, statuses, and metrics. Understand any
  listed value regardless of casing or where it appears in the sentence.
- When two values from one dimension are compared, create separate governed
  actions where the selected tool accepts only one value per action.
- Use structured memory to resolve follow-ups such as "for 2022", "explain
  that", "what does that term mean", "compare it", or "make a chart for it".
- Use mode=conversation only when no database evidence is required. Never
  promise that a query will happen later.
- If the request is a semantic follow-up that can be answered completely from
  the available cached evidence, use mode=conversation, intent exactly
  FOLLOW_UP_ON_EXISTING_RESULT, and no actions. Do not use this intent for a
  new topic, changed filter, refresh request, or question requiring new data.
- If the user's message repeats (exactly or nearly) a question already
  answered earlier in this conversation, that is a request to re-answer it,
  never a reason to ask a clarifying or confirming question. The earlier
  answer proves the question was already understood. Re-run the same data
  action (mode=data) so the answer is regenerated from fresh evidence, or use
  FOLLOW_UP_ON_EXISTING_RESULT if the cached evidence still applies. Do not
  ask "are you asking whether..." or offer alternate readings of a question
  you already answered.
- For Jira documentation or definition questions that need no live data, use
  mode=conversation and intent exactly KNOWLEDGE_EXPLANATION. For live schema
  checks use DATABASE_METADATA; for safe Jira aggregates use DATA_RETRIEVAL or
  ANALYSIS. These intent names let downstream evidence handling load the right
  verified context.
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
        temperature=settings.llm_planner_temperature,
    )
    parsed = _parse_json(raw) if raw else None
    if not parsed or "mode" not in parsed or "intent" not in parsed:
        # Fail closed rather than keyword-routing a request the model never
        # actually interpreted (see test_malformed_model_plan_...).
        return _planner_unavailable("The AI planner returned an unusable plan."), (
            "ai-planner-unavailable"
        )

    try:
        mode = str(parsed.get("mode", "data"))
        if mode not in {"data", "conversation", "clarification", "out_of_scope"}:
            raise ValueError("invalid mode")
        actions: list[QueryAction] = []
        # Deterministic extraction may ground literal values from the prompt,
        # but it never chooses the intent or query. The model remains the only
        # semantic planner.
        base_filters = {
            **extract_filters(
                message,
                project_key=settings.doradb_project_key,
            ),
            **grounding.get("filters", {}),
        }
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
            "intent": str(parsed["intent"])[:100],
            "confidence": max(0.0, min(1.0, float(parsed.get("confidence", 0.75)))),
            "actions": actions,
            "reason": str(parsed.get("reason") or "Model-generated plan")[:300],
            "clarification": str(parsed.get("clarification") or "")[:300],
        }

        if rejected_entity_filters:
            plan = {
                **plan,
                "mode": "clarification",
                "intent": "unknown_entity",
                "actions": [],
                "confidence": 1.0,
                "reason": (
                    "Filters not present in the live entity catalogue: "
                    + ", ".join(sorted(set(rejected_entity_filters)))
                ),
                # Name the value that actually failed. This used to say only
                # "one of the requested names", which left the responder to
                # guess which one -- and it guessed the squad, telling users
                # "I couldn't find a squad named MBK" about a squad that has
                # 1,434 bugs. An unnamed rejection becomes a false statement.
                "clarification": (
                    "I couldn't match "
                    + ", ".join(
                        f"`{item}`" for item in sorted(set(rejected_entity_filters))
                    )
                    + " to a current DoraDB value. Everything else in the request "
                    "was understood. Could you check that value, or ask me to list "
                    "the available options for it?"
                ),
            }

        planner_source = getattr(
            llm,
            "source",
            settings.llm_source,
        )
        if (
            "dcpsquad" in base_filters
            and plan["mode"] == "data"
            and plan["actions"]
            and not any(
                "dcpsquad"
                in (QUERY_CATALOGUE.get(action["query_id"], {}).get("allowed_filters") or ())
                for action in plan["actions"]
            )
        ):
            # A named squad is an explicit grounded constraint, so a plan whose
            # queries cannot accept it would silently answer project-wide.
            #
            # This used to require the query to be `dora_metrics_by_squad`
            # specifically, which made it fire on perfectly good plans: four
            # other approved queries also accept a squad, and asking "for squad
            # MBK, show work by status" produced an empty clarification that
            # the responder turned into a vague "can you confirm the squad?".
            # Test against what the query actually accepts instead. Still no
            # replacement query is chosen here -- that stays the model's job.
            plan = {
                **plan,
                "mode": "clarification",
                "intent": "model_plan_incomplete",
                "actions": [],
                "reason": "The selected queries cannot be filtered by the named squad.",
                "clarification": (
                    f"I can't break that particular view down by squad "
                    f"{base_filters['dcpsquad']} — the underlying query doesn't "
                    "support a squad filter. I can show it across the whole "
                    "project, or give you the squad-level metrics instead. "
                    "Which would you prefer?"
                ),
            }

        controlled = enforce_plan(plan)
        # The model produced a syntactically valid plan that still cannot
        # answer the question (e.g. it asked a clarifying question about an
        # unambiguous "list all the squads"). Recover only if the
        # deterministic router clearly recognizes the request.
        recovery = _deterministic_recovery(message, controlled)
        return recovery or (controlled, planner_source)
    except (TypeError, ValueError):
        return _planner_unavailable("The AI planner returned an invalid plan."), (
            "ai-planner-unavailable"
        )
