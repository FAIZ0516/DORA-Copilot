"""Cached access to verified Jira database documentation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


KNOWLEDGE_PATH = Path(__file__).resolve().parent / "knowledge" / "jira_issues.md"
MAX_SECTION_CHARS = 2400
MAX_CONTEXT_CHARS = 7200


@dataclass(frozen=True)
class KnowledgeSection:
    title: str
    content: str


@lru_cache(maxsize=1)
def load_jira_knowledge() -> tuple[KnowledgeSection, ...]:
    """Load and split the verified Markdown once per backend process."""

    text = KNOWLEDGE_PATH.read_text(encoding="utf-8")
    matches = list(re.finditer(r"(?m)^(#{2,3})\s+(.+?)\s*$", text))
    sections: list[KnowledgeSection] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        if content:
            sections.append(
                KnowledgeSection(title=match.group(2).strip(), content=content)
            )
    if not sections:
        raise ValueError(f"No Markdown sections found in {KNOWLEDGE_PATH}")
    return tuple(sections)


def _question_terms(question: str) -> set[str]:
    return {
        term
        for term in re.findall(r"[a-z][a-z0-9_]{2,}", question.lower())
        if term
        not in {
            "what",
            "which",
            "where",
            "does",
            "this",
            "that",
            "table",
            "database",
            "have",
            "with",
            "from",
        }
    }


def select_knowledge_sections(
    question: str,
    *,
    limit: int = 4,
) -> list[KnowledgeSection]:
    """Return a bounded set of sections relevant to one question."""

    lowered = question.lower()
    terms = _question_terms(question)
    title_hints: set[str] = {"Instructions for AI Assistants"}
    if "lead time" in lowered or "cycle time" in lowered:
        title_hints.update(
            {
                "Lead Time for Changes",
                "`created` vs `updated` vs `resolved`",
                "Calculate average resolution time",
            }
        )
    if "story point" in lowered:
        title_hints.update({"Concepts not present", "Check whether story points exist"})
    if "squad" in lowered or "team" in lowered:
        title_hints.update({"Squad", "Project, team, and people"})
    if "status" in lowered or "resolution" in lowered:
        title_hints.update(
            {"Status and status category", "`status` vs `resolution`"}
        )
    if "jira" in lowered or "issue" in lowered:
        title_hints.update(
            {"What the Jira Issues Table Represents", "What One Row Represents"}
        )
    if "column" in lowered or "schema" in lowered or "table" in lowered:
        title_hints.update({"Table Location and Technical Details", "Data Dictionary"})

    ranked: list[tuple[int, int, KnowledgeSection]] = []
    for index, section in enumerate(load_jira_knowledge()):
        title_lower = section.title.lower()
        content_lower = section.content.lower()
        exact_hint = 20 if section.title in title_hints else 0
        term_score = sum(
            5 if term in title_lower else 1
            for term in terms
            if term in title_lower or term in content_lower
        )
        score = exact_hint + term_score
        if score:
            ranked.append((score, -index, section))

    ranked.sort(reverse=True)
    selected: list[KnowledgeSection] = []
    used_chars = 0
    for _, _, section in ranked:
        if len(selected) >= limit or used_chars >= MAX_CONTEXT_CHARS:
            break
        remaining = MAX_CONTEXT_CHARS - used_chars
        content = section.content[: min(MAX_SECTION_CHARS, remaining)].rstrip()
        selected.append(KnowledgeSection(section.title, content))
        used_chars += len(content)
    return selected


def format_knowledge_context(sections: list[KnowledgeSection]) -> str:
    return "\n\n".join(
        f"## {section.title}\n{section.content}" for section in sections
    )


def knowledge_fallback_answer(question: str) -> str:
    """Provide a verified answer when model synthesis is unavailable."""

    lowered = question.lower()
    if "lead time" in lowered or "cycle time" in lowered:
        return (
            "`public.tbl_gdt_dte_jira_issues` has `created` and `resolved`, so it "
            "can approximate calendar issue-resolution duration after excluding "
            "invalid intervals. That is not DORA Lead Time for Changes or engineering "
            "cycle time. Official DORA lead time requires verified code-change and "
            "production-deployment evidence. A field such as `ltc` elsewhere must be "
            "verified from schema metadata and its business definition before it is "
            "presented as standard DORA lead time."
        )
    if "story point" in lowered:
        return (
            "Story points are not available in the verified schema for "
            "`public.tbl_gdt_dte_jira_issues`. `progress_pct` is not story points, "
            "time spent, or an effort estimate and must not be used as a substitute."
        )
    if "status_category" in lowered or "status category" in lowered:
        return (
            "`status` is the detailed Jira workflow state. `status_category` is the "
            "broader Jira grouping (`To Do`, `In Progress`, or `Done`). A `Done` "
            "category is an end-state and can include cancelled or rejected work, so "
            "it does not by itself prove successful completion."
        )
    if "status" in lowered and "resolution" in lowered:
        return (
            "`status` describes where an issue is in the workflow; `resolution` "
            "describes how it ended. They are not interchangeable, and an issue in "
            "the `Done` category may have a resolution such as `Cancelled` or "
            "`Rejected`."
        )
    return (
        "`public.tbl_gdt_dte_jira_issues` is a PostgreSQL snapshot table where one "
        "row represents the current stored state of one Jira issue. It contains 26 "
        "verified columns covering identity, classification, current workflow, "
        "ownership, dates, planning relationships, and protected custom text. It is "
        "not a status-history, code-change, deployment, or incident dataset."
    )


__all__ = [
    "KnowledgeSection",
    "format_knowledge_context",
    "knowledge_fallback_answer",
    "load_jira_knowledge",
    "select_knowledge_sections",
]
