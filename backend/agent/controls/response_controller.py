"""Derives *how* the agent should communicate, kept separate from *what* it says.

This is the Response Controller described in
``AI_AGENT_PROJECT_RESTRUCTURING_GUIDE.md`` (Sections 20-41): a deterministic,
testable module that turns the current message plus already-computed planning
signals (intent, follow-up/cache state, validation) into one ``ResponsePolicy``.
The responder (``orchestrator.py`` ``_analyze``/``_respond``/``_regenerate``) consults
that policy instead of re-deriving tone/length/format/evidence rules ad hoc
inside prompt strings.

This module never calls the model and never touches the database. It only
reads signals other deterministic layers (planner, result cache, validator)
already computed, so it does not duplicate their detection logic -- see
``backend.agent.planner`` for follow-up/context resolution and
``backend.memory.result_cache`` for cache-reuse eligibility.
"""

from __future__ import annotations

import re
from typing import Any, Literal, TypedDict

from ..request_router import CLARIFICATION_REQUIRED, KNOWLEDGE_EXPLANATION


Length = Literal["short", "normal", "detailed"]
Format = Literal["paragraph", "bullets", "table", "chart_and_text", "structured_sections"]
ExplanationLevel = Literal["layman", "standard", "technical", "executive"]
EvidenceStyle = Literal[
    "none_required", "brief_support", "metric_support", "detailed_evidence", "source_reference"
]
UncertaintyMode = Literal["normal", "explicit"]
RecommendationMode = Literal["none", "evidence_based"]
FollowUpType = Literal[
    "none",
    "deeper_explanation",
    "comparison_extension",
    "time_period_change",
    "format_change",
    "correction",
    "challenge_verification",
    "clarification",
]
LanguageHint = Literal["match_user", "ms"]

# Stable product personality. Tone adapts to explicit requests; this baseline
# never changes turn to turn (guide Section 40).
PRODUCT_PERSONALITY = (
    "professional, clear, calm, non-judgmental, evidence-first, helpful, "
    "not overly verbose, not robotic"
)

# Speak to a delivery manager, not a DBA. These are appended to *every*
# rendered policy (see describe_policy), so they apply to every LLM call in
# the app -- data answers, follow-ups, knowledge answers, and error
# explanations alike. They exist here rather than buried in one prompt
# because the same rule was previously stated only in the main data prompt
# and was routinely ignored: answers leaked "dcpsquad field", "fixversion
# linkage", "column-definition document", "63,481 rows" at the user.
PLAIN_LANGUAGE_RULES: tuple[str, ...] = (
    "Write for a delivery manager, not a database administrator. Never name "
    "raw database columns, tables, views, fields, query IDs, or file names in "
    "the answer -- say 'squad' not 'the dcpsquad field', 'release' not "
    "'fixversion', 'the data' not 'the snapshot table'.",
    "Do not describe internal mechanics: no mention of joins, linkage, "
    "mappings being populated, schema, extraction, or how the query was "
    "built. Report what is or is not known, not the plumbing behind it.",
    "Express gaps in human terms. Quantify a share only when the evidence "
    "includes a valid denominator; otherwise give the known count and explain "
    "what the gap means for the answer's reliability.",
    "Lead with the answer in one plain sentence, then only the context that "
    "changes how the user should act on it. Cut caveats that don't change a "
    "decision.",
    "Sound like a helpful colleague: warm, direct, and confident about what "
    "the data does show. Do not lecture, and do not pile on disclaimers.",
    "Answer what the evidence supports before mentioning what it doesn't. "
    "If the evidence answers part of the question, give that part in full -- "
    "never refuse the whole question because one part is unavailable, and "
    "never say something 'cannot be listed' when the values are present in "
    "the evidence.",
    "A limitation is a closing footnote, not the headline. Do not open with "
    "what is missing, undocumented, or unavailable.",
)

