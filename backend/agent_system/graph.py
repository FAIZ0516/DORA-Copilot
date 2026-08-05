"""Full LangGraph workflow for governed, generative DoraDB analysis."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from ..config import settings
from ..doradb import DoraDbConfigurationError, DoraDbQueryRejected
from ..doradb_catalog import (
    DISCOVERY_DIMENSIONS,
    METRIC_DEFINITIONS,
    planner_context,
)
from ..llm import GenerativeAIClient
from ..skills import (
    analyze_trend,
    build_chart_spec,
    classify_intent,
    compare_rows,
    detect_anomalies,
    execute_approved_query,
    load_entity_catalogue,
    merge_memory_entities,
    message_mentions_metric,
    select_delivery_performance_metric,
    select_metric,
    select_metric_by_id,
    resolve_entities,
)
from .audit import audit_log
from .control import ensure_within_deadline, public_policy
from .memory import memory_store
from .planner import create_plan
from .result_validator import validate_answer, validate_results
from .state import AgentState


def _strip_markdown_fence(text: str) -> str:
    return re.sub(
        r"\A```(?:markdown|md)?\s*\n?(.*?)\n?```\s*\Z",
        r"\1",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()


def _load_agents_md() -> str:
    """Extract the chatbot-relevant section from AGENTS.md at request time.

    Only the RESPONSE PROTOCOL section is sent to DeepSeek — the rest
    (coding standards, tech stack, file references) is for the IDE agent
    and would only confuse the chatbot. Reading on every call means edits
    to AGENTS.md take effect immediately.
    """
    agents_path = Path(__file__).resolve().parent.parent.parent / "AGENTS.md"
    try:
        full = agents_path.read_text(encoding="utf-8")
    except OSError:
        logger = logging.getLogger(__name__)
        logger.warning("AGENTS.md not found at %s — chatbot runs without it.", agents_path)
        return ""

    # Extract only the RESPONSE PROTOCOL section (between its heading
    # and the next heading or horizontal rule). The rest of AGENTS.md is
    # coding standards for the IDE agent — irrelevant to the chatbot.
    import re as _re
    m = _re.search(
        r"##\s*⚠️\s*RESPONSE\s+PROTOCOL.*?\n(?=\n*(?:---|##\s))",
        full,
        _re.DOTALL | _re.IGNORECASE,
    )
    if not m:
        logger = logging.getLogger(__name__)
        logger.warning("RESPONSE PROTOCOL section not found in AGENTS.md.")
        return ""

    section = m.group(0).strip()
    logger = logging.getLogger(__name__)
    logger.info("Loaded AGENTS.md RESPONSE PROTOCOL for chatbot (%d chars).", len(section))
    return section


AI_UNAVAILABLE_MESSAGE = (
    "The DeepSeek model is unavailable right now, or the API account has no "
    "available balance. I did not substitute a template answer. Please try "
    "again after the DeepSeek service or account is available."
)

logger = logging.getLogger(__name__)


def _table_spec(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not results or not results[0].get("rows"):
        return None
    rows = results[0]["rows"][:50]
    preferred = [
        "dimension",
        "value",
        "record_count",
        "total_values",
        "dcpsquad",
        "release_year",
        "release_date",
        "fixversion",
        "jira_key",
        "issuetype",
        "status",
        "release_count",
        "release_frequency_months",
        "change_failure_rate_pct",
        "lead_time_for_change_months",
        "delivery_cycle_time_months",
        "user_story_to_feature_ratio",
    ]
    keys = [key for key in preferred if key in rows[0]][:8]
    if not keys:
        keys = list(rows[0])[:8]
    return {
        "title": "Supporting data",
        "columns": [{"key": key, "label": key.replace("_", " ").title()} for key in keys],
        "rows": [{key: row.get(key) for key in keys} for row in rows],
        "truncated": len(results[0]["rows"]) > len(rows),
    }


def _wants_table(
    message: str,
    intent: str,
    results: list[dict[str, Any]] | None = None,
) -> bool:
    """Keep evidence available without forcing a table into every answer."""

    explicit = bool(
        re.search(
            r"\b(table|tabular|raw data|evidence table|data rows?|records?|"
            r"spreadsheet|csv)\b",
            message,
            re.I,
        )
    )
    if explicit or intent == "issue_listing":
        return True
    # A long catalogue is easier to scan as a table; short discovery answers
    # remain conversational unless the user explicitly requests rows.
    return bool(
        intent == "discovery"
        and results
        and results[0].get("row_count", len(results[0].get("rows", []))) > 30
    )


def _discovery_answer(result: dict[str, Any]) -> str:
    """Render simple catalogue evidence without asking a model to reinterpret it."""

    filters = result.get("filters", {})
    dimension = str(filters.get("dimension", "value"))
    definition = DISCOVERY_DIMENSIONS.get(
        dimension,
        {"label": dimension.replace("_", " ")},
    )
    label = str(definition["label"])
    rows = result.get("rows", [])
    if not rows:
        scope_parts = [f"project {filters.get('project_key', settings.doradb_project_key)}"]
        if filters.get("release_year"):
            years = ", ".join(str(year) for year in filters["release_year"])
            scope_parts.append(f"release year {years}")
        return (
            f"No matching {dimension.replace('_', ' ')} values were returned "
            f"for the applied filters. Scope: {'; '.join(scope_parts)}. "
            "This result applies only to that "
            "dimension and scope; it does not mean the rest of DoraDB is empty."
        )

    total = int(rows[0].get("total_values") or len(rows))
    values = [str(row.get("value", "")).strip() for row in rows]
    values = [value for value in values if value]
    displayed = values[:30]
    rendered = ", ".join(value.replace("_", " ") for value in displayed)
    suffix = (
        f" Showing the first {len(displayed)} here; the supporting table contains "
        f"{len(rows)} returned values."
        if total > len(displayed)
        else ""
    )
    return (
        f"DoraDB currently has {total} {label} in the governed "
        f"{filters.get('project_key', settings.doradb_project_key)} scope: "
        f"{rendered}.{suffix}"
    )


def _is_holistic_request(message: str, intent: str) -> bool:
    return intent in {
        "recommendation",
        "anomaly",
        "explanation",
        "comparison",
        "trend",
    } or bool(
        re.search(
            r"\b(overall|delivery performance|delivery risk|biggest risk|"
            r"most surprising|recommend|suggest|priorit(?:y|ize)|"
            r"improv(?:e|ement)|health|all metrics?)\b",
            message,
            re.I,
        )
    )


_ANALYTICAL_METRICS = {
    "release_frequency": "release_frequency_months",
    "change_failure_rate": "change_failure_rate_pct",
    "lead_time_for_change": "lead_time_for_change_months",
    "delivery_cycle_time": "delivery_cycle_time_months",
}


class AdvancedDoraDbAgent:
    """A DeepSeek agent with deterministic controls around every data action."""

    def __init__(self, session: Session | None) -> None:
        self.session = session
        self.llm = GenerativeAIClient(settings)
        graph = StateGraph(AgentState)
        graph.add_node("load_memory", self._load_memory)
        graph.add_node("plan", self._plan)
        graph.add_node("execute", self._execute)
        graph.add_node("validate_result", self._validate_result)
        graph.add_node("repair", self._repair)
        graph.add_node("analyze", self._analyze)
        graph.add_node("respond", self._respond)
        graph.add_node("validate_answer", self._validate_answer)
        graph.add_node("regenerate", self._regenerate)
        graph.add_node("save", self._save)
        graph.set_entry_point("load_memory")
        graph.add_edge("load_memory", "plan")
        graph.add_conditional_edges(
            "plan",
            self._route_after_plan,
            {"execute": "execute", "respond": "respond"},
        )
        graph.add_edge("execute", "validate_result")
        graph.add_conditional_edges(
            "validate_result",
            self._route_after_result_validation,
            {"repair": "repair", "analyze": "analyze"},
        )
        graph.add_edge("repair", "validate_result")
        graph.add_edge("analyze", "respond")
        graph.add_edge("respond", "validate_answer")
        graph.add_conditional_edges(
            "validate_answer",
            self._route_after_answer_validation,
            {"regenerate": "regenerate", "save": "save"},
        )
        graph.add_edge("regenerate", "validate_answer")
        graph.add_edge("save", END)
        self.graph = graph.compile()

    def _load_memory(self, state: AgentState) -> dict[str, Any]:
        memory = memory_store.get(state["session_id"])
        try:
            catalogue = load_entity_catalogue(
                state.get("db_session"),
                project_key=settings.doradb_project_key,
            )
        except SQLAlchemyError as exc:
            # Entity grounding improves language understanding, but a temporary
            # catalogue refresh failure must not block safe conversation. A
            # later data action will still surface the database outage.
            logger.warning("Could not refresh DoraDB entity catalogue: %s", exc)
            catalogue = load_entity_catalogue(None)
        catalogue = merge_memory_entities(catalogue, memory)
        return {
            "memory": memory,
            "entity_catalogue": catalogue,
            "grounding": resolve_entities(state["message"], catalogue),
            "started_at": time.monotonic(),
            "repair_count": 0,
            "answer_retry_count": 0,
            "warnings": [],
        }

    def _plan(self, state: AgentState) -> dict[str, Any]:
        plan, source = create_plan(
            state["message"],
            memory=state["memory"],
            browser_history=state.get("browser_history", []),
            llm=self.llm,
            entity_catalogue=state.get("entity_catalogue", {}),
            grounding=state.get("grounding", {}),
        )
        metric = select_metric(state["message"])
        if (
            not message_mentions_metric(state["message"])
            and _is_holistic_request(state["message"], plan["intent"])
        ):
            metric = select_delivery_performance_metric()
        elif not message_mentions_metric(state["message"]):
            metric = select_metric_by_id(
                state.get("memory", {}).get("last_context", {}).get("metric")
            )
        return {
            "plan": plan,
            "planner_source": source,
            "metric": metric,
        }

    @staticmethod
    def _route_after_plan(state: AgentState) -> str:
        return "execute" if state["plan"]["mode"] == "data" else "respond"

    def _execute(self, state: AgentState) -> dict[str, Any]:
        ensure_within_deadline(state["started_at"])
        if state.get("db_session") is None:
            raise DoraDbConfigurationError(
                "DoraDB credentials are required for dataset analysis. "
                "Configure DORADB_USER and DORADB_PASSWORD in .env."
            )
        results = [
            execute_approved_query(
                state["db_session"],
                query_id=action["query_id"],
                filters=action["filters"],
                limit=action["limit"],
            )
            for action in state["plan"]["actions"]
        ]
        return {"results": results}

    def _validate_result(self, state: AgentState) -> dict[str, Any]:
        validation = validate_results(state.get("results", []))
        return {
            "validation": validation,
            "warnings": validation.get("warnings", []),
        }

    @staticmethod
    def _route_after_result_validation(state: AgentState) -> str:
        if (
            not state["validation"]["valid"]
            and state.get("repair_count", 0) < settings.agent_max_retries
        ):
            return "repair"
        return "analyze"

    def _repair(self, state: AgentState) -> dict[str, Any]:
        """One controlled retry; it cannot change query identity or widen scope."""

        ensure_within_deadline(state["started_at"])
        if state.get("db_session") is None:
            raise DoraDbConfigurationError(
                "DoraDB credentials are required for dataset analysis."
            )
        repaired: list[dict[str, Any]] = []
        for action in state["plan"]["actions"]:
            repaired.append(
                execute_approved_query(
                    state["db_session"],
                    query_id=action["query_id"],
                    filters=action["filters"],
                    limit=min(action["limit"], 100),
                )
            )
        return {
            "results": repaired,
            "repair_count": state.get("repair_count", 0) + 1,
        }

    def _analyze(self, state: AgentState) -> dict[str, Any]:
        results = state.get("results", [])
        rows = results[0]["rows"] if results else []
        metric = state["metric"]
        primary_query = results[0]["query_id"] if results else ""
        by_query: list[dict[str, Any]] = []
        metric_trends: dict[str, list[dict[str, Any]]] = {
            metric_id: [] for metric_id in _ANALYTICAL_METRICS
        }
        for result in results:
            result_rows = result.get("rows", [])
            query_id = result.get("query_id", "")
            query_analysis: dict[str, Any] = {
                "query_id": query_id,
                "row_count": len(result_rows),
                "metrics": {},
            }
            if query_id in {"dora_metrics_by_year", "dora_metrics_by_squad"}:
                for metric_id, field in _ANALYTICAL_METRICS.items():
                    summary = {
                        "comparisons": compare_rows(result_rows, field),
                        "trend": analyze_trend(result_rows, field),
                        "anomalies": detect_anomalies(result_rows, field),
                    }
                    query_analysis["metrics"][metric_id] = summary
                    metric_trends[metric_id].append(
                        {"query_id": query_id, **summary}
                    )
            by_query.append(query_analysis)
        analysis = {
            "comparisons": compare_rows(rows, metric["field"])
            if primary_query in {"dora_metrics_by_year", "dora_metrics_by_squad"}
            else [],
            "trend": analyze_trend(rows, metric["field"])
            if primary_query in {"dora_metrics_by_year", "dora_metrics_by_squad"}
            else {},
            "anomalies": detect_anomalies(rows, metric["field"])
            if primary_query in {"dora_metrics_by_year", "dora_metrics_by_squad"}
            else [],
            "by_query": by_query,
            "metric_trends": metric_trends,
        }
        visualization_requested = classify_intent(
            state["message"]
        )["visualization_requested"]
        chart = (
            build_chart_spec(
                query_id=primary_query,
                rows=rows,
                metric=metric,
                question=state["message"],
            )
            if primary_query and visualization_requested
            else None
        )
        return {
            "analysis": analysis,
            "chart": chart,
            "table": (
                _table_spec(results)
                if _wants_table(
                    state["message"],
                    state.get("plan", {}).get("intent", ""),
                    results,
                )
                else None
            ),
        }

    def _respond(self, state: AgentState) -> dict[str, Any]:
        plan = state["plan"]
        answer_source = "control"
        if plan["mode"] == "out_of_scope":
            if plan["intent"] == "out_of_context":
                answer = (
                    "OK CAPTAIN. I can only help with the connected DoraDB dataset: DORA "
                    "metrics, releases, delivery performance, Jira issues, DCPM "
                    "squads, and related engineering analysis. Please ask a "
                    "question within that scope."
                )
                answer_source = "scope-guard"
            else:
                answer = (
                    "I can analyze DoraDB through approved read-only tools, but "
                    "I cannot modify data, run arbitrary SQL, or expose credentials."
                )
        elif plan["mode"] == "clarification":
            if state.get("planner_source", "").startswith("deepseek:"):
                answer = plan["clarification"]
                answer_source = self.llm.source
            else:
                answer = AI_UNAVAILABLE_MESSAGE
                answer_source = "ai-provider-unavailable"
        elif plan["mode"] == "conversation":
            conversation = "\n".join(
                f"{item.get('role', 'user').upper()}: {item.get('content', '')[:1200]}"
                for item in state.get("browser_history", [])[-10:]
            )
            if not conversation:
                conversation = "\n".join(
                    f"USER: {item.get('user', '')[:800]}\n"
                    f"ASSISTANT: {item.get('assistant', '')[:1200]}"
                    for item in state.get("memory", {}).get("turns", [])[-6:]
                )
            prompt = f"""{_load_agents_md()}

