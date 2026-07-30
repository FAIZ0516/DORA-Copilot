"""Fast deterministic intent signals that constrain generative planning."""

from __future__ import annotations

import re
from typing import Literal, TypedDict


IntentName = Literal[
    "metric_lookup",
    "comparison",
    "trend",
    "anomaly",
    "explanation",
    "release_drilldown",
    "issue_listing",
    "ratio",
    "visualization",
    "recommendation",
    "greeting",
    "general_conversation",
    "help",
    "out_of_scope",
]


class IntentMatch(TypedDict):
    name: IntentName
    confidence: float
    visualization_requested: bool


_UNSAFE = re.compile(
    r"\b(drop|delete|truncate|update|insert|alter|create|grant|revoke)\b.{0,30}\b(table|database|from|into|set|role)\b",
    re.I,
)
_DOMAIN = re.compile(
    r"\b(dora|doradb|releases?|deployments?|deploy|change failure|failure rate|"
    r"lead time|load time|cycle time|jira|feature|user stor(?:y|ies)|"
    r"delivery|throughput|metrics?|projects?|issues?|tickets?|sprints?|squads?|"
    r"titan|jaeger|fixversion)\b",
    re.I,
)


def classify_intent(message: str) -> IntentMatch:
    """Return a transparent baseline classification for steering and fallback."""

    lowered = message.lower()
    visualization = bool(
        re.search(r"\b(chart|graph|plot|diagram|visuali[sz]e|bar|line|pie|scatter)\b", lowered)
    )
    if _UNSAFE.search(message):
        name: IntentName = "out_of_scope"
        confidence = 1.0
    elif re.fullmatch(
        r"\s*(hi|hello|hey|good\s+(morning|afternoon|evening)|"
        r"assalamualaikum|salam)[!.?\s]*",
        lowered,
    ):
        name, confidence = "greeting", 0.99
    elif re.search(r"\b(help|what can you do|capabilit(?:y|ies)|examples?)\b", lowered):
        name, confidence = "help", 0.98
    elif not _DOMAIN.search(message):
        name, confidence = "general_conversation", 0.99
    elif re.search(r"\b(ratio|per feature|story.to.feature)\b", lowered):
        name, confidence = "ratio", 0.96
    elif re.search(r"\b(anomal|outlier|spike|unusual|unexpected)\b", lowered):
        name, confidence = "anomaly", 0.92
    elif re.search(
        r"\b(recommend|suggest|improv(?:e|ement)|action plan|next steps?|"
        r"what should|how (?:can|should) (?:we|the team|the squad))\b",
        lowered,
    ):
        name, confidence = "recommendation", 0.95
    elif re.search(r"\b(why|cause|driver|reason)\b", lowered):
        name, confidence = "explanation", 0.9
    elif re.search(
        r"\b(?:list|show|which)\b.{0,35}\b(?:issues?|tickets?|jira keys?|"
        r"user stor(?:y|ies)|features?)\b|\b(?:ticket|jira key)\b",
        lowered,
    ):
        name, confidence = "issue_listing", 0.86
    elif re.search(r"\b(compare|versus|vs\.?|difference|change between)\b", lowered):
        name, confidence = "comparison", 0.9
    elif re.search(r"\b(trend|over time|year over year|yoy|improv|declin)\b", lowered):
        name, confidence = "trend", 0.88
    elif re.search(r"\b(release|fixversion)\b", lowered) and re.search(
        r"\b(detail|drill|timeline|specific|date)\b", lowered
    ):
        name, confidence = "release_drilldown", 0.86
    elif visualization:
        name, confidence = "visualization", 0.84
    elif re.search(
        r"\b(dora|release|deploy|failure|lead time|load time|cycle time|jira|"
        r"feature|user stor|delivery|throughput|metric|project|issue|sprint|"
        r"squad|titan|jaeger)\b",
        lowered,
    ):
        name, confidence = "metric_lookup", 0.72
    else:
        name, confidence = "general_conversation", 0.82
    return {
        "name": name,
        "confidence": confidence,
        "visualization_requested": visualization,
    }