# How the answer is laid out on screen. Separate from PLAIN_LANGUAGE_RULES
# (which governs *wording*) because this governs *shape*, and both are
# appended to every rendered policy. Without these the model emitted one
# undifferentiated prose blob -- 21 squad names run together inside a
# sentence -- which is unreadable even when every word is correct.
STRUCTURE_RULES: tuple[str, ...] = (
    "Open with a one-sentence direct answer. No preamble, no restating the "
    "question.",
    "Never run a set of values together inside a sentence. Any enumeration of "
    "three or more items (squads, statuses, years, releases, types) must be a "
    "markdown bullet list, one item per line.",
    "Keep paragraphs to three sentences or fewer, and put a blank line "
    "between them. A wall of text is a failed answer even if it is accurate.",
    # This used to offer "Worth knowing" and "Next step" as examples, and the
    # model duly produced them on answers that needed neither -- the headings
    # were being instructed, not tolerated. Which sections are admissible is
    # now decided per turn in response_decision.py.
    "When an answer has genuinely distinct parts, label them with short bold "
    "headers on their own line, naming what the section actually contains. "
    "Use only headers that carry content the request called for -- never emit "
    "an empty, generic, or padded section.",
    "Put supporting numbers next to what they describe, not in a separate "
    "recital of figures.",
    "Prefer the shortest layout that stays clear: a two-sentence answer needs "
    "no headers at all.",
)

# Guide Section 31: content is always ordered this way; it is a fixed
# constant, not something derived per turn.
PRIORITY_ORDER: tuple[str, ...] = (
    "what answers the user's question",
    "highest decision impact",
    "strongest evidence",
    "important risks/limitations",
    "secondary detail",
)


class ResponsePolicy(TypedDict):
    tone: str
    length: Length
    format: Format
    explanation_level: ExplanationLevel
    language: LanguageHint
    is_follow_up: bool
    follow_up_type: FollowUpType
    context_reference: bool
    evidence_style: EvidenceStyle
    uncertainty_mode: UncertaintyMode
    recommendation_mode: RecommendationMode
    priority_order: tuple[str, ...]
    suggest_next_action: bool


_SHORT_REQUEST = re.compile(
    r"\b(briefly|brief|in short|short answer|quick(?:ly)?|tl;?dr|one line|"
    r"just the (?:answer|number)|only the answer)\b",
    re.I,
)
_DETAILED_REQUEST = re.compile(
    r"\b(detail(?:ed)?|in.?depth|thorough(?:ly)?|comprehensive|deep dive|"
    r"explain (?:everything|fully|in full))\b",
    re.I,
)
_TABLE_REQUEST = re.compile(
    # Deliberately requires an explicit *format* request ("as a table",
    # "make it a table"), not a bare "table"/"tabular" -- this app's domain
    # is full of database tables, so "what does the Jira issues table
    # represent" must not be misread as a formatting instruction the way a
    # bare `\btable\b` match previously did (it told the LLM "Answer
    # format: table" and produced an unreadable table for a prose answer).
    r"\b(?:make (?:it|this)|put (?:it|this)(?: in)?|show (?:it|this)|"
    r"display (?:it|this)|format (?:it|this))\s+(?:as\s+)?a\s+table\b"
    r"|\bas a table\b|\bin a table\b|\bin tabular form(?:at)?\b|"
    r"\btable format\b|\bas tabular\b"
    r"|\braw data\b|\bevidence table\b|\bdata rows?\b|\brecords?\b|"
    r"\bspreadsheet\b|\bcsv\b",
    re.I,
)
_BULLET_REQUEST = re.compile(r"\b(bullet(?:s|ed)?(?: points?)?|as a list)\b", re.I)
_PARAGRAPH_REQUEST = re.compile(
    r"\b(as a paragraph|in paragraph form|no bullets|without bullet points|plain text)\b",
    re.I,
)
_TECHNICAL_REQUEST = re.compile(r"\b(technical|under the hood|implementation detail)\b", re.I)
_EXECUTIVE_REQUEST = re.compile(
    r"\b(executive summary|for leadership|for management|high.?level summary)\b", re.I
)
_LAYMAN_REQUEST = re.compile(
    r"\b(simply|in simple terms|explain like i'?m|non.?technical|plain english)\b", re.I
)
_CORRECTION = re.compile(
    r"\b(that'?s (?:wrong|incorrect|not right)|that is (?:wrong|incorrect)|"
    r"you'?re wrong|not correct|actually,? it'?s|i meant|correction:|"
    r"no,? (?:it'?s|that'?s))\b",
    re.I,
)
_CHALLENGE = re.compile(
    r"\b(are you sure|double.?check|verify (?:that|this)|how do you know|"
    r"prove it|what'?s your source|source\??$)\b",
    re.I,
)
_REFRESH = re.compile(r"\b(current|latest|refresh|refreshed|rerun|re-run|updated)\b", re.I)
_DEEPER = re.compile(r"\b(why|explain|elaborate|break\s*down|what do(?:es)? that mean)\b", re.I)
_COMPARISON_EXTENSION = re.compile(
    r"\b(compare (?:them|that|those)|which one|what about)\b", re.I
)
# Common Malay function words. Deliberately small and precision-first: a
# false negative just falls back to mirroring the user's language via the
# model prompt; a false positive would wrongly force a language switch.
_MALAY_SIGNAL = re.compile(
    r"\b(apa|macam mana|bagaimana|berapa|ada tak|boleh tak|tolong|"
    r"terima kasih|kenapa|yang mana|squad mana|tak ada)\b",
    re.I,
)


