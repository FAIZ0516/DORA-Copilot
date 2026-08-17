"""What an answer is *allowed to contain* this turn.

``response_controller`` decides how the agent should sound -- tone, length,
format. This module decides what may appear at all: which blocks the current
request actually needs, and which are merely permitted if the evidence happens
to support them.

The distinction matters because the two failure modes are different. A wrong
tone is cosmetic. A padded answer is not: it buries the one line the user asked
for under "Worth knowing", a recommendation nobody wanted, and a suggested
follow-up that duplicates the frontend's own follow-up feature. Every one of
those was being *instructed* rather than merely tolerated -- the structure
rules offered "Worth knowing" as an example header, and fifteen skill templates
ended with "Would you like me to...".

An optional block is a permission, never an instruction. Nothing here tells the
model to produce a section; it only says which sections would be admissible if
the evidence already supports them.
"""

from __future__ import annotations

import re
from typing import Any, Literal, TypedDict

from ..request_router import CLARIFICATION_REQUIRED, KNOWLEDGE_EXPLANATION


ResponseProfile = Literal[
    "direct_fact",
    "list",
    "comparison",
    "explanation",
    "recommendation",
    "report",
    "clarification",
    "no_result",
    "error",
]

Block = Literal[
    "answer",
    "evidence",
    "breakdown",
    "comparison",
    "definition",
    "chart",
    "limitation",
    "recommendation",
    "next_step",
    "clarifying_question",
]


# Headings that exist to make an answer look complete rather than to carry
# anything the user asked for. Prohibited by default in every profile; a
# rewording of one of these carrying the same unrelated material is equally
# prohibited, which is why the gating is on the *block* and these are only the
# deterministic backstop.
PROHIBITED_HEADINGS: frozenset[str] = frozenset(
    {
        "worth knowing",
        "additional context",
        "other considerations",
        "more information",
        "helpful information",
        "background",
        "things to consider",
        "related insights",
        "you may also want to know",
        "next steps",
        "recommendations",
    }
)

# Which blocks each profile needs, and which it merely tolerates. Required does
# not mean "always rendered" -- a required block with no supported content is
# still omitted; it means the block is the point of the answer when it exists.
_PROFILE_BLOCKS: dict[ResponseProfile, tuple[tuple[Block, ...], tuple[Block, ...]]] = {
    # A number, a name, a date. Background and next steps are exactly what
    # turns a one-line answer into a screenful.
    "direct_fact": (("answer",), ("limitation",)),
    "list": (("answer", "breakdown"), ("limitation",)),
    "comparison": (("answer", "comparison"), ("evidence", "limitation")),
    "explanation": (("answer",), ("definition", "evidence", "limitation")),
    # Recommendations are included here because they were asked for, and each
    # one still has to trace to supplied evidence.
    "recommendation": (("answer", "recommendation"), ("evidence", "limitation")),
    "report": (
        ("answer",),
        ("evidence", "breakdown", "chart", "limitation", "recommendation", "next_step"),
    ),
    "clarification": (("clarifying_question",), ()),
    "no_result": (("answer",), ("limitation",)),
    "error": (("answer",), ("next_step",)),
}

