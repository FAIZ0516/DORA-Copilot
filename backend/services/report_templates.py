"""Report templates and the block vocabulary reports are built from.

Deterministic on purpose (AGENTS.md section 4: business logic lives in
``backend/services/``). A template decides which blocks exist and in what
order; the model is never asked to invent report structure, only to write the
narrative inside a block it was given.
"""

from __future__ import annotations

from typing import Any

# Every block type a report may contain. Anything outside this set is rejected
# before it reaches the database, so a bad model response or a crafted request
# cannot introduce an unknown block the exporters do not know how to render.
SECTION_TYPES = (
    "cover",
    "metadata",
    "executive_summary",
    "rich_text",
    "kpi_group",
    "key_finding",
    "chart",
    "data_table",
    "risk",
    "recommendation",
    "action_list",
    "data_quality",
    "scope_limitation",
    "methodology",
    "page_break",
)

# Blocks whose wording may be model-generated. Everything else is either
# structured data (chart/table/KPI) or deterministic text the code owns.
NARRATIVE_TYPES = frozenset(
    {
        "executive_summary",
        "rich_text",
        "key_finding",
        "risk",
        "recommendation",
        "action_list",
    }
)

# How a section's content came to exist. Drives the label a reader sees, so a
# recommendation is never mistaken for a measured fact.
CLASSIFICATIONS = ("observed_fact", "interpretation", "recommendation", "user_authored")

# What the user chose to do with selected chat content.
CONTENT_MODES = ("original", "summarize", "rewrite")

AUDIENCES = (
    "senior_leadership",
    "delivery_manager",
    "product_owner",
    "engineering_team",
    "technical_stakeholder",
)

TONES = ("executive", "professional", "concise", "detailed", "technical")

DETAIL_LEVELS = ("brief", "standard", "comprehensive")

STATUSES = ("draft", "ready", "exported", "needs_review", "stale")

# Which parts of an assistant answer a user may pull into a report.
SELECTIONS = ("full", "narrative", "chart", "table", "recommendations", "warnings")


def _section(type_: str, title: str, **extra: Any) -> dict[str, Any]:
    return {"type": type_, "title": title, **extra}


