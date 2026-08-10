"""Runtime skill registry: discovers, matches, and loads domain skill playbooks.

Guide reference: AI_AGENT_PROJECT_RESTRUCTURING_GUIDE.md Section 13. A custom
skill_registry/skill_loader is justified here because the runtime must (a)
discover local skills, (b) map a user message to zero or more matching
skills, and (c) selectively load a skill's full ``SKILL.md`` body only when
it is actually relevant to the current turn -- the framework in use here (a
plain chat-completions call to DeepSeek) has no native equivalent, so this
has to be application code, not prompt text.

Each skill lives at ``backend/agent/skills/<name>/SKILL.md`` with a required
frontmatter (``name``, ``description``) followed by an instruction body.
There is deliberately no ``handler.py`` anywhere here: every skill is
instruction-only (guide Section 12), so "loading" a skill means reading its
markdown body and handing it to the model for this turn, not executing code.

Before this module existed, ``orchestrator.py`` scanned these files but only
ever extracted the two frontmatter fields into a name+description catalogue
-- the detailed body (query IDs, interpretation rules, response templates,
common mistakes) was read from disk and then discarded, so it never actually
reached the model despite ``INSTRUCTIONS.md`` Section 2 telling the model to
"load and follow" the matching skill. ``match_skills``/``load_skill_playbooks``
close that gap deterministically, mirroring the same category table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent / "skills"

# Ordered most-specific-first so a message that could plausibly match
# several skills (e.g. a squad+DORA question matches both dora-by-squad and
# dora-overview) reports the more specific one first, then is capped by
# `limit` in match_skills/load_skill_playbooks.
#
# Patterns are hand-tuned from each skill's own frontmatter `description:`
# trigger phrases (see INSTRUCTIONS.md Section 2's table) -- not derived
# from free text at runtime -- so matching stays precise and testable.
_TRIGGERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("count-issues", re.compile(
        r"\bhow many (?:issues?|bugs?|stor(?:y|ies)|tasks?|features?)\b|"
        r"\bcount (?:of )?(?:issues?|bugs?|stor(?:y|ies)|tasks?|features?)\b",
        re.I,
    )),
    ("check-impeded", re.compile(r"\b(?:blocked|impeded|stuck|held up)\b", re.I)),
    ("ageing-analysis", re.compile(
        r"\bageing\b|\baging\b|\bstale work\b|\bold issues?\b|"
        r"\bhow long (?:has|have)\b.{0,20}\b(?:open|unresolved)\b|\bbeen open\b",
        re.I,
    )),
    ("bug-trend", re.compile(
        r"\bbug trends?\b|\bare bugs increasing\b|\bbug resolution rate\b|\bbug backlog\b",
        re.I,
    )),
    ("analyze-open-work", re.compile(
        r"\bopen work\b|\bpending work\b|\bunresolved work\b|\bwhat'?s not done\b",
        re.I,
    )),
    ("backlog-status", re.compile(r"\bbacklog\b", re.I)),
    ("data-quality", re.compile(
        r"\bdata quality\b|\bmissing data\b|\bhow clean is the data\b|\bdata problems?\b",
        re.I,
    )),
    ("dora-by-squad", re.compile(
        r"\bsquad performance\b|\bteam dora metrics?\b|\bwhich (?:team|squad) is performing\b|"
        r"\bdora\b.{0,15}\b(?:by|per) squad\b|\bsquad\b.{0,15}\bdora\b",
        re.I,
    )),
    ("dora-release-detail", re.compile(
        r"\brelease details?\b|\bper.release metrics?\b|\bhow did release\b", re.I,
    )),
    ("dora-vs-jira", re.compile(
        r"\bis this (?:official )?dora\b|\bare these official metrics?\b|\bdora vs\.? jira\b|"
        r"\bofficial dora\b",
        re.I,
    )),
    ("dora-overview", re.compile(
        r"\bdora metrics?\b|\bdelivery performance\b|\brelease frequency\b|\blead time\b|"
        r"\bchange failure rate\b",
        re.I,
    )),
    ("feature-story-ratio", re.compile(
        r"\bfeature story ratio\b|\bfeature breakdown\b|"
        r"\b(?:story to feature|feature to story)\b|"
        r"\buser stor(?:y|ies)\b.{0,15}\bratio\b",
        re.I,
    )),
    ("find-squad", re.compile(
        r"\bwhich squads exist\b|\bsquad list\b|\bteams with data\b|\bwhich squads have data\b",
        re.I,
    )),
    ("list-values", re.compile(
        r"\bwhat values exist\b|\blist all\b|\bshow me available\b|"
        r"\bwhat (?:squads?|releases?|years?|types?|statuses)\b.{0,20}\bexist\b",
        re.I,
    )),
    ("explain-limitations", re.compile(
        r"\bnot tell (?:me|us|you)\b|\bcan'?t\b.{0,20}\btell\b|"
        r"\blimitations?\b|\bwhat'?s missing\b|\bknown gaps?\b",
        re.I,
    )),
    ("explain-status", re.compile(
        r"\bwhat does status\b|\bexplain the workflow\b|\bstatus categor(?:y|ies)\b|\bstatus values?\b",
        re.I,
    )),
    ("explain-table", re.compile(
        r"\bwhat columns exist\b|\bwhat does this table have\b|\btable structure\b", re.I,
    )),
    ("explore-schema", re.compile(
        r"\bwhat tables exist\b|\bshow database structure\b|\bwhat'?s in the database\b|"
        r"\bdatabase schema\b",
        re.I,
    )),
    ("safe-reporting", re.compile(
        r"\bbuild a report\b|\bsummari[sz]e\b|\bcreate a summary\b|\bsummary for leadership\b|"
        r"\bgive me an overview\b",
        re.I,
    )),
)


@dataclass(frozen=True)
class SkillDoc:
    name: str
    description: str
    body: str  # full SKILL.md content, including its frontmatter block


def _parse_frontmatter(content: str) -> tuple[str, str]:
    name, description = "", ""
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("name:"):
            name = stripped.removeprefix("name:").strip()
        elif stripped.startswith("description:"):
            description = stripped.removeprefix("description:").strip()
        if name and description:
            break
    return name, description


def discover_skills() -> dict[str, SkillDoc]:
    """Scan backend/agent/skills/ fresh on every call.

    Not cached: INSTRUCTIONS.md and every SKILL.md are read live so edits
    take effect on the next request without a restart, matching the existing
    behavior of the rest of the runtime instruction loading in this package.
    19 small files is cheap enough to re-read per turn.
    """

    skills: dict[str, SkillDoc] = {}
    if not SKILLS_DIR.is_dir():
        return skills
    for skill_path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        try:
            content = skill_path.read_text(encoding="utf-8")
        except OSError:
            continue
        name, description = _parse_frontmatter(content)
        if name:
            skills[name] = SkillDoc(name=name, description=description, body=content.strip())
    return skills


def skill_catalogue() -> str:
    """One-line-per-skill summary for the model: name + description only."""

    skills = discover_skills()
    if not skills:
        return ""
    entries = [
        f"- **{skill.name}**: {skill.description}" if skill.description else f"- **{skill.name}**"
        for skill in skills.values()
    ]
    return (
        "\n\n---\n\n## Loaded Skills (from backend/agent/skills/)\n\n"
        "The following domain skills are available. Match the user's question "
        "to the most relevant skill(s) and follow its instructions:\n\n"
        + "\n".join(entries)
    )


def match_skills(message: str, *, limit: int = 2) -> list[str]:
    """Deterministically match a message to zero or more skill names.

    Mirrors INSTRUCTIONS.md Section 2's category table. Kept in code (not
    only in prompt text) so skill selection is testable and does not depend
    on the model re-deriving the mapping correctly from a markdown table on
    every turn.
    """

    matched = [name for name, pattern in _TRIGGERS if pattern.search(message)]
    return matched[:limit]


def load_skill_playbooks(message: str, *, limit: int = 2) -> str:
    """Return the full body of whichever skill(s) match this message, if any.

    This is the piece that was previously missing at runtime: the matched
    skill's actual instructions (query IDs, interpretation rules, response
    template, common mistakes), not just its one-line description.
    """

    skills = discover_skills()
    matched = [skills[name] for name in match_skills(message, limit=limit) if name in skills]
    if not matched:
        return ""
    sections = "\n\n".join(
        f"### Active skill playbook: {skill.name}\n\n{skill.body}" for skill in matched
    )
    return (
        "\n\n---\n\n## Matched Skill Playbook(s) — follow these exactly for this turn\n\n"
        + sections
    )


__all__ = [
    "SkillDoc",
    "discover_skills",
    "load_skill_playbooks",
    "match_skills",
    "skill_catalogue",
]
