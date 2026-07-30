"""Extract only filters understood by the approved DoraDB catalogue."""

from __future__ import annotations

import re
from datetime import date
from typing import Any


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
    elif match := re.search(
        r"\b(?:squad|team)\s+[\"']?([A-Za-z][A-Za-z0-9_-]{1,30})",
        message,
        re.I,
    ):
        filters["dcpsquad"] = match.group(1).upper()
    if match := re.search(r"\b([A-Z][A-Z0-9_]+-\d+)\b", message, re.I):
        filters["jira_key"] = match.group(1).upper()
    if match := re.search(
        r"\b(?:release|fix\s*version|fixversion)\s+(?:named\s+)?[\"']?([A-Za-z0-9][A-Za-z0-9._-]*)",
        message,
        re.I,
    ):
        candidate = match.group(1)
        reserved_release_terms = {
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
        filters["status"] = match.group(1).strip().rstrip("?.")
    return filters