You are the conversational reasoning layer of DORA
Intelligence. Answer the user's current in-domain conversational request
naturally and specifically using the supplied conversation. If they ask what
a word, caveat, conclusion, or earlier statement means, explain that exact
thing in context. If they greet you, greet them briefly. If they ask about
capabilities, describe the connected read-only DoraDB capabilities accurately.
Do not use a canned menu, do not repeat the scope statement, do not claim a
database query ran, and do not invent facts or numbers that are not present in
the conversation. Ask a follow-up only when it is genuinely required."""
            generated = self.llm.complete(
                prompt,
                (
                    f"Conversation:\n{conversation or '(none)'}\n\n"
                    f"Current request: {state['message']}"
                ),
            )
            answer = generated or AI_UNAVAILABLE_MESSAGE
            answer_source = (
                self.llm.source
                if generated
                else "ai-provider-unavailable"
            )
        else:
            results = state.get("results", [])
            primary = results[0] if results else {
                "query_id": "",
                "rows": [],
                "filters": {},
            }
            is_discovery = primary.get("query_id") == "list_dimension_values"
            answer = (
                _discovery_answer(primary)
                if is_discovery
                else AI_UNAVAILABLE_MESSAGE
            )
            answer_source = (
                "deterministic-discovery"
                if is_discovery
                else "ai-provider-unavailable"
            )
            if self.llm.enabled and state["validation"]["valid"]:
                conversation = "\n".join(
                    f"{item.get('role', 'user').upper()}: "
                    f"{item.get('content', '')[:1200]}"
                    for item in state.get("browser_history", [])[-8:]
                )
                evidence = json.dumps(
                    {
                        "question": state["message"],
                        "as_of_date": date.today().isoformat(),
                        "conversation": conversation,
                        "memory_context": state.get("memory", {}).get(
                            "last_context", {}
                        ),
                        "metric": state["metric"],
                        "results": results,
                        "deterministic_analysis": state.get("analysis", {}),
                        "chart_spec": state.get("chart"),
                    },
                    default=str,
                )
                prompt = f"""{_load_agents_md()}