# Wording that asks for a written report or briefing, which is the one profile
# where section scaffolding is the deliverable rather than padding.
_REPORT_REQUEST = re.compile(
    r"\b(report|briefing|write[- ]?up|summary document|executive summary|"
    r"full breakdown|deep dive)\b",
    re.I,
)
# Asking why a squad is flagged. The runtime instructions define a three-part
# shape for these -- the metrics driving the flag, the stabilising ones for
# balance, and one or two concrete actions under **What to Improve** -- so the
# actions are requested by product design even though the wording never says
# "recommend". Without this the relevance gating would strip exactly the
# section that answer is supposed to end with.
_RISK_EXPLANATION_REQUEST = re.compile(
    r"\b(?:why|what)\b[^?]{0,60}\b(?:at risk|needs attention|flagged|"
    r"risk(?:y|iest)?|struggling|behind|underperform\w*)\b"
    r"|\b(?:at risk|needs attention)\b[^?]{0,40}\bwhy\b",
    re.I,
)
_COMPARISON_REQUEST = re.compile(
    r"\b(compare|comparison|versus|vs\.?|against|difference between|"
    r"which (?:is|one is|squad is|team is) (?:better|worse|higher|lower|faster|slower))\b",
    re.I,
)
# Deliberately narrow. A bare "what is X" is nearly always a fact lookup in
# this product -- "what is the change failure rate for MBK" wants a number, not
# a definition -- so only definitional phrasing counts as an explanation.
_EXPLANATION_REQUEST = re.compile(
    r"\bexplain\b|\bdefine\b|\bmeaning of\b"
    r"|\bwhat do(?:es)?\b[^?]{0,60}\bmean\b"
    r"|\bwhat(?:'s| is) the difference\b"
    r"|\bhow (?:is|are)\b[^?]{0,40}\b(?:calculated|measured|derived|defined)\b",
    re.I,
)
_ENUMERATION_REQUEST = re.compile(
    r"\b(?:list|enumerate|name (?:all|the|every))\b"
    r"|\bwhat\s+\w+\s+(?:exist|are\s+there)\b"
    r"|\bshow\s+(?:me\s+)?(?:all|every)\b"
    r"|\ball\s+(?:the\s+)?(?:squads?|teams?|statuses|status|years?|releases?|"
    r"types?|values?|projects?)\b",
    re.I,
)


class ResponseDecision(TypedDict):
    profile: ResponseProfile
    required_blocks: tuple[Block, ...]
    optional_blocks: tuple[Block, ...]
    # Convenience for the validator: everything admissible this turn.
    allowed_blocks: frozenset[str]
    prohibited_headings: frozenset[str]
    # Whether a limitation is genuinely load-bearing, rather than decorative.
    limitation_required: bool


def _has_rows(results: list[dict[str, Any]]) -> bool:
    return any(result.get("rows") for result in results)


def choose_profile(
    message: str,
    *,
    plan: dict[str, Any],
    policy: dict[str, Any],
    results: list[dict[str, Any]],
    database_error: bool = False,
) -> ResponseProfile:
    """Pick the shape of answer this request needs.

    Ordered by how strongly each signal constrains the answer: a failure or a
    missing result determines the profile no matter what was asked, and an
    explicit request for advice or a report beats the question's grammar.
    """

    mode = str(plan.get("mode", ""))
    intent = str(plan.get("intent", ""))

    if database_error:
        return "error"
    if intent == CLARIFICATION_REQUIRED or mode == "clarification":
        return "clarification"
    if mode == "data" and results and not _has_rows(results):
        return "no_result"
    if policy.get("recommendation_mode") == "evidence_based":
        return "recommendation"
    if _RISK_EXPLANATION_REQUEST.search(message):
        # Explains the flag and closes with actions -- both are the answer.
        return "recommendation"
    if _REPORT_REQUEST.search(message):
        return "report"
    if _COMPARISON_REQUEST.search(message):
        return "comparison"
    if intent == KNOWLEDGE_EXPLANATION or mode in {"conversation", "out_of_scope"}:
        return "explanation"
    if _ENUMERATION_REQUEST.search(message) or policy.get("format") in {"bullets", "table"}:
        return "list"
    if _EXPLANATION_REQUEST.search(message):
        return "explanation"
    return "direct_fact"


def decide_response(
    message: str,
    *,
    plan: dict[str, Any],
    policy: dict[str, Any],
    results: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
    database_error: bool = False,
) -> ResponseDecision:
    """Derive this turn's admissible content from the request itself."""

    results = results or []
    warnings = warnings or []
    profile = choose_profile(
        message,
        plan=plan,
        policy=policy,
        results=results,
        database_error=database_error,
    )
    required, optional = _PROFILE_BLOCKS[profile]

    # A limitation earns its place when a validator produced one. Without that
    # signal it is decoration, and decoration at the end of a one-line answer
    # reads as doubt about the answer itself.
    limitation_required = bool(warnings)
    if limitation_required and "limitation" not in required:
        required = required + ("limitation",)
        optional = tuple(block for block in optional if block != "limitation")

    # A chart is admissible wherever one was actually produced, not only in a
    # report -- the renderer attaches it separately from the prose.
    if policy.get("format") == "chart_and_text" and "chart" not in optional:
        optional = optional + ("chart",)

    return {
        "profile": profile,
        "required_blocks": required,
        "optional_blocks": optional,
        "allowed_blocks": frozenset(required) | frozenset(optional),
        "prohibited_headings": PROHIBITED_HEADINGS,
        "limitation_required": limitation_required,
    }


