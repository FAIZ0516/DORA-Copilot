"""Answer a template's standard questions from live data.

This is what makes a template reproducible: the questions are fixed, so the
same report run next week asks exactly the same things and reports whatever the
database says then. The answers are produced by the existing governed agent --
the same approved queries, guardrails and validation as any chat answer -- so a
generated report carries real provenance rather than model prose.

No planner, validator or query catalogue is duplicated here. This module only
sequences existing pieces.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def scope_to_question(question: str, scope: dict[str, Any]) -> str:
    """Bind a template question to the report's scope.

    A template question is written generically ("Show the current delivery
    position"), but a report is always about a specific slice. Naming the slice
    in the question is what stops the assistant asking which squad was meant --
    the same fix applied to the dashboard's Ask Zara buttons.
    """

    parts = [f"squad {scope['squad']}" if scope.get("squad") else "all squads"]
    if scope.get("sprint"):
        parts.append(f"sprint {scope['sprint']}")
    if scope.get("release"):
        parts.append(f"release {scope['release']}")
    where = f"{', '.join(parts)} in {scope.get('project') or 'DCPM'}"
    if scope.get("date_from") or scope.get("date_to"):
        where += f", between {scope.get('date_from') or 'the earliest data'} and {scope.get('date_to') or 'today'}"
    return f"For {where}: {question}"


def dashboard_context_for(scope: dict[str, Any]) -> dict[str, Any]:
    """The structured scope the agent expects alongside the question."""

    context = {
        "project": scope.get("project") or "DCPM",
        "squad": scope.get("squad") or None,
        "sprint": scope.get("sprint") or None,
        "release": scope.get("release") or None,
        "date_from": scope.get("date_from") or None,
        "date_to": scope.get("date_to") or None,
    }
    return {key: value for key, value in context.items() if value}


def run_template_questions(
    *,
    agent_factory,
    questions: list[str],
    scope: dict[str, Any],
    session_id: str,
) -> list[dict[str, Any]]:
    """Ask each question and return its answer plus structured evidence.

    One failed question does not fail the report: it is recorded and skipped,
    because a partial report with honest gaps is more useful than none.
    """

    results: list[dict[str, Any]] = []
    dashboard_context = dashboard_context_for(scope)
    project = scope.get("project") or "DCPM"

    for index, question in enumerate(questions):
        grounded = scope_to_question(question, scope)
        try:
            agent = agent_factory()
            answer = agent.chat(
                grounded,
                session_id=f"{session_id}-{index}",
                persistent_context={
                    "dashboard_context": dashboard_context,
                    "last_context": {
                        "filters": {
                            key: value
                            for key, value in (
                                ("dcpsquad", scope.get("squad")),
                                ("project_key", project),
                            )
                            if value
                        },
                        "dashboard_context": dashboard_context,
                    },
                },
                project_scope={"project_key": project},
            )
        except Exception as exc:  # noqa: BLE001 - one question must not sink the report
            logger.warning("Report question failed (%s): %s", question, exc)
            results.append({"question": grounded, "error": str(exc)[:200]})
            continue

        metadata = answer.get("metadata") or {}
        results.append(
            {
                "question": grounded,
                "answer": answer.get("answer") or "",
                # Shaped like a stored conversation message so the same
                # snapshot code handles chat-sourced and generated evidence.
                "structured_content": {
                    "chart": answer.get("chart"),
                    "table": answer.get("table"),
                    "warnings": answer.get("warnings") or [],
                    "validation": answer.get("validation") or {},
                    "query_identifiers": metadata.get("query_ids") or [],
                    "row_counts": metadata.get("row_counts") or [],
                    "knowledge_sections": metadata.get("knowledge_sections") or [],
                    "detected_intent": answer.get("intent"),
                    "source_type": metadata.get("answer_source"),
                    "metadata": {
                        "dashboard_context": dashboard_context,
                        "project_scope": {"project_key": project},
                        "generated_at": metadata.get("generated_at"),
                    },
                },
            }
        )
    return results


__all__ = ["dashboard_context_for", "run_template_questions", "scope_to_question"]