You are a senior DORA analyst with freedom to reason
over trusted evidence. Understand the user's actual goal from the current
question and recent conversation, examine all supplied query results together,
and compose the most useful direct answer. Use only validated evidence for
facts and numbers, but make your own analytical judgment about which patterns
matter and how to explain them.

Do not follow a fixed answer template. Do not begin with row counts, query
names, validation language, or a generic definition unless the user asked for
one. Choose the structure, depth, comparisons, and emphasis that best fit this
specific question. Do not mention JSON, query IDs, database field names,
deterministic analysis, validation machinery, or implementation details.
 Never promise future querying. Speak as an experienced analyst.

For discovery requests, directly answer which governed values exist and how
many were found. Use the supplied list_dimension_values evidence, respect its
total_values and applied limit, and never replace it with remembered examples.
An empty filtered discovery result applies only to that dimension and scope;
it does not prove that other DoraDB data is absent.

Treat the current calendar year as potentially incomplete. Do not compare its
release count with completed full years as if they covered equal periods, and
state that limitation whenever it materially affects a conclusion. Never call
an earlier completed calendar year "year-to-date", "so far", "partial", or
"still in progress" merely because it has fewer rows. Do not say a completed
year is provisional until more releases arrive; later releases cannot change
that completed year's count. A small completed-year sample may be described as
limited, but not incomplete. Correlation
is not causation: describe possible drivers as hypotheses unless the evidence
directly proves them.