def _detect_length(message: str, *, intent: str, mode: str) -> Length:
    if _SHORT_REQUEST.search(message):
        return "short"
    if _DETAILED_REQUEST.search(message):
        return "detailed"
    if mode == "conversation" and intent in {"greeting", "help"}:
        return "short"
    if mode == "out_of_scope":
        return "short"
    if intent in {"recommendation", "comparison", "anomaly"}:
        return "normal"
    return "normal"


# Intent vocabularies have changed over time (the old deterministic planner
# emitted lowercase names like "discovery"; the model planner and Jira router
# emit uppercase ones like DATA_RETRIEVAL/LIST_SQUADS). Matching on intent
# alone silently rotted -- every live intent fell through to "paragraph", so
# the bullets/table branches were unreachable and 21-item lists were rendered
# as inline comma prose. Intent is still consulted, case-insensitively, but
# the message shape is now the primary signal because it doesn't depend on a
# vocabulary that keeps moving.
_LIST_INTENTS = frozenset(
    {"discovery", "list_squads", "list_values", "data_retrieval", "database_metadata"}
)
_TABLE_INTENTS = frozenset({"issue_listing", "comparison"})
# Same intent-vocabulary rot as _detect_format had: this only knew the
# retired lowercase "recommendation" intent, so every live request came back
# recommendation_mode="none" and evidence_style="metric_support" instead of
# "detailed_evidence". Match the message too, since intent names keep moving.
# Deliberately NOT "analysis": ANALYSIS is the generic intent the model emits
# for most data questions, so including it made every metric lookup look like
# a recommendation request.
_RECOMMENDATION_INTENTS = frozenset({"recommendation", "risk_analysis"})
_RECOMMENDATION_REQUEST = re.compile(
    r"\b(recommend|recommendation|suggest|suggestion|improve|improvement|"
    r"advice|advise|action plan|next steps?|what should (?:we|i|they)|"
    r"how (?:can|should) (?:we|i|they|the team|the squad))\b",
    re.I,
)


def _is_recommendation(message: str, intent: str) -> bool:
    return bool(_RECOMMENDATION_REQUEST.search(message)) or (
        intent.strip().lower() in _RECOMMENDATION_INTENTS
    )
_ENUMERATION_REQUEST = re.compile(
    r"\b(?:list|enumerate)\b"
    r"|\bwhat\s+\w+\s+(?:exist|are\s+there)\b"
    r"|\bshow\s+(?:me\s+)?(?:all|every)\b"
    r"|\ball\s+(?:the\s+)?(?:squads?|teams?|statuses|status|years?|releases?|"
    r"types?|values?|projects?)\b",
    re.I,
)


