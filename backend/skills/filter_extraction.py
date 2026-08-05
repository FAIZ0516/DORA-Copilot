"""Extract only filters understood by the approved DoraDB catalogue."""

from __future__ import annotations

import re
from datetime import date
from typing import Any


_DIMENSION_STOP_WORDS = {
    "all",
    "available",
    "do",
    "does",
    "every",
    "existing",
    "have",
    "is",
    "known",
    "listed",
    "recorded",
    "that",
    "the",
    "these",
    "those",
    "what",
    "which",
    "who",
    "you",
}


def _safe_named_dimension(raw_value: str) -> str | None:
    value = re.sub(r"\s+", " ", raw_value.strip(" \t\r\n\"'?.!,")).upper()
    if not value or len(value) > 40:
        return None
    words = value.lower().split()
    if not words or words[0] in _DIMENSION_STOP_WORDS:
        return None
    if any(word in _DIMENSION_STOP_WORDS for word in words):
        return None
    if not re.fullmatch(r"[A-Z][A-Z0-9_-]*(?: [A-Z][A-Z0-9_-]*)?", value):
        return None
    return value


def extract_filters(message: str, *, project_key: str = "DCPM") -> dict[str, Any]:
    filters: dict[str, Any] = {"project_key": project_key.upper()}
    years = sorted({int(year) for year in re.findall(r"\b(20\d{2})\b", message)})
    if years:
        filters["release_year"] = years
    date_candidates: list[tuple[int, int, int]] = []
    for match in re.finditer(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", message):
        date_candidates.append(
            (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        )
    for match in re.finditer(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b", message):
        date_candidates.append(
            (int(match.group(3)), int(match.group(2)), int(match.group(1)))
        )
    for year, month, day in date_candidates:
        try:
            filters["release_date"] = date(year, month, day).isoformat()
            break
        except ValueError:
            continue
    if match := re.search(r"\b(titan|jaeger)\b", message, re.I):
        filters["dcpsquad"] = match.group(1).upper()
    else:
        squad_patterns = (
            r"\b(?:squad|team)\s+(?:named|called)\s+[\"']?"
            r"([A-Za-z][A-Za-z0-9_-]*(?:\s+[A-Za-z][A-Za-z0-9_-]*)?)",
            r"\b(?:squad|team)\s+[\"']?"
            r"([A-Za-z][A-Za-z0-9_-]*(?:\s+[A-Za-z][A-Za-z0-9_-]*)?)",
            r"\b(?:for|from|of)\s+(?:the\s+)?[\"']?"
            r"([A-Za-z][A-Za-z0-9_-]*(?:\s+[A-Za-z][A-Za-z0-9_-]*)?)"
            r"[\"']?\s+(?:squad|team)\b",
        )
        for pattern in squad_patterns:
            match = re.search(pattern, message, re.I)
            if match and (squad := _safe_named_dimension(match.group(1))):
                filters["dcpsquad"] = squad
                break
    if match := re.search(r"\b([A-Z][A-Z0-9_]+-\d+)\b", message, re.I):
        filters["jira_key"] = match.group(1).upper()
    if match := re.search(
        r"\b(?:release|fix\s*version|fixversion)\s+(?:named\s+)?[\"']?([A-Za-z0-9][A-Za-z0-9._-]*)",
        message,
        re.I,
    ):
        candidate = match.group(1)
        reserved_release_terms = {
            "all",
            "available",
            "frequency",
            "cadence",
            "count",
            "date",
            "dates",
            "detail",
            "details",
            "metric",
            "metrics",
            "on",
            "recorded",
            "that",
            "the",
            "which",
            "you",
            "year",
            "years",
        }
        if (
            not re.fullmatch(r"20\d{2}", candidate)
            and candidate.lower() not in reserved_release_terms
        ):
            filters["fixversion"] = candidate
    lowered = message.lower()
    for token, value in (
        ("user stor", "User Story"),
        ("feature", "Feature"),
        ("bug", "Bug"),
        ("task", "Task"),
        ("test", "Test"),
    ):
        if token in lowered:
            filters["issuetype"] = value
            break
    if match := re.search(r"\bstatus\s+(?:is\s+)?[\"']?([A-Za-z][A-Za-z ]{1,30})", message, re.I):
        status = match.group(1).strip().rstrip("?.")
        if status.lower().split()[0] not in _DIMENSION_STOP_WORDS:
            filters["status"] = status
    return filters
