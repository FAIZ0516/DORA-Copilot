"""Turn a stored assistant message into an approved evidence snapshot.

Two responsibilities, both deterministic:

* **Snapshot** -- copy the provenance a report is allowed to keep out of a
  conversation message, and nothing else. The snapshot is a copy rather than a
  live reference so a report stays reproducible after the conversation is
  archived or its presentation changes.
* **Compare scopes** -- decide whether two snapshots describe the same slice of
  data. Combining "TITAN squad" evidence with "all squads" evidence into one
  paragraph would silently misstate both, so conflicts surface instead.

Restricted fields are stripped with the existing output guardrail rather than
a second list maintained here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..agent.guardrails.output_guardrail import strip_sensitive_fields

# The only provenance a report may carry. Anything not named here -- prompts,
# planner reasoning, credentials, raw SQL, internal errors -- never leaves the
# conversation record.
APPROVED_EVIDENCE_FIELDS = (
    "question",
    "answer",
    "chart",
    "table",
    "warnings",
    "validation",
    "query_ids",
    "row_counts",
    "knowledge_sections",
    "intent",
    "answer_source",
    "generated_at",
)

# Scope keys compared when deciding whether two sources can be merged.
SCOPE_KEYS = ("project", "squad", "sprint", "release", "date_from", "date_to")

_SCOPE_LABELS = {
    "project": "project",
    "squad": "squad",
    "sprint": "sprint",
    "release": "release",
    "date_from": "start date",
    "date_to": "end date",
}


def _clean(value: Any) -> Any:
    """Drop restricted keys from any nested structure before it is stored."""

    if isinstance(value, (dict, list)):
        return strip_sensitive_fields(value)
    return value


def snapshot_from_message(
    *,
    question: str | None,
    answer: str,
    structured_content: dict[str, Any] | None,
    selection: str = "full",
) -> dict[str, Any]:
    """Build the immutable evidence snapshot for one selected message."""

    structured = structured_content or {}
    metadata = structured.get("metadata") or {}
    snapshot: dict[str, Any] = {
        "question": (question or "").strip()[:2000],
        "answer": (answer or "").strip(),
        "chart": _clean(structured.get("chart")),
        "table": _clean(structured.get("table")),
        "warnings": list(structured.get("warnings") or []),
        "validation": _clean(structured.get("validation") or {}),
        "query_ids": list(
            structured.get("query_identifiers") or metadata.get("query_ids") or []
        ),
        "row_counts": list(structured.get("row_counts") or metadata.get("row_counts") or []),
        "knowledge_sections": list(
            structured.get("knowledge_sections") or metadata.get("knowledge_sections") or []
        ),
        "intent": structured.get("detected_intent") or metadata.get("intent"),
        "answer_source": structured.get("source_type") or metadata.get("answer_source"),
        "selection": selection,
    }

    # A selection narrows what the section will render, but the full snapshot is
    # still retained so the user can widen the selection later without having to
    # re-run the original question.
    if selection == "narrative":
        snapshot["chart"] = None
        snapshot["table"] = None
    elif selection == "chart":
        snapshot["table"] = None
    elif selection == "table":
        snapshot["chart"] = None

    return snapshot


def scope_from_message(structured_content: dict[str, Any] | None) -> dict[str, Any]:
    """Extract the data slice a message describes, for conflict detection."""

    structured = structured_content or {}
    metadata = structured.get("metadata") or {}
    dashboard = metadata.get("dashboard_context") or {}
    project_scope = metadata.get("project_scope") or {}
    return {
        "project": dashboard.get("project") or project_scope.get("project_key"),
        "squad": dashboard.get("squad"),
        "sprint": dashboard.get("sprint"),
        "release": dashboard.get("release"),
        "date_from": dashboard.get("date_from"),
        "date_to": dashboard.get("date_to"),
    }


def evidence_timestamp(structured_content: dict[str, Any] | None) -> datetime | None:
    """When the evidence behind a message was retrieved."""

    metadata = (structured_content or {}).get("metadata") or {}
    raw = metadata.get("generated_at") or metadata.get("data_as_of")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _describe(value: Any) -> str:
    return str(value) if value not in (None, "") else "all"


def detect_scope_conflicts(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Report every scope dimension where selected sources disagree.

    Sources are dicts with ``id``, ``label`` and ``scope``. A dimension is only
    a conflict when two sources give it *different concrete* values -- one
    source scoped to a squad and another left unscoped is a widening, reported
    separately so the user can decide, not silently merged either way.
    """

    conflicts: list[dict[str, Any]] = []
    if len(sources) < 2:
        return conflicts

    for key in SCOPE_KEYS:
        seen: dict[str, list[str]] = {}
        for source in sources:
            value = (source.get("scope") or {}).get(key)
            seen.setdefault(_describe(value), []).append(str(source.get("label") or source.get("id")))
        if len(seen) < 2:
            continue
        concrete = [value for value in seen if value != "all"]
        label = _SCOPE_LABELS[key]
        if len(concrete) >= 2:
            conflicts.append(
                {
                    "field": key,
                    "severity": "conflict",
                    "values": seen,
                    "message": (
                        f"Sources cover different values for {label}: "
                        + "; ".join(
                            f"{value} ({', '.join(names)})" for value, names in seen.items()
                        )
                        + ". Combining them into one statement would misstate both."
                    ),
                }
            )
        else:
            conflicts.append(
                {
                    "field": key,
                    "severity": "widening",
                    "values": seen,
                    "message": (
                        f"One source is limited to {label} {concrete[0]} while another "
                        "covers all values. Keep them as separately labelled sections "
                        "or narrow the report scope."
                    ),
                }
            )
    return conflicts


def staleness(
    data_as_of: datetime | None, *, now: datetime | None = None, threshold_hours: int = 24
) -> dict[str, Any]:
    """Describe how old a report's evidence is."""

    current = now or datetime.now(timezone.utc)
    if data_as_of is None:
        return {"stale": False, "age_hours": None, "reason": "No retrieval time was recorded."}
    reference = data_as_of if data_as_of.tzinfo else data_as_of.replace(tzinfo=timezone.utc)
    age = (current - reference).total_seconds() / 3600
    return {
        "stale": age >= threshold_hours,
        "age_hours": round(age, 1),
        "reason": (
            f"Evidence was retrieved {round(age)} hours ago."
            if age >= threshold_hours
            else "Evidence is current."
        ),
    }


def spread_hours(timestamps: list[datetime]) -> float:
    """Hours between the oldest and newest evidence in one report."""

    stamps = [t if t.tzinfo else t.replace(tzinfo=timezone.utc) for t in timestamps if t]
    if len(stamps) < 2:
        return 0.0
    return round((max(stamps) - min(stamps)).total_seconds() / 3600, 1)


__all__ = [
    "APPROVED_EVIDENCE_FIELDS",
    "SCOPE_KEYS",
    "detect_scope_conflicts",
    "evidence_timestamp",
    "scope_from_message",
    "snapshot_from_message",
    "spread_hours",
    "staleness",
]