def _detect_format(message: str, *, intent: str) -> Format:
    normalized = intent.strip().lower()
    if _TABLE_REQUEST.search(message) or normalized in _TABLE_INTENTS:
        # A comparison across consistent metrics reads best as a table
        # (guide Section 30); an explicit table request always wins.
        return "table"
    if _PARAGRAPH_REQUEST.search(message):
        return "paragraph"
    if _BULLET_REQUEST.search(message):
        return "bullets"
    if _ENUMERATION_REQUEST.search(message) and normalized in _LIST_INTENTS:
        return "bullets"
    return "paragraph"


def _detect_explanation_level(message: str) -> ExplanationLevel:
    if _EXECUTIVE_REQUEST.search(message):
        return "executive"
    if _TECHNICAL_REQUEST.search(message):
        return "technical"
    if _LAYMAN_REQUEST.search(message):
        return "layman"
    return "standard"


def _detect_tone(message: str) -> str:
    if _EXECUTIVE_REQUEST.search(message):
        return "executive-facing"
    if _TECHNICAL_REQUEST.search(message):
        return "technical"
    return "analytical"


def _detect_follow_up(
    message: str,
    *,
    is_follow_up: bool,
    cache_reason: str,
    plan_intent: str,
) -> tuple[bool, FollowUpType]:
    if _CORRECTION.search(message):
        return True, "correction"
    if plan_intent == CLARIFICATION_REQUIRED:
        return False, "none"
    if not is_follow_up:
        return False, "none"
    if _CHALLENGE.search(message):
        return True, "challenge_verification"
    if _TABLE_REQUEST.search(message) or _BULLET_REQUEST.search(message) or _PARAGRAPH_REQUEST.search(message):
        return True, "format_change"
    if cache_reason == "explicit_refresh" or _REFRESH.search(message):
        return True, "time_period_change"
    if _COMPARISON_EXTENSION.search(message):
        return True, "comparison_extension"
    if _DEEPER.search(message):
        return True, "deeper_explanation"
    return True, "deeper_explanation"


def _detect_evidence_style(
    message: str,
    *,
    mode: str,
    intent: str,
    has_results: bool,
    follow_up_type: FollowUpType,
) -> EvidenceStyle:
    if follow_up_type == "challenge_verification":
        return "detailed_evidence"
    if mode == "out_of_scope":
        return "none_required"
    if mode == "conversation" and intent in {"greeting", "help"}:
        return "none_required"
    if intent == KNOWLEDGE_EXPLANATION:
        return "source_reference"
    if mode == "data" and has_results:
        return (
            "detailed_evidence"
            if _is_recommendation(message, intent)
            else "metric_support"
        )
    if mode == "conversation":
        return "brief_support"
    return "brief_support"


def _detect_uncertainty(
    *,
    warnings: list[str],
    results: list[dict[str, Any]],
) -> UncertaintyMode:
    if warnings:
        return "explicit"
    if results and all(int(result.get("row_count", 0)) == 0 for result in results):
        return "explicit"
    return "normal"


def _detect_language(message: str) -> LanguageHint:
    return "ms" if _MALAY_SIGNAL.search(message) else "match_user"