# Per-profile wording for the prompt. Stated as restrictions rather than as a
# template, so the model is constrained rather than prompted to fill sections.
_PROFILE_GUIDANCE: dict[ResponseProfile, str] = {
    "direct_fact": (
        "Give the fact and stop. No background, no definitions, no "
        "recommendations, no next steps unless the user asked for them."
    ),
    "list": (
        "Return the requested values and only the context needed to read them. "
        "No unrelated background."
    ),
    "comparison": (
        "Include the compared values, the differences that matter, and any "
        "limitation that changes the comparison. Do not discuss metrics "
        "outside the comparison the user asked for."
    ),
    "explanation": (
        "Explain what was asked. Do not expand into unrelated metrics or into "
        "what else the system can do."
    ),
    "recommendation": (
        "Recommendations were requested, so include them -- and tie every one "
        "to the supplied evidence."
    ),
    "report": (
        "Include only the sections the requested scope and audience call for."
    ),
    "clarification": (
        "Ask the single smallest question needed to continue. Nothing else."
    ),
    "no_result": (
        "Say what was looked for and what finding nothing means. Do not add "
        "unrelated educational content."
    ),
    "error": ("State what failed and the one relevant recovery action. Briefly."),
}

_RELEVANCE_TEST = (
    "Before including any sentence, bullet, table, or section, it must do at "
    "least one of these: answer the question; supply evidence the answer needs; "
    "explain something the user explicitly asked to understand; state a "
    "limitation that changes how the answer should be read; give an action the "
    "user asked for; or prevent a misleading conclusion. If removing it would "
    "not make the answer less correct, less useful, or less safe, leave it out."
)


def describe_decision(decision: ResponseDecision) -> str:
    """Render the decision as prompt guidance."""

    profile = decision["profile"]
    lines = [
        f"Response profile: {profile.replace('_', ' ')}. {_PROFILE_GUIDANCE[profile]}",
        _RELEVANCE_TEST,
        (
            "Permitted content for this answer: "
            + ", ".join(sorted(decision["allowed_blocks"]))
            + ". A permitted block is permission, not an instruction -- include "
            "it only if the evidence already supports it, and never invent "
            "content to fill a section."
        ),
        (
            "Never use these headings: "
            + ", ".join(sorted(decision["prohibited_headings"]))
            + ". Do not reword one of them to smuggle in the same unrelated "
            "material."
        ),
        "Never state the same conclusion twice under different headings.",
    ]
    if decision["limitation_required"]:
        lines.append(
            "One limitation genuinely affects this result: state it once, as a "
            "closing sentence, not as an opening caveat."
        )
    else:
        lines.append(
            "Do not add a limitations section. Nothing about this result needs "
            "one."
        )
    if "recommendation" not in decision["allowed_blocks"]:
        lines.append("Do not volunteer recommendations or improvement ideas.")
    if "next_step" not in decision["allowed_blocks"]:
        lines.append(
            "Do not end with a suggested next step or an offer of further help. "
            "Do not write 'Would you like me to...', 'You can also...', or "
            "'Next, you should...'. Suggested follow-up questions are a "
            "separate feature of the interface; never put them in the answer."
        )
    return "\n".join(f"- {line}" for line in lines)


__all__ = [
    "PROHIBITED_HEADINGS",
    "Block",
    "ResponseDecision",
    "ResponseProfile",
    "choose_profile",
    "decide_response",
    "describe_decision",
]
