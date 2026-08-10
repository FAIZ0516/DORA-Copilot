"""Orchestration: the LangGraph node implementations for the governed
DoraDB agent (guide Section 9/11 -- planning/routing/analysis steps only).

``AgentOrchestrator`` is a mixin of node methods; it does not build the
graph or configure the model/provider -- that is ``agent_definition.py``,
which composes ``AdvancedDoraDbAgent(AgentOrchestrator)`` and wires these
methods into a ``StateGraph``. Final answer composition is not here either;
that is ``response/responder.py``, called from the ``_analyze``/``respond``
boundary via ``self.responder``.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from ..config import settings
from ..database.doradb import DoraDbConfigurationError, DoraDbQueryRejected
from ..knowledge_service import select_knowledge_sections
from ..memory.memory import memory_store
from ..memory.result_cache import (
    FOLLOW_UP_ON_EXISTING_RESULT,
    actions_from_cache,
    choose_cache_action,
    results_from_cache,
)
from ..services import (
    analyze_trend,
    build_chart_spec,
    classify_intent,
    compare_rows,
    detect_anomalies,
    message_mentions_metric,
    select_delivery_performance_metric,
    select_metric,
    select_metric_by_id,
)
from ..tools import execute_approved_query
from .audit import audit_log
from .controls.execution_control import ensure_within_deadline, public_policy
from .controls.response_controller import derive_policy
from .guardrails.input_guardrail import check_input
from .planner import create_plan
from .request_router import (
    ANALYSIS,
    CLARIFICATION_REQUIRED,
    DATABASE_METADATA,
    DATA_RETRIEVAL,
    KNOWLEDGE_EXPLANATION,
)
from .state import AgentState
from .validators import validate_answer, validate_results

logger = logging.getLogger(__name__)

JIRA_ROUTER_INTENTS = {
    DATABASE_METADATA,
    KNOWLEDGE_EXPLANATION,
    DATA_RETRIEVAL,
    ANALYSIS,
    CLARIFICATION_REQUIRED,
    FOLLOW_UP_ON_EXISTING_RESULT,
}

_ANALYTICAL_METRICS = {
    "release_frequency": "release_frequency_months",
    "change_failure_rate": "change_failure_rate_pct",
    "lead_time_for_change": "lead_time_for_change_months",
    "delivery_cycle_time": "delivery_cycle_time_months",
}


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


def _table_spec(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not results or not results[0].get("rows"):
        return None
    rows = results[0]["rows"][:50]
    preferred = [
        "table_schema",
        "table_name",
        "object_type",
        "column_name",
        "data_type",
        "dcpsquad",
        "missing_squad_rows",
        "issuetype",
        "status",
        "status_category",
        "issue_count",
        "oldest_created",
        "month",
        "created_bug_count",
        "resolved_bug_count",
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


class AgentOrchestrator:
    """Node implementations. Expects ``self.llm``, set by the subclass that

    configures the agent (``agent_definition.AdvancedDoraDbAgent``).
    """

    def _load_memory(self, state: AgentState) -> dict[str, Any]:
        volatile = memory_store.get(state["session_id"])
        persistent = state.get("persistent_context", {})
        memory = {
            **volatile,
            "last_context": persistent.get("last_context")
            or volatile.get("last_context", {}),
            "conversation_summary": persistent.get("conversation_summary", ""),
            "query_cache": persistent.get("query_cache", []),
            "workspace": persistent.get("workspace", "technical"),
            "project_scope": persistent.get("project_scope", {}),
        }
        context_reused = bool(
            memory.get("conversation_summary")
            or memory.get("query_cache")
            or memory.get("turns")
        )
        if context_reused and settings.app_env == "development":
            logger.info("CONTEXT_REUSED session_id=%s", state["session_id"])
        return {
            "memory": memory,
            "started_at": time.monotonic(),
            "repair_count": 0,
            "answer_retry_count": 0,
            "warnings": [],
            "context_reused": context_reused,
            "query_result_reused": False,
            "database_query_executed": False,
        }

    def _plan(self, state: AgentState) -> dict[str, Any]:
        # Explicit, traceable input-guardrail checkpoint (guide Section 17.1
        # / 47: "guardrail result" should be an inspectable event, not just
        # an implicit side effect of planning). This does not change
        # blocking behavior -- classify_intent()'s out_of_scope routing
        # below still owns that -- it makes the verdict observable.
        input_guardrail = check_input(state["message"])
        plan, source = create_plan(
            state["message"],
            memory=state["memory"],
            browser_history=state.get("browser_history", []),
            llm=self.llm,
        )
        model_source = getattr(self.llm, "source", "")
        model_planned = bool(model_source) and source == model_source
        decision = choose_cache_action(
            state["message"],
            memory=state["memory"],
            project_scope=state.get("project_scope", {}),
            semantic_follow_up=(
                plan["intent"] == FOLLOW_UP_ON_EXISTING_RESULT
                if model_planned
                else None
            ),
        )
        cached_results: list[dict[str, Any]] = []
        if decision.action == "reuse" and decision.entry:
            plan = {
                "mode": "data",
                "intent": FOLLOW_UP_ON_EXISTING_RESULT,
                "confidence": 1.0,
                "actions": [],
                "reason": "Answer from a fresh compatible conversation result.",
                "clarification": "",
            }
            source = "conversation-cache"
            cached_results = results_from_cache(decision.entry)
            if settings.app_env == "development":
                logger.info("QUERY_RESULT_REUSED session_id=%s", state["session_id"])
        elif decision.action == "refresh" and decision.entry:
            actions = actions_from_cache(decision.entry)
            if actions:
                plan = {
                    "mode": "data",
                    "intent": str(decision.entry.get("intent") or DATA_RETRIEVAL),
                    "confidence": 1.0,
                    "actions": actions,
                    "reason": "Refresh the previous approved query.",
                    "clarification": "",
                }
                source = "conversation-cache-refresh"
        elif plan["intent"] == FOLLOW_UP_ON_EXISTING_RESULT:
            # The model understood this as a follow-up, but the deterministic
            # cache compatibility checks found no safe reusable evidence.
            # Ask for clarification rather than answering from an empty cache
            # or silently selecting a keyword-based replacement query.
            plan = {
                **plan,
                "mode": "clarification",
                "intent": "model_plan_incomplete",
                "actions": [],
                "reason": "No compatible cached evidence is available.",
                "clarification": "",
            }
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
        sections = (
            select_knowledge_sections(state["message"])
            if plan["intent"] in JIRA_ROUTER_INTENTS
            else []
        )
        section_payload = [
            {"title": section.title, "content": section.content}
            for section in sections
        ]
        if settings.app_env == "development":
            logger.info(
                "request_route intent=%s knowledge_sections=%s",
                plan["intent"],
                [section.title for section in sections],
            )
        response_policy = derive_policy(
            state["message"],
            plan=plan,
            cache_reason=decision.reason,
            query_result_reused=bool(cached_results),
            results=cached_results,
        )
        return {
            "plan": plan,
            "planner_source": source,
            "metric": metric,
            "response_policy": response_policy,
            "input_guardrail": {
                "allowed": input_guardrail.allowed,
                "reason": input_guardrail.reason,
            },
            "knowledge_sections": section_payload,
            "evidence_sources": ["documentation"] if sections else [],
            "results": cached_results,
            "validation": (
                {
                    "valid": True,
                    "status": "reused",
                    "checks": ["conversation_cache"],
                    "warnings": [],
                }
                if cached_results else {}
            ),
            "query_result_reused": bool(cached_results),
            "cache_reason": decision.reason,
        }

    @staticmethod
    def _route_after_plan(state: AgentState) -> str:
        if state["plan"]["mode"] != "data":
            return "respond"
        return "analyze" if state.get("query_result_reused") else "execute"

    def _execute(self, state: AgentState) -> dict[str, Any]:
        ensure_within_deadline(state["started_at"])
        if state.get("db_session") is None:
            return {
                "results": [],
                "database_error": (
                    "DoraDB credentials are required for dataset analysis. "
                    "Configure DORADB_USER and DORADB_PASSWORD in .env."
                ),
                "database_query_executed": False,
            }
        try:
            results = [
                execute_approved_query(
                    state["db_session"],
                    query_id=action["query_id"],
                    filters=action["filters"],
                    limit=action["limit"],
                )
                for action in state["plan"]["actions"]
            ]
        except (DoraDbConfigurationError, DoraDbQueryRejected, SQLAlchemyError) as exc:
            # A database failure is not a code bug: let the graph continue to
            # `respond`, where the LLM composes an honest, guardrail-compliant
            # explanation instead of aborting the whole request with a raw
            # HTTP error the user never sees "thought through" at all.
            logger.warning("DoraDB query failed during execute: %s", exc)
            return {
                "results": [],
                "database_error": "The DoraDB database is temporarily unavailable.",
                "database_query_executed": False,
            }
        if settings.app_env == "development":
            logger.info("DATABASE_QUERY_EXECUTED session_id=%s", state["session_id"])
            for action, result in zip(state["plan"]["actions"], results):
                logger.info(
                    "approved_query intent=%s query_id=%s parameters=%s row_count=%s",
                    state["plan"]["intent"],
                    action["query_id"],
                    action["filters"],
                    result["row_count"],
                )
        evidence_kind = (
            "metadata"
            if state["plan"]["intent"] == DATABASE_METADATA
            else "live_data"
        )
        return {
            "results": results,
            "evidence_sources": list(
                dict.fromkeys([*state.get("evidence_sources", []), evidence_kind])
            ),
            "database_query_executed": True,
        }

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
            return {
                "results": [],
                "database_error": "DoraDB credentials are required for dataset analysis.",
                "repair_count": state.get("repair_count", 0) + 1,
            }
        try:
            repaired: list[dict[str, Any]] = [
                execute_approved_query(
                    state["db_session"],
                    query_id=action["query_id"],
                    filters=action["filters"],
                    limit=min(action["limit"], 100),
                )
                for action in state["plan"]["actions"]
            ]
        except (DoraDbConfigurationError, DoraDbQueryRejected, SQLAlchemyError) as exc:
            logger.warning("DoraDB query failed during repair: %s", exc)
            return {
                "results": [],
                "database_error": "The DoraDB database is temporarily unavailable.",
                "repair_count": state.get("repair_count", 0) + 1,
            }
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
            "knowledge_sections": state.get("knowledge_sections", []),
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
        # Refine the policy now that real query results and validation
        # warnings are known (the version from `_plan` only had cached or
        # empty results). This also decides table inclusion, replacing a
        # separate ad hoc "wants a table" check with one shared format signal.
        response_policy = derive_policy(
            state["message"],
            plan=state.get("plan", {}),
            cache_reason=state.get("cache_reason", ""),
            query_result_reused=bool(state.get("query_result_reused")),
            results=results,
            warnings=state.get("warnings", []),
        )
        return {
            "analysis": analysis,
            "chart": chart,
            "response_policy": response_policy,
            "table": (
                _table_spec(results) if response_policy["format"] == "table" else None
            ),
        }

    def _validate_answer(self, state: AgentState) -> dict[str, Any]:
        if state.get("answer_source") in {
            "ai-provider-unavailable",
            "live-data",
            "metadata",
            "verified-documentation",
        }:
            validation = {"valid": True, "unsupported_numbers": [], "warning_missing": False}
        elif state.get("database_error"):
            # There is no query evidence to check numbers against by
            # definition -- the query never ran. Evidence-grounding
            # validation doesn't apply here.
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
            "response_policy": state.get("response_policy", {}),
            "input_guardrail": state.get("input_guardrail", {}),
            "database_error": state.get("database_error", ""),
            "evidence_sources": state.get("evidence_sources", []),
            "knowledge_sections": [
                item["title"] for item in state.get("knowledge_sections", [])
            ],
            "context_reused": bool(state.get("context_reused")),
            "query_result_reused": bool(state.get("query_result_reused")),
            "database_query_executed": bool(state.get("database_query_executed")),
            "cache_reason": state.get("cache_reason", ""),
        }
        prior_context = state.get("memory", {}).get("last_context", {})
        next_context = (
            {
                "intent": state["plan"]["intent"],
                "metric": state.get("metric", {}).get("id"),
                "filters": filters,
                "query_ids": query_ids,
                "warnings": state.get("warnings", []),
            }
            if (
                state["plan"]["mode"] in {"data", "clarification"}
                and not state.get("database_error")
            )
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
                "evidence_sources": metadata["evidence_sources"],
                "knowledge_sections": metadata["knowledge_sections"],
                "duration_ms": round((time.monotonic() - state["started_at"]) * 1000, 2),
            }
        )
        persistence = {
            "last_context": next_context,
            "results": results,
            "intent": state["plan"]["intent"],
            "query_result_reused": bool(state.get("query_result_reused")),
        }
        return {"metadata": metadata, "persistence": persistence}


__all__ = ["AgentOrchestrator", "_is_holistic_request"]