def derive_policy(
    message: str,
    *,
    plan: dict[str, Any],
    cache_reason: str = "",
    query_result_reused: bool = False,
    results: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
) -> ResponsePolicy:
    """Compute the per-turn response policy.

    ``plan`` is the planner's :class:`AgentPlan`. ``cache_reason`` and
    ``query_result_reused`` come from ``result_cache.choose_cache_action``,
    which already decided whether this turn reuses a prior result -- that
    decision *is* the follow-up signal; this function only classifies its
    sub-type and derives style from it, it does not re-detect follow-ups.
    """

    mode = str(plan.get("mode", ""))
    intent = str(plan.get("intent", ""))
    results = results or []
    warnings = warnings or []

    is_follow_up, follow_up_type = _detect_follow_up(
        message,
        is_follow_up=query_result_reused or bool(cache_reason == "eligible_follow_up"),
        cache_reason=cache_reason,
        plan_intent=intent,
    )
    has_results = bool(results) and any(result.get("rows") for result in results)

    return {
        "tone": _detect_tone(message),
        "length": _detect_length(message, intent=intent, mode=mode),
        "format": _detect_format(message, intent=intent),
        "explanation_level": _detect_explanation_level(message),
        "language": _detect_language(message),
        "is_follow_up": is_follow_up,
        "follow_up_type": follow_up_type,
        "context_reference": is_follow_up,
        "evidence_style": _detect_evidence_style(
            message,
            mode=mode, intent=intent, has_results=has_results, follow_up_type=follow_up_type
        ),
        "uncertainty_mode": _detect_uncertainty(warnings=warnings, results=results),
        "recommendation_mode": (
            "evidence_based"
            if _is_recommendation(message, intent) and has_results
            else "none"
        ),
        "priority_order": PRIORITY_ORDER,
        # Was true for every data answer, which is why every data answer ended
        # with a suggestion nobody asked for -- duplicating the interface's own
        # follow-up feature. A next step is content like any other: it appears
        # when the user asked for direction.
        "suggest_next_action": _is_recommendation(message, intent),
    }


def describe_policy(policy: ResponsePolicy) -> str:
    """Render the policy as compact natural-language guidance for the prompt."""

    lines = [
        f"Product personality (always stable): {PRODUCT_PERSONALITY}.",
        f"Requested tone for this turn: {policy['tone']}.",
        f"Answer length: {policy['length']}.",
        f"Answer format: {policy['format'].replace('_', ' ')}.",
        f"Explanation level: {policy['explanation_level']}.",
        f"Evidence style: {policy['evidence_style'].replace('_', ' ')}.",
    ]
    if policy["is_follow_up"]:
        lines.append(
            f"This message is a follow-up ({policy['follow_up_type'].replace('_', ' ')}). "
            "Reuse the relevant prior conclusion, do not repeat the full previous "
            "answer, and answer only the new information need."
        )
    else:
        lines.append("This is a new request; do not assume unstated prior context.")
    if policy["follow_up_type"] == "correction":
        lines.append(
            "The user is correcting a prior statement. Accept the correction if "
            "appropriate, update accordingly, and do not defend the earlier answer. "
            "If the correction conflicts with the validated data, say so and explain "
            "the conflict instead of silently agreeing."
        )
    if policy["uncertainty_mode"] == "explicit":
        lines.append(
            "State plainly what is known, what is missing, and how that affects the "
            "conclusion. Do not invent precision."
        )
    else:
        lines.append("The evidence is sufficient; do not add unnecessary uncertainty disclaimers.")
    if policy["recommendation_mode"] == "evidence_based":
        lines.append("Base every recommendation directly on the supplied evidence.")
    else:
        lines.append("Do not volunteer recommendations unless the user asked for them.")
    lines.append(
        "Respond in Bahasa Melayu."
        if policy["language"] == "ms"
        else "Respond in the same language the user used for this message."
    )
    lines.append(
        "Offer at most one or two concise, specific next steps."
        if policy["suggest_next_action"]
        else "Do not append a suggested next action, an offer of further help, "
        "or a suggested follow-up question. The interface has its own "
        "follow-up feature; duplicating it inside the answer is noise."
    )
    lines.extend(PLAIN_LANGUAGE_RULES)
    lines.extend(STRUCTURE_RULES)
    return "\n".join(f"- {line}" for line in lines)


__all__ = [
    "PLAIN_LANGUAGE_RULES",
    "STRUCTURE_RULES",
    "PRIORITY_ORDER",
    "PRODUCT_PERSONALITY",
    "ResponsePolicy",
    "derive_policy",
    "describe_policy",
]