For recommendation or improvement requests, evaluate every DORA measure present
in the evidence, identify the strongest improvement opportunity, and propose
specific prioritized actions. Distinguish observed facts from possible causes.
Do not reduce a holistic squad recommendation to only release frequency.
If the user asks what years exist, count and list the release_year values. If
they ask for a metric, state the relevant values and explain the meaningful
pattern. If chart_spec is present, refer to it as the chart rendered below and
describe only the series actually listed in chart_spec. Never say the chart
"could" or "would" be created and never invent additional chart series. Use
concise bullets only when they improve clarity. Preserve warnings exactly.
Label possible causes as inferences and never claim causality without evidence.
Use the supplied precomputed comparisons silently and do not alter numeric values. Keep
under 550 words.

{planner_context()}
Metric definitions: {json.dumps(METRIC_DEFINITIONS)}"""
                generated = self.llm.complete(
                    prompt,
                    evidence,
                    temperature=settings.deepseek_response_temperature,
                )
                if generated:
                    answer = _strip_markdown_fence(generated)
                    answer_source = self.llm.source
        return {"answer": answer, "answer_source": answer_source}

    def _validate_answer(self, state: AgentState) -> dict[str, Any]:
        if state.get("answer_source") == "ai-provider-unavailable":
            validation = {"valid": True, "unsupported_numbers": [], "warning_missing": False}
        elif state["plan"]["mode"] != "data":
            validation = {"valid": True, "unsupported_numbers": [], "warning_missing": False}
        else:
            validation = validate_answer(
                state["answer"],
                results=state.get("results", []),
                analysis=state.get("analysis", {}),
                question=state["message"],
                required_warnings=state.get("warnings", []),
            )
        return {"answer_validation": validation}

    @staticmethod
    def _route_after_answer_validation(state: AgentState) -> str:
        if (
            not state["answer_validation"]["valid"]
            and state.get("answer_retry_count", 0) < 1
        ):
            return "regenerate"
        return "save"

    def _regenerate(self, state: AgentState) -> dict[str, Any]:
        """Ask the cloud model to repair an answer against the same evidence."""

        results = state.get("results", [])
        evidence = json.dumps(
            {
                "question": state["message"],
                "metric": state["metric"],
                "results": results,
                "deterministic_analysis": state.get("analysis", {}),
                "chart_spec": state.get("chart"),
                "validation_feedback": state.get("answer_validation", {}),
            },
            default=str,
        )
        repaired = self.llm.complete(
            f"""You are a senior DORA analyst repairing an evidence-grounded answer.