# A template is an ordered list of blocks. Narrative blocks start empty and are
# filled by composition; structural blocks (cover, methodology) are rendered
# deterministically from the report's own scope and provenance.
TEMPLATES: dict[str, dict[str, Any]] = {
    "blank": {
        "label": "Blank report",
        "description": "Start with only a cover and build the report yourself.",
        "default_title": "New report",
        "sections": [_section("cover", "")],
    },
    "executive_summary": {
        "label": "Executive Summary",
        "description": "A short leadership briefing: position, risks, and what to decide.",
        "default_title": "Executive Summary",
        "default_audience": "senior_leadership",
        "default_tone": "executive",
        "sections": [
            _section("cover", ""),
            _section("executive_summary", "Executive Summary"),
            _section("kpi_group", "Key Measures"),
            _section("key_finding", "What The Data Shows"),
            _section("risk", "Risks Requiring Attention"),
            _section("recommendation", "Recommended Actions"),
            _section("data_quality", "Data Quality and Limitations"),
            _section("methodology", "Evidence and Methodology"),
        ],
    },
    "sprint_performance": {
        "label": "Sprint Performance Report",
        "description": "Delivery position for a squad or sprint, with supporting evidence.",
        "default_title": "Sprint Performance Report",
        "default_audience": "delivery_manager",
        "default_tone": "professional",
        "sections": [
            _section("cover", ""),
            _section("executive_summary", "Summary"),
            _section("kpi_group", "Delivery Position"),
            _section("chart", "Work Status Distribution"),
            _section("key_finding", "Analysis"),
            _section("data_table", "Supporting Detail"),
            _section("risk", "Delivery Risks"),
            _section("recommendation", "Recommended Actions"),
            _section("data_quality", "Data Quality and Limitations"),
            _section("methodology", "Evidence and Methodology"),
        ],
    },
    "risk_and_action": {
        "label": "Risk and Action Report",
        "description": "Attention areas with evidence, severity, and owners.",
        "default_title": "Risk and Action Report",
        "default_audience": "delivery_manager",
        "default_tone": "professional",
        "sections": [
            _section("cover", ""),
            _section("executive_summary", "Summary"),
            _section("risk", "Risks Requiring Attention"),
            _section("chart", "Supporting Evidence"),
            _section("action_list", "Actions"),
            _section("data_quality", "Data Quality and Limitations"),
            _section("methodology", "Evidence and Methodology"),
        ],
    },
    "weekly_management_update": {
        "label": "Weekly Management Update",
        "description": "A short recurring update: what moved, what is blocked, what is next.",
        "default_title": "Weekly Management Update",
        "default_audience": "senior_leadership",
        "default_tone": "concise",
        "sections": [
            _section("cover", ""),
            _section("executive_summary", "This Week"),
            _section("kpi_group", "Key Measures"),
            _section("key_finding", "What Changed"),
            _section("action_list", "Next Steps"),
            _section("methodology", "Evidence and Methodology"),
        ],
    },
    "dora_performance": {
        "label": "DORA Performance Report",
        "description": "Release frequency, change failure rate, lead time and cycle time.",
        "default_title": "DORA Performance Report",
        "default_audience": "technical_stakeholder",
        "default_tone": "technical",
        "sections": [
            _section("cover", ""),
            _section("executive_summary", "Summary"),
            _section("kpi_group", "DORA Measures"),
            _section("chart", "Delivery Trend"),
            _section("key_finding", "Interpretation"),
            _section("data_table", "Measures by Period"),
            _section("scope_limitation", "What These Measures Do and Do Not Show"),
            _section("data_quality", "Data Quality and Limitations"),
            _section("methodology", "Evidence and Methodology"),
        ],
    },
}

TEMPLATE_IDS = tuple(TEMPLATES)


def template_catalogue() -> list[dict[str, Any]]:
    """Template metadata for the picker. No section bodies -- just choices."""

    return [
        {
            "id": key,
            "label": value["label"],
            "description": value["description"],
            "default_title": value["default_title"],
            "default_audience": value.get("default_audience", "delivery_manager"),
            "default_tone": value.get("default_tone", "professional"),
            "section_count": len(value["sections"]),
        }
        for key, value in TEMPLATES.items()
    ]


def sections_for_template(template: str) -> list[dict[str, Any]]:
    """Ordered starting blocks for a template, positioned and classified."""

    definition = TEMPLATES.get(template) or TEMPLATES["blank"]
    sections: list[dict[str, Any]] = []
    for index, section in enumerate(definition["sections"], start=1):
        type_ = section["type"]
        sections.append(
            {
                "type": type_,
                "title": section.get("title", ""),
                "content": "",
                "payload": None,
                "position": index,
                "visible": True,
                "content_mode": "rewrite",
                # A recommendation block is a recommendation even before it has
                # text, so an empty template can never be mislabelled as fact.
                "content_classification": _default_classification(type_),
                "manually_edited": False,
                "needs_review": False,
                "source_ids": [],
            }
        )
    return sections


def _default_classification(type_: str) -> str:
    if type_ in {"recommendation", "action_list"}:
        return "recommendation"
    if type_ in {"key_finding", "executive_summary", "risk"}:
        return "interpretation"
    return "observed_fact"


def default_title(template: str) -> str:
    return (TEMPLATES.get(template) or TEMPLATES["blank"])["default_title"]


__all__ = [
    "AUDIENCES",
    "CLASSIFICATIONS",
    "CONTENT_MODES",
    "DETAIL_LEVELS",
    "NARRATIVE_TYPES",
    "SECTION_TYPES",
    "SELECTIONS",
    "STATUSES",
    "TEMPLATES",
    "TEMPLATE_IDS",
    "TONES",
    "default_title",
    "sections_for_template",
    "template_catalogue",
]
