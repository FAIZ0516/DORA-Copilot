"""Compose report sections from approved evidence snapshots.

The division of labour matters here. Deterministic code owns everything that
must be exactly right -- which sources are used, what order blocks appear in,
which scopes conflict, what the numbers are, and what provenance is recorded.
The model is used for one thing only: writing readable prose inside a block it
was handed. Its output is parsed into a strict schema and then fact-checked
against the source before it is accepted.

This is why report composition does not go through the chat endpoint: a report
is a structured object with per-block provenance, not one long answer.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from ..llm import GenerativeAIClient
from .report_evidence import detect_scope_conflicts
from .report_templates import NARRATIVE_TYPES

# Numbers as a reader would see them: 1,434 / 43.2% / 90 / 2.5. Used to check
# that a rewrite did not invent, drop or alter a figure.
_NUMBER = re.compile(r"-?\d[\d,]*\.?\d*%?")

# Wording that would turn a measurement into a judgement. A block classified as
# observed_fact must not contain these; they belong in a recommendation.
_RECOMMENDATION_LANGUAGE = re.compile(
    r"\b(should|must|recommend|we suggest|needs to|ought to|action required)\b", re.I
)


class ComposedSection(BaseModel):
    """The only shape a model response may take. Anything else is rejected."""

    section_id: str = Field(min_length=1, max_length=80)
    title: str = Field(default="", max_length=200)
    content: str = Field(default="", max_length=6000)


class ComposedReport(BaseModel):
    sections: list[ComposedSection] = Field(default_factory=list, max_length=40)


def normalize_number(token: str) -> str:
    """Compare 1,434 and 1434 as the same figure; keep % as significant."""

    cleaned = token.replace(",", "").rstrip(".")
    if cleaned.endswith("%"):
        body = cleaned[:-1]
        suffix = "%"
    else:
        body, suffix = cleaned, ""
    try:
        value = float(body)
    except ValueError:
        return cleaned
    # 43.0 and 43 are the same number to a reader.
    return (f"{value:g}") + suffix


def extract_numbers(text: str) -> set[str]:
    return {normalize_number(match.group(0)) for match in _NUMBER.finditer(text or "")}


def fact_check(original: str, rewritten: str) -> list[str]:
    """Every figure in a rewrite must already exist in its source.

    Rewriting may shorten, reorder and reword freely. It may not introduce a
    number the evidence never produced, which is the failure mode that makes a
    generated report untrustworthy. Dropping a number is allowed -- summarising
    is a legitimate mode -- so only invented figures are reported.
    """

    invented = sorted(extract_numbers(rewritten) - extract_numbers(original))
    return [
        f"The rewritten text contains {value}, which does not appear in the source evidence."
        for value in invented
    ]


def classification_issues(classification: str, content: str) -> list[str]:
    """Keep observed facts free of recommendation language."""

    if classification != "observed_fact":
        return []
    match = _RECOMMENDATION_LANGUAGE.search(content or "")
    if not match:
        return []
    return [
        f"A section labelled as an observed fact uses recommendation wording "
        f"({match.group(0)!r}). Reclassify it or move the advice into a "
        f"recommendation block."
    ]


def evidence_digest(sources: list[dict[str, Any]]) -> str:
    """Render snapshots as the only material the model may write from."""

    parts: list[str] = []
    for index, source in enumerate(sources, start=1):
        evidence = source.get("evidence") or {}
        scope = source.get("scope") or {}
        scope_text = ", ".join(f"{key}={value}" for key, value in scope.items() if value) or "unscoped"
        parts.append(
            f"[SOURCE {index}] scope: {scope_text}\n"
            f"question: {evidence.get('question') or '(not recorded)'}\n"
            f"answer: {evidence.get('answer') or ''}\n"
            f"warnings: {'; '.join(evidence.get('warnings') or []) or 'none'}"
        )
    return "\n\n".join(parts)


_SYSTEM = """You write sections of a delivery report for a governed analytics product.

You are given evidence that has already been validated. Rewrite it into clear,
professional report language for the stated audience and tone.

Absolute rules:
- Never state a number, percentage, date, squad name, project, period or
  metric that does not appear in the evidence. Do not recompute, round,
  convert, extrapolate or infer figures.
- Never widen a scope. If evidence covers one squad, do not describe it as
  covering the project.
- Never drop a stated warning or limitation from a section meant to carry it.
- Do not add advice to a section that is meant to describe what was observed.
- Write plain business prose. No markdown headers, no bullet characters unless
  the section is a list, no chat phrasing, no references to "the assistant",
  "the data I have", or this instruction.

