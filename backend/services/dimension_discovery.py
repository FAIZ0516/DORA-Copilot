"""Recognize governed catalogue and dimension-discovery questions."""

from __future__ import annotations

import re
from typing import Final


DIMENSION_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "project": ("project", "projects"),
    "squad": ("squad", "squads", "team", "teams"),
    "release_year": ("release year", "release years", "year", "years"),
    "release": (
        "release",
        "releases",
        "fix version",
        "fix versions",
        "fixversion",
        "fixversions",
    ),
    "issue_type": (
        "issue type",
        "issue types",
        "ticket type",
        "ticket types",
        "jira type",
        "jira types",
    ),
    "status": (
        "status",
        "statuses",
        "issue status",
        "issue statuses",
        "ticket status",
        "ticket statuses",
    ),
    "metric": ("metric", "metrics", "dora metric", "dora metrics"),
}

_DISCOVERY_SIGNAL = re.compile(
    r"\b("
    r"list|enumerate|name|give\s+me|"
    r"show\s+(?:me\s+)?(?:all|the(?:\s+available)?|available)|"
    r"what|which|how\s+many|available|existing|known|distinct|"
    r"do\s+you\s+have|does\s+(?:the\s+)?(?:database|dataset)\s+have"
    r")\b",
    re.I,
)
_ANALYTICAL_SIGNAL = re.compile(
    r"\b(compare|trend|performance|frequency|failure|lead time|cycle time|"
    r"ratio|chart|graph|plot|analy[sz]e|recommend|improve)\b",
    re.I,
)


def match_discovery_dimension(message: str) -> str | None:
    """Return a safe dimension ID for explicit value/catalogue discovery."""

    normalized = re.sub(r"\s+", " ", message.strip().lower())
    if not _DISCOVERY_SIGNAL.search(normalized):
        return None
    if re.search(r"\b(chart|graph|plot|visuali[sz]e)\b", normalized):
        return None

    # Analytical requests such as "show release frequency by year" must retain
    # their analytical route. Explicit catalogue words still win.
    if _ANALYTICAL_SIGNAL.search(normalized) and not re.search(
        r"\b(all|available|existing|known|distinct|how many|do you have|"
        r"supported)\b",
        normalized,
    ):
        return None

    matches: list[tuple[int, int, str]] = []
    for dimension, aliases in DIMENSION_ALIASES.items():
        for alias in aliases:
            match = re.search(rf"\b{re.escape(alias)}\b", normalized)
            if match:
                # Prefer the longest phrase, then the earliest occurrence.
                matches.append((-len(alias), match.start(), dimension))
    if not matches:
        return None
    matches.sort()
    dimension = matches[0][2]
    if dimension == "release" and re.search(
        r"\b(issues?|tickets?|user stories|features?)\b", normalized
    ):
        return None
    return dimension


def is_scope_widening_request(message: str) -> bool:
    """Identify wording that explicitly asks to leave a remembered dimension."""

    return bool(
        re.search(
            r"\b(all(?:\s+the)?|every|available|existing|known|distinct)\s+"
            r"(?:projects?|squads?|teams?|release years?|years?|releases?|"
            r"fix\s*versions?|issue types?|ticket types?|statuses|metrics?)\b",
            message,
            re.I,
        )
        or re.search(r"\b(across|among)\s+(?:all\s+)?(?:squads?|teams?|years?)\b", message, re.I)
    )


__all__ = [
    "DIMENSION_ALIASES",
    "is_scope_widening_request",
    "match_discovery_dimension",
]