Answer the user's exact question now using only the supplied JSON. Do not
promise future work. Keep every numeric statement traceable to results or
the supplied comparisons. Be natural and specific, not a canned template.
The current date is {date.today().isoformat()}. Only {date.today().year} may be
described as current, year-to-date, or in progress. Never call an earlier
calendar year partial or provisional merely because it has fewer records, and
never imply future releases can be added to a completed year.
For recommendation requests, assess every DORA measure in the evidence and
prioritize concrete actions instead of merely listing values.
Never mention JSON, query IDs, field names, deterministic analysis, or
validation internals. If the question asks what years exist, count and list
those years. Keep under 350 words.""",
            evidence,
            temperature=min(settings.deepseek_response_temperature, 0.2),
        )
        answer = _strip_markdown_fence(repaired) if repaired else AI_UNAVAILABLE_MESSAGE
        return {
            "answer": answer,
            "answer_source": (
                self.llm.source
                if repaired
                else "ai-provider-unavailable"
            ),
            "answer_retry_count": state.get("answer_retry_count", 0) + 1,
        }

    def _save(self, state: AgentState) -> dict[str, Any]:
        results = state.get("results", [])
        query_ids = [item["query_id"] for item in results]
        filters = results[0].get("filters", {}) if results else {}
        metadata = {
            "data_source": "doradb",
            "project": settings.doradb_project_key,
            "query_ids": query_ids,
            "row_counts": [item["row_count"] for item in results],
            "analysis_steps": len(results),
            "planner": state.get("planner_source", "deterministic"),
            "answer_source": state.get("answer_source", "control"),
            "confidence": state["plan"]["confidence"],
            "warnings": state.get("warnings", []),
            "validation_status": state.get("validation", {}).get("status", "not_applicable"),
            "validation_checks": state.get("validation", {}).get("checks", []),
            "repairs": state.get("repair_count", 0),
            "answer_regenerations": state.get("answer_retry_count", 0),
            "control": public_policy(),
            "grounded_entities": state.get("grounding", {}).get("matches", {}),
            "presentation": {
                "chart": bool(state.get("chart")),
                "table": bool(state.get("table")),
            },
        }
        prior_context = state.get("memory", {}).get("last_context", {})
        discovered_values: dict[str, list[str]] = {}
        for result in results:
            if result.get("query_id") != "list_dimension_values":
                continue
            dimension = str(result.get("filters", {}).get("dimension", ""))
            if dimension:
                discovered_values[dimension] = [
                    str(row.get("value", "")).strip()
                    for row in result.get("rows", [])
                    if str(row.get("value", "")).strip()
                ]
        next_context = (
            {
                "intent": state["plan"]["intent"],
                "metric": state.get("metric", {}).get("id"),
                "filters": filters,
                "query_ids": query_ids,
                "warnings": state.get("warnings", []),
                "entities": state.get("grounding", {}).get("matches", {}),
                "discovered_values": discovered_values,
                "user_goal": state["message"],
            }
            if state["plan"]["mode"] in {"data", "clarification"}
            else prior_context
        )
        memory_store.remember(
            state["session_id"],
            user_message=state["message"],
            assistant_answer=state["answer"],
            context=next_context,
        )
        audit_log.add(
            {
                "request_id": state["request_id"],
                "session_id": state["session_id"],
                "intent": state["plan"]["intent"],
                "query_ids": query_ids,
                "row_counts": metadata["row_counts"],
                "planner": metadata["planner"],
                "validation_status": metadata["validation_status"],
                "repairs": metadata["repairs"],
                "answer_regenerations": metadata["answer_regenerations"],
                "duration_ms": round((time.monotonic() - state["started_at"]) * 1000, 2),
            }
        )
        return {"metadata": metadata}

    def chat(
        self,
        message: str,
        *,
        session_id: str,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        result = self.graph.invoke(
            {
                "request_id": str(uuid.uuid4()),
                "session_id": session_id,
                "message": message,
                "browser_history": (history or [])[-12:],
                "db_session": self.session,
            }
        )
        return {
            "answer": result["answer"],
            "intent": result["plan"]["intent"],
            "metric": result.get("metric", {}).get("id"),
            "chart": result.get("chart"),
            "table": result.get("table"),
            "warnings": result.get("warnings", []),
            "validation": result.get("validation", {}),
            "metadata": result.get("metadata", {}),
        }


__all__ = ["AdvancedDoraDbAgent", "DoraDbQueryRejected"]
