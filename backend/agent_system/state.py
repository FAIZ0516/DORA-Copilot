"""Typed state shared by every LangGraph node."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from sqlalchemy.orm import Session


PlanMode = Literal["data", "conversation", "clarification", "out_of_scope"]


class QueryAction(TypedDict):
    query_id: str
    filters: dict[str, Any]
    limit: int
    reason: str


class AgentPlan(TypedDict):
    mode: PlanMode
    intent: str
    confidence: float
    actions: list[QueryAction]
    reason: str
    clarification: str


class AgentState(TypedDict, total=False):
    request_id: str
    session_id: str
    message: str
    browser_history: list[dict[str, str]]
    memory: dict[str, Any]
    db_session: Session | None
    started_at: float
    planner_source: str
    plan: AgentPlan
    metric: dict[str, str]
    results: list[dict[str, Any]]
    validation: dict[str, Any]
    repair_count: int
    analysis: dict[str, Any]
    chart: dict[str, Any] | None
    table: dict[str, Any] | None
    answer: str
    answer_source: str
    answer_validation: dict[str, Any]
    answer_retry_count: int
    warnings: list[str]
    metadata: dict[str, Any]