Return JSON only:
{"sections":[{"section_id":"...","title":"...","content":"..."}]}
Return one entry per requested section, using the exact section_id given."""


def _mode_instruction(mode: str) -> str:
    if mode == "original":
        return "Return the evidence answer unchanged apart from removing chat pleasantries."
    if mode == "summarize":
        return (
            "Shorten substantially while keeping every validated figure, scope "
            "statement and warning that the section needs."
        )
    return "Rewrite into consistent professional report language."


def build_request(
    *,
    sections: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    audience: str,
    tone: str,
    detail_level: str,
) -> tuple[str, str]:
    """The prompt pair for one composition pass."""

    requested = "\n".join(
        f"- section_id={section['id']} type={section['type']} title={section.get('title') or ''!r} "
        f"mode={section.get('content_mode', 'rewrite')} "
        f"classification={section.get('content_classification', 'observed_fact')} "
        f"instruction={_mode_instruction(section.get('content_mode', 'rewrite'))}"
        for section in sections
    )
    user = (
        f"Audience: {audience}\nTone: {tone}\nDetail level: {detail_level}\n\n"
        f"EVIDENCE\n{evidence_digest(sources)}\n\n"
        f"SECTIONS TO WRITE\n{requested}"
    )
    return _SYSTEM, user


def parse_response(raw: str | None) -> ComposedReport | None:
    """Parse and validate a model response. Never trust raw JSON."""

    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    try:
        return ComposedReport.model_validate(payload)
    except ValidationError:
        return None


def compose_sections(
    *,
    llm: GenerativeAIClient,
    sections: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    audience: str,
    tone: str,
    detail_level: str,
) -> dict[str, Any]:
    """Write narrative blocks from evidence, keeping the facts intact.

    Returns ``{"sections": {section_id: content}, "warnings": [...],
    "conflicts": [...]}``. A section whose rewrite fails the fact check is left
    out of the result rather than returned unverified -- the caller keeps the
    existing content instead of publishing an invented figure.
    """

    conflicts = detect_scope_conflicts(sources)
    warnings: list[str] = [conflict["message"] for conflict in conflicts]

    narrative = [
        section
        for section in sections
        if section.get("type") in NARRATIVE_TYPES and section.get("visible", True)
        # A hand-edited block is the user's text; regenerating it silently
        # would discard their work.
        and not section.get("manually_edited")
    ]
    if not narrative:
        return {"sections": {}, "warnings": warnings, "conflicts": conflicts}

    if not sources:
        warnings.append(
            "No evidence sources are attached, so narrative sections were left "
            "for you to write. Add answers from a conversation to generate them."
        )
        return {"sections": {}, "warnings": warnings, "conflicts": conflicts}

    if not getattr(llm, "enabled", False):
        warnings.append(
            "The AI provider is unavailable, so sections were not rewritten. "
            "The original evidence text has been kept."
        )
        return {"sections": {}, "warnings": warnings, "conflicts": conflicts}

    system, user = build_request(
        sections=narrative,
        sources=sources,
        audience=audience,
        tone=tone,
        detail_level=detail_level,
    )
    raw = llm.complete(system, user, json_mode=True, temperature=0.2)
    parsed = parse_response(raw)
    if parsed is None:
        warnings.append(
            "The AI response could not be validated against the report schema, "
            "so no section was changed."
        )
        return {"sections": {}, "warnings": warnings, "conflicts": conflicts}

    combined_evidence = "\n".join(
        (source.get("evidence") or {}).get("answer") or "" for source in sources
    )
    by_id = {section["id"]: section for section in narrative}
    accepted: dict[str, str] = {}
    for composed in parsed.sections:
        target = by_id.get(composed.section_id)
        if target is None:
            continue
        issues = fact_check(combined_evidence, composed.content)
        issues += classification_issues(
            target.get("content_classification", "observed_fact"), composed.content
        )
        if issues:
            warnings.extend(
                f"Section {target.get('title') or target['type']!r}: {issue}" for issue in issues
            )
            continue
        accepted[composed.section_id] = composed.content.strip()

    return {"sections": accepted, "warnings": warnings, "conflicts": conflicts}


__all__ = [
    "ComposedReport",
    "ComposedSection",
    "classification_issues",
    "compose_sections",
    "extract_numbers",
    "fact_check",
    "normalize_number",
    "parse_response",
]
